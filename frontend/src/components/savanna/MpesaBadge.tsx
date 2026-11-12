import { cn } from '@/lib/utils';

/** Small green M-PESA pill (#3BB54A, white, 800 weight). */
export function MpesaBadge({ className }: { className?: string }) {
    return (
        <span
            className={cn(
                'inline-flex h-[22px] items-center rounded-md bg-mpesa px-2 text-[11px] font-extrabold tracking-wide text-white',
                className,
            )}
        >
            M-PESA
        </span>
    );
}
