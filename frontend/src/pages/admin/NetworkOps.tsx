import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { analyticsAPI, adminAPI } from '../../services/api';
import { Activity, Calendar, Gauge, TrendingDown, Users2 } from 'lucide-react';
import { format } from 'date-fns';
import { useAuthStore } from '../../store/authStore';

const PERIODS = [
    { key: 'live', label: 'Live' },
    { key: 'daily', label: 'Daily' },
    { key: 'weekly', label: 'Weekly' },
    { key: 'monthly', label: 'Monthly' },
] as const;

const LIVE_POLL_MS = 3000;
const LIVE_MAX_POINTS = 60;

type LivePoint = { time: string; down_mbps: number; up_mbps: number };

const CHURN_WINDOWS = [7, 14, 30] as const;

export default function NetworkOps() {
    const user = useAuthStore((state) => state.user);
    const canSeeChurn = !!user?.is_superuser || user?.role === 'admin' || user?.role === 'sales';

    const [routerId, setRouterId] = useState('');
    const [period, setPeriod] = useState<typeof PERIODS[number]['key']>('live');
    const isLive = period === 'live';
    const [date] = useState(format(new Date(), 'yyyy-MM-dd'));
    const [churnDays, setChurnDays] = useState<typeof CHURN_WINDOWS[number]>(30);

    const { data: routers } = useQuery({
        queryKey: ['routers'],
        queryFn: async () => {
            const res = await adminAPI.getRouters();
            return res.data.results || res.data;
        },
    });

    const { data: trend, isLoading: trendLoading } = useQuery({
        queryKey: ['router-bandwidth-trend', routerId, period, date],
        queryFn: async () => {
            const res = await analyticsAPI.getRouterBandwidthTrend({ router: Number(routerId), period, date });
            return res.data;
        },
        enabled: !!routerId && !isLive,
    });

    // Live mode: WAN byte counters are cumulative, so throughput is the diff between polls.
    const [livePoints, setLivePoints] = useState<LivePoint[]>([]);
    const prevLiveRef = useRef<{ rx: number; tx: number; ts: number } | null>(null);

    useEffect(() => {
        setLivePoints([]);
        prevLiveRef.current = null;
    }, [routerId, isLive]);

    const { data: liveHealth } = useQuery({
        queryKey: ['router-live-health', routerId],
        queryFn: async () => {
            const res = await adminAPI.getRouterHealth(Number(routerId));
            return res.data[routerId] as any;
        },
        enabled: !!routerId && isLive,
        refetchInterval: LIVE_POLL_MS,
        gcTime: 0,
    });

    useEffect(() => {
        if (!liveHealth?.success) return;
        const now = Date.now();
        const prev = prevLiveRef.current;
        prevLiveRef.current = { rx: liveHealth.wan_rx_bytes, tx: liveHealth.wan_tx_bytes, ts: now };
        if (!prev) return;
        const elapsedSec = (now - prev.ts) / 1000;
        if (elapsedSec <= 0) return;
        const toMbps = (delta: number) => Math.round((Math.max(0, delta) * 8) / elapsedSec / 1_000_000 * 100) / 100;
        const point: LivePoint = {
            time: format(new Date(now), 'HH:mm:ss'),
            down_mbps: toMbps(liveHealth.wan_rx_bytes - prev.rx),
            up_mbps: toMbps(liveHealth.wan_tx_bytes - prev.tx),
        };
        setLivePoints((pts) => [...pts, point].slice(-LIVE_MAX_POINTS));
    }, [liveHealth]);

    const latestLive = livePoints[livePoints.length - 1];

    const { data: churn, isLoading: churnLoading } = useQuery({
        queryKey: ['churn-forecast', churnDays],
        queryFn: async () => {
            const res = await analyticsAPI.getChurnForecast(churnDays);
            return res.data;
        },
        enabled: canSeeChurn,
    });

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">Network Ops</h1>

            {/* Router Bandwidth Trend */}
            <div className="bg-card rounded-2xl shadow-sm border border-border overflow-hidden">
                <div className="bg-primary px-6 py-4 flex items-center text-white font-bold">
                    <Activity className="h-5 w-5 mr-2" /> Router Bandwidth Trend
                </div>

                <div className="flex flex-wrap items-center gap-3 p-6 border-b">
                    <select
                        value={routerId}
                        onChange={(e) => setRouterId(e.target.value)}
                        className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    >
                        <option value="">Select a router...</option>
                        {routers?.map((r: any) => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </select>
                    <div className="flex border rounded-lg overflow-hidden">
                        {PERIODS.map((p) => (
                            <button
                                key={p.key}
                                onClick={() => setPeriod(p.key)}
                                className={`flex items-center px-3 py-2 text-sm font-medium transition-colors ${period === p.key
                                    ? 'bg-primary/10 text-primary'
                                    : 'text-muted-foreground hover:bg-secondary'
                                    }`}
                            >
                                <Calendar className="h-3.5 w-3.5 mr-1.5" /> {p.label}
                            </button>
                        ))}
                    </div>
                    {isLive && routerId ? (
                        <span className="text-sm text-muted-foreground">
                            Now: <strong className="text-foreground">{latestLive ? `${latestLive.down_mbps} down / ${latestLive.up_mbps} up Mbps` : 'measuring...'}</strong>
                            {' '}(WAN, every {LIVE_POLL_MS / 1000}s)
                        </span>
                    ) : trend?.router && (
                        <span className="text-sm text-muted-foreground">
                            Peak: <strong className="text-foreground">{trend.peak_mbps} Mbps</strong>
                            {trend.router.uplink_mbps ? ` of ${trend.router.uplink_mbps} Mbps capacity` : ' (no capacity set)'}
                        </span>
                    )}
                </div>

                <div className="p-6">
                    {!routerId ? (
                        <div className="h-72 flex items-center justify-center text-muted-foreground text-sm">
                            Select a router to see its bandwidth trend.
                        </div>
                    ) : isLive ? (
                        livePoints.length === 0 ? (
                            <div className="h-72 flex items-center justify-center text-muted-foreground text-sm">Collecting live data...</div>
                        ) : (
                            <div className="h-72">
                                <ResponsiveContainer width="100%" height="100%">
                                    <AreaChart data={livePoints} margin={{ left: 0, right: 10 }}>
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                                        <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${v} Mbps`} />
                                        <Tooltip formatter={(v) => `${v} Mbps`} />
                                        <Area type="monotone" dataKey="down_mbps" stroke="#7c3aed" fill="#c4b5fd" name="Download" isAnimationActive={false} />
                                        <Area type="monotone" dataKey="up_mbps" stroke="#0ea5e9" fill="#bae6fd" name="Upload" isAnimationActive={false} />
                                    </AreaChart>
                                </ResponsiveContainer>
                            </div>
                        )
                    ) : trendLoading ? (
                        <div className="h-72 flex items-center justify-center text-muted-foreground text-sm">Loading...</div>
                    ) : (trend?.series?.length ?? 0) === 0 ? (
                        <div className="h-72 flex items-center justify-center text-muted-foreground text-sm">No usage recorded for this period.</div>
                    ) : (
                        <div className="h-72">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={trend.series} margin={{ left: 0, right: 10 }}>
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${v} Mbps`} />
                                    <Tooltip formatter={(v: number) => `${v} Mbps`} />
                                    <Area type="monotone" dataKey="avg_mbps" stroke="#7c3aed" fill="#c4b5fd" name="Avg Mbps" />
                                    {trend.router?.uplink_mbps && (
                                        <ReferenceLine
                                            y={trend.router.uplink_mbps}
                                            stroke="#ef4444"
                                            strokeDasharray="4 4"
                                            label={{ value: 'Capacity', position: 'insideTopRight', fontSize: 11, fill: '#ef4444' }}
                                        />
                                    )}
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    )}
                    {!isLive && trend?.caveat && (
                        <p className="text-xs text-muted-foreground mt-3 flex items-start gap-1.5">
                            <Gauge className="h-3.5 w-3.5 shrink-0 mt-0.5" /> {trend.caveat}
                        </p>
                    )}
                </div>
            </div>

            {/* Churn / Expiry Forecast -- admin/sales only */}
            {canSeeChurn && (
                <div className="bg-card rounded-2xl shadow-sm border border-border overflow-hidden">
                    <div className="bg-primary px-6 py-4 flex items-center text-white font-bold">
                        <TrendingDown className="h-5 w-5 mr-2" /> Churn &amp; Expiry Forecast
                    </div>

                    <div className="flex flex-wrap items-center gap-2 p-6 border-b">
                        <span className="text-sm text-muted-foreground mr-1">Window:</span>
                        {CHURN_WINDOWS.map((d) => (
                            <button
                                key={d}
                                onClick={() => setChurnDays(d)}
                                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${churnDays === d
                                    ? 'bg-primary text-white'
                                    : 'bg-gray-100 text-foreground/80 hover:bg-gray-200'
                                    }`}
                            >
                                {d} days
                            </button>
                        ))}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 p-6">
                        <div className="border-l-4 border-l-amber-500 bg-secondary rounded-r-lg px-4 py-3">
                            <p className="text-xl font-bold text-foreground">{churn?.expiring_count ?? '-'}</p>
                            <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1">Expiring in {churnDays} days</p>
                        </div>
                        <div className="border-l-4 border-l-emerald-500 bg-secondary rounded-r-lg px-4 py-3">
                            <p className="text-xl font-bold text-foreground">
                                {churn?.renewal_rate?.renewal_rate_pct ?? 'N/A'}{churn?.renewal_rate?.renewal_rate_pct != null ? '%' : ''}
                            </p>
                            <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1">Renewal rate ({churnDays}d+ lapsed)</p>
                        </div>
                        <div className="border-l-4 border-l-purple-500 bg-secondary rounded-r-lg px-4 py-3">
                            <p className="text-xl font-bold text-foreground">{churn?.renewal_rate?.lapsed_count ?? '-'}</p>
                            <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1">Lapsed subscriptions</p>
                        </div>
                    </div>

                    <div className="overflow-x-auto border-t">
                        <table className="min-w-full divide-y divide-border">
                            <thead className="bg-secondary">
                                <tr>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
                                        <Users2 className="h-3.5 w-3.5 inline mr-1" /> Customer
                                    </th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Plan</th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Expires</th>
                                    <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Days Left</th>
                                </tr>
                            </thead>
                            <tbody className="bg-card divide-y divide-border">
                                {churnLoading ? (
                                    <tr><td colSpan={4} className="text-center py-8 text-muted-foreground">Loading...</td></tr>
                                ) : (churn?.expiring?.length ?? 0) === 0 ? (
                                    <tr><td colSpan={4} className="text-center py-8 text-muted-foreground">Nothing expiring in this window.</td></tr>
                                ) : churn?.expiring?.map((s: any) => (
                                    <tr key={`${s.username}-${s.expires_on}`} className="hover:bg-secondary">
                                        <td className="px-6 py-3 text-sm font-medium text-foreground">{s.username}</td>
                                        <td className="px-6 py-3 text-sm text-muted-foreground">{s.plan}</td>
                                        <td className="px-6 py-3 text-sm text-muted-foreground">{format(new Date(s.expires_on), 'MMM d, yyyy')}</td>
                                        <td className="px-6 py-3 text-sm text-right text-foreground">{s.days_left}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}
