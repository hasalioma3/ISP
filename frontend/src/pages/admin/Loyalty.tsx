import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Gift, Loader2, Search, Settings2, Sparkles } from 'lucide-react';
import { loyaltyAPI } from '../../services/api';
import { useAuthStore } from '../../store/authStore';
import { errText } from '../../utils/errText';
import { EmptyState, KpiCard, Panel, PanelHeader, ShellHeader, Skeleton, bandButtonClass, formatDateEAT } from '../../components/savanna';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { cn } from '@/lib/utils';

const INPUT = 'w-full border rounded-lg px-3 py-2 text-sm bg-card';
const LABEL = 'block text-sm font-medium text-foreground/80 mb-1';
const BTN = 'inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50';

const KIND_TONE: Record<string, string> = {
    earn: 'bg-ok-bg text-ok', bonus: 'bg-ok-bg text-ok', redeem: 'bg-sunset/15 text-sunset',
    adjust: 'bg-chip text-foreground', expire: 'bg-bad-bg text-bad',
};

/**
 * Loyalty programme: settings, programme totals, members by points, and
 * one member's history with redeem / adjust.
 */
export default function Loyalty() {
    const user = useAuthStore((s) => s.user);
    const isAdmin = !!user?.is_superuser || user?.role === 'admin';
    const [searchInput, setSearchInput] = useState('');
    const [search, setSearch] = useState('');
    const [showSettings, setShowSettings] = useState(false);
    const [open, setOpen] = useState<number | null>(null);
    const { data, isLoading } = useQuery({
        queryKey: ['loyalty-overview', search],
        queryFn: async () => (await loyaltyAPI.overview({ search: search || undefined })).data,
    });
    const st = data?.stats;
    const cfg = data?.settings;

    return (
        <div className="space-y-[18px]">
            <ShellHeader
                title="Loyalty"
                subtitle={cfg ? (cfg.enabled
                    ? `1 point per KES ${Number(cfg.kes_per_point).toLocaleString()} paid · 1 point = KES ${cfg.point_value_kes}`
                    : 'The programme is off. Turn it on in the programme settings.') : ' '}
                actions={isAdmin && (
                    <button className={bandButtonClass} onClick={() => setShowSettings((v) => !v)}>
                        <Settings2 className="h-[18px] w-[18px]" /> Programme settings
                    </button>
                )}
            />

            <div className="grid grid-cols-1 gap-[18px] sm:grid-cols-2 xl:grid-cols-4">
                <KpiCard label="Points outstanding" value={(st?.outstanding_points ?? 0).toLocaleString()} footnote={`Worth KES ${Number(st?.liability_kes ?? 0).toLocaleString()}`} />
                <KpiCard label="Earned this month" value={(st?.earned_this_month ?? 0).toLocaleString()} footnote="points" />
                <KpiCard label="Redeemed this month" value={(st?.redeemed_this_month ?? 0).toLocaleString()} footnote={`KES ${Number(st?.redeemed_kes_this_month ?? 0).toLocaleString()} credited`} />
                <KpiCard label="Members" value={(st?.members ?? 0).toLocaleString()} footnote="customers with points" />
            </div>

            {showSettings && isAdmin && <SettingsPanel onClose={() => setShowSettings(false)} />}

            <Panel>
                <PanelHeader
                    title="Members"
                    subtitle="Customers with points, highest balance first"
                    action={
                        <form onSubmit={(e) => { e.preventDefault(); setSearch(searchInput.trim()); }} className="relative">
                            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                            <input className="h-10 w-56 rounded-full border border-input bg-card pl-9 pr-4 text-[13.5px]" placeholder="Search name, phone…"
                                value={searchInput} onChange={(e) => setSearchInput(e.target.value)} />
                        </form>
                    }
                />
                {isLoading ? (
                    <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10" />)}</div>
                ) : !data?.members?.length ? (
                    <EmptyState message={search ? 'No members match.' : 'No one has earned points yet. Points are earned on each completed payment once the programme is on.'} />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-[13.5px]">
                            <thead>
                                <tr className="text-left text-[11.5px] uppercase tracking-wide text-faint">
                                    <th className="pb-2 pr-4 font-medium">Customer</th>
                                    <th className="pb-2 pr-4 font-medium">Service</th>
                                    <th className="pb-2 pr-4 text-right font-medium">Earned (all time)</th>
                                    <th className="pb-2 pr-4 text-right font-medium">Balance</th>
                                    <th className="pb-2 text-right font-medium">Worth</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.members.map((m: any) => (
                                    <tr key={m.customer_id} onClick={() => setOpen(m.customer_id)} className="cursor-pointer border-t border-border-soft hover:bg-secondary/60">
                                        <td className="py-2.5 pr-4"><p className="font-semibold">{m.name}</p><p className="text-xs text-muted-foreground">{m.username}{m.phone ? ` · ${m.phone}` : ''}</p></td>
                                        <td className="py-2.5 pr-4 uppercase text-xs text-muted-foreground">{m.service_type}</td>
                                        <td className="py-2.5 pr-4 text-right tabular-nums">{m.earned.toLocaleString()}</td>
                                        <td className="py-2.5 pr-4 text-right font-semibold tabular-nums">{m.points.toLocaleString()}</td>
                                        <td className="py-2.5 text-right tabular-nums">KES {Number(m.value_kes).toLocaleString()}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>

            <MemberDialog customerId={open} onClose={() => setOpen(null)} canAdjust={isAdmin} />
        </div>
    );
}

function SettingsPanel({ onClose }: { onClose: () => void }) {
    const qc = useQueryClient();
    const { data } = useQuery({ queryKey: ['loyalty-settings'], queryFn: async () => (await loyaltyAPI.getSettings()).data });
    const [f, setF] = useState<any>(null);
    useEffect(() => { if (data) setF(data); }, [data]);
    const save = useMutation({
        mutationFn: (d: Record<string, unknown>) => loyaltyAPI.updateSettings(d),
        onSuccess: () => { toast.success('Loyalty settings saved'); qc.invalidateQueries({ queryKey: ['loyalty-settings'] }); qc.invalidateQueries({ queryKey: ['loyalty-overview'] }); },
        onError: (e) => toast.error(errText(e, 'Could not save')),
    });
    if (!f) return <Panel><Loader2 className="h-4 w-4 animate-spin" /></Panel>;
    const set = (k: string, v: unknown) => setF({ ...f, [k]: v });
    const csv = (key: string, value: string, on: boolean) => {
        const s = new Set((f[key] || '').split(',').filter(Boolean));
        if (on) s.add(value); else s.delete(value);
        set(key, Array.from(s).join(','));
    };
    const example = Math.floor(2500 / Number(f.kes_per_point || 1));

    return (
        <Panel>
            <PanelHeader title="Programme settings" subtitle="Points are earned on M-Pesa, cash and bank payments (not on purchases paid from account balance)." />
            <label className="mb-4 flex items-center gap-2 text-sm font-medium">
                <input type="checkbox" checked={f.enabled} onChange={(e) => set('enabled', e.target.checked)} /> Loyalty programme is on
            </label>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div><label className={LABEL}>KES paid per point</label><input type="number" min={1} step="0.01" className={INPUT} value={f.kes_per_point} onChange={(e) => set('kes_per_point', e.target.value)} />
                    <p className="mt-1 text-xs text-muted-foreground">A KES 2,500 payment earns {example} points.</p></div>
                <div><label className={LABEL}>Value of 1 point (KES)</label><input type="number" min={0} step="0.01" className={INPUT} value={f.point_value_kes} onChange={(e) => set('point_value_kes', e.target.value)} /></div>
                <div><label className={LABEL}>Minimum points to redeem</label><input type="number" min={1} className={INPUT} value={f.min_redeem_points} onChange={(e) => set('min_redeem_points', Number(e.target.value))} /></div>
                <div><label className={LABEL}>Welcome bonus (points)</label><input type="number" min={0} className={INPUT} value={f.welcome_bonus} onChange={(e) => set('welcome_bonus', Number(e.target.value))} /></div>
                <div><label className={LABEL}>Points expire after (months, 0 = never)</label><input type="number" min={0} className={INPUT} value={f.expiry_months} onChange={(e) => set('expiry_months', Number(e.target.value))} /></div>
                <div className="text-sm">
                    <p className={LABEL}>Who takes part</p>
                    {[['pppoe', 'PPPoE'], ['static', 'Static IP'], ['hotspot', 'Hotspot']].map(([v, l]) => (
                        <label key={v} className="flex items-center gap-2"><input type="checkbox" checked={(f.service_types || '').split(',').includes(v)} onChange={(e) => csv('service_types', v, e.target.checked)} /> {l}</label>
                    ))}
                </div>
                <div className="text-sm">
                    <p className={LABEL}>Notify customers by</p>
                    {[['sms', 'SMS'], ['whatsapp', 'WhatsApp'], ['email', 'Email']].map(([v, l]) => (
                        <label key={v} className="flex items-center gap-2"><input type="checkbox" checked={(f.channels || '').split(',').includes(v)} onChange={(e) => csv('channels', v, e.target.checked)} /> {l}</label>
                    ))}
                </div>
                <div className="space-y-1 text-sm">
                    <p className={LABEL}>Messages and redemption</p>
                    <label className="flex items-center gap-2"><input type="checkbox" checked={f.notify_earn} onChange={(e) => set('notify_earn', e.target.checked)} /> Tell them when they earn</label>
                    <label className="flex items-center gap-2"><input type="checkbox" checked={f.notify_redeem} onChange={(e) => set('notify_redeem', e.target.checked)} /> Tell them when they redeem</label>
                    <label className="flex items-center gap-2"><input type="checkbox" checked={f.allow_self_redeem} onChange={(e) => set('allow_self_redeem', e.target.checked)} /> Customers can redeem themselves</label>
                </div>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">Redeemed points become KES on the customer&apos;s account balance, which pays toward their next renewal. Message wording is under Settings → Notifications → Message templates.</p>
            <div className="mt-4 flex gap-3">
                <button className={cn(BTN, 'bg-primary text-primary-foreground')} disabled={save.isPending} onClick={() => save.mutate(f)}>Save</button>
                <button className={cn(BTN, 'border')} onClick={onClose}>Close</button>
            </div>
        </Panel>
    );
}

function MemberDialog({ customerId, onClose, canAdjust }: { customerId: number | null; onClose: () => void; canAdjust: boolean }) {
    const qc = useQueryClient();
    const [points, setPoints] = useState('');
    const [reason, setReason] = useState('');
    const { data, isLoading } = useQuery({
        queryKey: ['loyalty-customer', customerId],
        queryFn: async () => (await loyaltyAPI.customer(customerId!)).data,
        enabled: customerId !== null,
    });
    const act = useMutation({
        mutationFn: (body: { action: 'redeem' | 'adjust'; points: number; reason?: string }) => loyaltyAPI.act(customerId!, body),
        onSuccess: (r, body) => {
            toast.success(body.action === 'redeem' ? `Redeemed; account balance is now KES ${r.data.account_balance}` : 'Points adjusted');
            setPoints(''); setReason('');
            qc.invalidateQueries({ queryKey: ['loyalty-customer', customerId] });
            qc.invalidateQueries({ queryKey: ['loyalty-overview'] });
        },
        onError: (e) => toast.error(errText(e)),
    });
    const n = Number(points);

    return (
        <Dialog open={customerId !== null} onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl">
                <DialogHeader><DialogTitle className="flex items-center gap-2"><Gift className="h-5 w-5" /> {data?.customer || 'Loyalty'}</DialogTitle></DialogHeader>
                {isLoading || !data ? <Skeleton className="h-40" /> : (
                    <div className="space-y-4">
                        <div className="flex flex-wrap items-center gap-6 rounded-xl bg-secondary p-4">
                            <div><p className="text-xs uppercase text-muted-foreground">Points</p><p className="text-2xl font-extrabold tabular-nums">{data.points.toLocaleString()}</p></div>
                            <div><p className="text-xs uppercase text-muted-foreground">Worth</p><p className="text-2xl font-extrabold tabular-nums">KES {Number(data.value_kes).toLocaleString()}</p></div>
                            {!data.enabled && <p className="text-xs text-warn">This customer isn&apos;t in the programme (it&apos;s off, or not for their service type).</p>}
                        </div>
                        <div className="flex flex-wrap items-end gap-3">
                            <div><label className={LABEL}>Points</label><input type="number" className="w-32 border rounded-lg px-3 py-2 text-sm" value={points} onChange={(e) => setPoints(e.target.value)} /></div>
                            {canAdjust && <div className="min-w-[180px] flex-1"><label className={LABEL}>Reason (for adjustments)</label><input className={INPUT} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Goodwill for outage" /></div>}
                            <button className={cn(BTN, 'bg-sunset text-white')} disabled={act.isPending || !(n > 0)}
                                onClick={() => act.mutate({ action: 'redeem', points: n })}>
                                <Sparkles className="h-4 w-4" /> Redeem {n > 0 ? `for KES ${(n * Number(data.point_value_kes)).toLocaleString()}` : ''}
                            </button>
                            {canAdjust && (
                                <button className={cn(BTN, 'border')} disabled={act.isPending || !n || !reason.trim()}
                                    onClick={() => act.mutate({ action: 'adjust', points: n, reason })}>
                                    {n < 0 ? 'Remove' : 'Add'} points
                                </button>
                            )}
                        </div>
                        {canAdjust && <p className="text-xs text-muted-foreground">Use a negative number to remove points.</p>}
                        <div className="max-h-80 overflow-y-auto rounded-lg border">
                            <table className="w-full text-[13px]">
                                <tbody>
                                    {data.entries.map((e: any) => (
                                        <tr key={e.id} className="border-b border-border-soft last:border-0">
                                            <td className="px-3 py-2 whitespace-nowrap text-muted-foreground">{formatDateEAT(e.created_at)}</td>
                                            <td className="px-3 py-2"><span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', KIND_TONE[e.kind])}>{e.kind}</span></td>
                                            <td className="px-3 py-2">{e.description}{e.created_by_username ? <span className="text-muted-foreground"> · {e.created_by_username}</span> : ''}</td>
                                            <td className={cn('px-3 py-2 text-right font-semibold tabular-nums', e.points < 0 ? 'text-bad' : 'text-ok')}>{e.points > 0 ? '+' : ''}{e.points}</td>
                                            <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{e.balance_after}</td>
                                        </tr>
                                    ))}
                                    {!data.entries.length && <tr><td className="p-4 text-center text-muted-foreground">No points activity yet.</td></tr>}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
