import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { billingAPI } from '../../services/api';
import { formatDistanceToNow } from 'date-fns';
import { Wifi, CreditCard, Activity, User } from 'lucide-react';

export default function CustomerDashboard() {
    const { user } = useAuthStore();
    console.log('Current User Debug:', user);

    const { data: subscription } = useQuery({
        queryKey: ['subscription'],
        queryFn: async () => {
            try {
                const response = await billingAPI.getCurrentSubscription();
                return response.data;
            } catch {
                return null;
            }
        },
    });

    const { data: usageData } = useQuery({
        queryKey: ['liveUsage'],
        queryFn: async () => {
            try {
                const response = await billingAPI.getUsage();
                // Handle paginated response
                const data = response.data;
                return Array.isArray(data) ? data : data.results || [];
            } catch {
                return [];
            }
        },
        refetchInterval: 1000, // Poll every 1 second
    });

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            {/* Welcome Section */}
            <div className="bg-gradient-to-r from-blue-600 to-purple-600 rounded-2xl p-8 text-white shadow-lg">
                <div className="flex items-center gap-4">
                    <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center backdrop-blur-sm">
                        <User className="w-8 h-8" />
                    </div>
                    <div>
                        <h2 className="text-3xl font-bold">Welcome, {user?.full_name || user?.username}!</h2>
                        <p className="text-blue-100 mt-1">Account Status: <span className="font-semibold px-2 py-0.5 bg-white/20 rounded-full text-sm">{user?.status}</span></p>
                    </div>
                </div>
            </div>

            {/* Subscription Card */}
            {subscription ? (
                <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-6 transition-colors">
                    <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-4">Current Subscription</h3>
                    <div className="grid md:grid-cols-2 gap-6">
                        <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-xl">
                            <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Active Plan</p>
                            <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">{subscription.plan.name}</p>
                            <p className="text-gray-600 dark:text-gray-300 mt-2 flex items-center gap-2">
                                <Activity className="w-4 h-4" />
                                {subscription.plan.download_speed}/{subscription.plan.upload_speed} Mbps
                            </p>
                        </div>
                        <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-xl">
                            <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Expires In</p>
                            <p className="text-lg font-semibold text-gray-900 dark:text-white">
                                {formatDistanceToNow(new Date(subscription.expiry_date), { addSuffix: true })}
                            </p>
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                {new Date(subscription.expiry_date).toLocaleDateString()}
                            </p>
                        </div>
                    </div>

                    {subscription.days_remaining <= 3 && (
                        <div className="mt-6 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700 rounded-xl p-4 flex items-center justify-between">
                            <p className="text-yellow-800 dark:text-yellow-400 font-semibold flex items-center gap-2">
                                <span>⚠️</span> Your subscription is expiring soon!
                            </p>
                            <Link to="/plans" className="px-4 py-2 bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-300 rounded-lg hover:bg-yellow-200 dark:hover:bg-yellow-900/60 transition text-sm font-medium">
                                Renew now
                            </Link>
                        </div>
                    )}
                </div>
            ) : (
                <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-8 text-center transition-colors">
                    <div className="w-20 h-20 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center mx-auto mb-6">
                        <Wifi className="w-10 h-10 text-gray-400 dark:text-gray-500" />
                    </div>
                    <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">No Active Subscription</h3>
                    <p className="text-gray-500 dark:text-gray-400 mb-8 max-w-sm mx-auto">Subscribe to one of our high-speed internet plans to get connected instantly.</p>
                    <Link
                        to="/plans"
                        className="inline-flex items-center gap-2 bg-blue-600 text-white px-8 py-3 rounded-xl font-semibold hover:bg-blue-700 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200"
                    >
                        View Plans <span aria-hidden="true">&rarr;</span>
                    </Link>
                </div>
            )}

            {/* Quick Actions */}
            <div className="grid md:grid-cols-3 gap-6">
                <Link
                    to="/plans"
                    className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-500 hover:shadow-md transition-all group"
                >
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 bg-blue-100 dark:bg-blue-900/30 rounded-xl flex items-center justify-center group-hover:bg-blue-600 group-hover:text-white transition-all text-blue-600 dark:text-blue-400">
                            <Wifi className="w-6 h-6" />
                        </div>
                        <div>
                            <h4 className="font-bold text-gray-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">View Plans</h4>
                            <p className="text-sm text-gray-500 dark:text-gray-400">Browse packages</p>
                        </div>
                    </div>
                </Link>

                <Link
                    to="/payment"
                    className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700 hover:border-green-500 dark:hover:border-green-500 hover:shadow-md transition-all group"
                >
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 bg-green-100 dark:bg-green-900/30 rounded-xl flex items-center justify-center group-hover:bg-green-600 group-hover:text-white transition-all text-green-600 dark:text-green-400">
                            <CreditCard className="w-6 h-6" />
                        </div>
                        <div>
                            <h4 className="font-bold text-gray-900 dark:text-white group-hover:text-green-600 dark:group-hover:text-green-400 transition-colors">Make Payment</h4>
                            <p className="text-sm text-gray-500 dark:text-gray-400">Pay via M-Pesa</p>
                        </div>
                    </div>
                </Link>

                <Link
                    to="/usage"
                    className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm border border-gray-100 dark:border-gray-700 hover:border-purple-500 dark:hover:border-purple-500 hover:shadow-md transition-all group"
                >
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 bg-purple-100 dark:bg-purple-900/30 rounded-xl flex items-center justify-center group-hover:bg-purple-600 group-hover:text-white transition-all text-purple-600 dark:text-purple-400">
                            <Activity className="w-6 h-6" />
                        </div>
                        <div>
                            <h4 className="font-bold text-gray-900 dark:text-white group-hover:text-purple-600 dark:group-hover:text-purple-400 transition-colors">Usage Stats</h4>
                            <p className="text-sm text-gray-500 dark:text-gray-400">View consumption</p>
                        </div>
                    </div>
                </Link>
            </div>

            {/* Live Usage Stats */}
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 p-6 transition-colors">
                <div className="flex items-center gap-3 mb-6">
                    <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                        <Activity className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                    </div>
                    <h3 className="text-xl font-bold text-gray-900 dark:text-white">Live Network Activity</h3>
                </div>

                {usageData && usageData.length > 0 ? (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                        <div className="bg-gray-50 dark:bg-gray-700/50 rounded-xl p-4 border border-transparent hover:border-blue-200 dark:hover:border-blue-700/50 transition-colors">
                            <p className="text-xs text-uppercase tracking-wider text-gray-500 dark:text-gray-400 font-semibold mb-1">DOWNLOAD</p>
                            <p className="text-2xl font-bold text-gray-900 dark:text-white">
                                {usageData[0].download_speed_mbps || 0} <span className="text-sm font-normal text-gray-500 dark:text-gray-400">Mbps</span>
                            </p>
                        </div>
                        <div className="bg-gray-50 dark:bg-gray-700/50 rounded-xl p-4 border border-transparent hover:border-green-200 dark:hover:border-green-700/50 transition-colors">
                            <p className="text-xs text-uppercase tracking-wider text-gray-500 dark:text-gray-400 font-semibold mb-1">UPLOAD</p>
                            <p className="text-2xl font-bold text-gray-900 dark:text-white">
                                {usageData[0].upload_speed_mbps || 0} <span className="text-sm font-normal text-gray-500 dark:text-gray-400">Mbps</span>
                            </p>
                        </div>
                        <div className="bg-gray-50 dark:bg-gray-700/50 rounded-xl p-4 border border-transparent hover:border-purple-200 dark:hover:border-purple-700/50 transition-colors">
                            <p className="text-xs text-uppercase tracking-wider text-gray-500 dark:text-gray-400 font-semibold mb-1">DATA USED</p>
                            <p className="text-2xl font-bold text-gray-900 dark:text-white">
                                {usageData[0].total_gb} <span className="text-sm font-normal text-gray-500 dark:text-gray-400">GB</span>
                            </p>
                        </div>
                        <div className="bg-gray-50 dark:bg-gray-700/50 rounded-xl p-4 border border-transparent hover:border-orange-200 dark:hover:border-orange-700/50 transition-colors">
                            <p className="text-xs text-uppercase tracking-wider text-gray-500 dark:text-gray-400 font-semibold mb-1">SESSION TIME</p>
                            <p className="text-2xl font-bold text-gray-900 dark:text-white">
                                {Math.floor((usageData[0].session_time_seconds || 0) / 3600)}h {Math.floor(((usageData[0].session_time_seconds || 0) % 3600) / 60)}m
                            </p>
                        </div>
                    </div>
                ) : (
                    <div className="text-center py-8">
                        <p className="text-gray-500 dark:text-gray-400">No active session detected.</p>
                        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Connect to the network to see live stats.</p>
                    </div>
                )}
            </div>

            {/* Admin Actions */}
            {(user?.is_staff || user?.is_superuser) && (
                <div className="mt-8 pt-8 border-t border-gray-200 dark:border-gray-700">
                    <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Administration</h3>
                    <div className="grid md:grid-cols-3 gap-6">
                        <Link
                            to="/admin"
                            className="bg-gray-900 dark:bg-black text-white rounded-xl shadow-lg p-6 hover:bg-gray-800 dark:hover:bg-gray-900 transition group"
                        >
                            <div className="flex items-center gap-4">
                                <div className="w-12 h-12 bg-gray-800 dark:bg-gray-800 rounded-lg flex items-center justify-center group-hover:bg-gray-700 transition">
                                    <Activity className="w-6 h-6 text-blue-400" />
                                </div>
                                <div>
                                    <h4 className="font-semibold">Admin Dashboard</h4>
                                    <p className="text-sm text-gray-400">Manage ISP System</p>
                                </div>
                            </div>
                        </Link>
                    </div>
                </div>
            )}
        </div>
    );
}
