import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import { voucherAPI, billingAPI, paymentAPI } from '../../services/api';
import { useSiteSettings } from '../../hooks/useSiteSettings';
import { formatPlanDuration } from '../../components/savanna/format';

/*
 * Hotspot captive portal (design/HANDOFF.md §3, "Savanna"). Walk-up phone
 * users behind a MikroTik walled garden where only the portal domain is
 * reachable, so this page stays deliberately light: no chart or UI-kit
 * imports, icons are inline SVG, one mobile column (max 420px).
 */

interface Plan {
    id: number;
    name: string;
    price: string;
    description: string;
    download_speed: number;
    upload_speed: number;
    duration_value: number;
    duration_unit: 'minutes' | 'hours' | 'days' | 'months';
}

const svg = { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true };
const WifiIcon = ({ size = 20 }: { size?: number }) => (
    <svg {...svg} width={size} height={size} strokeWidth={2.4}><path d="M5 12.55a11 11 0 0 1 14.08 0" /><path d="M8.53 16.11a6 6 0 0 1 6.95 0" /><path d="M2 8.82a15 15 0 0 1 20 0" /><circle cx="12" cy="20" r="1" fill="currentColor" /></svg>
);
const TicketIcon = () => (
    <svg {...svg}><path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z" /><path d="M13 5v2M13 17v2M13 11v2" /></svg>
);
const Spinner = ({ className = '' }: { className?: string }) => (
    <svg {...svg} className={`animate-spin ${className}`}><path d="M21 12a9 9 0 1 1-6.22-8.56" /></svg>
);
const CheckIcon = () => <svg {...svg} width={36} height={36} strokeWidth={2.4}><path d="M20 6 9 17l-5-5" /></svg>;

const durationText = (p: Plan) => formatPlanDuration(p);
const kes = (v: string | number) => new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(Number(v));

/** "712 345 678", "0712345678", "254712345678" -> "0712345678" (the format guest accounts have always used). */
function localPhone(input: string): string | null {
    const d = input.replace(/\D/g, '');
    const nine = d.startsWith('254') ? d.slice(3) : d.startsWith('0') ? d.slice(1) : d;
    return /^[17]\d{8}$/.test(nine) ? `0${nine}` : null;
}

