import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminAPI } from '../services/api';
import { StatusBadge } from './savanna';

const POLL_MS = 3000;
const MAX_POINTS = 40; // ~2 minutes

interface Point { down: number; up: number } // kbps

function rate(kbps: number) {
    return kbps >= 1000 ? `${(kbps / 1000).toFixed(1)} Mbps` : `${Math.round(kbps)} Kbps`;
}

/** Two-line inline SVG chart (download solid, upload dashed); no chart library needed. */
function MiniChart({ points }: { points: Point[] }) {
    const w = 600, h = 120;
    const max = Math.max(1, ...points.flatMap((p) => [p.down, p.up]));
    const path = (key: keyof Point) => points
        .map((p, i) => `${i ? 'L' : 'M'}${((i / Math.max(1, MAX_POINTS - 1)) * w).toFixed(1)} ${(h - 6 - (p[key] / max) * (h - 12)).toFixed(1)}`)
        .join(' ');
    return (
        <svg viewBox={`0 0 ${w} ${h}`} className="h-28 w-full" preserveAspectRatio="none" aria-hidden="true">
            <line x1="0" x2={w} y1={h - 6} y2={h - 6} stroke="var(--sv-border)" />
            {points.length > 1 && <path d={path('down')} fill="none" stroke="var(--sv-primary)" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />}
            {points.length > 1 && <path d={path('up')} fill="none" stroke="var(--sv-accent)" strokeWidth="2" strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />}
        </svg>
    );
}

/**
 * Live view of one subscriber's traffic for the admin Usage tab. Polls their
 * session on the router every 3s while open; the router only reports
 * cumulative byte counters, so speed = difference between two readings over
 * the time between them (timed by when each reading was fetched).
 */
export default function LiveActivity({ customerId }: { customerId: number }) {
    const { data, dataUpdatedAt, isLoading } = useQuery({
        queryKey: ['subscriber-live', customerId],
        queryFn: async () => (await adminAPI.getSubscriberLive(customerId)).data,
        refetchInterval: POLL_MS,
        gcTime: 0,
    });
    const [points, setPoints] = useState<Point[]>([]);
    const prev = useRef<{ up: number; down: number; ts: number } | null>(null);

    useEffect(() => {
        if (!data || !dataUpdatedAt) return;
        if (!data.active) { prev.current = null; return; }
        const p = prev.current;
        const cur = { up: Number(data.upload_bytes) || 0, down: Number(data.download_bytes) || 0, ts: dataUpdatedAt };
        if (p && cur.ts > p.ts) {
            const secs = (cur.ts - p.ts) / 1000;
            // Counters drop to 0 when a new session starts: skip that reading.
            if (cur.up >= p.up && cur.down >= p.down) {
                setPoints((pts) => [...pts, {
                    down: ((cur.down - p.down) * 8) / secs / 1000,
                    up: ((cur.up - p.up) * 8) / secs / 1000,
                }].slice(-MAX_POINTS));
            }
        }
        if (!p || cur.ts !== p.ts) prev.current = cur;
    }, [data, dataUpdatedAt]);

    const latest = points[points.length - 1];

    return (
        <div className="rounded-2xl border border-border p-4 mb-6">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <div>
                    <p className="text-sm font-bold text-foreground">Live activity</p>
                    <p className="text-xs text-muted-foreground">From {data?.router || 'their router'}, every {POLL_MS / 1000} s while this tab is open</p>
                </div>
                {isLoading ? null : data?.active
                    ? <StatusBadge status="online" />
                    : <StatusBadge status={data?.router_offline ? 'offline' : 'inactive'} label={data?.router_offline ? 'Router offline' : 'Not connected'} />}
            </div>

            {data?.active ? (
                <>
                    <div className="flex flex-wrap gap-x-8 gap-y-1 text-sm mb-1">
                        <span><span className="inline-block h-2 w-3 rounded-full bg-primary mr-1.5 align-middle" />Download <strong className="num">{latest ? rate(latest.down) : '…'}</strong></span>
                        <span><span className="inline-block h-0.5 w-3 bg-sunset mr-1.5 align-middle" />Upload <strong className="num">{latest ? rate(latest.up) : '…'}</strong></span>
                    </div>
                    <MiniChart points={points} />
                    <dl className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                        <div><dt className="text-muted-foreground">IP address</dt><dd className="num font-medium">{data.address || '—'}</dd></div>
                        <div><dt className="text-muted-foreground">MAC</dt><dd className="num font-medium">{data.mac_address || '—'}</dd></div>
                        <div><dt className="text-muted-foreground">Session uptime</dt><dd className="num font-medium">{data.uptime || '—'}</dd></div>
                        <div><dt className="text-muted-foreground">Connection</dt><dd className="font-medium uppercase">{data.session_type || data.service_type}</dd></div>
                    </dl>
                </>
            ) : (
                <p className="text-sm text-muted-foreground py-3">
                    {isLoading ? 'Checking their router…' : data?.reason || 'Not connected right now.'}
                </p>
            )}
        </div>
    );
}
