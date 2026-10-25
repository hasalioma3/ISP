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
import { Card } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';

type SortField = 'account_balance' | 'created_at';
type TabKey = 'all' | 'active' | 'expired' | 'hotspot' | 'static' | 'pppoe' | 'new';

const TABS: { key: TabKey; label: string; icon: any; activeClass: string; idleClass: string }[] = [
    { key: 'all', label: 'All Users', icon: Users, activeClass: 'bg-primary text-primary-foreground', idleClass: 'bg-primary/10 text-primary hover:bg-primary/20' },
    { key: 'active', label: 'Active Users', icon: CheckCircle, activeClass: 'bg-green-600 text-white', idleClass: 'bg-green-50 text-green-700 hover:bg-green-100' },
    { key: 'expired', label: 'Expired Users', icon: XCircle, activeClass: 'bg-red-600 text-white', idleClass: 'bg-red-50 text-red-700 hover:bg-red-100' },
    { key: 'hotspot', label: 'Hotspot Users', icon: Wifi, activeClass: 'bg-amber-500 text-white', idleClass: 'bg-amber-50 text-amber-700 hover:bg-amber-100' },
    { key: 'static', label: 'Static Users', icon: Monitor, activeClass: 'bg-cyan-600 text-white', idleClass: 'bg-cyan-50 text-cyan-700 hover:bg-cyan-100' },
    { key: 'pppoe', label: 'PPPoE Users', icon: Repeat, activeClass: 'bg-violet-600 text-white', idleClass: 'bg-violet-50 text-violet-700 hover:bg-violet-100' },
    { key: 'new', label: 'New Users', icon: UserPlus, activeClass: 'bg-gray-800 text-white', idleClass: 'bg-gray-50 text-gray-700 hover:bg-gray-100' },
];

