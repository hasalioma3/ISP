import { useState, useEffect } from 'react';
import { voucherAPI } from '../../services/api';
import toast from 'react-hot-toast';

interface Voucher {
    id: number;
    code: string;
    amount: string;
    status: 'active' | 'used' | 'expired';
}

interface VoucherBatch {
    id: number;
    created_at: string;
    quantity: number;
    value: string;
    note: string;
    generated_by_username: string;
    vouchers: Voucher[];
}

export default function VoucherManager() {
    const [batches, setBatches] = useState<VoucherBatch[]>([]);
    const [loading, setLoading] = useState(true);
    const [generating, setGenerating] = useState(false);

    // Form State
    const [quantity, setQuantity] = useState(10);
    const [value, setValue] = useState(50);
    const [note, setNote] = useState('');

    useEffect(() => {
        fetchBatches();
    }, []);

    const fetchBatches = async () => {
        try {
            const response = await voucherAPI.getBatches();
            setBatches(response.data);
        } catch (error) {
            toast.error('Failed to load vouchers');
        } finally {
            setLoading(false);
        }
    };

    const handleGenerate = async (e: React.FormEvent) => {
        e.preventDefault();
        setGenerating(true);
        try {
            await voucherAPI.generate({ quantity, value, note });
            toast.success('Vouchers generated successfully');
            setNote('');
            fetchBatches();
        } catch (error) {
            toast.error('Failed to generate vouchers');
        } finally {
            setGenerating(false);
        }
    };

    const handlePrint = (batch: VoucherBatch) => {
        const printWindow = window.open('', '_blank');
        if (!printWindow) return;

        const html = `
            <html>
            <head>
                <title>Print Vouchers - Batch #${batch.id}</title>
                <style>
                    body { font-family: monospace; padding: 20px; }
                    .voucher-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; }
                    .voucher-card { 
                        border: 1px dashed #000; 
                        padding: 15px; 
                        text-align: center; 
                        page-break-inside: avoid;
                    }
                    .amount { font-size: 1.2em; font-weight: bold; }
                    .code { font-size: 1.5em; letter-spacing: 2px; margin: 10px 0; font-weight: bold; }
                    @media print {
                        .no-print { display: none; }
                    }
                </style>
            </head>
            <body>
                <h2>Batch #${batch.id} - ${batch.quantity} x KES ${batch.value}</h2>
                <button class="no-print" onclick="window.print()">Print Now</button>
                <hr class="no-print" />
                <div class="voucher-grid">
                    ${batch.vouchers.map(v => `
                        <div class="voucher-card">
                            <div>ISP WIFI ACCESS</div>
                            <div class="amount">KES ${parseFloat(v.amount).toFixed(0)}</div>
                            <div class="code">${v.code.match(/.{1,4}/g)?.join(' ')}</div>
                            <div style="font-size: 0.8em">Dial *XXX* to redeem</div>
                        </div>
                    `).join('')}
                </div>
            </body>
            </html>
        `;

        printWindow.document.write(html);
        printWindow.document.close();
    };

    if (loading) return <div>Loading...</div>;

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">Voucher Manager</h1>

            {/* Generation Form */}
            <div className="bg-white p-6 rounded-lg shadow-md">
                <h2 className="text-lg font-semibold mb-4">Generate Vouchers</h2>
                <form onSubmit={handleGenerate} className="flex gap-4 items-end">
                    <div>
                        <label className="block text-sm font-medium mb-1">Quantity</label>
                        <input
                            type="number"
                            min="1" max="500"
                            value={quantity}
                            onChange={e => setQuantity(parseInt(e.target.value))}
                            className="w-full border rounded p-2"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium mb-1">Value (KES)</label>
                        <input
                            type="number"
                            min="1"
                            value={value}
                            onChange={e => setValue(parseInt(e.target.value))}
                            className="w-full border rounded p-2"
                        />
                    </div>
                    <div className="flex-1">
                        <label className="block text-sm font-medium mb-1">Note</label>
                        <input
                            type="text"
                            value={note}
                            onChange={e => setNote(e.target.value)}
                            placeholder="e.g. For Reseller A"
                            className="w-full border rounded p-2"
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={generating}
                        className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
                    >
                        {generating ? 'Generating...' : 'Generate and Save'}
                    </button>
                </form>
            </div>

            {/* Batch List */}
            <div className="bg-white rounded-lg shadow overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Batch ID</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created At</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Details</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Note</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {batches.map(batch => (
                            <tr key={batch.id}>
                                <td className="px-6 py-4 whitespace-nowrap">#{batch.id}</td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    {new Date(batch.created_at).toLocaleString()}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    {batch.quantity} x KES {batch.value}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">{batch.note}</td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <button
                                        onClick={() => handlePrint(batch)}
                                        className="text-indigo-600 hover:text-indigo-900"
                                    >
                                        Print
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
