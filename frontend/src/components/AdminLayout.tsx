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
    X,
    Search,
    Zap,
    ChevronDown,
    UsersRound,
    Radio,
    Package,
    Database,
} from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { useSiteSettings } from '../hooks/useSiteSettings';

export default function AdminLayout() {
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [isQuickActionsOpen, setIsQuickActionsOpen] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const quickActionsRef = useRef<HTMLDivElement>(null);
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
        { name: 'Reports', href: '/admin/reports', icon: BarChart, roles: ['admin', 'sales'] },
        { name: 'Vouchers', href: '/admin/vouchers', icon: Ticket, roles: ['admin', 'sales'] },
        { name: 'MikroTik', href: '/admin/mikrotik', icon: RouterIcon, roles: ['admin', 'technician'] },
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

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (quickActionsRef.current && !quickActionsRef.current.contains(e.target as Node)) {
                setIsQuickActionsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

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

    return (
        <div className="min-h-screen bg-gray-100 flex">
            {/* Mobile Sidebar Overlay */}
            {isSidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/50 z-40 lg:hidden"
                    onClick={() => setIsSidebarOpen(false)}
                />
            )}

            {/* Sidebar */}
            <div className={`
        fixed lg:static inset-y-0 left-0 z-50 w-64 bg-gray-900 shadow-xl transform transition-transform duration-200 ease-in-out
        ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
                <div className="h-full flex flex-col">
                    <div className="p-6 border-b border-gray-800">
                        <Link
                            to="/admin/dashboard"
                            onClick={() => setIsSidebarOpen(false)}
                            className="flex items-center gap-2 hover:opacity-80 transition-opacity"
                        >
                            {siteSettings?.logo ? (
                                <img src={siteSettings.logo} alt={siteSettings.company_name} className="h-9 w-9 rounded object-contain bg-white/5" />
                            ) : null}
                            <h1 className="text-2xl font-bold text-blue-400 truncate">{siteSettings?.company_name || 'ISP Admin'}</h1>
                        </Link>
                        <p className="text-sm text-gray-400">Welcome, {user?.first_name}</p>
                    </div>

                    <nav className="flex-1 p-4 space-y-1">
                        {navigation.map((item) => {
                            const isActive = location.pathname.startsWith(item.href);
                            return (
                                <Link
                                    key={item.name}
                                    to={item.href}
                                    onClick={() => setIsSidebarOpen(false)}
                                    className={`
                    flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors
                    ${isActive
                                            ? 'bg-blue-600/20 text-blue-400'
                                            : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                                        }
                  `}
                                >
                                    <item.icon className="h-5 w-5 mr-3" />
                                    {item.name}
                                </Link>
                            );
                        })}
                    </nav>

                    <div className="p-4 border-t border-gray-800">
                        <button
                            onClick={handleLogout}
                            className="flex items-center w-full px-4 py-3 text-sm font-medium text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                        >
                            <LogOut className="h-5 w-5 mr-3" />
                            Sign Out
                        </button>
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                {/* Top Bar */}
                <div className="bg-gray-900 text-white shadow-sm flex items-center justify-between px-4 lg:px-6 py-3 gap-4">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                        <button
                            onClick={() => setIsSidebarOpen(true)}
                            className="p-2 -ml-2 text-gray-300 hover:text-white lg:hidden"
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
                                    className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-9 pr-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                                <Search className="absolute left-2.5 top-2 h-4 w-4 text-gray-500" />
                            </div>
                        </form>
                    </div>

                    <div className="flex items-center gap-3">
                        <div className="relative" ref={quickActionsRef}>
                            <button
                                onClick={() => setIsQuickActionsOpen(!isQuickActionsOpen)}
                                className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm font-medium"
                            >
                                <Zap className="h-4 w-4 text-yellow-400" />
                                <span className="hidden sm:inline">Quick Actions</span>
                                <ChevronDown className="h-3.5 w-3.5" />
                            </button>
                            {isQuickActionsOpen && (
                                <div className="absolute right-0 mt-2 w-56 bg-white rounded-lg shadow-xl border border-gray-100 py-1 z-50">
                                    {quickActions.map((action) => (
                                        <button
                                            key={action.name}
                                            onClick={() => { navigate(action.href); setIsQuickActionsOpen(false); }}
                                            className="w-full flex items-center px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 text-left"
                                        >
                                            <action.icon className="h-4 w-4 mr-2.5 text-gray-400" />
                                            {action.name}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div className="hidden sm:flex items-center gap-2 pl-3 border-l border-gray-700">
                            <div className="h-8 w-8 rounded-full bg-blue-600 flex items-center justify-center text-sm font-bold">
                                {(user?.first_name || 'A')[0].toUpperCase()}
                            </div>
                            <span className="text-sm text-gray-300">{user?.first_name || 'Administrator'}</span>
                        </div>
                    </div>
                </div>

                <main className="flex-1 overflow-y-auto p-4 lg:p-8">
                    <Outlet />
                </main>
            </div>
        </div>
    );
}
