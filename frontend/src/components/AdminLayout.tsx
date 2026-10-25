import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import {
    LayoutDashboard,
    Users,
    BarChart,
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
    Bell,
    Wifi,
} from 'lucide-react';
import { useState } from 'react';
import { useSiteSettings } from '../hooks/useSiteSettings';
import AccountModal from './AccountModal';
import { Avatar, AvatarFallback, AvatarImage } from './ui/avatar';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { SidebarNavItem } from './ui/sidebar-nav-item';
import { ThemeToggle } from './ui/theme-toggle';

export default function AdminLayout() {
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [accountModalTab, setAccountModalTab] = useState<'profile' | 'password' | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const location = useLocation();
    const navigate = useNavigate();
    const logout = useAuthStore((state) => state.logout);
    const user = useAuthStore((state) => state.user);
    const { data: siteSettings } = useSiteSettings();

    // Undefined `roles` means visible to every staff role. Superusers
    // always see everything regardless of role.
    const allNavigation = [
        { name: 'Dashboard', href: '/admin/dashboard', icon: LayoutDashboard },
        { name: 'Subscribers', href: '/admin/subscribers', icon: Users },
        { name: 'Online Users', href: '/admin/online-users', icon: Radio, roles: ['admin', 'technician'] },
        { name: 'Data Usage', href: '/admin/data-usage', icon: Database },
        { name: 'Network Ops', href: '/admin/network-ops', icon: Activity, roles: ['admin', 'technician'] },
        { name: 'Payments', href: '/admin/payments', icon: CreditCard, roles: ['admin'] },
        { name: 'Accounting', href: '/admin/accounting', icon: Wallet, roles: ['admin', 'sales'] },
        { name: 'Inventory', href: '/admin/inventory', icon: Boxes },
        { name: 'Reports', href: '/admin/reports', icon: BarChart, roles: ['admin', 'sales'] },
        { name: 'Vouchers', href: '/admin/vouchers', icon: Ticket, roles: ['admin', 'sales'] },
        { name: 'MikroTik', href: '/admin/mikrotik', icon: RouterIcon, roles: ['admin', 'technician'] },
        { name: 'CPE Devices', href: '/admin/cpe-devices', icon: Wifi, roles: ['admin', 'technician'] },
        { name: 'Billing Plans', href: '/admin/billing-plans', icon: Package, roles: ['admin'] },
        { name: 'Settings', href: '/admin/settings', icon: Settings, roles: ['admin'] },
    ];
    const canSee = (roles?: string[]) => !roles || user?.is_superuser || roles.includes(user?.role || '');
    const navigation = allNavigation.filter(item => canSee(item.roles));

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
        }
    };

    const initials = (user?.first_name || user?.username || 'A')[0].toUpperCase();

    return (
        <div className="min-h-screen bg-background flex">
            {/* Mobile Sidebar Overlay */}
            {isSidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/50 z-40 lg:hidden"
                    onClick={() => setIsSidebarOpen(false)}
                />
            )}

            {/* Sidebar */}
            <div className={`
        fixed lg:static inset-y-0 left-0 z-50 w-64 bg-card border-r border-border transform transition-transform duration-200 ease-in-out
        ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
                <div className="h-full flex flex-col">
                    <div className="px-5 py-5 border-b border-border">
                        <Link
                            to="/admin/dashboard"
                            onClick={() => setIsSidebarOpen(false)}
                            className="flex items-center gap-2.5 hover:opacity-80 transition-opacity"
                        >
                            {siteSettings?.logo ? (
                                <img src={siteSettings.logo} alt={siteSettings.company_name} className="h-8 w-8 rounded-lg object-contain bg-accent" />
                            ) : (
                                <div className="h-8 w-8 rounded-lg bg-primary text-primary-foreground flex items-center justify-center font-bold text-sm shrink-0">
                                    {(siteSettings?.company_name || 'I')[0].toUpperCase()}
                                </div>
                            )}
                            <h1 className="text-lg font-bold text-foreground truncate">{siteSettings?.company_name || 'ISP Admin'}</h1>
                        </Link>
                        <p className="text-xs text-muted-foreground mt-1">Welcome, {user?.first_name}</p>
                    </div>

                    <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
                        {navigation.map((item) => (
                            <SidebarNavItem
                                key={item.name}
                                href={item.href}
                                icon={item.icon}
                                label={item.name}
                                active={location.pathname.startsWith(item.href)}
                                onClick={() => setIsSidebarOpen(false)}
                            />
                        ))}
                    </nav>

                    <div className="p-3 border-t border-border">
                        <button
                            onClick={handleLogout}
                            className="flex items-center w-full gap-3 px-3.5 py-2.5 text-sm font-medium text-red-600 hover:bg-red-50 rounded-full transition-colors"
                        >
                            <LogOut className="h-4 w-4" />
                            Sign Out
                        </button>
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                {/* Top Bar */}
                <div className="bg-card border-b border-border flex items-center justify-between px-4 lg:px-6 py-3 gap-4">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                        <button
                            onClick={() => setIsSidebarOpen(true)}
                            className="p-2 -ml-2 text-muted-foreground hover:text-foreground lg:hidden"
                        >
                            <Menu className="h-6 w-6" />
                        </button>
                        <form onSubmit={handleSearch} className="hidden sm:block max-w-xs w-full">
                            <div className="relative">
                                <input
                                    type="text"
                                    placeholder="Search users..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="w-full bg-secondary border border-transparent rounded-lg pl-9 pr-3 py-1.5 text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:bg-background"
                                />
                                <Search className="absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" />
                            </div>
                        </form>
                    </div>

                    <div className="flex items-center gap-2">
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <button className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-accent rounded-lg text-sm font-medium text-foreground">
                                    <Zap className="h-4 w-4 text-amber-500" />
                                    <span className="hidden sm:inline">Quick Actions</span>
                                    <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                                </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-56">
                                {quickActions.map((action) => (
                                    <DropdownMenuItem key={action.name} onClick={() => navigate(action.href)}>
                                        <action.icon className="h-4 w-4" />
                                        {action.name}
                                    </DropdownMenuItem>
                                ))}
                            </DropdownMenuContent>
                        </DropdownMenu>

                        <button className="relative p-2 text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg">
                            <Bell className="h-5 w-5" />
                            <span className="absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full bg-red-500" />
                        </button>

                        <ThemeToggle />

                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <button className="flex items-center gap-2 hover:bg-accent rounded-lg px-1.5 py-1 -my-1 ml-1 border-l border-border pl-3">
                                    <Avatar className="h-8 w-8">
                                        {siteSettings?.logo ? <AvatarImage src={siteSettings.logo} /> : null}
                                        <AvatarFallback className="bg-primary/10 text-primary">{initials}</AvatarFallback>
                                    </Avatar>
                                    <span className="hidden sm:inline text-sm text-foreground">{user?.first_name || 'Administrator'}</span>
                                    <ChevronDown className="h-3.5 w-3.5 text-muted-foreground hidden sm:inline" />
                                </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-56">
                                <DropdownMenuLabel className="font-normal">
                                    <p className="text-sm font-medium text-foreground truncate">{user?.full_name || user?.username}</p>
                                    <p className="text-xs text-muted-foreground truncate font-normal">{user?.email || user?.username}</p>
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

                <main className="flex-1 overflow-y-auto p-4 lg:p-8">
                    <Outlet />
                </main>
            </div>

            {accountModalTab && (
                <AccountModal initialTab={accountModalTab} onClose={() => setAccountModalTab(null)} />
            )}
        </div>
    );
}
