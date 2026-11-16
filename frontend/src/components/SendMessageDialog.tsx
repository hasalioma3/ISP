import { useEffect, useState } from 'react';
import { toast } from 'react-hot-toast';
import { Loader2, MessageSquare, X } from 'lucide-react';
import { adminAPI } from '../services/api';
import { useMessageTemplates } from './settings/MessageTemplatesSection';
import { cn } from '@/lib/utils';

const CHANNELS = [
    { value: 'sms', label: 'SMS' },
    { value: 'whatsapp', label: 'WhatsApp' },
    { value: 'email', label: 'Email' },
    { value: 'telegram', label: 'Telegram' },
];

const PLACEHOLDERS = ['{first_name}', '{name}', '{username}', '{company}', '{support_phone}'];

/**
 * "Send message" for the subscribers selected on the Subscribers page: their
 * payment reminder, a saved promotional template, or custom text, on any mix
 * of channels. Each subscriber gets it on every chosen channel they have an
 * address for; the rest are listed as skipped.
 */
export default function SendMessageDialog({ ids, onClose, onSent }: { ids: number[]; onClose: () => void; onSent: () => void }) {
    const { data: templates } = useMessageTemplates();
    const [kind, setKind] = useState<string>('reminder'); // 'reminder' | 'custom' | promo template id
    const [message, setMessage] = useState('');
    const [channels, setChannels] = useState<string[]>(['sms']);
    const [preview, setPreview] = useState<string | null | undefined>(undefined);
    const [sending, setSending] = useState(false);

    const custom = kind !== 'reminder';

    // Picking a promotional template fills the text box (editable).
    useEffect(() => {
        const t = templates?.promo.find((p) => String(p.id) === kind);
        if (t) setMessage(t.body);
    }, [kind, templates]);

    // Preview for the first selected subscriber, refreshed as the text changes.
    useEffect(() => {
        if (custom && !message.trim()) { setPreview(null); return; }
        setPreview(undefined);
        const t = setTimeout(async () => {
            try {
                const res = await adminAPI.bulkMessage(ids, channels.length ? channels : ['sms'], { message: custom ? message : undefined, preview: true });
                setPreview(res.data.preview);
            } catch (err: any) {
                setPreview(null);
                toast.error(err.response?.data?.error || 'Could not prepare the message');
            }
        }, custom ? 500 : 0);
        return () => clearTimeout(t);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [kind, message, ids]);

    const toggle = (c: string) => setChannels((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));

    const send = async () => {
        setSending(true);
        try {
            const res = await adminAPI.bulkMessage(ids, channels, { message: custom ? message : undefined });
            const { queued = 0, skipped = [] } = res.data;
            if (queued) toast.success(`${queued} message${queued === 1 ? '' : 's'} sending`);
            skipped.slice(0, 8).forEach((msg: string) => toast.error(msg, { duration: 6000 }));
            if (skipped.length > 8) toast.error(`…and ${skipped.length - 8} more skipped`, { duration: 6000 });
            onSent();
        } catch (err: any) {
            toast.error(err.response?.data?.error || 'Could not send');
        } finally {
            setSending(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="send-message-title">
            <div className="w-full max-w-lg rounded-card border border-border bg-card p-6 shadow-card">
                <div className="mb-4 flex items-start justify-between gap-3">
                    <div>
                        <h2 id="send-message-title" className="text-[18px] font-bold text-foreground">Send message</h2>
                        <p className="text-[13px] text-muted-foreground">To {ids.length} subscriber{ids.length === 1 ? '' : 's'}.</p>
                    </div>
                    <button onClick={onClose} aria-label="Close" className="grid h-9 w-9 place-items-center rounded-full text-muted-foreground hover:bg-accent">
                        <X className="h-4 w-4" />
                    </button>
                </div>

                <label className="mb-1.5 block text-[13px] font-medium text-foreground/80">Message</label>
                <select className="mb-3 w-full rounded-lg border px-3 py-2 text-sm" value={kind} onChange={(e) => setKind(e.target.value)}>
                    <option value="reminder">Payment reminder (their plan, amount and expiry)</option>
                    <option value="custom">Write a message</option>
                    {templates?.promo.map((t) => <option key={t.id} value={String(t.id)}>Template: {t.name}</option>)}
                </select>

                {custom && (
                    <>
                        <textarea
                            rows={4}
                            className="w-full rounded-lg border px-3 py-2 text-sm"
                            placeholder="Hi {first_name}, …"
                            value={message}
                            onChange={(e) => setMessage(e.target.value)}
                        />
                        <p className="mt-1 text-xs text-muted-foreground">Personalise with {PLACEHOLDERS.join(', ')}.</p>
                    </>
                )}

                <p className="mb-1.5 mt-4 text-[13px] font-medium text-foreground/80">Send by</p>
                <div className="flex flex-wrap gap-2">
                    {CHANNELS.map((c) => (
                        <button
                            key={c.value}
                            type="button"
                            aria-pressed={channels.includes(c.value)}
                            onClick={() => toggle(c.value)}
                            className={cn(
                                'h-8 rounded-full px-4 text-[13px] font-semibold',
                                channels.includes(c.value) ? 'bg-primary text-primary-foreground' : 'bg-chip text-muted-foreground',
                            )}
                        >
                            {c.label}
                        </button>
                    ))}
                </div>

                <p className="mb-1.5 mt-4 text-[12px] font-semibold uppercase tracking-[0.06em] text-faint">Preview (first subscriber)</p>
                <div className="min-h-[64px] rounded-2xl bg-surface2 p-4 text-[14px] leading-relaxed text-foreground">
                    {preview === undefined ? (
                        <span className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Preparing…</span>
                    ) : preview ?? (
                        <span className="text-muted-foreground">{custom ? 'Type a message to preview it.' : 'None of the selected subscribers has a plan to remind them about.'}</span>
                    )}
                </div>
                <p className="mt-2 text-[12.5px] text-muted-foreground">
                    Subscribers without an address for a chosen channel are skipped and listed after sending.
                </p>

                <div className="mt-5 flex justify-end gap-2">
                    <button onClick={onClose} className="h-10 rounded-full border border-input px-5 text-[14px] font-semibold text-foreground hover:bg-accent">
                        Cancel
                    </button>
                    <button
                        onClick={send}
                        disabled={sending || !preview || channels.length === 0}
                        className="flex h-10 items-center gap-2 rounded-full bg-primary px-5 text-[14px] font-semibold text-primary-foreground disabled:opacity-60"
                    >
                        {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageSquare className="h-4 w-4" />}
                        Send to {ids.length}
                    </button>
                </div>
            </div>
        </div>
    );
}
