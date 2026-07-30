import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { adminAPI } from '../../services/api';
import {
    Search, Loader2, ArrowUp, ArrowDown, ArrowUpDown, Users, CheckCircle, XCircle,
    Wifi, Monitor, Repeat, UserPlus, Eye, RefreshCw, Pencil, ChevronLeft, ChevronRight,
} from 'lucide-react';
import { format } from 'date-fns';
import SubscriberDetailModal from '../../components/SubscriberDetailModal';

type SortField = 'account_balance' | 'created_at';
type TabKey = 'all' | 'active' | 'expired' | 'hotspot' | 'static' | 'pppoe' | 'new';

const TABS: { key: TabKey; label: string; icon: any; activeClass: string; idleClass: string }[] = [
    { key: 'all', label: 'All Users', icon: Users, activeClass: 'bg-blue-600 text-white', idleClass: 'bg-blue-50 text-blue-700 hover:bg-blue-100' },
    { key: 'active', label: 'Active Users', icon: CheckCircle, activeClass: 'bg-green-600 text-white', idleClass: 'bg-green-50 text-green-700 hover:bg-green-100' },
    { key: 'expired', label: 'Expired Users', icon: XCircle, activeClass: 'bg-red-600 text-white', idleClass: 'bg-red-50 text-red-700 hover:bg-red-100' },
    { key: 'hotspot', label: 'Hotspot Users', icon: Wifi, activeClass: 'bg-amber-500 text-white', idleClass: 'bg-amber-50 text-amber-700 hover:bg-amber-100' },
    { key: 'static', label: 'Static Users', icon: Monitor, activeClass: 'bg-cyan-600 text-white', idleClass: 'bg-cyan-50 text-cyan-700 hover:bg-cyan-100' },
    { key: 'pppoe', label: 'PPPoE Users', icon: Repeat, activeClass: 'bg-purple-600 text-white', idleClass: 'bg-purple-50 text-purple-700 hover:bg-purple-100' },
    { key: 'new', label: 'New Users', icon: UserPlus, activeClass: 'bg-gray-800 text-white', idleClass: 'bg-gray-50 text-gray-700 hover:bg-gray-100' },
];

const PLAN_BADGE: Record<string, string> = {
    active: 'bg-green-100 text-green-800',
    expired: 'bg-red-100 text-red-800',
    suspended: 'bg-amber-100 text-amber-800',
    cancelled: 'bg-gray-100 text-gray-600',
};

