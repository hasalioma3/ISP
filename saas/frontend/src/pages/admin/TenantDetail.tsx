import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
    Activity, Banknote, ExternalLink, FileText, Hourglass, Pause, Play, RefreshCw, RotateCcw, Server, Trash2, Users, Wallet,
} from 'lucide-react';
import {
    KpiCard, Panel, PanelHeader, SegmentedControl, ShellHeader, bandButtonClass, bandCtaClass, formatCount, formatKES,
} from '@/components/savanna';
import { BarTrend } from '@/components/savanna/charts';
import {
    Button, Field, Input, Modal, Notice, Pager, Pill, Select, Spinner, Stat, Table, Td, TenantStatus, Textarea, Toggle,
} from '~/components/ui';
import { api, errorText } from '~/lib/api';
import { useAuth } from '~/lib/auth';
import { dateTime, duration } from '~/lib/format';

type Tab = 'overview' | 'money' | 'activity' | 'instance';

export default function TenantDetail() {
    const { id } = useParams();
    const qc = useQueryClient();
    const isAdmin = useAuth((s) => s.user?.is_platform_admin);
    const [tab, setTab] = useState<Tab>('overview');
    const [busyUntil, setBusyUntil] = useState(0);
    const { data: t, isLoading } = useQuery({
        queryKey: ['tenant', id],
        queryFn: async () => (await api.get(`/admin/tenants/${id}/`)).data,
        // Poll while it's being set up or right after an action was queued.
        refetchInterval: (q) => (['pending', 'provisioning'].includes(q.state.data?.status) || Date.now() < busyUntil ? 3000 : 30_000),
    });

    const act = useMutation({
        mutationFn: async (body: Record<string, unknown>) => (await api.post(`/admin/tenants/${id}/action/`, body)).data,
        onSuccess: (_d, body) => {
            toast.success(body.action === 'note' ? 'Note added' : 'Done -- it may take a moment to apply');
            setBusyUntil(Date.now() + 30_000);
            qc.invalidateQueries({ queryKey: ['tenant', id] });
        },
        onError: (err) => toast.error(errorText(err)),
    });

    if (isLoading || !t) return <div className="grid min-h-[40vh] place-items-center"><Spinner className="h-6 w-6" /></div>;
    const setting = ['pending', 'provisioning'].includes(t.status);

    return (
        <>
            <ShellHeader
                title={<span className="flex flex-wrap items-center gap-3">{t.name} <TenantStatus status={t.status} label={t.status_label} /></span>}
                subtitle={`${t.slug} · ${t.contact_name} · ${t.contact_email} · ${t.contact_phone}`}
                actions={<>
                    {t.url && t.status !== 'deleted' && <a href={t.url} target="_blank" rel="noreferrer" className={bandButtonClass}><ExternalLink className="h-4 w-4" />Open instance</a>}
                    {isAdmin && t.status === 'trial' && <button className={bandCtaClass} onClick={() => act.mutate({ action: 'activate' })}>Convert to paid</button>}
                    {isAdmin && t.status === 'failed' && <button className={bandCtaClass} onClick={() => act.mutate({ action: 'retry_provision' })}><RotateCcw className="h-4 w-4" />Retry setup</button>}
                </>}
            />
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
                <KpiCard highlight label="Counted subscribers" value={formatCount(t.estimate?.counted_subscribers)} icon={Users}
                    footnote={`${formatCount(t.subscribers?.active)} active · ${formatCount(t.subscribers?.all)} accounts`} />
                <KpiCard label="Held for this ISP" value={formatKES(t.balance)} icon={Wallet} footnote="customer payments not yet paid out" />
                <KpiCard label="This month's bill (est.)" value={formatKES(t.estimate?.amount)} icon={FileText} footnote={t.estimate?.plan || 'no plan'} />
                <KpiCard label={t.status === 'trial' ? 'Trial' : 'Customer since'} icon={Hourglass}
                    value={t.status === 'trial' ? duration(t.trial_seconds_left) : t.activated_at ? new Date(t.activated_at).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' }) : '—'}
                    footnote={t.status === 'trial' ? `ends ${dateTime(t.trial_ends_at)}` : t.activated_at ? dateTime(t.activated_at) : 'not converted yet'} />
            </div>

            {setting && <Notice tone="info" className="mt-5"><Spinner className="mr-2 inline" />Setting up the instance -- this takes a few minutes.</Notice>}
            {t.status === 'failed' && <Notice tone="bad" className="mt-5"><b>Setup failed.</b> <span className="font-mono text-[12.5px]">{t.last_error}</span></Notice>}
            {t.cancel_requested_at && <Notice className="mt-5">The owner asked to cancel on {dateTime(t.cancel_requested_at)}.</Notice>}

            <div className="mt-6">
                <SegmentedControl<Tab> aria-label="Section" value={tab} onChange={setTab}
                    options={[{ value: 'overview', label: 'Overview' }, { value: 'money', label: 'Money' }, { value: 'activity', label: 'Activity' }, { value: 'instance', label: 'Instance' }]} />
            </div>
            <div className="mt-5">
                {tab === 'overview' && <Overview t={t} isAdmin={!!isAdmin} />}
                {tab === 'money' && <Money t={t} isAdmin={!!isAdmin} />}
                {tab === 'activity' && <ActivityLog t={t} onNote={(message) => act.mutate({ action: 'note', message })} />}
                {tab === 'instance' && <Instance t={t} isAdmin={!!isAdmin} act={(body) => act.mutate(body)} busy={act.isPending} />}
            </div>
        </>
    );
}

function Overview({ t, isAdmin }: { t: any; isAdmin: boolean }) {
    const qc = useQueryClient();
    const { data: plans } = useQuery({ queryKey: ['plans'], queryFn: async () => (await api.get('/admin/plans/')).data });
    const [form, setForm] = useState<any>({});
    useEffect(() => setForm({
        plan: t.plan ?? '', discount_percent: t.discount_percent, notes: t.notes, settlement_method: t.settlement_method,
        settlement_account: t.settlement_account, settlement_account_ref: t.settlement_account_ref, settlement_name: t.settlement_name,
        settlement_hold: t.settlement_hold,
    }), [t]);
    const save = useMutation({
        mutationFn: async (body: any) => (await api.patch(`/admin/tenants/${t.id}/`, body)).data,
        onSuccess: () => { toast.success('Saved'); qc.invalidateQueries({ queryKey: ['tenant', String(t.id)] }); },
        onError: (err) => toast.error(errorText(err)),
    });
    const set = (k: string, v: unknown) => setForm((f: any) => ({ ...f, [k]: v }));
    const byType = (basis: 'active' | 'all') => ['pppoe', 'hotspot', 'static'].map((s) => t.metrics?.[basis]?.[s] ?? 0);
    const chart = [...(t.snapshots || [])].reverse().map((s: any) => ({
        date: s.date, count: ((s.peak?.active?.pppoe || 0) + (s.peak?.active?.hotspot || 0) + (s.peak?.active?.static || 0)),
    }));

    return (
        <div className="grid gap-5 xl:grid-cols-2">
            <Panel>
                <PanelHeader title="Plan & billing" subtitle={t.estimate ? `Estimate at today's counts: ${formatKES(t.estimate.amount)}` : undefined} />
                <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Pricing plan">
                        <Select disabled={!isAdmin} value={form.plan ?? ''} onChange={(e) => set('plan', e.target.value ? Number(e.target.value) : null)}>
                            <option value="">Default plan</option>
                            {plans?.map((p: any) => <option key={p.id} value={p.id}>{p.name}{p.is_active ? '' : ' (inactive)'}</option>)}
                        </Select>
                    </Field>
                    <Field label="Discount %"><Input disabled={!isAdmin} type="number" min={0} max={100} step="0.5" value={form.discount_percent ?? 0} onChange={(e) => set('discount_percent', e.target.value)} /></Field>
                </div>
                {t.estimate?.lines?.length > 0 && (
                    <ul className="mt-4 space-y-1 rounded-xl bg-secondary p-3 text-[13px]">
                        {t.estimate.lines.map((l: any, i: number) => <li key={i} className="flex justify-between gap-3"><span>{l.label}</span><span className="num">{formatKES(l.amount)}</span></li>)}
                    </ul>
                )}
                <PanelHeader className="mt-6" title="Payouts go to" subtitle={`Paybill account prefix for this ISP: ${t.account_prefix}`} />
                <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Method">
                        <Select disabled={!isAdmin} value={form.settlement_method || ''} onChange={(e) => set('settlement_method', e.target.value)}>
                            <option value="">Not set</option><option value="paybill">Paybill (B2B)</option><option value="till">Till / Buy Goods (B2B)</option><option value="phone">M-Pesa phone (B2C)</option>
                        </Select>
                    </Field>
                    <Field label={form.settlement_method === 'phone' ? 'Phone' : 'Paybill / till number'}><Input disabled={!isAdmin} value={form.settlement_account || ''} onChange={(e) => set('settlement_account', e.target.value)} /></Field>
                    {form.settlement_method === 'paybill' && <Field label="Account number"><Input disabled={!isAdmin} value={form.settlement_account_ref || ''} onChange={(e) => set('settlement_account_ref', e.target.value)} /></Field>}
                    <Field label="Registered name"><Input disabled={!isAdmin} value={form.settlement_name || ''} onChange={(e) => set('settlement_name', e.target.value)} /></Field>
                </div>
                <div className="mt-4"><Toggle disabled={!isAdmin} checked={!!form.settlement_hold} onChange={(v) => set('settlement_hold', v)} label="Hold payouts" hint="Stops automatic and manual payouts to this ISP." /></div>
                <Field label="Internal notes" className="mt-4"><Textarea value={form.notes || ''} onChange={(e) => set('notes', e.target.value)} /></Field>
                <div className="mt-4 flex justify-end">
                    <Button onClick={() => save.mutate(isAdmin ? form : { notes: form.notes })} disabled={save.isPending}>{save.isPending && <Spinner />}Save</Button>
                </div>
            </Panel>
            <div className="space-y-5">
                <Panel>
                    <PanelHeader title="Subscribers" subtitle={t.metrics_at ? `Read ${dateTime(t.metrics_at)}` : 'Not read yet'} />
                    <div className="grid grid-cols-3 gap-4">
                        {['PPPoE', 'Hotspot', 'Static'].map((label, i) => (
                            <Stat key={label} label={label} value={formatCount(byType('active')[i])} sub={`${formatCount(byType('all')[i])} accounts`} />
                        ))}
                    </div>
                    {chart.length > 1 && <div className="mt-5"><BarTrend data={chart} xKey="date" yKey="count" height={180} name="Active (daily peak)"
                        formatX={(d) => new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} /></div>}
                </Panel>
                <Panel>
                    <PanelHeader title="Owner" />
                    {t.owners?.map((o: any) => (
                        <div key={o.id} className="text-[14px]"><b>{o.full_name}</b><span className="block text-muted-foreground">{o.email} · {o.phone} · last signed in {o.last_login ? dateTime(o.last_login) : 'never'}</span></div>
                    ))}
                    <dl className="mt-4 grid grid-cols-2 gap-3 text-[13px]">
                        <div><dt className="text-muted-foreground">Signed up</dt><dd>{dateTime(t.created_at)}</dd></div>
                        <div><dt className="text-muted-foreground">Ready</dt><dd>{dateTime(t.ready_at)}</dd></div>
                        <div><dt className="text-muted-foreground">Instance admin</dt><dd className="font-mono">{t.admin_username}</dd></div>
                        <div><dt className="text-muted-foreground">Address</dt><dd className="break-all">{t.url || '—'}</dd></div>
                    </dl>
                </Panel>
            </div>
        </div>
    );
}

function Money({ t, isAdmin }: { t: any; isAdmin: boolean }) {
    const qc = useQueryClient();
    const [page, setPage] = useState(1);
    const [modal, setModal] = useState<null | 'adjust' | 'invoice' | 'payout'>(null);
    const ledger = useQuery({ queryKey: ['ledger', t.id, page], queryFn: async () => (await api.get(`/admin/tenants/${t.id}/ledger/`, { params: { page } })).data });
    const invoices = useQuery({ queryKey: ['invoices', { tenant: t.id }], queryFn: async () => (await api.get('/admin/invoices/', { params: { tenant: t.id } })).data });
    const payouts = useQuery({ queryKey: ['settlements', { tenant: t.id }], queryFn: async () => (await api.get('/admin/settlements/', { params: { tenant: t.id } })).data });
    const refresh = () => ['ledger', 'invoices', 'settlements', 'tenant'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));

    return (
        <div className="space-y-5">
            <Panel>
                <PanelHeader title="Statement" subtitle={`Balance ${formatKES(ledger.data?.balance)} · available to pay out ${formatKES(ledger.data?.available)}`}
                    action={<>
                        <a className="text-[13px] font-semibold text-primary" href={`/api/admin/tenants/${t.id}/ledger/?export=csv`} onClick={(e) => { e.preventDefault(); download(`/admin/tenants/${t.id}/ledger/?export=csv`, `statement-${t.slug}.csv`); }}>CSV</a>
                        {isAdmin && <Button size="sm" variant="outline" onClick={() => setModal('adjust')}>Adjust</Button>}
                        {isAdmin && <Button size="sm" onClick={() => setModal('payout')}><Banknote />Pay out</Button>}
                    </>} />
                <Table loading={ledger.isLoading} head={['Date', 'Type', 'Description', 'Reference', 'Amount']} empty="No money movements yet.">
                    {ledger.data?.results?.map((e: any) => (
                        <tr key={e.id}>
                            <Td className="text-[12.5px] text-muted-foreground">{dateTime(e.created_at)}</Td>
                            <Td>{e.kind_label}</Td>
                            <Td className="max-w-[320px] truncate">{e.description}{e.created_by && <span className="text-muted-foreground"> · {e.created_by}</span>}</Td>
                            <Td className="font-mono text-[12px]">{e.reference}</Td>
                            <Td className={`num text-right font-semibold ${Number(e.amount) < 0 ? 'text-bad' : 'text-ok'}`}>{formatKES(e.amount)}</Td>
                        </tr>
                    ))}
                </Table>
                <Pager page={page} count={ledger.data?.count || 0} onPage={setPage} />
            </Panel>
            <div className="grid gap-5 xl:grid-cols-2">
                <Panel>
                    <PanelHeader title="Invoices" action={isAdmin && <Button size="sm" variant="outline" onClick={() => setModal('invoice')}>Issue invoice</Button>} />
                    <Table loading={invoices.isLoading} head={['Number', 'Period', 'Subs', 'Amount', 'Status']} empty="No invoices yet.">
                        {invoices.data?.results?.map((i: any) => (
                            <tr key={i.id}><Td className="font-mono text-[12.5px]">{i.number}</Td><Td className="text-[12.5px]">{i.period_start} – {i.period_end}</Td>
                                <Td className="num">{i.subscriber_count}</Td><Td className="num">{formatKES(i.amount)}</Td><Td><Pill status={i.status} label={i.status_label} /></Td></tr>
                        ))}
                    </Table>
                </Panel>
                <Panel>
                    <PanelHeader title="Payouts" />
                    <Table loading={payouts.isLoading} head={['Date', 'Amount', 'To', 'Status']} empty="No payouts yet.">
                        {payouts.data?.results?.map((s: any) => (
                            <tr key={s.id}><Td className="text-[12.5px]">{dateTime(s.created_at)}</Td><Td className="num">{formatKES(s.amount)}</Td>
                                <Td className="text-[12.5px]">{s.destination}{s.account_ref && ` · ${s.account_ref}`}</Td><Td><Pill status={s.status} label={s.status_label} /></Td></tr>
                        ))}
                    </Table>
                </Panel>
            </div>
            <AdjustModal open={modal === 'adjust'} onClose={() => setModal(null)} tenant={t} onDone={refresh} />
            <InvoiceModal open={modal === 'invoice'} onClose={() => setModal(null)} tenant={t} onDone={refresh} />
            <PayoutModal open={modal === 'payout'} onClose={() => setModal(null)} tenant={t} available={ledger.data?.available} onDone={refresh} />
        </div>
    );
}

