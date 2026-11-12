import { formatDistanceToNow } from 'date-fns';

// Online/offline pill from the state the backend stores on each router
// (is_online / last_seen_at / last_error, refreshed by the usage poll), so
// it renders without contacting the router.
export default function RouterStatusBadge({ router }: { router: any }) {
    if (router.is_online == null) {
        return (
            <span className="flex items-center gap-1 text-muted-foreground bg-secondary px-3 py-1 rounded-full">
                <span className="h-2 w-2 rounded-full bg-gray-400" /> Not checked yet
            </span>
        );
    }
    if (router.is_online) {
        return (
            <span className="flex items-center gap-1 text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full">
                <span className="h-2 w-2 rounded-full bg-emerald-500" /> Online
            </span>
        );
    }
    const lastSeen = router.last_seen_at
        ? `last seen ${formatDistanceToNow(new Date(router.last_seen_at), { addSuffix: true })}`
        : 'never reached';
    return (
        <span
            title={router.last_error || 'Unreachable'}
            className="flex items-center gap-1 text-red-700 bg-red-50 px-3 py-1 rounded-full"
        >
            <span className="h-2 w-2 rounded-full bg-red-500" /> Offline · {lastSeen}
        </span>
    );
}
