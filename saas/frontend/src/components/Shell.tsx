import { useCallback, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import { Cloud, LogOut, Menu, Moon, Sun, X } from 'lucide-react';
import { BandRings, ShellContext, initials } from '@/components/savanna';
import { useThemeStore } from '@/store/themeStore';
import { cn } from '@/lib/utils';
import { useAuth } from '~/lib/auth';

export interface NavItem { name: string; href: string; icon: LucideIcon; adminOnly?: boolean }

/**
 * The ISP app's Savanna shell (green header band, pill navigation, rings),
 * for the master app. Pages put their title in the band with <ShellHeader>.
 */
export default function Shell({ nav, brand, home }: { nav: NavItem[]; brand: string; home: string }) {
    const [slot, setSlot] = useState<HTMLElement | null>(null);
    const [hasHeader, setHasHeaderState] = useState(false);
    const setHasHeader = useCallback((v: boolean) => setHasHeaderState(v), []);
    const [drawer, setDrawer] = useState(false);
    const location = useLocation();
    const navigate = useNavigate();
    const user = useAuth((s) => s.user);
    const logout = useAuth((s) => s.logout);
    const theme = useThemeStore((s) => s.theme);
    const toggleTheme = useThemeStore((s) => s.toggleTheme);
    const items = nav.filter((n) => !n.adminOnly || user?.is_platform_admin);
    const active = (href: string) => (href === home ? location.pathname === href : location.pathname.startsWith(href));
    const iconButton = 'grid h-11 w-11 place-items-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20';
    const signOut = () => { logout(); navigate('/login'); };

    return (
        <ShellContext.Provider value={{ slot, setHasHeader }}>
            <div className="min-h-screen bg-background">
                <header className={cn('relative overflow-hidden bg-band text-white', hasHeader ? 'pb-[142px]' : 'pb-6')}>
                    <BandRings />
                    <div className="relative px-5 pt-5 lg:px-9">
                        <div className="flex items-center gap-4">
                            <button onClick={() => setDrawer(true)} className={cn(iconButton, 'xl:hidden')} aria-label="Open navigation">
                                <Menu className="h-5 w-5" />
                            </button>
                            <Link to={home} className="flex shrink-0 items-center gap-3">
                                <span className="grid h-11 w-11 place-items-center rounded-full bg-sunset"><Cloud className="h-5 w-5" strokeWidth={2.4} /></span>
                                <span className="hidden text-[19px] font-extrabold tracking-tight sm:inline">{brand}</span>
                            </Link>
                            <nav className="ml-4 hidden min-w-0 flex-1 items-center gap-0.5 xl:flex" aria-label="Main">
                                {items.map((item) => (
                                    <Link key={item.href} to={item.href} aria-current={active(item.href) ? 'page' : undefined}
                                        className={cn('flex h-11 shrink-0 items-center gap-2 rounded-full px-3.5 text-[14px] font-semibold transition-colors',
                                            active(item.href) ? 'bg-white text-primary' : 'text-white/80 hover:bg-white/10 hover:text-white')}>
                                        <item.icon className="h-[18px] w-[18px]" strokeWidth={1.8} />{item.name}
                                    </Link>
                                ))}
                            </nav>
                            <div className="ml-auto flex shrink-0 items-center gap-2.5">
                                <button onClick={toggleTheme} className={iconButton} aria-label={theme === 'dark' ? 'Light mode' : 'Dark mode'}>
                                    {theme === 'dark' ? <Sun className="h-5 w-5" strokeWidth={1.8} /> : <Moon className="h-5 w-5" strokeWidth={1.8} />}
                                </button>
                                <span className="hidden text-right text-[12.5px] leading-tight text-white/80 md:block">
                                    <span className="block font-semibold text-white">{user?.full_name}</span>{user?.email}
                                </span>
                                <span className="grid h-11 w-11 place-items-center rounded-full bg-[#F4C542] text-[14px] font-extrabold text-[#5A3A00]">
                                    {initials(user?.full_name || user?.email)}
                                </span>
                                <button onClick={signOut} className={iconButton} aria-label="Sign out" title="Sign out"><LogOut className="h-5 w-5" strokeWidth={1.8} /></button>
                            </div>
                        </div>
                        <div ref={setSlot} className={hasHeader ? 'mt-10' : 'hidden'} />
                    </div>
                </header>

                <main className={cn('relative px-5 pb-12 lg:px-9', hasHeader ? '-mt-[110px]' : 'mt-6')}>
                    <Outlet />
                </main>

                {drawer && (
                    <div className="fixed inset-0 z-50 xl:hidden">
                        <div className="absolute inset-0 bg-black/40" onClick={() => setDrawer(false)} />
                        <aside className="absolute left-0 top-0 h-full w-72 bg-band p-5 text-white shadow-xl">
                            <div className="mb-6 flex items-center justify-between">
                                <span className="text-[18px] font-extrabold">{brand}</span>
                                <button onClick={() => setDrawer(false)} className={iconButton} aria-label="Close navigation"><X className="h-5 w-5" /></button>
                            </div>
                            <nav className="space-y-1">
                                {items.map((item) => (
                                    <Link key={item.href} to={item.href} onClick={() => setDrawer(false)}
                                        className={cn('flex h-11 items-center gap-3 rounded-full px-4 text-[14px] font-semibold',
                                            active(item.href) ? 'bg-white text-primary' : 'text-white/85 hover:bg-white/10')}>
                                        <item.icon className="h-[18px] w-[18px]" />{item.name}
                                    </Link>
                                ))}
                            </nav>
                        </aside>
                    </div>
                )}
            </div>
        </ShellContext.Provider>
    );
}
