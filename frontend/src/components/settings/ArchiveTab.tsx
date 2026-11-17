import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Archive, Download, Loader2, PlayCircle, RotateCcw, Trash2 } from 'lucide-react';
import { archiveAPI } from '../../services/api';
import { errText } from '../../utils/errText';
import { downloadBlob } from '../../utils/downloadBlob';
import { formatDateEAT } from '../savanna';
import { cn } from '@/lib/utils';

const CARD = 'bg-card border rounded-lg p-4 sm:p-5';
const BTN = 'inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50';
const HOURS = Array.from({ length: 24 }, (_, h) => h);
const hourLabel = (h: number) => `${String(h).padStart(2, '0')}:00`;
const MONTH_CHOICES = [3, 6, 12, 18, 24, 36, 60];

const bytes = (n?: number) => {
    if (!n) return '—';
    const u = ['B', 'KB', 'MB', 'GB'];
    const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
    return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`;
};

const STATUS_TONE: Record<string, string> = {
    done: 'bg-ok-bg text-ok', running: 'bg-chip text-muted-foreground', failed: 'bg-bad-bg text-bad', restored: 'bg-warn-bg text-warn',
};

/**
 * Settings -> Archive (superadmins): move rows older than N months out of
 * the live database into compressed files on the backup volume, nightly or
 * on demand; download, restore or delete each archive file.
 */
export default function ArchiveTab() {
    const qc = useQueryClient();
    const [months, setMonths] = useState<number | null>(null);
    const { data: s, isLoading } = useQuery({
        queryKey: ['archive-settings', months],
        queryFn: async () => (await archiveAPI.getSettings(months ? { months } : undefined)).data,
    });
    useEffect(() => { if (s && months === null) setMonths(s.months); }, [s, months]);
    const { data: runs } = useQuery({
        queryKey: ['archive-runs'],
        queryFn: async () => (await archiveAPI.runs()).data,
        refetchInterval: (q) => ((q.state.data as any[] | undefined)?.some((r) => r.status === 'running') ? 3000 : 30000),
    });
    const refresh = () => { qc.invalidateQueries({ queryKey: ['archive-settings'] }); qc.invalidateQueries({ queryKey: ['archive-runs'] }); };
    const save = useMutation({
        mutationFn: (data: Record<string, unknown>) => archiveAPI.updateSettings(data),
        onSuccess: () => { toast.success('Archive settings saved'); refresh(); },
        onError: (e) => toast.error(errText(e, 'Could not save')),
    });
    const runNow = useMutation({
        mutationFn: () => archiveAPI.runNow(),
        onSuccess: () => { toast.success('Archiving started; this list updates when it finishes'); setTimeout(refresh, 1500); },
        onError: (e) => toast.error(errText(e)),
    });
    const restore = useMutation({
        mutationFn: (id: number) => archiveAPI.restore(id),
        onSuccess: (r) => { toast.success(`${r.data.restored} rows restored`); refresh(); },
        onError: (e) => toast.error(errText(e)),
    });
    const remove = useMutation({
        mutationFn: (id: number) => archiveAPI.remove(id),
        onSuccess: () => { toast.success('Archive file deleted'); refresh(); },
        onError: (e) => toast.error(errText(e)),
    });

    if (isLoading || !s) return <div className="text-sm text-muted-foreground"><Loader2 className="inline h-4 w-4 animate-spin" /> Loading…</div>;

    const chosen = new Set((s.datasets || '').split(',').filter(Boolean));
    const toggle = (key: string, on: boolean) => {
        const next = new Set(chosen);
        if (on) next.add(key); else next.delete(key);
        save.mutate({ datasets: Array.from(next).join(',') });
    };
    const totalRows = (s.preview?.datasets || []).filter((d: any) => chosen.has(d.key)).reduce((a: number, d: any) => a + d.rows, 0);

    return (
        <div className="space-y-6 max-w-3xl">
            <div className={CARD}>
                <h3 className="text-lg font-bold mb-1 flex items-center gap-2"><Archive className="h-5 w-5" /> Archive old data</h3>
                <p className="text-sm text-muted-foreground mb-4">
                    Rows older than the age below are written to a compressed file on the backup disk and removed from the
                    live database, keeping the system fast. Archives can be downloaded or restored at any time. Payments,
                    transactions, subscriptions and invoices are never archived.
                </p>
                <div className="flex flex-wrap items-center gap-4 mb-4 text-sm">
                    <label className="flex items-center gap-2">
                        <input type="checkbox" checked={s.enabled} disabled={save.isPending}
                            onChange={(e) => save.mutate({ enabled: e.target.checked })} />
                        Archive automatically every night
                    </label>
                    <label className="flex items-center gap-2">
                        <span className="text-muted-foreground">at</span>
                        <select className="border rounded-lg px-2 py-1 text-sm" value={s.hour} disabled={!s.enabled || save.isPending}
                            onChange={(e) => save.mutate({ hour: Number(e.target.value) })}>
                            {HOURS.map((h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
                        </select>
                    </label>
                </div>
                <div className="flex flex-wrap items-end gap-3 mb-4">
                    <div>
                        <label className="block text-sm font-medium text-foreground/80 mb-1">Archive data older than</label>
                        <select className="border rounded-lg px-3 py-2 text-sm" value={months ?? s.months}
                            onChange={(e) => setMonths(Number(e.target.value))}>
                            {Array.from(new Set([...MONTH_CHOICES, s.months])).sort((a, b) => a - b).map((m) => (
                                <option key={m} value={m}>{m} months</option>
                            ))}
                        </select>
                    </div>
                    {months !== null && months !== s.months && (
                        <button className={cn(BTN, 'bg-primary text-primary-foreground')} disabled={save.isPending}
                            onClick={() => save.mutate({ months })}>Save {months} months</button>
                    )}
                </div>
                <p className="text-sm font-medium text-foreground/80 mb-2">
                    What to archive <span className="font-normal text-muted-foreground">(rows older than {formatDateEAT(s.preview?.cutoff)})</span>
                </p>
                <div className="divide-y rounded-lg border">
                    {(s.available || []).map((d: any) => {
                        const rows = s.preview?.datasets?.find((p: any) => p.key === d.key)?.rows ?? 0;
                        return (
                            <label key={d.key} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                                <span className="flex items-center gap-2">
                                    <input type="checkbox" checked={chosen.has(d.key)} disabled={save.isPending}
                                        onChange={(e) => toggle(d.key, e.target.checked)} />
                                    {d.label}
                                </span>
                                <span className="tabular-nums text-muted-foreground">{rows.toLocaleString()} rows</span>
                            </label>
                        );
                    })}
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                    <button className={cn(BTN, 'bg-primary text-primary-foreground')}
                        disabled={runNow.isPending || !chosen.size || months !== s.months}
                        onClick={() => {
                            if (window.confirm(`Archive ${totalRows.toLocaleString()} rows older than ${s.months} months now? They will be removed from the live database (the archive file keeps them).`)) runNow.mutate();
                        }}>
                        {runNow.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />} Archive now
                    </button>
                    {s.last_run_at && <span className="text-xs text-muted-foreground">Last run {formatDateEAT(s.last_run_at)}</span>}
                </div>
            </div>

            <div className={CARD}>
                <h3 className="text-lg font-bold mb-3">Archive files</h3>
                {!runs?.length ? (
                    <p className="text-sm text-muted-foreground">Nothing archived yet.</p>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="text-left text-xs uppercase text-muted-foreground">
                                    <th className="py-2 pr-3">When</th><th className="py-2 pr-3">Data</th><th className="py-2 pr-3 text-right">Rows</th>
                                    <th className="py-2 pr-3 text-right">Size</th><th className="py-2 pr-3">Status</th><th className="py-2" />
                                </tr>
                            </thead>
                            <tbody>
                                {runs.map((r: any) => (
                                    <tr key={r.id} className="border-t align-top">
                                        <td className="py-2 pr-3 whitespace-nowrap">{formatDateEAT(r.started_at)}<div className="text-xs text-muted-foreground">by {r.triggered_by || '—'}</div></td>
                                        <td className="py-2 pr-3">{r.label}<div className="text-xs text-muted-foreground">before {formatDateEAT(r.cutoff)}</div></td>
                                        <td className="py-2 pr-3 text-right tabular-nums">{r.rows.toLocaleString()}</td>
                                        <td className="py-2 pr-3 text-right tabular-nums">{bytes(r.size_bytes)}</td>
                                        <td className="py-2 pr-3">
                                            <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', STATUS_TONE[r.status])}>{r.status}</span>
                                            {r.error && <div className="mt-1 max-w-xs text-xs text-bad">{r.error}</div>}
                                        </td>
                                        <td className="py-2 whitespace-nowrap text-right">
                                            {r.file_exists && (
                                                <>
                                                    <button title="Download" className="p-1.5 rounded hover:bg-secondary"
                                                        onClick={async () => {
                                                            try { downloadBlob((await archiveAPI.download(r.id)).data, r.file_name.split('/').pop()); }
                                                            catch (e) { toast.error(errText(e)); }
                                                        }}><Download className="h-4 w-4" /></button>
                                                    <button title="Restore into the database" className="p-1.5 rounded hover:bg-secondary" disabled={restore.isPending}
                                                        onClick={() => window.confirm('Put these rows back into the live database?') && restore.mutate(r.id)}>
                                                        <RotateCcw className="h-4 w-4" /></button>
                                                </>
                                            )}
                                            <button title="Delete the archive file" className="p-1.5 rounded hover:bg-secondary text-bad" disabled={remove.isPending}
                                                onClick={() => window.confirm(r.file_exists ? 'Delete this archive file? The rows in it will be gone for good.' : 'Remove this entry?') && remove.mutate(r.id)}>
                                                <Trash2 className="h-4 w-4" /></button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}
