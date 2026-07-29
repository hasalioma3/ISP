import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { adminAPI } from '../../services/api';
import { Search, Loader2, ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react';
import { format } from 'date-fns';
import SubscriberDetailModal from '../../components/SubscriberDetailModal';

type SortField = 'account_balance' | 'calculated_expiry';

export default function Subscribers() {
    const [urlParams] = useSearchParams();
    const [searchTerm, setSearchTerm] = useState(urlParams.get('search') || '');
    const [serviceFilter, setServiceFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [sortField, setSortField] = useState<SortField | ''>('');
    const [sortDesc, setSortDesc] = useState(true);
    const [selectedId, setSelectedId] = useState<number | null>(null);

    const { data: subscribers, isLoading, isError, error } = useQuery({
        queryKey: ['admin-subscribers', searchTerm, serviceFilter, statusFilter, sortField, sortDesc],
        queryFn: async () => {
            const res = await adminAPI.getSubscribers({
                search: searchTerm || undefined,
                service_type: serviceFilter || undefined,
                status: statusFilter || undefined,
                ordering: sortField ? `${sortDesc ? '-' : ''}${sortField}` : undefined,
            });
            return res.data.results || res.data;
        }
    });

    const toggleSort = (field: SortField) => {
        if (sortField === field) {
            setSortDesc(!sortDesc);
        } else {
            setSortField(field);
            setSortDesc(true);
        }
    };

    const SortIcon = ({ field }: { field: SortField }) => {
        if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 text-gray-300" />;
        return sortDesc ? <ArrowDown className="h-3 w-3 ml-1" /> : <ArrowUp className="h-3 w-3 ml-1" />;
    };

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

            <div className="flex flex-wrap gap-3 mb-4">
                <select
                    value={serviceFilter}
                    onChange={(e) => setServiceFilter(e.target.value)}
                    className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                    <option value="">All Services</option>
                    <option value="pppoe">PPPoE</option>
                    <option value="hotspot">Hotspot</option>
                    <option value="both">Both</option>
                </select>
                <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                    <option value="">All Statuses</option>
                    <option value="active">Active</option>
                    <option value="suspended">Suspended</option>
                    <option value="expired">Expired</option>
                    <option value="pending">Pending</option>
                </select>
                {(serviceFilter || statusFilter || sortField) && (
                    <button
                        onClick={() => { setServiceFilter(''); setStatusFilter(''); setSortField(''); }}
                        className="text-sm text-blue-600 hover:text-blue-800 px-2"
                    >
                        Clear filters
                    </button>
                )}
            </div>

            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Service</th>
                                <th
                                    onClick={() => toggleSort('calculated_expiry')}
                                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:text-gray-700"
                                >
                                    <span className="flex items-center">Calculated Expiry <SortIcon field="calculated_expiry" /></span>
                                </th>
                                <th
                                    onClick={() => toggleSort('account_balance')}
                                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:text-gray-700"
                                >
                                    <span className="flex items-center">Balance <SortIcon field="account_balance" /></span>
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {isLoading ? (
                                <tr>
                                    <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                                        <div className="flex justify-center items-center">
                                            <Loader2 className="h-6 w-6 animate-spin mr-2" />
                                            Loading subscribers...
                                        </div>
                                    </td>
                                </tr>
                            ) : isError ? (
                                <tr>
                                    <td colSpan={5} className="px-6 py-8 text-center text-red-500">
                                        Error loading subscribers: {(error as Error).message}
                                    </td>
                                </tr>
                            ) : subscribers?.length === 0 ? (
                                <tr>
                                    <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                                        No subscribers found.
                                    </td>
                                </tr>
                            ) : (
                                subscribers?.map((user: any) => (
                                    <tr
                                        key={user.id}
                                        onClick={() => setSelectedId(user.id)}
                                        className="hover:bg-gray-50 transition cursor-pointer"
                                    >
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="text-sm font-medium text-gray-900">{user.username}</div>
                                            <div className="text-sm text-gray-500">{user.full_name}</div>
                                            <div className="text-xs text-gray-400">{user.phone_number}</div>
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
                                            {user.calculated_expiry ? format(new Date(user.calculated_expiry), 'MMM d, yyyy') : '-'}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                            KES {Number(user.account_balance).toLocaleString()}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize
                                                ${user.status === 'active' ? 'bg-green-100 text-green-800' :
                                                    user.status === 'expired' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800'}
                                            `}>
                                                {user.status}
                                            </span>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {selectedId !== null && (
                <SubscriberDetailModal id={selectedId} onClose={() => setSelectedId(null)} />
            )}
        </div>
    );
}
