import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export default function UsageChartPanels({ chart, loading, title }: { chart: any; loading: boolean; title?: string }) {
    if (loading) {
        return <div className="text-center py-8 text-gray-500">Loading usage...</div>;
    }
    if (!chart) return null;

    const donutData = [
        { name: 'Upload', value: chart.today.upload_gb },
        { name: 'Download', value: chart.today.download_gb },
    ];
    const hasToday = chart.today.total_gb > 0;

    return (
        <div>
            {title && <h4 className="text-sm font-bold mb-3">{title}</h4>}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <div className="border rounded-lg overflow-hidden">
                    <div className="bg-blue-600 text-white text-sm font-bold px-4 py-2">Today's Data Usage</div>
                    <div className="p-4">
                        <div className="h-40">
                            {hasToday ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie data={donutData} dataKey="value" innerRadius={40} outerRadius={65} paddingAngle={2}>
                                            <Cell fill="#60a5fa" />
                                            <Cell fill="#2dd4bf" />
                                        </Pie>
                                        <Tooltip formatter={(v: number) => `${v} GB`} />
                                    </PieChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="h-full flex items-center justify-center text-xs text-gray-400">No usage today</div>
                            )}
                        </div>
                        <div className="text-xs text-gray-500 mt-2 space-y-1">
                            <p>Upload: {chart.today.upload_gb} GB</p>
                            <p>Download: {chart.today.download_gb} GB</p>
                            <p className="font-medium text-gray-900">Total: {chart.today.total_gb} GB</p>
                        </div>
                    </div>
                </div>

                <div className="border rounded-lg overflow-hidden">
                    <div className="bg-blue-600 text-white text-sm font-bold px-4 py-2">Weekly Data Usage</div>
                    <div className="p-4 h-56">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={chart.weekly}>
                                <XAxis dataKey="day" tick={{ fontSize: 10 }} tickFormatter={(d: string) => d.slice(0, 3)} />
                                <YAxis tick={{ fontSize: 10 }} />
                                <Tooltip formatter={(v: number) => `${v} GB`} />
                                <Bar dataKey="upload_gb" stackId="a" fill="#60a5fa" name="Upload" />
                                <Bar dataKey="download_gb" stackId="a" fill="#2dd4bf" name="Download" />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="border rounded-lg overflow-hidden">
                    <div className="bg-blue-600 text-white text-sm font-bold px-4 py-2">Monthly Data Usage</div>
                    <div className="p-4 h-56">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={chart.monthly}>
                                <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                                <YAxis tick={{ fontSize: 10 }} />
                                <Tooltip formatter={(v: number) => `${v} GB`} />
                                <Bar dataKey="upload_gb" stackId="a" fill="#60a5fa" name="Upload" />
                                <Bar dataKey="download_gb" stackId="a" fill="#2dd4bf" name="Download" />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
        </div>
    );
}
