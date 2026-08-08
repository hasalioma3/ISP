import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { analyticsAPI } from '../../services/api';
import { Loader2, ShieldAlert, ChevronLeft, ChevronRight, Smartphone, Store } from 'lucide-react';
import { format } from 'date-fns';
import { useAuthStore } from '../../store/authStore';

const STATUS_BADGE: Record<string, string> = {
    utilized: 'bg-green-100 text-green-800',
    open: 'bg-amber-100 text-amber-800',
};

const METHOD_BADGE: Record<string, string> = {
    stk: 'bg-blue-100 text-blue-800',
    c2b: 'bg-purple-100 text-purple-800',
};

interface PaymentRow {
    transaction_id: string;
    customer: string;
    amount: number;
    method: 'stk' | 'c2b';
    status: 'utilized' | 'open';
    paid_at: string;
}

export default function Payments() {
    const user = useAuthStore((state) => state.user);
    const [page, setPage] = useState(1);
    const pageSize = 20;

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
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-8 text-center">
                <ShieldAlert className="h-10 w-10 text-red-400 mx-auto mb-3" />
                <h2 className="text-lg font-semibold text-gray-800">Admins only</h2>
                <p className="text-sm text-gray-500 mt-1">You don't have permission to view payments.</p>
            </div>
        );
    }

    const payments: PaymentRow[] = data?.results || [];
    const totalCount = data?.count ?? payments.length;
    const totalPages = data?.total_pages ?? Math.max(1, Math.ceil(totalCount / pageSize));

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6">Payments</h1>

            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                <div className="bg-blue-600 px-4 sm:px-6 py-4">
                    <h2 className="text-white font-bold text-lg">Recent Payments</h2>
                    <p className="text-blue-100 text-sm mt-0.5">STK Push and C2B till payments, most recent first</p>
                </div>

                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Transaction ID</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Customer</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Amount</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Method</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date &amp; Time</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {isLoading ? (
                                <tr>
                                    <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                                        <div className="flex justify-center items-center">
                                            <Loader2 className="h-6 w-6 animate-spin mr-2" />
                                            Loading payments...
                                        </div>
                                    </td>
                                </tr>
                            ) : isError ? (
                                <tr>
                                    <td colSpan={6} className="px-6 py-8 text-center text-red-500">
                                        Error loading payments: {(error as Error).message}
                                    </td>
                                </tr>
                            ) : payments.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                                        No payments found.
                                    </td>
                                </tr>
                            ) : (
                                payments.map((p) => (
                                    <tr key={`${p.method}-${p.transaction_id}`} className="hover:bg-gray-50 transition">
                                        <td className="px-4 py-4 whitespace-nowrap text-sm font-mono text-gray-900">{p.transaction_id}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-700 font-mono">{p.customer}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-900">KES {Number(p.amount).toLocaleString()}</td>
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
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">
                                            {p.paid_at ? format(new Date(p.paid_at), 'MMM d, yyyy HH:mm') : '-'}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 text-sm text-gray-600">
                    <span>
                        {totalCount === 0 ? '0 results' : `Page ${page} of ${totalPages} · ${totalCount} total`}
                    </span>
                    <div className="flex gap-2">
                        <button
                            disabled={page <= 1}
                            onClick={() => setPage((p) => Math.max(1, p - 1))}
                            className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
                        >
                            <ChevronLeft className="h-4 w-4" /> Prev
                        </button>
                        <button
                            disabled={page >= totalPages}
                            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                            className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
                        >
                            Next <ChevronRight className="h-4 w-4" />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
