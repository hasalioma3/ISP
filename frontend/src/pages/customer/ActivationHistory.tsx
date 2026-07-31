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
            <h1 className="text-2xl font-bold text-gray-900 mb-6 flex items-center gap-2">
                <History className="h-6 w-6 text-gray-500" /> Activation History
            </h1>

            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Plan</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Activated On</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Expires On</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {isLoading ? (
                                <tr><td colSpan={4} className="px-6 py-8 text-center text-gray-500">
                                    <Loader2 className="h-5 w-5 animate-spin inline mr-2" /> Loading...
                                </td></tr>
                            ) : subscriptions?.length === 0 ? (
                                <tr><td colSpan={4} className="px-6 py-8 text-center text-gray-500">No activations yet.</td></tr>
                            ) : subscriptions?.map((s: any) => (
                                <tr key={s.id} className="hover:bg-gray-50">
                                    <td className="px-6 py-4">
                                        <p className="text-sm font-medium text-gray-900">{s.plan?.name}</p>
                                        <p className="text-xs text-gray-500">{s.plan?.download_speed}/{s.plan?.upload_speed} Mbps</p>
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-500 whitespace-nowrap">{format(new Date(s.created_at), 'MMM d, yyyy HH:mm')}</td>
                                    <td className="px-6 py-4 text-sm text-gray-500 whitespace-nowrap">{format(new Date(s.expiry_date), 'MMM d, yyyy HH:mm')}</td>
                                    <td className="px-6 py-4">
                                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${s.status === 'active' ? 'bg-green-100 text-green-800' :
                                            s.status === 'expired' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800'
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
