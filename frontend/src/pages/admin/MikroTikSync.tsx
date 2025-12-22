import { useState } from 'react';
import api from '../../services/api';
import { toast } from 'react-hot-toast';

const MikroTikSync = () => {
    const [loading, setLoading] = useState(false);
    const [logs, setLogs] = useState<string[]>([]);

    const handleSync = async (action: 'sync_profiles' | 'sync_users') => {
        setLoading(true);
        setLogs([]);
        try {
            const response = await api.post('/network/sync/', { action });
            const { success, failed, error } = response.data;

            if (error) {
                toast.error(error);
                setLogs([`Error: ${error}`]);
            } else {
                const newLogs = [
                    ...success.map((msg: string) => `✅ Success: ${msg}`),
                    ...failed.map((msg: string) => `❌ Failed: ${msg}`)
                ];
                setLogs(newLogs);

                if (failed.length === 0) {
                    toast.success('Sync completed successfully');
                } else {
                    toast.error('Sync completed with errors');
                }
            }
        } catch (error) {
            toast.error('Failed to execute sync');
            console.error(error);
            setLogs(['❌ System Error: Failed to connect to server']);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="max-w-4xl mx-auto p-6">
            <h1 className="text-2xl font-bold mb-6">MikroTik Synchronization</h1>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                <div className="bg-white p-6 rounded-lg shadow-md">
                    <h2 className="text-xl font-semibold mb-4">Sync Profiles</h2>
                    <p className="text-gray-600 mb-4">
                        Push all Billing Plans to MikroTik as PPPoE/Hotspot Profiles.
                        This ensures speed limits are up to date.
                    </p>
                    <button
                        onClick={() => handleSync('sync_profiles')}
                        disabled={loading}
                        className={`w-full py-2 px-4 rounded text-white font-medium transition-colors
              ${loading ? 'bg-gray-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'}`}
                    >
                        {loading ? 'Syncing...' : 'Sync Profiles'}
                    </button>
                </div>

                <div className="bg-white p-6 rounded-lg shadow-md">
                    <h2 className="text-xl font-semibold mb-4">Sync Users</h2>
                    <p className="text-gray-600 mb-4">
                        Push all active Customer Subscriptions to MikroTik as Secrets (PPPoE) or Users (Hotspot).
                    </p>
                    <button
                        onClick={() => handleSync('sync_users')}
                        disabled={loading}
                        className={`w-full py-2 px-4 rounded text-white font-medium transition-colors
               ${loading ? 'bg-gray-400 cursor-not-allowed' : 'bg-green-600 hover:bg-green-700'}`}
                    >
                        {loading ? 'Syncing...' : 'Sync Users'}
                    </button>
                </div>
            </div>

            {logs.length > 0 && (
                <div className="bg-gray-900 text-gray-100 p-4 rounded-lg shadow-inner h-64 overflow-y-auto">
                    <h3 className="text-sm font-bold uppercase text-gray-400 mb-2">Sync Logs</h3>
                    <div className="space-y-1 font-mono text-sm">
                        {logs.map((log, index) => (
                            <div key={index} className={log.startsWith('✅') ? 'text-green-400' : 'text-red-400'}>
                                {log}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default MikroTikSync;