async function download(path: string, name: string) {
    try {
        const { data } = await api.get(path, { responseType: 'blob' });
        const url = URL.createObjectURL(data);
        const a = Object.assign(document.createElement('a'), { href: url, download: name });
        a.click();
        URL.revokeObjectURL(url);
    } catch (err) {
        toast.error(errorText(err, 'Download failed'));
    }
}

function AdjustModal({ open, onClose, tenant, onDone }: { open: boolean; onClose: () => void; tenant: any; onDone: () => void }) {
    const [amount, setAmount] = useState('');
    const [description, setDescription] = useState('');
    const save = useMutation({
        mutationFn: async () => (await api.post(`/admin/tenants/${tenant.id}/ledger/`, { amount, description })).data,
        onSuccess: () => { toast.success('Adjustment recorded'); onDone(); onClose(); setAmount(''); setDescription(''); },
        onError: (err) => toast.error(errorText(err)),
    });
    return (
        <Modal open={open} onClose={onClose} title="Adjust the balance" description="Positive adds money owed to the ISP, negative deducts. The reason is shown on their statement.">
            <div className="space-y-3">
                <Field label="Amount (KES)"><Input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
                <Field label="Reason"><Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="e.g. Refund of duplicate payment QK12..." /></Field>
                <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button><Button disabled={save.isPending} onClick={() => save.mutate()}>Record</Button></div>
            </div>
        </Modal>
    );
}