const PLAN_BADGE: Record<string, 'success' | 'destructive' | 'warning' | 'secondary'> = {
    active: 'success',
    expired: 'destructive',
    suspended: 'warning',
    cancelled: 'secondary',
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
        if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 text-muted-foreground/50" />;
        return sortDesc ? <ArrowDown className="h-3 w-3 ml-1" /> : <ArrowUp className="h-3 w-3 ml-1" />;
    };

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6 text-foreground">Subscribers</h1>

            <Card padding={false} className="overflow-hidden">
                {/* Banner */}
                <div className="bg-primary px-4 sm:px-6 py-4 flex flex-wrap gap-3 justify-between items-center">
                    <h2 className="text-primary-foreground font-bold text-lg">All Users</h2>
                    <Link
                        to="/admin/settings?tab=manual"
                        className="flex items-center gap-2 px-3 py-1.5 bg-white/95 text-primary rounded-lg text-sm font-medium hover:bg-white"
                    >
                        <UserPlus className="h-4 w-4" /> Add New Contact
                    </Link>
                </div>

                {/* Tabs */}
                <div className="flex flex-wrap gap-2 p-4 border-b border-border">
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
                <div className="flex flex-wrap items-center gap-3 p-4 border-b border-border">
                    <div className="relative flex-1 min-w-[220px]">
                        <input
                            type="text"
                            placeholder="Search by name, username, email, phone..."
                            className="pl-10 pr-4 py-2 border border-input rounded-lg w-full bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                            value={searchTerm}
                            onChange={(e) => { setSearchTerm(e.target.value); setPage(1); }}
                        />
                        <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                    </div>

                    <select
                        value={routerFilter}
                        onChange={(e) => { setRouterFilter(e.target.value); setPage(1); }}
                        className="border border-input rounded-lg px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                    >
                        <option value="">All Routers</option>
                        {routers?.map((r: any) => (
                            <option key={r.id} value={r.id}>{r.name}</option>
                        ))}
                    </select>

                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        Show
                        <select
                            value={pageSize}
                            onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                            className="border border-input rounded-lg px-2 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                        >
                            {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}
                        </select>
                        entries
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-border">
                        <thead className="bg-secondary">
                            <tr>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">#</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Username</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Full Name</th>
                                <th
                                    onClick={() => toggleSort('account_balance')}
                                    className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer select-none hover:text-foreground"
                                >
                                    <span className="flex items-center">Balance <SortIcon field="account_balance" /></span>
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Phone Number</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Email</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Package</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Service Type</th>
                                <th
                                    onClick={() => toggleSort('created_at')}
                                    className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer select-none hover:text-foreground"
                                >
                                    <span className="flex items-center">Created On <SortIcon field="created_at" /></span>
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">IP Address</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">MAC Address</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Router</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Manage</th>
                            </tr>
                        </thead>
                        <tbody className="bg-card divide-y divide-border">
                            {isLoading ? (
                                <tr>
                                    <td colSpan={12} className="px-6 py-8 text-center text-muted-foreground">
                                        <div className="flex justify-center items-center">
                                            <Loader2 className="h-6 w-6 animate-spin mr-2" />
                                            Loading subscribers...
                                        </div>
                                    </td>
                                </tr>
                            ) : isError ? (
                                <tr>
                                    <td colSpan={12} className="px-6 py-8 text-center text-red-600">
                                        Error loading subscribers: {(error as Error).message}
                                    </td>
                                </tr>
                            ) : subscribers.length === 0 ? (
                                <tr>
                                    <td colSpan={12} className="px-6 py-8 text-center text-muted-foreground">
                                        No subscribers found.
                                    </td>
                                </tr>
                            ) : (
                                subscribers.map((user: any, idx: number) => (
                                    <tr key={user.id} className="hover:bg-secondary/60 transition">
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-muted-foreground">{(page - 1) * pageSize + idx + 1}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm font-medium text-foreground">{user.username}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-foreground/80">{user.full_name || '-'}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-foreground">KES {Number(user.account_balance).toLocaleString()}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-muted-foreground">{user.phone_number || '-'}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-muted-foreground">{user.email || '-'}</td>
                                        <td className="px-4 py-4 whitespace-nowrap">
                                            {user.current_plan_name ? (
                                                <Badge variant={PLAN_BADGE[user.current_plan_status] || 'secondary'}>
                                                    {user.current_plan_name}
                                                </Badge>
                                            ) : (
                                                <span className="text-xs text-muted-foreground">No plan</span>
                                            )}
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap">
                                            <Badge variant="default" className="uppercase bg-primary/10 text-primary">
                                                {user.service_type}
                                            </Badge>
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-muted-foreground">
                                            {user.created_at ? format(new Date(user.created_at), 'MMM d, yyyy HH:mm') : '-'}
                                        </td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-muted-foreground">{user.last_ip || '-'}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-muted-foreground">{user.hotspot_mac_address || '-'}</td>
                                        <td className="px-4 py-4 whitespace-nowrap text-sm text-muted-foreground">{user.router_name || '-'}</td>
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
                <div className="flex items-center justify-between px-4 py-3 border-t border-border text-sm text-muted-foreground">
                    <span>
                        {totalCount === 0 ? '0 results' : `Page ${page} of ${totalPages} · ${totalCount} total`}
                    </span>
                    <div className="flex gap-2">
                        <Button
                            variant="secondary"
                            size="sm"
                            disabled={page <= 1}
                            onClick={() => setPage(p => Math.max(1, p - 1))}
                        >
                            <ChevronLeft className="h-4 w-4" /> Prev
                        </Button>
                        <Button
                            variant="secondary"
                            size="sm"
                            disabled={page >= totalPages}
                            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                        >
                            Next <ChevronRight className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            </Card>

            {selectedId !== null && (
                <SubscriberDetailModal id={selectedId} initialTab={initialTab} onClose={() => setSelectedId(null)} />
            )}
        </div>
    );
}
