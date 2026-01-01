import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer
} from 'recharts';
import { analyticsAPI } from '../../services/api';
import { Users, CreditCard, Activity, ArrowUpRight } from 'lucide-react';

export default function Dashboard() {
    const { data: stats, isLoading: statsLoading, isError: statsError, error: statsErrorObj } = useQuery({
        queryKey: ['admin-stats'],
        queryFn: async () => {
            console.log('Fetching admin stats...');
            try {
                const res = await analyticsAPI.getDashboardStats();
                console.log('Admin stats res:', res);
                return res.data;
            } catch (err) {
                console.error('Admin stats error:', err);
                throw err;
            }
        }
    });

    const { data: incomeData } = useQuery({
        queryKey: ['admin-income'],
        queryFn: async () => {
            const res = await analyticsAPI.getIncomeReport();
            return res.data;
        }
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

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6">Dashboard Overview</h1>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex items-center">
                    <div className="p-3 bg-blue-100 rounded-full text-blue-600 mr-4">
                        <Users className="h-6 w-6" />
                    </div>
                    <div>
                        <h3 className="text-gray-500 text-sm font-medium">Active Subscribers</h3>
                        <p className="text-2xl font-bold mt-1">{stats?.active_subscribers ?? '...'}</p>
                        <p className="text-xs text-green-600 flex items-center mt-1">
                            <ArrowUpRight className="h-3 w-3 mr-1" /> {stats?.new_customers ?? 0} new this month
                        </p>
                    </div>
                </div>

                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex items-center">
                    <div className="p-3 bg-green-100 rounded-full text-green-600 mr-4">
                        <CreditCard className="h-6 w-6" />
                    </div>
                    <div>
                        <h3 className="text-gray-500 text-sm font-medium">Monthly Revenue</h3>
                        <p className="text-2xl font-bold mt-1">KES {stats?.monthly_revenue?.toLocaleString() ?? '...'}</p>
                    </div>
                </div>

                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex items-center">
                    <div className="p-3 bg-purple-100 rounded-full text-purple-600 mr-4">
                        <Activity className="h-6 w-6" />
                    </div>
                    <div>
                        <h3 className="text-gray-500 text-sm font-medium">Data Usage</h3>
                        <p className="text-2xl font-bold mt-1">{stats?.monthly_usage_gb ?? '...'} GB</p>
                    </div>
                </div>
            </div>

            {/* Charts Row */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 lg:col-span-2">
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

                {/* Secondary Chart area - placeholder for now, maybe User Distribution */}
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100">
                    <h3 className="text-lg font-bold mb-4">Quick Actions</h3>
                    <div className="space-y-3">
                        <button className="w-full py-2 px-4 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 transition text-sm font-medium">
                            Generate Vouchers
                        </button>
                        <button className="w-full py-2 px-4 bg-gray-50 text-gray-700 rounded-lg hover:bg-gray-100 transition text-sm font-medium">
                            Manage Subscribers
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
