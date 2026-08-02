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
            <h1 className="text-2xl font-bold text-gray-900 mb-6 flex items-center gap-2">
                <Activity className="h-6 w-6 text-gray-500" /> Data Usage
            </h1>

            {isLoading ? (
                <div className="text-center py-12 text-gray-500">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto"></div>
                    <p className="mt-4">Loading usage data...</p>
                </div>
            ) : usageRecords && usageRecords.length > 0 ? (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Session Start
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Duration
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Data Used
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    IP Address
                                </th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {usageRecords.map((record: any) => (
                                <tr key={record.id}>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                        {new Date(record.start_time).toLocaleString()}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                        {Math.floor(record.session_time_seconds / 3600)}h {Math.floor((record.session_time_seconds % 3600) / 60)}m
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                        {record.total_gb} GB
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                        {record.framed_ip_address || 'N/A'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            ) : (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-12 text-center">
                    <Activity className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                    <h3 className="text-xl font-bold text-gray-900 mb-2">No Usage Data</h3>
                    <p className="text-gray-600">Your usage statistics will appear here once you start using the service.</p>
                </div>
            )}
        </div>
    );
}
