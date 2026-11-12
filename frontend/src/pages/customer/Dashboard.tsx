import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { ChevronUp, Download, Eye, EyeOff, HelpCircle, Phone, RefreshCw } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useSiteSettings } from '../../hooks/useSiteSettings';
import { billingAPI, networkAPI, paymentAPI } from '../../services/api';
import {
    EmptyState, MpesaPayCard, Panel, PanelHeader, ShellHeader, Skeleton, StatusBadge,
    formatDateEAT, formatKES, type PayState,
} from '../../components/savanna';
import { BarTrend } from '../../components/savanna/charts';

const GB = 1024 ** 3;
const eatDayKey = (d: Date) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Nairobi' }).format(d);

function formatRate(kbps: number) {
    return kbps >= 1000 ? `${(kbps / 1000).toFixed(1)} Mbps` : `${Math.round(kbps)} Kbps`;
}

export default function CustomerDashboard() {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { user } = useAuthStore();
    const { data: siteSettings } = useSiteSettings();
    const [showPassword, setShowPassword] = useState(false);

    const { data: subscription, isLoading: subLoading } = useQuery({
        queryKey: ['subscription'],
        queryFn: async () => {
            try {
                return (await billingAPI.getCurrentSubscription()).data;
            } catch {
                return null; // 404 = no active plan
            }
        },
    });

    const { data: usageRecords, isLoading: usageLoading } = useQuery({
        queryKey: ['dashboard-usage'],
        queryFn: async () => {
            const res = await billingAPI.getUsage();
            return (res.data.results || res.data) as any[];
        },
    });

    const { data: transactions } = useQuery({
        queryKey: ['dashboard-transactions'],
        queryFn: async () => {
            const res = await billingAPI.getTransactions();
            return (res.data.results || res.data) as any[];
        },
    });

    const { data: plans } = useQuery({
        queryKey: ['customer-plans'],
        queryFn: async () => {
            const res = await billingAPI.getPlans();
            return (res.data.results || res.data) as any[];
        },
    });

    // Live session, straight from the router, every 5s. Byte counters are
    // cumulative session totals, so the current speed is the difference
    // between two polls.
    const { data: liveSession } = useQuery({
        queryKey: ['my-session'],
        queryFn: async () => (await networkAPI.getMySession()).data,
        refetchInterval: 5000,
    });

    const [liveSpeed, setLiveSpeed] = useState<{ up: number; down: number } | null>(null);
    const prevSessionRef = useRef<{ up: number; down: number; ts: number } | null>(null);
    useEffect(() => {
        if (!liveSession?.active) {
            setLiveSpeed(null);
            prevSessionRef.current = null;
            return;
        }
        const now = Date.now();
        const prev = prevSessionRef.current;
        if (prev && now > prev.ts) {
            const secs = (now - prev.ts) / 1000;
            setLiveSpeed({
                up: (Math.max(0, liveSession.upload_bytes - prev.up) * 8) / secs / 1000,
                down: (Math.max(0, liveSession.download_bytes - prev.down) * 8) / secs / 1000,
            });
        }
        prevSessionRef.current = { up: liveSession.upload_bytes, down: liveSession.download_bytes, ts: now };
    }, [liveSession]);

    // Usage: last 14 days as daily totals, and this subscription period's total.
    const { daily, cycleGb } = useMemo(() => {
        const byDay = new Map<string, number>();
        let cycle = 0;
        const cycleStart = subscription?.start_date ? new Date(subscription.start_date).getTime() : null;
        for (const r of usageRecords || []) {
            const bytes = Number(r.upload_bytes || 0) + Number(r.download_bytes || 0);
            const key = eatDayKey(new Date(r.start_time));
            byDay.set(key, (byDay.get(key) || 0) + bytes);
            if (cycleStart && new Date(r.start_time).getTime() >= cycleStart) cycle += bytes;
        }
        const days = [];
        for (let i = 13; i >= 0; i--) {
            const d = new Date(Date.now() - i * 86_400_000);
            const key = eatDayKey(d);
            days.push({ day: key.slice(8), gb: Number(((byDay.get(key) || 0) / GB).toFixed(2)) });
        }
        return { daily: days, cycleGb: cycle / GB };
    }, [usageRecords, subscription?.start_date]);

    // Plan period progress.
    const plan = subscription?.plan;
    const now = Date.now();
    const start = subscription?.start_date ? new Date(subscription.start_date).getTime() : null;
    const end = subscription?.expiry_date ? new Date(subscription.expiry_date).getTime() : null;
    const msLeft = end ? Math.max(0, end - now) : 0;
    const daysLeft = Math.ceil(msLeft / 86_400_000);
    const hoursLeft = Math.ceil(msLeft / 3_600_000);
    const timeLeft = daysLeft >= 2 ? `${daysLeft} days` : `${hoursLeft} hour${hoursLeft === 1 ? '' : 's'}`;
    const progress = start && end && end > start ? Math.min(100, Math.max(0, ((now - start) / (end - start)) * 100)) : 0;

    // Pay & renew: the current plan, or (no plan) the cheapest one for
    // this customer's service type, sent as a real STK prompt; then poll
    // the request until M-Pesa reports back.
    const servicePlans = (plans || []).filter((p) => p.is_active !== false && p.service_type === (plan?.service_type || user?.service_type));
    const payPlan = plan || [...servicePlans].sort((a, b) => Number(a.price) - Number(b.price))[0];
    const [payState, setPayState] = useState<PayState>('idle');
    const [payMessage, setPayMessage] = useState<string>();
    const pollRef = useRef<number>();
    useEffect(() => () => window.clearInterval(pollRef.current), []);

    const pay = async (phone: string) => {
        if (!payPlan) return;
        setPayState('sending');
        setPayMessage(undefined);
        try {
            const res = await paymentAPI.initiatePayment({ plan_id: payPlan.id, phone_number: phone });
            const requestId = res.data.payment_request_id;
            setPayState('pending');
            const started = Date.now();
            window.clearInterval(pollRef.current);
            pollRef.current = window.setInterval(async () => {
                try {
                    const { data } = await paymentAPI.getPaymentStatus(requestId);
                    if (data.status === 'completed') {
                        window.clearInterval(pollRef.current);
                        setPayState('success');
                        queryClient.invalidateQueries({ queryKey: ['subscription'] });
                        queryClient.invalidateQueries({ queryKey: ['dashboard-transactions'] });
                    } else if (['failed', 'timeout', 'cancelled'].includes(data.status)) {
                        window.clearInterval(pollRef.current);
                        setPayState('failed');
                        setPayMessage(data.response_description || 'The payment was cancelled or timed out.');
                    } else if (Date.now() - started > 120_000) {
                        window.clearInterval(pollRef.current);
                        setPayState('failed');
                        setPayMessage("We haven't heard back from M-Pesa. If you paid, your plan renews as soon as it confirms.");
                    }
                } catch { /* keep polling */ }
            }, 3000);
        } catch (err: any) {
            setPayState('failed');
            setPayMessage(err.response?.data?.error || 'Could not send the payment prompt.');
        }
    };

    const upgrades = servicePlans
        .filter((p) => plan && Number(p.price) > Number(plan.price))
        .sort((a, b) => Number(a.price) - Number(b.price))
        .slice(0, 3);

    const credentialUsername = user?.pppoe_username || user?.hotspot_username || user?.username;
    const credentialPassword = user?.pppoe_password || user?.hotspot_password;
    const firstName = user?.first_name || user?.username || '';
    const online = !!liveSession?.active;

    return (
        <div className="space-y-[18px]">
            <ShellHeader
                title={
                    <span className="block">
                        <span className="mb-3 block text-[15px] font-medium tracking-normal text-white/75">Habari, {firstName}</span>
                        {subLoading ? (
                            <span className="block text-[34px] leading-tight sm:text-[52px]">&nbsp;</span>
                        ) : plan ? (
                            <span className="block text-[34px] leading-[1.08] sm:text-[52px]">
                                {online ? "You're connected." : 'Your plan is active.'}
                                <br />
                                <span className="text-[#8FD9A8]">{timeLeft}</span> left on your plan.
                            </span>
                        ) : (
                            <span className="block text-[34px] leading-[1.08] sm:text-[52px]">
                                No active plan.
                                <br />
                                <span className="text-[#F4C542]">Pick one</span> to get online.
                            </span>
                        )}
                    </span>
                }
            />

            <div className="grid grid-cols-1 gap-[18px] lg:grid-cols-[2fr_1fr]">
                {/* Left column */}
                <div className="space-y-[18px]">
                    <Panel>
                        {subLoading ? <Skeleton className="h-48 w-full" /> : plan ? (
                            <>
                                <div className="flex items-start justify-between gap-3">
                                    <div>
                                        <p className="text-[13.5px] text-muted-foreground">Current plan</p>
                                        <h2 className="mt-1 text-[28px] font-extrabold leading-tight text-foreground">{plan.name}</h2>
                                    </div>
                                    <StatusBadge status={daysLeft <= 3 ? 'expiring' : 'active'} />
                                </div>
                                <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
                                    <div>
                                        <p className="text-[13px] text-muted-foreground">Speed</p>
                                        <p className="num text-[22px] font-extrabold text-foreground">
                                            {plan.download_speed} / {plan.upload_speed} <span className="text-[13px] font-medium text-muted-foreground">Mbps</span>
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-[13px] text-muted-foreground">Renews</p>
                                        <p className="num text-[22px] font-extrabold text-foreground">{formatDateEAT(subscription.expiry_date)}</p>
                                    </div>
                                    <div>
                                        <p className="text-[13px] text-muted-foreground">Price</p>
                                        <p className="num text-[22px] font-extrabold text-foreground">{formatKES(plan.price)}</p>
                                    </div>
                                </div>
                                <div className="mt-6 flex justify-between text-[13px] text-muted-foreground">
                                    <span>Paid {formatDateEAT(subscription.start_date, { day: 'numeric', month: 'short' })}</span>
                                    <span>{timeLeft} left · renews {formatDateEAT(subscription.expiry_date, { day: 'numeric', month: 'short' })}</span>
                                </div>
                                <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-chip" role="progressbar" aria-label="Plan period used" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}>
                                    <div className="h-full rounded-full bg-mpesa" style={{ width: `${progress}%` }} />
                                </div>
                                <div className="mt-5 flex flex-wrap items-center gap-3">
                                    <Link to="/plans" className="inline-flex h-11 items-center gap-2 rounded-full border border-input px-5 text-[14.5px] font-semibold text-foreground hover:bg-accent">
                                        <ChevronUp className="h-4 w-4" /> Change plan
                                    </Link>
                                    <Link to="/usage" className="inline-flex h-11 items-center gap-2 px-2 text-[14.5px] font-medium text-muted-foreground hover:text-foreground">
                                        View usage history
                                    </Link>
                                </div>
                            </>
                        ) : (
                            <EmptyState
                                message="You don't have an active plan right now."
                                action={<Link to="/plans" className="inline-flex h-11 items-center rounded-full bg-primary px-5 text-[14.5px] font-semibold text-primary-foreground">Browse plans</Link>}
                            />
                        )}
                    </Panel>

                    <Panel>
                        <PanelHeader
                            title="Data usage"
                            subtitle={plan?.data_limit_gb ? `Last 14 days · plan cap ${plan.data_limit_gb} GB` : plan?.fup_limit_gb ? `Last 14 days · fair use ${plan.fup_limit_gb} GB` : 'Last 14 days'}
                            action={
                                <div className="text-right">
                                    <p className="num text-[26px] font-extrabold leading-none text-foreground">
                                        {cycleGb.toFixed(1)} <span className="text-[14px] font-medium text-muted-foreground">GB</span>
                                    </p>
                                    <p className="mt-1 text-[12.5px] text-faint">this plan period</p>
                                </div>
                            }
                        />
                        {usageLoading ? <Skeleton className="h-[240px] w-full" /> : (
                            <BarTrend data={daily} xKey="day" yKey="gb" name="Used" formatTooltip={(v) => `${v} GB`} />
                        )}
                    </Panel>

                    <div className="grid grid-cols-1 gap-[18px] md:grid-cols-2">
                        <Panel>
                            <PanelHeader title="Your connection" action={<StatusBadge status={online ? 'online' : 'offline'} />} />
                            <dl className="grid grid-cols-2 gap-x-4 gap-y-4 text-[14px]">
                                <div>
                                    <dt className="text-[13px] text-muted-foreground">Current speed</dt>
                                    <dd className="num font-semibold text-foreground">{online && liveSpeed ? `↓ ${formatRate(liveSpeed.down)}` : '—'}</dd>
                                </div>
                                <div>
                                    <dt className="text-[13px] text-muted-foreground">Uptime</dt>
                                    <dd className="num font-semibold text-foreground">{online ? (liveSession.uptime || '—') : '—'}</dd>
                                </div>
                                <div>
                                    <dt className="text-[13px] text-muted-foreground">IP address</dt>
                                    <dd className="num font-semibold text-foreground">{online ? (liveSession.address || '—') : '—'}</dd>
                                </div>
                                <div>
                                    <dt className="text-[13px] text-muted-foreground">Service</dt>
                                    <dd className="font-semibold uppercase text-foreground">{user?.service_type || '—'}</dd>
                                </div>
                                <div className="col-span-2">
                                    <dt className="text-[13px] text-muted-foreground">Login</dt>
                                    <dd className="flex items-center gap-2 font-semibold text-foreground">
                                        <span className="truncate">{credentialUsername || '—'}</span>
                                        {credentialPassword && (
                                            <>
                                                <span className="text-faint">·</span>
                                                <span className="num font-mono">{showPassword ? credentialPassword : '••••••••'}</span>
                                                <button
                                                    onClick={() => setShowPassword((v) => !v)}
                                                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                                                    className="text-muted-foreground hover:text-foreground"
                                                >
                                                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                                </button>
                                            </>
                                        )}
                                    </dd>
                                </div>
                            </dl>
                            {liveSession?.router_offline && (
                                <p className="mt-4 text-[12.5px] text-warn">We can't reach your area's router right now; status may be out of date.</p>
                            )}
                            <button
                                onClick={() => queryClient.invalidateQueries({ queryKey: ['my-session'] })}
                                className="mt-5 inline-flex h-10 w-full items-center justify-center gap-2 rounded-full border border-input text-[14px] font-semibold text-foreground hover:bg-accent"
                            >
                                <RefreshCw className="h-4 w-4" /> Refresh status
                            </button>
                        </Panel>

                        <Panel>
                            <PanelHeader title="Recent payments" action={<Link to="/orders" className="text-[13.5px] font-semibold text-primary">View all</Link>} />
                            {!transactions?.length ? (
                                <EmptyState message="No payments yet." />
                            ) : (
                                <div>
                                    {transactions.slice(0, 3).map((t) => (
                                        <div key={t.id} className="flex items-center justify-between gap-3 border-t border-border-soft py-3 first:border-t-0">
                                            <div className="min-w-0">
                                                <p className="num truncate font-semibold uppercase text-foreground">{t.mpesa_receipt_number || t.transaction_id}</p>
                                                <p className="text-[12.5px] text-muted-foreground">
                                                    {formatDateEAT(t.created_at)} · {t.payment_method === 'mpesa' ? 'M-Pesa' : t.payment_method}
                                                    {t.status !== 'completed' && <span className="text-warn"> · {t.status}</span>}
                                                </p>
                                            </div>
                                            <p className="num shrink-0 font-bold text-foreground">{formatKES(t.amount)}</p>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </Panel>
                    </div>
                </div>

                {/* Right column */}
                <div className="space-y-[18px]">
                    {payPlan ? (
                        <MpesaPayCard
                            title={plan ? 'Pay & renew' : 'Buy a plan'}
                            amount={Number(payPlan.price)}
                            amountNote={payPlan.name}
                            phone={user?.phone_number || ''}
                            onPay={pay}
                            state={payState}
                            message={payMessage}
                            onReset={() => { setPayState('idle'); setPayMessage(undefined); }}
                            paybill={siteSettings?.payment_shortcode ? {
                                shortcode: siteSettings.payment_shortcode,
                                type: siteSettings.payment_shortcode_type,
                                account: user?.username,
                                registeredPhone: user?.phone_number
                                    ? user.phone_number.replace(/^254/, '0').replace(/^(\d{4})(\d{3})(\d{3})$/, '$1 $2 $3')
                                    : undefined,
                            } : null}
                            disabled={payPlan.service_type === 'static'}
                        />
                    ) : (
                        <Panel><EmptyState message="No plans available to buy right now." /></Panel>
                    )}

                    {siteSettings?.support_phone && (
                        <div className="rounded-card bg-sunset p-[22px] text-white shadow-card">
                            <div className="flex gap-3">
                                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-white/20">
                                    <HelpCircle className="h-5 w-5" strokeWidth={1.8} />
                                </span>
                                <div>
                                    <p className="text-[16px] font-bold">Need help?</p>
                                    <p className="mt-0.5 text-[13.5px] text-white/85">Call or WhatsApp our support team.</p>
                                    <a
                                        href={`tel:${siteSettings.support_phone.replace(/\s/g, '')}`}
                                        className="mt-4 inline-flex h-11 items-center gap-2 rounded-full bg-white px-5 text-[14.5px] font-semibold text-sunset"
                                    >
                                        <Phone className="h-4 w-4" /> {siteSettings.support_phone}
                                    </a>
                                </div>
                            </div>
                        </div>
                    )}

                    {upgrades.length > 0 && (
                        <Panel>
                            <PanelHeader title="Upgrade & save" />
                            <div>
                                {upgrades.map((p) => (
                                    <button
                                        key={p.id}
                                        onClick={() => navigate('/plans')}
                                        className="flex w-full items-center justify-between gap-3 border-t border-border-soft py-3.5 text-left first:border-t-0"
                                    >
                                        <span className="min-w-0">
                                            <span className="block truncate font-semibold text-foreground">{p.name}</span>
                                            <span className="block text-[12.5px] text-muted-foreground">{p.download_speed}/{p.upload_speed} Mbps{p.description ? ` · ${p.description}` : ''}</span>
                                        </span>
                                        <span className="num shrink-0 font-bold text-foreground">{formatKES(p.price)}</span>
                                    </button>
                                ))}
                            </div>
                        </Panel>
                    )}

                    {transactions?.length ? (
                        <Link to="/orders" className="flex items-center justify-center gap-2 text-[13.5px] font-semibold text-muted-foreground hover:text-foreground">
                            <Download className="h-4 w-4" /> All receipts
                        </Link>
                    ) : null}
                </div>
            </div>
        </div>
    );
}
