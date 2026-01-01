import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
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
import { analyticsAPI, adminAPI } from '../../services/api';
import { Users, CreditCard, Activity, BarChart3, TrendingUp } from 'lucide-react';

export default function Dashboard() {
    const { data: networkActivity } = useQuery({
        queryKey: ['admin-network-activity'],
        queryFn: async () => {
            const res = await adminAPI.getNetworkActivity();
            return res.data;
        },
        refetchInterval: 1000,
    });

    const { data: statsData, isLoading: statsLoading, isError: statsError, error: statsErrorObj } = useQuery({
        queryKey: ['admin-stats'],
        queryFn: async () => {
            try {
                const res = await analyticsAPI.getMonthlyAnalytics();
                // Ensure we return an object, even if empty
                return res.data || {};
            } catch (err) {
                console.error("Error fetching stats:", err);
                throw err;
            }
        }
    });

    const { data: monthlyData } = useQuery({
        queryKey: ['admin-monthly-analytics-chart'],
        queryFn: async () => {
            const res = await analyticsAPI.getMonthlyAnalytics();
            // API structure might need adjustment depending on what getMonthlyAnalytics returns vs dashboard stats
            // Assuming getMonthlyAnalytics returns the chart data array for now, or stats returns everything.
            // Actually, let's assume statsData contains everything for the cards, and monthlyData is for charts.
            return res.data;
        }
    });

    // Mock income data if not provided (or fetch real)
    const incomeData = [
        { date: '2024-01-01', total: 4500 },
        { date: '2024-01-08', total: 5200 },
        { date: '2024-01-15', total: 4800 },
        { date: '2024-01-22', total: 6100 },
        { date: '2024-01-29', total: 5900 },
    ];

    const stats = [
        {
            name: 'Active Subscribers',
            value: statsData?.active_subscribers || 0,
            icon: Users,
            color: 'bg-blue-500',
            change: `+${statsData?.new_customers || 0} new`,
            trend: 'up'
        },
        {
            name: 'Monthly Revenue',
            value: `KES ${statsData?.monthly_revenue?.toLocaleString() || 0}`,
            icon: CreditCard,
            color: 'bg-green-500',
            trend: 'up'
        },
        {
            name: 'Data Usage',
            value: `${statsData?.monthly_usage_gb || 0} GB`,
            icon: Activity,
            color: 'bg-purple-500',
            trend: 'down' // Example
        },
        {
            name: 'Avg. Revenue/User',
            value: `KES ${Math.round((statsData?.monthly_revenue || 0) / (statsData?.active_subscribers || 1))}`,
            icon: TrendingUp,
            color: 'bg-orange-500',
            trend: 'up'
        }
    ];

    const isLoading = statsLoading; // Combine loading states if needed

    if (statsError) {
        return (
            <div className="p-6 text-red-600 dark:text-red-400">
                Error loading dashboard stats: {statsErrorObj instanceof Error ? statsErrorObj.message : 'Unknown error'}
                <br />
                Please ensure you are logged in as an Administrator.
            </div>
        );
    }

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-full min-h-[400px]">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard Overview</h1>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {/* Realtime Network Load Card */}
                <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700">
                    <div className="flex items-center justify-between mb-4">
                        <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                            <Activity className="h-6 w-6 text-blue-600 dark:text-blue-400" />
                        </div>
                        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Live</span>
                    </div>
                    <div className="space-y-2">
                        <div className="flex justify-between items-end">
                            <span className="text-sm text-gray-500 dark:text-gray-400">Download</span>
                            <span className="text-xl font-bold text-gray-900 dark:text-white">
                                {networkActivity?.download_mbps || 0} <span className="text-xs text-gray-500 dark:text-gray-400 font-normal">Mbps</span>
                            </span>
                        </div>
                        <div className="flex justify-between items-end">
                            <span className="text-sm text-gray-500 dark:text-gray-400">Upload</span>
                            <span className="text-xl font-bold text-gray-900 dark:text-white">
                                {networkActivity?.upload_mbps || 0} <span className="text-xs text-gray-500 dark:text-gray-400 font-normal">Mbps</span>
                            </span>
                        </div>
                    </div>
                </div>

                {stats.map((stat) => (
                    <div key={stat.name} className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700">
                        <div className="flex items-center justify-between mb-4">
                            <div className={`p-2 rounded-lg ${stat.color} bg-opacity-10 dark:bg-opacity-20`}>
                                <stat.icon className={`h-6 w-6 ${stat.color.replace('bg-', 'text-')}`} />
                            </div>
                            {stat.change && (
                                <span className={`text-xs font-medium px-2 py-1 rounded-full ${stat.trend === 'up'
                                    ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400'
                                    : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'
                                    }`}>
                                    {stat.change}
                                </span>
                            )}
                        </div>
                        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">{stat.name}</h3>
                        <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{stat.value}</p>
                    </div>
                ))}
            </div>

            {/* Monthly Analytics Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700">
                    <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Monthly Active Users</h2>
                    <div className="h-80">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={monthlyData || []}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.1} />
                                <XAxis dataKey="month" stroke="#9CA3AF" fontSize={12} tickLine={false} axisLine={false} />
                                <YAxis stroke="#9CA3AF" fontSize={12} tickLine={false} axisLine={false} />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#1F2937', borderColor: '#374151', color: '#F3F4F6' }}
                                    itemStyle={{ color: '#F3F4F6' }}
                                    cursor={{ fill: 'rgba(55, 65, 81, 0.4)' }} // Darker cursor for dark mode
                                />
                                <Bar dataKey="active_users" name="Active Users" fill="#22c55e" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700">
                    <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Monthly Data Consumption (GB)</h2>
                    <div className="h-80">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={monthlyData || []}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.1} />
                                <XAxis dataKey="month" stroke="#9CA3AF" fontSize={12} tickLine={false} axisLine={false} />
                                <YAxis stroke="#9CA3AF" fontSize={12} tickLine={false} axisLine={false} />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#1F2937', borderColor: '#374151', color: '#F3F4F6' }}
                                    itemStyle={{ color: '#F3F4F6' }}
                                    cursor={{ fill: 'rgba(55, 65, 81, 0.4)' }}
                                />
                                <Legend />
                                <Bar dataKey="download_gb" name="Download" stackId="a" fill="#3b82f6" />
                                <Bar dataKey="upload_gb" name="Upload" stackId="a" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>

            {/* Charts Row 2: Revenue & Actions */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700 lg:col-span-2">
                    <h3 className="text-lg font-bold mb-4 flex items-center gap-2 text-gray-900 dark:text-white">
                        <BarChart3 className="w-5 h-5 text-green-600 dark:text-green-400" />
                        Revenue Trend (Last 30 Days)
                    </h3>
                    <div className="h-72">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={incomeData || []}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                <XAxis dataKey="date" tickFormatter={(val) => val.split('-').slice(1).join('/')} />
                                <YAxis />
                                <Tooltip formatter={(value) => `KES ${value}`} />
                                <Bar dataKey="total" fill="#10b981" radius={[4, 4, 0, 0]} name="Revenue" />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Secondary Chart area - placeholder for now, maybe User Distribution */}
                <div className="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-sm border border-gray-100 dark:border-gray-700">
                    <h3 className="text-lg font-bold mb-4 text-gray-900 dark:text-white">Quick Actions</h3>
                    <div className="space-y-3">
                        <button className="w-full py-2 px-4 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/50 transition text-sm font-medium">
                            Generate Vouchers
                        </button>
                        <button className="w-full py-2 px-4 bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 transition text-sm font-medium">
                            Manage Subscribers
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
