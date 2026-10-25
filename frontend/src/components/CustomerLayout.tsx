import { useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Receipt, History, Activity, Wifi, LogOut, Home, ChevronRight, CircleUserRound, Menu } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useSiteSettings } from '../hooks/useSiteSettings';
import AccountModal from './AccountModal';
import { SidebarNavItem } from './ui/sidebar-nav-item';
import { ThemeToggle } from './ui/theme-toggle';

const NAVIGATION = [
    { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    { name: 'Buy Package', href: '/plans', icon: Wifi },
    { name: 'Order History', href: '/orders', icon: Receipt },
    { name: 'Activation History', href: '/activations', icon: History },
    { name: 'Data Usage', href: '/usage', icon: Activity },
];

export default function CustomerLayout() {
    const location = useLocation();
    const navigate = useNavigate();
    const { user, logout } = useAuthStore();
    const { data: siteSettings } = useSiteSettings();
    const [accountModalTab, setAccountModalTab] = useState<'profile' | 'password' | null>(null);
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const currentPage = NAVIGATION.find(item => location.pathname.startsWith(item.href))?.name || 'Dashboard';

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
        fixed lg:static inset-y-0 left-0 z-50 w-64 bg-card border-r border-border flex flex-col shrink-0 transform transition-transform duration-200 ease-in-out
        ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
                <div className="px-5 py-5 border-b border-border flex items-center justify-between">
                    <Link to="/dashboard" onClick={() => setIsSidebarOpen(false)} className="flex items-center gap-2.5 min-w-0">
                        {siteSettings?.logo ? (
                            <img src={siteSettings.logo} alt={siteSettings.company_name} className="h-8 w-8 rounded-lg object-contain bg-accent shrink-0" />
                        ) : (
                            <div className="h-8 w-8 rounded-lg bg-primary text-primary-foreground flex items-center justify-center font-bold text-sm shrink-0">
                                {(siteSettings?.company_name || 'I')[0].toUpperCase()}
                            </div>
                        )}
                        <span className="text-lg font-bold text-foreground truncate">{siteSettings?.company_name || 'ISP Portal'}</span>
                    </Link>
                    <button
                        onClick={() => setAccountModalTab('profile')}
                        title="My Account"
                        className="p-1.5 text-muted-foreground hover:text-primary hover:bg-accent rounded-full shrink-0"
                    >
                        <CircleUserRound className="h-5 w-5" />
                    </button>
                </div>

                <p className="px-5 pt-4 pb-2 text-xs font-semibold text-muted-foreground tracking-wide">MENU</p>
                <nav className="flex-1 px-3 space-y-1">
                    {NAVIGATION.map((item) => (
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

                <div className="p-4">
                    <div className="bg-primary rounded-2xl p-4 text-primary-foreground">
                        <p className="font-bold text-sm mb-1">Need more speed?</p>
                        <p className="text-primary-foreground/80 text-xs mb-3">Browse our other packages</p>
                        <Link to="/plans" onClick={() => setIsSidebarOpen(false)} className="text-xs font-semibold hover:underline">
                            View Plans &rarr;
                        </Link>
                    </div>
                    <button
                        onClick={handleLogout}
                        className="mt-3 w-full flex items-center justify-center gap-2 text-sm font-medium text-red-600 hover:bg-red-50 rounded-full py-2.5 transition-colors"
                    >
                        <LogOut className="h-4 w-4" /> Sign Out
                    </button>
                </div>
            </div>

            {/* Main */}
            <div className="flex-1 min-w-0 flex flex-col">
                <div className="px-4 sm:px-8 py-3 border-b border-border bg-card flex items-center gap-1.5 text-sm text-muted-foreground">
                    <button
                        onClick={() => setIsSidebarOpen(true)}
                        className="p-1 -ml-1 mr-1 text-muted-foreground hover:text-foreground lg:hidden shrink-0"
                    >
                        <Menu className="h-5 w-5" />
                    </button>
                    <Home className="h-3.5 w-3.5 shrink-0 hidden sm:block" />
                    <span className="hidden sm:inline">Home</span>
                    <ChevronRight className="h-3 w-3 shrink-0 hidden sm:block" />
                    <span className="truncate hidden sm:inline">{user?.full_name || user?.username}</span>
                    <ChevronRight className="h-3 w-3 shrink-0 hidden sm:block" />
                    <span className="text-foreground font-medium truncate">{currentPage}</span>
                    <div className="ml-auto">
                        <ThemeToggle />
                    </div>
                </div>

                <main className="flex-1 p-4 sm:p-8 bg-background">
                    <Outlet />
                </main>
            </div>

            {accountModalTab && (
                <AccountModal initialTab={accountModalTab} onClose={() => setAccountModalTab(null)} />
            )}
        </div>
    );
}
