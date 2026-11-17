import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { ArrowLeft, ArrowRight, Ban, CheckCircle2, Download, FileText, Loader2, Mail, Plus, Search, Settings2, ShieldCheck, Trash2 } from 'lucide-react';
import { adminAPI, invoiceAPI } from '../../services/api';
import { useAuthStore } from '../../store/authStore';
import { errText } from '../../utils/errText';
import { downloadBlob } from '../../utils/downloadBlob';
import { EmptyState, Panel, ShellHeader, Skeleton, bandButtonClass, bandCtaClass, formatDateEAT } from '../../components/savanna';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { PdfPreview, TEMPLATE_INFO } from '../../components/settings/InvoicesTab';
import { cn } from '@/lib/utils';

const INPUT = 'w-full border rounded-lg px-3 py-2 text-sm bg-card';
const LABEL = 'block text-sm font-medium text-foreground/80 mb-1';
const BTN = 'inline-flex items-center justify-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium disabled:opacity-50';
const TEMPLATES = Object.keys(TEMPLATE_INFO);
const kes = (v: string | number) => `KES ${Number(v).toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const STATUS_TONE: Record<string, string> = {
    paid: 'bg-ok-bg text-ok', issued: 'bg-warn-bg text-warn', draft: 'bg-chip text-muted-foreground', void: 'bg-bad-bg text-bad',
};
const ETIMS_TONE: Record<string, string> = {
    signed: 'bg-ok-bg text-ok', failed: 'bg-bad-bg text-bad', pending: 'bg-chip text-muted-foreground', credited: 'bg-chip text-foreground',
};

/**
 * Customer invoices: list, create (from a PPPoE payment or by hand), view
 * in any design, sign with KRA eTIMS, email, mark paid, void.
 */
export default function Invoices() {
    const navigate = useNavigate();
    const user = useAuthStore((s) => s.user);
    const isAdmin = !!user?.is_superuser || user?.role === 'admin';
    const [searchInput, setSearchInput] = useState('');
    const [search, setSearch] = useState('');
    const [status, setStatus] = useState('');
    const [etims, setEtims] = useState('');
    const [page, setPage] = useState(1);
    const [creating, setCreating] = useState(false);
    const [open, setOpen] = useState<number | null>(null);

    const { data, isLoading } = useQuery({
        queryKey: ['invoices', search, status, etims, page],
        queryFn: async () => (await invoiceAPI.list({ search: search || undefined, status: status || undefined, etims_status: etims || undefined, page })).data,
    });
    const pages = data ? Math.max(1, Math.ceil(data.count / 20)) : 1;
    const select = 'h-10 rounded-full border border-input bg-card px-4 text-[13.5px]';

    return (
        <div className="space-y-[18px]">
            <ShellHeader
                title="Invoices"
                subtitle={data ? `${data.count.toLocaleString()} invoice${data.count === 1 ? '' : 's'}` : ' '}
                actions={<>
                    {isAdmin && <button className={bandButtonClass} onClick={() => navigate('/admin/settings?tab=invoices')}><Settings2 className="h-[18px] w-[18px]" /> Design &amp; eTIMS</button>}
                    <button className={bandCtaClass} onClick={() => setCreating(true)}><Plus className="h-[18px] w-[18px]" /> New invoice</button>
                </>}
            />
            <Panel>
                <div className="mb-4 flex flex-wrap items-center gap-2">
                    <form onSubmit={(e) => { e.preventDefault(); setSearch(searchInput.trim()); setPage(1); }} className="relative">
                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <input className="h-10 w-64 rounded-full border border-input bg-card pl-9 pr-4 text-[13.5px]" placeholder="Number, customer, M-Pesa ref…"
                            value={searchInput} onChange={(e) => setSearchInput(e.target.value)} />
                    </form>
                    <select className={select} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
                        <option value="">All statuses</option><option value="paid">Paid</option><option value="issued">Unpaid</option>
                        <option value="draft">Draft</option><option value="void">Void</option>
                    </select>
                    <select className={select} value={etims} onChange={(e) => { setEtims(e.target.value); setPage(1); }}>
                        <option value="">eTIMS: any</option><option value="signed">Signed</option><option value="none">Not signed</option>
                        <option value="failed">Failed</option><option value="credited">Credit note</option>
                    </select>
                </div>
                {isLoading ? (
                    <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-11" />)}</div>
                ) : !data?.results?.length ? (
                    <EmptyState message="No invoices yet. Create one from a PPPoE payment, or turn on automatic invoicing in Settings → Invoices." />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-[13.5px]">
                            <thead>
                                <tr className="text-left text-[11.5px] uppercase tracking-wide text-faint">
                                    <th className="pb-2 pr-4 font-medium">Invoice</th><th className="pb-2 pr-4 font-medium">Customer</th>
                                    <th className="pb-2 pr-4 font-medium">Date</th><th className="pb-2 pr-4 text-right font-medium">Total</th>
                                    <th className="pb-2 pr-4 font-medium">Status</th><th className="pb-2 font-medium">KRA eTIMS</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.results.map((inv: any) => (
                                    <tr key={inv.id} onClick={() => setOpen(inv.id)} className="cursor-pointer border-t border-border-soft hover:bg-secondary/60">
                                        <td className="py-2.5 pr-4 font-semibold font-mono text-[13px]">{inv.number}<div className="font-sans text-xs font-normal text-muted-foreground">{inv.payment_ref}</div></td>
                                        <td className="py-2.5 pr-4">{inv.customer_name}<div className="text-xs text-muted-foreground">{inv.customer_username}</div></td>
                                        <td className="py-2.5 pr-4 whitespace-nowrap">{inv.issue_date}</td>
                                        <td className="py-2.5 pr-4 text-right font-semibold tabular-nums">{kes(inv.total)}</td>
                                        <td className="py-2.5 pr-4"><span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', STATUS_TONE[inv.status])}>{inv.status === 'issued' ? 'unpaid' : inv.status}</span></td>
                                        <td className="py-2.5">{inv.etims_status === 'none' ? <span className="text-xs text-muted-foreground">—</span>
                                            : <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', ETIMS_TONE[inv.etims_status])}>{inv.etims_status}</span>}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                        {pages > 1 && (
                            <div className="mt-4 flex items-center justify-end gap-2 text-sm">
                                <button className={cn(BTN, 'border')} disabled={page <= 1} onClick={() => setPage(page - 1)}><ArrowLeft className="h-4 w-4" /></button>
                                <span>Page {page} of {pages}</span>
                                <button className={cn(BTN, 'border')} disabled={page >= pages} onClick={() => setPage(page + 1)}><ArrowRight className="h-4 w-4" /></button>
                            </div>
                        )}
                    </div>
                )}
            </Panel>
            <CreateDialog open={creating} onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); setOpen(id); }} />
            <InvoiceDialog id={open} onClose={() => setOpen(null)} isAdmin={isAdmin} />
        </div>
    );
}

function CreateDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (id: number) => void }) {
    const qc = useQueryClient();
    const [mode, setMode] = useState<'payment' | 'manual'>('payment');
    const [search, setSearch] = useState('');
    const [pin, setPin] = useState('');
    const [address, setAddress] = useState('');
    const [customerSearch, setCustomerSearch] = useState('');
    const [customer, setCustomer] = useState<any>(null);
    const [lines, setLines] = useState([{ description: '', quantity: '1', unit_price: '' }]);
    const [status, setStatus] = useState('issued');
    const [notes, setNotes] = useState('');

    const { data: payments, isFetching } = useQuery({
        queryKey: ['invoiceable-payments', search],
        queryFn: async () => (await invoiceAPI.payments({ search: search || undefined })).data,
        enabled: open && mode === 'payment',
    });
    const { data: customers } = useQuery({
        queryKey: ['invoice-customer-search', customerSearch],
        queryFn: async () => {
            const r = await adminAPI.getSubscribers({ search: customerSearch, page_size: 8 });
            return r.data.results || r.data;
        },
        enabled: open && mode === 'manual' && customerSearch.length >= 2 && !customer,
    });
    const done = (r: any) => {
        toast.success(r.data.created === false ? `Already invoiced as ${r.data.number}` : `Invoice ${r.data.number} created`);
        qc.invalidateQueries({ queryKey: ['invoices'] });
        qc.invalidateQueries({ queryKey: ['invoiceable-payments'] });
        onCreated(r.data.id);
    };
    const fromPayment = useMutation({
        mutationFn: (transaction_id: number) => invoiceAPI.fromTransaction({ transaction_id, customer_pin: pin || undefined, customer_address: address || undefined }),
        onSuccess: done, onError: (e) => toast.error(errText(e)),
    });
    const manual = useMutation({
        mutationFn: () => invoiceAPI.create({ customer_id: customer?.id, lines, status, notes, customer_pin: pin || undefined, customer_address: address || undefined }),
        onSuccess: done, onError: (e) => toast.error(errText(e)),
    });
    const total = lines.reduce((a, l) => a + (Number(l.quantity) || 0) * (Number(l.unit_price) || 0), 0);

    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl">
                <DialogHeader><DialogTitle>New invoice</DialogTitle></DialogHeader>
                <div className="inline-flex rounded-full bg-chip p-1 text-[12.5px] font-semibold">
                    {(['payment', 'manual'] as const).map((m) => (
                        <button key={m} onClick={() => setMode(m)} className={cn('h-7 rounded-full px-3.5', mode === m ? 'bg-primary text-primary-foreground' : 'text-muted-foreground')}>
                            {m === 'payment' ? 'From a payment' : 'Manual'}
                        </button>
                    ))}
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div><label className={LABEL}>Customer KRA PIN (optional)</label><input className={INPUT} value={pin} onChange={(e) => setPin(e.target.value.toUpperCase())} placeholder="A123456789Z" /></div>
                    <div><label className={LABEL}>Customer address (optional)</label><input className={INPUT} value={address} onChange={(e) => setAddress(e.target.value)} /></div>
                </div>
                {mode === 'payment' ? (
                    <div>
                        <input className={INPUT} placeholder="Search by customer or M-Pesa code" value={search} onChange={(e) => setSearch(e.target.value)} />
                        <div className="mt-2 max-h-80 overflow-y-auto rounded-lg border">
                            {isFetching && !payments ? <div className="p-4"><Loader2 className="h-4 w-4 animate-spin" /></div> : (payments || []).map((p: any) => (
                                <div key={p.id} className="flex items-center justify-between gap-3 border-b border-border-soft px-3 py-2 text-sm last:border-0">
                                    <div className="min-w-0">
                                        <p className="truncate font-medium">{p.name} <span className="text-xs text-muted-foreground">· {p.username}</span></p>
                                        <p className="truncate text-xs text-muted-foreground">{formatDateEAT(p.created_at)} · {p.receipt} · {p.plan || 'balance top-up'}</p>
                                    </div>
                                    <span className="font-semibold tabular-nums">{kes(p.amount)}</span>
                                    {p.invoice_id
                                        ? <button className={cn(BTN, 'border')} onClick={() => onCreated(p.invoice_id)}>{p.invoice_number}</button>
                                        : <button className={cn(BTN, 'bg-primary text-primary-foreground')} disabled={fromPayment.isPending} onClick={() => fromPayment.mutate(p.id)}>Invoice</button>}
                                </div>
                            ))}
                            {payments && !payments.length && <p className="p-4 text-sm text-muted-foreground">No completed PPPoE / static IP payments found.</p>}
                        </div>
                    </div>
                ) : (
                    <div className="space-y-3">
                        <div>
                            <label className={LABEL}>Customer</label>
                            {customer ? (
                                <div className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
                                    <span>{customer.full_name || customer.username} <span className="text-muted-foreground">· {customer.username}</span></span>
                                    <button className="text-xs text-primary" onClick={() => setCustomer(null)}>Change</button>
                                </div>
                            ) : (
                                <>
                                    <input className={INPUT} placeholder="Type a name, username or phone" value={customerSearch} onChange={(e) => setCustomerSearch(e.target.value)} />
                                    {(customers || []).length > 0 && (
                                        <div className="mt-1 max-h-40 overflow-y-auto rounded-lg border">
                                            {customers.map((c: any) => (
                                                <button key={c.id} className="block w-full px-3 py-1.5 text-left text-sm hover:bg-secondary" onClick={() => setCustomer(c)}>
                                                    {c.full_name || c.username} <span className="text-xs text-muted-foreground">· {c.username} · {c.phone_number}</span>
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                        <div className="space-y-2">
                            {lines.map((l, i) => (
                                <div key={i} className="grid grid-cols-[1fr_70px_110px_32px] gap-2">
                                    <input className={INPUT} placeholder="Description" value={l.description} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, description: e.target.value } : x))} />
                                    <input className={INPUT} type="number" min={1} value={l.quantity} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, quantity: e.target.value } : x))} />
                                    <input className={INPUT} type="number" min={0} step="0.01" placeholder="Price" value={l.unit_price} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, unit_price: e.target.value } : x))} />
                                    <button className="text-muted-foreground hover:text-bad disabled:opacity-30" disabled={lines.length === 1} onClick={() => setLines(lines.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></button>
                                </div>
                            ))}
                            <button className="text-sm font-medium text-primary" onClick={() => setLines([...lines, { description: '', quantity: '1', unit_price: '' }])}>+ Add line</button>
                        </div>
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                            <div><label className={LABEL}>Status</label>
                                <select className={INPUT} value={status} onChange={(e) => setStatus(e.target.value)}>
                                    <option value="issued">Unpaid (issue now)</option><option value="paid">Already paid</option><option value="draft">Draft</option>
                                </select>
                            </div>
                            <div><label className={LABEL}>Notes</label><input className={INPUT} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-sm">Total <b className="tabular-nums">{kes(total)}</b></span>
                            <button className={cn(BTN, 'bg-primary text-primary-foreground')} disabled={!customer || manual.isPending} onClick={() => manual.mutate()}>
                                {manual.isPending && <Loader2 className="h-4 w-4 animate-spin" />} Create invoice
                            </button>
                        </div>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}

function InvoiceDialog({ id, onClose, isAdmin }: { id: number | null; onClose: () => void; isAdmin: boolean }) {
    const qc = useQueryClient();
    const [template, setTemplate] = useState('');
    const [version, setVersion] = useState(0);
    const { data: inv } = useQuery({ queryKey: ['invoice', id], queryFn: async () => (await invoiceAPI.get(id!)).data, enabled: id !== null });
    useEffect(() => { if (inv) setTemplate(inv.template); }, [inv?.id]); // eslint-disable-line react-hooks/exhaustive-deps
    const refresh = () => { qc.invalidateQueries({ queryKey: ['invoice', id] }); qc.invalidateQueries({ queryKey: ['invoices'] }); setVersion((v) => v + 1); };
    const act = useMutation({
        mutationFn: (action: string) => invoiceAPI.action(id!, action),
        onSuccess: (_r, action) => { toast.success({ sign: 'Signed with KRA', send: 'Invoice emailed', void: 'Invoice voided', mark_paid: 'Marked paid', issue: 'Invoice issued' }[action] || 'Done'); refresh(); },
        onError: (e) => { toast.error(errText(e)); refresh(); },
    });
    const saveTemplate = useMutation({
        mutationFn: (t: string) => invoiceAPI.update(id!, { template: t }),
        onSuccess: () => { toast.success('Design saved for this invoice'); refresh(); },
        onError: (e) => toast.error(errText(e)),
    });

    return (
        <Dialog open={id !== null} onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-5xl">
                <DialogHeader><DialogTitle className="flex items-center gap-2"><FileText className="h-5 w-5" /> {inv?.number || 'Invoice'}</DialogTitle></DialogHeader>
                {!inv ? <Skeleton className="h-96" /> : (
                    <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
                        <PdfPreview className="h-[70vh]" deps={[id, template, version]} load={async () => (await invoiceAPI.pdf(id!, template)).data} />
                        <div className="space-y-4 text-sm">
                            <div className="rounded-xl bg-secondary p-4">
                                <p className="text-xs uppercase text-muted-foreground">{inv.customer_name} · {inv.customer_username}</p>
                                <p className="mt-1 text-2xl font-extrabold tabular-nums">{kes(inv.total)}</p>
                                <p className="mt-1 flex flex-wrap gap-2">
                                    <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', STATUS_TONE[inv.status])}>{inv.status === 'issued' ? 'unpaid' : inv.status}</span>
                                    {inv.etims_status !== 'none' && <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', ETIMS_TONE[inv.etims_status])}>eTIMS {inv.etims_status}</span>}
                                    {inv.sent_at && <span className="text-xs text-muted-foreground">Emailed {formatDateEAT(inv.sent_at)}</span>}
                                </p>
                                {inv.etims_error && inv.etims_status === 'failed' && <p className="mt-2 text-xs text-bad">{inv.etims_error}</p>}
                                {inv.etims_status === 'signed' && <p className="mt-2 break-all text-xs text-muted-foreground">KRA receipt {inv.etims_receipt_no} · signature {inv.etims_signature}</p>}
                            </div>
                            <div>
                                <label className={LABEL}>Design</label>
                                <div className="flex flex-wrap gap-1.5">
                                    {TEMPLATES.map((t) => (
                                        <button key={t} onClick={() => setTemplate(t)}
                                            className={cn('rounded-full border px-3 py-1 text-xs font-medium capitalize', template === t ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-secondary')}>{t}</button>
                                    ))}
                                </div>
                                {template !== inv.template && (
                                    <button className="mt-2 text-xs font-medium text-primary" onClick={() => saveTemplate.mutate(template)}>Use {template} for this invoice</button>
                                )}
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                <button className={cn(BTN, 'border')} onClick={async () => {
                                    try { downloadBlob((await invoiceAPI.pdf(id!, template)).data, `${inv.number}.pdf`); } catch (e) { toast.error(errText(e)); }
                                }}><Download className="h-4 w-4" /> Download PDF</button>
                                <button className={cn(BTN, 'border')} disabled={act.isPending || !(inv.customer_email) || inv.status === 'draft'} title={inv.customer_email ? '' : 'No email address on this invoice'}
                                    onClick={() => act.mutate('send')}><Mail className="h-4 w-4" /> Email to customer</button>
                                {inv.status === 'draft' && <button className={cn(BTN, 'bg-primary text-primary-foreground')} disabled={act.isPending} onClick={() => act.mutate('issue')}>Issue invoice</button>}
                                {inv.status === 'issued' && <button className={cn(BTN, 'bg-primary text-primary-foreground')} disabled={act.isPending} onClick={() => act.mutate('mark_paid')}><CheckCircle2 className="h-4 w-4" /> Mark paid</button>}
                                {['none', 'failed', 'pending'].includes(inv.etims_status) && inv.status !== 'void' && inv.status !== 'draft' && (
                                    <button className={cn(BTN, 'border')} disabled={act.isPending} onClick={() => act.mutate('sign')}>
                                        {act.isPending && act.variables === 'sign' ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />} Sign with KRA
                                    </button>
                                )}
                                {isAdmin && inv.status !== 'void' && (
                                    <button className={cn(BTN, 'border text-bad')} disabled={act.isPending}
                                        onClick={() => window.confirm(inv.etims_status === 'signed'
                                            ? 'Void this invoice? A credit note will be sent to KRA eTIMS.' : 'Void this invoice?') && act.mutate('void')}>
                                        <Ban className="h-4 w-4" /> Void
                                    </button>
                                )}
                            </div>
                            {inv.customer_email === '' && <p className="text-xs text-muted-foreground">Add an email address to the customer to email invoices.</p>}
                        </div>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
