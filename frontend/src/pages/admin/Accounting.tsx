import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { accountingAPI } from '../../services/api';
import {
    ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
    PieChart, Pie, Cell,
} from 'recharts';
import {
    Wallet, TrendingUp, TrendingDown, Calendar, Plus, Pencil, Trash2, X,
    Search, Loader2, ChevronLeft, ChevronRight, ArrowDownCircle, ArrowUpCircle, Paperclip,
} from 'lucide-react';
import { format, subDays } from 'date-fns';
import toast from 'react-hot-toast';
import AttachmentInput from '../../components/AttachmentInput';
import { getErrorMessage } from '../../utils/getErrorMessage';

const EXPENSE_CATEGORIES = [
    { value: 'salaries', label: 'Salaries & Wages' },
    { value: 'rent', label: 'Rent' },
    { value: 'bandwidth', label: 'Bandwidth / Uplink' },
    { value: 'equipment', label: 'Equipment & Hardware' },
    { value: 'maintenance', label: 'Maintenance & Repairs' },
    { value: 'fuel', label: 'Fuel / Generator' },
    { value: 'transport', label: 'Transport' },
    { value: 'marketing', label: 'Marketing' },
    { value: 'licenses', label: 'Licenses & Permits' },
    { value: 'utilities', label: 'Utilities' },
    { value: 'other', label: 'Other' },
];

const INCOME_CATEGORIES = [
    { value: 'equipment_sale', label: 'Equipment Sale' },
    { value: 'installation_fee', label: 'Installation Fee' },
    { value: 'advertising', label: 'Advertising' },
    { value: 'commission', label: 'Commission' },
    { value: 'refund', label: 'Refund Received' },
    { value: 'other', label: 'Other' },
];

const PIE_COLORS = ['#7c3aed', '#dc2626', '#16a34a', '#d97706', '#7c3aed', '#0891b2', '#be185d', '#475569', '#ca8a04', '#059669', '#9333ea'];

const TABS = [
    { key: 'dashboard', label: 'Dashboard', icon: TrendingUp },
    { key: 'expenses', label: 'Expenses', icon: ArrowDownCircle },
    { key: 'income', label: 'Other Income', icon: ArrowUpCircle },
] as const;

