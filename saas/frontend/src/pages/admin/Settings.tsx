import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { AlertTriangle, CheckCircle2, Copy, KeyRound, Plug, RefreshCw } from 'lucide-react';
import { MpesaBadge, Panel, PanelHeader, ShellHeader } from '@/components/savanna';
import { Button, Field, Input, Notice, Select, Spinner, Textarea, Toggle } from '~/components/ui';
import { api, errorText } from '~/lib/api';
import { useAuth } from '~/lib/auth';
import { dateTime } from '~/lib/format';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const SECRET_FIELDS = ['mpesa_passkey', 'mpesa_consumer_key', 'mpesa_consumer_secret', 'tenant_consumer_key', 'tenant_consumer_secret', 'initiator_password', 'mpesa_certificate'];

export default function Settings() {
    const isAdmin = !!useAuth((s) => s.user?.is_platform_admin);
    const qc = useQueryClient();
    const { data: s, isLoading } = useQuery({ queryKey: ['platform-settings'], queryFn: async () => (await api.get('/admin/settings/')).data });
    const [form, setForm] = useState<any>(null);
    useEffect(() => { if (s) setForm({ ...s, ...Object.fromEntries(SECRET_FIELDS.map((k) => [k, ''])) }); }, [s]);
    const save = useMutation({
        mutationFn: async (fields: string[]) => (await api.patch('/admin/settings/', Object.fromEntries(fields.map((f) => [f, form[f]])))).data,
        onSuccess: (d) => { toast.success(d.resynced ? 'Saved -- re-applying to every ISP instance' : 'Saved'); qc.invalidateQueries({ queryKey: ['platform-settings'] }); },
        onError: (err) => toast.error(errorText(err)),
    });
    const mpesa = useMutation({
        mutationFn: async (action: string) => (await api.post('/admin/settings/mpesa/', { action })).data,
        onSuccess: (d, action) => { toast.success(action === 'test' ? `Safaricom accepted: ${Object.keys(d).filter((k) => k !== 'ok').join(', ')}` : 'C2B URLs registered'); qc.invalidateQueries({ queryKey: ['platform-settings'] }); },
        onError: (err) => toast.error(errorText(err)),
    });
    if (isLoading || !form) return <Panel><Spinner /></Panel>;
    const set = (k: string, v: unknown) => setForm((f: any) => ({ ...f, [k]: v }));
    const text = (k: string, props: any = {}) => <Input disabled={!isAdmin} value={form[k] ?? ''} onChange={(e) => set(k, e.target.value)} {...props} />;
    const num = (k: string, props: any = {}) => <Input disabled={!isAdmin} type="number" value={form[k] ?? ''} onChange={(e) => set(k, e.target.value)} {...props} />;
    const secret = (k: string) => <Input disabled={!isAdmin} type="password" autoComplete="new-password" value={form[k]} onChange={(e) => set(k, e.target.value)} placeholder={s[`${k}_set`] ? 'Saved -- leave blank to keep' : 'Not set'} />;
    const SaveBtn = ({ fields }: { fields: string[] }) => isAdmin ? (
        <div className="mt-5 flex justify-end"><Button onClick={() => save.mutate(fields)} disabled={save.isPending}>{save.isPending && <Spinner />}Save</Button></div>
    ) : null;
    const copy = (v: string) => { navigator.clipboard.writeText(v); toast.success('Copied'); };

    return (
        <>
            <ShellHeader title="Settings" subtitle={isAdmin ? 'How the platform runs, collects and pays out.' : 'Read-only: only platform admins can change these.'} />
            {s.warnings?.length > 0 && (
                <Panel className="mb-5">
                    <PanelHeader title="Before going live" />
                    <ul className="space-y-2">{s.warnings.map((w: string) => <li key={w} className="flex gap-2 text-[14px] text-warn"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{w}</li>)}</ul>
                </Panel>
            )}
            <div className="grid gap-5 xl:grid-cols-2">
                <Panel>
                    <PanelHeader title="Platform" />
                    <div className="grid gap-4 sm:grid-cols-2">
                        <Field label="Brand name">{text('brand_name')}</Field>
                        <Field label="Public address of this app" hint="HTTPS. Safaricom sends every payment here.">{text('public_base_url', { placeholder: 'https://cloud.example.com' })}</Field>
                        <Field label="Support email">{text('support_email')}</Field>
                        <Field label="Support phone">{text('support_phone')}</Field>
                        <Field label="ISP instances' host" hint="IP or domain the instances are reached on">{text('tenant_host')}</Field>
                        <Field label="Instance address" hint="{host} {port} {slug}">{text('tenant_url_template')}</Field>
                        <Field label="Ports from">{num('port_range_start')}</Field>
                        <Field label="to">{num('port_range_end')}</Field>
                        <Field label="Most ISPs on this server">{num('max_tenants')}</Field>
                    </div>
                    <SaveBtn fields={['brand_name', 'public_base_url', 'support_email', 'support_phone', 'tenant_host', 'tenant_url_template', 'port_range_start', 'port_range_end', 'max_tenants']} />
                </Panel>

                <Panel>
                    <PanelHeader title="Sign-ups, trials & invoices" />
                    <div className="space-y-4">
                        <Toggle disabled={!isAdmin} checked={form.signup_enabled} onChange={(v) => set('signup_enabled', v)} label="Accept new sign-ups" />
                        <div className="grid gap-4 sm:grid-cols-3">
                            <Field label="Free trial (days)">{num('trial_days', { min: 0, max: 60 })}</Field>
                            <Field label="Overdue grace (days)" hint="before suspension">{num('grace_days')}</Field>
                            <Field label="Keep suspended (days)" hint="before deletion is allowed">{num('retention_days')}</Field>
                            <Field label="Invoice on day">{num('invoice_day', { min: 1, max: 28 })}</Field>
                            <Field label="Due after (days)">{num('invoice_due_days')}</Field>
                        </div>
                        <Toggle disabled={!isAdmin} checked={form.auto_deduct_invoices} onChange={(v) => set('auto_deduct_invoices', v)}
                            label="Pay invoices from collections" hint="Deduct the platform bill from the M-Pesa money held for the ISP." />
                        <Field label="Terms of service link">{text('terms_url')}</Field>
                    </div>
                    <SaveBtn fields={['signup_enabled', 'trial_days', 'grace_days', 'retention_days', 'invoice_day', 'invoice_due_days', 'auto_deduct_invoices', 'terms_url']} />
                </Panel>

                <Panel>
                    <PanelHeader leading={<MpesaBadge />} title="M-Pesa collection" subtitle="All ISPs' customers pay to this shortcode."
                        action={isAdmin && <Button size="sm" variant="outline" onClick={() => mpesa.mutate('test')} disabled={mpesa.isPending}><Plug />Test</Button>} />
                    <div className="grid gap-4 sm:grid-cols-2">
                        <Field label="Environment">
                            <Select disabled={!isAdmin} value={form.mpesa_environment} onChange={(e) => set('mpesa_environment', e.target.value)}>
                                <option value="sandbox">Sandbox</option><option value="production">Production</option>
                            </Select>
                        </Field>
                        <Field label="Shortcode type">
                            <Select disabled={!isAdmin} value={form.mpesa_shortcode_type} onChange={(e) => set('mpesa_shortcode_type', e.target.value)}>
                                <option value="paybill">Paybill</option><option value="till">Till (Buy Goods)</option>
                            </Select>
                        </Field>
                        <Field label="Shortcode">{text('mpesa_shortcode')}</Field>
                        {form.mpesa_shortcode_type === 'till' && <Field label="Till number" hint="if different from the shortcode">{text('mpesa_till_number')}</Field>}
                        <Field label="Passkey">{secret('mpesa_passkey')}</Field>
                    </div>
                    <p className="mt-5 text-[13px] font-semibold"><KeyRound className="mr-1.5 inline h-4 w-4" />Platform Daraja app</p>
                    <p className="text-[12.5px] text-muted-foreground">Used only by this server: C2B registration, verifying payments, payouts.</p>
                    <div className="mt-2 grid gap-4 sm:grid-cols-2">
                        <Field label="Consumer key">{secret('mpesa_consumer_key')}</Field>
                        <Field label="Consumer secret">{secret('mpesa_consumer_secret')}</Field>
                    </div>
                    <p className="mt-5 text-[13px] font-semibold"><KeyRound className="mr-1.5 inline h-4 w-4" />ISP-instance Daraja app</p>
                    <p className="text-[12.5px] text-muted-foreground">Goes into every ISP's instance, where their admins can see it. Create a separate Daraja app with only <b>M-Pesa Express</b> enabled.</p>
                    <div className="mt-2 grid gap-4 sm:grid-cols-2">
                        <Field label="Consumer key">{secret('tenant_consumer_key')}</Field>
                        <Field label="Consumer secret">{secret('tenant_consumer_secret')}</Field>
                    </div>
                    <div className="mt-4"><Toggle disabled={!isAdmin} checked={form.verify_stk_callbacks} onChange={(v) => set('verify_stk_callbacks', v)}
                        label="Confirm every STK payment with Safaricom" hint="A forged callback can't create money. Leave on." /></div>
                    <SaveBtn fields={['mpesa_environment', 'mpesa_shortcode_type', 'mpesa_shortcode', 'mpesa_till_number', 'mpesa_passkey', 'mpesa_consumer_key', 'mpesa_consumer_secret', 'tenant_consumer_key', 'tenant_consumer_secret', 'verify_stk_callbacks']} />
                    <div className="mt-5 rounded-xl bg-secondary p-4 text-[13px]">
                        <p className="font-semibold">Paybill / till (C2B) URLs</p>
                        {s.c2b_urls?.confirmation ? (
                            <>
                                {(['confirmation', 'validation'] as const).map((k) => (
                                    <p key={k} className="mt-1 flex items-center gap-2 break-all font-mono text-[12px]">
                                        <span className="flex-1">{s.c2b_urls[k]}</span>
                                        <button onClick={() => copy(s.c2b_urls[k])} aria-label="Copy" className="text-muted-foreground"><Copy className="h-4 w-4" /></button>
                                    </p>
                                ))}
                                <p className="mt-2 text-muted-foreground">
                                    {s.c2b_registered_at ? <span className="text-ok"><CheckCircle2 className="mr-1 inline h-4 w-4" />Registered {dateTime(s.c2b_registered_at)}</span> : 'Not registered with Safaricom yet.'}
                                </p>
                                {isAdmin && <Button size="sm" className="mt-2" variant="outline" onClick={() => mpesa.mutate('register_c2b')} disabled={mpesa.isPending}><RefreshCw />Register with Safaricom</Button>}
                            </>
                        ) : <p className="text-muted-foreground">Set the public address first.</p>}
                    </div>
                </Panel>

                <Panel>
                    <PanelHeader title="Payouts to ISPs" subtitle="B2B (BusinessPayBill / BusinessBuyGoods) or B2C (BusinessPayment)" />
                    <div className="grid gap-4 sm:grid-cols-2">
                        <Field label="Paying shortcode" hint="blank = the collection shortcode">{text('settlement_shortcode')}</Field>
                        <Field label="Initiator name">{text('initiator_name')}</Field>
                        <Field label="Initiator password">{secret('initiator_password')}</Field>
                        <Field label="Schedule">
                            <Select disabled={!isAdmin} value={form.settlement_schedule} onChange={(e) => set('settlement_schedule', e.target.value)}>
                                <option value="daily">Every day</option><option value="weekly">Every week</option><option value="manual">Only when run by hand</option>
                            </Select>
                        </Field>
                        {form.settlement_schedule !== 'manual' && <Field label="At (hour, 0-23)">{num('settlement_hour', { min: 0, max: 23 })}</Field>}
                        {form.settlement_schedule === 'weekly' && (
                            <Field label="On">
                                <Select disabled={!isAdmin} value={form.settlement_weekday} onChange={(e) => set('settlement_weekday', Number(e.target.value))}>
                                    {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                                </Select>
                            </Field>
                        )}
                        <Field label="Smallest automatic payout (KES)">{num('settlement_min_amount')}</Field>
                        <Field label="Always keep back (KES)" hint="for refunds and reversals">{num('reserve_amount')}</Field>
                        <Field label="Default collection fee %">{num('collection_fee_percent', { step: '0.1' })}</Field>
                        <Field label="Default payout fee (KES)">{num('settlement_fee_flat')}</Field>
                    </div>
                    <Field label="Safaricom public certificate (PEM)" className="mt-4" hint="Encrypts the initiator password (SecurityCredential). Sandbox and production use different certificates.">
                        <Textarea disabled={!isAdmin} className="font-mono text-[11.5px]" value={form.mpesa_certificate} onChange={(e) => set('mpesa_certificate', e.target.value)}
                            placeholder={s.mpesa_certificate_set ? 'Saved -- paste a new one to replace it' : '-----BEGIN CERTIFICATE-----'} />
                    </Field>
                    <div className="mt-4"><Toggle disabled={!isAdmin} checked={form.settlement_requires_approval} onChange={(v) => set('settlement_requires_approval', v)}
                        label="A second admin approves every payout" hint="The person who created a payout can't approve it." /></div>
                    {!form.settlement_requires_approval && <Notice className="mt-3">Payouts will go out without anyone checking them.</Notice>}
                    <SaveBtn fields={['settlement_shortcode', 'initiator_name', 'initiator_password', 'settlement_schedule', 'settlement_hour', 'settlement_weekday', 'settlement_min_amount', 'reserve_amount', 'collection_fee_percent', 'settlement_fee_flat', 'mpesa_certificate', 'settlement_requires_approval']} />
                </Panel>
            </div>
        </>
    );
}
