import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminAPI, billingAPI } from '../../services/api';
import { Plus, Trash2, Edit2, UserPlus, Server, Users as UsersIcon, CreditCard, X } from 'lucide-react';
import toast from 'react-hot-toast';

import { coreAPI } from '../../services/api'; // Add coreAPI import
import { Settings as SettingsIcon } from 'lucide-react'; // Add SettingsIcon import

export default function Settings() {
    const [activeTab, setActiveTab] = useState('config'); // Default to config

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6">System Settings</h1>

            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden min-h-[500px]">
                {/* Tabs */}
                <div className="flex border-b">
                    <button
                        onClick={() => setActiveTab('config')}
                        className={`flex items-center px-6 py-4 text-sm font-medium border-b-2 transition-colors ${activeTab === 'config'
                            ? 'border-blue-500 text-blue-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                            }`}
                    >
                        <SettingsIcon className="h-4 w-4 mr-2" />
                        Configuration
                    </button>
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
                    <button
                        onClick={() => setActiveTab('plans')}
                        className={`flex items-center px-6 py-4 text-sm font-medium border-b-2 transition-colors ${activeTab === 'plans'
                            ? 'border-blue-500 text-blue-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                            }`}
                    >
                        <CreditCard className="h-4 w-4 mr-2" />
                        Billing Plans
                    </button>
                </div>

                {/* Content */}
                <div className="p-6">
                    {activeTab === 'config' && <ConfigurationTab />}
                    {activeTab === 'routers' && <RoutersTab />}
                    {activeTab === 'staff' && <StaffTab />}
                    {activeTab === 'manual' && <ManualUserTab />}
                    {activeTab === 'plans' && <PlansTab />}
                </div>
            </div>
        </div>
    );
}




