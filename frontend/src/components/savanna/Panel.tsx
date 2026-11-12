import * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * The handoff's `Card`: white surface, 20px radius, warm border, soft shadow,
 * 22px padding. Named Panel so it doesn't collide with components/ui/card,
 * which older pages still use (it shares the same look).
 */
export function Panel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
    return (
        <div
            className={cn('relative rounded-card border border-border bg-card p-[22px] text-card-foreground shadow-card', className)}
            {...props}
        />
    );
}

interface PanelHeaderProps {
    title: React.ReactNode;
    subtitle?: React.ReactNode;
    /** Shown before the title, e.g. <MpesaBadge />. */
    leading?: React.ReactNode;
    /** Right-side action slot. */
    action?: React.ReactNode;
    className?: string;
}

/** The handoff's `CardHeader`: title, subtitle, right-side action slot. */
export function PanelHeader({ title, subtitle, leading, action, className }: PanelHeaderProps) {
    return (
        <div className={cn('mb-4 flex items-start justify-between gap-3', className)}>
            <div className="flex min-w-0 items-center gap-2.5">
                {leading}
                <div className="min-w-0">
                    <h3 className="text-[15px] font-bold leading-tight text-foreground">{title}</h3>
                    {subtitle && <p className="mt-0.5 text-[12.5px] text-muted-foreground">{subtitle}</p>}
                </div>
            </div>
            {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
        </div>
    );
}

/** Small rounded chip ("4 new", "1 month"). */
export function Chip({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
    return (
        <span
            className={cn('inline-flex h-[30px] items-center gap-1.5 rounded-full bg-chip px-3 text-[12.5px] font-medium text-muted-foreground', className)}
            {...props}
        />
    );
}

/** Loading placeholder shaped like the content it stands in for. */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
    return <div className={cn('animate-pulse rounded-xl bg-chip', className)} aria-hidden="true" {...props} />;
}

/** One-line guidance + optional action, for panels with nothing to show. */
export function EmptyState({ message, action }: { message: React.ReactNode; action?: React.ReactNode }) {
    return (
        <div className="flex flex-col items-center justify-center gap-3 py-8 text-center text-[13px] text-muted-foreground">
            <p>{message}</p>
            {action}
        </div>
    );
}
