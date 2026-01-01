import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { billingAPI } from '../../services/api';
import { ArrowLeft, Wifi, Zap } from 'lucide-react';

export default function Plans() {
    const { data: plans, isLoading, error } = useQuery({
        queryKey: ['plans'],
        queryFn: async () => {
            const response = await billingAPI.getPlans();
            // DRF returns paginated response: {count, next, previous, results}
            return response.data.results || response.data;
        },
    });

    if (isLoading) {
        return (
            <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center transition-colors">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
                    <p className="mt-4 text-gray-600 dark:text-gray-400">Loading plans...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="text-center">
                    <p className="text-red-600">Error loading plans. Please try again.</p>
                    <p className="text-sm text-gray-600 mt-2">{String(error)}</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-200">
            <div className="bg-white dark:bg-gray-800 shadow transition-colors">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
                    <Link to="/dashboard" className="flex items-center gap-2 text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
                        <ArrowLeft className="w-5 h-5" />
                        Back to Dashboard
                    </Link>
                </div>
            </div>

            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="text-center mb-12">
                    <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-4">Choose Your Plan</h1>
                    <p className="text-xl text-gray-600 dark:text-gray-400">Select the perfect internet package for your needs</p>
                </div>

                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {plans?.map((plan: any) => (
                        <div
                            key={plan.id}
                            className="bg-white rounded-2xl shadow-lg overflow-hidden hover:shadow-2xl transition"
                        >
                            <div className="bg-gradient-to-r from-blue-600 to-purple-600 p-6 text-white">
                                <div className="flex items-center gap-3 mb-2">
                                    <Wifi className="w-8 h-8" />
                                    <h3 className="text-2xl font-bold">{plan.name}</h3>
                                </div>
                                <p className="text-blue-100">{plan.service_type.toUpperCase()}</p>
                            </div>

                            <div className="p-6 bg-white dark:bg-gray-800 transition-colors">
                                <div className="mb-6">
                                    <div className="flex items-baseline gap-2 mb-2">
                                        <span className="text-4xl font-bold text-gray-900 dark:text-white">KES {plan.price}</span>
                                        <span className="text-gray-600 dark:text-gray-400">/ {plan.duration_value} {plan.duration_unit}</span>
                                    </div>
                                </div>

                                <div className="space-y-3 mb-6">
                                    <div className="flex items-center gap-3">
                                        <Zap className="w-5 h-5 text-green-600 dark:text-green-400" />
                                        <span className="text-gray-700 dark:text-gray-300">
                                            <strong>{plan.download_speed} Mbps</strong> Download
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <Zap className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                        <span className="text-gray-700 dark:text-gray-300">
                                            <strong>{plan.upload_speed} Mbps</strong> Upload
                                        </span>
                                    </div>
                                    {plan.data_limit_gb && (
                                        <div className="flex items-center gap-3">
                                            <Wifi className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                                            <span className="text-gray-700 dark:text-gray-300">
                                                <strong>{plan.data_limit_gb} GB</strong> Data
                                            </span>
                                        </div>
                                    )}
                                    {!plan.data_limit_gb && (
                                        <div className="flex items-center gap-3">
                                            <Wifi className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                                            <span className="text-gray-700 dark:text-gray-300">
                                                <strong>Unlimited</strong> Data
                                            </span>
                                        </div>
                                    )}
                                </div>

                                {plan.description && (
                                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">{plan.description}</p>
                                )}

                                <Link
                                    to={`/payment?plan=${plan.id}`}
                                    className="block w-full bg-blue-600 text-white text-center py-3 rounded-lg font-semibold hover:bg-blue-700 transition"
                                >
                                    Subscribe Now
                                </Link>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
