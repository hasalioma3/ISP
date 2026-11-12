import { cn } from '@/lib/utils';

interface SegmentedControlProps<T extends string> {
    options: readonly T[] | { value: T; label: string }[];
    value: T;
    onChange: (value: T) => void;
    'aria-label': string;
    className?: string;
}

/** 7D / 30D / 90D / 12M style toggle: chip track, active segment in primary. */
export function SegmentedControl<T extends string>({ options, value, onChange, className, ...rest }: SegmentedControlProps<T>) {
    const items = (options as readonly (T | { value: T; label: string })[]).map((o) =>
        typeof o === 'string' ? { value: o as T, label: o as string } : o,
    );
    return (
        <div role="radiogroup" aria-label={rest['aria-label']} className={cn('inline-flex rounded-full bg-chip p-1', className)}>
            {items.map((item) => {
                const active = item.value === value;
                return (
                    <button
                        key={item.value}
                        type="button"
                        role="radio"
                        aria-checked={active}
                        onClick={() => onChange(item.value)}
                        className={cn(
                            'h-7 rounded-full px-3.5 text-[12.5px] font-semibold transition-colors',
                            active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
                        )}
                    >
                        {item.label}
                    </button>
                );
            })}
        </div>
    );
}
