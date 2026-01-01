import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { useTheme } from '../context/ThemeContext';
import {
    LayoutDashboard,
    Users,
    BarChart,
    Settings,
    Ticket,
    LogOut,
    Menu,
    Moon,
    Sun,
    X
} from 'lucide-react';
import { useState } from 'react';

export default function AdminLayout() {
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const location = useLocation();
    const navigate = useNavigate();
    const logout = useAuthStore((state) => state.logout);
    const user = useAuthStore((state) => state.user);
    const { theme, toggleTheme } = useTheme();

    const navigation = [
        { name: 'Dashboard', href: '/admin/dashboard', icon: LayoutDashboard },
        { name: 'Subscribers', href: '/admin/subscribers', icon: Users },
        { name: 'Reports', href: '/admin/reports', icon: BarChart },
        { name: 'Vouchers', href: '/admin/vouchers', icon: Ticket },
        { name: 'Settings', href: '/admin/settings', icon: Settings },
    ];

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    return (
        <div className="min-h-screen bg-gray-100 dark:bg-gray-900 flex transition-colors duration-200">
            {/* Mobile Sidebar Overlay */}
            {isSidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/50 z-40 lg:hidden"
                    onClick={() => setIsSidebarOpen(false)}
                />
            )}

            {/* Sidebar */}
            <div className={`
        fixed lg:static inset-y-0 left-0 z-50 w-64 bg-white dark:bg-gray-800 shadow-xl transform transition-transform duration-200 ease-in-out
        ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
                <div className="h-full flex flex-col">
                    <div className="p-6 border-b dark:border-gray-700 flex flex-col items-center">
                        <Link to="/admin/dashboard" className="flex flex-col items-center group">
                            <img src="/hasanet_logo.png" alt="Hasanet" className="h-16 mb-2 group-hover:opacity-90 transition-opacity" />
                            <h1 className="text-xl font-bold text-gray-900 dark:text-white group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">Hasanet</h1>
                        </Link>
                        <p className="text-xs text-primary-600 dark:text-primary-400 font-medium tracking-wider">TECHNOLOGIES</p>
                        <div className="mt-2 text-xs text-gray-500 dark:text-gray-400 text-center">
                            Welcome, {user?.first_name}
                        </div>
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
                                            ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-400'
                                            : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                                        }
                  `}
                                >
                                    <item.icon className="h-5 w-5 mr-3" />
                                    {item.name}
                                </Link>
                            );
                        })}
                    </nav>

                    <div className="p-4 border-t dark:border-gray-700 space-y-2">
                        <button
                            onClick={toggleTheme}
                            className="flex items-center w-full px-4 py-3 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                        >
                            {theme === 'light' ? (
                                <>
                                    <Moon className="h-5 w-5 mr-3" />
                                    Dark Mode
                                </>
                            ) : (
                                <>
                                    <Sun className="h-5 w-5 mr-3" />
                                    Light Mode
                                </>
                            )}
                        </button>
                        <button
                            onClick={handleLogout}
                            className="flex items-center w-full px-4 py-3 text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                        >
                            <LogOut className="h-5 w-5 mr-3" />
                            Sign Out
                        </button>
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                {/* Mobile Header */}
                <div className="lg:hidden bg-white dark:bg-gray-800 shadow-sm p-4 flex items-center justify-between transition-colors duration-200">
                    <Link to="/admin/dashboard" className="flex items-center gap-2">
                        <img src="/hasanet_logo.png" alt="Logo" className="h-8" />
                        <span className="text-xl font-bold text-gray-800 dark:text-white">Hasanet</span>
                    </Link>
                    <button
                        onClick={() => setIsSidebarOpen(true)}
                        className="p-2 -mr-2 text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
                    >
                        <Menu className="h-6 w-6" />
                    </button>
                </div>

                <main className="flex-1 overflow-y-auto p-4 lg:p-8">
                    <Outlet />
                </main>
            </div>
        </div>
    );
}
