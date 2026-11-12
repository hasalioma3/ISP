import type { LucideIcon } from 'lucide-react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Skeleton } from './Panel';

/**
 * Tiny trend line. Plain SVG rather than Recharts so it costs nothing to
 * render four of them in a row; the last point is the one that matters.
 */
export function Sparkline({ values, className, stroke = 'currentColor' }: { values: number[]; className?: string; stroke?: string }) {
    if (values.length < 2) return null;
    const w = 128;
    const h = 40;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const points = values.map((v, i) => [
        (i / (values.length - 1)) * w,
        h - 4 - ((v - min) / span) * (h - 8),
    ]);
    const d = points.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
    return (
        <svg viewBox={`0 0 ${w} ${h}`} className={cn('h-10 w-32', className)} fill="none" aria-hidden="true">
            <path d={d} stroke={stroke} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}

interface KpiCardProps {
    label: string;
    value: React.ReactNode;
    unit?: string;
    icon?: LucideIcon;
    /** Signed change; positive renders green ↑, negative red ↓. */
    delta?: { value: React.ReactNode; direction: 'up' | 'down' } | null;
    footnote?: React.ReactNode;
    sparkline?: number[];
    /** Orange hero variant (first KPI on the dashboard). */
    highlight?: boolean;
    loading?: boolean;
    onClick?: () => void;
}

export function KpiCard({ label, value, unit, icon: Icon, delta, footnote, sparkline, highlight, loading, onClick }: KpiCardProps) {
    const Wrapper = onClick ? 'button' : 'div';
    return (
        <Wrapper
            onClick={onClick}
            className={cn(
                'relative flex min-h-[188px] flex-col rounded-card border p-[22px] text-left shadow-card transition-transform',
                onClick && 'hover:-translate-y-0.5',
                highlight
                    ? 'border-transparent bg-sunset text-white'
                    : 'border-border bg-card text-card-foreground',
            )}
        >
            <div className="flex items-start justify-between gap-3">
                <p className={cn('text-[14px] font-medium', highlight ? 'text-white/85' : 'text-muted-foreground')}>{label}</p>
                {Icon && (
                    <span
                        className={cn(
                            'grid h-10 w-10 shrink-0 place-items-center rounded-full',
                            highlight ? 'bg-white/20 text-white' : 'bg-accent text-primary',
                        )}
                    >
                        <Icon className="h-[18px] w-[18px]" strokeWidth={1.8} />
                    </span>
                )}
            </div>

            {loading ? (
                <Skeleton className={cn('mt-4 h-10 w-32', highlight && 'bg-white/25')} />
            ) : (
                <p className="num mt-3 flex items-baseline gap-1.5">
                    <span className="text-[40px] font-extrabold leading-none">{value}</span>
                    {unit && <span className={cn('text-[15px] font-medium', highlight ? 'text-white/85' : 'text-muted-foreground')}>{unit}</span>}
                </p>
            )}

            <div className="mt-auto flex items-end justify-between gap-3 pt-4">
                <p className={cn('flex flex-wrap items-center gap-x-2 text-[13px]', highlight ? 'text-white/85' : 'text-muted-foreground')}>
                    {delta && (
                        <span
                            className={cn(
                                'num inline-flex items-center gap-0.5 font-semibold',
                                highlight ? 'text-white' : delta.direction === 'up' ? 'text-ok' : 'text-bad',
                            )}
                        >
                            {delta.direction === 'up'
                                ? <ChevronUp className="h-4 w-4" aria-label="up" />
                                : <ChevronDown className="h-4 w-4" aria-label="down" />}
                            {delta.value}
                        </span>
                    )}
                    {footnote}
                </p>
                {sparkline && sparkline.length > 1 && (
                    <Sparkline values={sparkline} className={highlight ? 'text-white' : 'text-primary'} />
                )}
            </div>
        </Wrapper>
    );
}
