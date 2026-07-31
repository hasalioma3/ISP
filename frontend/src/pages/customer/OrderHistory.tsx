import { useQuery } from '@tanstack/react-query';
import { billingAPI } from '../../services/api';
import { format } from 'date-fns';
import { Receipt, Loader2 } from 'lucide-react';

export default function OrderHistory() {
    const { data: transactions, isLoading } = useQuery({
        queryKey: ['order-history'],
        queryFn: async () => {
            const res = await billingAPI.getTransactions();
            return res.data.results || res.data;
        },
    });

    return (
        <div>
            <h1 className="text-2xl font-bold text-gray-900 mb-6 flex items-center gap-2">
                <Receipt className="h-6 w-6 text-gray-500" /> Order History
            </h1>

            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Amount</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Method</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Reference</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {isLoading ? (
                                <tr><td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                                    <Loader2 className="h-5 w-5 animate-spin inline mr-2" /> Loading...
                                </td></tr>
                            ) : transactions?.length === 0 ? (
                                <tr><td colSpan={5} className="px-6 py-8 text-center text-gray-500">No orders yet.</td></tr>
                            ) : transactions?.map((t: any) => (
                                <tr key={t.id} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 text-sm text-gray-500 whitespace-nowrap">{format(new Date(t.created_at), 'MMM d, yyyy HH:mm')}</td>
                                    <td className="px-6 py-4 text-sm font-medium text-gray-900">KES {Number(t.amount).toLocaleString()}</td>
                                    <td className="px-6 py-4 text-sm text-gray-500 uppercase">{t.payment_method}</td>
                                    <td className="px-6 py-4 text-sm text-gray-500 font-mono">{t.mpesa_receipt_number || t.transaction_id}</td>
                                    <td className="px-6 py-4">
                                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${t.status === 'completed' ? 'bg-green-100 text-green-800' :
                                            t.status === 'failed' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800'
                                            }`}>
                                            {t.status}
                                        </span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
