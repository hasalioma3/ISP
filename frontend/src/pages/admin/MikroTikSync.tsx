import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminAPI } from '../../services/api';
import { toast } from 'react-hot-toast';
import { Loader2, Router as RouterIcon, ShieldCheck, ShieldAlert, Plus, Pencil, Trash2, X, Wifi } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';

type ActionKey = 'backup' | 'sync_profiles' | 'sync_users';

const ACTIONS: { key: ActionKey; label: string; description: string; className: string }[] = [
    {
        key: 'backup',
        label: 'Backup Config',
        description: 'Read-only snapshot of what provisioning would touch. Makes no changes.',
        className: 'bg-gray-600 hover:bg-gray-700',
    },
    {
        key: 'sync_profiles',
        label: 'Sync Profiles',
        description: 'Push all Billing Plans to this router as PPPoE/Hotspot profiles.',
        className: 'bg-indigo-600 hover:bg-indigo-700',
    },
    {
        key: 'sync_users',
        label: 'Sync Users',
        description: 'Push all active subscriptions to this router as secrets/users.',
        className: 'bg-green-600 hover:bg-green-700',
    },
];

const runAction = (id: number, key: ActionKey) => {
    switch (key) {
        case 'backup': return adminAPI.backupRouter(id);
        case 'sync_profiles': return adminAPI.syncRouterProfiles(id);
        case 'sync_users': return adminAPI.syncRouterUsers(id);
    }
};

const DEFAULT_PORTAL_URL = import.meta.env.VITE_DEFAULT_PORTAL_URL || '';

const emptyForm = {
    name: '',
    ip_address: '',
    username: '',
    password: '',
    port: 8728,
    use_ssl: false,
    hotspot_subnet: '10.5.50.0/24',
    pppoe_subnet: '10.5.60.0/24',
    dns_servers: '8.8.8.8,8.8.4.4',
    portal_url: DEFAULT_PORTAL_URL,
    location: '',
    notes: '',
    is_active: true,
};

