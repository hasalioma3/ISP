import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { analyticsAPI, adminAPI } from '../../services/api';
import { Loader2, ShieldAlert, ChevronLeft, ChevronRight, Smartphone, Store, UserPlus, X, Search } from 'lucide-react';
import { format } from 'date-fns';
import toast from 'react-hot-toast';
import { useAuthStore } from '../../store/authStore';

const STATUS_BADGE: Record<string, string> = {
    utilized: 'bg-green-100 text-green-800',
    open: 'bg-amber-100 text-amber-800',
};

const METHOD_BADGE: Record<string, string> = {
    stk: 'bg-primary/10 text-primary',
    c2b: 'bg-cyan-100 text-cyan-800',
};

interface PaymentRow {
    c2b_payment_id: number | null;
    transaction_id: string;
    customer: string;
    matched: boolean;
    amount: number;
    method: 'stk' | 'c2b';
    status: 'utilized' | 'open';
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

    const { data, isLoading, isError, error } = useQuery({
        queryKey: ['admin-recent-payments', page],
        queryFn: async () => {
            const res = await analyticsAPI.getRecentPayments(page, pageSize);
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
            <h1 className="text-2xl font-bold mb-6">Payments</h1>

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
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Status</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Date &amp; Time</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="bg-card divide-y divide-border">
                            {isLoading ? (
                                <tr>
                                    <td colSpan={7} className="px-6 py-8 text-center text-muted-foreground">
                                        <div className="flex justify-center items-center">
                                            <Loader2 className="h-6 w-6 animate-spin mr-2" />
                                            Loading payments...
                                        </div>
                                    </td>
                                </tr>
                            ) : isError ? (
                                <tr>
                                    <td colSpan={7} className="px-6 py-8 text-center text-red-500">
                                        Error loading payments: {(error as Error).message}
                                    </td>
                                </tr>
                            ) : payments.length === 0 ? (
                                <tr>
                                    <td colSpan={7} className="px-6 py-8 text-center text-muted-foreground">
                                        No payments found.
                                    </td>
                                </tr>
                            ) : (
                                payments.map((p) => (
                                    <tr key={`${p.method}-${p.transaction_id}`} className="hover:bg-secondary transition">
                                        <td className="px-4 py-4 whitespace-nowrap text-sm font-mono text-foreground">{p.transaction_id}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-foreground/80 font-mono">{p.customer}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-foreground">KES {Number(p.amount).toLocaleString()}</td>
                                        <td className="px-4 py-4 whitespace-nowrap">
                                            <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium uppercase ${METHOD_BADGE[p.method]}`}>
                                                {p.method === 'stk' ? <Smartphone className="h-3 w-3" /> : <Store className="h-3 w-3" />}
                                                {p.method}
                                            </span>
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap">
                                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_BADGE[p.status]}`}>
                                                {p.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-muted-foreground">
                                            {p.paid_at ? format(new Date(p.paid_at), 'MMM d, yyyy HH:mm') : '-'}
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap">
                                            {!p.matched && p.c2b_payment_id && (
                                                <button
                                                    onClick={() => setAssignTarget(p)}
                                                    className="flex items-center px-2 py-1 bg-primary text-white rounded text-xs hover:bg-primary/90"
                                                    title="Assign this payment to a customer"
                                                >
                                                    <UserPlus className="h-3 w-3 mr-1" /> Assign
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

    const { data, isLoading } = useQuery({
        queryKey: ['assign-payment-search', search],
        queryFn: async () => {
            const res = await adminAPI.getSubscribers({ search: search || undefined, page_size: 8 });
            return res.data.results || [];
        },
    });

    const assignMutation = useMutation({
        mutationFn: (customerId: number) => adminAPI.assignC2BPayment(payment.c2b_payment_id!, customerId),
        onSuccess: (res) => {
            toast.success(res.data.message || 'Payment assigned');
            onAssigned();
        },
        onError: (err: any) => toast.error(err.response?.data?.error || 'Failed to assign payment'),
    });

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-card rounded-xl shadow-xl w-full max-w-md max-h-[80vh] flex flex-col">
                <div className="flex justify-between items-center p-5 border-b">
                    <div>
                        <h3 className="text-lg font-bold">Assign Payment</h3>
                        <p className="text-sm text-muted-foreground">
                            {payment.transaction_id} &middot; KES {Number(payment.amount).toLocaleString()} &middot; unmatched payer {payment.customer.slice(0, 8)}&hellip;
                        </p>
                    </div>
                    <button onClick={onClose} className="p-1 text-muted-foreground hover:text-muted-foreground">
                        <X className="h-5 w-5" />
                    </button>
                </div>

                <div className="p-5 space-y-4 overflow-y-auto flex-1">
                    <div className="relative">
                        <input
                            type="text"
                            autoFocus
                            placeholder="Search by name, username, email, phone..."
                            className="pl-10 pr-4 py-2 border rounded-lg w-full text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                        />
                        <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                    </div>

                    {isLoading ? (
                        <div className="text-center py-6 text-muted-foreground text-sm">Searching...</div>
                    ) : (data || []).length === 0 ? (
                        <div className="text-center py-6 text-muted-foreground text-sm">No customers found.</div>
                    ) : (
                        <ul className="divide-y divide-border border rounded-lg overflow-hidden">
                            {data.map((c: any) => (
                                <li key={c.id}>
                                    <button
                                        disabled={assignMutation.isPending}
                                        onClick={() => assignMutation.mutate(c.id)}
                                        className="w-full text-left px-4 py-2.5 hover:bg-secondary disabled:opacity-50 flex items-center justify-between"
                                    >
                                        <span>
                                            <span className="font-medium text-foreground">{c.username}</span>
                                            <span className="text-muted-foreground text-sm ml-2">{c.full_name} &middot; {c.phone_number}</span>
                                        </span>
                                        <UserPlus className="h-4 w-4 text-primary" />
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                    <p className="text-xs text-muted-foreground">
                        The full payment amount will be credited to whichever customer you pick.
                    </p>
                </div>
            </div>
        </div>
    );
}
