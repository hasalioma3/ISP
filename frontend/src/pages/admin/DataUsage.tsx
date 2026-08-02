import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
    PieChart, Pie, Cell,
} from 'recharts';
import { analyticsAPI, adminAPI } from '../../services/api';
import {
    PieChart as PieIcon, Calendar, Search, Filter, RotateCcw, Download,
    ArrowUp, ArrowDown, Users as UsersIcon, ArrowUpDown, TrendingUp,
} from 'lucide-react';
import { format } from 'date-fns';

const PERIODS = [
    { key: 'daily', label: 'Daily' },
    { key: 'weekly', label: 'Weekly' },
    { key: 'monthly', label: 'Monthly' },
] as const;

const SORTS = [
    { key: 'highest', label: 'Highest Usage', icon: ArrowDown },
    { key: 'lowest', label: 'Lowest Usage', icon: ArrowUp },
    { key: 'downloaders', label: 'Top Downloaders', icon: ArrowDown },
    { key: 'uploaders', label: 'Top Uploaders', icon: ArrowUp },
    { key: 'username', label: 'Username', icon: ArrowUpDown },
] as const;

export default function DataUsage() {
    const [period, setPeriod] = useState<typeof PERIODS[number]['key']>('daily');
    const [search, setSearch] = useState('');
    const [searchInput, setSearchInput] = useState('');
    const [routerFilter, setRouterFilter] = useState('');
    const [typeFilter, setTypeFilter] = useState('');
    const [date, setDate] = useState(format(new Date(), 'yyyy-MM-dd'));
    const [limit, setLimit] = useState(50);
    const [sort, setSort] = useState<typeof SORTS[number]['key']>('highest');

    const { data: routers } = useQuery({
        queryKey: ['routers'],
        queryFn: async () => {
            const res = await adminAPI.getRouters();
            return res.data.results || res.data;
        }
    });

    const { data, isLoading } = useQuery({
        queryKey: ['data-usage', period, date, search, routerFilter, typeFilter, sort, limit],
        queryFn: async () => {
            const res = await analyticsAPI.getDataUsage({
                period, date, search: search || undefined, router: routerFilter || undefined,
                type: typeFilter || undefined, sort, limit,
            });
            return res.data;
        }
    });

    const handleFilter = (e: React.FormEvent) => {
        e.preventDefault();
        setSearch(searchInput);
    };

    const handleReset = () => {
        setSearchInput(''); setSearch(''); setRouterFilter(''); setTypeFilter('');
        setDate(format(new Date(), 'yyyy-MM-dd')); setSort('highest'); setLimit(50);
    };

    const handleExportCSV = () => {
        const token = localStorage.getItem('access_token');
        const params = new URLSearchParams({
            period, date, sort, limit: String(limit), export: 'csv',
            ...(search ? { search } : {}), ...(routerFilter ? { router: routerFilter } : {}),
            ...(typeFilter ? { type: typeFilter } : {}),
        });
        const url = `${import.meta.env.VITE_API_URL || '/api'}/analytics/data-usage/?${params}`;
        fetch(url, { headers: { Authorization: `Bearer ${token}` } })
            .then(resp => resp.blob())
            .then(blob => {
                const objUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = objUrl;
                a.download = `data_usage_${period}_${date}.csv`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(objUrl);
            });
    };

    const totals = data?.totals;
    const vsPct = totals?.vs_previous_pct;
    const donutData = totals ? [
        { name: 'Upload', value: totals.upload_gb },
        { name: 'Download', value: totals.download_gb },
    ] : [];

    const statCards = [
        { label: 'Total Upload', value: `${totals?.upload_gb ?? 0} GB`, color: 'border-l-green-500' },
        { label: 'Total Download', value: `${totals?.download_gb ?? 0} GB`, color: 'border-l-orange-500' },
        { label: 'Total Usage', value: `${totals?.total_gb ?? 0} GB`, color: 'border-l-red-500' },
        { label: 'Active Users', value: totals?.active_users ?? 0, color: 'border-l-purple-500' },
        { label: 'Avg Per User', value: `${totals?.avg_per_user_gb ?? 0} GB`, color: 'border-l-blue-500' },
        {
            label: `vs Previous (${totals?.previous_total_gb ?? 0} GB)`,
            value: vsPct === null || vsPct === undefined ? 'N/A' : `${vsPct > 0 ? '+' : ''}${vsPct}%`,
            color: vsPct !== null && vsPct !== undefined && vsPct < 0 ? 'border-l-emerald-500' : 'border-l-rose-500',
        },
    ];

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6">Data Usage</h1>

            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                <div className="bg-blue-600 px-6 py-4 flex items-center text-white font-bold">
                    <PieIcon className="h-5 w-5 mr-2" /> Data Usage
                </div>

                <div className="flex border-b overflow-x-auto">
                    {PERIODS.map(p => (
                        <button
                            key={p.key}
                            onClick={() => setPeriod(p.key)}
                            className={`flex items-center shrink-0 px-4 sm:px-6 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${period === p.key
                                ? 'border-blue-500 text-blue-600 bg-blue-50'
                                : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                                }`}
                        >
                            <Calendar className="h-4 w-4 mr-2" /> {p.label}
                        </button>
                    ))}
                </div>

                {/* Stat cards */}
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 p-6">
                    {statCards.map(c => (
                        <div key={c.label} className={`border-l-4 ${c.color} bg-gray-50 rounded-r-lg px-4 py-3`}>
                            <p className="text-xl font-bold text-gray-900">{c.value}</p>
                            <p className="text-xs text-gray-500 uppercase tracking-wide mt-1">{c.label}</p>
                        </div>
                    ))}
                </div>

                {/* Filters */}
                <form onSubmit={handleFilter} className="flex flex-wrap items-center gap-2 px-6 pb-4">
                    <div className="relative flex-1 min-w-[180px]">
                        <input
                            type="text" placeholder="Search username or name"
                            value={searchInput} onChange={e => setSearchInput(e.target.value)}
                            className="w-full pl-9 pr-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-gray-400" />
                    </div>
                    <select value={routerFilter} onChange={e => setRouterFilter(e.target.value)} className="border rounded-lg px-3 py-2 text-sm">
                        <option value="">All Routers</option>
                        {routers?.map((r: any) => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </select>
                    <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} className="border rounded-lg px-3 py-2 text-sm">
                        <option value="">All Types</option>
                        <option value="pppoe">PPPoE</option>
                        <option value="hotspot">Hotspot</option>
                        <option value="both">Both</option>
                    </select>
                    <input type="date" value={date} onChange={e => setDate(e.target.value)} className="border rounded-lg px-3 py-2 text-sm" />
                    <select value={limit} onChange={e => setLimit(Number(e.target.value))} className="border rounded-lg px-3 py-2 text-sm">
                        {[10, 25, 50, 100, 200].map(n => <option key={n} value={n}>{n}</option>)}
                    </select>
                    <button type="submit" className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
                        <Filter className="h-4 w-4" /> Filter
                    </button>
                    <button type="button" onClick={handleReset} className="flex items-center gap-1.5 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200">
                        <RotateCcw className="h-4 w-4" /> Reset
                    </button>
                    <button type="button" onClick={handleExportCSV} className="flex items-center gap-1.5 px-4 py-2 bg-amber-500 text-white rounded-lg text-sm font-medium hover:bg-amber-600">
                        <Download className="h-4 w-4" /> CSV
                    </button>
                </form>

                {/* Sort by */}
                <div className="flex flex-wrap items-center gap-2 px-6 pb-6">
                    <span className="text-sm text-gray-500 mr-1">Sort by:</span>
                    {SORTS.map(s => (
                        <button
                            key={s.key}
                            onClick={() => setSort(s.key)}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${sort === s.key
                                ? 'bg-red-500 text-white'
                                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                }`}
                        >
                            <s.icon className="h-3.5 w-3.5" /> {s.label}
                        </button>
                    ))}
                </div>

                {/* Charts */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 px-6 pb-6">
                    <div className="lg:col-span-2 border rounded-lg p-4">
                        <h3 className="text-sm font-bold mb-4 flex items-center">
                            <TrendingUp className="h-4 w-4 mr-2 text-gray-400" /> Top 10 Users by Usage
                        </h3>
                        <div className="h-80">
                            {isLoading ? (
                                <div className="h-full flex items-center justify-center text-gray-400 text-sm">Loading...</div>
                            ) : (data?.top_users?.length ?? 0) === 0 ? (
                                <div className="h-full flex items-center justify-center text-gray-400 text-sm">No usage in this period.</div>
                            ) : (
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={data.top_users} layout="vertical" margin={{ left: 20 }}>
                                        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                                        <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v) => `${v} GB`} />
                                        <YAxis type="category" dataKey="username" tick={{ fontSize: 12 }} width={110} />
                                        <Tooltip formatter={(v: number) => `${v} GB`} />
                                        <Bar dataKey="total_gb" fill="#60a5fa" radius={[0, 4, 4, 0]} name="Total Usage" />
                                    </BarChart>
                                </ResponsiveContainer>
                            )}
                        </div>
                    </div>

                    <div className="border rounded-lg p-4">
                        <h3 className="text-sm font-bold mb-4 flex items-center">
                            <PieIcon className="h-4 w-4 mr-2 text-gray-400" /> Upload vs Download
                        </h3>
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie data={donutData} dataKey="value" innerRadius={55} outerRadius={90} paddingAngle={2}>
                                        <Cell fill="#fbbf24" />
                                        <Cell fill="#34d399" />
                                    </Pie>
                                    <Tooltip formatter={(v: number) => `${v} GB`} />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                        <div className="flex justify-center gap-4 text-xs text-gray-500 mt-2">
                            <span className="flex items-center"><span className="h-2 w-2 rounded-full bg-amber-400 mr-1" /> Upload</span>
                            <span className="flex items-center"><span className="h-2 w-2 rounded-full bg-emerald-400 mr-1" /> Download</span>
                        </div>
                    </div>
                </div>

                {/* Table */}
                <div className="border-t overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    <UsersIcon className="h-3.5 w-3.5 inline mr-1" /> User
                                </th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Upload (GB)</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Download (GB)</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Total (GB)</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {isLoading ? (
                                <tr><td colSpan={4} className="text-center py-8 text-gray-500">Loading...</td></tr>
                            ) : data?.users?.length === 0 ? (
                                <tr><td colSpan={4} className="text-center py-8 text-gray-500">No usage recorded for this period.</td></tr>
                            ) : data?.users?.map((u: any) => (
                                <tr key={u.username} className="hover:bg-gray-50">
                                    <td className="px-6 py-3 text-sm font-medium text-gray-900">{u.name}</td>
                                    <td className="px-6 py-3 text-sm text-gray-500 text-right">{u.upload_gb}</td>
                                    <td className="px-6 py-3 text-sm text-gray-500 text-right">{u.download_gb}</td>
                                    <td className="px-6 py-3 text-sm font-medium text-gray-900 text-right">{u.total_gb}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
