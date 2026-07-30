import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { billingAPI, adminAPI } from '../../services/api';
import { Plus, Pencil, Trash2, X, Package } from 'lucide-react';
import toast from 'react-hot-toast';

const emptyForm = {
    name: '', description: '', service_type: 'pppoe',
    download_speed: 5, upload_speed: 5, price: '', currency: 'KES',
    duration_value: 30, duration_unit: 'days',
    data_limit_gb: '', mikrotik_profile: '', is_active: true, routers: [] as number[],
};

export default function BillingPlans() {
    const queryClient = useQueryClient();
    const [isFormOpen, setIsFormOpen] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form, setForm] = useState<any>(emptyForm);

    const { data: plans, isLoading, isError } = useQuery({
        queryKey: ['billing-plans'],
        queryFn: async () => {
            const res = await billingAPI.getPlans();
            return res.data.results || res.data;
        }
    });

    const { data: routers } = useQuery({
        queryKey: ['routers'],
        queryFn: async () => {
            const res = await adminAPI.getRouters();
            return res.data.results || res.data;
        }
    });

    const resetForm = () => {
        setForm(emptyForm);
        setEditingId(null);
        setIsFormOpen(false);
    };

    const createMutation = useMutation({
        mutationFn: (data: any) => billingAPI.createPlan(data),
        onSuccess: () => {
            toast.success('Plan created');
            queryClient.invalidateQueries({ queryKey: ['billing-plans'] });
            resetForm();
        },
        onError: (err: any) => toast.error(formatError(err) || 'Failed to create plan')
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: any }) => billingAPI.updatePlan(id, data),
        onSuccess: () => {
            toast.success('Plan updated');
            queryClient.invalidateQueries({ queryKey: ['billing-plans'] });
            resetForm();
        },
        onError: (err: any) => toast.error(formatError(err) || 'Failed to update plan')
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => billingAPI.deletePlan(id),
        onSuccess: () => {
            toast.success('Plan deleted');
            queryClient.invalidateQueries({ queryKey: ['billing-plans'] });
        },
        onError: (err: any) => toast.error(formatError(err) || 'Failed to delete plan')
    });

    const openEdit = (plan: any) => {
        setForm({
            name: plan.name, description: plan.description || '', service_type: plan.service_type,
            download_speed: plan.download_speed, upload_speed: plan.upload_speed, price: plan.price,
            currency: plan.currency, duration_value: plan.duration_value, duration_unit: plan.duration_unit,
            data_limit_gb: plan.data_limit_gb ?? '', mikrotik_profile: plan.mikrotik_profile,
            is_active: plan.is_active, routers: plan.routers || [],
        });
        setEditingId(plan.id);
        setIsFormOpen(true);
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const payload = { ...form, data_limit_gb: form.data_limit_gb === '' ? null : form.data_limit_gb };
        if (editingId) {
            updateMutation.mutate({ id: editingId, data: payload });
        } else {
            createMutation.mutate(payload);
        }
    };

    const toggleRouter = (id: number) => {
        setForm((f: any) => ({
            ...f,
            routers: f.routers.includes(id) ? f.routers.filter((r: number) => r !== id) : [...f.routers, id],
        }));
    };

    return (
        <div>
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold">Billing Plans</h1>
                <button
                    onClick={() => { resetForm(); setIsFormOpen(true); }}
                    className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
                >
                    <Plus className="h-4 w-4 mr-2" /> Add Plan
                </button>
            </div>

            {isFormOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
                        <div className="flex justify-between items-center p-5 border-b">
                            <h2 className="text-lg font-semibold">{editingId ? 'Edit Plan' : 'Add Plan'}</h2>
                            <button onClick={resetForm} className="p-1 text-gray-400 hover:text-gray-600">
                                <X className="h-5 w-5" />
                            </button>
                        </div>
                        <form onSubmit={handleSubmit} className="p-5 space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div className="col-span-2">
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                                    <input required className="w-full border rounded-lg px-3 py-2 text-sm" value={form.name}
                                        onChange={e => setForm({ ...form, name: e.target.value })} />
                                </div>
                                <div className="col-span-2">
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                                    <textarea className="w-full border rounded-lg px-3 py-2 text-sm" rows={2} value={form.description}
                                        onChange={e => setForm({ ...form, description: e.target.value })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Service Type</label>
                                    <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.service_type}
                                        onChange={e => setForm({ ...form, service_type: e.target.value })}>
                                        <option value="pppoe">PPPoE</option>
                                        <option value="hotspot">Hotspot</option>
                                        <option value="static">Static IP</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">MikroTik Profile Name</label>
                                    <input required className="w-full border rounded-lg px-3 py-2 text-sm" value={form.mikrotik_profile}
                                        onChange={e => setForm({ ...form, mikrotik_profile: e.target.value })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Download (Mbps)</label>
                                    <input type="number" required min={1} className="w-full border rounded-lg px-3 py-2 text-sm" value={form.download_speed}
                                        onChange={e => setForm({ ...form, download_speed: Number(e.target.value) })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Upload (Mbps)</label>
                                    <input type="number" required min={1} className="w-full border rounded-lg px-3 py-2 text-sm" value={form.upload_speed}
                                        onChange={e => setForm({ ...form, upload_speed: Number(e.target.value) })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Price (KES)</label>
                                    <input type="number" required min={0} step="0.01" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.price}
                                        onChange={e => setForm({ ...form, price: e.target.value })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Data Limit (GB, blank=unlimited)</label>
                                    <input type="number" min={0} className="w-full border rounded-lg px-3 py-2 text-sm" value={form.data_limit_gb}
                                        onChange={e => setForm({ ...form, data_limit_gb: e.target.value })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Duration</label>
                                    <input type="number" required min={1} className="w-full border rounded-lg px-3 py-2 text-sm" value={form.duration_value}
                                        onChange={e => setForm({ ...form, duration_value: Number(e.target.value) })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Duration Unit</label>
                                    <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.duration_unit}
                                        onChange={e => setForm({ ...form, duration_unit: e.target.value })}>
                                        <option value="minutes">Minutes</option>
                                        <option value="hours">Hours</option>
                                        <option value="days">Days</option>
                                        <option value="months">Months</option>
                                    </select>
                                </div>
                                <div className="col-span-2">
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Apply to Routers (blank = all active routers)</label>
                                    <div className="flex flex-wrap gap-2">
                                        {routers?.map((r: any) => (
                                            <label key={r.id} className={`flex items-center px-3 py-1.5 rounded-lg border text-sm cursor-pointer ${form.routers.includes(r.id) ? 'bg-blue-50 border-blue-400 text-blue-700' : 'border-gray-300 text-gray-600'
                                                }`}>
                                                <input type="checkbox" className="mr-2" checked={form.routers.includes(r.id)}
                                                    onChange={() => toggleRouter(r.id)} />
                                                {r.name}
                                            </label>
                                        ))}
                                    </div>
                                </div>
                                <div className="col-span-2 flex items-center gap-2">
                                    <input type="checkbox" id="is_active" checked={form.is_active}
                                        onChange={e => setForm({ ...form, is_active: e.target.checked })} />
                                    <label htmlFor="is_active" className="text-sm text-gray-700">Active (visible to customers)</label>
                                </div>
                            </div>
                            <div className="flex justify-end gap-3 pt-2 border-t">
                                <button type="button" onClick={resetForm} className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg">
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={createMutation.isPending || updateMutation.isPending}
                                    className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50"
                                >
                                    {editingId ? 'Save Changes' : 'Create Plan'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Plan</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Speed</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Price</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Duration</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {isLoading ? (
                                <tr><td colSpan={7} className="text-center py-8 text-gray-500">Loading...</td></tr>
                            ) : isError ? (
                                <tr><td colSpan={7} className="text-center py-8 text-red-600">Failed to load plans.</td></tr>
                            ) : plans?.length === 0 ? (
                                <tr><td colSpan={7} className="text-center py-8 text-gray-500">No plans yet.</td></tr>
                            ) : plans?.map((plan: any) => (
                                <tr key={plan.id} className="hover:bg-gray-50">
                                    <td className="px-6 py-4">
                                        <div className="flex items-center">
                                            <Package className="h-4 w-4 text-gray-400 mr-2" />
                                            <div>
                                                <p className="text-sm font-medium text-gray-900">{plan.name}</p>
                                                <p className="text-xs text-gray-500">{plan.mikrotik_profile}</p>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4">
                                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 uppercase">
                                            {plan.service_type}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-500">{plan.download_speed}/{plan.upload_speed} Mbps</td>
                                    <td className="px-6 py-4 text-sm font-medium text-gray-900">KES {Number(plan.price).toLocaleString()}</td>
                                    <td className="px-6 py-4 text-sm text-gray-500">{plan.duration_value} {plan.duration_unit}</td>
                                    <td className="px-6 py-4">
                                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${plan.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
                                            }`}>
                                            {plan.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-right">
                                        <div className="flex justify-end gap-2">
                                            <button onClick={() => openEdit(plan)} className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg">
                                                <Pencil className="h-4 w-4" />
                                            </button>
                                            <button
                                                onClick={() => { if (confirm(`Delete plan "${plan.name}"?`)) deleteMutation.mutate(plan.id); }}
                                                className="p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded-lg"
                                            >
                                                <Trash2 className="h-4 w-4" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}

function formatError(err: any): string | null {
    const data = err?.response?.data;
    if (!data) return null;
    if (typeof data === 'string') return data;
    if (data.error) return data.error;
    const first = Object.values(data).flat()[0];
    return typeof first === 'string' ? first : null;
}
