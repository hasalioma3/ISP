import { Cloud } from 'lucide-react';
import { BandRings } from '@/components/savanna';

/** Green band left (brand, pitch), form right -- stacks on phones. */
export default function AuthLayout({ title, pitch, children, wide }: { title: string; pitch: React.ReactNode; children: React.ReactNode; wide?: boolean }) {
    return (
        <div className="min-h-screen bg-background lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
            <section className="relative overflow-hidden bg-band px-6 py-10 text-white lg:px-12 lg:py-14">
                <BandRings />
                <div className="relative">
                    <div className="flex items-center gap-3">
                        <span className="grid h-11 w-11 place-items-center rounded-full bg-sunset"><Cloud className="h-5 w-5" strokeWidth={2.4} /></span>
                        <span className="text-[19px] font-extrabold tracking-tight">ISP Cloud</span>
                    </div>
                    <h1 className="mt-10 max-w-md text-[30px] font-extrabold leading-tight tracking-tight sm:text-[38px]">{title}</h1>
                    <div className="mt-4 max-w-md text-[15px] text-white/80">{pitch}</div>
                </div>
            </section>
            <section className="flex items-start justify-center px-5 py-10 lg:items-center lg:py-14">
                <div className={wide ? 'w-full max-w-2xl' : 'w-full max-w-md'}>{children}</div>
            </section>
        </div>
    );
}
