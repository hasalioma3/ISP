import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminAPI, analyticsAPI } from '../services/api';
import type { SiteHealth, Status } from '../components/savanna';

export interface Site extends SiteHealth {
    id: number;
    lastSeenAt?: string | null;
}

function formatThroughput(kbps: number | undefined): string | null {
    if (kbps == null) return null;
    if (kbps >= 1_000_000) return `${(kbps / 1_000_000).toFixed(1)} Gbps`;
    if (kbps >= 1000) return `${Math.round(kbps / 1000)} Mbps`;
    return `${Math.round(kbps)} Kbps`;
}

/**
 * Per-router "site" status for the dashboard and Subscribers pages:
 * session counts and last-known state from the DB-backed dashboard stats,
 * plus live CPU and WAN throughput from the 10s health poll. RouterOS only
 * reports cumulative WAN byte counters, so throughput is the difference
 * between two polls. Both queries share their cache keys with the
 * dashboard, so switching pages doesn't refetch.
 */
export function useSites() {
    const { data: stats, isLoading, isError, error } = useQuery({
        queryKey: ['admin-stats'],
        queryFn: async () => (await analyticsAPI.getDashboardStats()).data,
        refetchInterval: 30_000,
    });
    const { data: health, refetch, isFetching, dataUpdatedAt } = useQuery({
        queryKey: ['admin-router-health'],
        queryFn: async () => (await adminAPI.getRouterHealth()).data as Record<string, any>,
        refetchInterval: 10_000,
    });

    const [kbps, setKbps] = useState<Record<string, number>>({});
    const prev = useRef<Record<string, { rx: number; tx: number; ts: number }>>({});

    useEffect(() => {
        if (!health || !dataUpdatedAt) return;
        // Time the reading was fetched, not "now": on a fresh page the first
        // reading is React Query's cached copy, possibly minutes old, and
        // stamping it with the current time divided minutes of traffic by a
        // few seconds (e.g. 523 Mbps on an idle RB951).
        const ts = dataUpdatedAt;
        const next: Record<string, number> = {};
        for (const [id, h] of Object.entries(health)) {
            if (!h?.success) continue;
            const p = prev.current[id];
            // Same reading seen again (re-render / remount): nothing to diff.
            if (p && p.ts === ts) continue;
            // Readings < 3s apart give jumpy numbers; wait for the next one.
            if (p && ts - p.ts >= 3000) {
                const bytes = Math.max(0, h.wan_rx_bytes - p.rx) + Math.max(0, h.wan_tx_bytes - p.tx);
                next[id] = (bytes * 8) / ((ts - p.ts) / 1000) / 1000;
            } else if (p) {
                continue;
            }
            prev.current[id] = { rx: h.wan_rx_bytes, tx: h.wan_tx_bytes, ts };
        }
        setKbps((old) => ({ ...old, ...next }));
    }, [health, dataUpdatedAt]);

    const routers: any[] = stats?.routers || [];

    const sites: Site[] = useMemo(() => routers.map((r) => {
        const h = health?.[r.id];
        let status: Status = 'unknown';
        if (h?.success) status = (h.cpu_load ?? 0) > 60 ? 'degraded' : 'online';
        else if (h && !h.success) status = 'offline';
        else if (r.is_online === true) status = 'online';
        else if (r.is_online === false) status = 'offline';
        return {
            id: r.id,
            name: r.name,
            model: h?.board_name || h?.last_health?.board_name || r.board_name,
            clients: r.online ?? 0,
            status,
            cpu: h?.success ? h.cpu_load : null,
            throughput: status === 'offline' ? null : formatThroughput(kbps[r.id]),
            lastSeenAt: h?.last_seen_at || r.last_seen_at,
        };
    }), [routers, health, kbps]);

    return { sites, stats, health, isLoading, isError, error, refetchHealth: refetch, healthFetching: isFetching };
}
