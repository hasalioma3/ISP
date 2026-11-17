import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { CheckCircle2, Copy, ExternalLink, FileText, Hourglass, Loader2, RotateCcw, Users, Wallet, XCircle } from 'lucide-react';
import { KpiCard, MpesaBadge, Panel, PanelHeader, ShellHeader, bandButtonClass, bandCtaClass, formatCount, formatKES } from '@/components/savanna';
import { Button, Notice, Spinner, Table, Td, TenantStatus } from '~/components/ui';
import { api, errorText } from '~/lib/api';
import { dateTime, duration } from '~/lib/format';
import { usePortal } from './usePortal';

export default function Overview() {
    const { data: t, isLoading, refetch } = usePortal();
    const payments = useQuery({
        enabled: !!t?.ready_at, queryKey: ['portal-collections'],
        queryFn: async () => (await api.get('/portal/collections/')).data,
    });
    if (isLoading || !t) return <div className="grid min-h-[40vh] place-items-center"><Spinner className="h-6 w-6" /></div>;
    if (['pending', 'provisioning', 'failed'].includes(t.status)) return <SettingUp t={t} onRetry={refetch} />;

    const ended = t.status === 'suspended';
    return (
        <>
            <ShellHeader
                title={<span className="flex flex-wrap items-center gap-3">{t.name} <TenantStatus status={t.status} label={t.status_label} /></span>}
                subtitle={t.status === 'trial' ? `Free trial: ${duration(t.trial_seconds_left)} (ends ${dateTime(t.trial_ends_at)})` : t.url}
                actions={<>
                    {t.url && !ended && <a href={t.url} target="_blank" rel="noreferrer" className={bandButtonClass}><ExternalLink className="h-4 w-4" />Open my system</a>}
                    {(t.status === 'trial' || (ended && !t.activated_at)) && <Link to="/account/billing" className={bandCtaClass}>Choose a plan</Link>}
                </>}
            />
            {ended && <Notice tone="bad" className="mb-5">Your system is paused: {t.suspend_reason}. Your data is safe. {t.activated_at ? 'Pay the open invoice on the Billing page' : 'Choose a plan on the Billing page'} and it comes back straight away.</Notice>}
            {t.status === 'past_due' && <Notice className="mb-5">An invoice is overdue. Pay it from the <Link to="/account/billing" className="font-semibold underline">Billing</Link> page to avoid a pause.</Notice>}
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
                <KpiCard highlight label="Active subscribers" value={formatCount(t.subscribers?.active)} icon={Users} footnote={`${formatCount(t.subscribers?.all)} accounts in total`} />
                <KpiCard label="Your money with us" value={formatKES(t.balance)} icon={Wallet} footnote={`${formatKES(t.available_to_pay_out)} ready to pay out`} />
                <KpiCard label="This month's bill (so far)" value={formatKES(t.estimate?.amount)} icon={FileText} footnote={`${t.estimate?.counted_subscribers ?? 0} counted · ${t.estimate?.plan || ''}`} />
                <KpiCard label={t.status === 'trial' ? 'Trial left' : 'Plan'} icon={Hourglass} value={t.status === 'trial' ? duration(t.trial_seconds_left) : (t.plan_name || '—')}
                    footnote={t.status === 'trial' ? 'every feature is on' : t.activated_at ? `since ${dateTime(t.activated_at)}` : ''} />
            </div>

            <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
                <Panel>
                    <PanelHeader leading={<MpesaBadge />} title="Recent customer payments" subtitle="Payments to the platform for your customers, credited to you"
                        action={<Link to="/account/payouts" className="text-[13px] font-semibold text-primary">Statement</Link>} />
                    <Table loading={payments.isLoading} head={['Receipt', 'Amount', 'From', 'Paid']} empty="No payments yet.">
                        {payments.data?.results?.slice(0, 8).map((c: any) => (
                            <tr key={c.id}><Td className="font-mono text-[12.5px]">{c.receipt}</Td><Td className="num font-semibold">{formatKES(c.amount)}</Td>
                                <Td className="text-[12.5px]">{c.payer_name || c.phone}{c.account && <span className="text-muted-foreground"> · {c.account}</span>}</Td>
                                <Td className="text-[12.5px] text-muted-foreground">{dateTime(c.paid_at)}</Td></tr>
                        ))}
                    </Table>
                </Panel>
                <div className="space-y-5">
                    <Panel>
                        <PanelHeader title="Your system" />
                        <dl className="space-y-3 text-[14px]">
                            <Row label="Address" value={t.url} copy />
                            <Row label="Admin username" value={t.admin_username} copy />
                            <div><dt className="text-[12.5px] text-muted-foreground">Admin password</dt><dd>The one you chose when you signed up</dd></div>
                        </dl>
                    </Panel>
                    <Panel>
                        <PanelHeader title="How your customers pay" />
                        <p className="text-[14px]">
                            {t.mpesa?.type === 'till' ? 'Buy Goods till' : 'Paybill'} <b className="num">{t.mpesa?.shortcode || '—'}</b>
                            {t.mpesa?.type !== 'till' && <>, account number: <b>their username</b></>}.
                        </p>
                        <p className="mt-2 text-[13px] text-muted-foreground">
                            Your system shows customers these details and sends STK prompts for you. If a username might also exist at another ISP,
                            customers can add your code in front: <b className="font-mono">{t.mpesa?.account_prefix} username</b>.
                        </p>
                    </Panel>
                </div>
            </div>
        </>
    );
}

function Row({ label, value, copy }: { label: string; value: string; copy?: boolean }) {
    return (
        <div>
            <dt className="text-[12.5px] text-muted-foreground">{label}</dt>
            <dd className="flex items-center gap-2 break-all font-medium">{value || '—'}
                {copy && value && <button onClick={() => { navigator.clipboard.writeText(value); toast.success('Copied'); }} className="text-muted-foreground" aria-label={`Copy ${label}`}><Copy className="h-4 w-4" /></button>}
            </dd>
        </div>
    );
}

function SettingUp({ t, onRetry }: { t: any; onRetry: () => void }) {
    const failed = t.status === 'failed';
    const retry = async () => {
        try { await api.post('/portal/retry/'); toast.success('Trying again'); onRetry(); } catch (err) { toast.error(errorText(err)); }
    };
    return (
        <>
            <ShellHeader title={failed ? 'Setup hit a problem' : `Setting up ${t.name}`} subtitle={failed ? 'Nothing is lost. Try again, or contact us.' : 'Your own system and database are being created. This takes a few minutes.'} />
            <Panel className="mx-auto max-w-2xl">
                <ol className="space-y-4">
                    {[...(t.setup_steps || []), ...(failed ? [] : ['Finishing up…'])].map((step: string, i: number, all: string[]) => {
                        const last = i === all.length - 1;
                        const bad = failed && step.startsWith('Setup failed');
                        return (
                            <li key={i} className="flex items-start gap-3 text-[14px]">
                                {bad ? <XCircle className="mt-0.5 h-5 w-5 text-bad" /> : last && !failed ? <Loader2 className="mt-0.5 h-5 w-5 animate-spin text-primary" /> : <CheckCircle2 className="mt-0.5 h-5 w-5 text-ok" />}
                                <span className={bad ? 'text-bad' : ''}>{step}</span>
                            </li>
                        );
                    })}
                </ol>
                {failed && <Button className="mt-6" onClick={retry}><RotateCcw />Try again</Button>}
                {!failed && <p className="mt-6 text-[13px] text-muted-foreground">We'll also email {t.contact_email} when it's ready.</p>}
            </Panel>
        </>
    );
}