function ConfigurationTab() {
    const queryClient = useQueryClient();
    const [logoFile, setLogoFile] = useState<File | null>(null);
    const [favFile, setFavFile] = useState<File | null>(null);

    const { data: config, isLoading } = useQuery({
        queryKey: ['tenantConfig'],
        queryFn: async () => {
            const res = await coreAPI.getConfig();
            return res.data;
        }
    });

    const [formData, setFormData] = useState({
        company_name: '',
        primary_color: '#000000',
        mpesa_consumer_key: '',
        mpesa_consumer_secret: '',
        mpesa_shortcode: '',
        mpesa_passkey: '',
        mpesa_environment: 'sandbox'
    });

    // Load initial data
    if (config && !formData.company_name && !isLoading) {
        setFormData({
            company_name: config.company_name,
            primary_color: config.primary_color,
            mpesa_consumer_key: config.mpesa_consumer_key,
            mpesa_consumer_secret: config.mpesa_consumer_secret,
            mpesa_shortcode: config.mpesa_shortcode,
            mpesa_passkey: config.mpesa_passkey,
            mpesa_environment: config.mpesa_environment
        });
    }

    const mutation = useMutation({
        mutationFn: async (e: React.FormEvent) => {
            e.preventDefault();
            const data = new FormData();
            Object.entries(formData).forEach(([key, value]) => {
                data.append(key, value);
            });
            if (logoFile) data.append('logo', logoFile);
            if (favFile) data.append('favicon', favFile);
            return coreAPI.updateConfig(data);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tenantConfig'] });
            toast.success('Configuration saved! Refresh to see branding changes.');
        },
        onError: (err: any) => {
            toast.error('Failed to save configuration');
        }
    });

    if (isLoading) return <div>Loading configuration...</div>;

    return (
        <form onSubmit={(e) => mutation.mutate(e)} className="max-w-4xl space-y-8">
            {/* Branding Section */}
            <div>
                <h3 className="text-lg font-bold mb-4 border-b pb-2">Branding</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                        <label className="block text-sm font-medium text-gray-700">Company Name</label>
                        <input
                            type="text"
                            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2"
                            value={formData.company_name}
                            onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700">Primary Color</label>
                        <div className="flex items-center gap-2 mt-1">
                            <input
                                type="color"
                                className="h-10 w-20 p-1 rounded border"
                                value={formData.primary_color}
                                onChange={(e) => setFormData({ ...formData, primary_color: e.target.value })}
                            />
                            <span className="text-sm text-gray-500">{formData.primary_color}</span>
                        </div>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700">Logo</label>
                        <input
                            type="file"
                            accept="image/*"
                            className="mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                            onChange={(e) => e.target.files && setLogoFile(e.target.files[0])}
                        />
                        {config?.logo && <p className="text-xs text-gray-500 mt-1">Current: <a href={config.logo} target="_blank" className="text-blue-600 underline">View Logo</a></p>}
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700">Favicon</label>
                        <input
                            type="file"
                            accept="image/*"
                            className="mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                            onChange={(e) => e.target.files && setFavFile(e.target.files[0])}
                        />
                        {config?.favicon && <p className="text-xs text-gray-500 mt-1">Current: <a href={config.favicon} target="_blank" className="text-blue-600 underline">View Favicon</a></p>}
                    </div>
                </div>
            </div>

            {/* M-Pesa Section */}
            <div>
                <h3 className="text-lg font-bold mb-4 border-b pb-2">M-Pesa Integration</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                        <label className="block text-sm font-medium text-gray-700">Environment</label>
                        <select
                            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2"
                            value={formData.mpesa_environment}
                            onChange={(e) => setFormData({ ...formData, mpesa_environment: e.target.value })}
                        >
                            <option value="sandbox">Sandbox</option>
                            <option value="production">Production</option>
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700">Shortcode (Paybill/Till)</label>
                        <input
                            type="text"
                            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2"
                            value={formData.mpesa_shortcode}
                            onChange={(e) => setFormData({ ...formData, mpesa_shortcode: e.target.value })}
                        />
                    </div>
                    <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700">Consumer Key</label>
                        <input
                            type="text"
                            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2"
                            value={formData.mpesa_consumer_key}
                            onChange={(e) => setFormData({ ...formData, mpesa_consumer_key: e.target.value })}
                        />
                    </div>
                    <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700">Consumer Secret</label>
                        <input
                            type="password"
                            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2"
                            value={formData.mpesa_consumer_secret}
                            onChange={(e) => setFormData({ ...formData, mpesa_consumer_secret: e.target.value })}
                        />
                    </div>
                    <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700">Passkey (Stk Push)</label>
                        <textarea
                            rows={3}
                            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2"
                            value={formData.mpesa_passkey}
                            onChange={(e) => setFormData({ ...formData, mpesa_passkey: e.target.value })}
                        />
                    </div>
                </div>
            </div>

            <div className="flex justify-end pt-4">
                <button
                    type="submit"
                    disabled={mutation.isPending}
                    className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
                >
                    {mutation.isPending ? 'Saving...' : 'Save Configuration'}
                </button>
            </div>
        </form>
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
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [formData, setFormData] = useState({
        username: '',
        email: '',
        password: '',
        is_staff: true,
        is_superuser: false
    });

    const { data: staff, isLoading } = useQuery({
        queryKey: ['staff'],
        queryFn: async () => {
            const res = await adminAPI.getStaff();
            return res.data.results || res.data;
        }
    });

    const createMutation = useMutation({
        mutationFn: adminAPI.createStaff,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['staff'] });
            toast.success('Staff member created');
            setIsModalOpen(false);
            setFormData({ username: '', email: '', password: '', is_staff: true, is_superuser: false });
        },
        onError: (err: any) => {
            toast.error(err.response?.data?.error || 'Failed to create staff');
        }
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        createMutation.mutate(formData);
    };

    return (
        <div>
            <div className="flex justify-between mb-4">
                <h3 className="text-lg font-bold">Staff Directory</h3>
                <button
                    onClick={() => setIsModalOpen(true)}
                    className="flex items-center px-3 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
                >
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
                            <span className={`px-2 py-1 rounded text-xs ${user.is_superuser ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-700'}`}>
                                {user.is_superuser ? 'Superuser' : 'Staff'}
                            </span>
                        </div>
                    </div>
                ))}
            </div>

            {isModalOpen && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-lg p-6 w-full max-w-md">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-bold">Add Staff Member</h3>
                            <button onClick={() => setIsModalOpen(false)}><X className="h-5 w-5" /></button>
                        </div>
                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium">Username</label>
                                <input type="text" required className="w-full border rounded p-2"
                                    value={formData.username} onChange={e => setFormData({ ...formData, username: e.target.value })} />
                            </div>
                            <div>
                                <label className="block text-sm font-medium">Email</label>
                                <input type="email" required className="w-full border rounded p-2"
                                    value={formData.email} onChange={e => setFormData({ ...formData, email: e.target.value })} />
                            </div>
                            <div>
                                <label className="block text-sm font-medium">Password</label>
                                <input type="password" required className="w-full border rounded p-2"
                                    value={formData.password} onChange={e => setFormData({ ...formData, password: e.target.value })} />
                            </div>
                            <div className="flex items-center gap-4">
                                <label className="flex items-center">
                                    <input type="checkbox" className="mr-2"
                                        checked={formData.is_superuser}
                                        onChange={e => setFormData({ ...formData, is_superuser: e.target.checked })} />
                                    Superuser Access
                                </label>
                            </div>
                            <button type="submit" disabled={createMutation.isPending} className="w-full bg-blue-600 text-white py-2 rounded">
                                {createMutation.isPending ? 'Creating...' : 'Create Staff'}
                            </button>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}

