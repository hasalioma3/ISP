import { useQuery } from '@tanstack/react-query';
import { billingAPI } from '../../services/api';
import { Activity } from 'lucide-react';
import { Panel, formatDateEAT } from '../../components/savanna';

export default function Usage() {
    const { data: usageRecords, isLoading } = useQuery({
        queryKey: ['usage'],
        queryFn: async () => {
            const response = await billingAPI.getUsage();
            return response.data.results || response.data;
        },
    });

    const { data: summary } = useQuery({
        queryKey: ['usage-summary'],
        queryFn: async () => (await billingAPI.getUsageSummary()).data,
    });
    const cards = [
        {
            title: summary?.plan_totals ? `Current plan · ${summary.plan_totals.plan_name}` : 'Current plan',
            note: summary?.plan_totals
                ? `Since ${formatDateEAT(summary.plan_totals.start_date)}`
                  + (summary.plan_totals.data_limit_gb ? ` · cap ${summary.plan_totals.data_limit_gb} GB` : '')
                : 'No active plan',
            t: summary?.plan_totals,
        },
        { title: 'All time', note: 'Everything recorded on your account', t: summary?.totals },
    ];

    return (
        <div>
            <h1 className="text-2xl font-bold text-foreground mb-6 flex items-center gap-2">
                <Activity className="h-6 w-6 text-muted-foreground" /> Data Usage
            </h1>
            <div className="mb-6 grid grid-cols-1 gap-[18px] sm:grid-cols-2">
                {cards.map(({ title, note, t }) => (
                    <Panel key={title}>
                        <p className="text-[15px] font-bold text-foreground">{title}</p>
                        <p className="text-[12.5px] text-muted-foreground">{note}</p>
                        <p className="num mt-4 text-[32px] font-extrabold leading-none text-foreground">
                            {t ? t.total_gb : '—'} {t && <span className="text-[15px] font-medium text-muted-foreground">GB</span>}
                        </p>
                        {t && <p className="num mt-2 text-[13px] text-muted-foreground">↑ {t.upload_gb} GB upload · ↓ {t.download_gb} GB download</p>}
                    </Panel>
                ))}
            </div>

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
