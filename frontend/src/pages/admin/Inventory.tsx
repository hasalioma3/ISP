import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { inventoryAPI, adminAPI } from '../../services/api';
import {
    Boxes, LayoutDashboard, Package, ShoppingCart, Wrench, Plus, Pencil, Trash2, X,
    Search, Loader2, ChevronLeft, ChevronRight, AlertTriangle, CheckCircle2, Paperclip,
} from 'lucide-react';
import { format } from 'date-fns';
import toast from 'react-hot-toast';
import { useAuthStore } from '../../store/authStore';
import AttachmentInput from '../../components/AttachmentInput';
import { getErrorMessage } from '../../utils/getErrorMessage';

const ITEM_CATEGORIES = [
    { value: 'router', label: 'Router / CPE' },
    { value: 'antenna', label: 'Antenna' },
    { value: 'cable', label: 'Cable' },
    { value: 'connector', label: 'Connector' },
    { value: 'mounting', label: 'Mounting Hardware' },
    { value: 'power', label: 'Power Supply / PoE' },
    { value: 'switch', label: 'Switch' },
    { value: 'fiber', label: 'Fiber Optic Equipment' },
    { value: 'tool', label: 'Tools' },
    { value: 'other', label: 'Other' },
];

const UNITS = [
    { value: 'piece', label: 'Piece' },
    { value: 'meter', label: 'Meter' },
    { value: 'box', label: 'Box' },
    { value: 'roll', label: 'Roll' },
    { value: 'pair', label: 'Pair' },
];

const USAGE_REASONS = [
    { value: 'new_install', label: 'New Install' },
    { value: 'repair', label: 'Repair' },
    { value: 'migration', label: 'Migration' },
    { value: 'office_setup', label: 'Office Setup' },
    { value: 'other', label: 'Other' },
];

const TABS = [
    { key: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, roles: undefined },
    { key: 'usage', label: 'Usage Log', icon: Wrench, roles: undefined },
    { key: 'items', label: 'Items', icon: Package, roles: ['admin', 'sales'] },
    { key: 'purchases', label: 'Purchases', icon: ShoppingCart, roles: ['admin', 'sales'] },
] as const;

export default function Inventory() {
    const user = useAuthStore((state) => state.user);
    const canSee = (roles?: readonly string[]) => !roles || user?.is_superuser || roles.includes(user?.role || '');
    const visibleTabs = TABS.filter(t => canSee(t.roles));
    const [activeTab, setActiveTab] = useState<typeof TABS[number]['key']>('dashboard');

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6 flex items-center gap-2"><Boxes className="h-6 w-6" /> Inventory</h1>

            <div className="bg-card rounded-2xl shadow-sm border border-border overflow-hidden min-h-[500px]">
                <div className="flex border-b overflow-x-auto">
                    {visibleTabs.map(t => {
                        const Icon = t.icon;
                        return (
                            <button
                                key={t.key}
                                onClick={() => setActiveTab(t.key)}
                                className={`flex items-center shrink-0 px-4 sm:px-6 py-4 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${activeTab === t.key
                                    ? 'border-ring text-primary'
                                    : 'border-transparent text-muted-foreground hover:text-foreground/80 hover:bg-secondary'
                                    }`}
                            >
                                <Icon className="h-4 w-4 mr-2" />
                                {t.label}
                            </button>
                        );
                    })}
                </div>

                <div className="p-4 sm:p-6">
                    {activeTab === 'dashboard' && <DashboardTab />}
                    {activeTab === 'usage' && <UsageTab />}
                    {activeTab === 'items' && canSee(['admin', 'sales']) && <ItemsTab />}
                    {activeTab === 'purchases' && canSee(['admin', 'sales']) && <PurchasesTab />}
                </div>
            </div>
        </div>
    );
}