export default function Accounting() {
    const [activeTab, setActiveTab] = useState<typeof TABS[number]['key']>('dashboard');

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6 flex items-center gap-2"><Wallet className="h-6 w-6" /> Accounting</h1>

            <div className="bg-card rounded-2xl shadow-sm border border-border overflow-hidden min-h-[500px]">
                <div className="flex border-b overflow-x-auto">
                    {TABS.map(t => {
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
                    {activeTab === 'expenses' && (
                        <LedgerTab
                            kind="expense"
                            categories={EXPENSE_CATEGORIES}
                            accentClass="bg-red-600 hover:bg-red-700"
                            listFn={accountingAPI.getExpenses}
                            createFn={accountingAPI.createExpense}
                            updateFn={accountingAPI.updateExpense}
                            deleteFn={accountingAPI.deleteExpense}
                        />
                    )}
                    {activeTab === 'income' && (
                        <LedgerTab
                            kind="income"
                            categories={INCOME_CATEGORIES}
                            accentClass="bg-green-600 hover:bg-green-700"
                            listFn={accountingAPI.getOtherIncome}
                            createFn={accountingAPI.createOtherIncome}
                            updateFn={accountingAPI.updateOtherIncome}
                            deleteFn={accountingAPI.deleteOtherIncome}
                        />
                    )}
                </div>
            </div>
        </div>
    );
}

function DashboardTab() {
    const [startDate, setStartDate] = useState(format(subDays(new Date(), 30), 'yyyy-MM-dd'));
    const [endDate, setEndDate] = useState(format(new Date(), 'yyyy-MM-dd'));

    const { data, isLoading, isError, error } = useQuery({
        queryKey: ['accounting-dashboard', startDate, endDate],
        queryFn: async () => (await accountingAPI.getDashboard(startDate, endDate)).data,
    });

    const profit = data?.profit ?? 0;

    return (
        <div>
            <div className="flex flex-wrap justify-end mb-6">
                <div className="flex items-center gap-2 bg-secondary px-3 py-2 rounded-lg border flex-wrap">
                    <Calendar className="h-4 w-4 text-muted-foreground" />
                    <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="text-sm border-none focus:ring-0 p-0 text-muted-foreground bg-transparent" />
                    <span className="text-muted-foreground">-</span>
                    <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="text-sm border-none focus:ring-0 p-0 text-muted-foreground bg-transparent" />
                </div>
            </div>

            {isLoading ? (
                <div className="py-16 text-center text-muted-foreground flex items-center justify-center gap-2"><Loader2 className="h-5 w-5 animate-spin" /> Loading...</div>
            ) : isError ? (
                <div className="py-16 text-center text-red-500">Error loading dashboard: {(error as Error).message}</div>
            ) : (
                <>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
                        <div className="bg-primary/10 border border-primary/20 rounded-xl p-5">
                            <p className="text-xs font-medium text-primary uppercase mb-1">Total Income</p>
                            <p className="text-2xl font-bold text-primary">KES {Number(data.total_income).toLocaleString()}</p>
                            <p className="text-xs text-primary mt-1">Revenue KES {Number(data.revenue).toLocaleString()} &middot; Other KES {Number(data.other_income).toLocaleString()}</p>
                        </div>
                        <div className="bg-red-50 border border-red-100 rounded-xl p-5">
                            <p className="text-xs font-medium text-red-700 uppercase mb-1">Total Expenses</p>
                            <p className="text-2xl font-bold text-red-900">KES {Number(data.total_expenses).toLocaleString()}</p>
                        </div>
                        <div className={`${profit >= 0 ? 'bg-green-50 border-green-100' : 'bg-amber-50 border-amber-100'} border rounded-xl p-5`}>
                            <p className={`text-xs font-medium uppercase mb-1 ${profit >= 0 ? 'text-green-700' : 'text-amber-700'}`}>Net Profit</p>
                            <p className={`text-2xl font-bold flex items-center gap-2 ${profit >= 0 ? 'text-green-900' : 'text-amber-900'}`}>
                                {profit >= 0 ? <TrendingUp className="h-5 w-5" /> : <TrendingDown className="h-5 w-5" />}
                                KES {Number(profit).toLocaleString()}
                            </p>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <div className="lg:col-span-2 bg-card rounded-xl border border-border p-4">
                            <h3 className="text-sm font-bold mb-3">Income vs Expenses</h3>
                            <div className="h-80">
                                <ResponsiveContainer width="100%" height="100%">
                                    <ComposedChart data={data.daily_series || []}>
                                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                                        <XAxis dataKey="date" tickFormatter={(v) => format(new Date(v), 'MMM d')} />
                                        <YAxis />
                                        <Tooltip
                                            formatter={(value: any, name: string) => [`KES ${Number(value).toLocaleString()}`, name]}
                                            labelFormatter={(label) => format(new Date(label), 'PPP')}
                                        />
                                        <Legend />
                                        <Bar dataKey="income" fill="#7c3aed" name="Income" radius={[4, 4, 0, 0]} />
                                        <Bar dataKey="expenses" fill="#dc2626" name="Expenses" radius={[4, 4, 0, 0]} />
                                        <Line type="monotone" dataKey="profit" stroke="#16a34a" strokeWidth={2} name="Profit" dot={false} />
                                    </ComposedChart>
                                </ResponsiveContainer>
                            </div>
                        </div>

                        <div className="bg-card rounded-xl border border-border p-4">
                            <h3 className="text-sm font-bold mb-3">Expenses by Category</h3>
                            {(data.expense_by_category || []).length === 0 ? (
                                <p className="text-sm text-muted-foreground text-center py-12">No expenses in this range.</p>
                            ) : (
                                <div className="h-60">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <PieChart>
                                            <Pie data={data.expense_by_category} dataKey="total" nameKey="label" outerRadius={75}>
                                                {data.expense_by_category.map((_: any, i: number) => (
                                                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                                                ))}
                                            </Pie>
                                            <Tooltip formatter={(value: any) => `KES ${Number(value).toLocaleString()}`} />
                                        </PieChart>
                                    </ResponsiveContainer>
                                </div>
                            )}
                            <ul className="mt-2 space-y-1 text-xs">
                                {(data.expense_by_category || []).map((e: any, i: number) => (
                                    <li key={e.category} className="flex items-center justify-between">
                                        <span className="flex items-center gap-1.5 text-muted-foreground">
                                            <span className="h-2 w-2 rounded-full inline-block" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                                            {e.label}
                                        </span>
                                        <span className="font-medium text-foreground">KES {Number(e.total).toLocaleString()}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}

interface LedgerTabProps {
    kind: 'expense' | 'income';
    categories: { value: string; label: string }[];
    accentClass: string;
    listFn: (params?: any) => Promise<any>;
    createFn: (data: any, file?: File | null) => Promise<any>;
    updateFn: (id: number, data: any, file?: File | null) => Promise<any>;
    deleteFn: (id: number) => Promise<any>;
}

function LedgerTab({ kind, categories, accentClass, listFn, createFn, updateFn, deleteFn }: LedgerTabProps) {
    const queryClient = useQueryClient();
    const queryKey = [`accounting-${kind}`];
    const [search, setSearch] = useState('');
    const [categoryFilter, setCategoryFilter] = useState('');
    const [page, setPage] = useState(1);
    const pageSize = 15;
    const [modalOpen, setModalOpen] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form, setForm] = useState({ category: categories[0].value, description: '', amount: '', date: format(new Date(), 'yyyy-MM-dd'), notes: '' });
    const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
    const [existingAttachmentUrl, setExistingAttachmentUrl] = useState<string | null>(null);

    const { data, isLoading, isError, error } = useQuery({
        queryKey: [...queryKey, search, categoryFilter, page],
        queryFn: async () => (await listFn({ search: search || undefined, category: categoryFilter || undefined, page, page_size: pageSize })).data,
    });

    const items = data?.results || [];
    const totalCount = data?.count ?? items.length;
    const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

    const invalidate = () => {
        queryClient.invalidateQueries({ queryKey });
        queryClient.invalidateQueries({ queryKey: ['accounting-dashboard'] });
    };

    const saveMutation = useMutation({
        mutationFn: () => editingId ? updateFn(editingId, form, attachmentFile) : createFn(form, attachmentFile),
        onSuccess: () => {
            toast.success(editingId ? 'Updated' : 'Added');
            setModalOpen(false);
            invalidate();
        },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Failed to save')),
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => deleteFn(id),
        onSuccess: () => {
            toast.success('Deleted');
            invalidate();
        },
        onError: () => toast.error('Failed to delete'),
    });

    const openAdd = () => {
        setEditingId(null);
        setForm({ category: categories[0].value, description: '', amount: '', date: format(new Date(), 'yyyy-MM-dd'), notes: '' });
        setAttachmentFile(null);
        setExistingAttachmentUrl(null);
        setModalOpen(true);
    };

    const openEdit = (item: any) => {
        setEditingId(item.id);
        setForm({ category: item.category, description: item.description, amount: String(item.amount), date: item.date, notes: item.notes || '' });
        setAttachmentFile(null);
        setExistingAttachmentUrl(item.attachment || null);
        setModalOpen(true);
    };

    const categoryLabel = (value: string) => categories.find(c => c.value === value)?.label || value;

    return (
        <div>
            <div className="flex flex-wrap items-center gap-3 mb-4">
                <div className="relative flex-1 min-w-[200px]">
                    <input
                        type="text"
                        placeholder="Search description/notes..."
                        className="pl-10 pr-4 py-2 border rounded-lg w-full text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        value={search}
                        onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                    />
                    <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                </div>
                <select
                    value={categoryFilter}
                    onChange={(e) => { setCategoryFilter(e.target.value); setPage(1); }}
                    className="border rounded-lg px-3 py-2 text-sm"
                >
                    <option value="">All Categories</option>
                    {categories.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
                <button
                    onClick={openAdd}
                    className={`flex items-center gap-2 px-4 py-2 text-white rounded-lg text-sm font-medium ${accentClass}`}
                >
                    <Plus className="h-4 w-4" /> Add {kind === 'expense' ? 'Expense' : 'Income'}
                </button>
            </div>

            <div className="overflow-x-auto border rounded-lg">
                <table className="min-w-full divide-y divide-border">
                    <thead className="bg-secondary">
                        <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Date</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Category</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Description</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Amount</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Recorded By</th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-card divide-y divide-border">
                        {isLoading ? (
                            <tr><td colSpan={6} className="px-6 py-8 text-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin inline mr-2" />Loading...</td></tr>
                        ) : isError ? (
                            <tr><td colSpan={6} className="px-6 py-8 text-center text-red-500">Error: {(error as Error).message}</td></tr>
                        ) : items.length === 0 ? (
                            <tr><td colSpan={6} className="px-6 py-8 text-center text-muted-foreground">No records yet.</td></tr>
                        ) : (
                            items.map((item: any) => (
                                <tr key={item.id} className="hover:bg-secondary">
                                    <td className="px-4 py-3 text-sm text-muted-foreground whitespace-nowrap">{format(new Date(item.date), 'MMM d, yyyy')}</td>
                                    <td className="px-4 py-3 text-sm whitespace-nowrap">
                                        <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-foreground/80">{item.category_display || categoryLabel(item.category)}</span>
                                    </td>
                                    <td className="px-4 py-3 text-sm text-foreground">{item.description}</td>
                                    <td className="px-4 py-3 text-sm font-medium whitespace-nowrap">KES {Number(item.amount).toLocaleString()}</td>
                                    <td className="px-4 py-3 text-sm text-muted-foreground whitespace-nowrap">{item.recorded_by_username || '-'}</td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        <div className="flex gap-1">
                                            {item.attachment && (
                                                <a href={item.attachment} target="_blank" rel="noreferrer" className="flex items-center px-2 py-1 bg-gray-100 text-muted-foreground rounded text-xs hover:bg-gray-200" title="View attachment">
                                                    <Paperclip className="h-3 w-3" />
                                                </a>
                                            )}
                                            <button onClick={() => openEdit(item)} className="flex items-center px-2 py-1 bg-amber-500 text-white rounded text-xs hover:bg-amber-600">
                                                <Pencil className="h-3 w-3 mr-1" /> Edit
                                            </button>
                                            <button
                                                onClick={() => { if (confirm('Delete this record?')) deleteMutation.mutate(item.id); }}
                                                className="flex items-center px-2 py-1 bg-red-600 text-white rounded text-xs hover:bg-red-700"
                                            >
                                                <Trash2 className="h-3 w-3 mr-1" /> Delete
                                            </button>
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
                    <button disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))} className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-secondary">
                        <ChevronLeft className="h-4 w-4" /> Prev
                    </button>
                    <button disabled={page >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))} className="flex items-center px-3 py-1.5 border rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-secondary">
                        Next <ChevronRight className="h-4 w-4" />
                    </button>
                </div>
            </div>

            {modalOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-card rounded-xl shadow-xl w-full max-w-md">
                        <div className="flex justify-between items-center p-5 border-b">
                            <h3 className="text-lg font-bold">{editingId ? 'Edit' : 'Add'} {kind === 'expense' ? 'Expense' : 'Income'}</h3>
                            <button onClick={() => setModalOpen(false)} className="p-1 text-muted-foreground hover:text-muted-foreground"><X className="h-5 w-5" /></button>
                        </div>
                        <form
                            onSubmit={(e) => { e.preventDefault(); saveMutation.mutate(); }}
                            className="p-5 space-y-4"
                        >
                            <div>
                                <label className="block text-sm font-medium text-foreground/80 mb-1">Category</label>
                                <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                                    {categories.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-foreground/80 mb-1">Description</label>
                                <input required type="text" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-foreground/80 mb-1">Amount (KES)</label>
                                    <input required type="number" min="0" step="0.01" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-foreground/80 mb-1">Date</label>
                                    <input required type="date" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
                                </div>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-foreground/80 mb-1">Notes (optional)</label>
                                <textarea className="w-full border rounded-lg px-3 py-2 text-sm" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                            </div>
                            {kind === 'expense' && (
                                <AttachmentInput
                                    label="Receipt / Invoice (optional)"
                                    file={attachmentFile}
                                    onFileChange={setAttachmentFile}
                                    existingUrl={existingAttachmentUrl}
                                />
                            )}
                            <button
                                type="submit"
                                disabled={saveMutation.isPending}
                                className={`w-full flex items-center justify-center px-4 py-2 text-white rounded-lg font-medium disabled:opacity-50 ${accentClass}`}
                            >
                                {saveMutation.isPending ? 'Saving...' : editingId ? 'Save Changes' : 'Add Record'}
                            </button>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
