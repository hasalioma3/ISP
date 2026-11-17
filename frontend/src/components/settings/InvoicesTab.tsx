import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { BadgeCheck, CheckCircle2, FileText, Loader2, ShieldCheck } from 'lucide-react';
import { invoiceAPI } from '../../services/api';
import { errText } from '../../utils/errText';
import { formatDateEAT } from '../savanna';
import { cn } from '@/lib/utils';

const CARD = 'bg-card border rounded-lg p-4 sm:p-5';
const INPUT = 'w-full border rounded-lg px-3 py-2 text-sm';
const LABEL = 'block text-sm font-medium text-foreground/80 mb-1';
const BTN = 'inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50';

export const TEMPLATE_INFO: Record<string, string> = {
    classic: 'Logo and company top-left, bold title, shaded item table. The familiar accounting-package look.',
    modern: 'A full-width colour band header with tinted detail cards.',
    minimal: 'Black on white with hairlines and lots of whitespace.',
    bold: 'A coloured sidebar carrying your company, the customer and the amount.',
    compact: 'An 80 mm receipt for thermal printers and phone screens.',
};

/** A PDF preview of `template` (the sample invoice, or a real one via `load`). */
export function PdfPreview({ load, deps, className }: { load: () => Promise<Blob>; deps: unknown[]; className?: string }) {
    const [url, setUrl] = useState<string>('');
    const [loading, setLoading] = useState(true);
    useEffect(() => {
        let alive = true;
        let made = '';
        setLoading(true);
        load().then((blob) => {
            if (!alive) return;
            made = URL.createObjectURL(blob);
            setUrl(made);
        }).catch(() => alive && setUrl('')).finally(() => alive && setLoading(false));
        return () => { alive = false; if (made) URL.revokeObjectURL(made); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, deps);
    return (
        <div className={cn('relative overflow-hidden rounded-lg border bg-secondary', className)}>
            {loading && <div className="absolute inset-0 grid place-items-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>}
            {url && <iframe title="Invoice preview" src={`${url}#toolbar=0&navpanes=0&view=FitH`} className="h-full w-full" />}
        </div>
    );
}

/**
 * Settings -> Invoices: how invoices look (design, colour, company details),
 * VAT, numbering, automatic invoicing of PPPoE payments, and KRA eTIMS.
 */
export default function InvoicesTab() {
    const qc = useQueryClient();
    const { data: s, isLoading } = useQuery({ queryKey: ['invoice-settings'], queryFn: async () => (await invoiceAPI.getSettings()).data });
    const [form, setForm] = useState<any>(null);
    useEffect(() => { if (s) setForm({ ...s, etims_cmc_key: '' }); }, [s]);
    const [previewKey, setPreviewKey] = useState(0);
    const save = useMutation({
        mutationFn: (data: Record<string, unknown>) => invoiceAPI.updateSettings(data),
        onSuccess: () => { toast.success('Invoice settings saved'); qc.invalidateQueries({ queryKey: ['invoice-settings'] }); setPreviewKey((k) => k + 1); },
        onError: (e) => toast.error(errText(e, 'Could not save')),
    });
    const etims = useMutation({
        mutationFn: (action: 'initialize' | 'register_item') => invoiceAPI.etims(action),
        onSuccess: (r) => { toast.success(r.data.message); qc.invalidateQueries({ queryKey: ['invoice-settings'] }); },
        onError: (e) => toast.error(errText(e)),
    });

    if (isLoading || !form) return <div className="text-sm text-muted-foreground"><Loader2 className="inline h-4 w-4 animate-spin" /> Loading…</div>;
    const set = (k: string, v: unknown) => setForm({ ...form, [k]: v });
    const saveFields = (keys: string[]) => save.mutate(Object.fromEntries(keys.map((k) => [k, form[k]])));

    return (
        <div className="space-y-6 max-w-5xl">
            <div className={CARD}>
                <h3 className="text-lg font-bold mb-1 flex items-center gap-2"><FileText className="h-5 w-5" /> Invoice design</h3>
                <p className="text-sm text-muted-foreground mb-4">Pick the default design. Staff can still choose another one for any single invoice.</p>
                <div className="grid gap-5 lg:grid-cols-[1fr_1.2fr]">
                    <div className="space-y-2">
                        {(s.templates || []).map((t: any) => (
                            <button key={t.key} type="button" onClick={() => save.mutate({ default_template: t.key })}
                                className={cn('w-full rounded-xl border p-3 text-left transition-colors',
                                    s.default_template === t.key ? 'border-primary bg-primary/5 ring-1 ring-primary' : 'hover:bg-secondary')}>
                                <span className="flex items-center justify-between font-semibold text-sm">
                                    {t.label}
                                    {s.default_template === t.key && <CheckCircle2 className="h-4 w-4 text-primary" />}
                                </span>
                                <span className="text-xs text-muted-foreground">{TEMPLATE_INFO[t.key]}</span>
                            </button>
                        ))}
                        <div className="flex flex-wrap items-end gap-3 pt-2">
                            <div>
                                <label className={LABEL}>Accent colour</label>
                                <div className="flex items-center gap-2">
                                    <input type="color" value={form.accent_color} onChange={(e) => set('accent_color', e.target.value)} className="h-9 w-12 rounded border" />
                                    <input className="w-28 border rounded-lg px-2 py-1.5 text-sm font-mono" value={form.accent_color} onChange={(e) => set('accent_color', e.target.value)} />
                                </div>
                            </div>
                            <label className="flex items-center gap-2 text-sm pb-2">
                                <input type="checkbox" checked={form.show_logo} onChange={(e) => set('show_logo', e.target.checked)} /> Show logo
                            </label>
                            <button className={cn(BTN, 'bg-primary text-primary-foreground')} disabled={save.isPending}
                                onClick={() => saveFields(['accent_color', 'show_logo'])}>Apply</button>
                        </div>
                    </div>
                    <PdfPreview className="h-[520px]" deps={[s.default_template, previewKey]}
                        load={async () => (await invoiceAPI.preview(s.default_template)).data} />
                </div>
            </div>

            <div className={CARD}>
                <h3 className="text-lg font-bold mb-1">Company details on invoices</h3>
                <p className="text-sm text-muted-foreground mb-4">The company name and logo come from General Settings.</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div><label className={LABEL}>KRA PIN</label><input className={INPUT} placeholder="P051234567X" value={form.company_pin} onChange={(e) => set('company_pin', e.target.value.toUpperCase())} /></div>
                    <div><label className={LABEL}>Phone</label><input className={INPUT} value={form.company_phone} onChange={(e) => set('company_phone', e.target.value)} /></div>
                    <div><label className={LABEL}>Email</label><input className={INPUT} type="email" value={form.company_email} onChange={(e) => set('company_email', e.target.value)} /></div>
                    <div><label className={LABEL}>Address</label><textarea rows={2} className={INPUT} value={form.company_address} onChange={(e) => set('company_address', e.target.value)} /></div>
                    <div><label className={LABEL}>How to pay (shown on unpaid invoices)</label><textarea rows={2} className={INPUT} placeholder="M-Pesa Paybill 123456, account: your username" value={form.payment_details} onChange={(e) => set('payment_details', e.target.value)} /></div>
                    <div><label className={LABEL}>Terms</label><textarea rows={2} className={INPUT} value={form.terms} onChange={(e) => set('terms', e.target.value)} /></div>
                    <div className="sm:col-span-2"><label className={LABEL}>Footer note</label><input className={INPUT} value={form.footer_note} onChange={(e) => set('footer_note', e.target.value)} /></div>
                </div>
                <button className={cn(BTN, 'bg-primary text-primary-foreground mt-4')} disabled={save.isPending}
                    onClick={() => saveFields(['company_pin', 'company_phone', 'company_email', 'company_address', 'payment_details', 'terms', 'footer_note'])}>
                    Save company details
                </button>
            </div>

            <div className={CARD}>
                <h3 className="text-lg font-bold mb-3">Tax, numbering and automation</h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <label className="flex items-center gap-2 text-sm sm:col-span-3">
                        <input type="checkbox" checked={form.vat_registered} onChange={(e) => set('vat_registered', e.target.checked)} /> We are VAT registered (invoices become tax invoices)
                    </label>
                    <div><label className={LABEL}>VAT rate (%)</label><input type="number" step="0.01" className={INPUT} disabled={!form.vat_registered} value={form.vat_rate} onChange={(e) => set('vat_rate', e.target.value)} /></div>
                    <label className="flex items-center gap-2 text-sm sm:col-span-2 pt-6">
                        <input type="checkbox" disabled={!form.vat_registered} checked={form.prices_include_vat} onChange={(e) => set('prices_include_vat', e.target.checked)} /> Plan prices already include VAT
                    </label>
                    <div><label className={LABEL}>Number prefix</label><input className={INPUT} value={form.number_prefix} onChange={(e) => set('number_prefix', e.target.value)} /></div>
                    <div><label className={LABEL}>Next number</label><input type="number" min={1} className={INPUT} value={form.next_number} onChange={(e) => set('next_number', Number(e.target.value))} /></div>
                    <div><label className={LABEL}>Payment due after (days)</label><input type="number" min={0} className={INPUT} value={form.due_days} onChange={(e) => set('due_days', Number(e.target.value))} /></div>
                    <label className="flex items-center gap-2 text-sm sm:col-span-3 border-t pt-4">
                        <input type="checkbox" checked={form.auto_invoice} onChange={(e) => set('auto_invoice', e.target.checked)} />
                        Create an invoice automatically for every PPPoE / static IP payment
                    </label>
                    <label className="flex items-center gap-2 text-sm sm:col-span-3">
                        <input type="checkbox" checked={form.auto_send} disabled={!form.auto_invoice} onChange={(e) => set('auto_send', e.target.checked)} />
                        …and email it to customers who have an email address (needs Email set up under Notifications)
                    </label>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">Next invoice: <span className="font-mono">{form.number_prefix}{String(form.next_number).padStart(5, '0')}</span></p>
                <button className={cn(BTN, 'bg-primary text-primary-foreground mt-4')} disabled={save.isPending}
                    onClick={() => saveFields(['vat_registered', 'vat_rate', 'prices_include_vat', 'number_prefix', 'next_number', 'due_days', 'auto_invoice', 'auto_send'])}>
                    Save
                </button>
            </div>

            <div className={CARD}>
                <h3 className="text-lg font-bold mb-1 flex items-center gap-2"><ShieldCheck className="h-5 w-5" /> KRA eTIMS</h3>
                <p className="text-sm text-muted-foreground mb-4">
                    Report invoices to KRA through eTIMS (OSCU). Signed invoices carry KRA&apos;s receipt signature and QR code.
                    Register an OSCU for your PIN on the eTIMS portal first; it gives you the device serial number.
                    Leave this off if you are not required to use eTIMS.
                </p>
                <label className="flex items-center gap-2 text-sm mb-4">
                    <input type="checkbox" checked={form.etims_enabled} onChange={(e) => set('etims_enabled', e.target.checked)} /> Use KRA eTIMS
                </label>
                <div className={cn('grid grid-cols-1 sm:grid-cols-3 gap-4', !form.etims_enabled && 'opacity-60')}>
                    <div>
                        <label className={LABEL}>Environment</label>
                        <select className={INPUT} value={form.etims_environment} onChange={(e) => set('etims_environment', e.target.value)}>
                            <option value="sandbox">Sandbox (testing)</option>
                            <option value="production">Production</option>
                        </select>
                    </div>
                    <div><label className={LABEL}>Branch ID</label><input className={INPUT} value={form.etims_branch_id} onChange={(e) => set('etims_branch_id', e.target.value)} /></div>
                    <div><label className={LABEL}>OSCU device serial</label><input className={INPUT} value={form.etims_device_serial} onChange={(e) => set('etims_device_serial', e.target.value)} /></div>
                    <div>
                        <label className={LABEL}>Tax type</label>
                        <select className={INPUT} value={form.etims_tax_type} onChange={(e) => set('etims_tax_type', e.target.value)}>
                            <option value="B">B: VAT 16%</option>
                            <option value="E">E: VAT 8%</option>
                            <option value="C">C: Zero rated</option>
                            <option value="A">A: Exempt</option>
                            <option value="D">D: Non-VAT</option>
                        </select>
                    </div>
                    <div><label className={LABEL}>Item class code</label><input className={INPUT} value={form.etims_item_class_code} onChange={(e) => set('etims_item_class_code', e.target.value)} /></div>
                    <div><label className={LABEL}>Item code</label><input className={INPUT} placeholder="KE3NTU0000001" value={form.etims_item_code} onChange={(e) => set('etims_item_code', e.target.value)} /></div>
                    <div className="sm:col-span-2">
                        <label className={LABEL}>CMC key {s.etims_cmc_key_set && <span className="text-ok font-normal">(saved)</span>}</label>
                        <input className={INPUT} type="password" autoComplete="off" placeholder={s.etims_cmc_key_set ? 'Leave blank to keep the saved key' : 'Filled in by "Initialise device"'}
                            value={form.etims_cmc_key} onChange={(e) => set('etims_cmc_key', e.target.value)} />
                    </div>
                    <div><label className={LABEL}>Custom API URL (optional)</label><input className={INPUT} placeholder="Standard KRA URL" value={form.etims_base_url} onChange={(e) => set('etims_base_url', e.target.value)} /></div>
                    <label className="flex items-center gap-2 text-sm sm:col-span-3">
                        <input type="checkbox" checked={form.etims_auto_sign} onChange={(e) => set('etims_auto_sign', e.target.checked)} /> Sign every new invoice automatically (otherwise use "Sign with KRA" on each invoice)
                    </label>
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                    <button className={cn(BTN, 'bg-primary text-primary-foreground')} disabled={save.isPending}
                        onClick={() => saveFields(['etims_enabled', 'etims_environment', 'etims_branch_id', 'etims_device_serial', 'etims_tax_type',
                            'etims_item_class_code', 'etims_item_code', 'etims_cmc_key', 'etims_base_url', 'etims_auto_sign'])}>
                        Save eTIMS settings
                    </button>
                    <button className={cn(BTN, 'border')} disabled={!s.etims_enabled || etims.isPending} onClick={() => etims.mutate('initialize')}>
                        {etims.isPending && etims.variables === 'initialize' ? <Loader2 className="h-4 w-4 animate-spin" /> : <BadgeCheck className="h-4 w-4" />} Initialise device
                    </button>
                    <button className={cn(BTN, 'border')} disabled={!s.etims_enabled || !s.etims_cmc_key_set || etims.isPending} onClick={() => etims.mutate('register_item')}>
                        Register item with KRA
                    </button>
                </div>
                <div className="mt-3 text-xs text-muted-foreground space-y-0.5">
                    {s.etims_initialized_at
                        ? <p className="text-ok">Device initialised {formatDateEAT(s.etims_initialized_at)}{s.etims_sdc_id ? ` · SCU ${s.etims_sdc_id}` : ''}</p>
                        : <p>Save the PIN (above), serial and branch first, then initialise the device once.</p>}
                    <p>Invoices reported so far: {s.etims_last_invoice_no}. Invoices that KRA couldn&apos;t sign are retried every 6 hours.</p>
                </div>
            </div>
        </div>
    );
}
