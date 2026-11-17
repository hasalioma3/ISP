import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Banknote, ChevronRight, Hourglass, Server, Users, Wallet } from 'lucide-react';
import { KpiCard, Panel, PanelHeader, ShellHeader, formatCount, formatKES } from '@/components/savanna';
import { AreaTrend } from '@/components/savanna/charts';
import { TenantStatus, Notice } from '~/components/ui';
import { api } from '~/lib/api';
import { dateTime } from '~/lib/format';

export default function Dashboard() {
    const { data, isLoading } = useQuery({ queryKey: ['dashboard'], queryFn: async () => (await api.get('/admin/dashboard/')).data, refetchInterval: 60_000 });
    const { data: recent } = useQuery({ queryKey: ['tenants', 'recent'], queryFn: async () => (await api.get('/admin/tenants/')).data });
    const s = data?.tenants?.by_status || {};
    const live = (s.trial || 0) + (s.active || 0) + (s.past_due || 0);
    const attention = data ? [
        { n: data.payouts_awaiting_approval, label: 'payouts awaiting approval', href: '/admin/payouts?status=pending_approval' },
        { n: data.unallocated_payments, label: 'payments not matched to an ISP', href: '/admin/payments?unallocated=1' },
        { n: data.unhealthy, label: 'live instances not responding', href: '/admin/tenants?status=trial,active,past_due' },
        { n: data.unpaid_invoices?.n, label: `unpaid invoices (${formatKES(data.unpaid_invoices?.s)})`, href: '/admin/invoices?status=open' },
        { n: s.failed, label: 'sign-ups whose setup failed', href: '/admin/tenants?status=failed' },
    ].filter((a) => a.n) : [];

    return (
        <>
            <ShellHeader title="Platform overview" subtitle="Every ISP on the platform, their money and their instances." />
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
                <KpiCard highlight label="Collected this month" value={formatKES(data?.collected_month)} icon={Wallet} loading={isLoading}
                    footnote={`${formatKES(data?.collected_today)} today`} sparkline={data?.collections_by_day?.map((d: any) => d.amount)} />
                <KpiCard label="Live ISPs" value={formatCount(live)} icon={Server} loading={isLoading}
                    footnote={`${s.active || 0} paying · ${s.trial || 0} on trial`} />
                <KpiCard label="Active subscribers" value={formatCount(data?.subscribers_active)} icon={Users} loading={isLoading} footnote="across all ISPs" />
                <KpiCard label="Held for ISPs" value={formatKES(data?.held_for_isps)} icon={Banknote} loading={isLoading}
                    footnote={`${formatKES(data?.paid_out_month)} paid out this month`} />
            </div>

            <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
                <Panel>
                    <PanelHeader title="Customer payments, last 30 days" subtitle="Verified M-Pesa payments for all ISPs" />
                    {data && <AreaTrend data={data.collections_by_day} xKey="date" yKey="amount" height={260}
                        formatX={(d) => new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
                        formatY={(v) => (v >= 1000 ? `${Math.round(v / 1000)}K` : String(v))} formatTooltip={(v) => formatKES(v)} name="Collected" />}
                </Panel>
                <Panel>
                    <PanelHeader title="Needs attention" />
                    {data?.settings_warnings?.map((w: string) => <Notice key={w} className="mb-2"><AlertTriangle className="mr-1.5 inline h-4 w-4" />{w} <Link to="/admin/settings" className="font-semibold underline">Settings</Link></Notice>)}
                    {attention.length === 0 && !data?.settings_warnings?.length && <p className="py-6 text-center text-[13.5px] text-muted-foreground">All clear.</p>}
                    <ul className="divide-y divide-border-soft">
                        {attention.map((a) => (
                            <li key={a.label}>
                                <Link to={a.href} className="flex items-center gap-3 py-3 text-[14px] hover:text-primary">
                                    <span className="num grid h-8 min-w-8 place-items-center rounded-full bg-warn-bg px-2 font-bold text-warn">{a.n}</span>
                                    <span className="flex-1">{a.label}</span><ChevronRight className="h-4 w-4 text-muted-foreground" />
                                </Link>
                            </li>
                        ))}
                    </ul>
                    {data?.trials_ending_24h > 0 && (
                        <p className="mt-3 flex items-center gap-2 text-[13px] text-muted-foreground"><Hourglass className="h-4 w-4" />{data.trials_ending_24h} trial(s) end in the next 24 hours</p>
                    )}
                </Panel>
            </div>

            <Panel className="mt-5">
                <PanelHeader title="Latest sign-ups" action={<Link to="/admin/tenants" className="text-[13px] font-semibold text-primary">All ISPs</Link>} />
                <ul className="divide-y divide-border-soft">
                    {recent?.results?.slice(0, 8).map((t: any) => (
                        <li key={t.id}>
                            <Link to={`/admin/tenants/${t.id}`} className="flex flex-wrap items-center gap-3 py-3 text-[14px] hover:text-primary">
                                <span className="min-w-0 flex-1"><b>{t.name}</b> <span className="text-muted-foreground">· {t.contact_name} · {t.contact_email}</span></span>
                                <TenantStatus status={t.status} label={t.status_label} />
                                <span className="w-40 text-right text-[12.5px] text-muted-foreground">{dateTime(t.created_at)}</span>
                            </Link>
                        </li>
                    ))}
                </ul>
            </Panel>
        </>
    );
}
