import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import { Loader2, Mail, Phone, Send, X } from 'lucide-react';
import { voucherAPI } from '../services/api';
import { getErrorMessage } from '../utils/getErrorMessage';
import { cn } from '@/lib/utils';

type Contact = { name: string; kind: 'phone' | 'email'; value: string };

/**
 * Hand a voucher batch's unused codes to sales people. The list is the
 * Sales-role staff accounts plus the sales contacts from Settings ->
 * Notifications; any other number or email can be typed in. Phones get the
 * codes as a text (SMS and/or WhatsApp), emails get a table and a CSV.
 */
export default function SendBatchDialog({ batch, onClose, onSent }: { batch: any; onClose: () => void; onSent: () => void }) {
    const { data, isLoading } = useQuery({
        queryKey: ['voucher-sales-contacts'],
        queryFn: async () => (await voucherAPI.salesContacts()).data as { contacts: Contact[]; email_enabled: boolean },
    });
    const [picked, setPicked] = useState<string[]>([]);
    const [extra, setExtra] = useState('');
    const [channels, setChannels] = useState<string[]>(['whatsapp']);
    const [sending, setSending] = useState(false);

    const unused = (batch.vouchers || []).filter((v: any) => v.status === 'active').length;
    const contacts = data?.contacts ?? [];
    const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

    const typed = extra.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean);
    const all = [...picked, ...typed];
    const emails = all.filter((v) => v.includes('@'));
    const phones = all.filter((v) => !v.includes('@'));

    const send = async () => {
        setSending(true);
        try {
            await voucherAPI.sendBatch(batch.id, { phones, emails, channels });
            toast.success(`${unused} code${unused === 1 ? '' : 's'} sending to ${all.length} recipient${all.length === 1 ? '' : 's'}`);
            onSent();
        } catch (err: any) {
            toast.error(getErrorMessage(err, 'Could not send the vouchers'));
        } finally {
            setSending(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[60] grid place-items-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="send-batch-title">
            <div className="w-full max-w-lg rounded-card border border-border bg-card p-6 shadow-card">
                <div className="mb-4 flex items-start justify-between gap-3">
                    <div>
                        <h2 id="send-batch-title" className="text-[18px] font-bold text-foreground">Send vouchers to sales</h2>
                        <p className="text-[13px] text-muted-foreground">
                            Batch #{batch.id} · {batch.plan_name || `KES ${batch.value}`} · {unused} unused code{unused === 1 ? '' : 's'}
                            {unused !== batch.quantity && ' (used ones are left out)'}
                        </p>
                    </div>
                    <button onClick={onClose} aria-label="Close" className="grid h-9 w-9 place-items-center rounded-full text-muted-foreground hover:bg-accent">
                        <X className="h-4 w-4" />
                    </button>
                </div>

                <p className="mb-1.5 text-[13px] font-medium text-foreground/80">Sales people</p>
                <div className="max-h-48 overflow-y-auto rounded-lg border divide-y divide-border">
                    {isLoading ? (
                        <p className="flex items-center gap-2 p-3 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</p>
                    ) : contacts.length === 0 ? (
                        <p className="p-3 text-sm text-muted-foreground">
                            No sales contacts yet. Add them under Settings → Notifications → Sales contacts, give staff the Sales role, or type one below.
                        </p>
                    ) : contacts.map((c) => (
                        <label key={c.value} className="flex items-center gap-3 px-3 py-2 text-sm">
                            <input type="checkbox" checked={picked.includes(c.value)} onChange={() => setPicked((p) => toggle(p, c.value))} />
                            {c.kind === 'email' ? <Mail className="h-4 w-4 text-muted-foreground" /> : <Phone className="h-4 w-4 text-muted-foreground" />}
                            <span className="font-medium">{c.name}</span>
                            <span className="text-muted-foreground">{c.value}</span>
                        </label>
                    ))}
                </div>

                <label className="mb-1.5 mt-4 block text-[13px] font-medium text-foreground/80">Or another phone / email</label>
                <input className="w-full rounded-lg border px-3 py-2 text-sm" placeholder="0722 123 456, sales@example.com"
                    value={extra} onChange={(e) => setExtra(e.target.value)} />

                {phones.length > 0 && (
                    <>
                        <p className="mb-1.5 mt-4 text-[13px] font-medium text-foreground/80">Send to phones by</p>
                        <div className="flex gap-2">
                            {[['whatsapp', 'WhatsApp'], ['sms', 'SMS']].map(([value, label]) => (
                                <button key={value} type="button" aria-pressed={channels.includes(value)}
                                    onClick={() => setChannels((c) => toggle(c, value))}
                                    className={cn('h-8 rounded-full px-4 text-[13px] font-semibold',
                                        channels.includes(value) ? 'bg-primary text-primary-foreground' : 'bg-chip text-muted-foreground')}>
                                    {label}
                                </button>
                            ))}
                        </div>
                        {channels.includes('sms') && unused > 10 && (
                            <p className="mt-1.5 text-xs text-muted-foreground">{unused} codes make a long SMS (several parts, each billed).</p>
                        )}
                    </>
                )}
                {emails.length > 0 && data && !data.email_enabled && (
                    <p className="mt-3 text-xs text-bad">Email isn&apos;t set up (Settings → Notifications → Email), so email recipients will be skipped.</p>
                )}

                <div className="mt-5 flex justify-end gap-2">
                    <button onClick={onClose} className="h-10 rounded-full border border-input px-5 text-[14px] font-semibold text-foreground hover:bg-accent">Cancel</button>
                    <button
                        onClick={send}
                        disabled={sending || !all.length || !unused || (phones.length > 0 && !channels.length)}
                        className="flex h-10 items-center gap-2 rounded-full bg-primary px-5 text-[14px] font-semibold text-primary-foreground disabled:opacity-60"
                    >
                        {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                        Send {unused} code{unused === 1 ? '' : 's'}
                    </button>
                </div>
            </div>
        </div>
    );
}
