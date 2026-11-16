import { Fragment, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
    CheckCircle2, ChevronDown, UploadCloud as CloudUpload, Copy, Download, ExternalLink, HardDrive, KeyRound, Loader2, Lock,
    PlayCircle, RefreshCw, Server, Network, Trash2, AlertTriangle as TriangleAlert, XCircle,
} from 'lucide-react';
import { backupAPI } from '../../services/api';
import { getErrorMessage } from '../../utils/getErrorMessage';
import { downloadBlob } from '../../utils/downloadBlob';
import { formatDateEAT, timeAgo } from '../savanna';
import { cn } from '@/lib/utils';

const CARD = 'bg-card border rounded-lg p-4 sm:p-5';
const INPUT = 'w-full border rounded-lg px-3 py-2 text-sm';
const BTN = 'inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50';
const HOURS = Array.from({ length: 24 }, (_, h) => h);
const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

const bytes = (n?: number | null) => {
    if (!n) return '—';
    const u = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
    return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`;
};

function useBackupSettings() {
    return useQuery({ queryKey: ['backup-settings'], queryFn: async () => (await backupAPI.getSettings()).data });
}

function useSave(msg = 'Saved') {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (data: Record<string, unknown>) => backupAPI.updateSettings(data),
        onSuccess: () => { toast.success(msg); qc.invalidateQueries({ queryKey: ['backup-settings'] }); },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Could not save')),
    });
}

/**
 * Settings -> Backups (superadmins only): what's backed up and when,
 * encryption, Google Drive, a Synology NAS, the list of backups, and moving
 * to a new host.
 */
export default function BackupsTab() {
    // Every card below the list needs these settings and renders nothing
    // without them -- so say when they fail to load instead of silently
    // showing a page with only the list (e.g. a migration not yet applied).
    const { error, refetch, isFetching } = useBackupSettings();
    return (
        <div className="space-y-6 max-w-3xl">
            <BackupList />
            {error && (
                <div className={cn(CARD, 'border-bad/40 text-sm')}>
                    <p className="font-semibold text-bad"><XCircle className="mr-1 inline h-4 w-4" />Backup settings could not be loaded</p>
                    <p className="mt-1 text-muted-foreground">
                        {getErrorMessage(error, 'The server returned an error.')} The schedule, encryption, Google Drive and NAS settings
                        appear here once it loads. After an update, make sure migrations were run
                        (<span className="font-mono">docker compose exec backend python manage.py migrate</span>).
                    </p>
                    <button onClick={() => refetch()} disabled={isFetching} className={cn(BTN, 'border mt-3')}>
                        {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Try again
                    </button>
                </div>
            )}
            <ScheduleSection />
            <EncryptionSection />
            <DriveSection />
            <NasSection />
            <MigrationSection />
        </div>
    );
}

function BackupList() {
    const qc = useQueryClient();
    const { data: s } = useBackupSettings();
    const { data, isLoading } = useQuery({
        queryKey: ['backups'],
        queryFn: async () => (await backupAPI.list()).data,
        // Poll while a backup or upload is in progress.
        refetchInterval: (q) => (q.state.data?.results?.some((b: any) => b.status === 'running' || b.remote_status === 'uploading' || b.nas_status === 'uploading') ? 4000 : 60_000),
    });
    const [open, setOpen] = useState<number | null>(null);
    const [busy, setBusy] = useState<string | null>(null);
    const refresh = () => qc.invalidateQueries({ queryKey: ['backups'] });

    const runNow = async () => {
        setBusy('run');
        try { await backupAPI.runNow(); toast.success('Backup started'); refresh(); }
        catch (err: any) { toast.error(getErrorMessage(err, 'Could not start the backup')); }
        finally { setBusy(null); }
    };
    const download = async (b: any) => {
        setBusy(`dl${b.id}`);
        try { downloadBlob((await backupAPI.download(b.id)).data, b.filename); }
        catch (err: any) { toast.error(getErrorMessage(err, 'Download failed')); }
        finally { setBusy(null); }
    };
    const retry = async (b: any, target: 'gdrive' | 'nas') => {
        try { await backupAPI.upload(b.id, target); toast.success(target === 'nas' ? 'Copying to the NAS' : 'Uploading to Google Drive'); refresh(); }
        catch (err: any) { toast.error(getErrorMessage(err, 'Could not upload')); }
    };
    const remove = async (b: any) => {
        const where = [b.remote_status === 'ok' && 'Google Drive', b.nas_status === 'ok' && 'the NAS'].filter(Boolean).join(' and ');
        const remote = !!where && window.confirm(`Also delete it from ${where}? (OK = yes, Cancel = keep the off-site copy)`);
        if (!window.confirm(`Delete ${b.filename || 'this backup'} from this server?`)) return;
        try { await backupAPI.remove(b.id, remote); toast.success('Deleted'); refresh(); }
        catch (err: any) { toast.error(getErrorMessage(err, 'Could not delete')); }
    };

    const backups: any[] = data?.results ?? [];
    const last = backups.find((b) => b.status === 'ok' || b.status === 'partial');
    const running = backups.some((b) => b.status === 'running');

    return (
        <div className={CARD}>
            <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
                <div>
                    <h3 className="text-lg font-bold">Backups</h3>
                    <p className="text-sm text-muted-foreground">
                        Database, MikroTik configs, uploaded files{' '}and (when encrypted) server secrets and the WhatsApp login.
                    </p>
                    <p className="text-sm mt-1">
                        {last ? <>Last good backup: <b>{timeAgo(last.created_at)}</b> ({bytes(last.size)})</> : 'No backups yet.'}
                        {data?.disk && <span className="text-muted-foreground"> · {bytes(data.disk.free)} free on the server</span>}
                    </p>
                </div>
                <button onClick={runNow} disabled={busy === 'run' || running} className={cn(BTN, 'bg-primary text-primary-foreground')}>
                    {busy === 'run' || running ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
                    {running ? 'Backing up…' : 'Back up now'}
                </button>
            </div>

            <div className="overflow-x-auto -mx-2">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                            <th className="px-2 py-2 font-medium">When</th><th className="px-2 py-2 font-medium">Status</th>
                            <th className="px-2 py-2 font-medium">Size</th><th className="px-2 py-2 font-medium">Off-site</th>
                            <th className="px-2 py-2" />
                        </tr>
                    </thead>
                    <tbody>
                        {isLoading ? <tr><td colSpan={5} className="px-2 py-6 text-center text-muted-foreground">Loading…</td></tr>
                            : !backups.length ? <tr><td colSpan={5} className="px-2 py-6 text-center text-muted-foreground">No backups yet — click “Back up now”.</td></tr>
                            : backups.map((b) => (
                                <Fragment key={b.id}>
                                    <tr className="border-t cursor-pointer hover:bg-secondary" onClick={() => setOpen(open === b.id ? null : b.id)}>
                                        <td className="px-2 py-2.5 whitespace-nowrap">
                                            {formatDateEAT(b.created_at, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                                            <span className="ml-1.5 text-xs text-muted-foreground capitalize">{b.kind}</span>
                                            {b.encrypted && <Lock className="ml-1 inline h-3 w-3 text-muted-foreground" aria-label="Encrypted" />}
                                        </td>
                                        <td className="px-2 py-2.5">
                                            <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold',
                                                b.status === 'ok' ? 'bg-ok-bg text-ok' : b.status === 'partial' ? 'bg-warn-bg text-warn'
                                                    : b.status === 'failed' ? 'bg-bad-bg text-bad' : 'bg-chip text-muted-foreground')}>
                                                {b.status === 'running' && <Loader2 className="h-3 w-3 animate-spin" />}{b.status_label}
                                            </span>
                                        </td>
                                        <td className="px-2 py-2.5 whitespace-nowrap">{bytes(b.size)}{b.local_deleted && <span className="text-xs text-muted-foreground"> (removed here)</span>}</td>
                                        <td className="px-2 py-2.5 whitespace-nowrap">
                                            {(s?.gdrive_connected || b.remote_status) && <RemoteStatus status={b.remote_status} label={b.remote_status ? b.remote_label : 'Not on Drive'} />}
                                            {(s?.nas_enabled || b.nas_status) && <RemoteStatus status={b.nas_status} label={b.nas_status ? b.nas_label : 'Not on NAS'} />}
                                            {!s?.gdrive_connected && !s?.nas_enabled && !b.remote_status && !b.nas_status && <span className="text-xs text-muted-foreground">This server only</span>}
                                        </td>
                                        <td className="px-2 py-2.5 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                                            {b.downloadable && (
                                                <button title="Download" onClick={() => download(b)} className="p-1.5 text-muted-foreground hover:text-primary">
                                                    {busy === `dl${b.id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                                                </button>
                                            )}
                                            {b.downloadable && s?.gdrive_connected && ['', 'failed', 'deleted'].includes(b.remote_status) && (
                                                <button title="Upload to Google Drive" onClick={() => retry(b, 'gdrive')} className="p-1.5 text-muted-foreground hover:text-primary"><CloudUpload className="h-4 w-4" /></button>
                                            )}
                                            {b.downloadable && s?.nas_enabled && ['', 'failed', 'deleted'].includes(b.nas_status) && (
                                                <button title="Copy to the NAS" onClick={() => retry(b, 'nas')} className="p-1.5 text-muted-foreground hover:text-primary"><Network className="h-4 w-4" /></button>
                                            )}
                                            {b.status !== 'running' && (
                                                <button title="Delete" onClick={() => remove(b)} className="p-1.5 text-muted-foreground hover:text-bad"><Trash2 className="h-4 w-4" /></button>
                                            )}
                                            <ChevronDown className={cn('inline h-4 w-4 text-muted-foreground transition-transform', open === b.id && 'rotate-180')} />
                                        </td>
                                    </tr>
                                    {open === b.id && (
                                        <tr className="bg-secondary/60"><td colSpan={5} className="px-3 py-3 space-y-2 text-[13px]">
                                            <BackupDetails b={b} />
                                        </td></tr>
                                    )}
                                </Fragment>
                            ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function RemoteStatus({ status, label }: { status: string; label: string }) {
    return (
        <span className={cn('block text-xs', status === 'ok' ? 'text-ok' : status === 'failed' ? 'text-bad' : 'text-muted-foreground')}>
            {status === 'uploading' && <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />}{label}
        </span>
    );
}

