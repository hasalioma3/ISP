import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Trophy, Wifi } from 'lucide-react';
import { topHotspotUsers } from '../services/api';
import { EmptyState, Panel, PanelHeader, SegmentedControl, Skeleton } from './savanna';
import { cn } from '@/lib/utils';

type Row = {
    rank: number; customer_id: number; username: string; name: string; phone: string; mac_address: string;
    upload_gb: number; download_gb: number; total_gb: number; active_days: number; spent: number;
    purchases: number; current_plan: string; online: boolean;
};

const PERIODS = [
    { value: 'daily', label: 'Today' },
    { value: 'weekly', label: 'Week' },
    { value: 'monthly', label: 'Month' },
];

/**
 * The ten heaviest hotspot users (or biggest spenders) for today / this
 * week / this month. Usage counts only traffic on hotspot plans.
 */
export default function TopHotspotUsers({ className, defaultPeriod = 'weekly' }: { className?: string; defaultPeriod?: string }) {
    const [period, setPeriod] = useState(defaultPeriod);
    const [by, setBy] = useState<'data' | 'spend'>('data');
    const { data, isLoading } = useQuery({
        queryKey: ['top-hotspot-users', period, by],
        queryFn: async () => (await topHotspotUsers({ period, by })).data,
        refetchInterval: 60_000,
    });
    const rows: Row[] = data?.results || [];
    const max = Math.max(1, ...rows.map((r) => (by === 'data' ? r.total_gb : r.spent)));

    return (
        <Panel className={className}>
            <PanelHeader
                leading={<span className="grid h-9 w-9 place-items-center rounded-full bg-sunset/15 text-sunset"><Trophy className="h-4 w-4" /></span>}
                title="Top 10 hotspot users"
                subtitle={by === 'data' ? 'Most data used on hotspot plans' : 'Most spent on hotspot plans'}
                action={
                    <div className="flex flex-wrap items-center gap-2">
                        <SegmentedControl
                            options={[{ value: 'data', label: 'Data' }, { value: 'spend', label: 'Spend' }]}
                            value={by}
                            onChange={(v) => setBy(v as 'data' | 'spend')}
                            aria-label="Rank by"
                        />
                        <SegmentedControl options={PERIODS} value={period} onChange={setPeriod} aria-label="Period" />
                    </div>
                }
            />
            {isLoading ? (
                <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-11" />)}</div>
            ) : rows.length === 0 ? (
                <EmptyState message="No hotspot usage in this period yet." />
            ) : (
                <ol className="space-y-1.5">
                    {rows.map((r) => {
                        const value = by === 'data' ? r.total_gb : r.spent;
                        return (
                            <li key={r.customer_id} className="relative overflow-hidden rounded-xl border border-border-soft px-3 py-2">
                                <div className="absolute inset-y-0 left-0 bg-primary/[0.07]" style={{ width: `${(value / max) * 100}%` }} aria-hidden />
                                <div className="relative flex items-center gap-3">
                                    <span className={cn('grid h-7 w-7 shrink-0 place-items-center rounded-full text-[12px] font-bold',
                                        r.rank === 1 ? 'bg-sunset text-white' : r.rank <= 3 ? 'bg-primary/15 text-primary' : 'bg-chip text-muted-foreground')}>
                                        {r.rank}
                                    </span>
                                    <div className="min-w-0 flex-1">
                                        <p className="flex items-center gap-1.5 truncate text-[13.5px] font-semibold">
                                            {r.name}
                                            {r.online && <Wifi className="h-3.5 w-3.5 text-ok" aria-label="Online now" />}
                                        </p>
                                        <p className="truncate text-[12px] text-muted-foreground">
                                            {r.username !== r.name ? `${r.username} · ` : ''}{r.current_plan || 'No active plan'}
                                            {r.active_days ? ` · ${r.active_days} day${r.active_days === 1 ? '' : 's'} active` : ''}
                                        </p>
                                    </div>
                                    <div className="text-right">
                                        <p className="text-[14px] font-bold tabular-nums">
                                            {by === 'data' ? `${r.total_gb.toFixed(2)} GB` : `KES ${r.spent.toLocaleString()}`}
                                        </p>
                                        <p className="text-[11.5px] text-muted-foreground tabular-nums">
                                            {by === 'data'
                                                ? `↓${r.download_gb.toFixed(1)} ↑${r.upload_gb.toFixed(1)}`
                                                : `${r.purchases} purchase${r.purchases === 1 ? '' : 's'} · ${r.total_gb.toFixed(1)} GB`}
                                        </p>
                                    </div>
                                </div>
                            </li>
                        );
                    })}
                </ol>
            )}
        </Panel>
    );
}
