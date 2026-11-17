// Formatting rules come from the ISP app (Savanna handoff §5): "KES 2,500",
// Africa/Nairobi times.
export { formatKES, formatDateEAT, timeAgo, formatCount, initials } from '@/components/savanna/format';
import { formatDateEAT } from '@/components/savanna/format';

export const dateTime = (v?: string | null) =>
    formatDateEAT(v, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });

export function duration(seconds?: number | null) {
    if (seconds == null) return '';
    if (seconds <= 0) return 'ended';
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (d) return `${d}d ${h}h left`;
    if (h) return `${h}h ${m}m left`;
    return `${m}m left`;
}
