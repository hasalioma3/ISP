import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
    AlertTriangle, CalendarClock, CheckCircle2, Clock, CreditCard, Gauge, Plus,
    RefreshCw, Users, Wifi, WifiOff,
} from 'lucide-react';
import { analyticsAPI } from '../../services/api';
import { useSites } from '../../hooks/useSites';
import UsageChartPanels from '../../components/UsageChartPanels';
import ExportMenu from '../../components/ExportMenu';
import { useAuthStore } from '../../store/authStore';
import {
    AlertRow, Chip, EmptyState, KpiCard, MpesaBadge, Panel, PanelHeader, PaymentsFeedRow,
    SegmentedControl, ShellHeader, SiteHealthRow, Skeleton, StatusBadge,
    bandCtaClass, formatAmount, formatCompact, formatCount, formatDateEAT,
    formatKES, percentChange, timeAgo, TIME_ZONE,
    type FeedPayment,
} from '../../components/savanna';
import { AreaTrend, BarTrend, Donut, DONUT_COLORS } from '../../components/savanna/charts';

type Range = '7D' | '30D' | '90D' | '12M';
const RANGE_DAYS: Record<Exclude<Range, '12M'>, number> = { '7D': 7, '30D': 30, '90D': 90 };

/** YYYY-MM-DD for a date as seen in Nairobi (matches the API's TruncDate). */
const eatDayKey = (d: Date) => new Intl.DateTimeFormat('en-CA', { timeZone: TIME_ZONE }).format(d);

/** Daily series for the last `days` days with zero-filled gaps (the API only returns days with payments). */
function fillDays(rows: { date: string; total: number }[] | undefined, days: number) {
    const byDay = new Map((rows || []).map((r) => [r.date, Number(r.total) || 0]));
    const out: { date: string; total: number }[] = [];
    for (let i = days - 1; i >= 0; i--) {
        const key = eatDayKey(new Date(Date.now() - i * 86_400_000));
        out.push({ date: key, total: byDay.get(key) ?? 0 });
    }
    return out;
}

