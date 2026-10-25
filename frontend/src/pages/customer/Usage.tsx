import { useQuery } from '@tanstack/react-query';
import { billingAPI } from '../../services/api';
import { Activity } from 'lucide-react';

export default function Usage() {
    const { data: usageRecords, isLoading } = useQuery({
        queryKey: ['usage'],
        queryFn: async () => {
            const response = await billingAPI.getUsage();
            return response.data.results || response.data;
        },
    });

    return (
        <div>
            <h1 className="text-2xl font-bold text-foreground mb-6 flex items-center gap-2">
                <Activity className="h-6 w-6 text-muted-foreground" /> Data Usage
            </h1>

            {isLoading ? (
                <div className="text-center py-12 text-muted-foreground">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary mx-auto"></div>
                    <p className="mt-4">Loading usage data...</p>
                </div>
            ) : usageRecords && usageRecords.length > 0 ? (
                <div className="bg-card rounded-2xl shadow-sm border border-border overflow-x-auto">
                    <table className="min-w-full divide-y divide-border">
                        <thead className="bg-secondary">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                                    Session Start
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                                    Duration
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                                    Data Used
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                                    IP Address
                                </th>
                            </tr>
                        </thead>
                        <tbody className="bg-card divide-y divide-border">
                            {usageRecords.map((record: any) => (
                                <tr key={record.id}>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
                                        {new Date(record.start_time).toLocaleString()}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
                                        {Math.floor(record.session_time_seconds / 3600)}h {Math.floor((record.session_time_seconds % 3600) / 60)}m
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
                                        {record.total_gb} GB
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground">
                                        {record.framed_ip_address || 'N/A'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            ) : (
                <div className="bg-card rounded-2xl shadow-sm border border-border p-12 text-center">
                    <Activity className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
                    <h3 className="text-xl font-bold text-foreground mb-2">No Usage Data</h3>
                    <p className="text-muted-foreground">Your usage statistics will appear here once you start using the service.</p>
                </div>
            )}
        </div>
    );
}
