import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Pencil, Plus, Star, Trash2 } from 'lucide-react';
import { Chip, EmptyState, Panel, PanelHeader, ShellHeader, bandCtaClass, formatKES } from '@/components/savanna';
import { Button, Field, Input, Modal, Select, Spinner, Textarea, Toggle } from '~/components/ui';
import { api, errorText } from '~/lib/api';
import { useAuth } from '~/lib/auth';

const TYPES = [['pppoe', 'PPPoE'], ['hotspot', 'Hotspot'], ['static', 'Static IP']] as const;

const blank = {
    name: '', code: '', description: '', is_active: true, is_public: true, is_default: false, sort_order: 0,
    count_basis: 'active', service_types: 'pppoe,static', count_method: 'peak', tier_mode: 'graduated',
    base_fee: '0', included_subscribers: 0, minimum_charge: '0', maximum_charge: null as string | null,
    prorate_first_period: true, collection_fee_percent: null as string | null, settlement_fee_flat: null as string | null,
    tiers: [{ up_to: 200, unit_price: '30', flat_fee: '0' }, { up_to: null, unit_price: '20', flat_fee: '0' }] as any[],
};

export default function Pricing() {
    const isAdmin = useAuth((s) => s.user?.is_platform_admin);
    const qc = useQueryClient();
    const { data: plans, isLoading } = useQuery({ queryKey: ['plans'], queryFn: async () => (await api.get('/admin/plans/')).data });
    const [editing, setEditing] = useState<any>(null);
    const remove = useMutation({
        mutationFn: async (id: number) => api.delete(`/admin/plans/${id}/`),
        onSuccess: () => { toast.success('Deleted'); qc.invalidateQueries({ queryKey: ['plans'] }); },
        onError: (err) => toast.error(errorText(err)),
    });

    return (
        <>
            <ShellHeader title="Pricing" subtitle="What ISPs pay each month, by how many subscribers they serve."
                actions={isAdmin && <button className={bandCtaClass} onClick={() => setEditing({ ...blank })}><Plus className="h-4 w-4" />New plan</button>} />
            {isLoading ? <Panel><Spinner /></Panel> : !plans?.length ? (
                <Panel><EmptyState message="No pricing plans yet." action={isAdmin && <Button onClick={() => setEditing({ ...blank })}>Create one</Button>} /></Panel>
            ) : (
                <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
                    {plans.map((p: any) => (
                        <Panel key={p.id} className={p.is_active ? '' : 'opacity-60'}>
                            <PanelHeader title={<span className="flex items-center gap-2">{p.name}{p.is_default && <Star className="h-4 w-4 fill-sunset text-sunset" aria-label="Default" />}</span>}
                                subtitle={p.description || `${p.tenant_count} ISP${p.tenant_count === 1 ? '' : 's'}`}
                                action={isAdmin && <>
                                    <button className="p-1.5 text-muted-foreground hover:text-primary" aria-label="Edit" onClick={() => setEditing(p)}><Pencil className="h-4 w-4" /></button>
                                    {p.tenant_count === 0 && <button className="p-1.5 text-muted-foreground hover:text-bad" aria-label="Delete" onClick={() => window.confirm(`Delete ${p.name}?`) && remove.mutate(p.id)}><Trash2 className="h-4 w-4" /></button>}
                                </>} />
                            <div className="flex flex-wrap gap-1.5">
                                {!p.is_public && <Chip>Private</Chip>}{!p.is_active && <Chip>Inactive</Chip>}
                                <Chip>{p.tier_mode === 'graduated' ? 'Graduated' : 'Volume'}</Chip>
                                <Chip>{p.count_method === 'peak' ? 'Peak count' : p.count_method === 'average' ? 'Average count' : 'End-of-month count'}</Chip>
                                <Chip>{p.service_types.split(',').map((t: string) => TYPES.find((x) => x[0] === t)?.[1]).join(' + ')}</Chip>
                            </div>
                            <ul className="mt-4 space-y-1 text-[13.5px]">
                                {Number(p.base_fee) > 0 && <li className="flex justify-between"><span>Base fee</span><span className="num font-semibold">{formatKES(p.base_fee)}</span></li>}
                                {p.included_subscribers > 0 && <li className="flex justify-between"><span>Included subscribers</span><span className="num font-semibold">{p.included_subscribers}</span></li>}
                                {p.tiers.map((t: any, i: number) => (
                                    <li key={t.id} className="flex justify-between"><span>{i === 0 ? 'First' : 'Then'} {t.up_to ? `up to ${t.up_to}` : 'every one after'}</span><span className="num font-semibold">{formatKES(t.unit_price)} each</span></li>
                                ))}
                                {Number(p.minimum_charge) > 0 && <li className="flex justify-between text-muted-foreground"><span>Minimum</span><span className="num">{formatKES(p.minimum_charge)}</span></li>}
                                {p.maximum_charge && <li className="flex justify-between text-muted-foreground"><span>Cap</span><span className="num">{formatKES(p.maximum_charge)}</span></li>}
                            </ul>
                            <div className="mt-4 grid grid-cols-4 gap-2 rounded-xl bg-secondary p-3 text-center">
                                {p.examples.map((e: any) => (
                                    <div key={e.subscribers}><p className="text-[11.5px] text-muted-foreground">{e.subscribers} subs</p><p className="num text-[13px] font-bold">{formatKES(e.amount)}</p></div>
                                ))}
                            </div>
                        </Panel>
                    ))}
                </div>
            )}
            {editing && <PlanEditor plan={editing} onClose={() => setEditing(null)} />}
        </>
    );
}