export default function Dashboard() {
    const navigate = useNavigate();
    const user = useAuthStore((state) => state.user);
    const showIncome = user?.is_superuser || user?.role !== 'technician';
    const [range, setRange] = useState<Range>('30D');
    const [expiringPage, setExpiringPage] = useState(1);

    const {
        sites, stats, isLoading: statsLoading, isError: statsError, error: statsErrorObj, refetchHealth, healthFetching,
    } = useSites();

    // Collections chart: daily totals for 7/30/90 days (12M uses the
    // year's monthly sales from the extra endpoint instead).
    const days = range === '12M' ? 30 : RANGE_DAYS[range];
    const { data: incomeRows, isLoading: incomeLoading } = useQuery({
        queryKey: ['admin-income', days],
        queryFn: async () => {
            const start = eatDayKey(new Date(Date.now() - (days - 1) * 86_400_000));
            return (await analyticsAPI.getIncomeReport({ start_date: start })).data as { date: string; total: number }[];
        },
        enabled: showIncome,
    });
    // The revenue KPI's sparkline is always the last 30 days.
    const { data: income30 } = useQuery({
        queryKey: ['admin-income', 30],
        queryFn: async () => {
            const start = eatDayKey(new Date(Date.now() - 29 * 86_400_000));
            return (await analyticsAPI.getIncomeReport({ start_date: start })).data as { date: string; total: number }[];
        },
        enabled: showIncome,
    });

    const { data: usageChart, isLoading: usageChartLoading } = useQuery({
        queryKey: ['admin-usage-chart'],
        queryFn: async () => (await analyticsAPI.getUsageChart()).data,
    });

    const { data: usageData, isLoading: usageLoading } = useQuery({
        queryKey: ['admin-usage'],
        queryFn: async () => (await analyticsAPI.getUsageReport()).data,
    });

    const { data: extra, isLoading: extraLoading } = useQuery({
        queryKey: ['admin-stats-extra'],
        queryFn: async () => (await analyticsAPI.getDashboardExtra()).data,
        // While the M-Pesa check is still running server-side, ask again shortly.
        refetchInterval: (query) => {
            const gateway = query.state.data?.payment_gateway;
            return gateway && gateway.connected == null ? 5000 : false;
        },
    });

    // Live payments feed: the cheap "section=payments" variant, every 15s.
    const { data: feed, isLoading: feedLoading } = useQuery({
        queryKey: ['admin-payments-feed'],
        queryFn: async () => (await analyticsAPI.getDashboardFeed()).data.last_transactions as FeedPayment[],
        enabled: showIncome,
        refetchInterval: 15_000,
    });

    const { data: expiring, isLoading: expiringLoading } = useQuery({
        queryKey: ['admin-expiring-today', expiringPage],
        queryFn: async () => (await analyticsAPI.getExpiringToday(expiringPage, 8)).data,
    });

    const { data: activity, isLoading: activityLoading } = useQuery({
        queryKey: ['admin-recent-activity'],
        queryFn: async () => (await analyticsAPI.getRecentActivity()).data,
        refetchInterval: 30_000,
    });

    const routers: any[] = stats?.routers || [];

    // Alerts are derived from live data, not stored: offline/hot routers,
    // a down payment gateway, and today's expiries.
    const alerts = useMemo(() => {
        const list: { key: string; icon: any; tone: 'bad' | 'warn' | 'ok' | 'neutral'; title: string; detail?: string; href?: string }[] = [];
        sites.forEach((site) => {
            if (site.status === 'offline') {
                list.push({
                    key: `off-${site.id}`, icon: WifiOff, tone: 'bad', title: `${site.name} unreachable`,
                    detail: `${site.lastSeenAt ? `Last seen ${timeAgo(site.lastSeenAt)}` : 'Never reached'} · ${site.clients} sessions last known`,
                    href: '/admin/mikrotik',
                });
            } else if (site.status === 'degraded') {
                list.push({
                    key: `cpu-${site.id}`, icon: Gauge, tone: 'warn', title: `${site.name} CPU at ${site.cpu}%`,
                    detail: 'Check queues and connected load', href: '/admin/network-ops',
                });
            }
        });
        if (extra?.payment_gateway?.connected === false) {
            list.push({
                key: 'gateway', icon: AlertTriangle, tone: 'bad', title: 'M-Pesa gateway unreachable',
                detail: `Daraja ${extra.payment_gateway.environment} · shortcode ${extra.payment_gateway.shortcode}`,
                href: '/admin/settings',
            });
        }
        if ((expiring?.count ?? 0) > 0) {
            list.push({
                key: 'expiring', icon: Clock, tone: 'warn', title: `${expiring.count} subscription${expiring.count === 1 ? '' : 's'} expire today`,
                detail: 'Expiry reminders go out daily at 08:00',
            });
        }
        return list;
    }, [sites, extra, expiring]);

    if (statsError) {
        return (
            <Panel className="mt-[110px] text-bad">
                Error loading dashboard stats: {statsErrorObj instanceof Error ? statsErrorObj.message : 'Unknown error'}.
                Please ensure you are logged in as an Administrator.
            </Panel>
        );
    }

    const firstName = user?.first_name || user?.username || 'there';
    const subtitle = [
        formatDateEAT(new Date(), { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }),
        stats ? `${routers.length} site${routers.length === 1 ? '' : 's'}` : null,
        stats ? `${formatCount(stats.total_customers)} subscribers` : null,
    ].filter(Boolean).join(' · ');

    // KPI figures
    const revenueChange = stats?.revenue_30d != null ? percentChange(stats.revenue_30d, stats.revenue_prev_30d) : null;
    const revenueSpark = fillDays(income30, 30).map((d) => d.total);
    const regSpark = (extra?.monthly_registrations || [])
        .slice(0, new Date().getMonth() + 1)
        .reduce((acc: number[], m: any) => [...acc, (acc[acc.length - 1] ?? 0) + m.count], []);

    const chartData = range === '12M'
        ? (extra?.monthly_sales || []).slice(0, new Date().getMonth() + 1).map((m: any) => ({ date: m.month, total: Number(m.total) || 0 }))
        : fillDays(incomeRows, days);

    // Plan mix: share of this month's revenue by plan (sales roles), or
    // subscribers by service type for technicians (no income figures).
    const mixSource: { name: string; value: number }[] = showIncome
        ? (extra?.best_selling_packages || []).map((p: any) => ({ name: p.name, value: p.revenue }))
        : (extra?.users_by_service_type || []).map((s: any) => ({ name: String(s.service_type).toUpperCase(), value: s.count }));
    const mix = mixSource.length > 6
        ? [...mixSource.slice(0, 5), { name: 'Other', value: mixSource.slice(5).reduce((a, b) => a + b.value, 0) }]
        : mixSource;
    const mixTotal = mix.reduce((a, b) => a + b.value, 0);

    return (
        <div className="space-y-[18px]">
            <ShellHeader
                title={`Habari, ${firstName}`}
                subtitle={subtitle}
                actions={
                    <>
                        {showIncome && (
                            <ExportMenu
                                path="/analytics/income/"
                                params={{ start_date: eatDayKey(new Date(Date.now() - 29 * 86_400_000)), end_date: eatDayKey(new Date()) }}
                                filename={`revenue_30d_${eatDayKey(new Date())}`}
                                className="h-[42px] border-white/25 bg-white/5 px-5 text-[14px] text-white hover:bg-white/10"
                            />
                        )}
                        <button onClick={() => navigate('/admin/settings?tab=manual')} className={bandCtaClass}>
                            <Plus className="h-[18px] w-[18px]" strokeWidth={2} /> New subscriber
                        </button>
                    </>
                }
            />

            {/* KPIs */}
            <div className="grid grid-cols-1 gap-[18px] sm:grid-cols-2 xl:grid-cols-4">
                {showIncome ? (
                    <KpiCard
                        highlight
                        label="Revenue · 30 days"
                        icon={CreditCard}
                        value={formatCompact(stats?.revenue_30d)}
                        unit="KES"
                        loading={statsLoading}
                        delta={revenueChange != null ? { value: `${Math.abs(revenueChange).toFixed(1)}%`, direction: revenueChange >= 0 ? 'up' : 'down' } : null}
                        footnote={revenueChange != null ? 'vs prev. 30d' : 'no earlier 30 days to compare'}
                        sparkline={revenueSpark}
                        onClick={() => navigate('/admin/reports')}
                    />
                ) : (
                    <KpiCard
                        highlight
                        label="Expired subscribers"
                        icon={CalendarClock}
                        value={formatCount(stats?.expired_subscribers)}
                        loading={statsLoading}
                        footnote="need a renewal"
                        onClick={() => navigate('/admin/subscribers')}
                    />
                )}
                <KpiCard
                    label="Active subscribers"
                    icon={Users}
                    value={formatCount(stats?.active_subscribers)}
                    loading={statsLoading}
                    delta={stats ? { value: formatCount(stats.new_this_week), direction: 'up' } : null}
                    footnote="new this week"
                    sparkline={regSpark}
                    onClick={() => navigate('/admin/subscribers')}
                />
                <KpiCard
                    label="Online now"
                    icon={Wifi}
                    value={formatCount(stats?.total_online)}
                    unit="sessions"
                    loading={statsLoading}
                    footnote={stats ? [
                        `PPPoE ${stats.pppoe_online}`,
                        `Hotspot ${stats.hotspot_online}`,
                        stats.static_online ? `Static ${stats.static_online}` : null,
                    ].filter(Boolean).join(' · ') : null}
                    onClick={() => navigate('/admin/online-users')}
                />
                <KpiCard
                    label="Expiring today"
                    icon={Clock}
                    value={formatCount(expiring?.count)}
                    loading={expiringLoading}
                    footnote={`${formatCount(stats?.expired_subscribers)} already expired`}
                />
            </div>

            {/* Collections + plan mix */}
            <div className="grid grid-cols-1 gap-[18px] xl:grid-cols-3">
                <Panel className="xl:col-span-2">
                    {showIncome ? (
                        <>
                            <PanelHeader
                                title="Collections"
                                subtitle={range === '12M' ? 'M-Pesa STK, Paybill & cash · monthly this year, KES' : 'M-Pesa STK, Paybill & cash · daily, KES'}
                                action={
                                    <SegmentedControl
                                        aria-label="Collections period"
                                        options={[
                                            { value: '7D', label: '7D' }, { value: '30D', label: '30D' },
                                            { value: '90D', label: '90D' }, { value: '12M', label: 'YTD' },
                                        ] as { value: Range; label: string }[]}
                                        value={range}
                                        onChange={setRange}
                                    />
                                }
                            />
                            <div className="mb-4 flex flex-wrap gap-x-10 gap-y-3">
                                {[
                                    { label: 'Today', value: formatKES(stats?.income_today) },
                                    { label: 'STK success rate', value: stats?.stk_success_rate != null ? `${stats.stk_success_rate}%` : '—' },
                                    { label: 'Avg. ticket (30d)', value: formatKES(stats?.avg_ticket_30d) },
                                ].map((s) => (
                                    <div key={s.label}>
                                        <p className="text-[13px] text-muted-foreground">{s.label}</p>
                                        {statsLoading ? <Skeleton className="mt-1 h-7 w-28" /> : (
                                            <p className="num text-[22px] font-extrabold text-foreground">{s.value}</p>
                                        )}
                                    </div>
                                ))}
                            </div>
                            {(range === '12M' ? extraLoading : incomeLoading) ? (
                                <Skeleton className="h-[300px] w-full" />
                            ) : (
                                <AreaTrend
                                    data={chartData}
                                    xKey="date"
                                    yKey="total"
                                    name="Collected"
                                    formatX={(v: string) => (range === '12M' ? v : formatDateEAT(`${v}T12:00:00+03:00`, { day: '2-digit', month: 'short' }))}
                                    formatY={(v) => formatCompact(v)}
                                    formatTooltip={(v) => formatKES(v)}
                                />
                            )}
                        </>
                    ) : (
                        <>
                            <PanelHeader title="Data usage" subtitle="Whole network" />
                            <UsageChartPanels chart={usageChart} loading={usageChartLoading} />
                        </>
                    )}
                </Panel>

                <Panel>
                    <PanelHeader
                        title={showIncome ? 'Plan mix' : 'Service mix'}
                        subtitle={showIncome ? "Share of this month's revenue" : 'Subscribers by service type'}
                    />
                    {extraLoading ? (
                        <Skeleton className="mx-auto h-[236px] w-[236px] rounded-full" />
                    ) : (
                        <>
                            <Donut
                                data={mix}
                                centerValue={formatCount(stats?.active_subscribers)}
                                centerLabel="active subscribers"
                            />
                            {mix.length === 0 ? (
                                <EmptyState message={showIncome ? 'No plan sales yet this month.' : 'No subscribers yet.'} />
                            ) : (
                                <ul className="mt-6 space-y-3">
                                    {mix.map((m, i) => (
                                        <li key={m.name} className="flex items-center justify-between gap-3 text-[14px]">
                                            <span className="flex min-w-0 items-center gap-2.5">
                                                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
                                                <span className="truncate text-foreground">{m.name}</span>
                                            </span>
                                            <span className="num font-semibold text-foreground">
                                                {mixTotal ? Math.round((m.value / mixTotal) * 100) : 0}%
                                            </span>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </>
                    )}
                </Panel>
            </div>

            {/* Payments / sites / alerts */}
            <div className={`grid grid-cols-1 gap-[18px] lg:grid-cols-2 ${showIncome ? 'xl:grid-cols-3' : ''}`}>
                {showIncome && (
                    <Panel>
                        <PanelHeader
                            leading={<MpesaBadge />}
                            title="Payments feed"
                            action={
                                extra?.payment_gateway?.connected === false
                                    ? <StatusBadge status="offline" label="Gateway down" />
                                    : <StatusBadge status="online" label="Live" />
                            }
                        />
                        {feedLoading ? (
                            <div className="space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
                        ) : !feed?.length ? (
                            <EmptyState message="No payments yet. They appear here within 15 seconds." />
                        ) : (
                            <div>{feed.map((p, i) => <PaymentsFeedRow key={`${p.date}-${i}`} payment={p} />)}</div>
                        )}
                    </Panel>
                )}

                <Panel>
                    <PanelHeader
                        title="Sites & core"
                        subtitle="MikroTik health"
                        action={
                            <button
                                onClick={() => refetchHealth()}
                                aria-label="Refresh router health"
                                className="grid h-9 w-9 place-items-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
                            >
                                <RefreshCw className={`h-[18px] w-[18px] ${healthFetching ? 'animate-spin' : ''}`} strokeWidth={1.8} />
                            </button>
                        }
                    />
                    {statsLoading ? (
                        <div className="space-y-3">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}</div>
                    ) : sites.length === 0 ? (
                        <EmptyState
                            message="No routers yet."
                            action={<button onClick={() => navigate('/admin/mikrotik')} className="text-[13px] font-semibold text-primary">Add a router</button>}
                        />
                    ) : (
                        <div>{sites.map((s) => <SiteHealthRow key={s.name} site={s} />)}</div>
                    )}
                </Panel>

                <Panel>
                    <PanelHeader
                        title="Alerts"
                        subtitle="Live from routers, payments and expiries"
                        action={alerts.length > 0 ? <Chip>{alerts.length} active</Chip> : null}
                    />
                    {alerts.length === 0 ? (
                        <AlertRow icon={CheckCircle2} tone="ok" title="All systems normal" detail="Routers reachable, payments flowing, nothing expiring today" />
                    ) : (
                        <div>
                            {alerts.map((a) => (
                                <AlertRow
                                    key={a.key}
                                    icon={a.icon}
                                    tone={a.tone}
                                    title={a.title}
                                    detail={a.detail}
                                    onClick={a.href ? () => navigate(a.href!) : undefined}
                                />
                            ))}
                        </div>
                    )}
                </Panel>
            </div>

            {/* Operational detail (kept from the previous dashboard) */}
            {showIncome && (
                <Panel>
                    <PanelHeader title="Data usage" subtitle="Whole network" />
                    <UsageChartPanels chart={usageChart} loading={usageChartLoading} />
                </Panel>
            )}

            <div className="grid grid-cols-1 gap-[18px] xl:grid-cols-3">
                <Panel className="xl:col-span-2">
                    <PanelHeader title="Expiring today" subtitle={`${formatCount(expiring?.count)} subscription${expiring?.count === 1 ? '' : 's'}`} />
                    <SimpleTable
                        loading={expiringLoading}
                        empty="No subscriptions expire today."
                        columns={['Subscriber', 'Created', 'Expires']}
                        rows={(expiring?.results || []).map((u: any) => [
                            <span className="font-semibold text-foreground">{u.username}</span>,
                            formatDateEAT(u.created_on, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }),
                            formatDateEAT(u.expires_on, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }),
                        ])}
                    />
                    {expiring && expiring.total_pages > 1 && (
                        <div className="mt-3 flex items-center justify-between text-[13px] text-muted-foreground">
                            <span>Page {expiring.page} of {expiring.total_pages}</span>
                            <div className="flex gap-2">
                                <button className="h-8 rounded-full border border-input px-3 disabled:opacity-40" disabled={expiringPage <= 1} onClick={() => setExpiringPage((p) => p - 1)}>Prev</button>
                                <button className="h-8 rounded-full border border-input px-3 disabled:opacity-40" disabled={expiringPage >= expiring.total_pages} onClick={() => setExpiringPage((p) => p + 1)}>Next</button>
                            </div>
                        </div>
                    )}
                </Panel>

                <Panel>
                    <PanelHeader title="Recent activity" subtitle="Logins and account events" />
                    {activityLoading ? (
                        <div className="space-y-3">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
                    ) : !activity?.length ? (
                        <EmptyState message="No activity recorded yet." />
                    ) : (
                        <div className="max-h-96 overflow-y-auto">
                            {activity.map((a: any, i: number) => (
                                <div key={i} className="border-t border-border-soft py-2.5 first:border-t-0">
                                    <p className="text-[13.5px] text-foreground">{a.message}</p>
                                    <p className="text-[12px] text-faint">{timeAgo(a.created_at)}</p>
                                </div>
                            ))}
                        </div>
                    )}
                </Panel>
            </div>

            <div className="grid grid-cols-1 gap-[18px] xl:grid-cols-3">
                <Panel className="xl:col-span-2">
                    <PanelHeader title="Top data usage" subtitle="By subscriber, last 30 days (GB)" />
                    <SimpleTable
                        loading={usageLoading}
                        empty="No usage recorded yet."
                        columns={['Subscriber', 'Upload', 'Download', 'Total']}
                        align={['left', 'right', 'right', 'right']}
                        rows={(usageData || []).map((u: any) => [
                            <span className="font-semibold text-foreground">{u.name}</span>,
                            u.upload_gb, u.download_gb,
                            <span className="font-semibold text-foreground">{u.total_gb}</span>,
                        ])}
                    />
                </Panel>
                <Panel>
                    <PanelHeader title="New subscribers" subtitle="Registrations per month, this year" />
                    {extraLoading ? <Skeleton className="h-[220px] w-full" /> : (
                        <BarTrend
                            data={(extra?.monthly_registrations || []).slice(0, new Date().getMonth() + 1)}
                            xKey="month"
                            yKey="count"
                            name="Registered"
                            height={220}
                        />
                    )}
                </Panel>
            </div>

            {showIncome && (
                <div className="grid grid-cols-1 gap-[18px] lg:grid-cols-2">
                    <Panel>
                        <PanelHeader title="Collections per router" subtitle="All time" />
                        <SimpleTable
                            loading={extraLoading}
                            empty="No transactions yet."
                            columns={['Router', 'Payments', 'Share', 'Amount']}
                            align={['left', 'right', 'right', 'right']}
                            rows={(extra?.transactions_per_router || []).map((r: any) => [
                                <span className="font-semibold text-foreground">{r.router}</span>,
                                formatCount(r.transactions), `${r.percentage}%`, formatKES(r.amount),
                            ])}
                        />
                    </Panel>
                    <Panel>
                        <PanelHeader title="Voucher stock" subtitle="Unused vs used, per plan" />
                        <SimpleTable
                            loading={extraLoading}
                            empty="No vouchers generated yet."
                            columns={['Plan', 'Unused', 'Used']}
                            align={['left', 'right', 'right']}
                            rows={(extra?.voucher_stock || []).map((v: any) => [
                                <span className="font-semibold text-foreground">{v.plan_name}</span>,
                                formatCount(v.unused), formatCount(v.used),
                            ])}
                        />
                    </Panel>
                </div>
            )}

            {showIncome && extra?.best_selling_packages?.length > 0 && (
                <Panel>
                    <PanelHeader title="Best-selling plans" subtitle="This month" />
                    <SimpleTable
                        columns={['Plan', 'Price', 'Sales', 'Revenue']}
                        align={['left', 'right', 'right', 'right']}
                        rows={extra.best_selling_packages.map((p: any) => [
                            <span className="font-semibold text-foreground">{p.name}</span>,
                            formatKES(p.price), formatAmount(p.sales), formatKES(p.revenue),
                        ])}
                    />
                </Panel>
            )}
        </div>
    );
}

/** Compact table in the Savanna table style (uppercase faint headers, soft row rules). */
function SimpleTable({ columns, rows, align, loading, empty }: {
    columns: string[];
    rows: React.ReactNode[][];
    align?: ('left' | 'right')[];
    loading?: boolean;
    empty?: string;
}) {
    if (loading) return <div className="space-y-2">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}</div>;
    if (!rows.length) return <EmptyState message={empty || 'Nothing to show.'} />;
    return (
        <div className="-mx-1 overflow-x-auto">
            <table className="w-full border-collapse text-[13.5px]">
                <thead>
                    <tr>
                        {columns.map((c, i) => (
                            <th
                                key={c}
                                className={`border-b border-border px-3 pb-2.5 text-[11.5px] font-semibold uppercase tracking-[0.06em] text-faint ${align?.[i] === 'right' ? 'text-right' : 'text-left'}`}
                            >
                                {c}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row, r) => (
                        <tr key={r} className="border-b border-border-soft last:border-0">
                            {row.map((cell, i) => (
                                <td key={i} className={`num whitespace-nowrap px-3 py-3 text-muted-foreground ${align?.[i] === 'right' ? 'text-right' : 'text-left'}`}>
                                    {cell}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
