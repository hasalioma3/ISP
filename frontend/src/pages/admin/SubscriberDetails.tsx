import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminAPI } from '../../services/api'; // Fix import path
import { useParams, Link } from 'react-router-dom';
import {
    Activity,
    ArrowLeft,
    Calendar,
    Wifi,
    Shield,
    CreditCard,
    Clock,
    Download,
    Upload
} from 'lucide-react';
import { format } from 'date-fns';

export default function SubscriberDetails() {
    const { id } = useParams<{ id: string }>();

    const { data: customer, isLoading, isError } = useQuery({
        queryKey: ['subscriber', id],
        queryFn: async () => {
            const response = await adminAPI.getSubscriber(id!);
            return response.data;
        },
        enabled: !!id,
        refetchInterval: 5000, // Poll update usage stats live-ish
    });

    if (isLoading) {
        return (
            <div className="flex justify-center items-center min-h-screen">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
            </div>
        );
    }

    if (isError || !customer) {
        return (
            <div className="p-8 text-center text-red-600">
                <h2 className="text-xl font-bold">Error loading subscriber details.</h2>
                <Link to="/admin/subscribers" className="text-indigo-600 mt-4 block hover:underline">
                    Back to Subscribers
                </Link>
            </div>
        );
    }

    const { usage_summary } = customer;

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-8">
            {/* Header */}
            <div className="flex items-center gap-4">
                <Link
                    to="/admin/subscribers"
                    className="p-2 bg-white rounded-full shadow hover:bg-gray-50 transition"
                >
                    <ArrowLeft className="w-6 h-6 text-gray-600" />
                </Link>
                <div>
                    <h1 className="text-3xl font-bold text-gray-900">{customer.full_name || customer.username}</h1>
                    <div className="flex gap-2 text-sm text-gray-500 mt-1">
                        <span>@{customer.username}</span>
                        <span>•</span>
                        <span>{customer.phone_number}</span>
                    </div>
                </div>
                <div className="ml-auto flex items-center gap-2">
                    <span className={`px-3 py-1 rounded-full text-sm font-medium ${customer.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                        }`}>
                        {customer.status?.toUpperCase()}
                    </span>
                </div>
            </div>

            {/* Top Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

                {/* 1. Current Plan */}
                <div className="bg-white rounded-2xl shadow-sm p-6 border border-gray-100">
                    <div className="flex items-center gap-3 mb-4">
                        <Shield className="w-5 h-5 text-indigo-600" />
                        <h2 className="text-lg font-bold text-gray-900">Current Plan</h2>
                    </div>
                    {customer.current_subscription ? (
                        <div className="space-y-4">
                            <div>
                                <p className="text-sm text-gray-500">Plan Name</p>
                                <p className="text-xl font-bold text-gray-900">
                                    {customer.current_subscription.plan_name}
                                </p>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <p className="text-sm text-gray-500">Expires On</p>
                                    <p className="font-medium text-gray-900">
                                        {format(new Date(customer.current_subscription.expiry_date), 'MMM dd, yyyy')}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-sm text-gray-500">Status</p>
                                    <p className={`font-medium ${customer.current_subscription.status === 'active'
                                            ? 'text-green-600'
                                            : 'text-red-500'
                                        }`}>
                                        {customer.current_subscription.status}
                                    </p>
                                </div>
                            </div>
                            {customer.current_subscription.status === 'active' && (
                                <div className="mt-2 bg-indigo-50 text-indigo-700 px-3 py-2 rounded-lg text-sm font-medium text-center">
                                    {customer.current_subscription.days_remaining} Days Remaining
                                </div>
                            )}
                        </div>
                    ) : (
                        <p className="text-gray-500 italic">No active subscription</p>
                    )}
                </div>

                {/* 2. Network Activity (Realtime) */}
                <div className="col-span-1 md:col-span-2 bg-white rounded-2xl shadow-sm p-6 border border-gray-100">
                    <div className="flex items-center gap-3 mb-6">
                        <Wifi className="w-5 h-5 text-blue-600" />
                        <h2 className="text-lg font-bold text-gray-900">Live Network Activity</h2>
                    </div>
                    {usage_summary ? (
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                            <div className="bg-blue-50 p-4 rounded-xl">
                                <p className="text-xs font-semibold text-blue-600 uppercase tracking-wide">Download</p>
                                <div className="mt-2 flex items-baseline gap-1">
                                    <span className="text-2xl font-bold text-gray-900">
                                        {usage_summary.download_speed_mbps}
                                    </span>
                                    <span className="text-sm text-gray-500">Mbps</span>
                                </div>
                            </div>
                            <div className="bg-green-50 p-4 rounded-xl">
                                <p className="text-xs font-semibold text-green-600 uppercase tracking-wide">Upload</p>
                                <div className="mt-2 flex items-baseline gap-1">
                                    <span className="text-2xl font-bold text-gray-900">
                                        {usage_summary.upload_speed_mbps}
                                    </span>
                                    <span className="text-sm text-gray-500">Mbps</span>
                                </div>
                            </div>
                            <div className="bg-purple-50 p-4 rounded-xl">
                                <p className="text-xs font-semibold text-purple-600 uppercase tracking-wide">Total Usage</p>
                                <div className="mt-2 flex items-baseline gap-1">
                                    <span className="text-2xl font-bold text-gray-900">
                                        {usage_summary.total_gb}
                                    </span>
                                    <span className="text-sm text-gray-500">GB</span>
                                </div>
                            </div>
                            <div className="bg-orange-50 p-4 rounded-xl">
                                <p className="text-xs font-semibold text-orange-600 uppercase tracking-wide">Session</p>
                                <div className="mt-2 text-xl font-bold text-gray-900">
                                    {Math.floor(usage_summary.session_time_seconds / 3600)}h {Math.floor((usage_summary.session_time_seconds % 3600) / 60)}m
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="flex flex-col items-center justify-center h-40 bg-gray-50 rounded-xl border border-dashed border-gray-200">
                            <Wifi className="w-8 h-8 text-gray-300 mb-2" />
                            <p className="text-gray-400">No active session</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Subscription History Table */}
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
                <div className="p-6 border-b border-gray-100 flex items-center gap-3">
                    <Clock className="w-5 h-5 text-gray-500" />
                    <h2 className="text-lg font-bold text-gray-900">Recent Subscriptions</h2>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm text-gray-600">
                        <thead className="bg-gray-50 text-gray-700 font-semibold">
                            <tr>
                                <th className="px-6 py-4">Start Date</th>
                                <th className="px-6 py-4">Plan</th>
                                <th className="px-6 py-4">Amount</th>
                                <th className="px-6 py-4">Payment</th>
                                <th className="px-6 py-4">Status</th>
                                <th className="px-6 py-4">Expiry</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                            {customer.subscription_history && customer.subscription_history.length > 0 ? (
                                customer.subscription_history.map((sub: any) => (
                                    <tr key={sub.id} className="hover:bg-gray-50 transition">
                                        <td className="px-6 py-4">
                                            {format(new Date(sub.start_date), 'MMM dd, yyyy HH:mm')}
                                        </td>
                                        <td className="px-6 py-4 font-medium text-gray-900">{sub.plan_name}</td>
                                        <td className="px-6 py-4">
                                            {sub.amount > 0 ? `KES ${sub.amount}` : '-'}
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex flex-col">
                                                <span className="capitalize">{sub.payment_method}</span>
                                                {sub.mpesa_receipt && (
                                                    <span className="text-xs text-gray-400">{sub.mpesa_receipt}</span>
                                                )}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className={`inline-flex px-2 py-1 text-xs rounded-full font-medium ${sub.status === 'active' ? 'bg-green-100 text-green-700' :
                                                    sub.status === 'expired' ? 'bg-gray-100 text-gray-600' :
                                                        'bg-yellow-100 text-yellow-700'
                                                }`}>
                                                {sub.status.toUpperCase()}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4">
                                            {format(new Date(sub.expiry_date), 'MMM dd, yyyy')}
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td colSpan={6} className="px-6 py-8 text-center text-gray-400">
                                        No subscription history found for this user.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
