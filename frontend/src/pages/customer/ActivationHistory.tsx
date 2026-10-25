import { useQuery } from '@tanstack/react-query';
import { billingAPI } from '../../services/api';
import { format } from 'date-fns';
import { History, Loader2 } from 'lucide-react';

export default function ActivationHistory() {
    const { data: subscriptions, isLoading } = useQuery({
        queryKey: ['activation-history'],
        queryFn: async () => {
            const res = await billingAPI.getSubscriptions();
            return res.data.results || res.data;
        },
    });

    return (
        <div>
            <h1 className="text-2xl font-bold text-foreground mb-6 flex items-center gap-2">
                <History className="h-6 w-6 text-muted-foreground" /> Activation History
            </h1>

            <div className="bg-card rounded-2xl shadow-sm border border-border overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-border">
                        <thead className="bg-secondary">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Plan</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Activated On</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Expires On</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Status</th>
                            </tr>
                        </thead>
                        <tbody className="bg-card divide-y divide-border">
                            {isLoading ? (
                                <tr><td colSpan={4} className="px-6 py-8 text-center text-muted-foreground">
                                    <Loader2 className="h-5 w-5 animate-spin inline mr-2" /> Loading...
                                </td></tr>
                            ) : subscriptions?.length === 0 ? (
                                <tr><td colSpan={4} className="px-6 py-8 text-center text-muted-foreground">No activations yet.</td></tr>
                            ) : subscriptions?.map((s: any) => (
                                <tr key={s.id} className="hover:bg-secondary">
                                    <td className="px-6 py-4">
                                        <p className="text-sm font-medium text-foreground">{s.plan?.name}</p>
                                        <p className="text-xs text-muted-foreground">{s.plan?.download_speed}/{s.plan?.upload_speed} Mbps</p>
                                    </td>
                                    <td className="px-6 py-4 text-sm text-muted-foreground whitespace-nowrap">{format(new Date(s.created_at), 'MMM d, yyyy HH:mm')}</td>
                                    <td className="px-6 py-4 text-sm text-muted-foreground whitespace-nowrap">{format(new Date(s.expiry_date), 'MMM d, yyyy HH:mm')}</td>
                                    <td className="px-6 py-4">
                                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${s.status === 'active' ? 'bg-green-100 text-green-800' :
                                            s.status === 'expired' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-foreground'
                                            }`}>
                                            {s.status}
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
