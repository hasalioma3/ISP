import { useState } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Receipt, History, Activity, Wifi, LogOut, Home, ChevronRight, CircleUserRound, Menu } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useSiteSettings } from '../hooks/useSiteSettings';
import AccountModal from './AccountModal';

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
        <div className="min-h-screen bg-gray-50 flex">
            {/* Mobile Sidebar Overlay */}
            {isSidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/50 z-40 lg:hidden"
                    onClick={() => setIsSidebarOpen(false)}
                />
            )}

            {/* Sidebar */}
            <div className={`
        fixed lg:static inset-y-0 left-0 z-50 w-64 bg-white border-r border-gray-200 flex flex-col shrink-0 transform transition-transform duration-200 ease-in-out
        ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
                <div className="p-6 border-b border-gray-100 flex items-center justify-between">
                    <Link to="/dashboard" onClick={() => setIsSidebarOpen(false)} className="flex items-center gap-2 min-w-0">
                        {siteSettings?.logo ? (
                            <img src={siteSettings.logo} alt={siteSettings.company_name} className="h-8 w-8 rounded-full object-contain bg-blue-50 shrink-0" />
                        ) : null}
                        <span className="text-lg font-bold text-gray-900 truncate">{siteSettings?.company_name || 'ISP Portal'}</span>
                    </Link>
                    <button
                        onClick={() => setAccountModalTab('profile')}
                        title="My Account"
                        className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-full shrink-0"
                    >
                        <CircleUserRound className="h-5 w-5" />
                    </button>
                </div>

                <p className="px-6 pt-4 pb-2 text-xs font-semibold text-gray-400 tracking-wide">MENU</p>
                <nav className="flex-1 px-3 space-y-1">
                    {NAVIGATION.map((item) => {
                        const isActive = location.pathname.startsWith(item.href);
                        return (
                            <Link
                                key={item.name}
                                to={item.href}
                                onClick={() => setIsSidebarOpen(false)}
                                className={`flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-colors ${isActive ? 'bg-blue-50 text-blue-600' : 'text-gray-600 hover:bg-gray-50'
                                    }`}
                            >
                                <item.icon className="h-4 w-4 mr-3" />
                                {item.name}
                            </Link>
                        );
                    })}
                </nav>

                <div className="p-4">
                    <div className="bg-gray-900 rounded-xl p-4 text-white">
                        <p className="font-bold text-sm mb-1">Need more speed?</p>
                        <p className="text-gray-400 text-xs mb-3">Browse our other packages</p>
                        <Link to="/plans" onClick={() => setIsSidebarOpen(false)} className="text-blue-400 text-xs font-semibold hover:text-blue-300">
                            View Plans &rarr;
                        </Link>
                    </div>
                    <button
                        onClick={handleLogout}
                        className="mt-3 w-full flex items-center justify-center gap-2 text-sm font-medium text-red-600 hover:bg-red-50 rounded-lg py-2.5 transition-colors"
                    >
                        <LogOut className="h-4 w-4" /> Sign Out
                    </button>
                </div>
            </div>

            {/* Main */}
            <div className="flex-1 min-w-0 flex flex-col">
                <div className="px-4 sm:px-8 py-3 border-b border-gray-200 bg-white flex items-center gap-1.5 text-sm text-gray-500">
                    <button
                        onClick={() => setIsSidebarOpen(true)}
                        className="p-1 -ml-1 mr-1 text-gray-500 hover:text-gray-900 lg:hidden shrink-0"
                    >
                        <Menu className="h-5 w-5" />
                    </button>
                    <Home className="h-3.5 w-3.5 shrink-0 hidden sm:block" />
                    <span className="hidden sm:inline">Home</span>
                    <ChevronRight className="h-3 w-3 shrink-0 hidden sm:block" />
                    <span className="truncate hidden sm:inline">{user?.full_name || user?.username}</span>
                    <ChevronRight className="h-3 w-3 shrink-0 hidden sm:block" />
                    <span className="text-gray-900 font-medium truncate">{currentPage}</span>
                </div>

                <main className="flex-1 p-4 sm:p-8">
                    <Outlet />
                </main>
            </div>

            {accountModalTab && (
                <AccountModal initialTab={accountModalTab} onClose={() => setAccountModalTab(null)} />
            )}
        </div>
    );
}
