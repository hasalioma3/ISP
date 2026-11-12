import { useEffect, useState } from 'react';
import { CheckCircle2, Loader2, Smartphone, XCircle, Zap } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MpesaBadge } from './MpesaBadge';
import { Panel } from './Panel';
import { formatAmount } from './format';

export type PayState = 'idle' | 'sending' | 'pending' | 'success' | 'failed';

interface MpesaPayCardProps {
    title?: string;
    amount: number;
    /** e.g. "Home 10 Mbps · 30 days" */
    amountNote?: string;
    phone: string;
    onPay: (phone: string) => void;
    state: PayState;
    /** Error/status line under the button. */
    message?: string;
    onReset?: () => void;
    /**
     * Manual-payment fallback under the button. For a till: "Buy Goods,
     * Till N, from <registeredPhone>" -- Till payments carry no account
     * number, so they're matched to the customer by the paying phone, which
     * must be the one on their account. For a paybill: "Paybill N, Account X".
     */
    paybill?: { shortcode: string; type: string; account?: string; registeredPhone?: string } | null;
    disabled?: boolean;
}

const PHONE_RE = /^(?:\+?254|0)?(7\d{8}|1\d{8})$/;

/**
 * Pay & renew card: amount, the M-Pesa number (pre-filled, "Change"), a green
 * STK button, then pending → success/failed once the prompt is sent. The
 * page owns the API calls and status polling; this only renders.
 *
 * The design's 1/3/6/12-month chips are left out: the payment API sells one
 * plan period per STK prompt, so there's nothing for them to do yet.
 */
export function MpesaPayCard({
    title = 'Pay & renew', amount, amountNote, phone, onPay, state, message, onReset, paybill, disabled,
}: MpesaPayCardProps) {
    const [number, setNumber] = useState(phone);
    const [editing, setEditing] = useState(!phone);
    useEffect(() => { setNumber(phone); setEditing(!phone); }, [phone]);

    const digits = number.replace(/\s/g, '');
    const valid = PHONE_RE.test(digits);
    const busy = state === 'sending' || state === 'pending';

    return (
        <Panel>
            <div className="mb-4 flex items-center gap-2.5">
                <MpesaBadge />
                <h3 className="text-[15px] font-bold text-foreground">{title}</h3>
            </div>

            <p className="mb-1.5 text-[13px] text-muted-foreground">Amount</p>
            <div className="flex h-14 items-center gap-3 rounded-full border border-input bg-card px-5">
                <span className="text-[14px] text-faint">KES</span>
                <span className="num text-[22px] font-extrabold text-foreground">{formatAmount(amount)}</span>
                {amountNote && (
                    <span className="ml-auto truncate rounded-full bg-chip px-3 py-1 text-[12px] text-muted-foreground">{amountNote}</span>
                )}
            </div>

            <label htmlFor="mpesa-number" className="mb-1.5 mt-4 block text-[13px] text-muted-foreground">M-Pesa number</label>
            <div className="flex h-12 items-center gap-3 rounded-full border border-input bg-card px-5">
                <Smartphone className="h-4 w-4 shrink-0 text-faint" strokeWidth={1.8} />
                <input
                    id="mpesa-number"
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel"
                    readOnly={!editing}
                    value={number}
                    onChange={(e) => setNumber(e.target.value)}
                    placeholder="07XX XXX XXX"
                    className="num min-w-0 flex-1 bg-transparent text-[15px] text-foreground placeholder:text-faint focus:outline-none"
                />
                {!editing && (
                    <button type="button" onClick={() => setEditing(true)} className="text-[13.5px] font-semibold text-primary">
                        Change
                    </button>
                )}
            </div>
            {editing && number && !valid && (
                <p className="mt-1.5 text-[12.5px] text-bad">Enter a Safaricom number, e.g. 0722 123 456.</p>
            )}

            {state === 'success' ? (
                <div className="mt-5 flex items-center gap-3 rounded-2xl bg-ok-bg p-4 text-ok">
                    <CheckCircle2 className="h-5 w-5 shrink-0" />
                    <p className="text-[14px] font-semibold">{message || 'Payment received. Your plan has been renewed.'}</p>
                </div>
            ) : (
                <button
                    type="button"
                    onClick={() => onPay(digits)}
                    disabled={disabled || busy || !valid}
                    className="mt-5 flex h-14 w-full items-center justify-center gap-2 rounded-full bg-mpesa text-[16px] font-semibold text-white transition-colors hover:bg-mpesa/90 disabled:opacity-60"
                >
                    {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <Zap className="h-5 w-5" strokeWidth={1.8} />}
                    {state === 'sending' ? 'Sending prompt…' : state === 'pending' ? 'Check your phone…' : 'Send payment prompt'}
                </button>
            )}

            {state === 'pending' && (
                <p className="mt-2 text-center text-[12.5px] text-muted-foreground">Enter your M-Pesa PIN on the prompt. This updates by itself.</p>
            )}
            {state === 'failed' && (
                <div className="mt-3 flex items-start gap-2 text-[13px] text-bad">
                    <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span className="flex-1">{message || 'Payment did not go through.'}</span>
                    {onReset && <button onClick={onReset} className="font-semibold underline">Try again</button>}
                </div>
            )}

            {paybill?.shortcode && (
                paybill.type === 'till' ? (
                    <p className="mt-4 text-center text-[12.5px] leading-relaxed text-muted-foreground">
                        Or pay with M-Pesa <span className="font-semibold text-foreground">Buy Goods</span>, Till{' '}
                        <span className="num font-bold text-foreground">{paybill.shortcode}</span>,{' '}
                        {paybill.registeredPhone ? (
                            <>from <span className="num font-bold text-foreground">{paybill.registeredPhone}</span>, the number on your account.</>
                        ) : (
                            <>from the phone number registered on your account. Add your number under My account first.</>
                        )}
                    </p>
                ) : (
                    <p className={cn('mt-4 text-center text-[12.5px] text-muted-foreground')}>
                        Or Paybill <span className="num font-bold text-foreground">{paybill.shortcode}</span>
                        {paybill.account && (
                            <> · Account <span className="font-bold text-foreground">{paybill.account}</span></>
                        )}
                    </p>
                )
            )}
        </Panel>
    );
}
