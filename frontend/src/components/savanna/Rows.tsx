import type { LucideIcon } from 'lucide-react';
import { Banknote, Wifi, Zap } from 'lucide-react';
import { cn } from '@/lib/utils';
import { StatusBadge, type Status } from './StatusBadge';
import { formatAmount, timeAgo } from './format';

/* ---------------------------------------------------------------- payments */

export interface FeedPayment {
    name: string;
    receipt?: string;
    phone?: string;         // already masked by the API ("0722 ••• 418")
    amount: number;
    date: string;
    method?: string;        // mpesa | cash | bank | balance | other
    service_type?: string;  // hotspot | pppoe | static
    plan?: string;
}

/** M-Pesa receipt, masked MSISDN, amount, relative time. */
export function PaymentsFeedRow({ payment }: { payment: FeedPayment }) {
    const hotspot = payment.service_type === 'hotspot';
    const Icon = payment.method === 'mpesa' ? (hotspot ? Wifi : Zap) : Banknote;
    const title = hotspot && payment.plan ? `Hotspot · ${payment.plan}` : payment.name;
    const detail = [payment.receipt || (payment.method && payment.method !== 'mpesa' ? payment.method : ''), payment.phone]
        .filter(Boolean)
        .join(' · ');
    return (
        <div className="flex items-center gap-3 border-t border-border-soft py-3 first:border-t-0">
            <span
                className={cn(
                    'grid h-10 w-10 shrink-0 place-items-center rounded-full',
                    hotspot ? 'bg-chip text-muted-foreground' : 'bg-ok-bg text-mpesa',
                )}
            >
                <Icon className="h-[18px] w-[18px]" strokeWidth={1.8} />
            </span>
            <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] font-semibold text-foreground">{title}</p>
                <p className="num truncate text-[12.5px] uppercase text-muted-foreground">{detail || '—'}</p>
            </div>
            <div className="text-right">
                <p className="num text-[14px] font-bold text-foreground">+{formatAmount(payment.amount)}</p>
                <p className="text-[12px] text-faint">{timeAgo(payment.date)}</p>
            </div>
        </div>
    );
}

/* ------------------------------------------------------------- site health */

export interface SiteHealth {
    name: string;
    model?: string | null;
    clients: number;
    status: Status;          // online | degraded | offline | unknown
    cpu?: number | null;     // %
    throughput?: string | null;
}

/** Site name, router model, client count, CPU bar (warn colour > 60%), throughput. */
export function SiteHealthRow({ site }: { site: SiteHealth }) {
    const cpu = site.cpu ?? null;
    const hot = cpu != null && cpu > 60;
    return (
        <div className="border-t border-border-soft py-3.5 first:border-t-0">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="truncate text-[14px] font-semibold text-foreground">{site.name}</p>
                    <p className="truncate text-[12.5px] text-muted-foreground">
                        {[site.model, `${site.clients} client${site.clients === 1 ? '' : 's'}`].filter(Boolean).join(' · ')}
                    </p>
                </div>
                <StatusBadge status={site.status} label={site.status === 'unknown' ? 'Checking' : undefined} />
            </div>
            <div className="mt-2.5 flex items-center gap-3 text-[12px]">
                <span className="num w-14 shrink-0 text-faint">CPU {cpu != null ? `${cpu}%` : '—'}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-chip" role="meter" aria-label={`${site.name} CPU`} aria-valuenow={cpu ?? 0} aria-valuemin={0} aria-valuemax={100}>
                    <div
                        className={cn('h-full rounded-full', hot ? 'bg-warn' : 'bg-primary')}
                        style={{ width: `${Math.min(100, Math.max(cpu ?? 0, cpu ? 2 : 0))}%` }}
                    />
                </div>
                <span className="num w-20 shrink-0 text-right text-muted-foreground">{site.throughput || '—'}</span>
            </div>
        </div>
    );
}

/* ------------------------------------------------------------------ alerts */

const ALERT_TONE = {
    bad: 'bg-bad-bg text-bad',
    warn: 'bg-warn-bg text-warn',
    ok: 'bg-ok-bg text-ok',
    neutral: 'bg-chip text-muted-foreground',
} as const;

/** Tinted icon square + title + detail. */
export function AlertRow({ icon: Icon, tone, title, detail, onClick }: {
    icon: LucideIcon;
    tone: keyof typeof ALERT_TONE;
    title: React.ReactNode;
    detail?: React.ReactNode;
    onClick?: () => void;
}) {
    const Wrapper = onClick ? 'button' : 'div';
    return (
        <Wrapper onClick={onClick} className="flex w-full items-start gap-3 border-t border-border-soft py-3.5 text-left first:border-t-0">
            <span className={cn('grid h-10 w-10 shrink-0 place-items-center rounded-full', ALERT_TONE[tone])}>
                <Icon className="h-[18px] w-[18px]" strokeWidth={1.8} />
            </span>
            <div className="min-w-0">
                <p className="text-[14px] font-semibold text-foreground">{title}</p>
                {detail && <p className="text-[12.5px] text-muted-foreground">{detail}</p>}
            </div>
        </Wrapper>
    );
}
