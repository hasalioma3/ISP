import { useQuery } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { billingAPI, invoiceAPI } from '../../services/api';
import { format } from 'date-fns';
import { Receipt, Loader2, FileText, Download } from 'lucide-react';
import { downloadBlob } from '../../utils/downloadBlob';
import { errText } from '../../utils/errText';

export default function OrderHistory() {
    const { data: transactions, isLoading } = useQuery({
        queryKey: ['order-history'],
        queryFn: async () => {
            const res = await billingAPI.getTransactions();
            return res.data.results || res.data;
        },
    });

    const { data: invoices } = useQuery({
        queryKey: ['my-invoices'],
        queryFn: async () => (await invoiceAPI.mine()).data as any[],
    });
    const download = async (inv: any) => {
        try { downloadBlob((await invoiceAPI.myPdf(inv.id)).data, `${inv.number}.pdf`); }
        catch (e) { toast.error(errText(e, 'Could not download the invoice')); }
    };

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

            {invoices && invoices.length > 0 && (
                <div className="mt-8">
                    <h2 className="text-lg font-bold text-foreground mb-3 flex items-center gap-2">
                        <FileText className="h-5 w-5 text-muted-foreground" /> Invoices
                    </h2>
                    <div className="bg-card rounded-2xl shadow-sm border border-border divide-y divide-border">
                        {invoices.map((inv) => (
                            <div key={inv.id} className="flex items-center justify-between gap-3 px-6 py-3 text-sm">
                                <div className="min-w-0">
                                    <p className="font-medium font-mono">{inv.number}
                                        {inv.etims_signed && <span className="ml-2 rounded-full bg-green-100 px-2 py-0.5 font-sans text-xs text-green-800">KRA eTIMS</span>}
                                    </p>
                                    <p className="truncate text-xs text-muted-foreground">{format(new Date(inv.issue_date), 'MMM d, yyyy')} · {inv.description}</p>
                                </div>
                                <span className="font-semibold whitespace-nowrap">KES {Number(inv.total).toLocaleString()}</span>
                                <button onClick={() => download(inv)} className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium hover:bg-secondary">
                                    <Download className="h-3.5 w-3.5" /> PDF
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
