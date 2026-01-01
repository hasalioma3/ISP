import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { voucherAPI, billingAPI } from '../../services/api';
import { Plus, Download, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { format } from 'date-fns';

export default function VoucherManager() {
    const [isGenerating, setIsGenerating] = useState(false);
    const [genParams, setGenParams] = useState({ quantity: 10, plan_id: '' });

    const queryClient = useQueryClient();

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

    const handleExport = (batch: any) => {
        if (!batch.vouchers || batch.vouchers.length === 0) {
            toast.error('No vouchers found in this batch');
            return;
        }

        const csvContent = [
            ['Code', 'Plan', 'Amount', 'Status', 'Expiry'],
            ...batch.vouchers.map((v: any) => [
                v.code,
                batch.plan_name || 'N/A',
                v.amount,
                v.status,
                v.expiry_date || 'Never'
            ])
        ].map(e => e.join(',')).join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `vouchers_batch_${batch.id}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    return (
        <div>
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold">Voucher Management</h1>
                <button
                    onClick={() => setIsGenerating(!isGenerating)}
                    className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
                >
                    <Plus className="h-4 w-4 mr-2" />
                    Generate Vouchers
                </button>
            </div>

            {isGenerating && (
                <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 mb-6 max-w-lg">
                    <h3 className="text-lg font-bold mb-4">Generate New Batch</h3>
                    <form onSubmit={handleGenerate} className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Quantity</label>
                                <input
                                    type="number"
                                    min="1" max="100"
                                    className="w-full border rounded-lg px-3 py-2"
                                    value={genParams.quantity}
                                    onChange={e => setGenParams({ ...genParams, quantity: parseInt(e.target.value) })}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Billing Plan</label>
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
                                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
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

            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Batch ID</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created Date</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Quantity</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Plan / Value</th>
                            <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {isLoading ? (
                            <tr><td colSpan={5} className="text-center py-8">Loading...</td></tr>
                        ) : isError ? (
                            <tr><td colSpan={5} className="text-center py-8 text-red-600">Error loading batches: {(error as Error).message}</td></tr>
                        ) : batches?.map((batch: any) => (
                            <tr key={batch.id} className="hover:bg-gray-50">
                                <td className="px-6 py-4 text-sm font-medium text-gray-900">#{batch.id}</td>
                                <td className="px-6 py-4 text-sm text-gray-500">
                                    {format(new Date(batch.created_at), 'MMM d, yyyy HH:mm')}
                                </td>
                                <td className="px-6 py-4 text-sm text-gray-900">{batch.quantity}</td>
                                <td className="px-6 py-4 text-sm font-medium text-gray-900">
                                    {batch.plan_name ? (
                                        <span className="text-blue-600 font-medium">{batch.plan_name}</span>
                                    ) : (
                                        <span className="text-green-600">KES {batch.value}</span>
                                    )}
                                </td>
                                <td className="px-6 py-4 text-right text-sm font-medium">
                                    <button
                                        onClick={() => handleExport(batch)}
                                        className="text-blue-600 hover:text-blue-900 flex items-center justify-end w-full"
                                    >
                                        <Download className="h-4 w-4 mr-1" /> Export
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
