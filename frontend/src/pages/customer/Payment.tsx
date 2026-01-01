import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { billingAPI, paymentAPI } from '../../services/api';
import toast from 'react-hot-toast';
import { ArrowLeft, Smartphone, CreditCard, CheckCircle, XCircle, Loader } from 'lucide-react';

export default function Payment() {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const planId = searchParams.get('plan');

    const [phoneNumber, setPhoneNumber] = useState('');
    const [selectedPlanId, setSelectedPlanId] = useState(planId || '');
    const [loading, setLoading] = useState(false);
    const [paymentRequestId, setPaymentRequestId] = useState<number | null>(null);
    const [paymentStatus, setPaymentStatus] = useState<'idle' | 'pending' | 'success' | 'failed'>('idle');

    const { data: plans } = useQuery({
        queryKey: ['plans'],
        queryFn: async () => {
            const response = await billingAPI.getPlans();
            // DRF returns paginated response: {count, next, previous, results}
            return response.data.results || response.data;
        },
    });

    const selectedPlan = plans?.find((p: any) => p.id === parseInt(selectedPlanId));

    // Poll payment status
    useEffect(() => {
        if (!paymentRequestId || paymentStatus !== 'pending') return;

        const interval = setInterval(async () => {
            try {
                const response = await paymentAPI.getPaymentStatus(paymentRequestId);
                const status = response.data.status;

                if (status === 'completed') {
                    setPaymentStatus('success');
                    clearInterval(interval);
                    toast.success('Payment successful! Your internet has been activated.');
                    setTimeout(() => navigate('/dashboard'), 3000);
                } else if (status === 'failed' || status === 'timeout') {
                    setPaymentStatus('failed');
                    clearInterval(interval);
                    toast.error('Payment failed. Please try again.');
                }
            } catch (error) {
                console.error('Error checking payment status:', error);
            }
        }, 3000); // Check every 3 seconds

        return () => clearInterval(interval);
    }, [paymentRequestId, paymentStatus, navigate]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!selectedPlanId) {
            toast.error('Please select a plan');
            return;
        }

        setLoading(true);

        try {
            const macAddress = localStorage.getItem('hotspot_mac');

            const response = await paymentAPI.initiatePayment({
                plan_id: parseInt(selectedPlanId),
                phone_number: phoneNumber,
                mac_address: macAddress || undefined
            });

            if (response.data.success) {
                setPaymentRequestId(response.data.payment_request_id);
                setPaymentStatus('pending');
                toast.success('STK Push sent! Please check your phone.');
            } else {
                toast.error(response.data.error || 'Failed to initiate payment');
            }
        } catch (error: any) {
            toast.error(error.response?.data?.error || 'Payment initiation failed');
        } finally {
            setLoading(false);
        }
    };

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

            <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 rounded-full mb-4">
                        <CreditCard className="w-8 h-8 text-green-600" />
                    </div>
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Make Payment</h1>
                    <p className="text-gray-600 dark:text-gray-400 mt-2">Pay via M-Pesa STK Push</p>
                </div>

                {paymentStatus === 'idle' && (
                    <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-8 transition-colors">
                        <form onSubmit={handleSubmit} className="space-y-6">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Select Plan
                                </label>
                                <select
                                    required
                                    className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-colors"
                                    value={selectedPlanId}
                                    onChange={(e) => setSelectedPlanId(e.target.value)}
                                >
                                    <option value="">Choose a plan...</option>
                                    {plans?.map((plan: any) => (
                                        <option key={plan.id} value={plan.id}>
                                            {plan.name} - KES {plan.price} ({plan.duration_days} days)
                                        </option>
                                    ))}
                                </select>
                            </div>

                            {selectedPlan && (
                                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 transition-colors">
                                    <h3 className="font-semibold text-gray-900 dark:text-white mb-2">{selectedPlan.name}</h3>
                                    <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
                                        Speed: {selectedPlan.download_speed}/{selectedPlan.upload_speed} Mbps
                                    </p>
                                    <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">KES {selectedPlan.price}</p>
                                </div>
                            )}

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    M-Pesa Phone Number
                                </label>
                                <div className="relative">
                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                        <Smartphone className="h-5 w-5 text-gray-400" />
                                    </div>
                                    <input
                                        type="tel"
                                        required
                                        placeholder="0712345678"
                                        className="w-full pl-10 pr-4 py-3 border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-colors"
                                        value={phoneNumber}
                                        onChange={(e) => setPhoneNumber(e.target.value)}
                                    />
                                </div>
                                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                    Enter the phone number to receive the STK Push prompt
                                </p>
                            </div>

                            <button
                                type="submit"
                                disabled={loading || !selectedPlanId}
                                className="w-full bg-green-600 text-white py-3 rounded-lg font-semibold hover:bg-green-700 transition disabled:opacity-50 flex items-center justify-center gap-2"
                            >
                                {loading ? (
                                    <>
                                        <Loader className="w-5 h-5 animate-spin" />
                                        Initiating Payment...
                                    </>
                                ) : (
                                    <>
                                        <CreditCard className="w-5 h-5" />
                                        Pay with M-Pesa
                                    </>
                                )}
                            </button>
                        </form>
                    </div>
                )}

                {paymentStatus === 'pending' && (
                    <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
                        <Loader className="w-16 h-16 text-blue-600 animate-spin mx-auto mb-4" />
                        <h3 className="text-2xl font-bold text-gray-900 mb-2">Waiting for Payment</h3>
                        <p className="text-gray-600 mb-4">
                            Please check your phone and enter your M-Pesa PIN to complete the payment.
                        </p>
                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                            <p className="text-sm text-blue-800">
                                You will receive an STK Push notification on <strong>{phoneNumber}</strong>
                            </p>
                        </div>
                    </div>
                )}

                {paymentStatus === 'success' && (
                    <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-8 text-center transition-colors">
                        <CheckCircle className="w-16 h-16 text-green-600 dark:text-green-500 mx-auto mb-4" />
                        <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Payment Successful!</h3>
                        <p className="text-gray-600 dark:text-gray-400 mb-4">
                            Your internet access has been activated. Redirecting to dashboard...
                        </p>
                    </div>
                )}

                {paymentStatus === 'failed' && (
                    <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
                        <XCircle className="w-16 h-16 text-red-600 mx-auto mb-4" />
                        <h3 className="text-2xl font-bold text-gray-900 mb-2">Payment Failed</h3>
                        <p className="text-gray-600 mb-4">
                            The payment was not completed. Please try again.
                        </p>
                        <button
                            onClick={() => {
                                setPaymentStatus('idle');
                                setPaymentRequestId(null);
                            }}
                            className="bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold hover:bg-blue-700"
                        >
                            Try Again
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
