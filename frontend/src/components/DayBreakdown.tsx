import { useQuery } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { analyticsAPI } from '../services/api';
import ExportMenu from './ExportMenu';
import { EmptyState, Skeleton, formatAmount, formatCount, formatDateEAT, formatKES } from './savanna';

/**
 * Drill-down shown under a Reports chart after clicking one day's bar:
 * revenue -> by plan, by payment method, and the payments themselves;
 * usage -> by service type and the top subscribers that day.
 */
export default function DayBreakdown({ kind, date, onClose }: { kind: 'revenue' | 'usage'; date: string; onClose: () => void }) {
    const { data, isLoading, isError } = useQuery({
        queryKey: ['day-breakdown', kind, date],
        queryFn: async () => (await analyticsAPI.getDayBreakdown(kind, date)).data,
    });

    const title = formatDateEAT(`${date}T12:00:00+03:00`, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

    return (
        <div className="mt-5 rounded-2xl border border-border-soft bg-surface2 p-4 sm:p-5" aria-live="polite">
            <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                    <p className="text-[15px] font-bold text-foreground">{title}</p>
                    {data && (
                        <p className="num text-[13px] text-muted-foreground">
                            {kind === 'revenue'
                                ? `${formatKES(data.total)} from ${formatCount(data.count)} payment${data.count === 1 ? '' : 's'}`
                                : `${data.total_gb} GB by ${formatCount(data.users)} subscriber${data.users === 1 ? '' : 's'} · ↑ ${data.upload_gb} GB · ↓ ${data.download_gb} GB`}
                        </p>
                    )}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                    <ExportMenu
                        path="/analytics/day-breakdown/"
                        params={{ kind, date }}
                        filename={`${kind === 'revenue' ? 'revenue' : 'data_usage'}_${date}`}
                        className="h-9"
                    />
                    <button onClick={onClose} aria-label="Close breakdown" className="grid h-9 w-9 place-items-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground">
                        <X className="h-4 w-4" />
                    </button>
                </div>
            </div>

            {isLoading ? (
                <div className="grid gap-3 sm:grid-cols-2">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
            ) : isError ? (
                <p className="text-[13px] text-bad">Could not load this day's breakdown.</p>
            ) : kind === 'revenue' ? (
                data.count === 0 ? <EmptyState message="No payments on this day." /> : (
                    <>
                        <div className="grid gap-4 sm:grid-cols-2">
                            <Shares title="By plan" rows={data.by_plan.map((r: any) => ({ name: r.name, value: r.amount, label: `${formatKES(r.amount)} · ${r.count}` }))} />
                            <Shares title="By payment method" rows={data.by_method.map((r: any) => ({ name: r.name, value: r.amount, label: `${formatKES(r.amount)} · ${r.count}` }))} />
                        </div>
                        <Table
                            columns={['Time', 'Subscriber', 'Plan', 'Method', 'Reference', 'Amount']}
                            rows={data.items.map((t: any) => [
                                formatDateEAT(t.time, { hour: '2-digit', minute: '2-digit' }),
                                <span className="font-semibold text-foreground">{t.customer}</span>,
                                t.plan || '—', t.method, <span className="uppercase">{t.reference}</span>,
                                <span className="font-semibold text-foreground">{formatAmount(t.amount)}</span>,
                            ])}
                        />
                    </>
                )
            ) : (
                data.users === 0 ? <EmptyState message="No usage recorded on this day." /> : (
                    <>
                        <Shares title="By service type" rows={data.by_type.map((r: any) => ({ name: r.name, value: r.total_gb, label: `${r.total_gb} GB · ${r.users} users` }))} />
                        <Table
                            columns={['Subscriber', 'Upload', 'Download', 'Total']}
                            rows={data.items.map((u: any) => [
                                <span className="font-semibold text-foreground">{u.customer}</span>,
                                `${u.upload_gb} GB`, `${u.download_gb} GB`,
                                <span className="font-semibold text-foreground">{u.total_gb} GB</span>,
                            ])}
                        />
                    </>
                )
            )}
        </div>
    );
}

/** Labelled share bars. */
function Shares({ title, rows }: { title: string; rows: { name: string; value: number; label: string }[] }) {
    const max = Math.max(...rows.map((r) => r.value), 0) || 1;
    return (
        <div>
            <p className="mb-2 text-[12px] font-semibold uppercase tracking-[0.06em] text-faint">{title}</p>
            <div className="space-y-2.5">
                {rows.map((r) => (
                    <div key={r.name}>
                        <div className="flex justify-between gap-3 text-[13px]">
                            <span className="truncate text-foreground">{r.name}</span>
                            <span className="num shrink-0 text-muted-foreground">{r.label}</span>
                        </div>
                        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-chip">
                            <div className="h-full rounded-full bg-primary" style={{ width: `${(r.value / max) * 100}%` }} />
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function Table({ columns, rows }: { columns: string[]; rows: React.ReactNode[][] }) {
    return (
        <div className="-mx-1 mt-5 max-h-80 overflow-auto">
            <table className="w-full border-collapse text-[13px]">
                <thead className="sticky top-0 bg-surface2">
                    <tr>
                        {columns.map((c, i) => (
                            <th key={c} className={`border-b border-border px-2 pb-2 text-[11.5px] font-semibold uppercase tracking-[0.06em] text-faint ${i === columns.length - 1 ? 'text-right' : 'text-left'}`}>{c}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row, r) => (
                        <tr key={r} className="border-b border-border-soft last:border-0">
                            {row.map((cell, i) => (
                                <td key={i} className={`num whitespace-nowrap px-2 py-2 text-muted-foreground ${i === row.length - 1 ? 'text-right' : ''}`}>{cell}</td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
