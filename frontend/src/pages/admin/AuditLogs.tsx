import { Fragment, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, subDays } from 'date-fns';
import { ArrowLeft, ArrowRight, Calendar, ChevronDown, Layers, Search, ShieldAlert } from 'lucide-react';
import { auditAPI } from '../../services/api';
import { useAuthStore } from '../../store/authStore';
import ExportMenu from '../../components/ExportMenu';
import { EmptyState, Panel, Skeleton, formatCount, formatDateEAT } from '../../components/savanna';
import { cn } from '@/lib/utils';

const today = () => format(new Date(), 'yyyy-MM-dd');

const ACTION_TONE: Record<string, string> = {
    create: 'bg-ok-bg text-ok',
    update: 'bg-chip text-foreground',
    delete: 'bg-bad-bg text-bad',
    login: 'bg-surface2 text-muted-foreground',
    login_failed: 'bg-warn-bg text-warn',
    request: 'bg-chip text-muted-foreground',
};

const show = (v: unknown) => {
    if (v === null || v === undefined || v === '') return '—';
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
};

/** What changed, as a field / before / after table (or field / value for create & delete). */
function Changes({ log }: { log: any }) {
    const entries = Object.entries(log.changes || {});
    if (log.action === 'request') {
        return (
            <div className="space-y-1 text-[13px]">
                <p><span className="text-muted-foreground">Request:</span> <span className="font-mono">{log.method} {log.path}</span> → <b>{log.status_code}</b></p>
                {log.changes?.body && (
                    <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-card p-3 font-mono text-[12px]">
                        {JSON.stringify(log.changes.body, null, 2)}
                    </pre>
                )}
            </div>
        );
    }
    if (!entries.length) return <p className="text-[13px] text-muted-foreground">No field details.</p>;
    const isUpdate = log.action === 'update';
    return (
        <table className="w-full text-[13px]">
            <thead>
                <tr className="text-left text-[11.5px] uppercase tracking-wide text-faint">
                    <th className="pb-1.5 pr-4 font-medium">Field</th>
                    {isUpdate ? <><th className="pb-1.5 pr-4 font-medium">Before</th><th className="pb-1.5 font-medium">After</th></> : <th className="pb-1.5 font-medium">Value</th>}
                </tr>
            </thead>
            <tbody>
                {entries.map(([field, v]: [string, any]) => (
                    <tr key={field} className="border-t border-border-soft align-top">
                        <td className="py-1.5 pr-4 font-medium whitespace-nowrap">{field.replace(/_/g, ' ')}</td>
                        {isUpdate && Array.isArray(v) && v.length === 2 ? (
                            <>
                                <td className="py-1.5 pr-4 break-all text-bad/90 line-through decoration-bad/40">{show(v[0])}</td>
                                <td className="py-1.5 break-all text-ok">{show(v[1])}</td>
                            </>
                        ) : (
                            <td className="py-1.5 break-all" colSpan={isUpdate ? 2 : 1}>{show(v)}</td>
                        )}
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

/**
 * The audit log: every change in the system -- records created, updated
 * (with before/after values) and deleted, sign-ins and failed sign-ins, and
 * every staff action -- with who did it, from where, and when. Superadmins
 * only (the API enforces this too).
 */
export default function AuditLogs() {
    const user = useAuthStore((s) => s.user);
    const [startDate, setStartDate] = useState(format(subDays(new Date(), 6), 'yyyy-MM-dd'));
    const [endDate, setEndDate] = useState(today());
    const [action, setAction] = useState('');
    const [model, setModel] = useState('');
    const [actor, setActor] = useState('');
    const [requestId, setRequestId] = useState('');
    const [hideRequests, setHideRequests] = useState(false);
    const [searchInput, setSearchInput] = useState('');
    const [search, setSearch] = useState('');
    const [page, setPage] = useState(1);
    const [open, setOpen] = useState<number | null>(null);

    const params = {
        start_date: requestId ? undefined : startDate, end_date: requestId ? undefined : endDate,
        action: action || undefined, model: model || undefined, actor: actor || undefined,
        search: search || undefined, request_id: requestId || undefined, hide_requests: hideRequests ? '1' : undefined,
    };
    const enabled = !!user?.is_superuser;
    const { data, isLoading } = useQuery({
        queryKey: ['audit-logs', params, page],
        queryFn: async () => (await auditAPI.getLogs({ ...params, page, page_size: 50 })).data,
        enabled,
        refetchInterval: 30_000,
    });
    const { data: facets } = useQuery({
        queryKey: ['audit-facets', params],
        queryFn: async () => (await auditAPI.getFacets(params)).data,
        enabled,
    });

    if (!enabled) {
        return <Panel><EmptyState message={<span className="inline-flex items-center gap-2"><ShieldAlert className="h-4 w-4" /> Only a superadmin can view the logs.</span>} /></Panel>;
    }

    const reset = () => setPage(1);
    const setRange = (days: number) => { setStartDate(format(subDays(new Date(), days - 1), 'yyyy-MM-dd')); setEndDate(today()); reset(); };
    const totalPages = data ? Math.max(1, Math.ceil(data.count / 50)) : 1;
    const selectClass = 'h-10 rounded-full border border-input bg-card px-4 text-[13.5px] focus:outline-none focus-visible:ring-2 focus-visible:ring-ring';
    const filtersOn = action || model || actor || search || requestId || hideRequests;

    return (
        <div className="space-y-[18px]">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h1 className="text-2xl font-bold">Logs</h1>
                    <p className="text-sm text-muted-foreground">Every change in the system: who made it, what changed, when and from where.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    {[1, 7, 30].map((d) => (
                        <button key={d} onClick={() => setRange(d)}
                            className={cn('h-9 rounded-full px-3.5 text-[13px] font-semibold',
                                startDate === format(subDays(new Date(), d - 1), 'yyyy-MM-dd') && endDate === today() ? 'bg-primary text-primary-foreground' : 'bg-chip text-muted-foreground')}>
                            {d === 1 ? 'Today' : `${d} days`}
                        </button>
                    ))}
                    <div className="flex h-10 items-center gap-2 rounded-full border border-input bg-card px-3">
                        <Calendar className="h-4 w-4 text-muted-foreground" />
                        <input type="date" aria-label="From" value={startDate} max={endDate} onChange={(e) => { setStartDate(e.target.value); reset(); }} className="bg-transparent text-[13px] focus:outline-none" />
                        <span className="text-muted-foreground">–</span>
                        <input type="date" aria-label="To" value={endDate} min={startDate} onChange={(e) => { setEndDate(e.target.value); reset(); }} className="bg-transparent text-[13px] focus:outline-none" />
                    </div>
                    <ExportMenu path="/audit/logs/" params={params} filename={`audit_log_${startDate}_${endDate}`} />
                </div>
            </div>

            {facets && (
                <div className="flex flex-wrap gap-2">
                    {facets.actions.map((a: any) => (
                        <button key={a.value} onClick={() => { setAction(action === a.value ? '' : a.value); reset(); }}
                            className={cn('rounded-full px-3.5 py-1.5 text-[13px] font-semibold', action === a.value ? 'bg-primary text-primary-foreground' : ACTION_TONE[a.value])}>
                            {a.label} <span className="num ml-1 opacity-80">{formatCount(facets.counts[a.value] || 0)}</span>
                        </button>
                    ))}
                </div>
            )}

            <Panel className="p-0">
                <div className="flex flex-wrap items-center gap-2 border-b border-border p-4">
                    <form onSubmit={(e) => { e.preventDefault(); setSearch(searchInput.trim()); reset(); }} className="relative">
                        <Search className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-faint" />
                        <input type="search" aria-label="Search logs" placeholder="Record, user, IP, path…" value={searchInput}
                            onChange={(e) => setSearchInput(e.target.value)}
                            className="h-10 w-60 rounded-full border border-input bg-card pl-10 pr-4 text-[13.5px] focus:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
                    </form>
                    <select aria-label="User" value={actor} onChange={(e) => { setActor(e.target.value); reset(); }} className={selectClass}>
                        <option value="">By: Anyone</option>
                        {facets?.actors.map((a: string) => <option key={a} value={a}>{a}</option>)}
                    </select>
                    <select aria-label="Record type" value={model} onChange={(e) => { setModel(e.target.value); reset(); }} className={selectClass}>
                        <option value="">Record: All</option>
                        {facets?.models.map((m: string) => <option key={m} value={m}>{m.split('.')[1]} ({m.split('.')[0]})</option>)}
                    </select>
                    <label className="flex items-center gap-2 text-[13px]">
                        <input type="checkbox" checked={hideRequests} onChange={(e) => { setHideRequests(e.target.checked); reset(); }} />
                        Hide request rows
                    </label>
                    {requestId && (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1.5 text-[13px] font-semibold text-primary">
                            <Layers className="h-3.5 w-3.5" /> One request
                        </span>
                    )}
                    {filtersOn && (
                        <button onClick={() => { setAction(''); setModel(''); setActor(''); setSearch(''); setSearchInput(''); setRequestId(''); setHideRequests(false); reset(); }}
                            className="text-[13px] font-semibold text-primary">Clear filters</button>
                    )}
                </div>

                <div className="overflow-x-auto px-3">
                    <table className="w-full border-collapse text-[13.5px]">
                        <thead>
                            <tr className="text-left text-[13px] text-faint">
                                {['Time', 'By', 'Action', 'Record', 'From', ''].map((h) => <th key={h} className="border-b border-border px-3 py-3 font-medium">{h}</th>)}
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? [...Array(8)].map((_, i) => <tr key={i}><td colSpan={6} className="px-3 py-2"><Skeleton className="h-9 w-full" /></td></tr>)
                                : !data?.results.length ? <tr><td colSpan={6}><EmptyState message="Nothing logged for these filters." /></td></tr>
                                : data.results.map((log: any) => (
                                    <Fragment key={log.id}>
                                        <tr className="border-b border-border-soft hover:bg-surface2 cursor-pointer" onClick={() => setOpen(open === log.id ? null : log.id)}>
                                            <td className="num whitespace-nowrap px-3 py-3 text-muted-foreground">
                                                {formatDateEAT(log.created_at, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                            </td>
                                            <td className="px-3 py-3">
                                                <span className="block font-medium">{log.actor_username || 'System'}</span>
                                                {log.actor_role && <span className="block text-xs text-muted-foreground capitalize">{log.actor_role}</span>}
                                            </td>
                                            <td className="px-3 py-3">
                                                <span className={cn('inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold', ACTION_TONE[log.action])}>{log.action_label}</span>
                                            </td>
                                            <td className="px-3 py-3">
                                                <span className="block truncate max-w-[320px]">{log.object_repr || '—'}</span>
                                                {log.model && <span className="block text-xs text-muted-foreground">{log.model.split('.')[1]}{log.action === 'update' ? ` · ${Object.keys(log.changes || {}).length} field(s)` : ''}</span>}
                                            </td>
                                            <td className="px-3 py-3 text-muted-foreground">
                                                <span className="num block">{log.ip_address || '—'}</span>
                                                <span className="block text-xs">{log.source_label}</span>
                                            </td>
                                            <td className="px-3 py-3 text-right"><ChevronDown className={cn('inline h-4 w-4 text-muted-foreground transition-transform', open === log.id && 'rotate-180')} /></td>
                                        </tr>
                                        {open === log.id && (
                                            <tr className="border-b border-border-soft bg-surface2">
                                                <td colSpan={6} className="px-4 py-3 space-y-3">
                                                    <Changes log={log} />
                                                    <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
                                                        {log.model && <span>Record: {log.model} #{log.object_id}</span>}
                                                        {log.path && log.action !== 'request' && <span>Via: {log.method} {log.path}</span>}
                                                        {log.user_agent && <span className="truncate max-w-[420px]">Device: {log.user_agent}</span>}
                                                    </div>
                                                    <div className="flex flex-wrap gap-3">
                                                        {log.request_id && !requestId && (
                                                            <button onClick={(e) => { e.stopPropagation(); setRequestId(log.request_id); reset(); }}
                                                                className="text-[13px] font-semibold text-primary">Everything from this request</button>
                                                        )}
                                                        {log.model && log.object_id && (
                                                            <button onClick={(e) => { e.stopPropagation(); setModel(log.model); setSearch(log.object_id); setSearchInput(log.object_id); reset(); }}
                                                                className="text-[13px] font-semibold text-primary">History of this record</button>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        )}
                                    </Fragment>
                                ))}
                        </tbody>
                    </table>
                </div>
                <div className="flex items-center justify-end gap-3 p-4">
                    <span className="num text-[13.5px] text-muted-foreground">Page {page} of {totalPages} · {formatCount(data?.count)} entries</span>
                    <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} aria-label="Previous page"
                        className="grid h-10 w-10 place-items-center rounded-full border border-input disabled:opacity-40"><ArrowLeft className="h-4 w-4" /></button>
                    <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} aria-label="Next page"
                        className="grid h-10 w-10 place-items-center rounded-full border border-input disabled:opacity-40"><ArrowRight className="h-4 w-4" /></button>
                </div>
            </Panel>
        </div>
    );
}
