import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { analyticsAPI, adminAPI, billingAPI } from '../../services/api';
import { Loader2, ShieldAlert, ChevronLeft, ChevronRight, Smartphone, Store, UserPlus, X, Search, Calendar } from 'lucide-react';
import { format, subDays } from 'date-fns';
import toast from 'react-hot-toast';
import { useAuthStore } from '../../store/authStore';
import ExportMenu from '../../components/ExportMenu';

// utilized = paid for a plan; assigned = in a subscriber's balance;
// review = hotspot payer waiting for an admin; open = not linked to anyone.
const STATUS_BADGE: Record<string, { label: string; className: string; title?: string }> = {
    utilized: { label: 'Used', className: 'bg-ok-bg text-ok', title: 'Paid for a plan' },
    assigned: { label: 'Assigned', className: 'bg-accent text-accent-foreground', title: "In the subscriber's balance" },
    review: { label: 'Needs assignment', className: 'bg-warn-bg text-warn', title: 'Hotspot payer: not applied automatically' },
    open: { label: 'Open', className: 'bg-chip text-muted-foreground', title: 'Not linked to anyone yet' },
};

const METHOD_BADGE: Record<string, string> = {
    stk: 'bg-primary/10 text-primary',
    c2b: 'bg-cyan-100 text-cyan-800',
};

interface PaymentRow {
    c2b_payment_id: number | null;
    transaction_id: string;
    customer: string;
    // Decoded name Safaricom sent with a Buy Goods/Paybill payment (or the matched customer's name).
    payer_name?: string;
    // Plan the money activated, 'Account balance', or null when not yet assigned.
    used_for?: string | null;
    // Hotspot payer's till payment: nothing applied until an admin assigns it.
    needs_assignment?: boolean;
    matched: boolean;
    amount: number;
    method: 'stk' | 'c2b';
    status: 'utilized' | 'assigned' | 'review' | 'open';
    paid_at: string;
}

