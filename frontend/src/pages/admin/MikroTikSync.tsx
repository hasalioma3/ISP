import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminAPI } from '../../services/api';
import { toast } from 'react-hot-toast';
import { Loader2, Router as RouterIcon, ShieldCheck, ShieldAlert } from 'lucide-react';

type ActionKey = 'provision' | 'backup' | 'sync_profiles' | 'sync_users';

const ACTIONS: { key: ActionKey; label: string; description: string; className: string }[] = [
    {
        key: 'provision',
        label: 'Provision',
        description: 'Full bootstrap: IP pools, DHCP, NAT, Hotspot server + profile, PPPoE server, walled garden, plan profiles.',
        className: 'bg-blue-600 hover:bg-blue-700',
    },
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
        case 'provision': return adminAPI.provisionRouter(id);
        case 'backup': return adminAPI.backupRouter(id);
        case 'sync_profiles': return adminAPI.syncRouterProfiles(id);
        case 'sync_users': return adminAPI.syncRouterUsers(id);
    }
};

export default function MikroTikSync() {
    const [loadingKey, setLoadingKey] = useState<string | null>(null);
    const [logsByRouter, setLogsByRouter] = useState<Record<number, string[]>>({});

    const { data: routers, isLoading, isError, refetch } = useQuery({
        queryKey: ['admin-routers'],
        queryFn: async () => {
            const res = await adminAPI.getRouters();
            return res.data.results || res.data;
        },
    });

    const handleAction = async (routerId: number, action: ActionKey) => {
        const loadingId = `${routerId}-${action}`;
        setLoadingKey(loadingId);
        try {
            const response = await runAction(routerId, action);
            const { success, failed, error, snapshot } = response.data;

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
                    toast.success(`${action} completed successfully`);
                } else {
                    toast.error(`${action} completed with ${failed.length} error(s)`);
                }
            }
            refetch();
        } catch (err: any) {
            const message = err.response?.data?.error || `Failed to run ${action}`;
            toast.error(message);
            setLogsByRouter((prev) => ({ ...prev, [routerId]: [`System Error: ${message}`] }));
        } finally {
            setLoadingKey(null);
        }
    };

    return (
        <div className="max-w-5xl mx-auto">
            <h1 className="text-2xl font-bold mb-6">MikroTik Routers</h1>

            {isLoading ? (
                <div className="flex justify-center items-center py-16 text-gray-500">
                    <Loader2 className="h-6 w-6 animate-spin mr-2" />
                    Loading routers...
                </div>
            ) : isError ? (
                <div className="text-center py-16 text-red-500">Failed to load routers.</div>
            ) : routers?.length === 0 ? (
                <div className="text-center py-16 text-gray-500">
                    No routers configured yet. Add one under Routers in Django admin.
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
                                </div>
                            </div>

                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
                                {ACTIONS.map((a) => {
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
        </div>
    );
}