function InvoiceModal({ open, onClose, tenant, onDone }: { open: boolean; onClose: () => void; tenant: any; onDone: () => void }) {
    const today = new Date();
    const first = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    const last = new Date(today.getFullYear(), today.getMonth(), 0);
    const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const [period, setPeriod] = useState({ start: iso(first), end: iso(last) });
    const preview = useQuery({
        enabled: open, queryKey: ['invoice-preview', tenant.id, period],
        queryFn: async () => (await api.post('/admin/invoices/create/', { tenant: tenant.id, ...period, preview: true })).data,
    });
    const issue = useMutation({
        mutationFn: async () => (await api.post('/admin/invoices/create/', { tenant: tenant.id, ...period })).data,
        onSuccess: (inv) => { toast.success(`${inv.number} issued (${inv.status_label})`); onDone(); onClose(); },
        onError: (err) => toast.error(errorText(err)),
    });
    return (
        <Modal open={open} onClose={onClose} title="Issue an invoice" description="Priced from the daily subscriber counts in the period. Paid from the ISP's balance straight away if it covers it.">
            <div className="grid grid-cols-2 gap-3">
                <Field label="From"><Input type="date" value={period.start} onChange={(e) => setPeriod({ ...period, start: e.target.value })} /></Field>
                <Field label="To"><Input type="date" value={period.end} onChange={(e) => setPeriod({ ...period, end: e.target.value })} /></Field>
            </div>
            {preview.isError && <Notice tone="bad">{errorText(preview.error)}</Notice>}
            {preview.data && (
                <div className="rounded-xl bg-secondary p-3 text-[13px]">
                    <p className="mb-2">{preview.data.plan}: <b>{preview.data.subscriber_count}</b> counted subscribers ({preview.data.count_detail?.days_measured} days measured)</p>
                    <ul className="space-y-1">{preview.data.lines.map((l: any, i: number) => <li key={i} className="flex justify-between"><span>{l.label}</span><span className="num">{formatKES(l.amount)}</span></li>)}</ul>
                    <p className="mt-2 flex justify-between border-t border-border pt-2 font-bold"><span>Total</span><span className="num">{formatKES(preview.data.amount)}</span></p>
                </div>
            )}
            <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button><Button disabled={issue.isPending || !preview.data} onClick={() => issue.mutate()}>Issue</Button></div>
        </Modal>
    );
}

