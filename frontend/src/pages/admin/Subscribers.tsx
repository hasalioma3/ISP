import { Link } from 'react-router-dom';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminAPI } from '../../services/api';
import { Search, Loader2, ExternalLink } from 'lucide-react';
import { format } from 'date-fns';

export default function Subscribers() {
    const [searchTerm, setSearchTerm] = useState('');

    const { data: subscribers, isLoading, isError, error } = useQuery({
        queryKey: ['admin-subscribers', searchTerm],
        queryFn: async () => {
            console.log('Fetching subscribers with term:', searchTerm);
            try {
                const res = await adminAPI.getSubscribers(searchTerm);
                console.log('Subscribers res:', res);
                // Handle DRF pagination
                return res.data.results || res.data;
            } catch (err) {
                console.error('Subscribers fetch error:', err);
                throw err;
            }
        }
    });

    return (
        <div>
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
                <h1 className="text-2xl font-bold">Subscribers</h1>
                <div className="relative">
                    <input
                        type="text"
                        placeholder="Search users..."
                        className="pl-10 pr-4 py-2 border rounded-lg w-full sm:w-64 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                    />
                    <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
                </div>
            </div>

            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Service</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Calculated Expiry</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Balance</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {isLoading ? (
                                <tr>
                                    <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                                        <div className="flex justify-center items-center">
                                            <Loader2 className="h-6 w-6 animate-spin mr-2" />
                                            Loading subscribers...
                                        </div>
                                    </td>
                                </tr>
                            ) : isError ? (
                                <tr>
                                    <td colSpan={6} className="px-6 py-8 text-center text-red-500">
                                        Error loading subscribers: {(error as Error).message}
                                    </td>
                                </tr>
                            ) : subscribers?.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                                        No subscribers found.
                                    </td>
                                </tr>
                            ) : (
                                subscribers?.map((user: any) => (
                                    <tr key={user.id} className="hover:bg-gray-50 transition group">
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="flex items-center gap-2">
                                                <div>
                                                    <Link to={`/admin/subscribers/${user.id}`} className="text-sm font-medium text-blue-600 hover:text-blue-800 hover:underline">
                                                        {user.username}
                                                    </Link>
                                                    <div className="text-sm text-gray-500">{user.full_name}</div>
                                                    <div className="text-xs text-gray-400">{user.phone_number}</div>
                                                </div>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 uppercase">
                                                {user.service_type}
                                            </span>
                                            {user.pppoe_username && (
                                                <div className="text-xs text-gray-500 mt-1">PPPoE: {user.pppoe_username}</div>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                            {user.current_subscription?.expiry_date ? (
                                                <div className="flex flex-col">
                                                    <span>{format(new Date(user.current_subscription.expiry_date), 'MMM d, yyyy')}</span>
                                                    <span className="text-xs text-gray-400">{format(new Date(user.current_subscription.expiry_date), 'HH:mm')}</span>
                                                </div>
                                            ) : (
                                                <span className="text-gray-400">-</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                            KES {Number(user.account_balance).toLocaleString()}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize
                                                ${(user.current_subscription?.status === 'expired' || new Date(user.current_subscription?.expiry_date) < new Date()) ? 'bg-red-100 text-red-800' :
                                                    user.status === 'active' ? 'bg-green-100 text-green-800' :
                                                        user.status === 'expired' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800'}
                                            `}>
                                                {(user.current_subscription?.status === 'expired' || new Date(user.current_subscription?.expiry_date) < new Date()) ? 'expired' : user.status}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-right">
                                            <Link
                                                to={`/admin/subscribers/${user.id}`}
                                                className="text-gray-400 hover:text-blue-600 transition"
                                                title="View Details"
                                            >
                                                <ExternalLink className="w-5 h-5" />
                                            </Link>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
