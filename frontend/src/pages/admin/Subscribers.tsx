import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import {
    ArrowDown, ArrowLeft, ArrowRight, ArrowUp, ArrowUpDown, Eye, Filter, Loader2, MapPin,
    MoreHorizontal, Package, Pencil, Plus, RefreshCw, Search, Upload, X, Zap, Layers,
} from 'lucide-react';
import { adminAPI, billingAPI } from '../../services/api';
import { useAuthStore } from '../../store/authStore';
import { useSites } from '../../hooks/useSites';
import SubscriberDetailModal from '../../components/SubscriberDetailModal';
import {
    DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '../../components/ui/dropdown-menu';
import {
    EmptyState, Panel, ShellHeader, Skeleton, StatusBadge, bandButtonClass, bandCtaClass,
    formatCount, formatDateEAT, formatKES, initials, type Status,
} from '../../components/savanna';
import { cn } from '@/lib/utils';

type TabKey = 'all' | 'active' | 'expiring' | 'expired' | 'suspended' | 'new';
type SortField = 'calculated_expiry' | 'account_balance' | 'created_at';

const TABS: { key: TabKey; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'active', label: 'Active' },
    { key: 'expiring', label: 'Expiring' },
    { key: 'expired', label: 'Expired' },
    { key: 'suspended', label: 'Suspended' },
    { key: 'new', label: 'New' },
];

// Avatar tints, picked per subscriber so the list is scannable.
const AVATAR_TONES = [
    'bg-[#FFF1E6] text-[#C2410C]', 'bg-[#E0F2FE] text-[#0369A1]', 'bg-[#EDE9FE] text-[#6D28D9]',
    'bg-[#E7F6EC] text-[#15803D]', 'bg-[#FCE7F3] text-[#BE185D]', 'bg-[#FEF9C3] text-[#A16207]',
];

const maskPhone = (phone?: string) => {
    const digits = (phone || '').replace(/\D/g, '');
    const local = digits.length === 12 && digits.startsWith('254') ? `0${digits.slice(3)}` : digits;
    return local.length === 10 ? `${local.slice(0, 4)} ••• ${local.slice(-3)}` : (phone || '');
};

/** Customer status, with "active but running out within 7 days" shown as expiring. */
function rowStatus(user: any): Status {
    if (user.status === 'active' && user.calculated_expiry) {
        const msLeft = new Date(user.calculated_expiry).getTime() - Date.now();
        if (msLeft > 0 && msLeft <= 7 * 86_400_000) return 'expiring';
    }
    if (['active', 'expired', 'suspended', 'pending'].includes(user.status)) return user.status;
    return 'unknown';
}

const selectClass =
    'h-10 rounded-full border border-input bg-card pl-9 pr-8 text-[13.5px] font-semibold text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring appearance-none';

