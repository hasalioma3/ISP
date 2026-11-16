import { useCallback, useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import {
    LayoutGrid,
    Users,
    LineChart,
    Settings,
    Ticket,
    Router as RouterIcon,
    LogOut,
    Menu,
    Search,
    Zap,
    ChevronDown,
    UsersRound,
    Radio,
    Package,
    Database,
    UserCog,
    KeyRound,
    CreditCard,
    Activity,
    Wallet,
    Boxes,
    Wifi,
    X,
    MoreHorizontal,
    ScrollText,
    Moon,
    Sun,
    MessageSquare,
} from 'lucide-react';
import { useSiteSettings } from '../hooks/useSiteSettings';
import AccountModal from './AccountModal';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { useThemeStore } from '../store/themeStore';
import { BandRings, ShellContext, initials as toInitials } from './savanna';
import { cn } from '@/lib/utils';

// How many nav items show as pills before the rest go under "More": a
// compact set between 1280px and 1536px (8 pills + More + the right-hand
// buttons overflowed into the search button there), the full set above.
const INLINE_NAV = 5;
const INLINE_NAV_WIDE = 8;

/**
 * Savanna admin shell (design/HANDOFF.md §3): no sidebar; a deep-green
 * header band with pill navigation (active = white pill) and decorative
 * rings. Pages that render <ShellHeader> get their title in the band and
 * their first cards overlapping it by ~110px; other pages keep their own
 * headings below a slim band. Below 1280px the nav collapses into a drawer.
 */
export default function AdminLayout() {
    const [isDrawerOpen, setIsDrawerOpen] = useState(false);
    const [isSearchOpen, setIsSearchOpen] = useState(false);
    const [accountModalTab, setAccountModalTab] = useState<'profile' | 'password' | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [headerSlot, setHeaderSlot] = useState<HTMLElement | null>(null);
    const [hasHeader, setHasHeaderState] = useState(false);
    const setHasHeader = useCallback((v: boolean) => setHasHeaderState(v), []);
    const location = useLocation();
    const navigate = useNavigate();
    const logout = useAuthStore((state) => state.logout);
    const user = useAuthStore((state) => state.user);
    const { data: siteSettings } = useSiteSettings();
    const theme = useThemeStore((s) => s.theme);
    const toggleTheme = useThemeStore((s) => s.toggleTheme);

    // Undefined `roles` means visible to every staff role. Superusers
    // always see everything regardless of role.
    const allNavigation = [
        { name: 'Overview', href: '/admin/dashboard', icon: LayoutGrid },
        { name: 'Subscribers', href: '/admin/subscribers', icon: Users },
        { name: 'Online', href: '/admin/online-users', icon: Radio, roles: ['admin', 'technician'] },
        { name: 'Network', href: '/admin/mikrotik', icon: RouterIcon, roles: ['admin', 'technician'] },
        { name: 'Vouchers', href: '/admin/vouchers', icon: Ticket, roles: ['admin', 'sales'] },
        { name: 'Plans', href: '/admin/billing-plans', icon: Package, roles: ['admin'] },
        { name: 'Payments', href: '/admin/payments', icon: CreditCard, roles: ['admin'] },
        { name: 'Reports', href: '/admin/reports', icon: LineChart, roles: ['admin', 'sales'] },
        { name: 'Data Usage', href: '/admin/data-usage', icon: Database },
        { name: 'Network Ops', href: '/admin/network-ops', icon: Activity, roles: ['admin', 'technician'] },
        { name: 'Accounting', href: '/admin/accounting', icon: Wallet, roles: ['admin', 'sales'] },
        { name: 'Inventory', href: '/admin/inventory', icon: Boxes },
        { name: 'Messages', href: '/admin/messages', icon: MessageSquare, roles: ['admin'] },
        { name: 'Settings', href: '/admin/settings', icon: Settings, roles: ['admin'] },
        // Superadmins only (empty role list, so only the superuser bypass passes).
        { name: 'Logs', href: '/admin/logs', icon: ScrollText, roles: [] as string[] },
    ];
    const canSee = (roles?: string[]) => !roles || user?.is_superuser || roles.includes(user?.role || '');
    const navigation = allNavigation.filter(item => canSee(item.roles));
    const inlineNav = navigation.slice(0, INLINE_NAV_WIDE);
    const moreNav = navigation.slice(INLINE_NAV);
    const isActive = (href: string) => location.pathname.startsWith(href);
    // "More" is highlighted when the current page sits inside it, which
    // differs between the compact and wide layouts.
    const moreActive = moreNav.some((item) => isActive(item.href));
    const moreActiveWide = navigation.slice(INLINE_NAV_WIDE).some((item) => isActive(item.href));
    const hasMoreWide = navigation.length > INLINE_NAV_WIDE;

    const allQuickActions = [
        { name: 'Generate Vouchers', icon: Ticket, href: '/admin/vouchers', roles: ['admin', 'sales'] },
        { name: 'Manage Subscribers', icon: UsersRound, href: '/admin/subscribers' },
        { name: 'Add / Provision Router', icon: RouterIcon, href: '/admin/mikrotik', roles: ['admin', 'technician'] },
    ];
    const quickActions = allQuickActions.filter(item => canSee(item.roles));

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        if (searchTerm.trim()) {
            navigate(`/admin/subscribers?search=${encodeURIComponent(searchTerm.trim())}`);
            setIsSearchOpen(false);
        }
    };

    const companyName = siteSettings?.company_name || 'ISP Admin';
    const avatarText = toInitials(user?.full_name || user?.first_name || user?.username || 'A');
    const iconButton = 'grid h-11 w-11 place-items-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20';

    return (
        <ShellContext.Provider value={{ slot: headerSlot, setHasHeader }}>
            <div className="min-h-screen bg-background">
                {/* Header band */}
                <header className={cn('relative overflow-hidden bg-band text-white', hasHeader ? 'pb-[142px]' : 'pb-6')}>
                    <BandRings />
                    <div className="relative px-5 pt-5 lg:px-9">
                        <div className="flex items-center gap-4">
                            <button
                                onClick={() => setIsDrawerOpen(true)}
                                className={cn(iconButton, 'xl:hidden')}
                                aria-label="Open navigation"
                            >
                                <Menu className="h-5 w-5" />
                            </button>

                            <Link to="/admin/dashboard" className="flex shrink-0 items-center gap-3 rounded-full">
                                {siteSettings?.logo ? (
                                    <img src={siteSettings.logo} alt="" className="h-11 w-11 rounded-full bg-white object-contain p-1" />
                                ) : (
                                    <span className="grid h-11 w-11 place-items-center rounded-full bg-sunset">
                                        <Wifi className="h-5 w-5" strokeWidth={2.4} />
                                    </span>
                                )}
                                <span className="hidden text-[19px] font-extrabold tracking-tight sm:inline">{companyName}</span>
                            </Link>

                            <nav className="ml-4 hidden min-w-0 flex-1 items-center gap-0.5 overflow-hidden xl:flex" aria-label="Main">
                                {inlineNav.map((item, index) => (
                                    <Link
                                        key={item.href}
                                        to={item.href}
                                        aria-current={isActive(item.href) ? 'page' : undefined}
                                        className={cn(
                                            'flex h-11 shrink-0 items-center gap-2 rounded-full px-3.5 text-[14px] font-semibold transition-colors',
                                            index >= INLINE_NAV && 'hidden 2xl:flex',
                                            isActive(item.href)
                                                ? 'bg-white text-primary'
                                                : 'text-white/80 hover:bg-white/10 hover:text-white',
                                        )}
                                    >
                                        <item.icon className="h-[18px] w-[18px]" strokeWidth={1.8} />
                                        {item.name}
                                    </Link>
                                ))}
                                {moreNav.length > 0 && (
                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <button
                                                className={cn(
                                                    'flex h-11 shrink-0 items-center gap-2 rounded-full px-3.5 text-[14px] font-semibold transition-colors',
                                                    !hasMoreWide && '2xl:hidden',
                                                    moreActive ? 'bg-white text-primary' : 'text-white/80 hover:bg-white/10 hover:text-white',
                                                    moreActive !== moreActiveWide && (moreActiveWide
                                                        ? '2xl:bg-white 2xl:text-primary'
                                                        : '2xl:bg-transparent 2xl:text-white/80'),
                                                )}
                                            >
                                                <MoreHorizontal className="h-[18px] w-[18px]" strokeWidth={1.8} />
                                                More
                                                <ChevronDown className="h-3.5 w-3.5" />
                                            </button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="start" className="w-52">
                                            {moreNav.map((item, index) => (
                                                <DropdownMenuItem
                                                    key={item.href}
                                                    onClick={() => navigate(item.href)}
                                                    // Shown as a pill on wide screens, so only listed here below 1536px.
                                                    className={INLINE_NAV + index < INLINE_NAV_WIDE ? '2xl:hidden' : undefined}
                                                >
                                                    <item.icon className="h-4 w-4" />
                                                    {item.name}
                                                </DropdownMenuItem>
                                            ))}
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                )}
                            </nav>

                            <div className="ml-auto flex shrink-0 items-center gap-2.5">
                                {isSearchOpen ? (
                                    <form onSubmit={handleSearch} className="relative">
                                        <Search className="absolute left-3.5 top-3 h-4 w-4 text-white/70" />
                                        <input
                                            autoFocus
                                            type="search"
                                            placeholder="Name, phone, username..."
                                            aria-label="Search subscribers"
                                            value={searchTerm}
                                            onChange={(e) => setSearchTerm(e.target.value)}
                                            onBlur={() => !searchTerm && setIsSearchOpen(false)}
                                            className="h-11 w-56 rounded-full border border-white/20 bg-white/10 pl-10 pr-4 text-[14px] text-white placeholder:text-white/60 focus:outline-none focus:ring-2 focus:ring-white/60"
                                        />
                                    </form>
                                ) : (
                                    <button onClick={() => setIsSearchOpen(true)} className={iconButton} aria-label="Search subscribers">
                                        <Search className="h-5 w-5" strokeWidth={1.8} />
                                    </button>
                                )}

                                <button
                                    onClick={toggleTheme}
                                    className={iconButton}
                                    aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                                    title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                                >
                                    {theme === 'dark' ? <Sun className="h-5 w-5" strokeWidth={1.8} /> : <Moon className="h-5 w-5" strokeWidth={1.8} />}
                                </button>

                                <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                        <button className={iconButton} aria-label="Quick actions">
                                            <Zap className="h-5 w-5" strokeWidth={1.8} />
                                        </button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end" className="w-56">
                                        <DropdownMenuLabel>Quick actions</DropdownMenuLabel>
                                        {quickActions.map((action) => (
                                            <DropdownMenuItem key={action.name} onClick={() => navigate(action.href)}>
                                                <action.icon className="h-4 w-4" />
                                                {action.name}
                                            </DropdownMenuItem>
                                        ))}
                                    </DropdownMenuContent>
                                </DropdownMenu>

                                <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                        <button
                                            className="grid h-11 w-11 place-items-center rounded-full bg-[#F4C542] text-[14px] font-extrabold text-[#5A3A00]"
                                            aria-label="Account menu"
                                        >
                                            {avatarText}
                                        </button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end" className="w-56">
                                        <DropdownMenuLabel className="font-normal">
                                            <p className="truncate text-sm font-medium text-foreground">{user?.full_name || user?.username}</p>
                                            <p className="truncate text-xs font-normal text-muted-foreground">{user?.email || user?.username}</p>
                                        </DropdownMenuLabel>
                                        <DropdownMenuSeparator />
                                        <DropdownMenuItem onClick={() => setAccountModalTab('profile')}>
                                            <UserCog className="h-4 w-4" />
                                            Edit Profile
                                        </DropdownMenuItem>
                                        <DropdownMenuItem onClick={() => setAccountModalTab('password')}>
                                            <KeyRound className="h-4 w-4" />
                                            Change Password
                                        </DropdownMenuItem>
                                        <DropdownMenuSeparator />
                                        <DropdownMenuItem onClick={handleLogout} className="text-red-600 focus:text-red-600 [&_svg]:text-red-500">
                                            <LogOut className="h-4 w-4" />
                                            Sign Out
                                        </DropdownMenuItem>
                                    </DropdownMenuContent>
                                </DropdownMenu>
                            </div>
                        </div>

                        {/* Pages render their title/actions here via <ShellHeader>. */}
                        <div ref={setHeaderSlot} className={hasHeader ? 'mt-10' : 'hidden'} />
                    </div>
                </header>

                <main className={cn('relative px-5 pb-10 lg:px-9', hasHeader ? '-mt-[110px]' : 'pt-7')}>
                    <Outlet />
                </main>

                {/* Navigation drawer (below 1280px) */}
                {isDrawerOpen && (
                    <div className="fixed inset-0 z-50 xl:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
                        <div className="absolute inset-0 bg-black/40" onClick={() => setIsDrawerOpen(false)} />
                        <div className="absolute inset-y-0 left-0 flex w-72 flex-col bg-band text-white shadow-xl">
                            <div className="flex items-center justify-between px-5 py-5">
                                <span className="text-[18px] font-extrabold">{companyName}</span>
                                <button onClick={() => setIsDrawerOpen(false)} className={iconButton} aria-label="Close navigation">
                                    <X className="h-5 w-5" />
                                </button>
                            </div>
                            <nav className="flex-1 space-y-1 overflow-y-auto px-3" aria-label="Main">
                                {navigation.map((item) => (
                                    <Link
                                        key={item.href}
                                        to={item.href}
                                        onClick={() => setIsDrawerOpen(false)}
                                        aria-current={isActive(item.href) ? 'page' : undefined}
                                        className={cn(
                                            'flex h-11 items-center gap-3 rounded-full px-4 text-[14.5px] font-semibold',
                                            isActive(item.href) ? 'bg-white text-primary' : 'text-white/80 hover:bg-white/10',
                                        )}
                                    >
                                        <item.icon className="h-[18px] w-[18px]" strokeWidth={1.8} />
                                        {item.name}
                                    </Link>
                                ))}
                            </nav>
                            <div className="p-3">
                                <button
                                    onClick={handleLogout}
                                    className="flex h-11 w-full items-center gap-3 rounded-full px-4 text-[14.5px] font-semibold text-white/80 hover:bg-white/10"
                                >
                                    <LogOut className="h-[18px] w-[18px]" />
                                    Sign Out
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {accountModalTab && (
                    <AccountModal initialTab={accountModalTab} onClose={() => setAccountModalTab(null)} />
                )}
            </div>
        </ShellContext.Provider>
    );
}
