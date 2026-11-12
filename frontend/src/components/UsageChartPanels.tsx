import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export default function UsageChartPanels({ chart, loading, title }: { chart: any; loading: boolean; title?: string }) {
    if (loading) {
        return <div className="text-center py-8 text-muted-foreground">Loading usage...</div>;
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
                <div className="rounded-2xl border border-border-soft bg-surface2 overflow-hidden">
                    <div className="px-4 pt-3.5 text-[13px] font-bold text-foreground">Today's Data Usage</div>
                    <div className="p-4">
                        <div className="h-40">
                            {hasToday ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie data={donutData} dataKey="value" innerRadius={44} outerRadius={66} paddingAngle={2} stroke="var(--sv-surface)">
                                            <Cell fill="#F2772E" />
                                            <Cell fill="#0B4D33" />
                                        </Pie>
                                        <Tooltip formatter={(v: number) => `${v} GB`} />
                                    </PieChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="h-full flex items-center justify-center text-xs text-muted-foreground">No usage today</div>
                            )}
                        </div>
                        <div className="text-xs text-muted-foreground mt-2 space-y-1">
                            <p>Upload: {chart.today.upload_gb} GB</p>
                            <p>Download: {chart.today.download_gb} GB</p>
                            <p className="font-medium text-foreground">Total: {chart.today.total_gb} GB</p>
                        </div>
                    </div>
                </div>

                <div className="rounded-2xl border border-border-soft bg-surface2 overflow-hidden">
                    <div className="px-4 pt-3.5 text-[13px] font-bold text-foreground">Weekly Data Usage</div>
                    <div className="p-4 h-56">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={chart.weekly}>
                                <XAxis dataKey="day" tick={{ fontSize: 10, fill: 'var(--sv-faint)' }} tickLine={false} axisLine={false} tickFormatter={(d: string) => d.slice(0, 3)} />
                                <YAxis tick={{ fontSize: 10, fill: 'var(--sv-faint)' }} tickLine={false} axisLine={false} />
                                <Tooltip formatter={(v: number) => `${v} GB`} />
                                <Bar dataKey="upload_gb" stackId="a" fill="#F2772E" name="Upload" />
                                <Bar dataKey="download_gb" stackId="a" fill="#0B4D33" name="Download" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="rounded-2xl border border-border-soft bg-surface2 overflow-hidden">
                    <div className="px-4 pt-3.5 text-[13px] font-bold text-foreground">Monthly Data Usage</div>
                    <div className="p-4 h-56">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={chart.monthly}>
                                <XAxis dataKey="month" tick={{ fontSize: 10, fill: 'var(--sv-faint)' }} tickLine={false} axisLine={false} />
                                <YAxis tick={{ fontSize: 10, fill: 'var(--sv-faint)' }} tickLine={false} axisLine={false} />
                                <Tooltip formatter={(v: number) => `${v} GB`} />
                                <Bar dataKey="upload_gb" stackId="a" fill="#F2772E" name="Upload" />
                                <Bar dataKey="download_gb" stackId="a" fill="#0B4D33" name="Download" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
        </div>
    );
}