export default function Subscribers() {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const user = useAuthStore((s) => s.user);
    const isAdmin = !!user?.is_superuser || user?.role === 'admin';
    // Renewing records cash, which technicians can't do (API enforces it too).
    const canRenew = !!user?.is_superuser || user?.role !== 'technician';
    const [urlParams] = useSearchParams();
    const [searchTerm, setSearchTerm] = useState(urlParams.get('search') || '');
    const [search, setSearch] = useState(searchTerm);
    const [activeTab, setActiveTab] = useState<TabKey>('all');
    const [routerFilter, setRouterFilter] = useState('');
    const [planFilter, setPlanFilter] = useState('');
    const [typeFilter, setTypeFilter] = useState('');
    const [pageSize, setPageSize] = useState(10);
    const [page, setPage] = useState(1);
    const [sortField, setSortField] = useState<SortField | ''>('');
    const [sortDesc, setSortDesc] = useState(true);
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const [initialTab, setInitialTab] = useState<'details' | 'usage' | 'plans'>('details');
    const [selected, setSelected] = useState<Record<number, any>>({});
    const [bulkBusy, setBulkBusy] = useState<'stk' | 'renew' | null>(null);

    // Debounce typing so every keystroke isn't a query.
    useEffect(() => {
        const t = setTimeout(() => { setSearch(searchTerm.trim()); setPage(1); }, 300);
        return () => clearTimeout(t);
    }, [searchTerm]);

    const { sites, isLoading: sitesLoading } = useSites();

    const { data: plans } = useQuery({
        queryKey: ['billing-plans-filter'],
        queryFn: async () => {
            const res = await billingAPI.getPlans();
            return (res.data.results || res.data) as any[];
        },
    });

    const filters = {
        search: search || undefined,
        router: routerFilter || undefined,
        plan: planFilter || undefined,
        service_type: typeFilter || undefined,
    };

    const { data: summary } = useQuery({
        queryKey: ['admin-subscriber-summary', filters],
        queryFn: async () => (await adminAPI.getSubscriberSummary(filters)).data as Record<TabKey, number>,
    });

    const { data, isLoading, isError, error } = useQuery({
        queryKey: ['admin-subscribers', filters, activeTab, sortField, sortDesc, page, pageSize],
        queryFn: async () => (await adminAPI.getSubscribers({
            ...filters,
            status: ['active', 'expired', 'suspended'].includes(activeTab) ? activeTab : undefined,
            expiring: activeTab === 'expiring' ? 'true' : undefined,
            is_new: activeTab === 'new' ? 'true' : undefined,
            ordering: sortField ? `${sortDesc ? '-' : ''}${sortField}` : undefined,
            page,
            page_size: pageSize,
        })).data,
    });

    const subscribers: any[] = data?.results || [];
    const totalCount = data?.count ?? subscribers.length;
    const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
    const firstRow = totalCount === 0 ? 0 : (page - 1) * pageSize + 1;
    const lastRow = Math.min(page * pageSize, totalCount);

    // Selection is per page: changing page/filters clears it.
    useEffect(() => { setSelected({}); }, [page, pageSize, activeTab, search, routerFilter, planFilter, typeFilter]);

    const selectedRows = Object.values(selected);
    const allOnPageSelected = subscribers.length > 0 && subscribers.every((s) => selected[s.id]);

    const toggleRow = (row: any) =>
        setSelected((prev) => {
            const next = { ...prev };
            if (next[row.id]) delete next[row.id];
            else next[row.id] = row;
            return next;
        });
    const toggleAll = () =>
        setSelected(allOnPageSelected ? {} : Object.fromEntries(subscribers.map((s) => [s.id, s])));

    const selectTab = (key: TabKey) => { setActiveTab(key); setPage(1); };

    const toggleSort = (field: SortField) => {
        if (sortField === field) setSortDesc(!sortDesc);
        else { setSortField(field); setSortDesc(true); }
    };

    const openModal = (id: number, tab: 'details' | 'usage' | 'plans') => {
        setInitialTab(tab);
        setSelectedId(id);
    };

    const refreshLists = () => {
        queryClient.invalidateQueries({ queryKey: ['admin-subscribers'] });
        queryClient.invalidateQueries({ queryKey: ['admin-subscriber-summary'] });
    };

    const sendStkReminders = async () => {
        const ids = selectedRows.map((r) => r.id);
        if (!window.confirm(
            `Send an M-Pesa payment prompt to ${ids.length} subscriber${ids.length === 1 ? '' : 's'} for their current plan? `
            + 'Each one gets a real STK prompt on their phone; paying it renews them automatically.',
        )) return;
        setBulkBusy('stk');
        try {
            const res = await adminAPI.bulkStkReminder(ids);
            const { success = [], failed = [] } = res.data;
            if (success.length) toast.success(`${success.length} prompt${success.length === 1 ? '' : 's'} sent`);
            failed.forEach((msg: string) => toast.error(msg, { duration: 6000 }));
            setSelected({});
        } catch (err: any) {
            toast.error(err.response?.data?.error || 'Could not send payment prompts');
        } finally {
            setBulkBusy(null);
        }
    };

    const renewSelected = async () => {
        const rows = selectedRows.filter((r) => r.current_plan_id);
        const skipped = selectedRows.length - rows.length;
        if (!rows.length) { toast.error('None of the selected subscribers has a plan to renew.'); return; }
        const total = rows.reduce((sum, r) => sum + Number(r.current_plan_price || 0), 0);
        if (!window.confirm(
            `Renew ${rows.length} subscriber${rows.length === 1 ? '' : 's'} on their current plan? `
            + `This records a manual cash payment for each (${formatKES(total)} in total), the same as Recharge.`
            + (skipped ? ` ${skipped} without a plan will be skipped.` : ''),
        )) return;
        setBulkBusy('renew');
        let ok = 0;
        for (const row of rows) {
            try {
                await adminAPI.topUpSubscriber(row.id, row.current_plan_id);
                ok += 1;
            } catch (err: any) {
                toast.error(`${row.full_name || row.username}: ${err.response?.data?.error || 'renewal failed'}`, { duration: 6000 });
            }
        }
        if (ok) toast.success(`${ok} subscriber${ok === 1 ? '' : 's'} renewed`);
        setBulkBusy(null);
        setSelected({});
        refreshLists();
    };

    const subtitle = summary
        ? `${formatCount(summary.active)} active · ${formatCount(summary.expiring)} expiring this week · ${formatCount(summary.suspended)} suspended`
        : 'Loading…';

    const SortIcon = ({ field }: { field: SortField }) => {
        if (sortField !== field) return <ArrowUpDown className="h-3 w-3 opacity-50" />;
        return sortDesc ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />;
    };

    const routerOptions = useMemo(() => sites.map((s) => ({ id: String(s.id), name: s.name })), [sites]);

    return (
        <div className="space-y-[18px]">
            <ShellHeader
                title="Subscribers"
                subtitle={subtitle}
                actions={
                    <>
                        <button onClick={() => navigate('/admin/settings?tab=bulk-import')} className={bandButtonClass}>
                            <Upload className="h-[18px] w-[18px]" strokeWidth={1.8} /> Import CSV
                        </button>
                        <button onClick={() => navigate('/admin/settings?tab=manual')} className={bandCtaClass}>
                            <Plus className="h-[18px] w-[18px]" strokeWidth={2} /> Add subscriber
                        </button>
                    </>
                }
            />

            {/* Site cards: click one to filter the table to that router. */}
            <div className="grid grid-cols-1 gap-[18px] sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
                {sitesLoading
                    ? [...Array(4)].map((_, i) => <Skeleton key={i} className="h-[150px] rounded-card" />)
                    : sites.map((site) => {
                        const active = routerFilter === String(site.id);
                        return (
                            <button
                                key={site.id}
                                onClick={() => { setRouterFilter(active ? '' : String(site.id)); setPage(1); }}
                                aria-pressed={active}
                                className={cn(
                                    'rounded-card border bg-card p-[20px] text-left shadow-card transition-colors',
                                    active ? 'border-primary ring-2 ring-primary/20' : 'border-border hover:border-border-strong',
                                )}
                            >
                                <div className="flex items-start justify-between gap-2">
                                    <div className="min-w-0">
                                        <p className="truncate text-[14.5px] font-semibold text-foreground">{site.name}</p>
                                        <p className="truncate text-[12.5px] text-muted-foreground">{site.model || 'MikroTik'}</p>
                                    </div>
                                    <StatusBadge status={site.status} label={site.status === 'unknown' ? 'Checking' : undefined} />
                                </div>
                                <div className="mt-5 flex items-end justify-between gap-3">
                                    <div>
                                        <p className="num text-[24px] font-extrabold leading-none text-foreground">{formatCount(site.clients)}</p>
                                        <p className="mt-1 text-[12.5px] text-faint">online</p>
                                    </div>
                                    <div className="text-right">
                                        <p className="num text-[15px] font-semibold text-foreground">{site.throughput || '—'}</p>
                                        <p className="text-[12.5px] text-faint">throughput</p>
                                    </div>
                                </div>
                            </button>
                        );
                    })}
            </div>

            <Panel className="p-0">
                {/* Tabs + filters */}
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4">
                    <div className="flex flex-wrap items-center gap-1" role="tablist" aria-label="Subscriber status">
                        {TABS.map((t) => {
                            const active = activeTab === t.key;
                            return (
                                <button
                                    key={t.key}
                                    role="tab"
                                    aria-selected={active}
                                    onClick={() => selectTab(t.key)}
                                    className={cn(
                                        'flex h-10 items-center gap-2 rounded-full px-4 text-[14px] font-semibold transition-colors',
                                        active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
                                    )}
                                >
                                    {t.label}
                                    <span className={cn(
                                        'num rounded-full px-2 py-0.5 text-[12px] font-semibold',
                                        active ? 'bg-white/20 text-white' : 'bg-chip text-muted-foreground',
                                    )}>
                                        {summary ? formatCount(summary[t.key]) : '·'}
                                    </span>
                                </button>
                            );
                        })}
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                        <div className="relative">
                            <Search className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-faint" />
                            <input
                                type="search"
                                aria-label="Search subscribers"
                                placeholder="Name, phone, username…"
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="h-10 w-56 rounded-full border border-input bg-card pl-10 pr-4 text-[13.5px] placeholder:text-faint focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            />
                        </div>
                        <label className="relative">
                            <span className="sr-only">Site</span>
                            <Filter className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-foreground" />
                            <select value={routerFilter} onChange={(e) => { setRouterFilter(e.target.value); setPage(1); }} className={selectClass}>
                                <option value="">Site: All</option>
                                {routerOptions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                            </select>
                        </label>
                        <label className="relative">
                            <span className="sr-only">Plan</span>
                            <Package className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-foreground" />
                            <select value={planFilter} onChange={(e) => { setPlanFilter(e.target.value); setPage(1); }} className={selectClass}>
                                <option value="">Plan: All</option>
                                {plans?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                            </select>
                        </label>
                        <label className="relative">
                            <span className="sr-only">Service type</span>
                            <Layers className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-foreground" />
                            <select value={typeFilter} onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }} className={selectClass}>
                                <option value="">Type: All</option>
                                <option value="pppoe">PPPoE</option>
                                <option value="hotspot">Hotspot</option>
                                <option value="static">Static</option>
                            </select>
                        </label>
                    </div>
                </div>

                <div className="overflow-x-auto px-3">
                    <table className="w-full border-collapse text-[13.5px]">
                        <thead>
                            <tr className="text-left">
                                <th className="w-10 border-b border-border px-3 py-3.5">
                                    <input
                                        type="checkbox"
                                        aria-label="Select all on this page"
                                        checked={allOnPageSelected}
                                        onChange={toggleAll}
                                        className="h-[18px] w-[18px] rounded-md accent-[hsl(var(--primary))]"
                                    />
                                </th>
                                {['Subscriber', 'Plan', 'Site', 'Type', 'Status'].map((h) => (
                                    <th key={h} className="border-b border-border px-3 py-3.5 text-[13px] font-medium text-faint">{h}</th>
                                ))}
                                <th className="border-b border-border px-3 py-3.5 text-[13px] font-medium text-faint">
                                    <button onClick={() => toggleSort('calculated_expiry')} className="inline-flex items-center gap-1 hover:text-foreground">
                                        Expires <SortIcon field="calculated_expiry" />
                                    </button>
                                </th>
                                <th className="border-b border-border px-3 py-3.5 text-right text-[13px] font-medium text-faint">
                                    <button onClick={() => toggleSort('account_balance')} className="inline-flex items-center gap-1 hover:text-foreground">
                                        Balance <SortIcon field="account_balance" />
                                    </button>
                                </th>
                                <th className="w-12 border-b border-border px-3 py-3.5"><span className="sr-only">Actions</span></th>
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? (
                                [...Array(6)].map((_, i) => (
                                    <tr key={i}><td colSpan={9} className="px-3 py-3"><Skeleton className="h-11 w-full" /></td></tr>
                                ))
                            ) : isError ? (
                                <tr><td colSpan={9} className="px-3 py-8 text-center text-bad">Error loading subscribers: {(error as Error).message}</td></tr>
                            ) : subscribers.length === 0 ? (
                                <tr><td colSpan={9}>
                                    <EmptyState
                                        message={search || routerFilter || planFilter || typeFilter ? 'No subscribers match these filters.' : 'No subscribers yet.'}
                                        action={search || routerFilter || planFilter || typeFilter ? (
                                            <button
                                                onClick={() => { setSearchTerm(''); setRouterFilter(''); setPlanFilter(''); setTypeFilter(''); }}
                                                className="text-[13px] font-semibold text-primary"
                                            >
                                                Clear filters
                                            </button>
                                        ) : undefined}
                                    />
                                </td></tr>
                            ) : subscribers.map((row, idx) => {
                                const name = row.full_name || row.username;
                                const isSelected = !!selected[row.id];
                                return (
                                    <tr key={row.id} className={cn('border-b border-border-soft last:border-0', isSelected ? 'bg-surface2' : 'hover:bg-surface2')}>
                                        <td className="px-3 py-3.5">
                                            <input
                                                type="checkbox"
                                                aria-label={`Select ${name}`}
                                                checked={isSelected}
                                                onChange={() => toggleRow(row)}
                                                className="h-[18px] w-[18px] rounded-md accent-[hsl(var(--primary))]"
                                            />
                                        </td>
                                        <td className="px-3 py-3.5">
                                            <button onClick={() => openModal(row.id, 'details')} className="flex items-center gap-3 text-left">
                                                <span className={cn('grid h-9 w-9 shrink-0 place-items-center rounded-xl text-[12.5px] font-bold', AVATAR_TONES[((page - 1) * pageSize + idx) % AVATAR_TONES.length])}>
                                                    {initials(name)}
                                                </span>
                                                <span className="min-w-0">
                                                    <span className="block truncate font-semibold text-foreground">{name}</span>
                                                    <span className="num block truncate text-[12.5px] text-muted-foreground">
                                                        {[row.username !== name ? row.username : null, maskPhone(row.phone_number)].filter(Boolean).join(' · ') || '—'}
                                                    </span>
                                                </span>
                                            </button>
                                        </td>
                                        <td className="whitespace-nowrap px-3 py-3.5">
                                            {row.current_plan_name ? (
                                                <>
                                                    <span className="block text-foreground">{row.current_plan_name}</span>
                                                    {row.current_plan_price != null && (
                                                        <span className="num block text-[12.5px] text-muted-foreground">{formatKES(row.current_plan_price)}</span>
                                                    )}
                                                </>
                                            ) : <span className="text-faint">No plan</span>}
                                        </td>
                                        <td className="whitespace-nowrap px-3 py-3.5">
                                            {row.router_name ? (
                                                <span className="inline-flex items-center gap-2 text-foreground">
                                                    <MapPin className="h-4 w-4 text-muted-foreground" strokeWidth={1.8} />
                                                    {row.router_name}
                                                </span>
                                            ) : <span className="text-faint">—</span>}
                                        </td>
                                        <td className="whitespace-nowrap px-3 py-3.5">
                                            <span className="rounded-full bg-chip px-2.5 py-1 text-[11.5px] font-semibold uppercase tracking-wide text-muted-foreground">
                                                {row.service_type}
                                            </span>
                                        </td>
                                        <td className="whitespace-nowrap px-3 py-3.5"><StatusBadge status={rowStatus(row)} /></td>
                                        <td className="num whitespace-nowrap px-3 py-3.5 text-foreground">
                                            {row.calculated_expiry ? formatDateEAT(row.calculated_expiry, { day: '2-digit', month: 'short' }) : '—'}
                                        </td>
                                        <td className="num whitespace-nowrap px-3 py-3.5 text-right text-muted-foreground">{formatKES(row.account_balance)}</td>
                                        <td className="px-3 py-3.5 text-right">
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <button aria-label={`Actions for ${name}`} className="grid h-8 w-8 place-items-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground">
                                                        <MoreHorizontal className="h-5 w-5" />
                                                    </button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent align="end" className="w-48">
                                                    <DropdownMenuItem onClick={() => openModal(row.id, 'usage')}><Eye className="h-4 w-4" /> Usage & history</DropdownMenuItem>
                                                    <DropdownMenuItem onClick={() => openModal(row.id, 'plans')}><RefreshCw className="h-4 w-4" /> Recharge</DropdownMenuItem>
                                                    <DropdownMenuItem onClick={() => openModal(row.id, 'details')}><Pencil className="h-4 w-4" /> Edit profile</DropdownMenuItem>
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>

                {/* Bulk bar + pagination */}
                <div className={cn('flex flex-wrap items-center justify-between gap-3 rounded-b-card border-t border-border bg-card p-4', selectedRows.length > 0 && 'sticky bottom-0 z-10')}>
                    {selectedRows.length > 0 ? (
                        <div className="flex flex-wrap items-center gap-2 rounded-full bg-[#14231B] py-2 pl-5 pr-2 text-white">
                            <span className="text-[14px] font-bold">{selectedRows.length} selected</span>
                            <span className="mr-2 max-w-[180px] truncate text-[13.5px] text-white/60">
                                {selectedRows.length === 1 ? (selectedRows[0].full_name || selectedRows[0].username) : ''}
                            </span>
                            {isAdmin && (
                                <button
                                    onClick={sendStkReminders}
                                    disabled={!!bulkBusy}
                                    className="flex h-10 items-center gap-2 rounded-full bg-mpesa px-4 text-[14px] font-semibold disabled:opacity-60"
                                >
                                    {bulkBusy === 'stk' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
                                    Send STK reminder
                                </button>
                            )}
                            {canRenew && <button
                                onClick={renewSelected}
                                disabled={!!bulkBusy}
                                className="flex h-10 items-center gap-2 rounded-full border border-white/25 px-4 text-[14px] font-semibold hover:bg-white/10 disabled:opacity-60"
                            >
                                {bulkBusy === 'renew' ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                                Renew
                            </button>}
                            <button
                                onClick={() => setSelected({})}
                                aria-label="Clear selection"
                                className="grid h-10 w-10 place-items-center rounded-full hover:bg-white/10"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                    ) : (
                        <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
                            Rows
                            <select
                                value={pageSize}
                                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
                                className="h-9 rounded-full border border-input bg-card px-3 text-[13px] focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            >
                                {[10, 20, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
                            </select>
                        </label>
                    )}

                    <div className="flex items-center gap-3">
                        <span className="num text-[13.5px] text-muted-foreground">
                            {firstRow}–{lastRow} of {formatCount(totalCount)}
                        </span>
                        <button
                            onClick={() => setPage((p) => Math.max(1, p - 1))}
                            disabled={page <= 1}
                            aria-label="Previous page"
                            className="grid h-10 w-10 place-items-center rounded-full border border-input text-foreground hover:bg-accent disabled:opacity-40"
                        >
                            <ArrowLeft className="h-4 w-4" />
                        </button>
                        <button
                            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                            disabled={page >= totalPages}
                            aria-label="Next page"
                            className="grid h-10 w-10 place-items-center rounded-full border border-input text-foreground hover:bg-accent disabled:opacity-40"
                        >
                            <ArrowRight className="h-4 w-4" />
                        </button>
                    </div>
                </div>
            </Panel>

            {selectedId !== null && (
                <SubscriberDetailModal id={selectedId} initialTab={initialTab} onClose={() => { setSelectedId(null); refreshLists(); }} />
            )}
        </div>
    );
}
