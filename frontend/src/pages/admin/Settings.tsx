import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminAPI, billingAPI } from '../../services/api';
import { Plus, Trash2, Edit2, UserPlus, Server, Users as UsersIcon, CreditCard, X } from 'lucide-react';
import toast from 'react-hot-toast';

export default function Settings() {
    const [activeTab, setActiveTab] = useState('routers');

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6">System Settings</h1>

            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden min-h-[500px]">
                {/* Tabs */}
                <div className="flex border-b">
                    <button
                        onClick={() => setActiveTab('routers')}
                        className={`flex items-center px-6 py-4 text-sm font-medium border-b-2 transition-colors ${activeTab === 'routers'
                            ? 'border-blue-500 text-blue-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                            }`}
                    >
                        <Server className="h-4 w-4 mr-2" />
                        Routers
                    </button>
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
                    {activeTab === 'routers' && <RoutersTab />}
                    {activeTab === 'staff' && <StaffTab />}
                    {activeTab === 'manual' && <ManualUserTab />}
                </div>
            </div>
        </div>
    );
}

function RoutersTab() {
    const queryClient = useQueryClient();
    const { data: routers, isLoading, isError, error } = useQuery({
        queryKey: ['routers'],
        queryFn: async () => {
            const res = await adminAPI.getRouters();
            return res.data.results || res.data;
        }
    });

    const deleteMutation = useMutation({
        mutationFn: adminAPI.deleteRouter,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['routers'] });
            toast.success('Router deleted');
        }
    });

    const [isModalOpen, setIsModalOpen] = useState(false);
    const [newRouter, setNewRouter] = useState({
        name: '',
        ip_address: '',
        username: '',
        password: '',
        port: 8728,
        use_ssl: false
    });

    const createMutation = useMutation({
        mutationFn: adminAPI.createRouter,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['routers'] });
            toast.success('Router added successfully');
            setIsModalOpen(false);
            setNewRouter({
                name: '',
                ip_address: '',
                username: '',
                password: '',
                port: 8728,
                use_ssl: false
            });
        },
        onError: (err: any) => {
            toast.error(err.response?.data?.error || 'Failed to add router');
        }
    });

    const handleCreate = (e: React.FormEvent) => {
        e.preventDefault();
        createMutation.mutate(newRouter);
    };



    if (isLoading) return <div className="p-4">Loading routers...</div>;
    if (isError) return <div className="p-4 text-red-600">Error loading routers: {(error as Error).message}</div>;

    return (
        <div>
            <div className="flex justify-between mb-4">
                <h3 className="text-lg font-bold">Network Routers</h3>
                <button
                    onClick={() => setIsModalOpen(true)}
                    className="flex items-center px-3 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
                >
                    <Plus className="h-4 w-4 mr-2" /> Add Router
                </button>
            </div>

            {/* Add Router Modal */}
            {isModalOpen && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center index-50 z-50">
                    <div className="bg-white rounded-lg p-6 w-full max-w-md">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-bold">Add Router</h3>
                            <button onClick={() => setIsModalOpen(false)} className="text-gray-500 hover:text-gray-700">
                                <X className="h-5 w-5" />
                            </button>
                        </div>
                        <form onSubmit={handleCreate} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Name</label>
                                <input
                                    type="text"
                                    required
                                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 border p-2"
                                    value={newRouter.name}
                                    onChange={e => setNewRouter({ ...newRouter, name: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700">IP Address</label>
                                <input
                                    type="text"
                                    required
                                    placeholder="192.168.88.1"
                                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 border p-2"
                                    value={newRouter.ip_address}
                                    onChange={e => setNewRouter({ ...newRouter, ip_address: e.target.value })}
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700">Username</label>
                                    <input
                                        type="text"
                                        required
                                        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 border p-2"
                                        value={newRouter.username}
                                        onChange={e => setNewRouter({ ...newRouter, username: e.target.value })}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700">Password</label>
                                    <input
                                        type="password"
                                        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 border p-2"
                                        value={newRouter.password}
                                        onChange={e => setNewRouter({ ...newRouter, password: e.target.value })}
                                    />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700">Port (API)</label>
                                    <input
                                        type="number"
                                        required
                                        className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 border p-2"
                                        value={newRouter.port}
                                        onChange={e => setNewRouter({ ...newRouter, port: parseInt(e.target.value) })}
                                    />
                                </div>
                                <div className="flex items-center pt-6">
                                    <input
                                        type="checkbox"
                                        className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                                        checked={newRouter.use_ssl}
                                        onChange={e => setNewRouter({ ...newRouter, use_ssl: e.target.checked })}
                                    />
                                    <label className="ml-2 block text-sm text-gray-900">Use SSL</label>
                                </div>
                            </div>
                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    type="button"
                                    onClick={() => setIsModalOpen(false)}
                                    className="px-4 py-2 border rounded-md text-gray-700 hover:bg-gray-50"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={createMutation.isPending}
                                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                                >
                                    {createMutation.isPending ? 'Adding...' : 'Add Router'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Minimal Router List */}
            <div className="space-y-4">
                {routers?.length === 0 && <p className="text-gray-500 text-center py-4">No routers found.</p>}
                {routers?.map((router: any) => (
                    <RouterRow key={router.id} router={router} onDelete={() => deleteMutation.mutate(router.id)} />
                ))}
            </div>
        </div>
    );
}

function RouterRow({ router, onDelete }: { router: any; onDelete: () => void }) {
    const configureMutation = useMutation({
        mutationFn: adminAPI.configureRouter,
        onSuccess: (data) => {
            if (data.data.success) {
                toast.success(`Router ${data.data.router} configured successfully!`);
            } else {
                toast.error('Configuration finished with errors. Check console.');
                console.error(data.data.results);
            }
        },
        onError: (error: any) => {
            toast.error(`Failed to configure router: ${error.response?.data?.error || error.message}`);
        }
    });

    return (
        <div className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50">
            <div>
                <p className="font-bold">{router.name}</p>
                <p className="text-sm text-gray-500">{router.ip_address} ({router.username})</p>
            </div>
            <div className="flex gap-2">
                <button
                    onClick={onDelete}
                    className="p-2 text-red-600 hover:bg-red-50 rounded"
                >
                    <Trash2 className="h-4 w-4" />
                </button>
                <button
                    onClick={() => configureMutation.mutate(router.id)}
                    disabled={configureMutation.isPending}
                    className="px-3 py-1 bg-green-100 text-green-700 rounded text-sm hover:bg-green-200 disabled:opacity-50"
                >
                    {configureMutation.isPending ? 'Configuring...' : 'Configure'}
                </button>
            </div>
        </div>
    );
}


function StaffTab() {
    const queryClient = useQueryClient();
    const { data: staff, isLoading } = useQuery({
        queryKey: ['staff'],
        queryFn: async () => {
            const res = await adminAPI.getStaff();
            return res.data.results || res.data;
        }
    });

    // Placeholder for add staff logic (modal needed)

    return (
        <div>
            <div className="flex justify-between mb-4">
                <h3 className="text-lg font-bold">Staff Directory</h3>
                <button className="flex items-center px-3 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
                    <UserPlus className="h-4 w-4 mr-2" /> Add Staff
                </button>
            </div>
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
