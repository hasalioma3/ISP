import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { MessageSquare, Send, QrCode, CheckCircle2, Radio } from 'lucide-react';
import { notificationAPI } from '../../services/api';
import { getErrorMessage } from '../../utils/getErrorMessage';

const SECTION_CARD = 'bg-card border rounded-lg p-4 sm:p-5';

export default function NotificationsTab() {
    return (
        <div className="space-y-6 max-w-2xl">
            <SmsSection />
            <WhatsAppSection />
            <TelegramSection />
            <BroadcastSection />
        </div>
    );
}

function TestSendRow({ channel, disabled }: { channel: 'sms' | 'whatsapp' | 'telegram'; disabled?: boolean }) {
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
                placeholder={channel === 'telegram' ? 'Telegram chat ID' : 'Phone number (07...)'}
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
                        {['sms', 'whatsapp', 'telegram'].map(c => (
                            <label key={c} className="flex items-center text-sm capitalize">
                                <input type="checkbox" className="mr-1.5" checked={channels.includes(c)} onChange={() => toggleChannel(c)} />
                                {c}
                            </label>
                        ))}
                    </div>
                </div>
                <div>
                    <label className="block text-xs font-medium text-foreground/80 mb-1">Message</label>
                    <textarea
                        rows={3}
                        className="w-full border rounded-lg px-3 py-2 text-sm"
                        value={message}
                        onChange={e => { setMessage(e.target.value); setPreviewCount(null); }}
                    />
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
