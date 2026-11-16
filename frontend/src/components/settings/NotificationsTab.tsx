import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { MessageSquare, Send, QrCode, CheckCircle2, Radio } from 'lucide-react';
import { notificationAPI } from '../../services/api';
import { getErrorMessage } from '../../utils/getErrorMessage';
import MessageTemplatesSection, { useMessageTemplates } from './MessageTemplatesSection';

const SECTION_CARD = 'bg-card border rounded-lg p-4 sm:p-5';

export default function NotificationsTab() {
    return (
        <div className="space-y-6 max-w-2xl">
            <AdminContactsSection />
            <SalesContactsSection />
            <ConfirmationsSection />
            <RenewalRemindersSection />
            <SuperadminEmailsSection />
            <MessageTemplatesSection />
            <SmsSection />
            <WhatsAppSection />
            <TelegramSection />
            <EmailSection />
            <BroadcastSection />
        </div>
    );
}

/** Which customers get payment/activation confirmations (default: PPPoE only). */
function ConfirmationsSection() {
    const queryClient = useQueryClient();
    const { data: settings } = useQuery({
        queryKey: ['notification-settings'],
        queryFn: async () => (await notificationAPI.getSettings()).data,
    });
    const selected = new Set<string>((settings?.confirmation_service_types ?? 'pppoe').split(',').filter(Boolean));

    const channels = new Set<string>((settings?.confirmation_channels ?? 'whatsapp').split(',').filter(Boolean));
    const saveSettings = useMutation({
        mutationFn: (data: Record<string, unknown>) => notificationAPI.updateSettings(data),
        onSuccess: () => { toast.success('Saved'); queryClient.invalidateQueries({ queryKey: ['notification-settings'] }); },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Could not save')),
    });
    const toggleChannel = (c: string) => {
        const next = new Set(channels);
        if (next.has(c)) next.delete(c); else next.add(c);
        if (!next.size) { toast.error('Keep at least one channel'); return; }
        saveSettings.mutate({ confirmation_channels: [...next].join(',') });
    };

    const save = useMutation({
        mutationFn: (types: string[]) => notificationAPI.updateSettings({ confirmation_service_types: types.join(',') }),
        onSuccess: () => { toast.success('Saved'); queryClient.invalidateQueries({ queryKey: ['notification-settings'] }); },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Could not save')),
    });

    const toggle = (type: string) => {
        const next = new Set(selected);
        if (next.has(type)) next.delete(type); else next.add(type);
        save.mutate([...next]);
    };

    return (
        <div className={SECTION_CARD}>
            <h3 className="text-lg font-bold mb-1">Payment confirmations</h3>
            <p className="text-sm text-muted-foreground mb-3">
                Who gets a message when a payment activates their plan (and when staff recharge, extend or add cash).
                Hotspot buyers already see the result on the login page.
            </p>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">Who gets them</p>
            <div className="flex flex-wrap gap-4">
                {[['pppoe', 'PPPoE'], ['static', 'Static IP'], ['hotspot', 'Hotspot']].map(([value, label]) => (
                    <label key={value} className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={selected.has(value)} disabled={save.isPending} onChange={() => toggle(value)} />
                        {label}
                    </label>
                ))}
            </div>

            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mt-4 mb-1.5">Send by</p>
            <div className="flex flex-wrap gap-2">
                {[['whatsapp', 'WhatsApp'], ['sms', 'SMS'], ['email', 'Email']].map(([value, label]) => (
                    <button
                        key={value}
                        type="button"
                        aria-pressed={channels.has(value)}
                        disabled={saveSettings.isPending}
                        onClick={() => toggleChannel(value)}
                        className={`h-8 rounded-full px-4 text-[13px] font-semibold ${channels.has(value) ? 'bg-primary text-primary-foreground' : 'bg-chip text-muted-foreground'}`}
                    >
                        {label}
                    </button>
                ))}
            </div>
            {!channels.has('sms') && (
                <label className="mt-3 flex items-start gap-2 text-sm">
                    <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={settings?.confirmation_sms_fallback ?? true}
                        disabled={saveSettings.isPending}
                        onChange={(e) => saveSettings.mutate({ confirmation_sms_fallback: e.target.checked })}
                    />
                    <span>If it can't be delivered that way (e.g. WhatsApp isn't connected), send it by SMS instead.</span>
                </label>
            )}
        </div>
    );
}

const HOURS = Array.from({ length: 24 }, (_, h) => h);
const hourLabel = (h: number) => `${String(h).padStart(2, '0')}:00`;

function useSettingsSave(successMsg = 'Saved') {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (data: Record<string, unknown>) => notificationAPI.updateSettings(data),
        onSuccess: () => { toast.success(successMsg); queryClient.invalidateQueries({ queryKey: ['notification-settings'] }); },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Could not save')),
    });
}

/**
 * Sales team contacts: they get only the daily "expired today, not renewed"
 * follow-up list (admin contacts get it too), not every admin notice.
 */
