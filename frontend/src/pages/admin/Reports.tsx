import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { analyticsAPI } from '../../services/api';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend
} from 'recharts';
import { Download, Calendar } from 'lucide-react';
import { format, subDays } from 'date-fns';

export default function Reports() {
    const [startDate, setStartDate] = useState(format(subDays(new Date(), 30), 'yyyy-MM-dd'));
    const [endDate, setEndDate] = useState(format(new Date(), 'yyyy-MM-dd'));

    const { data: incomeData, isLoading, isError, error } = useQuery({
        queryKey: ['admin-income-report', startDate, endDate],
        queryFn: async () => {
            const res = await analyticsAPI.getIncomeReport({ start_date: startDate, end_date: endDate });
            return res.data;
        }
    });

    const handleDownloadCSV = () => {
        // Direct download link
        // We need auth token in params or headers? 
        // Direct link won't have headers.
        // We must fetch blob and download.
        // Or cleaner: use window.open if cookies. typically JWT is in localStorage so fetch is better.

        // Actually, let's use the API method but with responseType blob
        // For now, simpler: user clicks, we fetch blob, create objectURL.

        // Wait, analyticsAPI.getIncomeReport calls axios. 
        // Let's manually reconstruct the URL for simplicity or use a dedicated download function in API.
        // Let's do fetch manually here or improve API.

        const token = localStorage.getItem('access_token');
        const url = `${import.meta.env.VITE_API_URL || '/api'}/analytics/income/?start_date=${startDate}&end_date=${endDate}&export=csv`;

        fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        })
            .then(resp => resp.blob())
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = `income_report_${startDate}_${endDate}.csv`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
            });
    };

    return (
        <div>
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
                <h1 className="text-2xl font-bold">Financial Reports</h1>
                <div className="flex gap-2">
                    <div className="flex items-center gap-2 bg-white px-3 py-2 rounded-lg border shadow-sm">
                        <Calendar className="h-4 w-4 text-gray-400" />
                        <input
                            type="date"
                            value={startDate}
                            onChange={(e) => setStartDate(e.target.value)}
                            className="text-sm border-none focus:ring-0 p-0 text-gray-600"
                        />
                        <span className="text-gray-400">-</span>
                        <input
                            type="date"
                            value={endDate}
                            onChange={(e) => setEndDate(e.target.value)}
                            className="text-sm border-none focus:ring-0 p-0 text-gray-600"
                        />
                    </div>
                    <button
                        onClick={handleDownloadCSV}
                        className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition text-sm font-medium"
                    >
                        <Download className="h-4 w-4" />
                        Export CSV
                    </button>
                </div>
            </div>

            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 mb-6">
                <h3 className="text-lg font-bold mb-4">Revenue Overview</h3>
                <div className="h-96">
                    {isLoading ? (
                        <div className="h-full flex items-center justify-center text-gray-500">Loading chart...</div>
                    ) : isError ? (
                        <div className="h-full flex items-center justify-center text-red-500">Error loading report: {(error as Error).message}</div>
                    ) : (
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={incomeData || []}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                <XAxis
                                    dataKey="date"
                                    tickFormatter={(val) => format(new Date(val), 'MMM d')}
                                />
                                <YAxis />
                                <Tooltip
                                    formatter={(value) => [`KES ${Number(value).toLocaleString()}`, 'Revenue']}
                                    labelFormatter={(label) => format(new Date(label), 'PPP')}
                                />
                                <Legend />
                                <Bar dataKey="total" fill="#3b82f6" name="Revenue" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </div>
            </div>

            {/* Can add another section for Usage Stats if needed */}
        </div>
    );
}