function BackupDetails({ b }: { b: any }) {
    const c = b.contents || {};
    const routers: any[] = c.routers || [];
    return (
        <>
            {b.filename && <p className="font-mono text-xs break-all">{b.filename}{b.created_by && <span className="font-sans text-muted-foreground"> · by {b.created_by}</span>}</p>}
            {b.error && <p className="text-bad"><XCircle className="mr-1 inline h-4 w-4" />{b.error}</p>}
            <ul className="space-y-1">
                {c.database && <li><CheckCircle2 className="mr-1 inline h-4 w-4 text-ok" />Database ({c.database.engine}{c.database.size ? `, ${bytes(c.database.size)}` : ''})
                    {c.counts && <span className="text-muted-foreground"> — {c.counts.customers} customers, {c.counts.transactions} payments, {c.counts.vouchers} vouchers</span>}</li>}
                {routers.map((r) => (
                    <li key={r.name}>
                        {r.ok ? <CheckCircle2 className="mr-1 inline h-4 w-4 text-ok" /> : <XCircle className="mr-1 inline h-4 w-4 text-bad" />}
                        Router {r.name} ({r.ip}){r.ok ? `: ${r.files.join(', ')}` : `: ${r.error}`}
                    </li>
                ))}
                {c.media_files != null && <li><CheckCircle2 className="mr-1 inline h-4 w-4 text-ok" />{c.media_files} uploaded files</li>}
                {c.secrets && <li><Lock className="mr-1 inline h-4 w-4 text-ok" />Secrets: {c.secrets.join(', ')}</li>}
            </ul>
            {(b.warnings || []).length > 0 && (
                <ul className="space-y-1 text-warn">
                    {b.warnings.map((w: string) => <li key={w}><TriangleAlert className="mr-1 inline h-4 w-4" />{w}</li>)}
                </ul>
            )}
            {b.remote_error && <p className="text-bad">Google Drive: {b.remote_error}</p>}
            {b.nas_error && <p className="text-bad">NAS: {b.nas_error}</p>}
            {b.nas_status === 'ok' && b.nas_path && <p className="text-xs text-muted-foreground">On the NAS at <span className="font-mono">{b.nas_path}</span></p>}
            {b.sha256 && <p className="font-mono text-[11px] text-muted-foreground break-all">SHA-256 {b.sha256}</p>}
        </>
    );
}

