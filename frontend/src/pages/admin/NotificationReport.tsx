import { Fragment, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import { format, subDays } from 'date-fns';
import { ArrowLeft, ArrowRight, Calendar, ChevronDown, Loader2, RotateCw, Search } from 'lucide-react';
import { notificationAPI } from '../../services/api';
import ExportMenu from '../../components/ExportMenu';
import { EmptyState, KpiCard, Panel, PanelHeader, Skeleton, StatusBadge, formatCount, formatDateEAT } from '../../components/savanna';
import { CheckCircle2, Send, XCircle, Percent } from 'lucide-react';

const today = () => format(new Date(), 'yyyy-MM-dd');

/**
 * Delivery status of every outgoing message (SMS, WhatsApp, email, Telegram),
 * from the notification log: totals, per channel and message type, the
 * commonest failure reasons, and each message with its error -- failed ones
 * can be resent.
 */
export default function NotificationReport() {
    const queryClient = useQueryClient();
    const [startDate, setStartDate] = useState(format(subDays(new Date(), 6), 'yyyy-MM-dd'));
    const [endDate, setEndDate] = useState(today());
    const [channel, setChannel] = useState('');
    const [status, setStatus] = useState('');
    const [eventType, setEventType] = useState('');
    const [searchInput, setSearchInput] = useState('');
    const [search, setSearch] = useState('');
    const [page, setPage] = useState(1);
    const [open, setOpen] = useState<number | null>(null);
    const [resending, setResending] = useState<number | null>(null);

    const params = {
        start_date: startDate, end_date: endDate, channel: channel || undefined, status: status || undefined,
        event_type: eventType || undefined, search: search || undefined,
    };
    const { data, isLoading } = useQuery({
        queryKey: ['notification-report', params, page],
        queryFn: async () => (await notificationAPI.getReport({ ...params, page, page_size: 25 })).data,
        refetchInterval: 30_000,
    });

    const setRange = (days: number) => { setStartDate(format(subDays(new Date(), days - 1), 'yyyy-MM-dd')); setEndDate(today()); setPage(1); };
    const resend = async (id: number) => {
        setResending(id);
        try {
            await notificationAPI.resendMessage(id);
            toast.success('Sent again');
        } catch (err: any) {
            toast.error(err.response?.data?.error || 'Still failing', { duration: 7000 });
        } finally {
            setResending(null);
            queryClient.invalidateQueries({ queryKey: ['notification-report'] });
        }
    };

    const s = data?.summary;
    const selectClass = 'h-10 rounded-full border border-input bg-card px-4 text-[13.5px] focus:outline-none focus-visible:ring-2 focus-visible:ring-ring';

    return (
        <div className="space-y-[18px]">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h1 className="text-2xl font-bold">Messages</h1>
                    <p className="text-sm text-muted-foreground">Delivery status of every SMS, WhatsApp, email and Telegram message sent.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    {[1, 7, 30].map((d) => (
                        <button key={d} onClick={() => setRange(d)}
                            className={`h-9 rounded-full px-3.5 text-[13px] font-semibold ${startDate === format(subDays(new Date(), d - 1), 'yyyy-MM-dd') && endDate === today() ? 'bg-primary text-primary-foreground' : 'bg-chip text-muted-foreground'}`}>
                            {d === 1 ? 'Today' : `${d} days`}
                        </button>
                    ))}
                    <div className="flex h-10 items-center gap-2 rounded-full border border-input bg-card px-3">
                        <Calendar className="h-4 w-4 text-muted-foreground" />
                        <input type="date" aria-label="From" value={startDate} max={endDate} onChange={(e) => { setStartDate(e.target.value); setPage(1); }} className="bg-transparent text-[13px] focus:outline-none" />
                        <span className="text-muted-foreground">–</span>
                        <input type="date" aria-label="To" value={endDate} min={startDate} onChange={(e) => { setEndDate(e.target.value); setPage(1); }} className="bg-transparent text-[13px] focus:outline-none" />
                    </div>
                    <ExportMenu path="/notifications/report/" params={params} filename={`messages_${startDate}_${endDate}`} />
                </div>
            </div>

            <div className="grid grid-cols-2 gap-[18px] xl:grid-cols-4">
                <KpiCard label="Messages" icon={Send} value={formatCount(s?.total)} loading={isLoading} />
                <KpiCard label="Delivered to provider" icon={CheckCircle2} value={formatCount(s?.sent)} loading={isLoading} />
                <KpiCard label="Failed" icon={XCircle} value={formatCount(s?.failed)} loading={isLoading} highlight={!!s?.failed} />
                <KpiCard label="Delivery rate" icon={Percent} value={s?.delivery_rate != null ? `${s.delivery_rate}%` : '—'} loading={isLoading} />
            </div>

            <div className="grid grid-cols-1 gap-[18px] xl:grid-cols-3">
                <Panel>
                    <PanelHeader title="By channel" />
                    {isLoading ? <Skeleton className="h-24 w-full" /> : !data?.by_channel.length ? <EmptyState message="No messages in this period." /> : (
                        <table className="w-full text-[13.5px]">
                            <thead><tr className="text-left text-[11.5px] uppercase tracking-wide text-faint"><th className="pb-2">Channel</th><th className="pb-2 text-right">Sent</th><th className="pb-2 text-right">Failed</th></tr></thead>
                            <tbody>{data.by_channel.map((c: any) => (
                                <tr key={c.channel} className="border-t border-border-soft cursor-pointer hover:bg-surface2" onClick={() => { setChannel(c.channel); setPage(1); }}>
                                    <td className="py-2 font-medium">{c.label}</td><td className="num py-2 text-right">{c.sent}</td>
                                    <td className={`num py-2 text-right ${c.failed ? 'text-bad font-semibold' : ''}`}>{c.failed}</td>
                                </tr>
                            ))}</tbody>
                        </table>
                    )}
                </Panel>
                <Panel>
                    <PanelHeader title="By message type" />
                    {isLoading ? <Skeleton className="h-24 w-full" /> : !data?.by_event.length ? <EmptyState message="No messages in this period." /> : (
                        <table className="w-full text-[13.5px]">
                            <thead><tr className="text-left text-[11.5px] uppercase tracking-wide text-faint"><th className="pb-2">Type</th><th className="pb-2 text-right">Sent</th><th className="pb-2 text-right">Failed</th></tr></thead>
                            <tbody>{data.by_event.map((e: any) => (
                                <tr key={e.event_type} className="border-t border-border-soft cursor-pointer hover:bg-surface2" onClick={() => { setEventType(e.event_type); setPage(1); }}>
                                    <td className="py-2">{e.label}</td><td className="num py-2 text-right">{e.sent}</td>
                                    <td className={`num py-2 text-right ${e.failed ? 'text-bad font-semibold' : ''}`}>{e.failed}</td>
                                </tr>
                            ))}</tbody>
                        </table>
                    )}
                </Panel>
                <Panel>
                    <PanelHeader title="Most common failures" />
                    {isLoading ? <Skeleton className="h-24 w-full" /> : !data?.top_errors.length ? <EmptyState message="No failures in this period." /> : (
                        <ul className="space-y-2.5">{data.top_errors.map((e: any) => (
                            <li key={e.error} className="flex items-start justify-between gap-3 text-[13px]">
                                <span className="text-foreground break-words">{e.error}</span>
                                <span className="num shrink-0 rounded-full bg-bad-bg px-2 py-0.5 text-[12px] font-semibold text-bad">{e.count}</span>
                            </li>
                        ))}</ul>
                    )}
                </Panel>
            </div>

            <Panel className="p-0">
                <div className="flex flex-wrap items-center gap-2 border-b border-border p-4">
                    <form onSubmit={(e) => { e.preventDefault(); setSearch(searchInput.trim()); setPage(1); }} className="relative">
                        <Search className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-faint" />
                        <input type="search" aria-label="Search messages" placeholder="Recipient, customer, text…" value={searchInput}
                            onChange={(e) => setSearchInput(e.target.value)}
                            className="h-10 w-60 rounded-full border border-input bg-card pl-10 pr-4 text-[13.5px] focus:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
                    </form>
                    <select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className={selectClass}>
                        <option value="">Status: All</option><option value="sent">Sent</option><option value="failed">Failed</option>
                    </select>
                    <select aria-label="Channel" value={channel} onChange={(e) => { setChannel(e.target.value); setPage(1); }} className={selectClass}>
                        <option value="">Channel: All</option>
                        {data?.channels.map((c: any) => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                    <select aria-label="Message type" value={eventType} onChange={(e) => { setEventType(e.target.value); setPage(1); }} className={selectClass}>
                        <option value="">Type: All</option>
                        {data?.event_types.map((t: any) => <option key={t.value} value={t.value}>{t.label}</option>)}
                    </select>
                    {(channel || status || eventType || search) && (
                        <button onClick={() => { setChannel(''); setStatus(''); setEventType(''); setSearch(''); setSearchInput(''); setPage(1); }}
                            className="text-[13px] font-semibold text-primary">Clear filters</button>
                    )}
                </div>

                <div className="overflow-x-auto px-3">
                    <table className="w-full border-collapse text-[13.5px]">
                        <thead>
                            <tr className="text-left text-[13px] text-faint">
                                {['Time', 'Channel', 'Type', 'Recipient', 'Status', ''].map((h) => <th key={h} className="border-b border-border px-3 py-3 font-medium">{h}</th>)}
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? [...Array(6)].map((_, i) => <tr key={i}><td colSpan={6} className="px-3 py-2"><Skeleton className="h-9 w-full" /></td></tr>)
                                : !data?.results.length ? <tr><td colSpan={6}><EmptyState message="No messages match these filters." /></td></tr>
                                : data.results.map((m: any) => (
                                    <Fragment key={m.id}>
                                        <tr className="border-b border-border-soft hover:bg-surface2 cursor-pointer" onClick={() => setOpen(open === m.id ? null : m.id)}>
                                            <td className="num whitespace-nowrap px-3 py-3 text-muted-foreground">{formatDateEAT(m.created_at, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                                            <td className="whitespace-nowrap px-3 py-3">{m.channel_label}</td>
                                            <td className="px-3 py-3">{m.event_label}</td>
                                            <td className="px-3 py-3">
                                                <span className="block truncate max-w-[220px]">{m.customer?.name || m.recipient || '—'}</span>
                                                {m.customer && <span className="num block text-xs text-muted-foreground truncate max-w-[220px]">{m.recipient}</span>}
                                            </td>
                                            <td className="px-3 py-3"><StatusBadge status={m.status === 'sent' ? 'active' : 'failed'} label={m.status === 'sent' ? 'Sent' : 'Failed'} /></td>
                                            <td className="px-3 py-3 text-right"><ChevronDown className={`inline h-4 w-4 text-muted-foreground transition-transform ${open === m.id ? 'rotate-180' : ''}`} /></td>
                                        </tr>
                                        {open === m.id && (
                                            <tr className="border-b border-border-soft bg-surface2">
                                                <td colSpan={6} className="px-4 py-3">
                                                    <p className="text-xs font-semibold uppercase tracking-wide text-faint mb-1">Message</p>
                                                    <p className="whitespace-pre-wrap text-[13.5px] text-foreground">{m.message}</p>
                                                    {m.error && (
                                                        <>
                                                            <p className="text-xs font-semibold uppercase tracking-wide text-faint mt-3 mb-1">Why it failed</p>
                                                            <p className="text-[13px] text-bad break-words">{m.error}</p>
                                                        </>
                                                    )}
                                                    {m.status !== 'sent' && m.recipient && (
                                                        <button onClick={(e) => { e.stopPropagation(); resend(m.id); }} disabled={resending === m.id}
                                                            className="mt-3 inline-flex items-center gap-2 rounded-full bg-primary px-4 py-1.5 text-[13px] font-semibold text-primary-foreground disabled:opacity-60">
                                                            {resending === m.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCw className="h-4 w-4" />} Resend
                                                        </button>
                                                    )}
                                                </td>
                                            </tr>
                                        )}
                                    </Fragment>
                                ))}
                        </tbody>
                    </table>
                </div>
                <div className="flex items-center justify-end gap-3 p-4">
                    <span className="num text-[13.5px] text-muted-foreground">Page {data?.page ?? 1} of {data?.total_pages ?? 1} · {formatCount(data?.count)} messages</span>
                    <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} aria-label="Previous page"
                        className="grid h-10 w-10 place-items-center rounded-full border border-input disabled:opacity-40"><ArrowLeft className="h-4 w-4" /></button>
                    <button onClick={() => setPage((p) => Math.min(data?.total_pages ?? 1, p + 1))} disabled={page >= (data?.total_pages ?? 1)} aria-label="Next page"
                        className="grid h-10 w-10 place-items-center rounded-full border border-input disabled:opacity-40"><ArrowRight className="h-4 w-4" /></button>
                </div>
            </Panel>
        </div>
    );
}