export default function MikroTikSync() {
    const user = useAuthStore((state) => state.user);
    const canManage = !!user?.is_superuser || user?.role === 'admin';
    const visibleActions = canManage ? ACTIONS : ACTIONS.filter((a) => a.key !== 'backup');
    const [loadingKey, setLoadingKey] = useState<string | null>(null);
    const [logsByRouter, setLogsByRouter] = useState<Record<number, string[]>>({});

    // Add/Edit Router modal
    const [formOpen, setFormOpen] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [formData, setFormData] = useState<typeof emptyForm>(emptyForm);
    const [formSaving, setFormSaving] = useState(false);
    const [testResult, setTestResult] = useState<any[] | null>(null);
    const [testLoading, setTestLoading] = useState(false);
    const [testError, setTestError] = useState<string | null>(null);

    // Provision credentials modal
    const [provisionRouter, setProvisionRouter] = useState<any | null>(null);
    const [provisionUsername, setProvisionUsername] = useState('');
    const [provisionPassword, setProvisionPassword] = useState('');
    const [provisionPortalUrl, setProvisionPortalUrl] = useState('');
    const [provisionSubmitting, setProvisionSubmitting] = useState(false);

    const { data: routers, isLoading, isError, refetch } = useQuery({
        queryKey: ['admin-routers'],
        queryFn: async () => {
            const res = await adminAPI.getRouters();
            return res.data.results || res.data;
        },
    });

    const applyResult = (routerId: number, data: any, label: string) => {
        const { success, failed, error, snapshot } = data;
        if (error) {
            toast.error(error);
            setLogsByRouter((prev) => ({ ...prev, [routerId]: [`Error: ${error}`] }));
        } else if (snapshot) {
            toast.success('Snapshot captured');
            setLogsByRouter((prev) => ({
                ...prev,
                [routerId]: [`Snapshot captured with ${Object.keys(snapshot).length} resource types recorded.`],
            }));
        } else {
            const newLogs = [
                ...(success ?? []).map((msg: string) => `Success: ${msg}`),
                ...(failed ?? []).map((msg: string) => `Failed: ${msg}`),
            ];
            setLogsByRouter((prev) => ({ ...prev, [routerId]: newLogs }));
            if (!failed || failed.length === 0) {
                toast.success(`${label} completed successfully`);
            } else {
                toast.error(`${label} completed with ${failed.length} error(s)`);
            }
        }
    };

    const handleAction = async (routerId: number, action: ActionKey) => {
        const loadingId = `${routerId}-${action}`;
        setLoadingKey(loadingId);
        try {
            const response = await runAction(routerId, action);
            applyResult(routerId, response.data, action);
            refetch();
        } catch (err: any) {
            const message = err.response?.data?.error || `Failed to run ${action}`;
            toast.error(message);
            setLogsByRouter((prev) => ({ ...prev, [routerId]: [`System Error: ${message}`] }));
        } finally {
            setLoadingKey(null);
        }
    };

    const openCreateForm = () => {
        setEditingId(null);
        setFormData(emptyForm);
        setTestResult(null);
        setTestError(null);
        setFormOpen(true);
    };

    const openEditForm = (router: any) => {
        setEditingId(router.id);
        setFormData({
            name: router.name ?? '',
            ip_address: router.ip_address ?? '',
            username: router.username ?? '',
            password: '',
            port: router.port ?? 8728,
            use_ssl: router.use_ssl ?? false,
            hotspot_subnet: router.hotspot_subnet ?? '10.5.50.0/24',
            pppoe_subnet: router.pppoe_subnet ?? '10.5.60.0/24',
            dns_servers: router.dns_servers ?? '8.8.8.8,8.8.4.4',
            portal_url: router.portal_url ?? DEFAULT_PORTAL_URL,
            location: router.location ?? '',
            notes: router.notes ?? '',
            is_active: router.is_active ?? true,
        });
        setTestResult(null);
        setTestError(null);
        setFormOpen(true);
    };

    const closeForm = () => setFormOpen(false);

    const handleTestConnection = async () => {
        if (!formData.ip_address || !formData.username || !formData.password) {
            toast.error('IP address, username and password are required to test the connection.');
            return;
        }
        setTestLoading(true);
        setTestResult(null);
        setTestError(null);
        try {
            const res = await adminAPI.testRouterConnection({
                ip_address: formData.ip_address,
                username: formData.username,
                password: formData.password,
                port: formData.port,
                use_ssl: formData.use_ssl,
            });
            setTestResult(res.data.interfaces);
        } catch (err: any) {
            setTestError(err.response?.data?.error || 'Connection failed');
        } finally {
            setTestLoading(false);
        }
    };

    const handleFormSubmit = async () => {
        setFormSaving(true);
        try {
            const payload: any = { ...formData };
            if (editingId && !payload.password) {
                delete payload.password; // keep existing password on edit if left blank
            }
            if (editingId) {
                await adminAPI.updateRouter(editingId, payload);
                toast.success('Router updated');
            } else {
                await adminAPI.createRouter(payload);
                toast.success('Router added');
            }
            setFormOpen(false);
            refetch();
        } catch (err: any) {
            const data = err.response?.data;
            const message = typeof data === 'object' ? Object.values(data).flat().join(' ') : 'Failed to save router';
            toast.error(message || 'Failed to save router');
        } finally {
            setFormSaving(false);
        }
    };

    const handleDelete = async (router: any) => {
        if (!window.confirm(`Delete router "${router.name}"? This only removes it from the app, not from the router itself.`)) return;
        try {
            await adminAPI.deleteRouter(router.id);
            toast.success('Router deleted');
            refetch();
        } catch (err: any) {
            toast.error(err.response?.data?.error || 'Failed to delete router');
        }
    };

    const openProvisionModal = (router: any) => {
        setProvisionRouter(router);
        setProvisionUsername(router.username ?? '');
        setProvisionPassword('');
        setProvisionPortalUrl(router.portal_url ?? DEFAULT_PORTAL_URL);
    };

    const closeProvisionModal = () => setProvisionRouter(null);

    const submitProvision = async () => {
        if (!provisionRouter) return;
        if (!provisionUsername || !provisionPassword) {
            toast.error('Username and password are required to provision.');
            return;
        }
        setProvisionSubmitting(true);
        try {
            const response = await adminAPI.provisionRouter(provisionRouter.id, provisionUsername, provisionPassword, provisionPortalUrl);
            applyResult(provisionRouter.id, response.data, 'provision');
            refetch();
            setProvisionRouter(null);
        } catch (err: any) {
            const message = err.response?.data?.error || 'Failed to provision router';
            toast.error(message);
            setLogsByRouter((prev) => ({ ...prev, [provisionRouter.id]: [`System Error: ${message}`] }));
        } finally {
            setProvisionSubmitting(false);
        }
    };

    return (
        <div className="max-w-5xl mx-auto">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
                <h1 className="text-2xl font-bold">MikroTik Routers</h1>
                {canManage && (
                    <button
                        onClick={openCreateForm}
                        className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium py-2 px-4 rounded"
                    >
                        <Plus className="h-4 w-4" /> Add Router
                    </button>
                )}
            </div>

            {isLoading ? (
                <div className="flex justify-center items-center py-16 text-gray-500">
                    <Loader2 className="h-6 w-6 animate-spin mr-2" />
                    Loading routers...
                </div>
            ) : isError ? (
                <div className="text-center py-16 text-red-500">Failed to load routers.</div>
            ) : routers?.length === 0 ? (
                <div className="text-center py-16 text-gray-500">
                    No routers configured yet. Click "Add Router" to get started.
                </div>
            ) : (
                <div className="space-y-6">
                    {routers?.map((router: any) => (
                        <div key={router.id} className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                                <div className="flex items-center gap-3">
                                    <RouterIcon className="h-6 w-6 text-gray-400" />
                                    <div>
                                        <h2 className="text-lg font-semibold">{router.name}</h2>
                                        <p className="text-sm text-gray-500">{router.ip_address}</p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2 text-sm">
                                    {router.provisioned ? (
                                        <span className="flex items-center gap-1 text-green-600 bg-green-50 px-3 py-1 rounded-full">
                                            <ShieldCheck className="h-4 w-4" /> Provisioned
                                        </span>
                                    ) : (
                                        <span className="flex items-center gap-1 text-amber-600 bg-amber-50 px-3 py-1 rounded-full">
                                            <ShieldAlert className="h-4 w-4" /> Not provisioned
                                        </span>
                                    )}
                                    {canManage && (
                                        <>
                                            <button onClick={() => openEditForm(router)} title="Edit" className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg">
                                                <Pencil className="h-4 w-4" />
                                            </button>
                                            <button onClick={() => handleDelete(router)} title="Delete" className="p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded-lg">
                                                <Trash2 className="h-4 w-4" />
                                            </button>
                                        </>
                                    )}
                                </div>
                            </div>

                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
                                {canManage && (
                                    <button
                                        title="Full bootstrap: IP pools, DHCP, NAT, Hotspot server + profile, PPPoE server, walled garden, plan profiles. Asks for router login each time."
                                        onClick={() => openProvisionModal(router)}
                                        disabled={loadingKey !== null}
                                        className="py-2 px-3 rounded text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-700"
                                    >
                                        Provision
                                    </button>
                                )}
                                {visibleActions.map((a) => {
                                    const key = `${router.id}-${a.key}`;
                                    const isLoading = loadingKey === key;
                                    return (
                                        <button
                                            key={a.key}
                                            title={a.description}
                                            onClick={() => handleAction(router.id, a.key)}
                                            disabled={loadingKey !== null}
                                            className={`py-2 px-3 rounded text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${a.className}`}
                                        >
                                            {isLoading ? 'Running...' : a.label}
                                        </button>
                                    );
                                })}
                            </div>

                            {logsByRouter[router.id]?.length > 0 && (
                                <div className="bg-gray-900 text-gray-100 p-4 rounded-lg shadow-inner max-h-64 overflow-y-auto">
                                    <div className="space-y-1 font-mono text-xs">
                                        {logsByRouter[router.id].map((log, index) => (
                                            <div key={index} className={log.startsWith('Failed') || log.startsWith('Error') || log.startsWith('System Error') ? 'text-red-400' : 'text-green-400'}>
                                                {log}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* Add/Edit Router modal */}
            {formOpen && (
                <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
                        <div className="flex items-center justify-between p-5 border-b">
                            <h2 className="text-lg font-semibold">{editingId ? 'Edit Router' : 'Add Router'}</h2>
                            <button onClick={closeForm} className="p-1 text-gray-400 hover:text-gray-600">
                                <X className="h-5 w-5" />
                            </button>
                        </div>
                        <div className="p-5 space-y-4">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div className="sm:col-span-2">
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                                    <input className="w-full border rounded px-3 py-2 text-sm" value={formData.name}
                                        onChange={(e) => setFormData({ ...formData, name: e.target.value })} />
                                </div>
                                <div className="sm:col-span-2">
                                    <label className="block text-sm font-medium text-gray-700 mb-1">IP Address</label>
                                    <input className="w-full border rounded px-3 py-2 text-sm" value={formData.ip_address}
                                        onChange={(e) => setFormData({ ...formData, ip_address: e.target.value })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
                                    <input className="w-full border rounded px-3 py-2 text-sm" value={formData.username}
                                        onChange={(e) => setFormData({ ...formData, username: e.target.value })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">
                                        Password {editingId && <span className="text-gray-400 font-normal">(leave blank to keep)</span>}
                                    </label>
                                    <input type="password" className="w-full border rounded px-3 py-2 text-sm" value={formData.password}
                                        onChange={(e) => setFormData({ ...formData, password: e.target.value })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">API Port</label>
                                    <input type="number" className="w-full border rounded px-3 py-2 text-sm" value={formData.port}
                                        onChange={(e) => setFormData({ ...formData, port: Number(e.target.value) })} />
                                </div>
                                <div className="flex items-center gap-2 pt-6">
                                    <input type="checkbox" id="use_ssl" checked={formData.use_ssl}
                                        onChange={(e) => setFormData({ ...formData, use_ssl: e.target.checked })} />
                                    <label htmlFor="use_ssl" className="text-sm text-gray-700">Use SSL/TLS for API</label>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Hotspot Subnet</label>
                                    <input className="w-full border rounded px-3 py-2 text-sm" value={formData.hotspot_subnet}
                                        onChange={(e) => setFormData({ ...formData, hotspot_subnet: e.target.value })} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">PPPoE Subnet</label>
                                    <input className="w-full border rounded px-3 py-2 text-sm" value={formData.pppoe_subnet}
                                        onChange={(e) => setFormData({ ...formData, pppoe_subnet: e.target.value })} />
                                </div>
                                <div className="sm:col-span-2">
                                    <label className="block text-sm font-medium text-gray-700 mb-1">DNS Servers</label>
                                    <input className="w-full border rounded px-3 py-2 text-sm" value={formData.dns_servers}
                                        onChange={(e) => setFormData({ ...formData, dns_servers: e.target.value })} />
                                </div>
                                <div className="sm:col-span-2">
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Captive Portal URL</label>
                                    <input className="w-full border rounded px-3 py-2 text-sm" value={formData.portal_url}
                                        onChange={(e) => setFormData({ ...formData, portal_url: e.target.value })} />
                                    <p className="text-xs text-gray-500 mt-1">
                                        Where the router's Hotspot login page redirects unauthenticated clients.
                                    </p>
                                </div>
                                <div className="sm:col-span-2">
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Location</label>
                                    <input className="w-full border rounded px-3 py-2 text-sm" value={formData.location}
                                        onChange={(e) => setFormData({ ...formData, location: e.target.value })} />
                                </div>
                            </div>

                            <div className="border-t pt-4">
                                <button
                                    onClick={handleTestConnection}
                                    disabled={testLoading}
                                    className="flex items-center gap-2 text-sm font-medium text-blue-600 hover:text-blue-700 disabled:opacity-50"
                                >
                                    <Wifi className="h-4 w-4" /> {testLoading ? 'Testing connection...' : 'Test Connection & List Interfaces'}
                                </button>
                                <p className="text-xs text-gray-500 mt-1">
                                    Confirms the router is reachable with these credentials and shows real interface names,
                                    so you can check they match the server's configured provisioning interface before saving.
                                </p>
                                {testError && <p className="text-sm text-red-600 mt-2">{testError}</p>}
                                {testResult && (
                                    <div className="mt-2 bg-gray-50 border rounded p-3 text-xs font-mono max-h-32 overflow-y-auto">
                                        {testResult.length === 0 ? (
                                            <p className="text-gray-500">No interfaces returned.</p>
                                        ) : testResult.map((i: any) => (
                                            <div key={i.name}>
                                                {i.name} <span className="text-gray-400">({i.type}, {i.disabled ? 'disabled' : i.running ? 'running' : 'not running'})</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                        <div className="flex justify-end gap-3 p-5 border-t bg-gray-50 rounded-b-xl">
                            <button onClick={closeForm} className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded">
                                Cancel
                            </button>
                            <button
                                onClick={handleFormSubmit}
                                disabled={formSaving}
                                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded disabled:opacity-50"
                            >
                                {formSaving ? 'Saving...' : editingId ? 'Save Changes' : 'Add Router'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Provision credentials modal */}
            {provisionRouter && (
                <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-sm">
                        <div className="flex items-center justify-between p-5 border-b">
                            <h2 className="text-lg font-semibold">Provision "{provisionRouter.name}"</h2>
                            <button onClick={closeProvisionModal} className="p-1 text-gray-400 hover:text-gray-600">
                                <X className="h-5 w-5" />
                            </button>
                        </div>
                        <div className="p-5 space-y-4">
                            <p className="text-sm text-gray-600">
                                This writes real configuration to the router. Enter its current login to confirm before proceeding.
                            </p>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
                                <input className="w-full border rounded px-3 py-2 text-sm" value={provisionUsername}
                                    onChange={(e) => setProvisionUsername(e.target.value)} autoFocus />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
                                <input type="password" className="w-full border rounded px-3 py-2 text-sm" value={provisionPassword}
                                    onChange={(e) => setProvisionPassword(e.target.value)} />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Captive Portal URL</label>
                                <input className="w-full border rounded px-3 py-2 text-sm" value={provisionPortalUrl}
                                    onChange={(e) => setProvisionPortalUrl(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && submitProvision()} />
                                <p className="text-xs text-gray-500 mt-1">
                                    Written into the router's Hotspot login page as a redirect target.
                                </p>
                            </div>
                        </div>
                        <div className="flex justify-end gap-3 p-5 border-t bg-gray-50 rounded-b-xl">
                            <button onClick={closeProvisionModal} className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded">
                                Cancel
                            </button>
                            <button
                                onClick={submitProvision}
                                disabled={provisionSubmitting}
                                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded disabled:opacity-50"
                            >
                                {provisionSubmitting ? 'Provisioning...' : 'Provision'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
