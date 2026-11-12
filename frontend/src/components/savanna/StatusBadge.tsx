import { cn } from '@/lib/utils';

export type Status =
    | 'active' | 'online'
    | 'expiring' | 'degraded' | 'pending'
    | 'expired' | 'offline' | 'failed'
    | 'suspended' | 'inactive' | 'unknown';

const TONE: Record<Status, string> = {
    active: 'text-ok bg-ok-bg',
    online: 'text-ok bg-ok-bg',
    expiring: 'text-warn bg-warn-bg',
    degraded: 'text-warn bg-warn-bg',
    pending: 'text-warn bg-warn-bg',
    expired: 'text-bad bg-bad-bg',
    offline: 'text-bad bg-bad-bg',
    failed: 'text-bad bg-bad-bg',
    suspended: 'text-muted-foreground bg-chip',
    inactive: 'text-muted-foreground bg-chip',
    unknown: 'text-muted-foreground bg-chip',
};

/** Dot + label pill. The dot inherits the text colour. */
export function StatusBadge({ status, label, className }: { status: Status; label?: string; className?: string }) {
    const text = label ?? status.charAt(0).toUpperCase() + status.slice(1);
    return (
        <span
            className={cn(
                'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full py-[3px] pl-2 pr-2.5 text-xs font-medium',
                TONE[status] ?? TONE.unknown,
                className,
            )}
        >
            <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
            {text}
        </span>
    );
}

/** Map the backend's Customer/Subscription status strings onto badge variants. */
export function statusFromBackend(value: string | null | undefined): Status {
    switch ((value || '').toLowerCase()) {
        case 'active': return 'active';
        case 'online': return 'online';
        case 'expiring': return 'expiring';
        case 'expired': return 'expired';
        case 'suspended': return 'suspended';
        case 'pending': return 'pending';
        case 'inactive': return 'inactive';
        default: return 'unknown';
    }
}