function PayoutModal({ open, onClose, tenant, available, onDone }: { open: boolean; onClose: () => void; tenant: any; available?: string; onDone: () => void }) {
    const [amount, setAmount] = useState('');
    const go = useMutation({
        mutationFn: async () => (await api.post('/admin/settlements/', { tenant: tenant.id, amount: amount || undefined })).data,
        onSuccess: (s) => { toast.success(`Payout ${s.status_label.toLowerCase()}`); onDone(); onClose(); },
        onError: (err) => toast.error(errorText(err)),
    });
    return (
        <Modal open={open} onClose={onClose} title={`Pay out to ${tenant.name}`}
            description={tenant.settlement_method ? `${tenant.settlement_method === 'phone' ? 'B2C to' : 'B2B to'} ${tenant.settlement_account}${tenant.settlement_account_ref ? ` (account ${tenant.settlement_account_ref})` : ''}. Available: ${formatKES(available)} before the payout fee.` : 'This ISP has not set where to send its money.'}>
            <Field label="Amount (blank = everything available)"><Input type="number" step="1" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
            <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button><Button disabled={go.isPending || !tenant.settlement_method} onClick={() => go.mutate()}>Create payout</Button></div>
        </Modal>
    );
}

function ActivityLog({ t, onNote }: { t: any; onNote: (m: string) => void }) {
    const [note, setNote] = useState('');
    const tone: Record<string, string> = { error: 'bg-bad', billing: 'bg-sunset', settlement: 'bg-mpesa', payment: 'bg-mpesa', lifecycle: 'bg-warn', provision: 'bg-primary' };
    return (
        <Panel>
            <PanelHeader title="Activity" subtitle="Everything that happened to this ISP" />
            <form className="mb-5 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (note.trim()) { onNote(note); setNote(''); } }}>
                <Input placeholder="Add a note (call log, agreement, ...)" value={note} onChange={(e) => setNote(e.target.value)} />
                <Button type="submit">Add</Button>
            </form>
            <ol className="space-y-4">
                {t.events?.map((e: any) => (
                    <li key={e.id} className="flex gap-3">
                        <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${tone[e.kind] || 'bg-border-strong'}`} />
                        <div className="min-w-0 text-[14px]">
                            <p className="break-words">{e.message}</p>
                            <p className="text-[12px] text-muted-foreground">{dateTime(e.created_at)} · {e.kind}{e.actor && ` · ${e.actor}`}</p>
                        </div>
                    </li>
                ))}
            </ol>
        </Panel>
    );
}

function Instance({ t, isAdmin, act, busy }: { t: any; isAdmin: boolean; act: (b: Record<string, unknown>) => void; busy: boolean }) {
    const [logs, setLogs] = useState<string | null>(null);
    const [service, setService] = useState('backend');
    const [suspendOpen, setSuspendOpen] = useState(false);
    const [reason, setReason] = useState('');
    const [days, setDays] = useState('2');
    const [confirm, setConfirm] = useState('');
    const loadLogs = async () => {
        try { setLogs((await api.post(`/admin/tenants/${t.id}/action/`, { action: 'logs', service })).data.logs); }
        catch (err) { toast.error(errorText(err)); }
    };
    const live = ['trial', 'active', 'past_due'].includes(t.status);
    return (
        <div className="grid gap-5 xl:grid-cols-2">
            <Panel>
                <PanelHeader title="Instance" leading={<Server className="h-5 w-5 text-primary" />} />
                <div className="grid grid-cols-2 gap-4">
                    <Stat label="State" value={t.instance_state ? <Pill status={t.instance_state} label={t.instance_label} /> : '—'} sub={t.last_health_at ? `healthy ${dateTime(t.last_health_at)}` : undefined} />
                    <Stat label="Port" value={t.port || '—'} sub={t.url} />
                    <Stat label="Version" value={t.image_tag || '—'} />
                    <Stat label="Paybill prefix" value={t.account_prefix} sub="customers may type it before their username" />
                </div>
                {t.last_error && <Notice tone="bad" className="mt-4"><span className="font-mono text-[12px]">{t.last_error}</span></Notice>}
                <div className="mt-5 flex flex-wrap gap-2">
                    <Button variant="outline" onClick={() => act({ action: 'health' })} disabled={busy}><Activity />Check health</Button>
                    <Button variant="outline" onClick={() => act({ action: 'metrics' })} disabled={busy}><Users />Read subscriber counts</Button>
                    {isAdmin && <Button variant="outline" onClick={() => act({ action: 'resync' })} disabled={busy}><RefreshCw />Re-apply config</Button>}
                    {isAdmin && live && <Button variant="outline" onClick={() => act({ action: 'restart' })} disabled={busy}><RotateCcw />Restart</Button>}
                </div>
            </Panel>
            {isAdmin && (
                <Panel>
                    <PanelHeader title="Lifecycle" />
                    <div className="space-y-4">
                        {t.status === 'trial' && (
                            <div className="flex items-end gap-2">
                                <Field label="Extend the trial by (days)" className="flex-1"><Input type="number" min={1} max={60} value={days} onChange={(e) => setDays(e.target.value)} /></Field>
                                <Button variant="outline" onClick={() => act({ action: 'extend_trial', days: Number(days) })}>Extend</Button>
                            </div>
                        )}
                        {live && <Button variant="outline" className="w-full" onClick={() => setSuspendOpen(true)}><Pause />Suspend (stop the instance, keep data)</Button>}
                        {['suspended', 'cancelled'].includes(t.status) && <Button className="w-full" onClick={() => act({ action: 'resume' })}><Play />Resume</Button>}
                        {t.status === 'suspended' && !t.activated_at && <Button variant="outline" className="w-full" onClick={() => act({ action: 'extend_trial', days: Number(days) })}>Give {days} more trial day(s)</Button>}
                        {!['cancelled', 'deleted'].includes(t.status) && <Button variant="outline" className="w-full" onClick={() => window.confirm(`Cancel ${t.name}? The instance stops; data is kept.`) && act({ action: 'cancel' })}>Cancel subscription</Button>}
                        {t.status !== 'deleted' && (
                            <div className="rounded-xl border border-bad/30 p-4">
                                <p className="text-[13.5px] font-semibold text-bad">Delete the instance and its database</p>
                                <p className="mt-1 text-[12.5px] text-muted-foreground">Cannot be undone. The money history is kept. Type <b>{t.slug}</b> to confirm.</p>
                                <div className="mt-2 flex gap-2">
                                    <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder={t.slug} />
                                    <Button variant="destructive" disabled={confirm !== t.slug} onClick={() => act({ action: 'destroy', confirm })}><Trash2 />Delete</Button>
                                </div>
                            </div>
                        )}
                    </div>
                </Panel>
            )}
            <Panel className="xl:col-span-2">
                <PanelHeader title="Logs" action={<>
                    <Select className="h-9 w-44" value={service} onChange={(e) => setService(e.target.value)}>
                        {['backend', 'celery_worker', 'celery_beat', 'frontend', 'whatsapp_service'].map((s) => <option key={s}>{s}</option>)}
                    </Select>
                    <Button size="sm" variant="outline" onClick={loadLogs}>Load</Button>
                </>} />
                {logs != null ? <pre className="max-h-[420px] overflow-auto rounded-xl bg-[#0f1a14] p-4 text-[12px] leading-relaxed text-[#cfe3d6]">{logs || '(empty)'}</pre>
                    : <p className="text-[13px] text-muted-foreground">The last 200 lines of the chosen container.</p>}
            </Panel>
            <Modal open={suspendOpen} onClose={() => setSuspendOpen(false)} title={`Suspend ${t.name}`} description="The instance is stopped: the ISP and its customers lose access (including the hotspot portal) until it is resumed. The owner is emailed the reason.">
                <Field label="Reason"><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. invoice INV-2026-00012 unpaid" /></Field>
                <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setSuspendOpen(false)}>Cancel</Button>
                    <Button variant="destructive" onClick={() => { act({ action: 'suspend', reason }); setSuspendOpen(false); }}>Suspend</Button></div>
            </Modal>
        </div>
    );
}
