import * as React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { StatusBadge, type Status } from '@/components/savanna';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';

export { Button } from '@/components/ui/button';

export const inputClass =
    'h-[42px] w-full rounded-xl border border-input bg-card px-3.5 text-[14px] text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-60';

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
    ({ className, ...props }, ref) => <input ref={ref} className={cn(inputClass, className)} {...props} />,
);
Input.displayName = 'Input';

export function Select({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
    return <select className={cn(inputClass, 'pr-8', className)} {...props}>{children}</select>;
}

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
    return <textarea className={cn(inputClass, 'h-auto min-h-[90px] py-2.5', className)} {...props} />;
}

export function Field({ label, hint, error, children, className }: {
    label: React.ReactNode; hint?: React.ReactNode; error?: string | null; children: React.ReactNode; className?: string;
}) {
    return (
        <label className={cn('block', className)}>
            <span className="mb-1.5 block text-[13px] font-semibold text-foreground/85">{label}</span>
            {children}
            {error ? <span className="mt-1 block text-[12.5px] text-bad">{error}</span>
                : hint ? <span className="mt-1 block text-[12.5px] text-muted-foreground">{hint}</span> : null}
        </label>
    );
}

export function Toggle({ checked, onChange, label, hint, disabled }: {
    checked: boolean; onChange: (v: boolean) => void; label: React.ReactNode; hint?: React.ReactNode; disabled?: boolean;
}) {
    return (
        <label className={cn('flex cursor-pointer items-start gap-3', disabled && 'cursor-not-allowed opacity-60')}>
            <button
                type="button" role="switch" aria-checked={checked} disabled={disabled} onClick={() => onChange(!checked)}
                className={cn('relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors', checked ? 'bg-primary' : 'bg-border-strong/60')}
            >
                <span className={cn('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform', checked ? 'translate-x-[22px]' : 'translate-x-0.5')} />
            </button>
            <span className="text-[14px]">
                <span className="font-medium">{label}</span>
                {hint && <span className="mt-0.5 block text-[12.5px] text-muted-foreground">{hint}</span>}
            </span>
        </label>
    );
}

export function Modal({ open, onClose, title, description, children, wide }: {
    open: boolean; onClose: () => void; title: React.ReactNode; description?: React.ReactNode; children: React.ReactNode; wide?: boolean;
}) {
    return (
        <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
            <DialogContent className={cn('max-h-[90vh] overflow-y-auto', wide ? 'sm:max-w-2xl' : 'sm:max-w-lg')}>
                <DialogHeader>
                    <DialogTitle>{title}</DialogTitle>
                    {description && <DialogDescription>{description}</DialogDescription>}
                </DialogHeader>
                {children}
            </DialogContent>
        </Dialog>
    );
}

export function Spinner({ className }: { className?: string }) {
    return <Loader2 className={cn('h-4 w-4 animate-spin', className)} />;
}

export function Notice({ tone = 'warn', children, className }: { tone?: 'warn' | 'bad' | 'ok' | 'info'; children: React.ReactNode; className?: string }) {
    const tones = { warn: 'bg-warn-bg text-warn', bad: 'bg-bad-bg text-bad', ok: 'bg-ok-bg text-ok', info: 'bg-accent text-primary' };
    return <div className={cn('rounded-xl px-4 py-3 text-[13.5px]', tones[tone], className)}>{children}</div>;
}

const TENANT_TONE: Record<string, Status> = {
    pending: 'pending', provisioning: 'pending', trial: 'expiring', active: 'active', past_due: 'degraded',
    suspended: 'suspended', cancelled: 'inactive', failed: 'failed', deleted: 'inactive',
};

export function TenantStatus({ status, label }: { status: string; label?: string }) {
    return <StatusBadge status={TENANT_TONE[status] || 'unknown'} label={label} />;
}

const GENERIC_TONE: Record<string, Status> = {
    paid: 'active', succeeded: 'active', ok: 'active', running: 'online', open: 'pending', pending_approval: 'pending',
    queued: 'pending', processing: 'pending', failed: 'failed', void: 'inactive', cancelled: 'inactive',
    stopped: 'suspended', unhealthy: 'degraded', missing: 'offline',
};

export function Pill({ status, label }: { status: string; label?: string }) {
    return <StatusBadge status={GENERIC_TONE[status] || 'unknown'} label={label} />;
}

/** Plain table with the Savanna look. */
export function Table({ head, children, empty, loading, colSpan }: {
    head: React.ReactNode[]; children?: React.ReactNode; empty?: React.ReactNode; loading?: boolean; colSpan?: number;
}) {
    const span = colSpan ?? head.length;
    const rows = React.Children.toArray(children).filter(Boolean);
    return (
        <div className="-mx-[22px] overflow-x-auto">
            <table className="w-full min-w-[640px] text-[13.5px]">
                <thead>
                    <tr className="border-b border-border-soft text-left text-[11.5px] font-semibold uppercase tracking-wide text-muted-foreground">
                        {head.map((h, i) => <th key={i} className="whitespace-nowrap px-[22px] py-2.5 font-semibold first:pl-[22px]">{h}</th>)}
                    </tr>
                </thead>
                <tbody>
                    {loading ? (
                        <tr><td colSpan={span} className="px-[22px] py-10 text-center text-muted-foreground"><Spinner className="mx-auto" /></td></tr>
                    ) : rows.length ? rows : (
                        <tr><td colSpan={span} className="px-[22px] py-10 text-center text-muted-foreground">{empty || 'Nothing here yet.'}</td></tr>
                    )}
                </tbody>
            </table>
        </div>
    );
}

export const Td = ({ className, ...p }: React.TdHTMLAttributes<HTMLTableCellElement>) =>
    <td className={cn('whitespace-nowrap border-b border-border-soft px-[22px] py-3 align-middle', className)} {...p} />;

export function Pager({ page, count, pageSize = 20, onPage }: { page: number; count: number; pageSize?: number; onPage: (p: number) => void }) {
    const pages = Math.max(1, Math.ceil(count / pageSize));
    if (pages <= 1) return null;
    return (
        <div className="mt-4 flex items-center justify-between text-[13px] text-muted-foreground">
            <span>{count} total</span>
            <div className="flex items-center gap-2">
                <button className="rounded-full border px-3 py-1 disabled:opacity-40" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
                <span>Page {page} of {pages}</span>
                <button className="rounded-full border px-3 py-1 disabled:opacity-40" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
            </div>
        </div>
    );
}

export function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
    return (
        <div>
            <p className="text-[12.5px] font-medium text-muted-foreground">{label}</p>
            <p className="num mt-1 text-[20px] font-extrabold leading-tight">{value}</p>
            {sub && <p className="mt-0.5 text-[12px] text-muted-foreground">{sub}</p>}
        </div>
    );
}
