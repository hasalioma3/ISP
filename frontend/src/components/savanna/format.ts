// Formatting rules from design/HANDOFF.md §5: money is always "KES 2,500"
// (en-KE grouping, tabular numerals via the .num class), times are shown in
// Africa/Nairobi (EAT) regardless of the viewer's own timezone.

const kes = new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 });
const kesCompact = new Intl.NumberFormat('en-KE', { notation: 'compact', maximumFractionDigits: 2 });

export const TIME_ZONE = 'Africa/Nairobi';

export function formatKES(value: number | string | null | undefined): string {
    return `KES ${kes.format(Number(value ?? 0))}`;
}

/** Just the number part ("2,500"), for layouts that render "KES" separately. */
export function formatAmount(value: number | string | null | undefined): string {
    return kes.format(Number(value ?? 0));
}

/** "5.3M" / "242K" -- for headline KPIs where space is tight. */
export function formatCompact(value: number | string | null | undefined): string {
    return kesCompact.format(Number(value ?? 0));
}

export function formatCount(value: number | string | null | undefined): string {
    return kes.format(Number(value ?? 0));
}

/** "12 Nov 2026" (or a custom Intl option set) in EAT. */
export function formatDateEAT(
    value: string | number | Date | null | undefined,
    options: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' },
): string {
    if (value == null || value === '') return '—';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return '—';
    return new Intl.DateTimeFormat('en-GB', { timeZone: TIME_ZONE, ...options }).format(d);
}

/** "2m ago", "3h ago", "4d ago". */
export function timeAgo(value: string | number | Date | null | undefined): string {
    if (value == null) return '';
    const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
    if (seconds < 60) return 'just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
}

/** Percentage change, or null when there's no baseline to compare with. */
export function percentChange(current: number, previous: number): number | null {
    if (!previous) return null;
    return ((current - previous) / previous) * 100;
}

export function initials(name: string | null | undefined): string {
    const parts = (name || '?').trim().split(/\s+/).filter(Boolean);
    return ((parts[0]?.[0] || '?') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

const DURATION_UNITS: Record<string, [string, string]> = {
    minutes: ['minute', 'minutes'], hours: ['hour', 'hours'], days: ['day', 'days'], months: ['month', 'months'],
};

/**
 * "1 day", "3 hours", "30 days" from a plan's duration_value + duration_unit
 * -- the fields the backend actually uses for expiry. Never read the legacy
 * duration_days: it isn't kept in sync (a 1-day plan can still say 30).
 */
export function formatPlanDuration(plan: { duration_value?: number | null; duration_unit?: string | null }): string {
    const value = Number(plan?.duration_value ?? 0);
    const [one, many] = DURATION_UNITS[plan?.duration_unit || ''] || [plan?.duration_unit || '', plan?.duration_unit || ''];
    return `${value} ${value === 1 ? one : many}`.trim();
}
