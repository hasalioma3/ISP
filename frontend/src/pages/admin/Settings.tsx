import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { adminAPI, billingAPI } from '../../services/api';
import { Users as UsersIcon, CreditCard } from 'lucide-react';
import toast from 'react-hot-toast';

export default function Settings() {
    const [activeTab, setActiveTab] = useState('staff');

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6">System Settings</h1>

            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden min-h-[500px]">
                {/* Tabs */}
                <div className="flex border-b">
                    <button
                        onClick={() => setActiveTab('staff')}
                        className={`flex items-center px-6 py-4 text-sm font-medium border-b-2 transition-colors ${activeTab === 'staff'
                            ? 'border-blue-500 text-blue-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                            }`}
                    >
                        <UsersIcon className="h-4 w-4 mr-2" />
                        Staff
                    </button>
                    <button
                        onClick={() => setActiveTab('manual')}
                        className={`flex items-center px-6 py-4 text-sm font-medium border-b-2 transition-colors ${activeTab === 'manual'
                            ? 'border-blue-500 text-blue-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                            }`}
                    >
                        <CreditCard className="h-4 w-4 mr-2" />
                        Manual User
                    </button>
                </div>

                {/* Content */}
                <div className="p-6">
                    {activeTab === 'staff' && <StaffTab />}
                    {activeTab === 'manual' && <ManualUserTab />}
                </div>
            </div>
        </div>
    );
}

function StaffTab() {
    const { data: staff, isLoading } = useQuery({
        queryKey: ['staff'],
        queryFn: async () => {
            const res = await adminAPI.getStaff();
            return res.data.results || res.data;
        }
    });

    return (
        <div>
            <h3 className="text-lg font-bold mb-4">Staff Directory</h3>
            {isLoading && <p className="text-gray-500 text-center py-4">Loading...</p>}
            <div className="space-y-4">
                {staff?.map((user: any) => (
                    <div key={user.id} className="flex items-center justify-between p-4 border rounded-lg">
                        <div>
                            <p className="font-bold">{user.username}</p>
                            <p className="text-sm text-gray-500">{user.email || 'No email'}</p>
                        </div>
                        <div className="flex gap-2">
                            <span className="px-2 py-1 bg-gray-100 rounded text-xs">
                                {user.is_superuser ? 'Superuser' : 'Staff'}
                            </span>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function ManualUserTab() {
    const [formData, setFormData] = useState({ username: '', plan_id: '', password: '', phone_number: '' });
    const { data: plans } = useQuery({
        queryKey: ['plans'],
        queryFn: async () => {
            const res = await billingAPI.getPlans();
            return res.data.results || res.data;
        }
    });

    const createMutation = useMutation({
        mutationFn: adminAPI.manualSubscribe,
        onSuccess: () => {
            toast.success('User activated successfully');
            setFormData({ username: '', plan_id: '', password: '', phone_number: '' });
        },
        onError: (err: any) => {
            toast.error('Failed to create user');
        }
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        createMutation.mutate(formData);
    };

    return (
        <div className="max-w-md">
            <h3 className="text-lg font-bold mb-4">Manual Subscription Activation</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
                    <input
                        type="text"
                        required
                        className="w-full border rounded-lg px-3 py-2"
                        value={formData.username}
                        onChange={e => setFormData({ ...formData, username: e.target.value })}
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
                    <input
                        type="password"
                        required
                        className="w-full border rounded-lg px-3 py-2"
                        value={formData.password}
                        onChange={e => setFormData({ ...formData, password: e.target.value })}
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Phone (Optional)</label>
                    <input
                        type="text"
                        className="w-full border rounded-lg px-3 py-2"
                        value={formData.phone_number}
                        onChange={e => setFormData({ ...formData, phone_number: e.target.value })}
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Plan</label>
                    <select
                        required
                        className="w-full border rounded-lg px-3 py-2"
                        value={formData.plan_id}
                        onChange={e => setFormData({ ...formData, plan_id: e.target.value })}
                    >
                        <option value="">Select a plan...</option>
                        {plans?.map((plan: any) => (
                            <option key={plan.id} value={plan.id}>{plan.name} - KES {plan.price}</option>
                        ))}
                    </select>
                </div>
                <button
                    type="submit"
                    disabled={createMutation.isPending}
                    className="w-full py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                >
                    {createMutation.isPending ? 'Activating...' : 'Create & Activate'}
                </button>
            </form>
        </div>
    );
}
