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
            <h1 className="text-2xl font-bold text-foreground mb-6 flex items-center gap-2">
                <Receipt className="h-6 w-6 text-muted-foreground" /> Order History
            </h1>

            <div className="bg-card rounded-2xl shadow-sm border border-border overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-border">
                        <thead className="bg-secondary">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Date</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Amount</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Method</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Reference</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Status</th>
                            </tr>
                        </thead>
                        <tbody className="bg-card divide-y divide-border">
                            {isLoading ? (
                                <tr><td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                                    <Loader2 className="h-5 w-5 animate-spin inline mr-2" /> Loading...
                                </td></tr>
                            ) : transactions?.length === 0 ? (
                                <tr><td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">No orders yet.</td></tr>
                            ) : transactions?.map((t: any) => (
                                <tr key={t.id} className="hover:bg-secondary">
                                    <td className="px-6 py-4 text-sm text-muted-foreground whitespace-nowrap">{format(new Date(t.created_at), 'MMM d, yyyy HH:mm')}</td>
                                    <td className="px-6 py-4 text-sm font-medium text-foreground">KES {Number(t.amount).toLocaleString()}</td>
                                    <td className="px-6 py-4 text-sm text-muted-foreground uppercase">{t.payment_method}</td>
                                    <td className="px-6 py-4 text-sm text-muted-foreground font-mono">{t.mpesa_receipt_number || t.transaction_id}</td>
                                    <td className="px-6 py-4">
                                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${t.status === 'completed' ? 'bg-green-100 text-green-800' :
                                            t.status === 'failed' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-foreground'
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
