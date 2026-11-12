import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { analyticsAPI } from '../../services/api';
import { BarTrend } from '../../components/savanna/charts';
import { Panel, PanelHeader, Skeleton, formatCompact, formatDateEAT, formatKES } from '../../components/savanna';
import DayBreakdown from '../../components/DayBreakdown';
import { Download, Calendar, Search } from 'lucide-react';
import { addDays, format, subDays } from 'date-fns';
import { downloadBlob } from '../../utils/downloadBlob';

export default function Reports() {
    const [startDate, setStartDate] = useState(format(subDays(new Date(), 30), 'yyyy-MM-dd'));
    const [endDate, setEndDate] = useState(format(new Date(), 'yyyy-MM-dd'));
    const [voucherSearchInput, setVoucherSearchInput] = useState('');
    const [voucherSearch, setVoucherSearch] = useState('');
    const [voucherPage, setVoucherPage] = useState(1);

    const { data: incomeData, isLoading, isError, error } = useQuery({
        queryKey: ['admin-income-report', startDate, endDate],
        queryFn: async () => {
            const res = await analyticsAPI.getIncomeReport({ start_date: startDate, end_date: endDate });
            return res.data;
        }
    });

    const [revenueDay, setRevenueDay] = useState<string | null>(null);
    const [usageDay, setUsageDay] = useState<string | null>(null);

    // The income report only has days with payments; fill the gaps with 0
    // so the bars line up day by day.
    const revenueDays = (() => {
        const byDay = new Map<string, number>((incomeData || []).map((r: any) => [String(r.date), Number(r.total) || 0]));
        const out: { date: string; total: number }[] = [];
        for (let d = new Date(`${startDate}T12:00:00`); format(d, 'yyyy-MM-dd') <= endDate; d = addDays(d, 1)) {
            const key = format(d, 'yyyy-MM-dd');
            out.push({ date: key, total: byDay.get(key) ?? 0 });
            if (out.length > 400) break;
        }
        return out;
    })();
    const revenueTotal = revenueDays.reduce((sum, d) => sum + d.total, 0);

    const { data: usageDays, isLoading: usageLoading } = useQuery({
        queryKey: ['admin-daily-usage', startDate, endDate],
        queryFn: async () => (await analyticsAPI.getDailyUsage({ start_date: startDate, end_date: endDate })).data as { date: string; total_gb: number }[],
    });
    const usageTotal = (usageDays || []).reduce((sum, d) => sum + d.total_gb, 0);
    const shortDay = (v: string) => formatDateEAT(`${v}T12:00:00+03:00`, { day: '2-digit', month: 'short' });

    const { data: voucherReport, isLoading: vouchersLoading, isError: vouchersError } = useQuery({
        queryKey: ['admin-voucher-usage', startDate, endDate, voucherSearch, voucherPage],
        queryFn: async () => {
            const res = await analyticsAPI.getVoucherUsageReport({
                start_date: startDate,
                end_date: endDate,
                search: voucherSearch || undefined,
                page: voucherPage,
                page_size: 25,
            });
            return res.data;
        },
    });

    const handleVoucherSearch = (e: React.FormEvent) => {
        e.preventDefault();
        setVoucherPage(1);
        setVoucherSearch(voucherSearchInput.trim());
    };

    const handleVoucherExport = async () => {
        const res = await analyticsAPI.downloadVoucherUsageReport({
            start_date: startDate,
            end_date: endDate,
            search: voucherSearch || undefined,
        });
        downloadBlob(res.data, `voucher_usage_${startDate}_${endDate}.csv`);
    };

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
                <h1 className="text-2xl font-bold">Reports</h1>
                <div className="flex flex-wrap gap-2">
                    <div className="flex items-center gap-2 bg-card px-3 py-2 rounded-lg border shadow-sm flex-wrap">
                        <Calendar className="h-4 w-4 text-muted-foreground" />
                        <input
                            type="date"
                            value={startDate}
                            onChange={(e) => { setStartDate(e.target.value); setVoucherPage(1); setRevenueDay(null); setUsageDay(null); }}
                            className="text-sm border-none focus:ring-0 p-0 text-muted-foreground"
                        />
                        <span className="text-muted-foreground">-</span>
                        <input
                            type="date"
                            value={endDate}
                            onChange={(e) => { setEndDate(e.target.value); setVoucherPage(1); setRevenueDay(null); setUsageDay(null); }}
                            className="text-sm border-none focus:ring-0 p-0 text-muted-foreground"
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

            {/* Click a day's bar to see what made it up. */}
            <div className="mb-6 grid grid-cols-1 gap-[18px] 2xl:grid-cols-2">
                <Panel>
                    <PanelHeader
                        title="Revenue overview"
                        subtitle={`Completed payments per day · ${formatKES(revenueTotal)} in range · click a bar for the breakdown`}
                    />
                    {isLoading ? <Skeleton className="h-[300px] w-full" /> : isError ? (
                        <p className="py-16 text-center text-bad">Error loading report: {(error as Error).message}</p>
                    ) : (
                        <BarTrend
                            data={revenueDays}
                            xKey="date"
                            yKey="total"
                            name="Revenue"
                            height={300}
                            showYAxis
                            formatX={shortDay}
                            formatY={(v) => formatCompact(v)}
                            formatTooltip={(v) => formatKES(v)}
                            selected={revenueDay}
                            onBarClick={(row) => setRevenueDay(row.date === revenueDay ? null : row.date)}
                        />
                    )}
                    {revenueDay && <DayBreakdown kind="revenue" date={revenueDay} onClose={() => setRevenueDay(null)} />}
                </Panel>

                <Panel>
                    <PanelHeader
                        title="Data usage overview"
                        subtitle={`Whole network per day · ${usageTotal.toFixed(1)} GB in range · click a bar for the breakdown`}
                    />
                    {usageLoading ? <Skeleton className="h-[300px] w-full" /> : (
                        <BarTrend
                            data={usageDays || []}
                            xKey="date"
                            yKey="total_gb"
                            name="Usage"
                            height={300}
                            showYAxis
                            formatX={shortDay}
                            formatY={(v) => `${v}`}
                            formatTooltip={(v) => `${v} GB`}
                            selected={usageDay}
                            onBarClick={(row) => setUsageDay(row.date === usageDay ? null : row.date)}
                        />
                    )}
                    {usageDay && <DayBreakdown kind="usage" date={usageDay} onClose={() => setUsageDay(null)} />}
                </Panel>
            </div>

            <section className="bg-card rounded-xl shadow-sm border border-border">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-5 border-b border-border">
                    <div>
                        <h2 className="text-lg font-bold">Voucher Usage</h2>
                        <p className="text-sm text-muted-foreground">Redeemed vouchers in the selected date range</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <form onSubmit={handleVoucherSearch} className="flex">
                            <label className="sr-only" htmlFor="voucher-usage-search">Search vouchers</label>
                            <input
                                id="voucher-usage-search"
                                type="search"
                                value={voucherSearchInput}
                                onChange={(e) => setVoucherSearchInput(e.target.value)}
                                placeholder="Code, MAC, customer, plan"
                                className="w-56 max-w-full border border-input rounded-l-md px-3 py-2 text-sm"
                            />
                            <button type="submit" aria-label="Search voucher usage" className="px-3 border border-l-0 border-input rounded-r-md hover:bg-accent">
                                <Search className="h-4 w-4" />
                            </button>
                        </form>
                        <button
                            type="button"
                            onClick={handleVoucherExport}
                            className="flex items-center gap-2 px-3 py-2 border border-input rounded-md hover:bg-accent text-sm font-medium"
                        >
                            <Download className="h-4 w-4" />
                            Export vouchers
                        </button>
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                        <thead className="bg-muted/40 text-muted-foreground">
                            <tr>
                                <th className="px-5 py-3 font-medium">Voucher</th>
                                <th className="px-5 py-3 font-medium">MAC Address</th>
                                <th className="px-5 py-3 font-medium">Customer</th>
                                <th className="px-5 py-3 font-medium">Plan</th>
                                <th className="px-5 py-3 font-medium">Redeemed At</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                            {vouchersLoading ? (
                                <tr><td colSpan={5} className="px-5 py-8 text-center text-muted-foreground">Loading voucher usage...</td></tr>
                            ) : vouchersError ? (
                                <tr><td colSpan={5} className="px-5 py-8 text-center text-red-500">Could not load voucher usage.</td></tr>
                            ) : voucherReport?.results?.length ? voucherReport.results.map((row: any) => (
                                <tr key={row.id}>
                                    <td className="px-5 py-3 font-medium">{row.voucher_code}</td>
                                    <td className="px-5 py-3 font-mono">{row.mac_address || 'Not recorded'}</td>
                                    <td className="px-5 py-3">{row.customer_name || row.customer_username || '—'}</td>
                                    <td className="px-5 py-3">{row.plan_name || '—'}</td>
                                    <td className="px-5 py-3 whitespace-nowrap">{row.used_at ? new Date(row.used_at).toLocaleString() : '—'}</td>
                                </tr>
                            )) : (
                                <tr><td colSpan={5} className="px-5 py-8 text-center text-muted-foreground">No redeemed vouchers found for these filters.</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
                <div className="flex items-center justify-between gap-3 px-5 py-3 border-t border-border text-sm">
                    <span className="text-muted-foreground">{voucherReport?.count ?? 0} redemptions</span>
                    <div className="flex items-center gap-2">
                        <span className="text-muted-foreground">Page {voucherReport?.page ?? 1} of {voucherReport?.total_pages ?? 1}</span>
                        <button
                            type="button"
                            onClick={() => setVoucherPage((page) => Math.max(1, page - 1))}
                            disabled={voucherPage <= 1 || vouchersLoading}
                            className="px-3 py-1.5 border border-input rounded disabled:opacity-40"
                        >Previous</button>
                        <button
                            type="button"
                            onClick={() => setVoucherPage((page) => Math.min(voucherReport?.total_pages ?? 1, page + 1))}
                            disabled={voucherPage >= (voucherReport?.total_pages ?? 1) || vouchersLoading}
                            className="px-3 py-1.5 border border-input rounded disabled:opacity-40"
                        >Next</button>
                    </div>
                </div>
            </section>
        </div>
    );
}