export default function Subscribers() {
    const [urlParams] = useSearchParams();
    const [searchTerm, setSearchTerm] = useState(urlParams.get('search') || '');
    const [activeTab, setActiveTab] = useState<TabKey>('all');
    const [routerFilter, setRouterFilter] = useState('');
    const [pageSize, setPageSize] = useState(10);
    const [page, setPage] = useState(1);
    const [sortField, setSortField] = useState<SortField | ''>('');
    const [sortDesc, setSortDesc] = useState(true);
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const [initialTab, setInitialTab] = useState<'details' | 'usage' | 'plans'>('details');

    const serviceFilter = ['hotspot', 'static', 'pppoe'].includes(activeTab) ? activeTab : '';
    const statusFilter = activeTab === 'active' || activeTab === 'expired' ? activeTab : '';
    const isNew = activeTab === 'new';

    const selectTab = (key: TabKey) => {
        setActiveTab(key);
        setPage(1);
    };

    const { data: routers } = useQuery({
        queryKey: ['routers-for-filter'],
        queryFn: async () => {
            const res = await adminAPI.getRouters();
            return res.data.results || res.data;
        }
    });

    const { data, isLoading, isError, error } = useQuery({
        queryKey: ['admin-subscribers', searchTerm, serviceFilter, statusFilter, isNew, routerFilter, sortField, sortDesc, page, pageSize],
        queryFn: async () => {
            const res = await adminAPI.getSubscribers({
                search: searchTerm || undefined,
                service_type: serviceFilter || undefined,
                status: statusFilter || undefined,
                is_new: isNew ? 'true' : undefined,
                router: routerFilter || undefined,
                ordering: sortField ? `${sortDesc ? '-' : ''}${sortField}` : undefined,
                page,
                page_size: pageSize,
            });
            return res.data;
        }
    });

    const subscribers = data?.results || [];
    const totalCount = data?.count ?? subscribers.length;
    const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

    const toggleSort = (field: SortField) => {
        if (sortField === field) {
            setSortDesc(!sortDesc);
        } else {
            setSortField(field);
            setSortDesc(true);
        }
    };

    const openModal = (id: number, tab: 'details' | 'usage' | 'plans') => {
        setInitialTab(tab);
        setSelectedId(id);
    };

    const SortIcon = ({ field }: { field: SortField }) => {
        if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 text-gray-300" />;
        return sortDesc ? <ArrowDown className="h-3 w-3 ml-1" /> : <ArrowUp className="h-3 w-3 ml-1" />;
    };

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6">Subscribers</h1>

            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                {/* Banner */}
                <div className="bg-blue-600 px-6 py-4 flex justify-between items-center">
                    <h2 className="text-white font-bold text-lg">All Users</h2>
                    <Link
                        to="/admin/settings?tab=manual"
                        className="flex items-center gap-2 px-3 py-1.5 bg-white text-blue-700 rounded-lg text-sm font-medium hover:bg-blue-50"
                    >
                        <UserPlus className="h-4 w-4" /> Add New Contact
                    </Link>
                </div>

                {/* Tabs */}
                <div className="flex flex-wrap gap-2 p-4 border-b border-gray-100">
                    {TABS.map(t => {
                        const Icon = t.icon;
                        const isActive = activeTab === t.key;
                        return (
                            <button
                                key={t.key}
                                onClick={() => selectTab(t.key)}
                                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${isActive ? t.activeClass : t.idleClass}`}
                            >
                                <Icon className="h-4 w-4" />
                                {t.label}
                            </button>
                        );
                    })}
                </div>

                {/* Controls */}
                <div className="flex flex-wrap items-center gap-3 p-4 border-b border-gray-100">
                    <div className="relative flex-1 min-w-[220px]">
                        <input
                            type="text"
                            placeholder="Search by name, username, email, phone..."
                            className="pl-10 pr-4 py-2 border rounded-lg w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
                            value={searchTerm}
                            onChange={(e) => { setSearchTerm(e.target.value); setPage(1); }}
                        />
                        <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                    </div>

                    <select
                        value={routerFilter}
                        onChange={(e) => { setRouterFilter(e.target.value); setPage(1); }}
                        className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                        <option value="">All Routers</option>
                        {routers?.map((r: any) => (
                            <option key={r.id} value={r.id}>{r.name}</option>
                        ))}
                    </select>

                    <div className="flex items-center gap-2 text-sm text-gray-600">
                        Show
                        <select
                            value={pageSize}
                            onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                            className="border rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                            {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}
                        </select>
                        entries
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">#</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Username</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Full Name</th>
                                <th
                                    onClick={() => toggleSort('account_balance')}
                                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:text-gray-700"
                                >
                                    <span className="flex items-center">Balance <SortIcon field="account_balance" /></span>
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Phone Number</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Email</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Package</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Service Type</th>
                                <th
                                    onClick={() => toggleSort('created_at')}
                                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:text-gray-700"
                                >
                                    <span className="flex items-center">Created On <SortIcon field="created_at" /></span>
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">IP Address</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">MAC Address</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Router</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Manage</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {isLoading ? (
                                <tr>
                                    <td colSpan={12} className="px-6 py-8 text-center text-gray-500">
                                        <div className="flex justify-center items-center">
                                            <Loader2 className="h-6 w-6 animate-spin mr-2" />
                                            Loading subscribers...
                                        </div>
                                    </td>
                                </tr>
                            ) : isError ? (
                                <tr>
                                    <td colSpan={12} className="px-6 py-8 text-center text-red-500">
                                        Error loading subscribers: {(error as Error).message}
                                    </td>
                                </tr>
                            ) : subscribers.length === 0 ? (
                                <tr>
                                    <td colSpan={12} className="px-6 py-8 text-center text-gray-500">
                                        No subscribers found.
                                    </td>
                                </tr>
                            ) : (
                                subscribers.map((user: any, idx: number) => (
                                    <tr key={user.id} className="hover:bg-gray-50 transition">
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">{(page - 1) * pageSize + idx + 1}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{user.username}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-700">{user.full_name || '-'}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-900">KES {Number(user.account_balance).toLocaleString()}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">{user.phone_number || '-'}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">{user.email || '-'}</td>
                                        <td className="px-4 py-4 whitespace-nowrap">
                                            {user.current_plan_name ? (
                                                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize ${PLAN_BADGE[user.current_plan_status] || 'bg-gray-100 text-gray-600'}`}>
                                                    {user.current_plan_name}
                                                </span>
                                            ) : (
                                                <span className="text-xs text-gray-400">No plan</span>
                                            )}
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap">
                                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 uppercase">
                                                {user.service_type}
                                            </span>
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">
                                            {user.created_at ? format(new Date(user.created_at), 'MMM d, yyyy HH:mm') : '-'}
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">{user.last_ip || '-'}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">{user.hotspot_mac_address || '-'}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">{user.router_name || '-'}</td>
                                        <td className="px-4 py-4 whitespace-nowrap">
                                            <div className="flex gap-1">
                                                <button
                                                    onClick={() => openModal(user.id, 'usage')}
                                                    className="flex items-center px-2 py-1 bg-cyan-500 text-white rounded text-xs hover:bg-cyan-600"
                                                    title="View usage & history"
                                                >
                                                    <Eye className="h-3 w-3 mr-1" /> View
                                                </button>
                                                <button
                                                    onClick={() => openModal(user.id, 'plans')}
                                                    className="flex items-center px-2 py-1 bg-green-600 text-white rounded text-xs hover:bg-green-700"
                                                    title="Assign / top up a plan"
                                                >
                                                    <RefreshCw className="h-3 w-3 mr-1" /> Recharge
                                                </button>
                                                <button
                                                    onClick={() => openModal(user.id, 'details')}
                                                    className="flex items-center px-2 py-1 bg-amber-500 text-white rounded text-xs hover:bg-amber-600"
                                                    title="Edit profile"
                                                >
                                                    <Pencil className="h-3 w-3 mr-1" /> Edit
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {/* Pagination */}
                <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 text-sm text-gray-600">
                    <span>
                        {totalCount === 0 ? '0 results' : `Page ${page} of ${totalPages} · ${totalCount} total`}
                    </span>
                    <div className="flex gap-2">
                        <button
                            disabled={page <= 1}
                            onClick={() => setPage(p => Math.max(1, p - 1))}
                            className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
                        >
                            <ChevronLeft className="h-4 w-4" /> Prev
                        </button>
                        <button
                            disabled={page >= totalPages}
                            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                            className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
                        >
                            Next <ChevronRight className="h-4 w-4" />
                        </button>
                    </div>
                </div>
            </div>

            {selectedId !== null && (
                <SubscriberDetailModal id={selectedId} initialTab={initialTab} onClose={() => setSelectedId(null)} />
            )}
        </div>
    );
}
