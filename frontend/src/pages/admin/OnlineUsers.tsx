import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminAPI } from '../../services/api';
import { RefreshCw, Search, UserX, Edit2, Wifi, Share2, Network, Users as UsersIcon } from 'lucide-react';
import { format } from 'date-fns';
import toast from 'react-hot-toast';
import SubscriberDetailModal from '../../components/SubscriberDetailModal';

const TABS = [
    { key: 'all', label: 'All Online', icon: UsersIcon },
    { key: 'hotspot', label: 'Hotspot', icon: Wifi },
    { key: 'pppoe', label: 'PPPoE', icon: Share2 },
    { key: 'static', label: 'Static IP', icon: Network },
] as const;

export default function OnlineUsers() {
    const [urlParams] = useSearchParams();
    const initialTab = (urlParams.get('type') as typeof TABS[number]['key']) || 'all';
    const [tab, setTab] = useState<typeof TABS[number]['key']>(initialTab);
    const [search, setSearch] = useState('');
    const [selectedCustomerId, setSelectedCustomerId] = useState<number | null>(null);
    const queryClient = useQueryClient();

    const { data: users, isLoading, isFetching } = useQuery({
        queryKey: ['online-users', tab],
        queryFn: async () => {
            const res = await adminAPI.getOnlineUsers(tab === 'all' ? undefined : tab);
            return res.data;
        },
        refetchInterval: 30000,
    });

    const syncMutation = useMutation({
        mutationFn: adminAPI.syncOnlineUsers,
        onSuccess: () => {
            toast.success('Synced with routers');
            queryClient.invalidateQueries({ queryKey: ['online-users'] });
        },
        onError: () => toast.error('Sync failed')
    });

    const disconnectMutation = useMutation({
        mutationFn: (sessionId: number) => adminAPI.disconnectUser(sessionId),
        onSuccess: () => {
            toast.success('User disconnected');
            queryClient.invalidateQueries({ queryKey: ['online-users'] });
        },
        onError: (err: any) => toast.error(err.response?.data?.error || 'Failed to disconnect')
    });

    const filtered = (users || []).filter((u: any) =>
        !search || u.username.toLowerCase().includes(search.toLowerCase())
    );

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6">Online Users</h1>

            <div className="bg-card rounded-2xl shadow-sm border border-border overflow-hidden">
                <div className="bg-primary px-4 sm:px-6 py-4 flex flex-wrap gap-3 items-center justify-between">
                    <h3 className="text-white font-bold">Online Users</h3>
                    <button
                        onClick={() => syncMutation.mutate()}
                        disabled={syncMutation.isPending}
                        className="flex items-center gap-2 bg-white/95 hover:bg-white px-3 py-1.5 rounded-lg text-sm font-medium text-foreground/80 disabled:opacity-50"
                    >
                        <RefreshCw className={`h-4 w-4 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
                        Sync
                    </button>
                </div>

                <div className="flex border-b overflow-x-auto">
                    {TABS.map(t => (
                        <button
                            key={t.key}
                            onClick={() => setTab(t.key)}
                            className={`flex items-center shrink-0 px-4 sm:px-6 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${tab === t.key
                                ? 'border-ring text-primary bg-primary/10'
                                : 'border-transparent text-muted-foreground hover:text-foreground/80 hover:bg-secondary'
                                }`}
                        >
                            <t.icon className="h-4 w-4 mr-2" />
                            {t.label}
                        </button>
                    ))}
                </div>

                <div className="p-4 flex gap-2 border-b">
                    <div className="relative flex-1 max-w-sm">
                        <input
                            type="text"
                            placeholder="Search by username..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="w-full pl-9 pr-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-border">
                        <thead className="bg-secondary">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Username</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Plan Name</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Type</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Created On</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Expires On</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Method</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Router</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Status</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Manage</th>
                            </tr>
                        </thead>
                        <tbody className="bg-card divide-y divide-border">
                            {isLoading ? (
                                <tr><td colSpan={9} className="text-center py-8 text-muted-foreground">Loading...</td></tr>
                            ) : filtered.length === 0 ? (
                                <tr><td colSpan={9} className="text-center py-8 text-muted-foreground">No users currently online.</td></tr>
                            ) : filtered.map((u: any) => (
                                <tr key={u.session_id} className="hover:bg-secondary">
                                    <td className="px-6 py-4 text-sm font-medium text-primary">{u.username}</td>
                                    <td className="px-6 py-4 text-sm text-foreground">{u.plan_name}</td>
                                    <td className="px-6 py-4 text-sm uppercase text-muted-foreground">{u.type}</td>
                                    <td className="px-6 py-4 text-sm text-muted-foreground">
                                        {u.created_on ? format(new Date(u.created_on), 'd MMM yyyy HH:mm') : '-'}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-muted-foreground">
                                        {u.expires_on ? format(new Date(u.expires_on), 'd MMM yyyy HH:mm') : '-'}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-muted-foreground">{u.method}</td>
                                    <td className="px-6 py-4 text-sm text-muted-foreground">{u.router}</td>
                                    <td className="px-6 py-4">
                                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                            Online
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-right">
                                        <div className="flex justify-end gap-2">
                                            <button
                                                onClick={() => setSelectedCustomerId(u.customer_id)}
                                                title="Edit subscriber"
                                                className="p-1.5 text-amber-600 hover:bg-amber-50 rounded"
                                            >
                                                <Edit2 className="h-4 w-4" />
                                            </button>
                                            {u.type !== 'static' && (
                                                <button
                                                    onClick={() => {
                                                        if (confirm(`Disconnect ${u.username}?`)) {
                                                            disconnectMutation.mutate(u.session_id);
                                                        }
                                                    }}
                                                    title="Disconnect"
                                                    className="p-1.5 text-red-600 hover:bg-red-50 rounded"
                                                >
                                                    <UserX className="h-4 w-4" />
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                {isFetching && !isLoading && (
                    <div className="text-xs text-muted-foreground px-6 py-2">Refreshing...</div>
                )}
            </div>

            {selectedCustomerId !== null && (
                <SubscriberDetailModal id={selectedCustomerId} onClose={() => setSelectedCustomerId(null)} />
            )}
        </div>
    );
}
