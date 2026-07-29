import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminAPI, billingAPI } from '../services/api';
import { X, Save, PlusCircle } from 'lucide-react';
import { format } from 'date-fns';
import toast from 'react-hot-toast';
import UsageChartPanels from './UsageChartPanels';

export default function SubscriberDetailModal({ id, onClose }: { id: number; onClose: () => void }) {
    const [tab, setTab] = useState<'details' | 'usage' | 'plans'>('details');
    const [form, setForm] = useState<any | null>(null);
    const [topUpPlanId, setTopUpPlanId] = useState('');
    const queryClient = useQueryClient();

    const { data: subscriber, isLoading } = useQuery({
        queryKey: ['subscriber', id],
        queryFn: async () => {
            const res = await adminAPI.getSubscriber(id);
            if (!form) setForm(res.data);
            return res.data;
        }
    });

    const { data: usageData, isLoading: usageLoading } = useQuery({
        queryKey: ['subscriber-usage', id],
        queryFn: async () => {
            const res = await adminAPI.getSubscriberUsage(id);
            return res.data;
        },
        enabled: tab === 'usage' || tab === 'plans'
    });

    const { data: plans } = useQuery({
        queryKey: ['plans'],
        queryFn: async () => {
            const res = await billingAPI.getPlans();
            return res.data.results || res.data;
        }
    });

    const saveMutation = useMutation({
        mutationFn: (data: any) => adminAPI.updateSubscriber(id, data),
        onSuccess: () => {
            toast.success('Subscriber updated');
            queryClient.invalidateQueries({ queryKey: ['admin-subscribers'] });
            queryClient.invalidateQueries({ queryKey: ['subscriber', id] });
            queryClient.invalidateQueries({ queryKey: ['online-users'] });
        },
        onError: () => toast.error('Failed to update subscriber')
    });

    const topUpMutation = useMutation({
        mutationFn: () => adminAPI.topUpSubscriber(id, parseInt(topUpPlanId)),
        onSuccess: (res) => {
            toast.success(res.data.message || 'Plan assigned');
            setTopUpPlanId('');
            queryClient.invalidateQueries({ queryKey: ['admin-subscribers'] });
            queryClient.invalidateQueries({ queryKey: ['subscriber', id] });
            queryClient.invalidateQueries({ queryKey: ['subscriber-usage', id] });
            queryClient.invalidateQueries({ queryKey: ['online-users'] });
        },
        onError: (err: any) => toast.error(err.response?.data?.error || 'Failed to assign plan')
    });

    const handleSave = (e: React.FormEvent) => {
        e.preventDefault();
        const { username, email, phone_number, first_name, last_name, service_type, address, id_number, notes } = form;
        saveMutation.mutate({ username, email, phone_number, first_name, last_name, service_type, address, id_number, notes });
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-4xl max-h-[85vh] flex flex-col">
                <div className="flex justify-between items-center p-6 border-b">
                    <div>
                        <h3 className="text-lg font-bold">{subscriber?.full_name || subscriber?.username || 'Subscriber'}</h3>
                        <p className="text-sm text-gray-500">{subscriber?.username} &middot; {subscriber?.phone_number}</p>
                    </div>
                    <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600">
                        <X className="h-5 w-5" />
                    </button>
                </div>

                <div className="flex border-b px-6">
                    {(['details', 'usage', 'plans'] as const).map(t => (
                        <button
                            key={t}
                            onClick={() => setTab(t)}
                            className={`px-4 py-3 text-sm font-medium border-b-2 capitalize transition-colors ${tab === t
                                ? 'border-blue-500 text-blue-600'
                                : 'border-transparent text-gray-500 hover:text-gray-700'
                                }`}
                        >
                            {t === 'plans' ? 'Plans & Top-up' : t}
                        </button>
                    ))}
                </div>

                <div className="overflow-y-auto flex-1 p-6">
                    {isLoading || !form ? (
                        <div className="text-center py-8 text-gray-500">Loading...</div>
                    ) : tab === 'details' ? (
                        <form onSubmit={handleSave} className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <Field label="First Name" value={form.first_name} onChange={v => setForm({ ...form, first_name: v })} />
                                <Field label="Last Name" value={form.last_name} onChange={v => setForm({ ...form, last_name: v })} />
                                <Field label="Username" value={form.username} onChange={v => setForm({ ...form, username: v })} />
                                <Field label="Email" value={form.email} onChange={v => setForm({ ...form, email: v })} />
                                <Field label="Phone Number" value={form.phone_number} onChange={v => setForm({ ...form, phone_number: v })} />
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Service Type</label>
                                    <select
                                        className="w-full border rounded-lg px-3 py-2"
                                        value={form.service_type}
                                        onChange={e => setForm({ ...form, service_type: e.target.value })}
                                    >
                                        <option value="pppoe">PPPoE</option>
                                        <option value="hotspot">Hotspot</option>
                                        <option value="both">Both</option>
                                    </select>
                                </div>
                                <Field label="ID Number" value={form.id_number} onChange={v => setForm({ ...form, id_number: v })} />
                                <Field label="Address" value={form.address} onChange={v => setForm({ ...form, address: v })} />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                                <textarea
                                    className="w-full border rounded-lg px-3 py-2"
                                    rows={3}
                                    value={form.notes || ''}
                                    onChange={e => setForm({ ...form, notes: e.target.value })}
                                />
                            </div>
                            <button
                                type="submit"
                                disabled={saveMutation.isPending}
                                className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                            >
                                <Save className="h-4 w-4 mr-2" />
                                {saveMutation.isPending ? 'Saving...' : 'Save Changes'}
                            </button>
                        </form>
                    ) : tab === 'usage' ? (
                        usageLoading ? (
                            <div className="text-center py-8 text-gray-500">Loading usage...</div>
                        ) : (
                            <div>
                                <div className="mb-6">
                                    <UsageChartPanels chart={usageData?.chart} loading={false} />
                                </div>
                                <div className="grid grid-cols-3 gap-4 mb-6">
                                    <div className="bg-gray-50 rounded-lg p-4 text-center">
                                        <p className="text-xs text-gray-500 uppercase">All-Time Upload</p>
                                        <p className="text-xl font-bold">{usageData?.totals.upload_gb} GB</p>
                                    </div>
                                    <div className="bg-gray-50 rounded-lg p-4 text-center">
                                        <p className="text-xs text-gray-500 uppercase">All-Time Download</p>
                                        <p className="text-xl font-bold">{usageData?.totals.download_gb} GB</p>
                                    </div>
                                    <div className="bg-gray-50 rounded-lg p-4 text-center">
                                        <p className="text-xs text-gray-500 uppercase">All-Time Total</p>
                                        <p className="text-xl font-bold">{usageData?.totals.total_gb} GB</p>
                                    </div>
                                </div>
                                <h4 className="text-sm font-bold mb-2">Session History</h4>
                                <table className="min-w-full divide-y divide-gray-200 text-sm">
                                    <thead>
                                        <tr className="text-left text-xs text-gray-500 uppercase">
                                            <th className="py-2">Date</th>
                                            <th className="py-2">IP</th>
                                            <th className="py-2 text-right">Up (GB)</th>
                                            <th className="py-2 text-right">Down (GB)</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100">
                                        {usageData?.usage_records?.length === 0 ? (
                                            <tr><td colSpan={4} className="py-6 text-center text-gray-400">No usage recorded yet.</td></tr>
                                        ) : usageData?.usage_records?.map((u: any) => (
                                            <tr key={u.id}>
                                                <td className="py-2">{format(new Date(u.created_at), 'MMM d, yyyy HH:mm')}</td>
                                                <td className="py-2 text-gray-500">{u.framed_ip_address || '-'}</td>
                                                <td className="py-2 text-right">{(u.upload_bytes / (1024 ** 3)).toFixed(2)}</td>
                                                <td className="py-2 text-right">{(u.download_bytes / (1024 ** 3)).toFixed(2)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )
                    ) : (
                        <div className="space-y-6">
                            <div className="bg-gray-50 rounded-lg p-4">
                                <h4 className="text-sm font-bold mb-3">Assign / Top Up Plan</h4>
                                <div className="flex gap-2">
                                    <select
                                        className="flex-1 border rounded-lg px-3 py-2 text-sm"
                                        value={topUpPlanId}
                                        onChange={e => setTopUpPlanId(e.target.value)}
                                    >
                                        <option value="">Select a plan...</option>
                                        {plans?.map((plan: any) => (
                                            <option key={plan.id} value={plan.id}>{plan.name} - KES {plan.price}</option>
                                        ))}
                                    </select>
                                    <button
                                        disabled={!topUpPlanId || topUpMutation.isPending}
                                        onClick={() => topUpMutation.mutate()}
                                        className="flex items-center px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium"
                                    >
                                        <PlusCircle className="h-4 w-4 mr-2" />
                                        {topUpMutation.isPending ? 'Assigning...' : 'Confirm'}
                                    </button>
                                </div>
                            </div>

                            <div>
                                <h4 className="text-sm font-bold mb-2">Subscription History</h4>
                                <table className="min-w-full divide-y divide-gray-200 text-sm">
                                    <thead>
                                        <tr className="text-left text-xs text-gray-500 uppercase">
                                            <th className="py-2">Plan</th>
                                            <th className="py-2">Status</th>
                                            <th className="py-2">Expiry</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100">
                                        {usageData?.subscriptions?.length === 0 ? (
                                            <tr><td colSpan={3} className="py-4 text-center text-gray-400">No subscriptions yet.</td></tr>
                                        ) : usageData?.subscriptions?.map((s: any) => (
                                            <tr key={s.id}>
                                                <td className="py-2 font-medium">{s.plan?.name}</td>
                                                <td className="py-2 capitalize">{s.status}</td>
                                                <td className="py-2 text-gray-500">{format(new Date(s.expiry_date), 'MMM d, yyyy')}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>

                            <div>
                                <h4 className="text-sm font-bold mb-2">Recent Transactions</h4>
                                <table className="min-w-full divide-y divide-gray-200 text-sm">
                                    <thead>
                                        <tr className="text-left text-xs text-gray-500 uppercase">
                                            <th className="py-2">Amount</th>
                                            <th className="py-2">Method</th>
                                            <th className="py-2">M-Pesa Code</th>
                                            <th className="py-2">Status</th>
                                            <th className="py-2">Date</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100">
                                        {usageData?.transactions?.length === 0 ? (
                                            <tr><td colSpan={5} className="py-4 text-center text-gray-400">No transactions yet.</td></tr>
                                        ) : usageData?.transactions?.map((t: any) => (
                                            <tr key={t.id}>
                                                <td className="py-2 font-medium">KES {Number(t.amount).toLocaleString()}</td>
                                                <td className="py-2 uppercase">{t.payment_method}</td>
                                                <td className="py-2 font-mono text-xs">{t.mpesa_receipt_number || '-'}</td>
                                                <td className="py-2 capitalize">{t.status}</td>
                                                <td className="py-2 text-gray-500">{format(new Date(t.created_at), 'MMM d, yyyy')}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
    return (
        <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
            <input
                type="text"
                className="w-full border rounded-lg px-3 py-2"
                value={value || ''}
                onChange={e => onChange(e.target.value)}
            />
        </div>
    );
}
