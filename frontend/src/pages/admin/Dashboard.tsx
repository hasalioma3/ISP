import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    PieChart,
    Pie,
    Cell,
    Legend,
} from 'recharts';
import { format } from 'date-fns';
import { analyticsAPI } from '../../services/api';
import {
    Users, CreditCard, ShoppingBag, BarChart3, Wifi, Share2, Radio, UsersRound,
    RouterIcon, ChevronDown, RefreshCw, ArrowRight, Smartphone, CheckCircle2, XCircle,
} from 'lucide-react';
import UsageChartPanels from '../../components/UsageChartPanels';

const INSIGHT_COLORS = ['#16a34a', '#7c2d3f', '#475569'];

const CARD_STYLES: Record<string, string> = {
    teal: 'bg-teal-600',
    sky: 'bg-sky-700',
    slate: 'bg-slate-700',
    indigo: 'bg-indigo-900',
    emerald: 'bg-emerald-600',
    cyan: 'bg-cyan-700',
    violet: 'bg-violet-800',
    green: 'bg-green-600',
};

export default function Dashboard() {
    const navigate = useNavigate();
    const [routerFilter, setRouterFilter] = useState<number | 'all'>('all');
    const [isRouterDropdownOpen, setIsRouterDropdownOpen] = useState(false);
    const [expiringPage, setExpiringPage] = useState(1);

    const { data: stats, isLoading: statsLoading, isError: statsError, error: statsErrorObj, refetch: refetchStats, isFetching: statsFetching } = useQuery({
        queryKey: ['admin-stats'],
        queryFn: async () => {
            const res = await analyticsAPI.getDashboardStats();
            return res.data;
        }
    });

    const { data: incomeData } = useQuery({
        queryKey: ['admin-income'],
        queryFn: async () => {
            const res = await analyticsAPI.getIncomeReport();
            return res.data;
        }
    });

    const { data: usageChart, isLoading: usageChartLoading } = useQuery({
        queryKey: ['admin-usage-chart'],
        queryFn: async () => {
            const res = await analyticsAPI.getUsageChart();
            return res.data;
        }
    });

    const { data: usageData, isLoading: usageLoading } = useQuery({
        queryKey: ['admin-usage'],
        queryFn: async () => {
            const res = await analyticsAPI.getUsageReport();
            return res.data;
        }
    });

    const { data: extra, isLoading: extraLoading } = useQuery({
        queryKey: ['admin-stats-extra'],
        queryFn: async () => {
            const res = await analyticsAPI.getDashboardExtra();
            return res.data;
        }
    });

    const { data: expiring, isLoading: expiringLoading } = useQuery({
        queryKey: ['admin-expiring-today', expiringPage],
        queryFn: async () => {
            const res = await analyticsAPI.getExpiringToday(expiringPage, 10);
            return res.data;
        }
    });

    const { data: activity, isLoading: activityLoading } = useQuery({
        queryKey: ['admin-recent-activity'],
        queryFn: async () => {
            const res = await analyticsAPI.getRecentActivity();
            return res.data;
        },
        refetchInterval: 30000,
    });

    if (statsError) {
        return (
            <div className="p-6 text-red-600">
                Error loading dashboard stats: {statsErrorObj instanceof Error ? statsErrorObj.message : 'Unknown error'}
                <br />
                Please ensure you are logged in as an Administrator.
            </div>
        );
    }

    const routers = stats?.routers || [];
    const visibleRouters = routerFilter === 'all' ? routers : routers.filter((r: any) => r.id === routerFilter);
    const selectedRouterName = routerFilter === 'all'
        ? 'All Routers - System Wide'
        : routers.find((r: any) => r.id === routerFilter)?.name || 'All Routers - System Wide';

    const statCards = [
        {
            label: 'Income Today', value: `Ksh. ${Number(stats?.income_today ?? 0).toLocaleString()}`,
            icon: ShoppingBag, color: 'teal', href: '/admin/reports', linkLabel: 'View Reports',
        },
        {
            label: 'Income This Month', value: `Ksh. ${Number(stats?.monthly_revenue ?? 0).toLocaleString()}`,
            icon: BarChart3, color: 'sky', href: '/admin/reports', linkLabel: 'View Reports',
        },
        {
            label: 'Active/Expired', value: `${stats?.active_subscribers ?? 0}/${stats?.expired_subscribers ?? 0}`,
            icon: Users, color: 'slate', href: '/admin/subscribers', linkLabel: 'View All',
        },
        {
            label: 'Total Users', value: stats?.total_customers ?? 0,
            icon: UsersRound, color: 'indigo', href: '/admin/subscribers', linkLabel: 'View All',
        },
        {
            label: 'Hotspot Online Users', value: stats?.hotspot_online ?? 0,
            icon: Wifi, color: 'emerald', href: '/admin/online-users?type=hotspot', linkLabel: 'View All',
        },
        {
            label: 'PPPoE Online Users', value: stats?.pppoe_online ?? 0,
            icon: Share2, color: 'cyan', href: '/admin/online-users?type=pppoe', linkLabel: 'View All',
        },
        {
            label: 'Total Online Users', value: stats?.total_online ?? 0,
            icon: Radio, color: 'violet', href: '/admin/online-users', linkLabel: 'View All',
        },
        {
            label: 'New This Month', value: stats?.new_customers ?? 0,
            icon: CreditCard, color: 'green', href: '/admin/subscribers', linkLabel: 'View All',
        },
    ];

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

            {/* Router View */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden mb-6">
                <div className="bg-blue-600 px-6 py-4 flex items-center justify-between">
                    <div className="flex items-center text-white font-bold">
                        <RouterIcon className="h-5 w-5 mr-2" />
                        Router View
                    </div>
                    <div className="relative">
                        <button
                            onClick={() => setIsRouterDropdownOpen(!isRouterDropdownOpen)}
                            className="flex items-center gap-2 bg-white/95 hover:bg-white px-3 py-1.5 rounded-lg text-sm font-medium text-gray-700"
                        >
                            {selectedRouterName}
                            <ChevronDown className="h-4 w-4" />
                        </button>
                        {isRouterDropdownOpen && (
                            <div className="absolute right-0 mt-1 w-56 bg-white rounded-lg shadow-xl border border-gray-100 py-1 z-20">
                                <button
                                    onClick={() => { setRouterFilter('all'); setIsRouterDropdownOpen(false); }}
                                    className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                                >
                                    All Routers - System Wide
                                </button>
                                {routers.map((r: any) => (
                                    <button
                                        key={r.id}
                                        onClick={() => { setRouterFilter(r.id); setIsRouterDropdownOpen(false); }}
                                        className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                                    >
                                        {r.name}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                <div className="p-4 flex flex-wrap gap-4">
                    {statsLoading ? (
                        <div className="text-gray-500 text-sm py-4 px-2">Loading routers...</div>
                    ) : visibleRouters.length === 0 ? (
                        <div className="text-gray-500 text-sm py-4 px-2">No routers configured yet.</div>
                    ) : visibleRouters.map((r: any) => (
                        <button
                            key={r.id}
                            onClick={() => navigate('/admin/mikrotik')}
                            className="border rounded-lg px-4 py-3 min-w-[180px] text-left hover:bg-gray-50 transition"
                        >
                            <p className="font-medium text-blue-600 mb-1">{r.name}</p>
                            <div className="flex items-center gap-3 text-sm">
                                <span className="flex items-center text-emerald-600">
                                    <span className="h-2 w-2 rounded-full bg-emerald-500 mr-1" /> {r.online}
                                </span>
                                <span className="text-blue-600">✓ {r.valid}</span>
                                <span className="text-red-500">✕ {r.invalid}</span>
                            </div>
                        </button>
                    ))}
                </div>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                {statCards.map((card) => (
                    <div key={card.label} className={`${CARD_STYLES[card.color]} rounded-xl p-6 text-white shadow-sm`}>
                        <div className="flex items-start justify-between mb-2">
                            <p className="text-2xl font-bold">{card.value}</p>
                            <card.icon className="h-6 w-6 opacity-70" />
                        </div>
                        <p className="text-xs uppercase tracking-wide opacity-80 mb-3">{card.label}</p>
                        <button
                            onClick={() => navigate(card.href)}
                            className="flex items-center text-xs font-medium opacity-90 hover:opacity-100 border-t border-white/20 pt-2 w-full"
                        >
                            {card.linkLabel} <ArrowRight className="h-3 w-3 ml-1" />
                        </button>
                    </div>
                ))}
            </div>

            <div className="flex justify-end mb-6">
                <button
                    onClick={() => refetchStats()}
                    disabled={statsFetching}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition text-sm font-medium disabled:opacity-50"
                >
                    <RefreshCw className={`h-4 w-4 ${statsFetching ? 'animate-spin' : ''}`} />
                    Refresh Online Users
                </button>
            </div>

            {/* Registration / Sales trends + Gateway / Insights / Packages */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                <div className="lg:col-span-2 space-y-6">
                    <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
                        <h3 className="text-lg font-bold mb-4">Monthly Registered Customers</h3>
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={extra?.monthly_registrations || []}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                    <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                                    <YAxis tick={{ fontSize: 12 }} />
                                    <Tooltip />
                                    <Bar dataKey="count" fill="#818cf8" name="Registered" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
                        <h3 className="text-lg font-bold mb-4">Total Monthly Sales</h3>
                        <div className="h-64">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={extra?.monthly_sales || []}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                    <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                                    <YAxis tick={{ fontSize: 12 }} />
                                    <Tooltip formatter={(v: number) => `KES ${v}`} />
                                    <Bar dataKey="total" fill="#2563eb" name="Sales" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </div>

                <div className="space-y-6">
                    <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                        <div className="bg-blue-600 px-4 py-3 text-white font-bold text-sm">
                            Payment Gateway: {extra?.payment_gateway?.name || '-'}
                        </div>
                        <div className="p-4 text-sm space-y-2">
                            {extraLoading ? (
                                <p className="text-gray-400">Checking...</p>
                            ) : (
                                <>
                                    <div className="flex items-center justify-between">
                                        <span className="text-gray-500">Status</span>
                                        {extra?.payment_gateway?.connected ? (
                                            <span className="flex items-center text-green-600 font-medium">
                                                <CheckCircle2 className="h-4 w-4 mr-1" /> Connected
                                            </span>
                                        ) : (
                                            <span className="flex items-center text-red-600 font-medium">
                                                <XCircle className="h-4 w-4 mr-1" /> Disconnected
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-gray-500">Environment</span>
                                        <span className="capitalize">{extra?.payment_gateway?.environment}</span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-gray-500">Shortcode</span>
                                        <span>{extra?.payment_gateway?.shortcode}</span>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>

                    <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                        <div className="bg-blue-600 px-4 py-3 text-white font-bold text-sm">All Users Insights</div>
                        <div className="p-4">
                            <div className="h-48">
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie
                                            data={[
                                                { name: 'Active Users', value: extra?.user_insights?.active || 0 },
                                                { name: 'Expired Users', value: extra?.user_insights?.expired || 0 },
                                                { name: 'Inactive Users', value: extra?.user_insights?.inactive || 0 },
                                            ]}
                                            dataKey="value"
                                            outerRadius={70}
                                        >
                                            {INSIGHT_COLORS.map((c, i) => <Cell key={i} fill={c} />)}
                                        </Pie>
                                        <Legend wrapperStyle={{ fontSize: 11 }} />
                                        <Tooltip />
                                    </PieChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>

                    <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                        <div className="bg-blue-600 px-4 py-3 text-white font-bold text-sm">Best Selling Packages This Month</div>
                        <div className="overflow-x-auto">
                            <table className="min-w-full text-sm">
                                <thead>
                                    <tr className="text-left text-xs text-gray-500 uppercase border-b">
                                        <th className="px-4 py-2">Package</th>
                                        <th className="px-4 py-2 text-right">Sales</th>
                                        <th className="px-4 py-2 text-right">Revenue</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100">
                                    {extra?.best_selling_packages?.length === 0 ? (
                                        <tr><td colSpan={3} className="px-4 py-4 text-center text-gray-400">No sales this month.</td></tr>
                                    ) : extra?.best_selling_packages?.map((p: any) => (
                                        <tr key={p.name}>
                                            <td className="px-4 py-2 font-medium">{p.name}</td>
                                            <td className="px-4 py-2 text-right">{p.sales}</td>
                                            <td className="px-4 py-2 text-right">Ksh. {p.revenue.toLocaleString()}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            {/* Network-wide Data Usage */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 mb-6">
                <h3 className="text-lg font-bold mb-4">General Data Usage (Whole Network)</h3>
                <UsageChartPanels chart={usageChart} loading={usageChartLoading} />
            </div>

            {/* Revenue Chart */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 mb-6">
                <h3 className="text-lg font-bold mb-4">Revenue Trend (Last 30 Days)</h3>
                <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={incomeData || []}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} />
                            <XAxis dataKey="date" tickFormatter={(val) => val.split('-').slice(1).join('/')} />
                            <YAxis />
                            <Tooltip formatter={(value) => `KES ${value}`} />
                            <Bar dataKey="total" fill="#3b82f6" radius={[4, 4, 0, 0]} name="Revenue" />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Transactions per Router / Last 5 Transactions / Users by Service Type */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                    <div className="bg-blue-600 px-4 py-3 text-white font-bold text-sm">Transactions per Router</div>
                    <div className="overflow-x-auto">
                        <table className="min-w-full text-sm">
                            <thead>
                                <tr className="text-left text-xs text-gray-500 uppercase border-b">
                                    <th className="px-4 py-2">Router</th>
                                    <th className="px-4 py-2 text-right">Txns</th>
                                    <th className="px-4 py-2 text-right">%</th>
                                    <th className="px-4 py-2 text-right">Amount</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                                {extra?.transactions_per_router?.length === 0 ? (
                                    <tr><td colSpan={4} className="px-4 py-4 text-center text-gray-400">No transactions yet.</td></tr>
                                ) : extra?.transactions_per_router?.map((r: any) => (
                                    <tr key={r.router}>
                                        <td className="px-4 py-2 font-medium">{r.router}</td>
                                        <td className="px-4 py-2 text-right">{r.transactions}</td>
                                        <td className="px-4 py-2 text-right">{r.percentage}%</td>
                                        <td className="px-4 py-2 text-right">Ksh. {r.amount.toLocaleString()}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                    <div className="bg-blue-600 px-4 py-3 text-white font-bold text-sm">Last 5 Transactions</div>
                    <div className="overflow-x-auto">
                        <table className="min-w-full text-sm">
                            <thead>
                                <tr className="text-left text-xs text-gray-500 uppercase border-b">
                                    <th className="px-4 py-2">Username</th>
                                    <th className="px-4 py-2 text-right">Amount</th>
                                    <th className="px-4 py-2 text-right">Date</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                                {extra?.last_transactions?.length === 0 ? (
                                    <tr><td colSpan={3} className="px-4 py-4 text-center text-gray-400">No transactions yet.</td></tr>
                                ) : extra?.last_transactions?.map((t: any, i: number) => (
                                    <tr key={i}>
                                        <td className="px-4 py-2 font-medium truncate max-w-[120px]">{t.username}</td>
                                        <td className="px-4 py-2 text-right">Ksh. {t.amount}</td>
                                        <td className="px-4 py-2 text-right text-gray-500">{format(new Date(t.date), 'yyyy-MM-dd')}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                    <div className="bg-blue-600 px-4 py-3 text-white font-bold text-sm flex items-center">
                        <Smartphone className="h-4 w-4 mr-2" /> Users by Service Type
                    </div>
                    <div className="overflow-x-auto">
                        <table className="min-w-full text-sm">
                            <thead>
                                <tr className="text-left text-xs text-gray-500 uppercase border-b">
                                    <th className="px-4 py-2">Service Type</th>
                                    <th className="px-4 py-2 text-right">Users</th>
                                    <th className="px-4 py-2 text-right">%</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                                {extra?.users_by_service_type?.map((s: any) => (
                                    <tr key={s.service_type}>
                                        <td className="px-4 py-2 font-medium capitalize">{s.service_type}</td>
                                        <td className="px-4 py-2 text-right">{s.count}</td>
                                        <td className="px-4 py-2 text-right">{s.percentage}%</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            {/* Voucher Stock */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden mb-6">
                <div className="bg-blue-600 px-6 py-4 text-white font-bold">Vouchers Stock</div>
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200 text-sm">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Plan Name</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Unused</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Used</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                            {extra?.voucher_stock?.length === 0 ? (
                                <tr><td colSpan={3} className="px-6 py-4 text-center text-gray-400">No vouchers generated yet.</td></tr>
                            ) : extra?.voucher_stock?.map((v: any) => (
                                <tr key={v.plan_name}>
                                    <td className="px-6 py-3 font-medium">{v.plan_name}</td>
                                    <td className="px-6 py-3 text-right">{v.unused}</td>
                                    <td className="px-6 py-3 text-right">{v.used}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Usage by User */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100">
                <div className="p-6 border-b border-gray-100">
                    <h3 className="text-lg font-bold">Top Data Usage by User (Last 30 Days)</h3>
                </div>
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">User</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Upload (GB)</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Download (GB)</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Total (GB)</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {usageLoading ? (
                                <tr><td colSpan={4} className="text-center py-8 text-gray-500">Loading...</td></tr>
                            ) : usageData?.length === 0 ? (
                                <tr><td colSpan={4} className="text-center py-8 text-gray-500">No usage recorded yet.</td></tr>
                            ) : usageData?.map((u: any) => (
                                <tr key={u.username} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 text-sm font-medium text-gray-900">{u.name}</td>
                                    <td className="px-6 py-4 text-sm text-gray-500 text-right">{u.upload_gb}</td>
                                    <td className="px-6 py-4 text-sm text-gray-500 text-right">{u.download_gb}</td>
                                    <td className="px-6 py-4 text-sm font-medium text-gray-900 text-right">{u.total_gb}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Users Expiring Today / Recent Activity */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
                <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                    <div className="bg-blue-600 px-6 py-4 text-white font-bold">Users Expiring Today</div>
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 text-sm">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Username</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created On</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Expires On</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                                {expiringLoading ? (
                                    <tr><td colSpan={3} className="px-6 py-6 text-center text-gray-400">Loading...</td></tr>
                                ) : expiring?.results?.length === 0 ? (
                                    <tr><td colSpan={3} className="px-6 py-6 text-center text-gray-400">No subscriptions expiring today.</td></tr>
                                ) : expiring?.results?.map((u: any, i: number) => (
                                    <tr key={i}>
                                        <td className="px-6 py-3 font-medium text-blue-600">{u.username}</td>
                                        <td className="px-6 py-3 text-gray-500">{format(new Date(u.created_on), 'd MMM yyyy HH:mm')}</td>
                                        <td className="px-6 py-3 text-gray-500">{format(new Date(u.expires_on), 'd MMM yyyy HH:mm')}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    {expiring && expiring.total_pages > 1 && (
                        <div className="flex items-center justify-between px-6 py-3 border-t text-sm">
                            <button
                                onClick={() => setExpiringPage(p => Math.max(1, p - 1))}
                                disabled={expiringPage <= 1}
                                className="px-3 py-1 rounded border disabled:opacity-40"
                            >
                                Prev
                            </button>
                            <span className="text-gray-500">Page {expiring.page} of {expiring.total_pages}</span>
                            <button
                                onClick={() => setExpiringPage(p => Math.min(expiring.total_pages, p + 1))}
                                disabled={expiringPage >= expiring.total_pages}
                                className="px-3 py-1 rounded border disabled:opacity-40"
                            >
                                Next
                            </button>
                        </div>
                    )}
                </div>

                <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                    <div className="bg-blue-600 px-6 py-4 text-white font-bold">Recent Activity</div>
                    <div className="p-4 space-y-2 max-h-96 overflow-y-auto">
                        {activityLoading ? (
                            <p className="text-gray-400 text-sm">Loading...</p>
                        ) : activity?.length === 0 ? (
                            <p className="text-gray-400 text-sm">No login activity recorded yet.</p>
                        ) : activity?.map((a: any, i: number) => (
                            <div key={i} className="text-sm border-b last:border-0 pb-2">
                                <p className="text-gray-800">{a.message}</p>
                                <p className="text-xs text-gray-400">{format(new Date(a.created_at), 'd MMM yyyy HH:mm')}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
