import { createContext, useContext, useEffect } from 'react';
import { createPortal } from 'react-dom';

/**
 * The admin/customer shells render a deep-green header band. A page that
 * wants its title in the band (and its first row of cards overlapping it,
 * per the design) renders <ShellHeader>; pages that don't keep their own
 * in-content headings and the band stays a slim nav bar.
 */
interface ShellContextValue {
    slot: HTMLElement | null;
    setHasHeader: (value: boolean) => void;
}

export const ShellContext = createContext<ShellContextValue>({ slot: null, setHasHeader: () => {} });

interface ShellHeaderProps {
    title: React.ReactNode;
    subtitle?: React.ReactNode;
    /** Right-side buttons (use Button variant="sunset" for the primary CTA). */
    actions?: React.ReactNode;
}

export function ShellHeader({ title, subtitle, actions }: ShellHeaderProps) {
    const { slot, setHasHeader } = useContext(ShellContext);

    useEffect(() => {
        setHasHeader(true);
        return () => setHasHeader(false);
    }, [setHasHeader]);

    if (!slot) return null;
    return createPortal(
        <div className="flex flex-wrap items-end justify-between gap-4">
            <div className="min-w-0">
                <h1 className="text-[28px] font-extrabold leading-tight tracking-tight text-white sm:text-[34px]">{title}</h1>
                {subtitle && <p className="mt-1.5 text-[14px] text-white/75">{subtitle}</p>}
            </div>
            {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
        </div>,
        slot,
    );
}

/** Outline button for use on the green band ("Export", "Import CSV"). */
export const bandButtonClass =
    'inline-flex h-[42px] items-center gap-2 rounded-full border border-white/25 bg-white/5 px-5 text-[14px] font-semibold text-white transition-colors hover:bg-white/10';

/** Orange primary CTA on the band ("New subscriber"). */
export const bandCtaClass =
    'inline-flex h-[42px] items-center gap-2 rounded-full bg-sunset px-5 text-[14px] font-semibold text-white shadow-sm transition-colors hover:bg-sunset/90';

/** Decorative concentric circles, top-right of the band. */
export function BandRings() {
    return (
        <svg className="pointer-events-none absolute -right-24 -top-28 h-[440px] w-[440px] text-white/[0.06]" viewBox="0 0 440 440" fill="none" aria-hidden="true">
            <circle cx="220" cy="220" r="200" stroke="currentColor" strokeWidth="40" />
            <circle cx="220" cy="220" r="120" stroke="#F2772E" strokeOpacity="0.18" strokeWidth="28" />
        </svg>
    );
}
