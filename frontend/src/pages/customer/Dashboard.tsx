import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { billingAPI, networkAPI } from '../../services/api';
import { format } from 'date-fns';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Wifi, Activity, RefreshCw, Wallet, ShieldCheck, Router } from 'lucide-react';

function greeting() {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good Morning';
    if (hour < 17) return 'Good Afternoon';
    return 'Good Evening';
}

export default function CustomerDashboard() {
    const { user } = useAuthStore();

    const { data: subscription, refetch: refetchSubscription, isFetching: statusRefreshing } = useQuery({
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

    const recentTransactions = transactions?.slice(0, 3) || [];

    // Live session, straight from the router -- refreshed every 5s. Byte
    // counters are cumulative session totals (that's all the router gives
    // us), so "current speed" is derived by diffing this poll against the
    // last one, not something the backend provides directly.
    const { data: liveSession } = useQuery({
        queryKey: ['my-session'],
        queryFn: async () => {
            const res = await networkAPI.getMySession();
            return res.data;
        },
        refetchInterval: 5000,
    });

    const [liveSpeed, setLiveSpeed] = useState<{ uploadKbps: number; downloadKbps: number } | null>(null);
    const prevSessionRef = useRef<{ upload_bytes: number; download_bytes: number; ts: number } | null>(null);

    // Rolling window of recent speed samples for the live chart -- 30
    // samples at one every 5s is 2.5 minutes of visible history.
    const MAX_TRAFFIC_SAMPLES = 30;
    const [trafficSamples, setTrafficSamples] = useState<{ time: string; download: number; upload: number }[]>([]);

    useEffect(() => {
        if (!liveSession?.active) {
            setLiveSpeed(null);
            setTrafficSamples([]);
            prevSessionRef.current = null;
            return;
        }
        const now = Date.now();
        const prev = prevSessionRef.current;
        if (prev) {
            const elapsedSec = (now - prev.ts) / 1000;
            if (elapsedSec > 0) {
                const uploadDelta = Math.max(0, liveSession.upload_bytes - prev.upload_bytes);
                const downloadDelta = Math.max(0, liveSession.download_bytes - prev.download_bytes);
                const uploadKbps = (uploadDelta * 8) / elapsedSec / 1024;
                const downloadKbps = (downloadDelta * 8) / elapsedSec / 1024;
                setLiveSpeed({ uploadKbps, downloadKbps });
                setTrafficSamples(samples => [
                    ...samples,
                    { time: format(new Date(now), 'HH:mm:ss'), download: Number(downloadKbps.toFixed(1)), upload: Number(uploadKbps.toFixed(1)) },
                ].slice(-MAX_TRAFFIC_SAMPLES));
            }
        }
        prevSessionRef.current = { upload_bytes: liveSession.upload_bytes, download_bytes: liveSession.download_bytes, ts: now };
    }, [liveSession]);

    // Daily-bucketed usage, computed client-side from real session records --
    // there's no separate pre-aggregated chart endpoint for a customer's own
    // usage (the admin one is staff-only), so this is built from the exact
    // same records shown on the /usage page.
    const dailyUsage = (() => {
        const byDay = new Map<string, { upload: number; download: number }>();
        for (const r of usageRecords || []) {
            const day = format(new Date(r.start_time), 'MMM d');
            const entry = byDay.get(day) || { upload: 0, download: 0 };
            entry.upload += Number(r.upload_bytes || 0) / (1024 ** 3);
            entry.download += Number(r.download_bytes || 0) / (1024 ** 3);
            byDay.set(day, entry);
        }
        return Array.from(byDay.entries())
            .map(([day, v]) => ({ day, upload: Number(v.upload.toFixed(2)), download: Number(v.download.toFixed(2)) }))
            .slice(-14);
    })();

    const credentialUsername = user?.pppoe_username || user?.hotspot_username || user?.username;
    const credentialPassword = user?.pppoe_password || user?.hotspot_password;

    return (
        <div>
            <h1 className="text-2xl font-bold text-gray-900 mb-6">Your Account Information</h1>

            <div className="grid md:grid-cols-4 gap-4 mb-6">
                <div className="bg-gradient-to-br from-blue-600 to-blue-700 rounded-2xl p-5 text-white">
                    <p className="text-blue-100 text-sm">{greeting()},</p>
                    <p className="text-xl font-bold mb-2">{user?.full_name || user?.username}</p>
                    <p className="text-blue-100 text-xs">Welcome to {user?.full_name ? 'your portal' : 'the portal'}</p>
                </div>

                <div className="bg-gray-900 rounded-2xl p-5 text-white">
                    <div className="flex items-center gap-2 text-gray-400 text-xs mb-2">
                        <Wallet className="h-3.5 w-3.5" /> Current Balance
                    </div>
                    <p className="text-2xl font-bold">KES {Number(user?.account_balance || 0).toLocaleString()}</p>
                </div>

                <div className="bg-gray-900 rounded-2xl p-5 text-white">
                    <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2 text-gray-400 text-xs">
                            <ShieldCheck className="h-3.5 w-3.5" /> Account Status
                        </div>
                        <button
                            onClick={() => refetchSubscription()}
                            disabled={statusRefreshing}
                            className="text-gray-400 hover:text-white disabled:opacity-50"
                            title="Refresh"
                        >
                            <RefreshCw className={`h-3.5 w-3.5 ${statusRefreshing ? 'animate-spin' : ''}`} />
                        </button>
                    </div>
                    <p className={`text-2xl font-bold capitalize ${user?.status === 'active' ? 'text-green-400' : 'text-amber-400'}`}>
                        {user?.status || 'Unknown'}
                    </p>
                </div>

                <div className="bg-gray-900 rounded-2xl p-5 text-white">
                    <div className="flex items-center gap-2 text-gray-400 text-xs mb-2">
                        <Wifi className="h-3.5 w-3.5" /> Current Plan
                    </div>
                    {subscription ? (
                        <>
                            <p className="text-lg font-bold truncate">{subscription.plan.name}</p>
                            <p className="text-gray-400 text-xs">{subscription.plan.download_speed}/{subscription.plan.upload_speed} Mbps</p>
                        </>
                    ) : (
                        <>
                            <p className="text-lg font-bold text-gray-400">No active plan</p>
                            <Link to="/plans" className="text-blue-400 text-xs font-semibold hover:text-blue-300">Browse plans &rarr;</Link>
                        </>
                    )}
                </div>
            </div>

            <div className="grid lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
                    <div className="flex items-center justify-between mb-2">
                        <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                            <Activity className="h-5 w-5 text-purple-600" /> Data Usage
                        </h3>
                        <Link to="/usage" className="text-sm text-blue-600 hover:text-blue-800">View all</Link>
                    </div>
                    <div className="flex items-center gap-4 mb-4 text-sm">
                        <span className={`flex items-center gap-1.5 font-medium ${liveSession?.active ? 'text-green-600' : 'text-gray-400'}`}>
                            <span className={`h-2 w-2 rounded-full ${liveSession?.active ? 'bg-green-500 animate-pulse' : 'bg-gray-300'}`} />
                            {liveSession?.active ? 'Online now' : 'Offline'}
                        </span>
                        {liveSession?.active && liveSpeed && (
                            <>
                                <span className="text-gray-500">&darr; {liveSpeed.downloadKbps.toFixed(0)} Kbps</span>
                                <span className="text-gray-500">&uarr; {liveSpeed.uploadKbps.toFixed(0)} Kbps</span>
                            </>
                        )}
                    </div>

                    {liveSession?.active && trafficSamples.length > 0 && (
                        <div className="h-40 mb-6">
                            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">Live Traffic</p>
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={trafficSamples}>
                                    <defs>
                                        <linearGradient id="liveDownloadGrad" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#14b8a6" stopOpacity={0.4} />
                                            <stop offset="95%" stopColor="#14b8a6" stopOpacity={0} />
                                        </linearGradient>
                                        <linearGradient id="liveUploadGrad" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <XAxis dataKey="time" tick={{ fontSize: 10 }} minTickGap={40} />
                                    <YAxis tick={{ fontSize: 10 }} unit=" Kbps" width={70} />
                                    <Tooltip formatter={(v: number) => `${v} Kbps`} />
                                    <Area type="monotone" dataKey="download" name="Download" stroke="#14b8a6" fill="url(#liveDownloadGrad)" isAnimationActive={false} />
                                    <Area type="monotone" dataKey="upload" name="Upload" stroke="#3b82f6" fill="url(#liveUploadGrad)" isAnimationActive={false} />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    )}

                    {dailyUsage.length > 0 ? (
                        <div className="h-72">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={dailyUsage}>
                                    <defs>
                                        <linearGradient id="uploadGrad" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.5} />
                                            <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
                                        </linearGradient>
                                        <linearGradient id="downloadGrad" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#2dd4bf" stopOpacity={0.5} />
                                            <stop offset="95%" stopColor="#2dd4bf" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                                    <YAxis tick={{ fontSize: 11 }} unit=" GB" />
                                    <Tooltip formatter={(v: number) => `${v} GB`} />
                                    <Area type="monotone" dataKey="upload" name="Upload" stroke="#3b82f6" fill="url(#uploadGrad)" />
                                    <Area type="monotone" dataKey="download" name="Download" stroke="#14b8a6" fill="url(#downloadGrad)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-72 flex items-center justify-center text-gray-400 text-sm">No usage recorded yet.</div>
                    )}
                </div>

                <div className="space-y-6">
                    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
                        <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2 mb-4">
                            <Router className="h-4 w-4 text-gray-500" /> Account Overview
                        </h3>
                        <dl className="space-y-3 text-sm">
                            <div className="flex justify-between">
                                <dt className="text-gray-500">Username</dt>
                                <dd className="font-medium text-gray-900">{credentialUsername || '-'}</dd>
                            </div>
                            {credentialPassword && (
                                <div className="flex justify-between">
                                    <dt className="text-gray-500">Password</dt>
                                    <dd className="font-mono font-medium text-gray-900">{credentialPassword}</dd>
                                </div>
                            )}
                            <div className="flex justify-between">
                                <dt className="text-gray-500">Balance</dt>
                                <dd className="font-medium text-gray-900">KES {Number(user?.account_balance || 0).toLocaleString()}</dd>
                            </div>
                            {subscription && (
                                <>
                                    <div className="flex justify-between">
                                        <dt className="text-gray-500">Plan</dt>
                                        <dd className="font-medium text-gray-900">{subscription.plan.name}</dd>
                                    </div>
                                    <div className="flex justify-between">
                                        <dt className="text-gray-500">Created On</dt>
                                        <dd className="font-medium text-gray-900">{format(new Date(subscription.created_at), 'MMM d, yyyy')}</dd>
                                    </div>
                                    <div className="flex justify-between">
                                        <dt className="text-gray-500">Expires On</dt>
                                        <dd className="font-medium text-gray-900">{format(new Date(subscription.expiry_date), 'MMM d, yyyy HH:mm')}</dd>
                                    </div>
                                </>
                            )}
                        </dl>
                        <Link
                            to="/plans"
                            className="mt-4 block text-center w-full bg-blue-600 text-white py-2 rounded-lg text-sm font-semibold hover:bg-blue-700"
                        >
                            Renew / Buy a Package
                        </Link>
                    </div>

                    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
                        <div className="flex items-center justify-between mb-3">
                            <h3 className="text-sm font-bold text-gray-900">Recent Transactions</h3>
                            <Link to="/orders" className="text-xs text-blue-600 hover:text-blue-800">View all</Link>
                        </div>
                        {recentTransactions.length > 0 ? (
                            <div className="space-y-3">
                                {recentTransactions.map((t: any) => (
                                    <div key={t.id} className="flex justify-between items-center text-sm border-t pt-2 first:border-t-0 first:pt-0">
                                        <div>
                                            <p className="font-medium text-gray-900">KES {Number(t.amount).toLocaleString()}</p>
                                            <p className="text-gray-500 text-xs uppercase">{t.payment_method}</p>
                                        </div>
                                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${t.status === 'completed' ? 'bg-green-100 text-green-800' :
                                            t.status === 'failed' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800'
                                            }`}>
                                            {t.status}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <p className="text-gray-400 text-sm">No transactions yet.</p>
                        )}
                    </div>
                </div>
            </div>

            {(user?.is_staff || user?.is_superuser) && (
                <div className="mt-6">
                    <Link
                        to="/admin"
                        className="inline-flex items-center gap-2 text-sm font-medium text-gray-700 hover:text-blue-600"
                    >
                        &rarr; Go to Admin Dashboard
                    </Link>
                </div>
            )}
        </div>
    );
}
