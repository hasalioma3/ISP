import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { voucherAPI, billingAPI } from '../../services/api';
import { Plus, Eye, X, Copy, Send } from 'lucide-react';
import toast from 'react-hot-toast';
import { format } from 'date-fns';
import { getErrorMessage } from '../../utils/getErrorMessage';

export default function VoucherManager() {
    const [isGenerating, setIsGenerating] = useState(false);
    const [genParams, setGenParams] = useState({ quantity: 10, plan_id: '' });
    const [viewingBatch, setViewingBatch] = useState<any>(null);
    const [sendingVoucherId, setSendingVoucherId] = useState<number | null>(null);
    const [sendForm, setSendForm] = useState({ recipient: '', channel: 'sms' as 'sms' | 'whatsapp' | 'telegram' });

    const queryClient = useQueryClient();

    const sendMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: typeof sendForm }) => voucherAPI.send(id, data),
        onSuccess: () => {
            toast.success('Voucher code queued for delivery');
            setSendingVoucherId(null);
            setSendForm({ recipient: '', channel: 'sms' });
        },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Failed to send voucher')),
    });

    const { data: batches, isLoading, isError, error } = useQuery({
        queryKey: ['voucher-batches'],
        queryFn: async () => {
            const res = await voucherAPI.getBatches();
            return res.data.results || res.data;
        }
    });

    const { data: plans } = useQuery({
        queryKey: ['plans'],
        queryFn: async () => {
            const res = await billingAPI.getPlans();
            return res.data.results || res.data;
        }
    });

    const generateMutation = useMutation({
        mutationFn: voucherAPI.generate,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['voucher-batches'] });
            toast.success('Vouchers generated successfully');
            setIsGenerating(false);
            setGenParams({ quantity: 10, plan_id: '' });
        },
        onError: () => toast.error('Failed to generate vouchers')
    });

    const handleGenerate = (e: React.FormEvent) => {
        e.preventDefault();
        if (!genParams.plan_id) {
            toast.error('Please select a plan');
            return;
        }
        generateMutation.mutate(genParams);
    };

    const handleCopyAll = (batch: any) => {
        const codes = (batch.vouchers || []).map((v: any) => v.code).join('\n');
        navigator.clipboard.writeText(codes);
        toast.success('Codes copied to clipboard');
    };

    const handleCopyCode = (code: string) => {
        navigator.clipboard.writeText(code);
        toast.success('Code copied');
    };

    return (
        <div>
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 mb-6">
                <h1 className="text-2xl font-bold">Voucher Management</h1>
                <button
                    onClick={() => setIsGenerating(!isGenerating)}
                    className="flex items-center justify-center px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition"
                >
                    <Plus className="h-4 w-4 mr-2" />
                    Generate Vouchers
                </button>
            </div>

            {isGenerating && (
                <div className="bg-card p-6 rounded-xl shadow-sm border border-border mb-6 max-w-lg">
                    <h3 className="text-lg font-bold mb-4">Generate New Batch</h3>
                    <form onSubmit={handleGenerate} className="space-y-4">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-foreground/80 mb-1">Quantity</label>
                                <input
                                    type="number"
                                    min="1" max="100"
                                    className="w-full border rounded-lg px-3 py-2"
                                    value={genParams.quantity}
                                    onChange={e => setGenParams({ ...genParams, quantity: parseInt(e.target.value) })}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-foreground/80 mb-1">Billing Plan</label>
                                <select
                                    className="w-full border rounded-lg px-3 py-2"
                                    value={genParams.plan_id}
                                    onChange={e => setGenParams({ ...genParams, plan_id: e.target.value })}
                                    required
                                >
                                    <option value="">Select Plan...</option>
                                    {plans?.map((plan: any) => (
                                        <option key={plan.id} value={plan.id}>
                                            {plan.name} ({plan.price} KES)
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </div>
                        <div className="flex justify-end gap-2">
                            <button
                                type="button"
                                onClick={() => setIsGenerating(false)}
                                className="px-4 py-2 text-muted-foreground hover:bg-accent rounded-lg"
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                disabled={generateMutation.isPending}
                                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                            >
                                {generateMutation.isPending ? 'Generating...' : 'Confirm Generation'}
                            </button>
                        </div>
                    </form>
                </div>
            )}

            <div className="bg-card rounded-2xl shadow-sm border border-border overflow-x-auto">
                <table className="min-w-full divide-y divide-border">
                    <thead className="bg-secondary">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Batch ID</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Created Date</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Quantity</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Plan / Value</th>
                            <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-card divide-y divide-border">
                        {isLoading ? (
                            <tr><td colSpan={5} className="text-center py-8">Loading...</td></tr>
                        ) : isError ? (
                            <tr><td colSpan={5} className="text-center py-8 text-red-600">Error loading batches: {(error as Error).message}</td></tr>
                        ) : batches?.map((batch: any) => (
                            <tr key={batch.id} className="hover:bg-secondary">
                                <td className="px-6 py-4 text-sm font-medium text-foreground">#{batch.id}</td>
                                <td className="px-6 py-4 text-sm text-muted-foreground">
                                    {format(new Date(batch.created_at), 'MMM d, yyyy HH:mm')}
                                </td>
                                <td className="px-6 py-4 text-sm text-foreground">{batch.quantity}</td>
                                <td className="px-6 py-4 text-sm font-medium text-foreground">
                                    {batch.plan_name ? (
                                        <span className="text-primary font-medium">{batch.plan_name}</span>
                                    ) : (
                                        <span className="text-green-600">KES {batch.value}</span>
                                    )}
                                </td>
                                <td className="px-6 py-4 text-right text-sm font-medium">
                                    <button
                                        onClick={() => setViewingBatch(batch)}
                                        className="text-primary hover:text-primary flex items-center justify-end w-full"
                                    >
                                        <Eye className="h-4 w-4 mr-1" /> View Codes
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {viewingBatch && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-card rounded-xl shadow-xl w-full max-w-lg max-h-[80vh] flex flex-col">
                        <div className="flex justify-between items-center p-6 border-b">
                            <div>
                                <h3 className="text-lg font-bold">Batch #{viewingBatch.id} Codes</h3>
                                <p className="text-sm text-muted-foreground">
                                    {viewingBatch.plan_name || `KES ${viewingBatch.value}`} &middot; {viewingBatch.quantity} vouchers
                                </p>
                            </div>
                            <button onClick={() => setViewingBatch(null)} className="p-1 text-muted-foreground hover:text-muted-foreground">
                                <X className="h-5 w-5" />
                            </button>
                        </div>

                        <div className="overflow-y-auto flex-1 divide-y divide-border">
                            {(viewingBatch.vouchers || []).map((v: any) => (
                                <div key={v.id} className="px-6 py-3">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="font-mono font-medium text-foreground">{v.code}</p>
                                            <p className="text-xs text-muted-foreground">
                                                {v.expiry_date ? `Expires ${format(new Date(v.expiry_date), 'MMM d, yyyy')}` : 'No expiry'}
                                            </p>
                                        </div>
                                        <div className="flex items-center gap-3">
                                            <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize
                                                ${v.status === 'active' ? 'bg-green-100 text-green-800' :
                                                    v.status === 'used' ? 'bg-gray-100 text-muted-foreground' : 'bg-red-100 text-red-800'}`}>
                                                {v.status}
                                            </span>
                                            <button onClick={() => handleCopyCode(v.code)} className="text-muted-foreground hover:text-primary">
                                                <Copy className="h-4 w-4" />
                                            </button>
                                            {v.status === 'active' && (
                                                <button
                                                    onClick={() => setSendingVoucherId(sendingVoucherId === v.id ? null : v.id)}
                                                    className="text-muted-foreground hover:text-primary"
                                                    title="Send code to a customer"
                                                >
                                                    <Send className="h-4 w-4" />
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                    {sendingVoucherId === v.id && (
                                        <div className="mt-2 flex flex-col sm:flex-row gap-2 bg-secondary border rounded-lg p-2">
                                            <input
                                                type="text"
                                                placeholder="Phone or Telegram chat ID"
                                                className="flex-1 border rounded-lg px-2 py-1.5 text-sm"
                                                value={sendForm.recipient}
                                                onChange={e => setSendForm({ ...sendForm, recipient: e.target.value })}
                                            />
                                            <select
                                                className="border rounded-lg px-2 py-1.5 text-sm"
                                                value={sendForm.channel}
                                                onChange={e => setSendForm({ ...sendForm, channel: e.target.value as any })}
                                            >
                                                <option value="sms">SMS</option>
                                                <option value="whatsapp">WhatsApp</option>
                                                <option value="telegram">Telegram</option>
                                            </select>
                                            <button
                                                disabled={!sendForm.recipient || sendMutation.isPending}
                                                onClick={() => sendMutation.mutate({ id: v.id, data: sendForm })}
                                                className="px-3 py-1.5 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50 whitespace-nowrap"
                                            >
                                                {sendMutation.isPending ? 'Sending...' : 'Send'}
                                            </button>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>

                        <div className="p-4 border-t flex justify-end gap-2">
                            <button
                                onClick={() => handleCopyAll(viewingBatch)}
                                className="flex items-center px-4 py-2 bg-primary/10 text-primary rounded-lg hover:bg-primary/10 text-sm font-medium"
                            >
                                <Copy className="h-4 w-4 mr-2" /> Copy All Codes
                            </button>
                            <button
                                onClick={() => setViewingBatch(null)}
                                className="px-4 py-2 text-muted-foreground hover:bg-accent rounded-lg text-sm font-medium"
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