function PlanEditor({ plan, onClose }: { plan: any; onClose: () => void }) {
    const qc = useQueryClient();
    const [p, setP] = useState<any>(() => ({ ...plan, tiers: plan.tiers.map((t: any) => ({ ...t })) }));
    const [count, setCount] = useState(300);
    const [quote, setQuote] = useState<any>(null);
    const set = (k: string, v: unknown) => setP((x: any) => ({ ...x, [k]: v }));
    const types = p.service_types.split(',').filter(Boolean);

    // Live price for the slider count, from the unsaved form.
    useEffect(() => {
        const t = setTimeout(async () => {
            try { setQuote((await api.post('/public/quote/', { count, plan: p })).data); } catch { setQuote(null); }
        }, 250);
        return () => clearTimeout(t);
    }, [p, count]);

    const save = useMutation({
        mutationFn: async () => {
            const body = { ...p, maximum_charge: p.maximum_charge || null, collection_fee_percent: p.collection_fee_percent === '' ? null : p.collection_fee_percent,
                settlement_fee_flat: p.settlement_fee_flat === '' ? null : p.settlement_fee_flat,
                tiers: p.tiers.map((t: any) => ({ up_to: t.up_to === '' || t.up_to == null ? null : Number(t.up_to), unit_price: t.unit_price || '0', flat_fee: t.flat_fee || '0' })) };
            return p.id ? (await api.patch(`/admin/plans/${p.id}/`, body)).data : (await api.post('/admin/plans/', body)).data;
        },
        onSuccess: () => { toast.success('Plan saved'); qc.invalidateQueries({ queryKey: ['plans'] }); onClose(); },
        onError: (err) => toast.error(errorText(err)),
    });
    const setTier = (i: number, k: string, v: unknown) => set('tiers', p.tiers.map((t: any, j: number) => (j === i ? { ...t, [k]: v } : t)));

    return (
        <Modal open onClose={onClose} wide title={p.id ? `Edit ${plan.name}` : 'New pricing plan'} description="Changes apply to the next invoice of every ISP on this plan.">
            <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Name"><Input value={p.name} onChange={(e) => set('name', e.target.value)} /></Field>
                <Field label="Code" hint="Used in links, e.g. standard"><Input value={p.code} onChange={(e) => set('code', e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))} /></Field>
                <Field label="Description" className="sm:col-span-2"><Textarea className="min-h-[60px]" value={p.description} onChange={(e) => set('description', e.target.value)} /></Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Count">
                    <Select value={p.count_basis} onChange={(e) => set('count_basis', e.target.value)}>
                        <option value="active">Subscribers with an active plan</option><option value="all">All subscriber accounts</option>
                    </Select>
                </Field>
                <Field label="Over the month, use the">
                    <Select value={p.count_method} onChange={(e) => set('count_method', e.target.value)}>
                        <option value="peak">Highest count</option><option value="average">Average count</option><option value="latest">Count at month end</option>
                    </Select>
                </Field>
                <Field label="Tier pricing">
                    <Select value={p.tier_mode} onChange={(e) => set('tier_mode', e.target.value)}>
                        <option value="graduated">Graduated (each tier its own price)</option><option value="volume">Volume (one price for all)</option>
                    </Select>
                </Field>
            </div>
            <div>
                <p className="mb-2 text-[13px] font-semibold">Which subscribers count</p>
                <div className="flex flex-wrap gap-4">
                    {TYPES.map(([v, label]) => (
                        <label key={v} className="flex items-center gap-2 text-[14px]">
                            <input type="checkbox" checked={types.includes(v)} onChange={(e) => set('service_types', (e.target.checked ? [...types, v] : types.filter((x: string) => x !== v)).join(','))} />{label}
                        </label>
                    ))}
                </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-4">
                <Field label="Base fee"><Input type="number" min={0} value={p.base_fee} onChange={(e) => set('base_fee', e.target.value)} /></Field>
                <Field label="Included subs"><Input type="number" min={0} value={p.included_subscribers} onChange={(e) => set('included_subscribers', Number(e.target.value))} /></Field>
                <Field label="Minimum"><Input type="number" min={0} value={p.minimum_charge} onChange={(e) => set('minimum_charge', e.target.value)} /></Field>
                <Field label="Cap" hint="blank = none"><Input type="number" min={0} value={p.maximum_charge ?? ''} onChange={(e) => set('maximum_charge', e.target.value || null)} /></Field>
            </div>

            <div>
                <p className="mb-2 text-[13px] font-semibold">Price per subscriber{p.included_subscribers > 0 && ` (after the ${p.included_subscribers} included)`}</p>
                <div className="space-y-2">
                    {p.tiers.map((t: any, i: number) => (
                        <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] items-center gap-2">
                            <Input type="number" min={1} placeholder="Up to (blank = no limit)" value={t.up_to ?? ''} onChange={(e) => setTier(i, 'up_to', e.target.value === '' ? null : e.target.value)} aria-label="Up to" />
                            <Input type="number" min={0} step="0.5" placeholder="Price each" value={t.unit_price} onChange={(e) => setTier(i, 'unit_price', e.target.value)} aria-label="Price each" />
                            <Input type="number" min={0} placeholder="Flat fee" value={t.flat_fee} onChange={(e) => setTier(i, 'flat_fee', e.target.value)} aria-label="Flat fee" />
                            <button className="p-2 text-muted-foreground hover:text-bad" aria-label="Remove tier" onClick={() => set('tiers', p.tiers.filter((_: any, j: number) => j !== i))}><Trash2 className="h-4 w-4" /></button>
                        </div>
                    ))}
                    <Button size="sm" variant="outline" onClick={() => set('tiers', [...p.tiers, { up_to: null, unit_price: '0', flat_fee: '0' }])}><Plus />Add tier</Button>
                </div>
            </div>

            <div className="rounded-2xl bg-secondary p-4">
                <div className="flex items-center justify-between gap-3 text-[14px]">
                    <span>An ISP with <b className="num">{count}</b> counted subscribers pays</span>
                    <span className="num text-[20px] font-extrabold">{quote ? formatKES(quote.amount) : '…'}</span>
                </div>
                <input type="range" min={0} max={5000} step={10} value={count} onChange={(e) => setCount(Number(e.target.value))} className="mt-2 w-full" aria-label="Subscribers" />
                {quote?.lines?.length > 0 && <ul className="mt-2 space-y-0.5 text-[12.5px] text-muted-foreground">{quote.lines.map((l: any, i: number) => <li key={i} className="flex justify-between"><span>{l.label}</span><span className="num">{formatKES(l.amount)}</span></li>)}</ul>}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Collection fee %" hint="Of each customer payment. Blank = platform default"><Input type="number" min={0} step="0.1" value={p.collection_fee_percent ?? ''} onChange={(e) => set('collection_fee_percent', e.target.value)} /></Field>
                <Field label="Payout fee (KES)" hint="Per payout. Blank = platform default"><Input type="number" min={0} value={p.settlement_fee_flat ?? ''} onChange={(e) => set('settlement_fee_flat', e.target.value)} /></Field>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
                <Toggle checked={p.is_active} onChange={(v) => set('is_active', v)} label="Active" />
                <Toggle checked={p.is_public} onChange={(v) => set('is_public', v)} label="Offered on sign-up" />
                <Toggle checked={p.is_default} onChange={(v) => set('is_default', v)} label="Default plan" hint="For ISPs that pick nothing" />
                <Toggle checked={p.prorate_first_period} onChange={(v) => set('prorate_first_period', v)} label="Prorate the first month" />
            </div>
            <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={onClose}>Cancel</Button>
                <Button onClick={() => save.mutate()} disabled={save.isPending || !p.name || !p.code}>{save.isPending && <Spinner />}Save plan</Button>
            </div>
        </Modal>
    );
}