function PlansTab() {
    const queryClient = useQueryClient();
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingPlan, setEditingPlan] = useState<any>(null);
    const [formData, setFormData] = useState({
        name: '',
        price: 0,
        speed_limit_mbps: 5,
        service_type: 'pppoe',
        duration_days: 30,
        description: '',
        is_active: true
    });

    const { data: plans } = useQuery({
        queryKey: ['plans'],
        queryFn: async () => {
            const res = await billingAPI.getPlans();
            return res.data.results || res.data;
        }
    });

    const createMutation = useMutation({
        mutationFn: billingAPI.createPlan,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['plans'] });
            toast.success('Plan created');
            resetForm();
        },
        onError: (err: any) => toast.error('Failed to create plan')
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: any) => billingAPI.updatePlan(id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['plans'] });
            toast.success('Plan updated');
            resetForm();
        },
        onError: (err: any) => toast.error('Failed to update plan')
    });

    const deleteMutation = useMutation({
        mutationFn: billingAPI.deletePlan,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['plans'] });
            toast.success('Plan deleted');
        },
        onError: (err: any) => toast.error('Failed to delete plan')
    });

    const resetForm = () => {
        setFormData({ name: '', price: 0, speed_limit_mbps: 5, service_type: 'pppoe', duration_days: 30, description: '', is_active: true });
        setEditingPlan(null);
        setIsModalOpen(false);
    };

    const handleEdit = (plan: any) => {
        setEditingPlan(plan);
        setFormData({
            name: plan.name,
            price: plan.price,
            speed_limit_mbps: plan.speed_limit_mbps,
            service_type: plan.service_type,
            duration_days: plan.duration_days,
            description: plan.description || '',
            is_active: plan.is_active
        });
        setIsModalOpen(true);
    };

    return (
        <div>
            <div className="flex justify-between mb-4">
                <h3 className="text-lg font-bold">Billing Plans</h3>
                <button
                    onClick={() => { resetForm(); setIsModalOpen(true); }}
                    className="flex items-center px-3 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
                >
                    <Plus className="h-4 w-4 mr-2" /> Add Plan
                </button>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {plans?.map((plan: any) => (
                    <div key={plan.id} className="border rounded-lg p-5 hover:shadow-md transition-shadow">
                        <div className="flex justify-between items-start mb-2">
                            <h4 className="font-bold text-lg">{plan.name}</h4>
                            <span className="bg-green-100 text-green-700 px-2 py-1 rounded text-xs">
                                KES {plan.price}
                            </span>
                        </div>
                        <p className="text-gray-600 text-sm mb-4">{plan.description}</p>
                        <ul className="text-sm text-gray-500 space-y-1 mb-4">
                            <li>Speed: {plan.speed_limit_mbps} Mbps</li>
                            <li>Type: {plan.service_type.toUpperCase()}</li>
                            <li>Duration: {plan.duration_days} Days</li>
                        </ul>
                        <div className="flex justify-end gap-2 pt-2 border-t mt-2">
                            <button onClick={() => deleteMutation.mutate(plan.id)} className="p-2 text-red-500 hover:bg-red-50 rounded"><Trash2 className="h-4 w-4" /></button>
                            <button onClick={() => handleEdit(plan)} className="p-2 text-blue-500 hover:bg-blue-50 rounded"><Edit2 className="h-4 w-4" /></button>
                        </div>
                    </div>
                ))}
            </div>

            {isModalOpen && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-lg p-6 w-full max-w-lg">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-bold">{editingPlan ? 'Edit Plan' : 'New Plan'}</h3>
                            <button onClick={resetForm}><X className="h-5 w-5" /></button>
                        </div>
                        <form onSubmit={(e) => {
                            e.preventDefault();
                            if (editingPlan) updateMutation.mutate({ id: editingPlan.id, data: formData });
                            else createMutation.mutate(formData);
                        }} className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium">Plan Name</label>
                                    <input type="text" required className="w-full border rounded p-2"
                                        value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium">Price (KES)</label>
                                    <input type="number" required className="w-full border rounded p-2"
                                        value={formData.price} onChange={e => setFormData({ ...formData, price: parseFloat(e.target.value) })} />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium">Speed (Mbps)</label>
                                    <input type="number" required className="w-full border rounded p-2"
                                        value={formData.speed_limit_mbps} onChange={e => setFormData({ ...formData, speed_limit_mbps: parseInt(e.target.value) })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium">Duration (Days)</label>
                                    <input type="number" required className="w-full border rounded p-2"
                                        value={formData.duration_days} onChange={e => setFormData({ ...formData, duration_days: parseInt(e.target.value) })} />
                                </div>
                            </div>
                            <div>
                                <label className="block text-sm font-medium">Service Type</label>
                                <select className="w-full border rounded p-2"
                                    value={formData.service_type} onChange={e => setFormData({ ...formData, service_type: e.target.value })}>
                                    <option value="pppoe">PPPoE</option>
                                    <option value="hotspot">Hotspot</option>
                                    <option value="static">Static IP</option>
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium">Description</label>
                                <textarea className="w-full border rounded p-2" rows={2}
                                    value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} />
                            </div>
                            <button type="submit" disabled={createMutation.isPending || updateMutation.isPending} className="w-full bg-blue-600 text-white py-2 rounded">
                                {createMutation.isPending || updateMutation.isPending ? 'Saving...' : 'Save Plan'}
                            </button>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}

function ManualUserTab() {
    // ... (Keep existing ManualUserTab implementation, but I need to include it here or it will be lost if I replace the block poorly)
    // The instructions say "Replace StaffTab and ManualUserTab".
    // I will include ManualUserTab content below to ensure it's not lost.
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