function ScheduleSection() {
    const { data: s } = useBackupSettings();
    const save = useSave();
    const [keep, setKeep] = useState({ keep_local: '7', keep_remote: '30', keep_nas: '30' });
    useEffect(() => { if (s) setKeep({ keep_local: String(s.keep_local), keep_remote: String(s.keep_remote), keep_nas: String(s.keep_nas) }); }, [s]);
    if (!s) return null;
    const toggle = (field: string) => (e: React.ChangeEvent<HTMLInputElement>) => save.mutate({ [field]: e.target.checked });

    return (
        <div className={CARD}>
            <h3 className="text-lg font-bold mb-1">Automatic backups</h3>
            <p className="text-sm text-muted-foreground mb-4">Runs in the background; admins are notified if one fails.</p>
            <label className="flex items-center gap-2 text-sm mb-4">
                <input type="checkbox" checked={s.schedule_enabled} onChange={toggle('schedule_enabled')} /> Back up automatically
            </label>
            <fieldset disabled={!s.schedule_enabled || save.isPending} className="flex flex-wrap items-end gap-3 text-sm disabled:opacity-60">
                <label><span className="block mb-1 text-foreground/80">How often</span>
                    <select className={INPUT} value={s.frequency} onChange={(e) => save.mutate({ frequency: e.target.value })}>
                        <option value="daily">Every day</option><option value="weekly">Every week</option>
                    </select>
                </label>
                {s.frequency === 'weekly' && (
                    <label><span className="block mb-1 text-foreground/80">On</span>
                        <select className={INPUT} value={s.weekday} onChange={(e) => save.mutate({ weekday: Number(e.target.value) })}>
                            {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                        </select>
                    </label>
                )}
                <label><span className="block mb-1 text-foreground/80">At</span>
                    <select className={INPUT} value={s.hour} onChange={(e) => save.mutate({ hour: Number(e.target.value) })}>
                        {HOURS.map((h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}
                    </select>
                </label>
            </fieldset>

            <form className="mt-4 flex flex-wrap items-end gap-3 text-sm" onSubmit={(e) => { e.preventDefault(); save.mutate({ keep_local: Number(keep.keep_local), keep_remote: Number(keep.keep_remote), keep_nas: Number(keep.keep_nas) }); }}>
                <label><span className="block mb-1 text-foreground/80">Keep on this server</span>
                    <input type="number" min={1} max={365} className={cn(INPUT, 'w-28')} value={keep.keep_local} onChange={(e) => setKeep({ ...keep, keep_local: e.target.value })} />
                </label>
                <label><span className="block mb-1 text-foreground/80">Keep on Google Drive</span>
                    <input type="number" min={1} max={365} className={cn(INPUT, 'w-28')} value={keep.keep_remote} onChange={(e) => setKeep({ ...keep, keep_remote: e.target.value })} />
                </label>
                {s.nas_enabled && (
                    <label><span className="block mb-1 text-foreground/80">Keep on the NAS</span>
                        <input type="number" min={1} max={365} className={cn(INPUT, 'w-28')} value={keep.keep_nas} onChange={(e) => setKeep({ ...keep, keep_nas: e.target.value })} />
                    </label>
                )}
                <button className={cn(BTN, 'border')} disabled={save.isPending}>Save</button>
                <span className="text-xs text-muted-foreground pb-2">newest backups; older ones are deleted</span>
            </form>

            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mt-5 mb-2">Include</p>
            <div className="space-y-2 text-sm">
                <label className="flex items-center gap-2"><input type="checkbox" checked disabled /> Database (always)</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={s.include_routers} onChange={toggle('include_routers')} /> MikroTik configs (export + binary backup of every router)</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={s.include_media} onChange={toggle('include_media')} /> Uploaded files (logo, receipts, attachments)</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={s.include_secrets} onChange={toggle('include_secrets')} /> Server secrets and WhatsApp login (only in encrypted backups)</label>
            </div>
            {s.include_routers && (
                <p className="mt-2 text-xs text-muted-foreground">
                    The full export (.rsc) and binary backup are fetched over the router&apos;s FTP service. Where FTP is off, the backup still has the
                    settings read over the API, and the binary backup stays on the router as <span className="font-mono">isp-billing.backup</span>.
                </p>
            )}
        </div>
    );
}

function EncryptionSection() {
    const { data: s } = useBackupSettings();
    const save = useSave('Passphrase saved');
    const [pass, setPass] = useState('');
    const [confirm, setConfirm] = useState('');
    if (!s) return null;
    const submit = (e: React.FormEvent) => {
        e.preventDefault();
        if (pass !== confirm) { toast.error("The passphrases don't match"); return; }
        save.mutate({ encryption_passphrase: pass }, { onSuccess: () => { setPass(''); setConfirm(''); } });
    };
    return (
        <div className={CARD}>
            <h3 className="text-lg font-bold mb-1 flex items-center gap-2"><KeyRound className="h-5 w-5" /> Encryption</h3>
            <p className="text-sm text-muted-foreground mb-3">
                With a passphrase, backups are encrypted (AES-256) before they leave the server, and can include the server&apos;s secret keys and
                WhatsApp login — so a restore on a new host comes back fully working.{' '}
                <b className="text-foreground">Write the passphrase down somewhere safe: without it an encrypted backup cannot be restored.</b>
            </p>
            <p className="text-sm mb-3">
                {s.encryption_passphrase_set
                    ? <span className="text-ok"><Lock className="mr-1 inline h-4 w-4" />Backups are encrypted.</span>
                    : <span className="text-warn"><TriangleAlert className="mr-1 inline h-4 w-4" />Not encrypted — secrets and the WhatsApp login are left out.</span>}
            </p>
            <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2 items-end">
                <input type="password" autoComplete="new-password" className={INPUT} placeholder={s.encryption_passphrase_set ? 'New passphrase' : 'Passphrase (10+ characters)'} value={pass} onChange={(e) => setPass(e.target.value)} />
                <input type="password" autoComplete="new-password" className={INPUT} placeholder="Repeat it" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
                <button className={cn(BTN, 'bg-primary text-primary-foreground')} disabled={!pass || save.isPending}>{s.encryption_passphrase_set ? 'Change' : 'Set'}</button>
            </form>
            {s.encryption_passphrase_set && (
                <button className="mt-2 text-xs text-bad" onClick={() => window.confirm('Stop encrypting new backups? Existing ones still need the old passphrase.') && save.mutate({ clear_passphrase: true })}>
                    Remove passphrase
                </button>
            )}
            <p className="mt-2 text-xs text-muted-foreground">Changing it only affects new backups; older ones keep the passphrase they were made with.</p>
        </div>
    );
}

function DriveSection() {
    const qc = useQueryClient();
    const { data: s } = useBackupSettings();
    const save = useSave('Google settings saved');
    const [clientId, setClientId] = useState('');
    const [secret, setSecret] = useState('');
    const [flow, setFlow] = useState<{ user_code: string; verification_url: string; interval: number } | null>(null);
    const [testing, setTesting] = useState(false);
    useEffect(() => { if (s) setClientId(s.gdrive_client_id || ''); }, [s]);

    // Poll Google while the admin approves the sign-in on their phone/computer.
    useEffect(() => {
        if (!flow) return;
        let stop = false;
        let wait = Math.max(5, flow.interval) * 1000;
        const tick = async () => {
            if (stop) return;
            try {
                const res = (await backupAPI.pollDrive()).data;
                if (res.state === 'ok') {
                    toast.success(`Google Drive connected${res.account ? ` (${res.account})` : ''}`);
                    if (res.warning) toast.error(res.warning, { duration: 8000 });
                    setFlow(null);
                    qc.invalidateQueries({ queryKey: ['backup-settings'] });
                    return;
                }
                if (res.state === 'denied' || res.state === 'expired') {
                    toast.error(res.state === 'denied' ? 'Sign-in was declined' : 'The code expired — try again');
                    setFlow(null);
                    return;
                }
                if (res.state === 'slow_down') wait += 5000;
            } catch (err: any) {
                toast.error(getErrorMessage(err, 'Google sign-in failed'));
                setFlow(null);
                return;
            }
            setTimeout(tick, wait);
        };
        const t = setTimeout(tick, wait);
        return () => { stop = true; clearTimeout(t); };
    }, [flow, qc]);

    if (!s) return null;
    const connect = async () => {
        try { setFlow((await backupAPI.connectDrive()).data); }
        catch (err: any) { toast.error(getErrorMessage(err, 'Could not start Google sign-in')); }
    };
    const test = async () => {
        setTesting(true);
        try {
            const r = (await backupAPI.testDrive()).data;
            toast.success(`Working — ${r.account}${r.limit ? `, ${bytes(r.used)} of ${bytes(r.limit)} used` : ''}`);
        } catch (err: any) { toast.error(getErrorMessage(err, 'Google Drive test failed')); }
        finally { setTesting(false); }
    };
    const disconnect = async () => {
        if (!window.confirm('Disconnect Google Drive? Backups already there stay in your Drive.')) return;
        await backupAPI.disconnectDrive();
        qc.invalidateQueries({ queryKey: ['backup-settings'] });
    };

    return (
        <div className={CARD}>
            <h3 className="text-lg font-bold mb-1 flex items-center gap-2"><HardDrive className="h-5 w-5" /> Google Drive</h3>
            <p className="text-sm text-muted-foreground mb-3">
                Every backup is also uploaded to a folder in your Google Drive, so it survives if this server&apos;s SD card or disk dies.
                The app can only see the files it puts there.
            </p>

            {s.gdrive_connected ? (
                <div className="space-y-3">
                    <p className="text-sm"><CheckCircle2 className="mr-1 inline h-4 w-4 text-ok" />Connected as <b>{s.gdrive_account || 'your Google account'}</b>, folder “{s.gdrive_folder_name}”.</p>
                    <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={s.gdrive_enabled} onChange={(e) => save.mutate({ gdrive_enabled: e.target.checked })} /> Upload every backup to Google Drive
                    </label>
                    <div className="flex flex-wrap gap-2">
                        <button onClick={test} disabled={testing} className={cn(BTN, 'border')}>{testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Test</button>
                        <button onClick={disconnect} className={cn(BTN, 'border text-bad')}>Disconnect</button>
                    </div>
                </div>
            ) : (
                <>
                    <details className="mb-3 rounded-lg bg-secondary p-3 text-sm">
                        <summary className="cursor-pointer font-medium">One-time setup in Google Cloud (about 5 minutes)</summary>
                        <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
                            <li>Open <a className="text-primary underline" href="https://console.cloud.google.com/projectcreate" target="_blank" rel="noreferrer">console.cloud.google.com</a> and create a project (e.g. “ISP Backups”).</li>
                            <li>APIs &amp; Services → Library → enable <b>Google Drive API</b>.</li>
                            <li>OAuth consent screen: User type <b>External</b>, fill in the app name and your email, add yourself as a test user, then click <b>Publish app</b> (otherwise Google signs it out every 7 days).</li>
                            <li>Credentials → Create credentials → OAuth client ID → Application type <b>TVs and Limited Input devices</b>.</li>
                            <li>Paste the Client ID and Client secret below, save, then click Connect.</li>
                        </ol>
                    </details>
                    <form onSubmit={(e) => { e.preventDefault(); save.mutate({ gdrive_client_id: clientId.trim(), ...(secret ? { gdrive_client_secret: secret.trim() } : {}) }, { onSuccess: () => setSecret('') }); }}
                        className="space-y-2">
                        <input className={INPUT} placeholder="Client ID (….apps.googleusercontent.com)" value={clientId} onChange={(e) => setClientId(e.target.value)} />
                        <input type="password" className={INPUT} placeholder={s.gdrive_client_secret_set ? 'Client secret (saved — leave blank to keep)' : 'Client secret'} value={secret} onChange={(e) => setSecret(e.target.value)} />
                        <input className={INPUT} placeholder="Folder name in Drive" defaultValue={s.gdrive_folder_name}
                            onBlur={(e) => e.target.value !== s.gdrive_folder_name && save.mutate({ gdrive_folder_name: e.target.value })} />
                        <div className="flex flex-wrap gap-2">
                            <button className={cn(BTN, 'border')} disabled={save.isPending}>Save</button>
                            <button type="button" onClick={connect} disabled={!s.gdrive_client_id || !s.gdrive_client_secret_set || !!flow} className={cn(BTN, 'bg-primary text-primary-foreground')}>
                                Connect Google Drive
                            </button>
                        </div>
                    </form>
                    {flow && (
                        <div className="mt-4 rounded-lg border-2 border-primary/40 p-4 text-sm">
                            <p>On any phone or computer, open</p>
                            <a href={flow.verification_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary font-semibold underline">
                                {flow.verification_url} <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                            <p className="mt-2">and enter this code:</p>
                            <p className="my-2 flex items-center gap-3 font-mono text-2xl font-bold tracking-widest">
                                {flow.user_code}
                                <button onClick={() => { navigator.clipboard.writeText(flow.user_code); toast.success('Copied'); }} className="text-muted-foreground"><Copy className="h-4 w-4" /></button>
                            </p>
                            <p className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Waiting for you to approve…</p>
                            <button onClick={() => setFlow(null)} className="mt-2 text-xs text-muted-foreground underline">Cancel</button>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

/**
 * Synology NAS, by QuickConnect ID (File Station API through Synology's
 * directory/relay -- no port forwarding) or by direct WebDAV address. See
 * backend apps/backups/nas.py. The form tests the unsaved values first, so a
 * typo never gets saved as the setup the 2 a.m. backup silently fails on.
 */
function NasSection() {
    const { data: s } = useBackupSettings();
    const save = useSave('NAS settings saved');
    const blank = { nas_mode: 'quickconnect', nas_quickconnect_id: '', nas_url: '', nas_username: '', nas_password: '', nas_folder: '/backups/isp-billing', nas_verify_tls: true };
    const [form, setForm] = useState(blank);
    const [testing, setTesting] = useState(false);
    const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
    useEffect(() => {
        if (s) setForm({
            nas_mode: s.nas_mode || 'quickconnect', nas_quickconnect_id: s.nas_quickconnect_id || '', nas_url: s.nas_url || '',
            nas_username: s.nas_username || '', nas_password: '', nas_folder: s.nas_folder || '/backups/isp-billing', nas_verify_tls: s.nas_verify_tls,
        });
    }, [s]);
    if (!s) return null;
    const qc = form.nas_mode === 'quickconnect';
    const target = qc ? form.nas_quickconnect_id : form.nas_url;
    const set = (k: string, v: unknown) => { setForm({ ...form, [k]: v }); setResult(null); };
    const payload = () => {
        const { nas_password, ...rest } = form;
        return { ...rest, ...(nas_password ? { nas_password } : {}) };
    };
    const test = async () => {
        setTesting(true);
        try {
            const r = (await backupAPI.testNas(payload())).data;
            const via = r.via && qc ? (r.via.includes('.direct.') || !r.via.includes('quickconnect.to') ? ' (direct connection)' : ' (through the QuickConnect relay — slower)') : '';
            setResult({ ok: true, text: `Connected${via} — ${r.folder} is writable${r.free != null ? `, ${bytes(r.free)} free` : ''}.` });
            return true;
        } catch (err: any) {
            setResult({ ok: false, text: err?.response?.data?.error || getErrorMessage(err, 'Could not reach the NAS') });
            return false;
        } finally { setTesting(false); }
    };
    const submit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!(await test())) return;
        save.mutate({ ...payload(), nas_enabled: true }, { onSuccess: () => setForm((f) => ({ ...f, nas_password: '' })) });
    };

    return (
        <div className={CARD}>
            <h3 className="text-lg font-bold mb-1 flex items-center gap-2"><Server className="h-5 w-5" /> Synology NAS</h3>
            <p className="text-sm text-muted-foreground mb-3">
                Copies every backup to a folder on your Synology. Use it on its own or alongside Google Drive.
                For a real off-site copy, keep the NAS in a different building from this server.
            </p>
            {s.nas_password_set && (
                <label className="flex items-center gap-2 text-sm mb-3">
                    <input type="checkbox" checked={s.nas_enabled} onChange={(e) => save.mutate({ nas_enabled: e.target.checked })} /> Copy every backup to the NAS
                </label>
            )}
            <div className="mb-3 inline-flex rounded-lg border p-0.5 text-sm" role="radiogroup" aria-label="How to reach the NAS">
                {[['quickconnect', 'QuickConnect'], ['webdav', 'Direct address (WebDAV)']].map(([v, label]) => (
                    <button key={v} type="button" role="radio" aria-checked={form.nas_mode === v} onClick={() => set('nas_mode', v)}
                        className={cn('rounded-md px-3 py-1.5', form.nas_mode === v ? 'bg-primary text-primary-foreground' : 'text-muted-foreground')}>
                        {label}
                    </button>
                ))}
            </div>
            <details className="mb-3 rounded-lg bg-secondary p-3 text-sm" open={!s.nas_password_set}>
                <summary className="cursor-pointer font-medium">Setting up the NAS (DSM 7)</summary>
                <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
                    {qc ? (
                        <>
                            <li>Control Panel → External Access → <b>QuickConnect</b>: enable it and note the QuickConnect ID. Under Advanced → Permission settings, make sure <b>DSM</b> is allowed.</li>
                            <li>Control Panel → Shared Folder → create a folder (e.g. <span className="font-mono">backups</span>). Turn on the Recycle Bin, and if you have Snapshot Replication, schedule snapshots of it — that keeps your copies safe even if this server is ever compromised.</li>
                            <li>Control Panel → User → create a user just for this (e.g. <span className="font-mono">isp-backup</span>) with Read/Write on that folder only and the <b>File Station</b> application allowed. <b>Don&apos;t turn on 2-step verification</b> for it: an automatic backup can&apos;t type a code.</li>
                            <li>Enter the ID below. No port forwarding or VPN is needed: the server connects directly when it can, otherwise through Synology&apos;s relay (slower — Synology limits relay speed).</li>
                        </>
                    ) : (
                        <>
                            <li>Package Center → install <b>WebDAV Server</b> → open it and tick <b>Enable HTTPS</b> (port 5006).</li>
                            <li>Control Panel → Shared Folder → create a folder (e.g. <span className="font-mono">backups</span>). Turn on the Recycle Bin and, if you can, Snapshot Replication.</li>
                            <li>Control Panel → User → create a user just for this with Read/Write on that folder only (and, if Application Privileges lists WebDAV, allow it).</li>
                            <li>From this server the NAS must be reachable: same LAN, a VPN, or a DDNS name with port 5006 forwarded.</li>
                        </>
                    )}
                    <li>The folder path starts with the shared folder; sub-folders are created for you.</li>
                </ol>
            </details>
            <form onSubmit={submit} className="space-y-2 text-sm">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {qc
                        ? <input className={INPUT} placeholder="QuickConnect ID (quickconnect.to/…)" value={form.nas_quickconnect_id} onChange={(e) => set('nas_quickconnect_id', e.target.value)} />
                        : <input className={INPUT} placeholder="https://nas.example.com:5006" value={form.nas_url} onChange={(e) => set('nas_url', e.target.value)} />}
                    <input className={INPUT} placeholder="/backups/isp-billing" value={form.nas_folder} onChange={(e) => set('nas_folder', e.target.value)} />
                    <input className={INPUT} autoComplete="off" placeholder="NAS username" value={form.nas_username} onChange={(e) => set('nas_username', e.target.value)} />
                    <input type="password" autoComplete="new-password" className={INPUT} placeholder={s.nas_password_set ? 'Password (saved — leave blank to keep)' : 'Password'} value={form.nas_password} onChange={(e) => set('nas_password', e.target.value)} />
                </div>
                <label className="flex items-center gap-2">
                    <input type="checkbox" checked={form.nas_verify_tls} onChange={(e) => set('nas_verify_tls', e.target.checked)} />
                    {qc ? 'Verify the certificate on direct connections' : 'Verify the NAS certificate'}
                </label>
                {!form.nas_verify_tls && (
                    <p className="text-xs text-warn">
                        {qc
                            ? "Lets the server also try the NAS's plain IP addresses, which never match its certificate. Only turn this off if this server is on the NAS's own trusted LAN; the relay is always verified."
                            : "The connection is still encrypted, but this server can't tell your NAS from an impostor. Fine on your own LAN/VPN; prefer a Let's Encrypt certificate on the NAS otherwise."}
                    </p>
                )}
                {result && (
                    <p className={cn('text-sm', result.ok ? 'text-ok' : 'text-bad')}>
                        {result.ok ? <CheckCircle2 className="mr-1 inline h-4 w-4" /> : <XCircle className="mr-1 inline h-4 w-4" />}{result.text}
                    </p>
                )}
                <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={test} disabled={testing || !target} className={cn(BTN, 'border')}>
                        {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} {testing && qc ? 'Finding the NAS…' : 'Test'}
                    </button>
                    <button className={cn(BTN, 'bg-primary text-primary-foreground')} disabled={testing || save.isPending || !target || !form.nas_username || (!form.nas_password && !s.nas_password_set)}>
                        Test &amp; save
                    </button>
                </div>
            </form>
        </div>
    );
}

function CopyLine({ text }: { text: string }) {
    return (
        <div className="flex items-start gap-2 rounded-lg bg-secondary px-3 py-2 font-mono text-[12.5px]">
            <span className="flex-1 break-all">{text}</span>
            <button onClick={() => { navigator.clipboard.writeText(text); toast.success('Copied'); }} className="text-muted-foreground shrink-0" aria-label="Copy"><Copy className="h-4 w-4" /></button>
        </div>
    );
}

function MigrationSection() {
    const [checks, setChecks] = useState<any>(null);
    const [running, setRunning] = useState(false);
    const run = async () => {
        setRunning(true);
        try { setChecks((await backupAPI.migrationCheck()).data); }
        catch (err: any) { toast.error(getErrorMessage(err, 'Checks failed')); }
        finally { setRunning(false); }
    };
    return (
        <div className={CARD}>
            <h3 className="text-lg font-bold mb-1 flex items-center gap-2"><Server className="h-5 w-5" /> Move to a new host</h3>
            <p className="text-sm text-muted-foreground mb-3">
                Moves everything — database, uploaded files, WhatsApp login, backups, settings and certificates — to another machine with
                about a minute of downtime. Everything is copied and tested on the new host while this one keeps serving; then a short
                final copy, and this host forwards traffic to the new one until you&apos;ve switched DNS / port forwarding.
            </p>
            <ol className="space-y-3 text-sm">
                <li><b>1.</b> Prepare the new machine: install the OS, give it a fixed IP, and make sure it can reach your routers (same LAN or VPN). From your Mac, set up key login:
                    <CopyLine text="ssh-copy-id USER@NEW_HOST" /></li>
                <li><b>2.</b> From the project folder on your Mac — copies and tests everything, no downtime (safe to repeat):
                    <CopyLine text="./migrate_host.sh prepare NEW_HOST USER" /></li>
                <li><b>3.</b> Check the new host in a browser at https://NEW_HOST, then cut over (about a minute of downtime):
                    <CopyLine text="./migrate_host.sh cutover NEW_HOST USER" /></li>
                <li><b>4.</b> Point the domain / port-forward at the new host, then:
                    <CopyLine text="./migrate_host.sh finish NEW_HOST USER" />
                    <span className="text-muted-foreground">Something wrong? </span><span className="font-mono text-xs">./migrate_host.sh rollback NEW_HOST USER</span></li>
            </ol>
            <p className="mt-3 text-sm text-muted-foreground">
                If the old server is gone: deploy a fresh host, copy a backup from Google Drive onto it and run{' '}
                <span className="font-mono text-xs">python manage.py restore_backup FILE</span> (see DEPLOY.md).
            </p>

            <div className="mt-4 flex items-center gap-3">
                <button onClick={run} disabled={running} className={cn(BTN, 'border')}>
                    {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Run readiness checks on this server
                </button>
                {checks && <span className="text-xs text-muted-foreground">{checks.host} · {formatDateEAT(checks.checked_at, { hour: '2-digit', minute: '2-digit' })}</span>}
            </div>
            {checks && (
                <ul className="mt-3 space-y-1.5 text-sm">
                    {checks.checks.map((c: any) => (
                        <li key={c.name} className="flex items-start gap-2">
                            {c.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" /> : c.level === 'warn'
                                ? <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warn" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />}
                            <span><b className="font-medium">{c.name}</b>{c.detail && <span className="text-muted-foreground"> — {c.detail}</span>}</span>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