export default function Payments() {
    const user = useAuthStore((state) => state.user);
    const [page, setPage] = useState(1);
    const [assignTarget, setAssignTarget] = useState<PaymentRow | null>(null);
    const pageSize = 20;
    const queryClient = useQueryClient();

    // Admin only -- this page shows raw payer data (including unmatched
    // C2B payers' hashed phone numbers), not just revenue totals, so the
    // admin/sales split used elsewhere (e.g. Reports) isn't strict enough.
    const isAdmin = !!user?.is_superuser || user?.role === 'admin';
    // Period filter (defaults to this month); both ends inclusive, Nairobi days.
    const [startDate, setStartDate] = useState(format(new Date(), 'yyyy-MM-01'));
    const [endDate, setEndDate] = useState(format(new Date(), 'yyyy-MM-dd'));
    const setRange = (start: string, end: string) => { setStartDate(start); setEndDate(end); setPage(1); };

    const { data, isLoading, isError, error } = useQuery({
        queryKey: ['admin-recent-payments', page, startDate, endDate],
        queryFn: async () => {
            const res = await analyticsAPI.getRecentPayments(page, pageSize, { start_date: startDate || undefined, end_date: endDate || undefined });
            return res.data;
        },
        enabled: isAdmin,
    });

    if (!isAdmin) {
        return (
            <div className="bg-card rounded-2xl shadow-sm border border-border p-8 text-center">
                <ShieldAlert className="h-10 w-10 text-red-400 mx-auto mb-3" />
                <h2 className="text-lg font-semibold text-foreground">Admins only</h2>
                <p className="text-sm text-muted-foreground mt-1">You don't have permission to view payments.</p>
            </div>
        );
    }

    const payments: PaymentRow[] = data?.results || [];
    const totalCount = data?.count ?? payments.length;
    const totalPages = data?.total_pages ?? Math.max(1, Math.ceil(totalCount / pageSize));

    return (
        <div>
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
                <h1 className="text-2xl font-bold">Payments</h1>
                <div className="flex flex-wrap items-center gap-2">
                    {[
                        { label: 'Today', start: format(new Date(), 'yyyy-MM-dd') },
                        { label: '7 days', start: format(subDays(new Date(), 6), 'yyyy-MM-dd') },
                        { label: 'This month', start: format(new Date(), 'yyyy-MM-01') },
                        { label: 'All', start: '' },
                    ].map((r) => {
                        const active = startDate === r.start && (r.start ? endDate === format(new Date(), 'yyyy-MM-dd') : !endDate);
                        return (
                            <button
                                key={r.label}
                                onClick={() => setRange(r.start, r.start ? format(new Date(), 'yyyy-MM-dd') : '')}
                                className={`h-9 rounded-full px-3.5 text-[13px] font-semibold ${active ? 'bg-primary text-primary-foreground' : 'bg-chip text-muted-foreground hover:text-foreground'}`}
                            >
                                {r.label}
                            </button>
                        );
                    })}
                    <div className="flex h-10 items-center gap-2 rounded-full border border-input bg-card px-3">
                        <Calendar className="h-4 w-4 text-muted-foreground" />
                        <input type="date" aria-label="From" value={startDate} max={endDate || undefined}
                            onChange={(e) => setRange(e.target.value, endDate)}
                            className="bg-transparent text-[13px] text-foreground focus:outline-none" />
                        <span className="text-muted-foreground">–</span>
                        <input type="date" aria-label="To" value={endDate} min={startDate || undefined}
                            onChange={(e) => setRange(startDate, e.target.value)}
                            className="bg-transparent text-[13px] text-foreground focus:outline-none" />
                    </div>
                    <ExportMenu
                        path="/analytics/recent-payments/"
                        params={{ start_date: startDate || undefined, end_date: endDate || undefined }}
                        filename={`payments_${startDate || 'all'}_${endDate || 'now'}`}
                    />
                </div>
            </div>

            {data && (
                <div className="mb-4 flex flex-wrap gap-x-8 gap-y-2 text-sm">
                    <span className="text-muted-foreground">Payments <strong className="num text-foreground">{totalCount.toLocaleString()}</strong></span>
                    <span className="text-muted-foreground">Total <strong className="num text-foreground">KES {Number(data.amount_total || 0).toLocaleString()}</strong></span>
                    {data.unassigned > 0 && (
                        <span className="text-muted-foreground">Not assigned <strong className="num text-warn">{data.unassigned}</strong></span>
                    )}
                </div>
            )}

            <div className="bg-card rounded-2xl shadow-sm border border-border overflow-hidden">
                <div className="bg-primary px-4 sm:px-6 py-4">
                    <h2 className="text-white font-bold text-lg">Recent Payments</h2>
                    <p className="text-primary-foreground/80 text-sm mt-0.5">STK Push and C2B till payments, most recent first</p>
                </div>

                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-border">
                        <thead className="bg-secondary">
                            <tr>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Transaction ID</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Customer</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Amount</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Method</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Used for</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Status</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Date &amp; Time</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="bg-card divide-y divide-border">
                            {isLoading ? (
                                <tr>
                                    <td colSpan={8} className="px-6 py-8 text-center text-muted-foreground">
                                        <div className="flex justify-center items-center">
                                            <Loader2 className="h-6 w-6 animate-spin mr-2" />
                                            Loading payments...
                                        </div>
                                    </td>
                                </tr>
                            ) : isError ? (
                                <tr>
                                    <td colSpan={8} className="px-6 py-8 text-center text-red-500">
                                        Error loading payments: {(error as Error).message}
                                    </td>
                                </tr>
                            ) : payments.length === 0 ? (
                                <tr>
                                    <td colSpan={8} className="px-6 py-8 text-center text-muted-foreground">
                                        No payments found.
                                    </td>
                                </tr>
                            ) : (
                                payments.map((p) => (
                                    <tr key={`${p.method}-${p.transaction_id}`} className="hover:bg-secondary transition">
                                        <td className="px-4 py-4 whitespace-nowrap text-sm font-mono text-foreground">{p.transaction_id}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm">
                                            {p.payer_name && <span className="block font-semibold text-foreground">{p.payer_name}</span>}
                                            <span className="block max-w-[220px] truncate font-mono text-xs text-muted-foreground" title={p.customer}>{p.customer}</span>
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-foreground">KES {Number(p.amount).toLocaleString()}</td>
                                        <td className="px-4 py-4 whitespace-nowrap">
                                            <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium uppercase ${METHOD_BADGE[p.method]}`}>
                                                {p.method === 'stk' ? <Smartphone className="h-3 w-3" /> : <Store className="h-3 w-3" />}
                                                {p.method}
                                            </span>
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm">
                                            {p.used_for ? (
                                                <span className={p.used_for === 'Account balance' || p.used_for === 'Activation failed' ? 'text-muted-foreground' : 'font-medium text-foreground'}>
                                                    {p.used_for}
                                                </span>
                                            ) : p.c2b_payment_id ? (
                                                <button
                                                    onClick={() => setAssignTarget(p)}
                                                    className="inline-flex items-center gap-1 rounded-full bg-warn-bg px-2.5 py-1 text-xs font-semibold text-warn hover:opacity-90"
                                                    title="Not linked to anyone yet: assign it to a subscriber"
                                                >
                                                    <UserPlus className="h-3 w-3" /> Assign to subscriber
                                                </button>
                                            ) : <span className="text-muted-foreground">—</span>}
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap">
                                            {(() => {
                                                const badge = STATUS_BADGE[p.status] || STATUS_BADGE.open;
                                                return (
                                                    <span title={badge.title} className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badge.className}`}>
                                                        {badge.label}
                                                    </span>
                                                );
                                            })()}
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-muted-foreground">
                                            {p.paid_at ? format(new Date(p.paid_at), 'MMM d, yyyy HH:mm') : '-'}
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap">
                                            {/* Any till payment that hasn't paid for a plan can be (re)assigned. */}
                                            {p.status !== 'utilized' && p.c2b_payment_id && (
                                                <button
                                                    onClick={() => setAssignTarget(p)}
                                                    className="flex items-center px-2 py-1 bg-primary text-white rounded text-xs hover:bg-primary/90"
                                                    title="Assign this payment to a customer"
                                                >
                                                    <UserPlus className="h-3 w-3 mr-1" /> {p.matched ? 'Reassign' : 'Assign'}
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                <div className="flex items-center justify-between px-4 py-3 border-t border-border text-sm text-muted-foreground">
                    <span>
                        {totalCount === 0 ? '0 results' : `Page ${page} of ${totalPages} · ${totalCount} total`}
                    </span>
                    <div className="flex gap-2">
                        <button
                            disabled={page <= 1}
                            onClick={() => setPage((p) => Math.max(1, p - 1))}
                            className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-secondary"
                        >
                            <ChevronLeft className="h-4 w-4" /> Prev
                        </button>
                        <button
                            disabled={page >= totalPages}
                            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                            className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-secondary"
                        >
                            Next <ChevronRight className="h-4 w-4" />
                        </button>
                    </div>
                </div>
            </div>

            {assignTarget && (
                <AssignPaymentModal
                    payment={assignTarget}
                    onClose={() => setAssignTarget(null)}
                    onAssigned={() => {
                        setAssignTarget(null);
                        queryClient.invalidateQueries({ queryKey: ['admin-recent-payments'] });
                    }}
                />
            )}
        </div>
    );
}

function AssignPaymentModal({ payment, onClose, onAssigned }: { payment: PaymentRow; onClose: () => void; onAssigned: () => void }) {
    const [search, setSearch] = useState('');
    const [selected, setSelected] = useState<any | null>(null);
    const [planId, setPlanId] = useState<string>('');

    const { data, isLoading } = useQuery({
        queryKey: ['assign-payment-search', search],
        queryFn: async () => {
            const res = await adminAPI.getSubscribers({ search: search || undefined, page_size: 8 });
            return res.data.results || [];
        },
    });

    const { data: plans } = useQuery({
        queryKey: ['assign-payment-plans'],
        queryFn: async () => {
            const res = await billingAPI.getPlans();
            return ((res.data.results || res.data) as any[]).filter((p) => p.is_active !== false && p.service_type !== 'static');
        },
    });

    // Suggest the plan this amount pays for, for the chosen subscriber's service type.
    useEffect(() => {
        if (!selected || !plans) return;
        const exact = plans.filter((p) => Number(p.price) === Number(payment.amount));
        const match = exact.find((p) => p.service_type === selected.service_type) || exact[0];
        setPlanId(match ? String(match.id) : '');
    }, [selected, plans, payment.amount]);

    const assignMutation = useMutation({
        mutationFn: () => adminAPI.assignC2BPayment(payment.c2b_payment_id!, selected.id, planId ? Number(planId) : undefined),
        onSuccess: (res) => {
            toast.success(res.data.message || 'Payment assigned');
            onAssigned();
        },
        onError: (err: any) => toast.error(err.response?.data?.error || 'Failed to assign payment'),
    });

    const where = !payment.matched
        ? `Not linked to anyone yet${payment.payer_name ? ` (paid by ${payment.payer_name})` : ''}.`
        : payment.needs_assignment
            ? `Hotspot payment from the phone of ${payment.customer}. Nothing has been credited yet.`
        : payment.used_for === 'Account balance'
            ? `Currently in ${payment.customer}'s balance. Assigning to someone else moves it.`
            : `Matched to ${payment.customer}; ${payment.used_for || 'not applied yet'}.`;

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" role="dialog" aria-modal="true">
            <div className="bg-card rounded-xl shadow-xl w-full max-w-md max-h-[85vh] flex flex-col">
                <div className="flex justify-between items-start p-5 border-b">
                    <div>
                        <h3 className="text-lg font-bold">Assign payment</h3>
                        <p className="text-sm text-muted-foreground">
                            {payment.transaction_id} &middot; KES {Number(payment.amount).toLocaleString()}
                        </p>
                        <p className="text-xs text-muted-foreground mt-1">{where}</p>
                    </div>
                    <button onClick={onClose} aria-label="Close" className="p-1 text-muted-foreground hover:text-foreground">
                        <X className="h-5 w-5" />
                    </button>
                </div>

                <div className="p-5 space-y-4 overflow-y-auto flex-1">
                    <div className="relative">
                        <input
                            type="text"
                            autoFocus
                            placeholder="Search by name, username, phone..."
                            className="pl-10 pr-4 py-2 border rounded-lg w-full text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                        />
                        <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                    </div>

                    {isLoading ? (
                        <div className="text-center py-6 text-muted-foreground text-sm">Searching...</div>
                    ) : (data || []).length === 0 ? (
                        <div className="text-center py-6 text-muted-foreground text-sm">No subscribers found.</div>
                    ) : (
                        <ul className="divide-y divide-border border rounded-lg overflow-hidden" role="listbox" aria-label="Subscribers">
                            {data.map((c: any) => (
                                <li key={c.id}>
                                    <button
                                        role="option"
                                        aria-selected={selected?.id === c.id}
                                        onClick={() => setSelected(c)}
                                        className={`w-full text-left px-4 py-2.5 flex items-center justify-between ${selected?.id === c.id ? 'bg-accent' : 'hover:bg-secondary'}`}
                                    >
                                        <span className="min-w-0">
                                            <span className="block font-medium text-foreground truncate">{c.full_name || c.username}</span>
                                            <span className="block text-muted-foreground text-xs truncate">
                                                {c.username} &middot; {c.phone_number || 'no phone'} &middot; {String(c.service_type).toUpperCase()}
                                            </span>
                                        </span>
                                        {selected?.id === c.id && <UserPlus className="h-4 w-4 text-primary shrink-0" />}
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}

                    {selected && (
                        <div>
                            <label className="block text-sm font-medium text-foreground/80 mb-1">Use the money for</label>
                            <select className="w-full border rounded-lg px-3 py-2 text-sm" value={planId} onChange={(e) => setPlanId(e.target.value)}>
                                <option value="">Keep as account balance</option>
                                {plans?.map((p) => (
                                    <option key={p.id} value={p.id}>
                                        Activate {p.name} (KES {Number(p.price).toLocaleString()}){Number(p.price) === Number(payment.amount) ? ' · matches amount' : ''}
                                    </option>
                                ))}
                            </select>
                            <p className="text-xs text-muted-foreground mt-1">
                                A plan is paid from this payment plus any balance the subscriber already has.
                            </p>
                        </div>
                    )}
                </div>

                <div className="flex justify-end gap-2 border-t p-4">
                    <button onClick={onClose} className="px-4 py-2 border rounded-lg text-sm font-medium">Cancel</button>
                    <button
                        disabled={!selected || assignMutation.isPending}
                        onClick={() => assignMutation.mutate()}
                        className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50"
                    >
                        {assignMutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                        {selected ? `Assign to ${selected.username}` : 'Choose a subscriber'}
                    </button>
                </div>
            </div>
        </div>
    );
}
