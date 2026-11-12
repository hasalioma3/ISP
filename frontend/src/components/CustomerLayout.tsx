import { useCallback, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { ChevronDown, KeyRound, LayoutDashboard, LogOut, UserCog, Wifi } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useSiteSettings } from '../hooks/useSiteSettings';
import AccountModal from './AccountModal';
import { ThemeToggle } from './ui/theme-toggle';
import {
    DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { ShellContext, initials } from './savanna';
import { cn } from '@/lib/utils';

const NAVIGATION = [
    { name: 'Overview', href: '/dashboard' },
    { name: 'Usage', href: '/usage' },
    { name: 'Payments', href: '/orders' },
    { name: 'Activations', href: '/activations' },
    { name: 'Plans', href: '/plans' },
];

/**
 * Savanna customer shell (design/HANDOFF.md §3): top nav only, inside the
 * deep-green band. Mobile-first: the nav scrolls sideways on small screens
 * rather than hiding behind a menu, since it's only five links. Pages may
 * render <ShellHeader> (or their own band content) the same way as admin.
 */
export default function CustomerLayout() {
    const location = useLocation();
    const navigate = useNavigate();
    const { user, logout } = useAuthStore();
    const { data: siteSettings } = useSiteSettings();
    const [accountModalTab, setAccountModalTab] = useState<'profile' | 'password' | null>(null);
    const [headerSlot, setHeaderSlot] = useState<HTMLElement | null>(null);
    const [hasHeader, setHasHeaderState] = useState(false);
    const setHasHeader = useCallback((v: boolean) => setHasHeaderState(v), []);

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const displayName = user?.full_name || user?.username || '';

    return (
        <ShellContext.Provider value={{ slot: headerSlot, setHasHeader }}>
            <div className="min-h-screen bg-background">
                <header className={cn('relative overflow-hidden bg-band text-white', hasHeader ? 'pb-[150px]' : 'pb-6')}>
                    <svg className="pointer-events-none absolute -right-10 top-16 h-[360px] w-[520px] text-white/[0.05]" viewBox="0 0 520 360" fill="none" aria-hidden="true">
                        <circle cx="400" cy="70" r="64" fill="#F2772E" fillOpacity="0.35" />
                        <path d="M0 360 C120 200 240 180 330 250 C400 300 460 180 520 90 V360 Z" fill="currentColor" />
                    </svg>
                    <div className="relative mx-auto max-w-[1440px] px-4 pt-5 sm:px-8 lg:px-[72px]">
                        <div className="flex items-center gap-4">
                            <Link to="/dashboard" className="flex shrink-0 items-center gap-3">
                                {siteSettings?.logo ? (
                                    <img src={siteSettings.logo} alt="" className="h-10 w-10 rounded-full bg-white object-contain p-1" />
                                ) : (
                                    <span className="grid h-10 w-10 place-items-center rounded-full bg-sunset">
                                        <Wifi className="h-5 w-5" strokeWidth={2.4} />
                                    </span>
                                )}
                                <span className="hidden text-[19px] font-extrabold tracking-tight sm:inline">{siteSettings?.company_name || 'ISP Portal'}</span>
                            </Link>

                            <nav className="mx-auto hidden items-center gap-1 md:flex" aria-label="Account">
                                {NAVIGATION.map((item) => {
                                    const active = location.pathname.startsWith(item.href);
                                    return (
                                        <Link
                                            key={item.href}
                                            to={item.href}
                                            aria-current={active ? 'page' : undefined}
                                            className={cn(
                                                'flex h-11 items-center rounded-full px-5 text-[15px] font-semibold transition-colors',
                                                active ? 'bg-white text-primary' : 'text-white/80 hover:bg-white/10 hover:text-white',
                                            )}
                                        >
                                            {item.name}
                                        </Link>
                                    );
                                })}
                            </nav>

                            <div className="ml-auto flex items-center gap-2 md:ml-0">
                                <ThemeToggle className="grid h-10 w-10 place-items-center rounded-full bg-white/10 text-white hover:bg-white/20" />
                                <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                        <button className="flex items-center gap-3 rounded-full py-1 pl-1 pr-2 hover:bg-white/10" aria-label="Account menu">
                                            <span className="grid h-10 w-10 place-items-center rounded-full bg-[#F4C542] text-[13.5px] font-extrabold text-[#5A3A00]">
                                                {initials(displayName)}
                                            </span>
                                            <span className="hidden text-left leading-tight sm:block">
                                                <span className="block text-[14.5px] font-semibold">{displayName}</span>
                                                <span className="block text-[12.5px] text-white/70">{user?.username}</span>
                                            </span>
                                            <ChevronDown className="hidden h-4 w-4 text-white/70 sm:block" />
                                        </button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end" className="w-56">
                                        <DropdownMenuLabel className="font-normal">
                                            <p className="truncate text-sm font-medium text-foreground">{displayName}</p>
                                            <p className="truncate text-xs text-muted-foreground">{user?.phone_number || user?.email || user?.username}</p>
                                        </DropdownMenuLabel>
                                        <DropdownMenuSeparator />
                                        <DropdownMenuItem onClick={() => setAccountModalTab('profile')}><UserCog className="h-4 w-4" /> My account</DropdownMenuItem>
                                        <DropdownMenuItem onClick={() => setAccountModalTab('password')}><KeyRound className="h-4 w-4" /> Change password</DropdownMenuItem>
                                        {(user?.is_staff || user?.is_superuser) && (
                                            <DropdownMenuItem onClick={() => navigate('/admin')}><LayoutDashboard className="h-4 w-4" /> Admin dashboard</DropdownMenuItem>
                                        )}
                                        <DropdownMenuSeparator />
                                        <DropdownMenuItem onClick={handleLogout} className="text-red-600 focus:text-red-600 [&_svg]:text-red-500">
                                            <LogOut className="h-4 w-4" /> Sign out
                                        </DropdownMenuItem>
                                    </DropdownMenuContent>
                                </DropdownMenu>
                            </div>
                        </div>

                        {/* Mobile nav: a sideways-scrolling pill row. */}
                        <nav className="-mx-4 mt-4 flex gap-1 overflow-x-auto px-4 pb-1 md:hidden" aria-label="Account">
                            {NAVIGATION.map((item) => {
                                const active = location.pathname.startsWith(item.href);
                                return (
                                    <Link
                                        key={item.href}
                                        to={item.href}
                                        aria-current={active ? 'page' : undefined}
                                        className={cn(
                                            'flex h-10 shrink-0 items-center rounded-full px-4 text-[14px] font-semibold',
                                            active ? 'bg-white text-primary' : 'bg-white/10 text-white/85',
                                        )}
                                    >
                                        {item.name}
                                    </Link>
                                );
                            })}
                        </nav>

                        <div ref={setHeaderSlot} className={hasHeader ? 'mt-10 sm:mt-14' : 'hidden'} />
                    </div>
                </header>

                <main className={cn('relative mx-auto max-w-[1440px] px-4 pb-12 sm:px-8 lg:px-[72px]', hasHeader ? '-mt-[110px]' : 'pt-7')}>
                    <Outlet />
                </main>

                {accountModalTab && (
                    <AccountModal initialTab={accountModalTab} onClose={() => setAccountModalTab(null)} />
                )}
            </div>
        </ShellContext.Provider>
    );
}
