import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { voucherAPI, billingAPI, paymentAPI } from '../../services/api';
import toast from 'react-hot-toast';
import { Wifi, Lock, Loader, ArrowRight, CreditCard, X, Check } from 'lucide-react';

interface Plan {
    id: number;
    name: string;
    price: string;
    description: string;
    download_speed: number;
    upload_speed: number;
    duration_value: number;
    duration_unit: 'minutes' | 'hours' | 'days' | 'months';
}

const CaptivePortal: React.FC = () => {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();

    const mac = searchParams.get('mac') || searchParams.get('mac_esc');
    const linkLogin = searchParams.get('link-login') || searchParams.get('link_login');
    const linkOrig = searchParams.get('link-orig') || searchParams.get('link_orig');

    // Default to the IP if link-login is missing
    const loginActionUrl = linkLogin ? decodeURIComponent(linkLogin) : 'http://10.5.50.1/login';

    const [loading, setLoading] = useState(true);
    const [status, setStatus] = useState<'checking' | 'active' | 'inactive'>('checking');
    const [message, setMessage] = useState('Checking connection status...');
    const [voucherCode, setVoucherCode] = useState('');
    const [redeeming, setRedeeming] = useState(false);

    // Guest Checkout State
    const [plans, setPlans] = useState<Plan[]>([]);
    const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
    const [phoneNumber, setPhoneNumber] = useState('');
    const [processingPayment, setProcessingPayment] = useState(false);
    const [paymentSuccess, setPaymentSuccess] = useState(false);

    // Use relative path for API to support access via IP or Domain without CORS/DNS issues
    // Nginx is configured to proxy /api to the backend
    const API_URL = '/api';

    useEffect(() => {
        checkStatus();
        fetchPlans();
    }, [mac]);

    const fetchPlans = async () => {
        try {
            const response = await billingAPI.getPlans();
            // Handle DRF pagination (response.data.results) or flat list (response.data)
            const data = response.data.results ? response.data.results : response.data;
            if (Array.isArray(data)) {
                setPlans(data);
            } else {
                console.error('Invalid plans format:', data);
                setPlans([]);
            }
        } catch (error) {
            console.error('Failed to fetch plans', error);
            setPlans([]);
        }
    };

    const checkStatus = async () => {
        if (!mac) {
            setLoading(false);
            setStatus('inactive');
            setMessage('No device detected. Please connect to WiFi properly.');
            return;
        }

        try {
            const response = await axios.get(`${API_URL}/network/hotspot/status/?mac=${mac}`);
            if (response.data.active) {
                setStatus('active');
                setMessage('Subscription found! Logging you in...');
                doLogin(response.data.username, response.data.password);
            } else {
                setStatus('inactive');
                setMessage('No active subscription found.');
                setLoading(false);

                // Clear any stale tokens so we don't accidentally send them with payment requests
                // This ensures "guest" mode for payments and new user creation if needed
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
            }
        } catch (error) {
            console.error('Status check failed:', error);
            setStatus('inactive');
            setMessage('Welcome! Please buy a plan to connect.');
            setLoading(false);
        }
    };

    const doLogin = (username: string, password: string) => {
        if (!linkLogin) {
            setLoading(false);
            setStatus('active');
            setMessage('You are already authorized! (Dev Mode: No redirect URL provided)');
            toast.success('Login logic triggered but no redirect URL found.');
            return;
        }

        const form = document.createElement('form');
        form.method = 'POST';
        form.action = loginActionUrl;

        const uField = document.createElement('input');
        uField.type = 'hidden';
        uField.name = 'username';
        uField.value = username;
        form.appendChild(uField);

        const pField = document.createElement('input');
        pField.type = 'hidden';
        pField.name = 'password';
        pField.value = password;
        form.appendChild(pField);

        const dstField = document.createElement('input');
        dstField.type = 'hidden';
        dstField.name = 'dst';
        dstField.value = linkOrig || 'http://google.com';
        form.appendChild(dstField);

        document.body.appendChild(form);
        form.submit();
    };

    const handleRedeemVoucher = async (e: React.FormEvent) => {
        e.preventDefault();
        setRedeeming(true);
        try {
            const response = await voucherAPI.redeem(voucherCode);
            toast.success(response.data.message);

            // Auto Login if tokens are present
            if (response.data.tokens) {
                localStorage.setItem('access_token', response.data.tokens.access);
                localStorage.setItem('refresh_token', response.data.tokens.refresh);

                // Use the returned customer username/password (which defaults to voucher code) to authorize in Mikrotik
                // The doLogin function submits a form to the Mikrotik router
                const customer = response.data.customer;
                // Note: Security-wise, we might want to change how doLogin works, 
                // but for now we follow the existing pattern if password is available or assumed.

                // If we don't have the password explicitly in the response (serialized customer usually hides it), 
                // we can assume password = voucherCode based on our backend logic for auto-created users.
                doLogin(customer.username || voucherCode, voucherCode);
            } else if (mac) {
                checkStatus();
            }

            setVoucherCode('');
        } catch (error: any) {
            console.error('Redeem error:', error);
            toast.error(error.response?.data?.error || 'Failed to redeem voucher');
        } finally {
            setRedeeming(false);
        }
    };

    const handleBuyPlan = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!selectedPlan || !phoneNumber) return;

        setProcessingPayment(true);
        try {
            await paymentAPI.initiatePayment({
                plan_id: selectedPlan.id,
                phone_number: phoneNumber,
                mac_address: mac || undefined
            });
            setPaymentSuccess(true);
            toast.success('Payment request sent! Check your phone.');
        } catch (error: any) {
            toast.error(error.response?.data?.error || 'Payment initiation failed');
        } finally {
            setProcessingPayment(false);
        }
    };

    if (loading || status === 'active') {
        return (
            <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4 text-white">
                <div className="text-center">
                    <Loader className="h-12 w-12 animate-spin mx-auto text-blue-500 mb-4" />
                    <h2 className="text-xl font-bold">{message}</h2>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-900 p-4 font-sans">
            <div className="max-w-4xl mx-auto space-y-6">
                {/* Header */}
                <div className="text-center text-white pt-8 pb-4">
                    <div className="mx-auto bg-blue-600 rounded-full w-16 h-16 flex items-center justify-center mb-4 shadow-lg shadow-blue-500/50">
                        <Wifi className="h-8 w-8 text-white" />
                    </div>
                    <h1 className="text-3xl font-bold mb-2">Connect to ISP Wi-Fi</h1>
                    <p className="text-gray-400">Choose a package to get started instantly.</p>
                </div>

                {/* Plans Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {plans.map((plan) => (
                        <div key={plan.id} className="bg-gray-800 rounded-xl p-6 border border-gray-700 hover:border-blue-500 transition-all shadow-lg flex flex-col relative overflow-hidden group">
                            <div className="absolute top-0 right-0 bg-blue-600 text-white text-xs font-bold px-3 py-1 rounded-bl-lg">
                                {plan.download_speed} Mbps
                            </div>
                            <h3 className="text-xl font-bold text-white mb-2">{plan.name}</h3>
                            <div className="text-3xl font-bold text-green-400 mb-4">
                                <span className="text-sm text-gray-400 font-normal">KES</span> {Math.floor(parseFloat(plan.price))}
                            </div>
                            <p className="text-gray-400 text-sm mb-6 flex-1">{plan.description || `${plan.duration_value} ${plan.duration_unit} Unlimited Internet`}</p>
                            <button
                                onClick={() => setSelectedPlan(plan)}
                                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-lg transition flex items-center justify-center gap-2 group-hover:scale-105 active:scale-95 transform duration-200"
                            >
                                <CreditCard className="h-4 w-4" />
                                Buy Now
                            </button>
                        </div>
                    ))}
                </div>

                {/* Voucher & Login Section */}
                <div className="max-w-md mx-auto space-y-4">
                    <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
                        <h3 className="text-white font-medium mb-3 text-sm uppercase tracking-wider text-gray-400">Have a Voucher?</h3>
                        <form onSubmit={handleRedeemVoucher} className="flex gap-2">
                            <input
                                type="text"
                                placeholder="Enter Voucher Code"
                                value={voucherCode}
                                onChange={(e) => setVoucherCode(e.target.value)}
                                className="flex-1 bg-gray-900 border border-gray-600 rounded-lg p-3 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition"
                            />
                            <button
                                type="submit"
                                disabled={redeeming}
                                className="bg-green-600 hover:bg-green-700 text-white px-6 rounded-lg font-bold disabled:opacity-50 transition"
                            >
                                {redeeming ? <Loader className="animate-spin h-5 w-5" /> : 'Redeem'}
                            </button>
                        </form>
                    </div>

                    <button
                        onClick={() => navigate('/login')}
                        className="w-full text-gray-400 hover:text-white text-sm py-2 transition"
                    >
                        Already have an account? Login here
                    </button>
                </div>

                <div className="text-center text-xs text-gray-600 pb-8">
                    MAC: {mac || 'Unknown'} • Secure Connection <Lock className="h-3 w-3 inline ml-1" />
                </div>
            </div>

            {/* Payment Modal */}
            {selectedPlan && (
                <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
                    <div className="bg-gray-800 rounded-2xl max-w-sm w-full p-6 shadow-2xl border border-gray-700 relative animate-in fade-in zoom-in duration-200">
                        <button
                            onClick={() => { setSelectedPlan(null); setPaymentSuccess(false); }}
                            className="absolute top-4 right-4 text-gray-400 hover:text-white"
                        >
                            <X className="h-6 w-6" />
                        </button>

                        {!paymentSuccess ? (
                            <>
                                <h2 className="text-2xl font-bold text-white mb-1">Confirm Purchase</h2>
                                <p className="text-gray-400 mb-6">You are buying <span className="text-blue-400 font-bold">{selectedPlan.name}</span> for <span className="text-green-400 font-bold">KES {Math.floor(parseFloat(selectedPlan.price))}</span></p>

                                <form onSubmit={handleBuyPlan} className="space-y-4">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-300 mb-1">M-Pesa Phone Number</label>
                                        <input
                                            type="tel"
                                            placeholder="07XXXXXXXX"
                                            value={phoneNumber}
                                            onChange={(e) => setPhoneNumber(e.target.value)}
                                            className="w-full bg-gray-900 border border-gray-600 rounded-lg p-3 text-white text-lg placeholder-gray-500 focus:outline-none focus:border-blue-500 transition"
                                            required
                                        />
                                    </div>
                                    <button
                                        type="submit"
                                        disabled={processingPayment}
                                        className="w-full bg-green-600 hover:bg-green-700 text-white font-bold py-4 rounded-xl transition flex items-center justify-center gap-2 text-lg disabled:opacity-50"
                                    >
                                        {processingPayment ? <Loader className="animate-spin h-6 w-6" /> : 'Pay with M-Pesa'}
                                    </button>
                                </form>
                            </>
                        ) : (
                            <div className="text-center py-8">
                                <div className="bg-green-600/20 text-green-500 rounded-full w-20 h-20 flex items-center justify-center mx-auto mb-6">
                                    <Check className="h-10 w-10" />
                                </div>
                                <h2 className="text-2xl font-bold text-white mb-2">Check your phone!</h2>
                                <p className="text-gray-400 mb-6">Enter your M-Pesa PIN to complete the payment.</p>
                                <p className="text-sm text-gray-500">Your internet will activate automatically once received.</p>
                                <button
                                    onClick={() => { setSelectedPlan(null); setPaymentSuccess(false); checkStatus(); }}
                                    className="mt-6 w-full bg-gray-700 hover:bg-gray-600 text-white font-bold py-3 rounded-lg transition"
                                >
                                    Close & Wait for Connection
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default CaptivePortal;