function SalesContactsSection() {
    const { data: settings } = useQuery({
        queryKey: ['notification-settings'],
        queryFn: async () => (await notificationAPI.getSettings()).data,
    });
    const [phones, setPhones] = useState('');
    const [emails, setEmails] = useState('');
    useEffect(() => {
        if (settings) { setPhones(settings.sales_phones || ''); setEmails(settings.sales_emails || ''); }
    }, [settings]);
    const save = useSettingsSave('Sales contacts saved');
    const enabled = settings?.expired_followup_enabled ?? true;

    return (
        <div className={SECTION_CARD}>
            <h3 className="text-lg font-bold mb-1">Sales contacts &amp; expired follow-up</h3>
            <p className="text-sm text-muted-foreground mb-4">
                Every evening, admin and sales contacts get the list of PPPoE customers whose plan expired today and who
                haven&apos;t renewed (hotspot users are left out) (name, phone, plan), so someone can follow up. Emails include a CSV. Phones use the
                admin contacts&apos; channels. One per line.
            </p>
            <div className="flex flex-wrap items-center gap-4 mb-4 text-sm">
                <label className="flex items-center gap-2">
                    <input type="checkbox" checked={enabled} disabled={save.isPending}
                        onChange={(e) => save.mutate({ expired_followup_enabled: e.target.checked })} />
                    Send the daily expired list
                </label>
                <label className="flex items-center gap-2">
                    <span className="text-muted-foreground">at</span>
                    <select className="border rounded-lg px-2 py-1 text-sm" disabled={!enabled || save.isPending}
                        value={settings?.expired_followup_hour ?? 20}
                        onChange={(e) => save.mutate({ expired_followup_hour: Number(e.target.value) })}>
                        {HOURS.map((h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
                    </select>
                </label>
            </div>
            <form onSubmit={(e) => { e.preventDefault(); save.mutate({ sales_phones: phones, sales_emails: emails }); }} className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label className="block text-sm font-medium text-foreground/80 mb-1">Sales phone numbers</label>
                        <textarea rows={3} className="w-full border rounded-lg px-3 py-2 text-sm" placeholder={'0722 123 456'}
                            value={phones} onChange={(e) => setPhones(e.target.value)} />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-foreground/80 mb-1">Sales email addresses</label>
                        <textarea rows={3} className="w-full border rounded-lg px-3 py-2 text-sm" placeholder={'sales@example.com'}
                            value={emails} onChange={(e) => setEmails(e.target.value)} />
                        {!settings?.email_enabled && <p className="mt-1 text-xs text-muted-foreground">Turn on Email below for these to be sent.</p>}
                    </div>
                </div>
                <button type="submit" disabled={save.isPending} className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50">
                    {save.isPending ? 'Saving...' : 'Save sales contacts'}
                </button>
            </form>
        </div>
    );
}

/** Scheduled renewal reminders: when, how often, to whom and on which channels. */
function RenewalRemindersSection() {
    const { data: settings } = useQuery({
        queryKey: ['notification-settings'],
        queryFn: async () => (await notificationAPI.getSettings()).data,
    });
    const save = useSettingsSave();
    const [daysBefore, setDaysBefore] = useState('3');
    const [every, setEvery] = useState('3');
    useEffect(() => {
        if (settings) {
            setDaysBefore(String(settings.reminder_days_before ?? 3));
            setEvery(String(settings.reminder_every_days ?? 3));
        }
    }, [settings]);

    const enabled = settings?.reminder_enabled ?? true;
    const types = new Set<string>((settings?.reminder_service_types ?? 'pppoe,static').split(',').filter(Boolean));
    const channels = new Set<string>((settings?.reminder_channels ?? 'whatsapp').split(',').filter(Boolean));
    const schedule: number[] = settings?.reminder_schedule ?? [3, 0];

    const toggleSet = (set: Set<string>, value: string, field: string, needOne: boolean) => {
        const next = new Set(set);
        if (next.has(value)) next.delete(value); else next.add(value);
        if (needOne && !next.size) { toast.error('Keep at least one channel'); return; }
        save.mutate({ [field]: [...next].join(',') });
    };
    const saveNumbers = () => save.mutate({ reminder_days_before: Number(daysBefore) || 0, reminder_every_days: Number(every) || 1 });
    const scheduleText = schedule.length
        ? schedule.map((d) => (d === 0 ? 'on the expiry day' : `${d} day${d === 1 ? '' : 's'} before`)).join(', ')
        : 'no reminders';

    return (
        <div className={SECTION_CARD}>
            <h3 className="text-lg font-bold mb-1">Renewal reminders</h3>
            <p className="text-sm text-muted-foreground mb-3">
                Automatic reminders before a plan expires, with the plan, amount and how to pay. Customers who have
                already renewed aren&apos;t reminded. Wording: the &quot;Renewal reminder&quot; message template.
            </p>
            <label className="flex items-center gap-2 text-sm mb-4">
                <input type="checkbox" checked={enabled} disabled={save.isPending}
                    onChange={(e) => save.mutate({ reminder_enabled: e.target.checked })} />
                Send renewal reminders
            </label>
            <fieldset disabled={!enabled || save.isPending} className="space-y-4 disabled:opacity-60">
                <form onSubmit={(e) => { e.preventDefault(); saveNumbers(); }} className="flex flex-wrap items-end gap-3 text-sm">
                    <label>
                        <span className="block text-foreground/80 mb-1">First reminder (days before)</span>
                        <input type="number" min={0} max={60} className="w-28 border rounded-lg px-3 py-2"
                            value={daysBefore} onChange={(e) => setDaysBefore(e.target.value)} onBlur={saveNumbers} />
                    </label>
                    <label>
                        <span className="block text-foreground/80 mb-1">Then every (days)</span>
                        <input type="number" min={1} max={60} className="w-28 border rounded-lg px-3 py-2"
                            value={every} onChange={(e) => setEvery(e.target.value)} onBlur={saveNumbers} />
                    </label>
                    <label>
                        <span className="block text-foreground/80 mb-1">Send at</span>
                        <select className="border rounded-lg px-3 py-2" value={settings?.reminder_hour ?? 8}
                            onChange={(e) => save.mutate({ reminder_hour: Number(e.target.value) })}>
                            {HOURS.map((h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
                        </select>
                    </label>
                    <label className="flex items-center gap-2 pb-2">
                        <input type="checkbox" checked={settings?.reminder_on_expiry_day ?? true}
                            onChange={(e) => save.mutate({ reminder_on_expiry_day: e.target.checked })} />
                        Also on the expiry day
                    </label>
                </form>
                <p className="text-sm rounded-lg bg-surface2 px-3 py-2">Reminders go out {scheduleText}.</p>

                <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">Who gets them</p>
                    <div className="flex flex-wrap gap-4">
                        {[['pppoe', 'PPPoE'], ['static', 'Static IP'], ['hotspot', 'Hotspot']].map(([value, label]) => (
                            <label key={value} className="flex items-center gap-2 text-sm">
                                <input type="checkbox" checked={types.has(value)} onChange={() => toggleSet(types, value, 'reminder_service_types', false)} />
                                {label}
                            </label>
                        ))}
                    </div>
                </div>

                <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">Send by</p>
                    <div className="flex flex-wrap gap-2">
                        {[['whatsapp', 'WhatsApp'], ['sms', 'SMS'], ['email', 'Email']].map(([value, label]) => (
                            <button key={value} type="button" aria-pressed={channels.has(value)}
                                onClick={() => toggleSet(channels, value, 'reminder_channels', true)}
                                className={`h-8 rounded-full px-4 text-[13px] font-semibold ${channels.has(value) ? 'bg-primary text-primary-foreground' : 'bg-chip text-muted-foreground'}`}>
                                {label}
                            </button>
                        ))}
                    </div>
                    {!channels.has('sms') && (
                        <label className="mt-3 flex items-start gap-2 text-sm">
                            <input type="checkbox" className="mt-0.5" checked={settings?.reminder_sms_fallback ?? true}
                                onChange={(e) => save.mutate({ reminder_sms_fallback: e.target.checked })} />
                            <span>If it can&apos;t be delivered that way, send it by SMS instead.</span>
                        </label>
                    )}
                </div>
            </fieldset>
        </div>
    );
}

/**
 * Emails to every superadmin with an email address: the 11 pm daily sales
 * report, and event emails (vouchers generated, new PPPoE customer, manual
 * top-up). Needs the Email (SMTP) section below to be set up.
 */
function SuperadminEmailsSection() {
    const queryClient = useQueryClient();
    const { data: settings } = useQuery({
        queryKey: ['notification-settings'],
        queryFn: async () => (await notificationAPI.getSettings()).data,
    });
    const save = useMutation({
        mutationFn: (data: Record<string, boolean>) => notificationAPI.updateSettings(data),
        onSuccess: () => { toast.success('Saved'); queryClient.invalidateQueries({ queryKey: ['notification-settings'] }); },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Could not save')),
    });
    const sendNow = useMutation({
        mutationFn: () => notificationAPI.sendDailyReportNow(),
        onSuccess: (res) => toast.success(`Report delivered ${res.data.sent} time${res.data.sent === 1 ? '' : 's'}`),
        onError: (err: any) => toast.error(getErrorMessage(err, 'Could not send the report')),
    });
    return (
        <div className={SECTION_CARD}>
            <h3 className="text-lg font-bold mb-1">Admin notifications</h3>
            <p className="text-sm text-muted-foreground mb-3">
                Sent to the admin contacts above (emails get the full report; phones get a short summary).
            </p>
            <div className="space-y-2">
                <label className="flex items-start gap-2 text-sm">
                    <input type="checkbox" className="mt-0.5" checked={!!settings?.daily_report_enabled} disabled={save.isPending}
                        onChange={(e) => save.mutate({ daily_report_enabled: e.target.checked })} />
                    <span><span className="font-medium">Daily sales report at 11 pm</span> -- revenue, payments, sales by plan and by payment method, with a PDF copy.</span>
                </label>
                <label className="flex items-start gap-2 text-sm">
                    <input type="checkbox" className="mt-0.5" checked={!!settings?.admin_event_emails} disabled={save.isPending}
                        onChange={(e) => save.mutate({ admin_event_emails: e.target.checked })} />
                    <span><span className="font-medium">Event emails</span> -- vouchers generated (with the codes), a new PPPoE customer, and every manual top-up or cash credit.</span>
                </label>
            </div>
            <button
                type="button"
                disabled={sendNow.isPending}
                onClick={() => sendNow.mutate()}
                className="mt-3 px-3 py-1.5 border rounded-lg text-sm font-medium disabled:opacity-50"
            >
                {sendNow.isPending ? 'Sending…' : "Send today's report now"}
            </button>
        </div>
    );
}

function TestSendRow({ channel, disabled }: { channel: 'sms' | 'whatsapp' | 'telegram' | 'email'; disabled?: boolean }) {
    const [recipient, setRecipient] = useState('');

    const testMutation = useMutation({
        mutationFn: () => notificationAPI.testSend({ channel, recipient }),
        onSuccess: () => toast.success('Test message sent'),
        onError: (err: any) => toast.error(getErrorMessage(err, 'Test message failed')),
    });

    return (
        <div className="flex flex-col sm:flex-row gap-2 mt-3">
            <input
                type="text"
                placeholder={channel === 'telegram' ? 'Telegram chat ID' : channel === 'email' ? 'Email address' : 'Phone number (07...)'}
                className="flex-1 border rounded-lg px-3 py-2 text-sm disabled:bg-gray-100"
                value={recipient}
                disabled={disabled}
                onChange={e => setRecipient(e.target.value)}
            />
            <button
                type="button"
                disabled={disabled || !recipient || testMutation.isPending}
                onClick={() => testMutation.mutate()}
                className="flex items-center justify-center px-3 py-2 bg-gray-100 text-foreground/80 rounded-lg text-sm font-medium hover:bg-gray-200 disabled:opacity-50 whitespace-nowrap"
            >
                <Send className="h-4 w-4 mr-2" /> {testMutation.isPending ? 'Sending...' : 'Send Test'}
            </button>
        </div>
    );
}

function SmsSection() {
    const queryClient = useQueryClient();
    const { data: settings } = useQuery({
        queryKey: ['notification-settings'],
        queryFn: async () => (await notificationAPI.getSettings()).data,
    });
    const [form, setForm] = useState({ at_username: '', at_api_key: '', at_sender_id: '', at_environment: 'sandbox' });

    useEffect(() => {
        if (settings) {
            setForm({
                at_username: settings.at_username || '',
                at_api_key: '',
                at_sender_id: settings.at_sender_id || '',
                at_environment: settings.at_environment || 'sandbox',
            });
        }
    }, [settings]);

    const saveMutation = useMutation({
        mutationFn: () => notificationAPI.updateSettings(form),
        onSuccess: () => {
            toast.success('SMS settings saved');
            queryClient.invalidateQueries({ queryKey: ['notification-settings'] });
            setForm(f => ({ ...f, at_api_key: '' }));
        },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Failed to save SMS settings')),
    });

    return (
        <div className={SECTION_CARD}>
            <div className="flex items-center mb-1">
                <MessageSquare className="h-5 w-5 text-primary mr-2" />
                <h3 className="text-lg font-bold">SMS (Africa's Talking)</h3>
            </div>
            <p className="text-sm text-muted-foreground mb-4">Used for welcome messages, payment confirmations, expiry reminders, and promo broadcasts.</p>
            <form onSubmit={e => { e.preventDefault(); saveMutation.mutate(); }} className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-medium text-foreground/80 mb-1">Username</label>
                        <input className="w-full border rounded-lg px-3 py-2 text-sm" value={form.at_username}
                            onChange={e => setForm({ ...form, at_username: e.target.value })} />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-foreground/80 mb-1">Environment</label>
                        <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.at_environment}
                            onChange={e => setForm({ ...form, at_environment: e.target.value })}>
                            <option value="sandbox">Sandbox</option>
                            <option value="production">Production</option>
                        </select>
                        {form.at_environment === 'sandbox' && (
                            <p className="mt-1 text-xs text-warn">
                                Sandbox only delivers to Africa's Talking's simulator, never to real phones. Use Production with your live app's username.
                            </p>
                        )}
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-foreground/80 mb-1">API Key</label>
                        <input
                            type="password"
                            placeholder={settings?.at_api_key_is_set ? '•••••••• (set -- leave blank to keep)' : 'Not set'}
                            className="w-full border rounded-lg px-3 py-2 text-sm"
                            value={form.at_api_key}
                            onChange={e => setForm({ ...form, at_api_key: e.target.value })}
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-foreground/80 mb-1">Sender ID (optional)</label>
                        <input className="w-full border rounded-lg px-3 py-2 text-sm" value={form.at_sender_id}
                            onChange={e => setForm({ ...form, at_sender_id: e.target.value })} />
                    </div>
                </div>
                <button type="submit" disabled={saveMutation.isPending}
                    className="px-4 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50">
                    {saveMutation.isPending ? 'Saving...' : 'Save SMS Settings'}
                </button>
            </form>
            <TestSendRow channel="sms" disabled={!settings?.at_api_key_is_set} />
        </div>
    );
}

function WhatsAppSection() {
    const queryClient = useQueryClient();
    const { data: settings } = useQuery({
        queryKey: ['notification-settings'],
        queryFn: async () => (await notificationAPI.getSettings()).data,
    });
    const provider = settings?.whatsapp_provider || 'baileys';
    const [atNumber, setAtNumber] = useState('');
    useEffect(() => { setAtNumber(settings?.whatsapp_at_number || ''); }, [settings]);

    const saveMutation = useMutation({
        mutationFn: (data: Record<string, string>) => notificationAPI.updateSettings(data),
        onSuccess: () => {
            toast.success('WhatsApp settings saved');
            queryClient.invalidateQueries({ queryKey: ['notification-settings'] });
        },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Failed to save WhatsApp settings')),
    });

    const { data: status, isLoading } = useQuery({
        queryKey: ['whatsapp-status'],
        queryFn: async () => (await notificationAPI.getWhatsAppStatus()).data,
        refetchInterval: 5000,
        enabled: provider === 'baileys',
    });

    return (
        <div className={SECTION_CARD}>
            <div className="flex items-center mb-1">
                <Radio className="h-5 w-5 text-green-600 mr-2" />
                <h3 className="text-lg font-bold">WhatsApp</h3>
            </div>
            <div className="mb-4">
                <label className="block text-xs font-medium text-foreground/80 mb-1">Provider</label>
                <select className="w-full border rounded-lg px-3 py-2 text-sm" value={provider}
                    onChange={e => saveMutation.mutate({ whatsapp_provider: e.target.value })}>
                    <option value="baileys">QR-paired (Baileys)</option>
                    <option value="africastalking">Africa's Talking WhatsApp API</option>
                </select>
            </div>

            {provider === 'africastalking' ? (
                <div className="space-y-3">
                    <p className="text-sm text-muted-foreground">
                        Official WhatsApp Business API via Africa's Talking. Uses the Username, API Key and
                        Environment from the SMS settings above. Messages outside a customer's 24-hour reply
                        window need an approved template.
                    </p>
                    <form onSubmit={e => { e.preventDefault(); saveMutation.mutate({ whatsapp_at_number: atNumber }); }}
                        className="flex gap-2">
                        <input className="flex-1 border rounded-lg px-3 py-2 text-sm" placeholder="Registered WhatsApp number, e.g. +2547XXXXXXXX"
                            value={atNumber} onChange={e => setAtNumber(e.target.value)} />
                        <button type="submit" disabled={saveMutation.isPending}
                            className="px-4 py-2 bg-primary text-white rounded-lg text-sm font-medium disabled:opacity-50">Save</button>
                    </form>
                    <TestSendRow channel="whatsapp" disabled={!settings?.at_api_key_is_set || !settings?.whatsapp_at_number} />
                </div>
            ) : (<>
            <p className="text-sm text-muted-foreground mb-4">
                QR-paired, like WhatsApp Web -- this is not the official WhatsApp Business API. Use a dedicated
                number (not your personal one): automated/bulk messaging on an unofficial connection carries a
                real risk of that number being banned by WhatsApp.
            </p>

            {isLoading ? (
                <p className="text-sm text-muted-foreground">Checking connection...</p>
            ) : status?.connected ? (
                <div className="flex items-center text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-3">
                    <CheckCircle2 className="h-5 w-5 mr-2 shrink-0" />
                    <span className="text-sm font-medium">Connected{status.number ? ` as ${status.number}` : ''}</span>
                </div>
            ) : status?.qr ? (
                <div className="text-center py-2">
                    <img src={status.qr} alt="WhatsApp QR code" className="mx-auto h-48 w-48 border rounded-lg" />
                    <p className="text-sm text-muted-foreground mt-2 flex items-center justify-center">
                        <QrCode className="h-4 w-4 mr-1" /> Scan with WhatsApp on the business phone (Linked Devices)
                    </p>
                </div>
            ) : (
                <p className="text-sm text-muted-foreground italic">
                    Not connected -- waiting for a QR code from the WhatsApp service. If this doesn't appear
                    within a minute, the whatsapp_service container may not be running.
                </p>
            )}

            <TestSendRow channel="whatsapp" disabled={!status?.connected} />
            </>)}
        </div>
    );
}

/**
 * Admin contacts: everyone listed gets every admin notification -- staff
 * alerts (extensions, cash), the daily report and event notices. Phones get
 * a short text on the chosen channels; emails get the full email.
 */
function AdminContactsSection() {
    const queryClient = useQueryClient();
    const { data: settings } = useQuery({
        queryKey: ['notification-settings'],
        queryFn: async () => (await notificationAPI.getSettings()).data,
    });
    const [phones, setPhones] = useState('');
    const [emails, setEmails] = useState('');
    const [channels, setChannels] = useState<string[]>(['sms']);

    useEffect(() => {
        if (settings) {
            setPhones(settings.admin_phones || '');
            setEmails(settings.admin_emails || '');
            setChannels((settings.admin_phone_channels || 'sms').split(',').filter(Boolean));
        }
    }, [settings]);

    const save = useMutation({
        mutationFn: () => notificationAPI.updateSettings({
            admin_phones: phones, admin_emails: emails, admin_phone_channels: channels.join(','),
        }),
        onSuccess: () => { toast.success('Admin contacts saved'); queryClient.invalidateQueries({ queryKey: ['notification-settings'] }); },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Could not save admin contacts')),
    });

    const toggle = (c: string) => setChannels((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
    const profileEmails: string[] = settings?.superadmin_recipients || [];

    return (
        <div className={SECTION_CARD}>
            <h3 className="text-lg font-bold mb-1">Admin contacts</h3>
            <p className="text-sm text-muted-foreground mb-4">
                Everyone here gets admin notifications: staff extensions and cash credits, the daily report, and
                voucher / new customer / top-up notices. One per line.
            </p>
            <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label className="block text-sm font-medium text-foreground/80 mb-1">Phone numbers</label>
                        <textarea rows={3} className="w-full border rounded-lg px-3 py-2 text-sm" placeholder={'0722 123 456\n0733 987 654'}
                            value={phones} onChange={(e) => setPhones(e.target.value)} />
                        <div className="mt-1.5 flex gap-4 text-sm">
                            <span className="text-muted-foreground">Send by:</span>
                            {[['sms', 'SMS'], ['whatsapp', 'WhatsApp']].map(([value, label]) => (
                                <label key={value} className="flex items-center gap-1.5">
                                    <input type="checkbox" checked={channels.includes(value)} onChange={() => toggle(value)} /> {label}
                                </label>
                            ))}
                        </div>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-foreground/80 mb-1">Email addresses</label>
                        <textarea rows={3} className="w-full border rounded-lg px-3 py-2 text-sm" placeholder={'manager@example.com\nowner@example.com'}
                            value={emails} onChange={(e) => setEmails(e.target.value)} />
                        <p className="mt-1 text-xs text-muted-foreground">
                            {profileEmails.length ? <>Superadmins are always included: {profileEmails.join(', ')}.</> : 'Superadmins with an email on their profile are always included.'}
                            {!settings?.email_enabled && ' Turn on Email below for these to be sent.'}
                        </p>
                    </div>
                </div>
                <button type="submit" disabled={save.isPending} className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50">
                    {save.isPending ? 'Saving...' : 'Save admin contacts'}
                </button>
            </form>
        </div>
    );
}

/**
 * Email over SMTP. Gmail is the default (host/port/encryption fixed; sign in
 * with the Gmail address and a Google App Password); "Custom SMTP" exposes
 * host, port and encryption for any other mail server.
 */
function EmailSection() {
    const queryClient = useQueryClient();
    const { data: settings } = useQuery({
        queryKey: ['notification-settings'],
        queryFn: async () => (await notificationAPI.getSettings()).data,
    });
    const [form, setForm] = useState({
        email_enabled: false, smtp_provider: 'gmail', smtp_host: '', smtp_port: 587, smtp_security: 'starttls',
        smtp_username: '', smtp_password: '', email_from_address: '', email_from_name: '',
    });

    useEffect(() => {
        if (settings) {
            setForm({
                email_enabled: !!settings.email_enabled,
                smtp_provider: settings.smtp_provider || 'gmail',
                smtp_host: settings.smtp_host || '',
                smtp_port: settings.smtp_port || 587,
                smtp_security: settings.smtp_security || 'starttls',
                smtp_username: settings.smtp_username || '',
                smtp_password: '',
                email_from_address: settings.email_from_address || '',
                email_from_name: settings.email_from_name || '',
            });
        }
    }, [settings]);

    const saveMutation = useMutation({
        mutationFn: () => notificationAPI.updateSettings(form),
        onSuccess: () => {
            toast.success('Email settings saved');
            queryClient.invalidateQueries({ queryKey: ['notification-settings'] });
            setForm(f => ({ ...f, smtp_password: '' }));
        },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Failed to save email settings')),
    });

    const gmail = form.smtp_provider === 'gmail';
    const field = 'w-full border rounded-lg px-3 py-2 text-sm';
    const label = 'block text-sm font-medium text-foreground/80 mb-1';

    // Typical port for each encryption mode, applied when switching.
    const setSecurity = (security: string) =>
        setForm(f => ({ ...f, smtp_security: security, smtp_port: security === 'ssl' ? 465 : security === 'starttls' ? 587 : 25 }));

    return (
        <div className={SECTION_CARD}>
            <div className="flex items-center justify-between gap-3 mb-1">
                <h3 className="text-lg font-bold">Email</h3>
                <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form.email_enabled} onChange={e => setForm({ ...form, email_enabled: e.target.checked })} />
                    Enabled
                </label>
            </div>
            <p className="text-sm text-muted-foreground mb-4">
                Sends staff alerts, payment reminders and broadcasts by email, and emails customers who have an
                address when their plan is extended or cash is added.
            </p>
            <form onSubmit={e => { e.preventDefault(); saveMutation.mutate(); }} className="space-y-3">
                <div className="inline-flex rounded-full bg-chip p-1" role="radiogroup" aria-label="Mail server">
                    {[['gmail', 'Gmail'], ['custom', 'Custom SMTP']].map(([value, text]) => (
                        <button
                            key={value}
                            type="button"
                            role="radio"
                            aria-checked={form.smtp_provider === value}
                            onClick={() => setForm({ ...form, smtp_provider: value })}
                            className={`h-8 rounded-full px-4 text-[13px] font-semibold ${form.smtp_provider === value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}
                        >
                            {text}
                        </button>
                    ))}
                </div>

                {gmail ? (
                    <p className="text-xs text-muted-foreground">
                        Uses smtp.gmail.com, port 587 with STARTTLS. Google doesn't accept your normal password here: turn on
                        2-Step Verification, then create an <span className="font-semibold">App Password</span> under Google Account
                        → Security → App passwords, and paste it below.
                    </p>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-[1fr_110px_150px] gap-3">
                        <div>
                            <label className={label}>SMTP host</label>
                            <input className={field} placeholder="mail.example.com" value={form.smtp_host}
                                onChange={e => setForm({ ...form, smtp_host: e.target.value })} />
                        </div>
                        <div>
                            <label className={label}>Port</label>
                            <input type="number" min={1} max={65535} className={field} value={form.smtp_port}
                                onChange={e => setForm({ ...form, smtp_port: Number(e.target.value) })} />
                        </div>
                        <div>
                            <label className={label}>Encryption</label>
                            <select className={field} value={form.smtp_security} onChange={e => setSecurity(e.target.value)}>
                                <option value="starttls">STARTTLS</option>
                                <option value="ssl">SSL/TLS</option>
                                <option value="none">None</option>
                            </select>
                        </div>
                    </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label className={label}>{gmail ? 'Gmail address' : 'Username'}</label>
                        <input className={field} autoComplete="off" placeholder={gmail ? 'you@gmail.com' : 'SMTP username'}
                            value={form.smtp_username} onChange={e => setForm({ ...form, smtp_username: e.target.value })} />
                    </div>
                    <div>
                        <label className={label}>{gmail ? 'App Password' : 'Password'}</label>
                        <input type="password" className={field} autoComplete="new-password"
                            placeholder={settings?.smtp_password_is_set ? '•••••••• (saved, type to replace)' : gmail ? '16-character app password' : 'SMTP password'}
                            value={form.smtp_password} onChange={e => setForm({ ...form, smtp_password: e.target.value })} />
                    </div>
                    <div>
                        <label className={label}>From name</label>
                        <input className={field} placeholder="e.g. Hasanet Support" value={form.email_from_name}
                            onChange={e => setForm({ ...form, email_from_name: e.target.value })} />
                    </div>
                    <div>
                        <label className={label}>From address</label>
                        <input type="email" className={field} placeholder={gmail ? 'Defaults to the Gmail address' : 'Defaults to the username'}
                            value={form.email_from_address} onChange={e => setForm({ ...form, email_from_address: e.target.value })} />
                    </div>
                </div>

                <button
                    type="submit"
                    disabled={saveMutation.isPending}
                    className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50"
                >
                    {saveMutation.isPending ? 'Saving...' : 'Save email settings'}
                </button>
            </form>
            <TestSendRow channel="email" disabled={!settings?.email_enabled || !settings?.smtp_password_is_set} />
        </div>
    );
}

function TelegramSection() {
    const queryClient = useQueryClient();
    const { data: settings } = useQuery({
        queryKey: ['notification-settings'],
        queryFn: async () => (await notificationAPI.getSettings()).data,
    });
    const [form, setForm] = useState({ telegram_bot_token: '', telegram_webhook_secret: '', telegram_bot_username: '' });

    useEffect(() => {
        if (settings) {
            setForm({
                telegram_bot_token: '',
                telegram_webhook_secret: '',
                telegram_bot_username: settings.telegram_bot_username || '',
            });
        }
    }, [settings]);

    const saveMutation = useMutation({
        mutationFn: () => notificationAPI.updateSettings(form),
        onSuccess: () => {
            toast.success('Telegram settings saved');
            queryClient.invalidateQueries({ queryKey: ['notification-settings'] });
            setForm(f => ({ ...f, telegram_bot_token: '', telegram_webhook_secret: '' }));
        },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Failed to save Telegram settings')),
    });

    return (
        <div className={SECTION_CARD}>
            <h3 className="text-lg font-bold mb-1">Telegram</h3>
            <p className="text-sm text-muted-foreground mb-4">
                Telegram doesn't allow a bot to message someone first -- a customer must open
                {settings?.telegram_bot_username ? ` @${settings.telegram_bot_username}` : ' your bot'} and send{' '}
                <code className="text-xs bg-gray-100 px-1 rounded">/start their_portal_username</code> once before
                they can receive any notification here. This is a Telegram platform rule, not a limitation of this system.
            </p>
            <form onSubmit={e => { e.preventDefault(); saveMutation.mutate(); }} className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-medium text-foreground/80 mb-1">Bot Username (without @)</label>
                        <input className="w-full border rounded-lg px-3 py-2 text-sm" value={form.telegram_bot_username}
                            onChange={e => setForm({ ...form, telegram_bot_username: e.target.value })} />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-foreground/80 mb-1">Bot Token</label>
                        <input
                            type="password"
                            placeholder={settings?.telegram_bot_token_is_set ? '•••••••• (set -- leave blank to keep)' : 'From @BotFather'}
                            className="w-full border rounded-lg px-3 py-2 text-sm"
                            value={form.telegram_bot_token}
                            onChange={e => setForm({ ...form, telegram_bot_token: e.target.value })}
                        />
                    </div>
                    <div className="sm:col-span-2">
                        <label className="block text-xs font-medium text-foreground/80 mb-1">Webhook Secret</label>
                        <input
                            type="password"
                            placeholder={settings?.telegram_webhook_secret_is_set ? '•••••••• (set -- leave blank to keep)' : 'A random string only you and Telegram know'}
                            className="w-full border rounded-lg px-3 py-2 text-sm"
                            value={form.telegram_webhook_secret}
                            onChange={e => setForm({ ...form, telegram_webhook_secret: e.target.value })}
                        />
                    </div>
                </div>
                <button type="submit" disabled={saveMutation.isPending}
                    className="px-4 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50">
                    {saveMutation.isPending ? 'Saving...' : 'Save Telegram Settings'}
                </button>
            </form>
            <TestSendRow channel="telegram" disabled={!settings?.telegram_bot_token_is_set} />
        </div>
    );
}

function BroadcastSection() {
    const [message, setMessage] = useState('');
    const [channels, setChannels] = useState<string[]>(['sms']);
    const [serviceType, setServiceType] = useState('pppoe');
    const [previewCount, setPreviewCount] = useState<number | null>(null);
    const { data: templates } = useMessageTemplates();

    const previewMutation = useMutation({
        mutationFn: () => notificationAPI.broadcast({ message, channels, service_type: serviceType, dry_run: true }),
        onSuccess: (res) => setPreviewCount(res.data.recipient_count),
        onError: (err: any) => toast.error(getErrorMessage(err, 'Preview failed')),
    });

    const sendMutation = useMutation({
        mutationFn: () => notificationAPI.broadcast({ message, channels, service_type: serviceType, dry_run: false }),
        onSuccess: (res) => {
            toast.success(`Broadcast queued for ${res.data.recipient_count} customer(s)`);
            setMessage('');
            setPreviewCount(null);
        },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Broadcast failed')),
    });

    const toggleChannel = (c: string) => {
        setPreviewCount(null);
        setChannels(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]);
    };

    const handleSend = () => {
        if (!confirm(`Send this message to ${previewCount ?? 'the matching'} customer(s)? This can't be undone.`)) return;
        sendMutation.mutate();
    };

    return (
        <div className={SECTION_CARD}>
            <h3 className="text-lg font-bold mb-1">Promo Broadcast</h3>
            <p className="text-sm text-muted-foreground mb-4">Send a one-off message to every active customer matching the audience below.</p>

            <div className="space-y-3">
                <div>
                    <label className="block text-xs font-medium text-foreground/80 mb-1">Audience</label>
                    <select className="w-full border rounded-lg px-3 py-2 text-sm" value={serviceType}
                        onChange={e => { setServiceType(e.target.value); setPreviewCount(null); }}>
                        <option value="pppoe">All PPPoE customers</option>
                        <option value="hotspot">All Hotspot customers</option>
                        <option value="all">All customers</option>
                    </select>
                </div>
                <div>
                    <label className="block text-xs font-medium text-foreground/80 mb-1">Channels</label>
                    <div className="flex gap-4">
                        {['sms', 'whatsapp', 'telegram', 'email'].map(c => (
                            <label key={c} className="flex items-center text-sm capitalize">
                                <input type="checkbox" className="mr-1.5" checked={channels.includes(c)} onChange={() => toggleChannel(c)} />
                                {c}
                            </label>
                        ))}
                    </div>
                </div>
                {!!templates?.promo.length && (
                    <div>
                        <label className="block text-xs font-medium text-foreground/80 mb-1">Start from a template</label>
                        <select
                            className="w-full border rounded-lg px-3 py-2 text-sm"
                            value=""
                            onChange={e => {
                                const t = templates.promo.find(p => String(p.id) === e.target.value);
                                if (t) { setMessage(t.body); setPreviewCount(null); }
                            }}
                        >
                            <option value="">Choose a promotional template…</option>
                            {templates.promo.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                        </select>
                    </div>
                )}
                <div>
                    <label className="block text-xs font-medium text-foreground/80 mb-1">Message</label>
                    <textarea
                        rows={3}
                        className="w-full border rounded-lg px-3 py-2 text-sm"
                        value={message}
                        onChange={e => { setMessage(e.target.value); setPreviewCount(null); }}
                    />
                    <p className="mt-1 text-xs text-muted-foreground">
                        Personalise with {'{first_name}'}, {'{name}'}, {'{username}'}, {'{company}'} or {'{support_phone}'}.
                    </p>
                </div>

                {previewCount !== null && (
                    <p className="text-sm text-primary bg-primary/10 border border-primary/20 rounded-lg px-3 py-2">
                        This will reach <strong>{previewCount}</strong> customer(s).
                    </p>
                )}

                <div className="flex gap-2">
                    <button
                        type="button"
                        disabled={!message || channels.length === 0 || previewMutation.isPending}
                        onClick={() => previewMutation.mutate()}
                        className="px-4 py-2 border rounded-lg text-sm font-medium text-foreground/80 hover:bg-secondary disabled:opacity-50"
                    >
                        {previewMutation.isPending ? 'Checking...' : 'Preview'}
                    </button>
                    <button
                        type="button"
                        disabled={previewCount === null || sendMutation.isPending}
                        onClick={handleSend}
                        className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50"
                    >
                        {sendMutation.isPending ? 'Sending...' : `Send to ${previewCount ?? '...'} customer(s)`}
                    </button>
                </div>
            </div>
        </div>
    );
}
