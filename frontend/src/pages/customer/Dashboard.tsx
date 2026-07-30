import { useQuery } from '@tanstack/react-query';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { billingAPI } from '../../services/api';
import { format, formatDistanceToNow } from 'date-fns';
import { Wifi, CreditCard, Activity, LogOut, User, Receipt } from 'lucide-react';

export default function CustomerDashboard() {
    const navigate = useNavigate();
    const { user, logout } = useAuthStore();
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

    const { data: usageRecords } = useQuery({
        queryKey: ['dashboard-usage'],
        queryFn: async () => {
            const response = await billingAPI.getUsage();
            return response.data.results || response.data;
        },
    });

    const { data: transactions } = useQuery({
        queryKey: ['dashboard-transactions'],
        queryFn: async () => {
            const response = await billingAPI.getTransactions();
            return response.data.results || response.data;
        },
    });

    const recentUsage = usageRecords?.slice(0, 5) || [];
    const usageTotalGb = (usageRecords || []).reduce((sum: number, r: any) => sum + Number(r.total_gb || 0), 0);
    const recentTransactions = transactions?.slice(0, 5) || [];

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    return (
        <div className="min-h-screen bg-gray-50">
            {/* Header */}
            <div className="bg-white shadow">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
                    <div className="flex justify-between items-center">
                        <h1 className="text-2xl font-bold text-gray-900">ISP Dashboard</h1>
                        <button
                            onClick={handleLogout}
                            className="flex items-center gap-2 text-gray-600 hover:text-gray-900"
                        >
                            <LogOut className="w-5 h-5" />
                            Logout
                        </button>
                    </div>
                </div>
            </div>

            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {/* Welcome Section */}
                <div className="bg-gradient-to-r from-blue-600 to-purple-600 rounded-2xl p-8 text-white mb-8">
                    <div className="flex items-center gap-4 mb-4">
                        <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center">
                            <User className="w-8 h-8" />
                        </div>
                        <div>
                            <h2 className="text-3xl font-bold">Welcome, {user?.full_name || user?.username}!</h2>
                            <p className="text-blue-100">Account Status: <span className="font-semibold">{user?.status}</span></p>
                        </div>
                    </div>
                </div>

                {/* Subscription Card */}
                {subscription ? (
                    <div className="bg-white rounded-2xl shadow-lg p-6 mb-8">
                        <h3 className="text-xl font-bold text-gray-900 mb-4">Current Subscription</h3>
                        <div className="grid md:grid-cols-2 gap-6">
                            <div>
                                <p className="text-sm text-gray-600 mb-1">Plan</p>
                                <p className="text-2xl font-bold text-blue-600">{subscription.plan.name}</p>
                                <p className="text-gray-600 mt-2">{subscription.plan.download_speed}/{subscription.plan.upload_speed} Mbps</p>
                            </div>
                            <div>
                                <p className="text-sm text-gray-600 mb-1">Expires</p>
                                <p className="text-lg font-semibold text-gray-900">
                                    {formatDistanceToNow(new Date(subscription.expiry_date), { addSuffix: true })}
                                </p>
                                <p className="text-sm text-gray-600 mt-1">
                                    {new Date(subscription.expiry_date).toLocaleDateString()}
                                </p>
                            </div>
                        </div>

                        {subscription.days_remaining <= 3 && (
                            <div className="mt-4 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                                <p className="text-yellow-800 font-semibold">⚠️ Your subscription is expiring soon!</p>
                                <Link to="/plans" className="text-yellow-900 underline">Renew now</Link>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="bg-white rounded-2xl shadow-lg p-8 mb-8 text-center">
                        <Wifi className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                        <h3 className="text-xl font-bold text-gray-900 mb-2">No Active Subscription</h3>
                        <p className="text-gray-600 mb-4">Subscribe to a plan to get started</p>
                        <Link
                            to="/plans"
                            className="inline-block bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold hover:bg-blue-700"
                        >
                            View Plans
                        </Link>
                    </div>
                )}

                {/* Usage Stats & Recent Transactions */}
                <div className="grid md:grid-cols-2 gap-6 mb-8">
                    <div className="bg-white rounded-2xl shadow-lg p-6">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                                <Activity className="w-5 h-5 text-purple-600" />
                                Usage Stats
                            </h3>
                            <Link to="/usage" className="text-sm text-blue-600 hover:text-blue-800">View all</Link>
                        </div>
                        {recentUsage.length > 0 ? (
                            <>
                                <p className="text-sm text-gray-600 mb-1">Data used (recent sessions)</p>
                                <p className="text-3xl font-bold text-purple-600 mb-4">{usageTotalGb.toFixed(2)} GB</p>
                                <div className="space-y-2">
                                    {recentUsage.map((r: any) => (
                                        <div key={r.id} className="flex justify-between text-sm border-t pt-2">
                                            <span className="text-gray-600">{format(new Date(r.start_time), 'MMM d, HH:mm')}</span>
                                            <span className="font-medium text-gray-900">{r.total_gb} GB</span>
                                        </div>
                                    ))}
                                </div>
                            </>
                        ) : (
                            <p className="text-gray-500 text-sm">No usage recorded yet.</p>
                        )}
                    </div>

                    <div className="bg-white rounded-2xl shadow-lg p-6">
                        <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2 mb-4">
                            <Receipt className="w-5 h-5 text-green-600" />
                            Recent Transactions
                        </h3>
                        {recentTransactions.length > 0 ? (
                            <div className="space-y-2">
                                {recentTransactions.map((t: any) => (
                                    <div key={t.id} className="flex justify-between items-center text-sm border-t pt-2">
                                        <div>
                                            <p className="font-medium text-gray-900">KES {Number(t.amount).toLocaleString()}</p>
                                            <p className="text-gray-500 uppercase text-xs">
                                                {t.payment_method}{t.mpesa_receipt_number ? ` · ${t.mpesa_receipt_number}` : ''}
                                            </p>
                                        </div>
                                        <div className="text-right">
                                            <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium capitalize ${t.status === 'completed' ? 'bg-green-100 text-green-800' :
                                                t.status === 'failed' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800'
                                                }`}>
                                                {t.status}
                                            </span>
                                            <p className="text-gray-500 text-xs mt-1">{format(new Date(t.created_at), 'MMM d, yyyy')}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <p className="text-gray-500 text-sm">No transactions yet.</p>
                        )}
                    </div>
                </div>

                {/* Quick Actions */}
                <div className="grid md:grid-cols-3 gap-6">
                    <Link
                        to="/plans"
                        className="bg-white rounded-xl shadow-lg p-6 hover:shadow-xl transition group"
                    >
                        <div className="flex items-center gap-4">
                            <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center group-hover:bg-blue-200 transition">
                                <Wifi className="w-6 h-6 text-blue-600" />
                            </div>
                            <div>
                                <h4 className="font-semibold text-gray-900">View Plans</h4>
                                <p className="text-sm text-gray-600">Browse packages</p>
                            </div>
                        </div>
                    </Link>

                    <Link
                        to="/payment"
                        className="bg-white rounded-xl shadow-lg p-6 hover:shadow-xl transition group"
                    >
                        <div className="flex items-center gap-4">
                            <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center group-hover:bg-green-200 transition">
                                <CreditCard className="w-6 h-6 text-green-600" />
                            </div>
                            <div>
                                <h4 className="font-semibold text-gray-900">Make Payment</h4>
                                <p className="text-sm text-gray-600">Pay via M-Pesa</p>
                            </div>
                        </div>
                    </Link>

                    <Link
                        to="/usage"
                        className="bg-white rounded-xl shadow-lg p-6 hover:shadow-xl transition group"
                    >
                        <div className="flex items-center gap-4">
                            <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center group-hover:bg-purple-200 transition">
                                <Activity className="w-6 h-6 text-purple-600" />
                            </div>
                            <div>
                                <h4 className="font-semibold text-gray-900">Usage Stats</h4>
                                <p className="text-sm text-gray-600">View consumption</p>
                            </div>
                        </div>
                    </Link>
                </div>

                {/* Admin Actions */}
                {(user?.is_staff || user?.is_superuser) && (
                    <div className="mt-8 pt-8 border-t border-gray-200">
                        <h3 className="text-lg font-bold text-gray-900 mb-4">Administration</h3>
                        <div className="grid md:grid-cols-3 gap-6">
                            <Link
                                to="/admin"
                                className="bg-gray-800 text-white rounded-xl shadow-lg p-6 hover:bg-gray-700 transition group"
                            >
                                <div className="flex items-center gap-4">
                                    <div className="w-12 h-12 bg-gray-700 rounded-lg flex items-center justify-center group-hover:bg-gray-600 transition">
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
        </div>
    );
}
