import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { billingAPI } from '../../services/api';
import { ArrowLeft, Wifi, Zap } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { filterSelfServicePlans } from '../../utils/plans';
import { Card } from '../../components/ui/card';

export default function Plans() {
    const userServiceType = useAuthStore((state) => state.user?.service_type);

    const { data: plans, isLoading, error } = useQuery({
        queryKey: ['plans', userServiceType],
        queryFn: async () => {
            const response = await billingAPI.getPlans();
            // DRF returns paginated response: {count, next, previous, results}
            const allPlans = response.data.results || response.data;
            return filterSelfServicePlans(allPlans, userServiceType);
        },
    });

    if (isLoading) {
        return (
            <div className="min-h-screen bg-secondary flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
                    <p className="mt-4 text-muted-foreground">Loading plans...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="min-h-screen bg-secondary flex items-center justify-center">
                <div className="text-center">
                    <p className="text-red-600">Error loading plans. Please try again.</p>
                    <p className="text-sm text-muted-foreground mt-2">{String(error)}</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-secondary">
            <div className="bg-card border-b border-border">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
                    <Link to="/dashboard" className="flex items-center gap-2 text-muted-foreground hover:text-foreground">
                        <ArrowLeft className="w-5 h-5" />
                        Back to Dashboard
                    </Link>
                </div>
            </div>

            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="text-center mb-12">
                    <h1 className="text-4xl font-bold text-foreground mb-4">Choose Your Plan</h1>
                    <p className="text-xl text-muted-foreground">Select the perfect internet package for your needs</p>
                </div>

                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {plans?.map((plan: any) => (
                        <Card
                            key={plan.id}
                            className="overflow-hidden shadow-lg hover:shadow-xl transition"
                        >
                            <div className="bg-gradient-to-r from-primary to-primary/70 p-6 text-primary-foreground">
                                <div className="flex items-center gap-3 mb-2">
                                    <Wifi className="w-8 h-8" />
                                    <h3 className="text-2xl font-bold">{plan.name}</h3>
                                </div>
                                <p className="text-primary-foreground/80">{plan.service_type.toUpperCase()}</p>
                            </div>

                            <div className="p-6">
                                <div className="mb-6">
                                    <div className="flex items-baseline gap-2 mb-2">
                                        <span className="text-4xl font-bold text-foreground">KES {plan.price}</span>
                                        <span className="text-muted-foreground">/ {plan.duration_value} {plan.duration_unit}</span>
                                    </div>
                                </div>

                                <div className="space-y-3 mb-6">
                                    <div className="flex items-center gap-3">
                                        <Zap className="w-5 h-5 text-green-600" />
                                        <span className="text-foreground/80">
                                            <strong>{plan.download_speed} Mbps</strong> Download
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <Zap className="w-5 h-5 text-primary" />
                                        <span className="text-foreground/80">
                                            <strong>{plan.upload_speed} Mbps</strong> Upload
                                        </span>
                                    </div>
                                    {plan.data_limit_gb !== null && plan.data_limit_gb !== undefined && (
                                        <div className="flex items-center gap-3">
                                            <Wifi className="w-5 h-5 text-primary" />
                                            <span className="text-foreground/80">
                                                <strong>{Number(plan.data_limit_gb).toLocaleString(undefined, { maximumFractionDigits: 3 })} GB</strong> Data
                                            </span>
                                        </div>
                                    )}
                                    {(plan.data_limit_gb === null || plan.data_limit_gb === undefined) && (
                                        <div className="flex items-center gap-3">
                                            <Wifi className="w-5 h-5 text-primary" />
                                            <span className="text-foreground/80">
                                                <strong>Unlimited</strong> Data
                                            </span>
                                        </div>
                                    )}
                                </div>

                                {plan.description && (
                                    <p className="text-sm text-muted-foreground mb-6">{plan.description}</p>
                                )}

                                <Link
                                    to={`/payment?plan=${plan.id}`}
                                    className="block w-full bg-primary text-white text-center py-3 rounded-lg font-semibold hover:bg-primary/90 transition"
                                >
                                    Subscribe Now
                                </Link>
                            </div>
                        </Card>
                    ))}
                </div>
            </div>
        </div>
    );
}