function DashboardTab() {
    const { data, isLoading, isError, error } = useQuery({
        queryKey: ['inventory-dashboard'],
        queryFn: async () => (await inventoryAPI.getDashboard()).data,
    });

    if (isLoading) return <div className="py-16 text-center text-muted-foreground flex items-center justify-center gap-2"><Loader2 className="h-5 w-5 animate-spin" /> Loading...</div>;
    if (isError) return <div className="py-16 text-center text-red-500">Error: {(error as Error).message}</div>;

    return (
        <div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
                <div className="bg-primary/10 border border-primary/20 rounded-xl p-5">
                    <p className="text-xs font-medium text-primary uppercase mb-1">Items Tracked</p>
                    <p className="text-2xl font-bold text-primary">{data.total_items}</p>
                </div>
                <div className={`${data.low_stock_count > 0 ? 'bg-amber-50 border-amber-100' : 'bg-green-50 border-green-100'} border rounded-xl p-5`}>
                    <p className={`text-xs font-medium uppercase mb-1 ${data.low_stock_count > 0 ? 'text-amber-700' : 'text-green-700'}`}>Running Low</p>
                    <p className={`text-2xl font-bold flex items-center gap-2 ${data.low_stock_count > 0 ? 'text-amber-900' : 'text-green-900'}`}>
                        {data.low_stock_count > 0 ? <AlertTriangle className="h-5 w-5" /> : <CheckCircle2 className="h-5 w-5" />}
                        {data.low_stock_count}
                    </p>
                </div>
                {data.total_purchase_value !== undefined && (
                    <div className="bg-secondary border border-border rounded-xl p-5">
                        <p className="text-xs font-medium text-foreground/80 uppercase mb-1">Total Purchase Value</p>
                        <p className="text-2xl font-bold text-foreground">KES {Number(data.total_purchase_value).toLocaleString()}</p>
                    </div>
                )}
            </div>

            {data.low_stock_items.length > 0 && (
                <div className="mb-6 bg-amber-50 border border-amber-200 rounded-xl p-4">
                    <h3 className="text-sm font-bold text-amber-900 mb-2 flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> Running Low -- Reorder Soon</h3>
                    <ul className="space-y-1 text-sm">
                        {data.low_stock_items.map((i: any) => (
                            <li key={i.id} className="flex items-center justify-between text-amber-900">
                                <span>{i.name} <span className="text-amber-600">({i.category_display})</span></span>
                                <span className="font-medium">{i.current_stock} / {i.reorder_level} {i.unit_display.toLowerCase()}(s)</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            <div className="overflow-x-auto border rounded-lg">
                <table className="min-w-full divide-y divide-border">
                    <thead className="bg-secondary">
                        <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Item</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Category</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">In Storage</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Reorder Level</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Status</th>
                        </tr>
                    </thead>
                    <tbody className="bg-card divide-y divide-border">
                        {data.items.length === 0 ? (
                            <tr><td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">No items tracked yet.</td></tr>
                        ) : (
                            data.items.map((i: any) => (
                                <tr key={i.id} className="hover:bg-secondary">
                                    <td className="px-4 py-3 text-sm font-medium text-foreground">{i.name}</td>
                                    <td className="px-4 py-3 text-sm text-muted-foreground">{i.category_display}</td>
                                    <td className="px-4 py-3 text-sm text-foreground">{i.current_stock} {i.unit_display.toLowerCase()}(s)</td>
                                    <td className="px-4 py-3 text-sm text-muted-foreground">{i.reorder_level}</td>
                                    <td className="px-4 py-3">
                                        <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${i.is_low_stock ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-800'}`}>
                                            {i.is_low_stock ? 'Low Stock' : 'OK'}
                                        </span>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function useAllItems() {
    return useQuery({
        queryKey: ['inventory-items-all'],
        queryFn: async () => (await inventoryAPI.getItems({ page_size: 200, is_active: true })).data.results || [],
    });
}

function ItemsTab() {
    const queryClient = useQueryClient();
    const [search, setSearch] = useState('');
    const [page, setPage] = useState(1);
    const pageSize = 15;
    const [modalOpen, setModalOpen] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form, setForm] = useState({ name: '', category: 'other', unit: 'piece', sku: '', reorder_level: '0', notes: '', is_active: true });

    const { data, isLoading } = useQuery({
        queryKey: ['inventory-items', search, page],
        queryFn: async () => (await inventoryAPI.getItems({ search: search || undefined, page, page_size: pageSize })).data,
    });

    const items = data?.results || [];
    const totalCount = data?.count ?? items.length;
    const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

    const invalidate = () => {
        queryClient.invalidateQueries({ queryKey: ['inventory-items'] });
        queryClient.invalidateQueries({ queryKey: ['inventory-items-all'] });
        queryClient.invalidateQueries({ queryKey: ['inventory-dashboard'] });
    };

    const saveMutation = useMutation({
        mutationFn: () => editingId ? inventoryAPI.updateItem(editingId, form) : inventoryAPI.createItem(form),
        onSuccess: () => { toast.success(editingId ? 'Updated' : 'Added'); setModalOpen(false); invalidate(); },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Failed to save')),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => inventoryAPI.deleteItem(id),
        onSuccess: () => { toast.success('Deleted'); invalidate(); },
        onError: () => toast.error('Failed to delete -- it may have purchase/usage history'),
    });

    const openAdd = () => {
        setEditingId(null);
        setForm({ name: '', category: 'other', unit: 'piece', sku: '', reorder_level: '0', notes: '', is_active: true });
        setModalOpen(true);
    };

    const openEdit = (item: any) => {
        setEditingId(item.id);
        setForm({ name: item.name, category: item.category, unit: item.unit, sku: item.sku || '', reorder_level: String(item.reorder_level), notes: item.notes || '', is_active: item.is_active });
        setModalOpen(true);
    };

    return (
        <div>
            <div className="flex flex-wrap items-center gap-3 mb-4">
                <div className="relative flex-1 min-w-[200px]">
                    <input type="text" placeholder="Search name/SKU..." className="pl-10 pr-4 py-2 border rounded-lg w-full text-sm" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
                    <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                </div>
                <button onClick={openAdd} className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary/90 text-white rounded-lg text-sm font-medium">
                    <Plus className="h-4 w-4" /> Add Item
                </button>
            </div>

            <div className="overflow-x-auto border rounded-lg">
                <table className="min-w-full divide-y divide-border">
                    <thead className="bg-secondary">
                        <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Name</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Category</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Unit</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">In Storage</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Reorder Level</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-card divide-y divide-border">
                        {isLoading ? (
                            <tr><td colSpan={6} className="px-6 py-8 text-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin inline mr-2" />Loading...</td></tr>
                        ) : items.length === 0 ? (
                            <tr><td colSpan={6} className="px-6 py-8 text-center text-muted-foreground">No items yet.</td></tr>
                        ) : (
                            items.map((item: any) => (
                                <tr key={item.id} className="hover:bg-secondary">
                                    <td className="px-4 py-3 text-sm font-medium text-foreground">{item.name} {item.sku && <span className="text-muted-foreground font-mono text-xs">({item.sku})</span>}</td>
                                    <td className="px-4 py-3 text-sm text-muted-foreground">{item.category_display}</td>
                                    <td className="px-4 py-3 text-sm text-muted-foreground">{item.unit_display}</td>
                                    <td className="px-4 py-3 text-sm">
                                        <span className={item.is_low_stock ? 'text-amber-700 font-medium' : 'text-foreground'}>{item.current_stock}</span>
                                    </td>
                                    <td className="px-4 py-3 text-sm text-muted-foreground">{item.reorder_level}</td>
                                    <td className="px-4 py-3">
                                        <div className="flex gap-1">
                                            <button onClick={() => openEdit(item)} className="flex items-center px-2 py-1 bg-amber-500 text-white rounded text-xs hover:bg-amber-600"><Pencil className="h-3 w-3 mr-1" /> Edit</button>
                                            <button onClick={() => { if (confirm('Delete this item?')) deleteMutation.mutate(item.id); }} className="flex items-center px-2 py-1 bg-red-600 text-white rounded text-xs hover:bg-red-700"><Trash2 className="h-3 w-3 mr-1" /> Delete</button>
                                        </div>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            <div className="flex items-center justify-between px-1 py-3 text-sm text-muted-foreground">
                <span>{totalCount === 0 ? '0 results' : `Page ${page} of ${totalPages} · ${totalCount} total`}</span>
                <div className="flex gap-2">
                    <button disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))} className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 hover:bg-secondary"><ChevronLeft className="h-4 w-4" /> Prev</button>
                    <button disabled={page >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))} className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 hover:bg-secondary">Next <ChevronRight className="h-4 w-4" /></button>
                </div>
            </div>

            {modalOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-card rounded-xl shadow-xl w-full max-w-md">
                        <div className="flex justify-between items-center p-5 border-b">
                            <h3 className="text-lg font-bold">{editingId ? 'Edit' : 'Add'} Item</h3>
                            <button onClick={() => setModalOpen(false)} className="p-1 text-muted-foreground hover:text-muted-foreground"><X className="h-5 w-5" /></button>
                        </div>
                        <form onSubmit={(e) => { e.preventDefault(); saveMutation.mutate(); }} className="p-5 space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-foreground/80 mb-1">Name</label>
                                <input required type="text" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-foreground/80 mb-1">Category</label>
                                    <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                                        {ITEM_CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-foreground/80 mb-1">Unit</label>
                                    <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })}>
                                        {UNITS.map(u => <option key={u.value} value={u.value}>{u.label}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-foreground/80 mb-1">SKU (optional)</label>
                                    <input type="text" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-foreground/80 mb-1">Reorder Level</label>
                                    <input required type="number" min="0" step="0.01" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.reorder_level} onChange={(e) => setForm({ ...form, reorder_level: e.target.value })} />
                                </div>
                            </div>
                            <label className="flex items-center gap-2 text-sm text-foreground/80">
                                <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                                Active (shown as a usable item)
                            </label>
                            <button type="submit" disabled={saveMutation.isPending} className="w-full flex items-center justify-center px-4 py-2 bg-primary hover:bg-primary/90 text-white rounded-lg font-medium disabled:opacity-50">
                                {saveMutation.isPending ? 'Saving...' : editingId ? 'Save Changes' : 'Add Item'}
                            </button>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}

function PurchasesTab() {
    const queryClient = useQueryClient();
    const { data: items } = useAllItems();
    const [page, setPage] = useState(1);
    const pageSize = 15;
    const [modalOpen, setModalOpen] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form, setForm] = useState({ item: '', quantity: '', unit_cost: '', supplier: '', date: format(new Date(), 'yyyy-MM-dd'), notes: '' });
    const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
    const [existingAttachmentUrl, setExistingAttachmentUrl] = useState<string | null>(null);

    const { data, isLoading } = useQuery({
        queryKey: ['inventory-purchases', page],
        queryFn: async () => (await inventoryAPI.getPurchases({ page, page_size: pageSize })).data,
    });

    const purchases = data?.results || [];
    const totalCount = data?.count ?? purchases.length;
    const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

    const invalidate = () => {
        queryClient.invalidateQueries({ queryKey: ['inventory-purchases'] });
        queryClient.invalidateQueries({ queryKey: ['inventory-dashboard'] });
        queryClient.invalidateQueries({ queryKey: ['inventory-items'] });
        queryClient.invalidateQueries({ queryKey: ['accounting-expense'] });
    };

    const saveMutation = useMutation({
        mutationFn: () => editingId ? inventoryAPI.updatePurchase(editingId, form, attachmentFile) : inventoryAPI.createPurchase(form, attachmentFile),
        onSuccess: () => { toast.success(editingId ? 'Updated' : 'Purchase recorded'); setModalOpen(false); invalidate(); },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Failed to save')),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => inventoryAPI.deletePurchase(id),
        onSuccess: () => { toast.success('Deleted'); invalidate(); },
        onError: () => toast.error('Failed to delete'),
    });

    const openAdd = () => {
        setEditingId(null);
        setForm({ item: items?.[0]?.id ? String(items[0].id) : '', quantity: '', unit_cost: '', supplier: '', date: format(new Date(), 'yyyy-MM-dd'), notes: '' });
        setAttachmentFile(null);
        setExistingAttachmentUrl(null);
        setModalOpen(true);
    };

    const openEdit = (p: any) => {
        setEditingId(p.id);
        setForm({ item: String(p.item), quantity: String(p.quantity), unit_cost: String(p.unit_cost), supplier: p.supplier || '', date: p.date, notes: p.notes || '' });
        setAttachmentFile(null);
        setExistingAttachmentUrl(p.attachment || null);
        setModalOpen(true);
    };

    return (
        <div>
            <div className="flex justify-end mb-4">
                <button onClick={openAdd} disabled={!items?.length} className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium disabled:opacity-50">
                    <Plus className="h-4 w-4" /> Record Purchase
                </button>
            </div>
            {!items?.length && <p className="text-sm text-amber-600 mb-4">Add an item in the Items tab first.</p>}

            <div className="overflow-x-auto border rounded-lg">
                <table className="min-w-full divide-y divide-border">
                    <thead className="bg-secondary">
                        <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Date</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Item</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Quantity</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Unit Cost</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Total</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Supplier</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-card divide-y divide-border">
                        {isLoading ? (
                            <tr><td colSpan={7} className="px-6 py-8 text-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin inline mr-2" />Loading...</td></tr>
                        ) : purchases.length === 0 ? (
                            <tr><td colSpan={7} className="px-6 py-8 text-center text-muted-foreground">No purchases recorded yet.</td></tr>
                        ) : (
                            purchases.map((p: any) => (
                                <tr key={p.id} className="hover:bg-secondary">
                                    <td className="px-4 py-3 text-sm text-muted-foreground whitespace-nowrap">{format(new Date(p.date), 'MMM d, yyyy')}</td>
                                    <td className="px-4 py-3 text-sm font-medium text-foreground">{p.item_name}</td>
                                    <td className="px-4 py-3 text-sm text-foreground">{p.quantity}</td>
                                    <td className="px-4 py-3 text-sm text-muted-foreground">KES {Number(p.unit_cost).toLocaleString()}</td>
                                    <td className="px-4 py-3 text-sm font-medium text-foreground">KES {Number(p.total_cost).toLocaleString()}</td>
                                    <td className="px-4 py-3 text-sm text-muted-foreground">{p.supplier || '-'}</td>
                                    <td className="px-4 py-3">
                                        <div className="flex gap-1">
                                            {p.attachment && (
                                                <a href={p.attachment} target="_blank" rel="noreferrer" className="flex items-center px-2 py-1 bg-gray-100 text-muted-foreground rounded text-xs hover:bg-gray-200" title="View attachment">
                                                    <Paperclip className="h-3 w-3" />
                                                </a>
                                            )}
                                            <button onClick={() => openEdit(p)} className="flex items-center px-2 py-1 bg-amber-500 text-white rounded text-xs hover:bg-amber-600"><Pencil className="h-3 w-3 mr-1" /> Edit</button>
                                            <button onClick={() => { if (confirm('Delete this purchase? Its linked expense will also be removed.')) deleteMutation.mutate(p.id); }} className="flex items-center px-2 py-1 bg-red-600 text-white rounded text-xs hover:bg-red-700"><Trash2 className="h-3 w-3 mr-1" /> Delete</button>
                                        </div>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            <div className="flex items-center justify-between px-1 py-3 text-sm text-muted-foreground">
                <span>{totalCount === 0 ? '0 results' : `Page ${page} of ${totalPages} · ${totalCount} total`}</span>
                <div className="flex gap-2">
                    <button disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))} className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 hover:bg-secondary"><ChevronLeft className="h-4 w-4" /> Prev</button>
                    <button disabled={page >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))} className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 hover:bg-secondary">Next <ChevronRight className="h-4 w-4" /></button>
                </div>
            </div>

            {modalOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-card rounded-xl shadow-xl w-full max-w-md">
                        <div className="flex justify-between items-center p-5 border-b">
                            <h3 className="text-lg font-bold">{editingId ? 'Edit' : 'Record'} Purchase</h3>
                            <button onClick={() => setModalOpen(false)} className="p-1 text-muted-foreground hover:text-muted-foreground"><X className="h-5 w-5" /></button>
                        </div>
                        <form onSubmit={(e) => { e.preventDefault(); saveMutation.mutate(); }} className="p-5 space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-foreground/80 mb-1">Item</label>
                                <select required className="w-full border rounded-lg px-3 py-2 text-sm" value={form.item} onChange={(e) => setForm({ ...form, item: e.target.value })}>
                                    <option value="">Select an item...</option>
                                    {items?.map((i: any) => <option key={i.id} value={i.id}>{i.name}</option>)}
                                </select>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-foreground/80 mb-1">Quantity</label>
                                    <input required type="number" min="0.01" step="0.01" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-foreground/80 mb-1">Unit Cost (KES)</label>
                                    <input required type="number" min="0" step="0.01" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.unit_cost} onChange={(e) => setForm({ ...form, unit_cost: e.target.value })} />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-foreground/80 mb-1">Supplier (optional)</label>
                                    <input type="text" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.supplier} onChange={(e) => setForm({ ...form, supplier: e.target.value })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-foreground/80 mb-1">Date</label>
                                    <input required type="date" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
                                </div>
                            </div>
                            <AttachmentInput
                                label="Receipt / Invoice (optional)"
                                file={attachmentFile}
                                onFileChange={setAttachmentFile}
                                existingUrl={existingAttachmentUrl}
                            />
                            <p className="text-xs text-muted-foreground">This automatically records a matching Expense (Equipment & Hardware) in Accounting.</p>
                            <button type="submit" disabled={saveMutation.isPending} className="w-full flex items-center justify-center px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium disabled:opacity-50">
                                {saveMutation.isPending ? 'Saving...' : editingId ? 'Save Changes' : 'Record Purchase'}
                            </button>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}

function CustomerPicker({ value, onChange }: { value: { id: number; username: string } | null; onChange: (c: { id: number; username: string } | null) => void }) {
    const [query, setQuery] = useState('');
    const { data } = useQuery({
        queryKey: ['customer-picker', query],
        queryFn: async () => (await adminAPI.getSubscribers({ search: query, page_size: 6 })).data.results || [],
        enabled: query.length > 0,
    });

    if (value) {
        return (
            <div className="flex items-center justify-between border rounded-lg px-3 py-2 text-sm bg-secondary">
                <span className="font-medium text-foreground">{value.username}</span>
                <button type="button" onClick={() => onChange(null)} className="text-muted-foreground hover:text-muted-foreground"><X className="h-4 w-4" /></button>
            </div>
        );
    }

    return (
        <div className="relative">
            <input
                type="text"
                placeholder="Search customer by name/username/phone..."
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
            />
            {query.length > 0 && (data?.length || 0) > 0 && (
                <ul className="absolute z-10 w-full bg-card border rounded-lg mt-1 shadow-lg max-h-48 overflow-y-auto">
                    {data.map((c: any) => (
                        <li key={c.id}>
                            <button
                                type="button"
                                onClick={() => { onChange({ id: c.id, username: c.username }); setQuery(''); }}
                                className="w-full text-left px-3 py-2 text-sm hover:bg-secondary"
                            >
                                {c.username} <span className="text-muted-foreground">{c.full_name}</span>
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

function UsageTab() {
    const queryClient = useQueryClient();
    const user = useAuthStore((state) => state.user);
    const canManage = !!user?.is_superuser || user?.role === 'admin' || user?.role === 'sales';
    const { data: items } = useAllItems();
    const [page, setPage] = useState(1);
    const pageSize = 15;
    const [modalOpen, setModalOpen] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [customer, setCustomer] = useState<{ id: number; username: string } | null>(null);
    const [form, setForm] = useState({ item: '', quantity: '', reason: USAGE_REASONS[0].value, date: format(new Date(), 'yyyy-MM-dd'), notes: '' });

    const { data, isLoading } = useQuery({
        queryKey: ['inventory-usages', page],
        queryFn: async () => (await inventoryAPI.getUsages({ page, page_size: pageSize })).data,
    });

    const usages = data?.results || [];
    const totalCount = data?.count ?? usages.length;
    const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

    const invalidate = () => {
        queryClient.invalidateQueries({ queryKey: ['inventory-usages'] });
        queryClient.invalidateQueries({ queryKey: ['inventory-dashboard'] });
        queryClient.invalidateQueries({ queryKey: ['inventory-items'] });
    };

    const saveMutation = useMutation({
        mutationFn: () => {
            const payload = { ...form, customer: customer?.id };
            return editingId ? inventoryAPI.updateUsage(editingId, payload) : inventoryAPI.createUsage(payload);
        },
        onSuccess: () => { toast.success(editingId ? 'Updated' : 'Usage logged'); setModalOpen(false); invalidate(); },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Failed to save')),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => inventoryAPI.deleteUsage(id),
        onSuccess: () => { toast.success('Deleted'); invalidate(); },
        onError: () => toast.error('Failed to delete'),
    });

    const openAdd = () => {
        setEditingId(null);
        setCustomer(null);
        setForm({ item: items?.[0]?.id ? String(items[0].id) : '', quantity: '', reason: USAGE_REASONS[0].value, date: format(new Date(), 'yyyy-MM-dd'), notes: '' });
        setModalOpen(true);
    };

    const openEdit = (u: any) => {
        setEditingId(u.id);
        setCustomer(u.customer ? { id: u.customer, username: u.customer_username } : null);
        setForm({ item: String(u.item), quantity: String(u.quantity), reason: u.reason, date: u.date, notes: u.notes || '' });
        setModalOpen(true);
    };

    return (
        <div>
            <div className="flex justify-end mb-4">
                <button onClick={openAdd} disabled={!items?.length} className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary/90 text-white rounded-lg text-sm font-medium disabled:opacity-50">
                    <Plus className="h-4 w-4" /> Log Usage
                </button>
            </div>
            {!items?.length && <p className="text-sm text-amber-600 mb-4">No items available to log yet.</p>}

            <div className="overflow-x-auto border rounded-lg">
                <table className="min-w-full divide-y divide-border">
                    <thead className="bg-secondary">
                        <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Date</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Item</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Quantity</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Used On</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Reason</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Recorded By</th>
                            {canManage && <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Actions</th>}
                        </tr>
                    </thead>
                    <tbody className="bg-card divide-y divide-border">
                        {isLoading ? (
                            <tr><td colSpan={7} className="px-6 py-8 text-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin inline mr-2" />Loading...</td></tr>
                        ) : usages.length === 0 ? (
                            <tr><td colSpan={7} className="px-6 py-8 text-center text-muted-foreground">No usage logged yet.</td></tr>
                        ) : (
                            usages.map((u: any) => (
                                <tr key={u.id} className="hover:bg-secondary">
                                    <td className="px-4 py-3 text-sm text-muted-foreground whitespace-nowrap">{format(new Date(u.date), 'MMM d, yyyy')}</td>
                                    <td className="px-4 py-3 text-sm font-medium text-foreground">{u.item_name}</td>
                                    <td className="px-4 py-3 text-sm text-foreground">{u.quantity}</td>
                                    <td className="px-4 py-3 text-sm text-muted-foreground">{u.customer_username || '-'}</td>
                                    <td className="px-4 py-3 text-sm">
                                        <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-foreground/80">{u.reason_display || u.reason}</span>
                                    </td>
                                    <td className="px-4 py-3 text-sm text-muted-foreground">{u.recorded_by_username || '-'}</td>
                                    {canManage && (
                                        <td className="px-4 py-3">
                                            <div className="flex gap-1">
                                                <button onClick={() => openEdit(u)} className="flex items-center px-2 py-1 bg-amber-500 text-white rounded text-xs hover:bg-amber-600"><Pencil className="h-3 w-3 mr-1" /> Edit</button>
                                                <button onClick={() => { if (confirm('Delete this usage record?')) deleteMutation.mutate(u.id); }} className="flex items-center px-2 py-1 bg-red-600 text-white rounded text-xs hover:bg-red-700"><Trash2 className="h-3 w-3 mr-1" /> Delete</button>
                                            </div>
                                        </td>
                                    )}
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            <div className="flex items-center justify-between px-1 py-3 text-sm text-muted-foreground">
                <span>{totalCount === 0 ? '0 results' : `Page ${page} of ${totalPages} · ${totalCount} total`}</span>
                <div className="flex gap-2">
                    <button disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))} className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 hover:bg-secondary"><ChevronLeft className="h-4 w-4" /> Prev</button>
                    <button disabled={page >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))} className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 hover:bg-secondary">Next <ChevronRight className="h-4 w-4" /></button>
                </div>
            </div>

            {modalOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-card rounded-xl shadow-xl w-full max-w-md">
                        <div className="flex justify-between items-center p-5 border-b">
                            <h3 className="text-lg font-bold">{editingId ? 'Edit' : 'Log'} Usage</h3>
                            <button onClick={() => setModalOpen(false)} className="p-1 text-muted-foreground hover:text-muted-foreground"><X className="h-5 w-5" /></button>
                        </div>
                        <form onSubmit={(e) => { e.preventDefault(); saveMutation.mutate(); }} className="p-5 space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-foreground/80 mb-1">Item</label>
                                <select required className="w-full border rounded-lg px-3 py-2 text-sm" value={form.item} onChange={(e) => setForm({ ...form, item: e.target.value })}>
                                    <option value="">Select an item...</option>
                                    {items?.map((i: any) => <option key={i.id} value={i.id}>{i.name} ({i.current_stock} in storage)</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-foreground/80 mb-1">Quantity Used</label>
                                <input required type="number" min="0.01" step="0.01" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-foreground/80 mb-1">Customer</label>
                                <CustomerPicker value={customer} onChange={setCustomer} />
                                <p className="text-xs text-muted-foreground mt-1">For internal/non-customer use (tower, office, etc.), search and pick your internal-use account.</p>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-foreground/80 mb-1">Reason</label>
                                <select required className="w-full border rounded-lg px-3 py-2 text-sm" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })}>
                                    {USAGE_REASONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-foreground/80 mb-1">Date</label>
                                <input required type="date" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
                            </div>
                            <button type="submit" disabled={saveMutation.isPending || !customer} className="w-full flex items-center justify-center px-4 py-2 bg-primary hover:bg-primary/90 text-white rounded-lg font-medium disabled:opacity-50">
                                {saveMutation.isPending ? 'Saving...' : !customer ? 'Select a customer first' : editingId ? 'Save Changes' : 'Log Usage'}
                            </button>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