const CaptivePortal: React.FC = () => {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const { data: siteSettings } = useSiteSettings();

    const mac = searchParams.get('mac') || searchParams.get('mac_esc');
    const linkLogin = searchParams.get('link-login') || searchParams.get('link_login');
    const linkOrig = searchParams.get('link-orig') || searchParams.get('link_orig');

    // Default to the IP if link-login is missing
    const loginActionUrl = linkLogin ? decodeURIComponent(linkLogin) : 'http://10.5.50.1/login';

    const [loading, setLoading] = useState(true);
    const [status, setStatus] = useState<'checking' | 'active' | 'inactive'>('checking');
    const [message, setMessage] = useState('Checking connection status…');
    const [voucherCode, setVoucherCode] = useState('');
    const [redeeming, setRedeeming] = useState(false);
    const [pppoeCredentials, setPppoeCredentials] = useState<{ username: string; password: string } | null>(null);
    const [mpesaCode, setMpesaCode] = useState('');
    const [reactivating, setReactivating] = useState(false);
    const [showReconnect, setShowReconnect] = useState(false);

    // Guest checkout
    const [plans, setPlans] = useState<Plan[]>([]);
    const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
    const [phoneNumber, setPhoneNumber] = useState('');
    const [processingPayment, setProcessingPayment] = useState(false);
    const [paymentSuccess, setPaymentSuccess] = useState(false);
    const [pollTimedOut, setPollTimedOut] = useState(false);

    // Relative path so the portal works via IP or domain (nginx proxies /api).
    const API_URL = '/api';

    useEffect(() => {
        checkStatus();
        fetchPlans();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [mac]);

    // After a payment is initiated, keep re-checking automatically until
    // the subscription shows up (checkStatus then logs the device in) or
    // ~90s pass: 18 tries * 5s covers STK push + PIN entry + callback.
    useEffect(() => {
        if (!paymentSuccess || pollTimedOut || status === 'active') return;
        let attempts = 0;
        const interval = setInterval(async () => {
            attempts += 1;
            await checkStatus();
            if (attempts >= 18) {
                clearInterval(interval);
                setPollTimedOut(true);
            }
        }, 5000);
        return () => clearInterval(interval);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [paymentSuccess, pollTimedOut, status]);

    const fetchPlans = async () => {
        try {
            const response = await billingAPI.getPlans();
            const data = response.data.results ? response.data.results : response.data;
            // Only Hotspot plans belong here -- PPPoE needs a configured
            // router login and Static IP is technician-assigned.
            const hotspot = Array.isArray(data) ? data.filter((p: any) => p.service_type === 'hotspot') : [];
            hotspot.sort((a: Plan, b: Plan) => Number(a.price) - Number(b.price));
            setPlans(hotspot);
            if (hotspot.length && !selectedPlan) setSelectedPlan(hotspot[0]);
        } catch (error) {
            console.error('Failed to fetch plans', error);
            setPlans([]);
        }
    };

    const checkStatus = async () => {
        if (!mac) {
            setLoading(false);
            setStatus('inactive');
            setMessage('No device detected. Please connect to WiFi properly.');
            return;
        }
        try {
            const response = await axios.get(`${API_URL}/network/hotspot/status/?mac=${mac}`);
            if (response.data.active) {
                setStatus('active');
                setMessage('Plan found. Logging you in…');
                doLogin(response.data.username, response.data.password);
            } else {
                setStatus('inactive');
                setMessage('No active subscription found.');
                setLoading(false);
                // Clear stale tokens so payment requests go out as a guest.
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
            }
        } catch (error) {
            console.error('Status check failed:', error);
            setStatus('inactive');
            setMessage('Welcome! Please buy a plan to connect.');
            setLoading(false);
        }
    };

    const doLogin = (username: string, password: string) => {
        // loginActionUrl falls back to the default gateway login URL when
        // link-login wasn't in the redirect; submitting is still right then.
        if (!linkLogin) {
            console.warn('No link-login param in the captive portal redirect -- submitting to the default gateway login URL instead.');
        }
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = loginActionUrl;
        for (const [name, value] of [['username', username], ['password', password], ['dst', linkOrig || 'http://google.com']]) {
            const field = document.createElement('input');
            field.type = 'hidden';
            field.name = name;
            field.value = value;
            form.appendChild(field);
        }
        document.body.appendChild(form);
        form.submit();
    };

    const handleRedeemVoucher = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!voucherCode.trim()) return;
        setRedeeming(true);
        setPppoeCredentials(null);
        try {
            const response = await voucherAPI.redeem(voucherCode.trim(), mac || undefined);
            toast.success(response.data.message);
            if (response.data.tokens) {
                localStorage.setItem('access_token', response.data.tokens.access);
                localStorage.setItem('refresh_token', response.data.tokens.refresh);
            }
            // Use the credentials actually provisioned on the router.
            const credentials = response.data.credentials;
            const serviceType = response.data.customer?.service_type;
            const isHotspotCapable = serviceType === 'hotspot' || serviceType === 'both';
            if (isHotspotCapable && credentials?.hotspot_username) {
                doLogin(credentials.hotspot_username, credentials.hotspot_password);
            } else if (credentials?.pppoe_username) {
                // PPPoE can't log in through a captive portal; show the
                // details the customer's own router needs to dial in.
                setPppoeCredentials({ username: credentials.pppoe_username, password: credentials.pppoe_password });
            } else if (mac) {
                checkStatus();
            }
            setVoucherCode('');
        } catch (error: any) {
            toast.error(error.response?.data?.error || 'Failed to redeem voucher');
        } finally {
            setRedeeming(false);
        }
    };

    const handleReactivate = async (e: React.FormEvent) => {
        e.preventDefault();
        setReactivating(true);
        try {
            const response = await paymentAPI.reactivateSession(mpesaCode.trim(), mac || undefined);
            toast.success(response.data.message);
            doLogin(response.data.username, response.data.password);
            setMpesaCode('');
        } catch (error: any) {
            toast.error(error.response?.data?.error || 'Failed to reconnect');
        } finally {
            setReactivating(false);
        }
    };

    const phone = localPhone(phoneNumber);

    const handleBuyPlan = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!selectedPlan || !phone) return;
        setProcessingPayment(true);
        try {
            await paymentAPI.initiatePayment({ plan_id: selectedPlan.id, phone_number: phone, mac_address: mac || undefined });
            setPollTimedOut(false);
            setPaymentSuccess(true);
        } catch (error: any) {
            toast.error(error.response?.data?.error || 'Payment initiation failed');
        } finally {
            setProcessingPayment(false);
        }
    };

    const resetPayment = () => { setPaymentSuccess(false); setPollTimedOut(false); };
    const company = siteSettings?.company_name || 'WiFi';

    if (loading || status === 'active') {
        return (
            <div className="grid min-h-screen place-items-center bg-band p-6 text-white">
                <div className="text-center">
                    <Spinner className="mx-auto mb-4 h-10 w-10 text-sunset" />
                    <p className="text-[18px] font-bold">{message}</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-background">
            {/* Band */}
            <div className="relative overflow-hidden rounded-b-[40px] bg-band px-5 pb-28 pt-6 text-white">
                <span className="pointer-events-none absolute -right-8 top-36 h-24 w-24 rounded-full bg-sunset/40" aria-hidden="true" />
                <div className="mx-auto max-w-[420px]">
                    <div className="flex items-center gap-3">
                        {siteSettings?.logo ? (
                            <img src={siteSettings.logo} alt="" className="h-12 w-12 rounded-full bg-white object-contain p-1" />
                        ) : (
                            <span className="grid h-12 w-12 place-items-center rounded-full bg-sunset"><WifiIcon size={24} /></span>
                        )}
                        <span className="text-[20px] font-extrabold tracking-tight">{company}</span>
                    </div>
                    <h1 className="mt-8 text-[38px] font-extrabold leading-[1.05] tracking-tight">
                        Karibu!<br />Get online <span className="text-[#F4C542]">now.</span>
                    </h1>
                </div>
            </div>

            <main className="relative mx-auto -mt-20 max-w-[420px] px-5 pb-10">
                {paymentSuccess ? (
                    <section className="rounded-card border border-border bg-card p-6 text-center shadow-card">
                        {!pollTimedOut ? (
                            <>
                                <span className="mx-auto mb-5 grid h-20 w-20 place-items-center rounded-full bg-ok-bg text-ok"><CheckIcon /></span>
                                <h2 className="text-[22px] font-extrabold text-foreground">Check your phone</h2>
                                <p className="mt-1 text-[14.5px] text-muted-foreground">
                                    Enter your M-Pesa PIN to pay KES {kes(selectedPlan?.price || 0)} for {selectedPlan?.name}.
                                </p>
                                <p className="mt-5 flex items-center justify-center gap-2 text-[13.5px] text-muted-foreground">
                                    <Spinner className="h-4 w-4" /> You'll be connected automatically.
                                </p>
                            </>
                        ) : (
                            <>
                                <span className="mx-auto mb-5 grid h-20 w-20 place-items-center rounded-full bg-warn-bg text-warn"><Spinner className="h-9 w-9" /></span>
                                <h2 className="text-[22px] font-extrabold text-foreground">Still waiting…</h2>
                                <p className="mt-1 text-[14.5px] text-muted-foreground">
                                    If you've entered your PIN, check again. Otherwise the prompt may have expired; you can pay again.
                                </p>
                                <button
                                    onClick={() => { setPollTimedOut(false); checkStatus(); }}
                                    className="mt-5 h-12 w-full rounded-full bg-primary text-[15px] font-semibold text-primary-foreground"
                                >
                                    Check again
                                </button>
                            </>
                        )}
                        <button onClick={resetPayment} className="mt-3 h-12 w-full rounded-full border border-input text-[15px] font-semibold text-foreground">
                            Back to packages
                        </button>
                    </section>
                ) : (
                    <form onSubmit={handleBuyPlan}>
                        <section className="rounded-card border border-border bg-card p-5 shadow-card">
                            <div className="mb-3 flex items-center justify-between">
                                <h2 className="text-[16px] font-bold text-foreground">Choose a package</h2>
                                <span className="text-[13px] text-faint">{plans.length} option{plans.length === 1 ? '' : 's'}</span>
                            </div>
                            {plans.length === 0 ? (
                                <p className="py-6 text-center text-[14px] text-muted-foreground">No packages available right now. Have a voucher? Use it below.</p>
                            ) : (
                                <div className="space-y-3" role="radiogroup" aria-label="Packages">
                                    {plans.map((plan) => {
                                        const active = selectedPlan?.id === plan.id;
                                        return (
                                            <label
                                                key={plan.id}
                                                className={`flex cursor-pointer items-center gap-4 rounded-[18px] border-2 px-4 py-3.5 transition-colors ${active ? 'border-primary bg-accent' : 'border-border hover:border-border-strong'}`}
                                            >
                                                <input
                                                    type="radio"
                                                    name="plan"
                                                    className="sr-only"
                                                    checked={active}
                                                    onChange={() => setSelectedPlan(plan)}
                                                />
                                                <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full border-2 ${active ? 'border-primary' : 'border-border-strong'}`} aria-hidden="true">
                                                    {active && <span className="h-3 w-3 rounded-full bg-primary" />}
                                                </span>
                                                <span className="min-w-0 flex-1">
                                                    <span className="block text-[16px] font-bold text-foreground">{plan.name}</span>
                                                    <span className="block truncate text-[13.5px] text-muted-foreground">
                                                        {plan.description || `${durationText(plan)} · ${plan.download_speed} Mbps`}
                                                    </span>
                                                </span>
                                                <span className="shrink-0 text-right">
                                                    <span className="mr-1 text-[13px] text-muted-foreground">KES</span>
                                                    <span className="num text-[20px] font-extrabold text-foreground">{kes(plan.price)}</span>
                                                </span>
                                            </label>
                                        );
                                    })}
                                </div>
                            )}
                        </section>

                        {plans.length > 0 && (
                            <>
                                <label htmlFor="portal-phone" className="mb-2 mt-6 block text-[14px] text-muted-foreground">M-Pesa phone number</label>
                                <div className="flex h-14 items-center rounded-full border border-input bg-card px-5 focus-within:ring-2 focus-within:ring-ring">
                                    <span className="border-r border-border pr-3 text-[16px] font-semibold text-foreground">+254</span>
                                    <input
                                        id="portal-phone"
                                        type="tel"
                                        inputMode="tel"
                                        autoComplete="tel"
                                        placeholder="712 345 678"
                                        value={phoneNumber}
                                        onChange={(e) => setPhoneNumber(e.target.value)}
                                        className="num min-w-0 flex-1 bg-transparent pl-3 text-[16px] text-foreground placeholder:text-faint focus:outline-none"
                                    />
                                </div>
                                {phoneNumber && !phone && (
                                    <p className="mt-1.5 px-2 text-[12.5px] text-bad">Enter a Safaricom number, e.g. 712 345 678.</p>
                                )}
                                <button
                                    type="submit"
                                    disabled={!selectedPlan || !phone || processingPayment}
                                    className="mt-4 flex h-14 w-full items-center justify-center gap-3 rounded-full bg-mpesa text-[18px] font-bold text-white transition-colors hover:bg-mpesa/90 disabled:opacity-60"
                                >
                                    {processingPayment ? <Spinner className="h-6 w-6" /> : (
                                        <>
                                            <span className="rounded-md bg-white/20 px-2 py-0.5 text-[12px] font-extrabold tracking-wide">M-PESA</span>
                                            Pay KES {kes(selectedPlan?.price || 0)}
                                        </>
                                    )}
                                </button>
                            </>
                        )}
                    </form>
                )}

                {/* Voucher */}
                <div className="my-6 flex items-center gap-3 text-[14px] text-faint">
                    <span className="h-px flex-1 bg-border" /> Have a voucher? <span className="h-px flex-1 bg-border" />
                </div>
                <form onSubmit={handleRedeemVoucher} className="flex gap-3">
                    <div className="flex h-14 min-w-0 flex-1 items-center gap-3 rounded-full border border-input bg-card px-5 text-faint focus-within:ring-2 focus-within:ring-ring">
                        <TicketIcon />
                        <input
                            type="text"
                            aria-label="Voucher code"
                            placeholder="Enter voucher code"
                            value={voucherCode}
                            onChange={(e) => setVoucherCode(e.target.value)}
                            autoCapitalize="characters"
                            className="min-w-0 flex-1 bg-transparent text-[16px] uppercase text-foreground placeholder:normal-case placeholder:text-faint focus:outline-none"
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={redeeming || !voucherCode.trim()}
                        className="h-14 shrink-0 rounded-full border border-input bg-card px-6 text-[16px] font-semibold text-foreground disabled:opacity-60"
                    >
                        {redeeming ? <Spinner className="h-5 w-5" /> : 'Connect'}
                    </button>
                </form>

                {pppoeCredentials && (
                    <section className="mt-4 rounded-card border border-border bg-card p-5 shadow-card">
                        <h3 className="font-bold text-foreground">PPPoE ready</h3>
                        <p className="mt-1 text-[13.5px] text-muted-foreground">
                            PPPoE doesn't connect from this page. Enter these in your own router's PPPoE settings:
                        </p>
                        <dl className="mt-3 space-y-1 rounded-2xl bg-surface2 p-3 font-mono text-[14px]">
                            <div><dt className="inline text-muted-foreground">Username: </dt><dd className="inline text-foreground">{pppoeCredentials.username}</dd></div>
                            <div><dt className="inline text-muted-foreground">Password: </dt><dd className="inline text-foreground">{pppoeCredentials.password}</dd></div>
                        </dl>
                    </section>
                )}

                {/* Reconnect with an M-Pesa code */}
                {showReconnect && (
                    <form onSubmit={handleReactivate} className="mt-4 rounded-card border border-border bg-card p-5 shadow-card">
                        <label htmlFor="mpesa-code" className="block text-[14px] font-semibold text-foreground">Reconnect with your M-Pesa code</label>
                        <p className="mt-0.5 text-[13px] text-muted-foreground">Paid but got disconnected? Enter the code from your payment SMS.</p>
                        <div className="mt-3 flex gap-3">
                            <input
                                id="mpesa-code"
                                type="text"
                                placeholder="e.g. SKC4H7XQ2P"
                                value={mpesaCode}
                                onChange={(e) => setMpesaCode(e.target.value)}
                                autoCapitalize="characters"
                                className="h-12 min-w-0 flex-1 rounded-full border border-input bg-card px-5 text-[15px] uppercase text-foreground placeholder:normal-case placeholder:text-faint focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            />
                            <button
                                type="submit"
                                disabled={reactivating || !mpesaCode.trim()}
                                className="h-12 shrink-0 rounded-full bg-primary px-5 text-[15px] font-semibold text-primary-foreground disabled:opacity-60"
                            >
                                {reactivating ? <Spinner className="h-5 w-5" /> : 'Reconnect'}
                            </button>
                        </div>
                    </form>
                )}

                <div className="mt-8 flex items-center justify-between gap-3 text-[14px] text-faint">
                    {siteSettings?.support_phone ? (
                        <a href={`tel:${siteSettings.support_phone.replace(/\s/g, '')}`}>Help: {siteSettings.support_phone}</a>
                    ) : (
                        <button type="button" onClick={() => navigate('/login')}>Account login</button>
                    )}
                    <span>
                        Already paid?{' '}
                        <button type="button" onClick={() => setShowReconnect((v) => !v)} className="font-bold text-primary">
                            Reconnect
                        </button>
                    </span>
                </div>
                {siteSettings?.support_phone && (
                    <button type="button" onClick={() => navigate('/login')} className="mt-3 text-[13px] text-faint underline-offset-2 hover:underline">
                        Have an account? Log in
                    </button>
                )}
                <p className="mt-6 text-center text-[11.5px] text-faint">Device {mac || 'unknown'}</p>
            </main>
        </div>
    );
};

export default CaptivePortal;
