import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { voucherAPI, billingAPI, paymentAPI } from '../../services/api';
import { useSiteSettings } from '../../hooks/useSiteSettings';
import toast from 'react-hot-toast';
import { Wifi, Lock, Loader, CreditCard, X, Check } from 'lucide-react';
import { Card } from '../../components/ui/card';
import { Button } from '../../components/ui/button';

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
    const { data: siteSettings } = useSiteSettings();

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
    const [pppoeCredentials, setPppoeCredentials] = useState<{ username: string; password: string } | null>(null);
    const [mpesaCode, setMpesaCode] = useState('');
    const [reactivating, setReactivating] = useState(false);

    // Guest Checkout State
    const [plans, setPlans] = useState<Plan[]>([]);
    const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
    const [phoneNumber, setPhoneNumber] = useState('');
    const [processingPayment, setProcessingPayment] = useState(false);
    const [paymentSuccess, setPaymentSuccess] = useState(false);
    const [pollTimedOut, setPollTimedOut] = useState(false);

    // Use relative path for API to support access via IP or Domain without CORS/DNS issues
    // Nginx is configured to proxy /api to the backend
    const API_URL = '/api';

    useEffect(() => {
        checkStatus();
        fetchPlans();
    }, [mac]);

    // After a payment is initiated, keep re-checking automatically (rather
    // than requiring a manual click) until either the subscription shows up
    // (checkStatus flips status to 'active' and logs the device in itself)
    // or we've retried for a while without luck -- 18 tries * 5s = 90s,
    // long enough to cover a normal STK push + M-Pesa PIN entry + callback
    // round trip, short enough not to leave someone staring at a spinner
    // forever if something actually went wrong.
    useEffect(() => {
        if (!paymentSuccess || pollTimedOut || status === 'active') return;

        let attempts = 0;
        const MAX_ATTEMPTS = 18;
        const interval = setInterval(async () => {
            attempts += 1;
            await checkStatus();
            if (attempts >= MAX_ATTEMPTS) {
                clearInterval(interval);
                setPollTimedOut(true);
            }
        }, 5000);

        return () => clearInterval(interval);
    }, [paymentSuccess, pollTimedOut, status]);

    const fetchPlans = async () => {
        try {
            const response = await billingAPI.getPlans();
            // Handle DRF pagination (response.data.results) or flat list (response.data)
            const data = response.data.results ? response.data.results : response.data;
            if (Array.isArray(data)) {
                // Only Hotspot plans belong here -- PPPoE requires a wired/
                // configured router login, not a WiFi captive-portal guest,
                // and Static IP is technician-assigned only.
                setPlans(data.filter((p: any) => p.service_type === 'hotspot'));
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
        // loginActionUrl already falls back to the default gateway login URL
        // when link-login wasn't in the redirect -- submitting is still the
        // right move even then (silently no-op-ing here just stranded the
        // device with no internet and a confusing "success" toast).
        if (!linkLogin) {
            console.warn('No link-login param in the captive portal redirect -- submitting to the default gateway login URL instead.');
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
        setPppoeCredentials(null);
        try {
            const response = await voucherAPI.redeem(voucherCode, mac || undefined);
            toast.success(response.data.message);

            if (response.data.tokens) {
                localStorage.setItem('access_token', response.data.tokens.access);
                localStorage.setItem('refresh_token', response.data.tokens.refresh);
            }

            // credentials.hotspot_username/password are the actual values
            // provisioned on the router (not reconstructed from the voucher
            // code client-side, which could drift if the backend had to
            // de-duplicate the username) -- use them directly for the
            // captive-portal login.
            const credentials = response.data.credentials;
            const serviceType = response.data.customer?.service_type;
            const isHotspotCapable = serviceType === 'hotspot' || serviceType === 'both';

            if (isHotspotCapable && credentials?.hotspot_username) {
                doLogin(credentials.hotspot_username, credentials.hotspot_password);
            } else if (credentials?.pppoe_username) {
                // PPPoE has no "instant login" the way Hotspot does -- there's
                // no captive-portal form that can authenticate a PPPoE
                // session. The only thing left to do is show the customer
                // the credentials their own router needs to dial in with.
                setPppoeCredentials({ username: credentials.pppoe_username, password: credentials.pppoe_password });
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

    const handleReactivate = async (e: React.FormEvent) => {
        e.preventDefault();
        setReactivating(true);
        try {
            const response = await paymentAPI.reactivateSession(mpesaCode, mac || undefined);
            toast.success(response.data.message);
            doLogin(response.data.username, response.data.password);
            setMpesaCode('');
        } catch (error: any) {
            toast.error(error.response?.data?.error || 'Failed to reactivate session');
        } finally {
            setReactivating(false);
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
            setPollTimedOut(false);
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
            <div className="min-h-screen bg-secondary flex items-center justify-center p-4">
                <div className="text-center">
                    <Loader className="h-12 w-12 animate-spin mx-auto text-primary mb-4" />
                    <h2 className="text-xl font-bold text-foreground">{message}</h2>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-secondary p-4 font-sans">
            <div className="max-w-4xl mx-auto space-y-6">
                {/* Header */}
                <div className="text-center pt-8 pb-4">
                    {siteSettings?.logo ? (
                        <img
                            src={siteSettings.logo}
                            alt={siteSettings.company_name}
                            className="mx-auto rounded-2xl w-16 h-16 object-contain bg-card border border-border mb-4 shadow-sm"
                        />
                    ) : (
                        <div className="mx-auto bg-primary rounded-2xl w-16 h-16 flex items-center justify-center mb-4 shadow-lg shadow-primary/30">
                            <Wifi className="h-8 w-8 text-primary-foreground" />
                        </div>
                    )}
                    <h1 className="text-3xl font-bold mb-2 text-foreground">
                        Connect to {siteSettings?.company_name || 'WiFi'}
                    </h1>
                    <p className="text-muted-foreground">Choose a package to get started instantly.</p>
                </div>

                {/* Plans Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {plans.map((plan) => (
                        <Card key={plan.id} className="p-6 hover:border-primary/50 transition-all flex flex-col relative overflow-hidden group">
                            <div className="absolute top-0 right-0 bg-primary text-primary-foreground text-xs font-bold px-3 py-1 rounded-bl-lg">
                                {plan.download_speed} Mbps
                            </div>
                            <h3 className="text-xl font-bold text-foreground mb-2">{plan.name}</h3>
                            <div className="text-3xl font-bold text-green-600 mb-4">
                                <span className="text-sm text-muted-foreground font-normal">KES</span> {Math.floor(parseFloat(plan.price))}
                            </div>
                            <p className="text-muted-foreground text-sm mb-6 flex-1">{plan.description || `${plan.duration_value} ${plan.duration_unit} Unlimited Internet`}</p>
                            <Button
                                onClick={() => setSelectedPlan(plan)}
                                className="w-full group-hover:scale-105 active:scale-95 transform duration-200"
                                size="lg"
                            >
                                <CreditCard className="h-4 w-4" />
                                Buy Now
                            </Button>
                        </Card>
                    ))}
                </div>

                {/* Voucher & Login Section */}
                <div className="max-w-md mx-auto space-y-4">
                    <Card className="p-4">
                        <h3 className="text-foreground font-medium mb-3 text-xs uppercase tracking-wider text-muted-foreground">Have a Voucher?</h3>
                        <form onSubmit={handleRedeemVoucher} className="flex gap-2">
                            <input
                                type="text"
                                placeholder="Enter Voucher Code"
                                value={voucherCode}
                                onChange={(e) => setVoucherCode(e.target.value)}
                                className="flex-1 bg-background border border-input rounded-lg p-3 text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring transition"
                            />
                            <Button type="submit" disabled={redeeming} variant="default" className="px-6 bg-green-600 hover:bg-green-700">
                                {redeeming ? <Loader className="animate-spin h-5 w-5" /> : 'Redeem'}
                            </Button>
                        </form>
                    </Card>

                    {pppoeCredentials && (
                        <Card className="p-4 bg-primary/5 border-primary/20">
                            <h3 className="text-foreground font-bold mb-2 flex items-center gap-2"><Check className="h-4 w-4 text-green-600" /> PPPoE Ready</h3>
                            <p className="text-muted-foreground text-sm mb-3">
                                PPPoE doesn't connect automatically here -- enter these details in your own
                                router's PPPoE/dial-up settings to get online:
                            </p>
                            <div className="bg-background rounded-lg p-3 space-y-1 font-mono text-sm border border-border">
                                <p className="text-muted-foreground">Username: <span className="text-foreground">{pppoeCredentials.username}</span></p>
                                <p className="text-muted-foreground">Password: <span className="text-foreground">{pppoeCredentials.password}</span></p>
                            </div>
                        </Card>
                    )}

                    <Card className="p-4">
                        <h3 className="text-foreground font-medium mb-3 text-xs uppercase tracking-wider text-muted-foreground">Already Paid? Reconnect</h3>
                        <form onSubmit={handleReactivate} className="flex gap-2">
                            <input
                                type="text"
                                placeholder="Enter M-Pesa Code"
                                value={mpesaCode}
                                onChange={(e) => setMpesaCode(e.target.value)}
                                className="flex-1 bg-background border border-input rounded-lg p-3 text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring transition uppercase"
                            />
                            <Button type="submit" disabled={reactivating} className="px-6">
                                {reactivating ? <Loader className="animate-spin h-5 w-5" /> : 'Reconnect'}
                            </Button>
                        </form>
                        <p className="text-xs text-muted-foreground mt-2">Already have an active plan but got disconnected? Enter the M-Pesa code from your payment SMS.</p>
                    </Card>

                    <button
                        onClick={() => navigate('/login')}
                        className="w-full text-muted-foreground hover:text-foreground text-sm py-2 transition"
                    >
                        Already have an account? Login here
                    </button>
                </div>

                <div className="text-center text-xs text-muted-foreground pb-8">
                    MAC: {mac || 'Unknown'} &middot; Secure Connection <Lock className="h-3 w-3 inline ml-1" />
                </div>
            </div>

            {/* Payment Modal */}
            {selectedPlan && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
                    <Card className="max-w-sm w-full p-6 shadow-2xl relative animate-in fade-in zoom-in duration-200">
                        <button
                            onClick={() => { setSelectedPlan(null); setPaymentSuccess(false); setPollTimedOut(false); }}
                            className="absolute top-4 right-4 text-muted-foreground hover:text-foreground"
                        >
                            <X className="h-6 w-6" />
                        </button>

                        {!paymentSuccess ? (
                            <>
                                <h2 className="text-2xl font-bold text-foreground mb-1">Confirm Purchase</h2>
                                <p className="text-muted-foreground mb-6">You are buying <span className="text-primary font-bold">{selectedPlan.name}</span> for <span className="text-green-600 font-bold">KES {Math.floor(parseFloat(selectedPlan.price))}</span></p>

                                <form onSubmit={handleBuyPlan} className="space-y-4">
                                    <div>
                                        <label className="block text-sm font-medium text-foreground mb-1">M-Pesa Phone Number</label>
                                        <input
                                            type="tel"
                                            placeholder="07XXXXXXXX"
                                            value={phoneNumber}
                                            onChange={(e) => setPhoneNumber(e.target.value)}
                                            className="w-full bg-background border border-input rounded-lg p-3 text-foreground text-lg placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring transition"
                                            required
                                        />
                                    </div>
                                    <Button
                                        type="submit"
                                        disabled={processingPayment}
                                        className="w-full bg-green-600 hover:bg-green-700 text-lg"
                                        size="lg"
                                    >
                                        {processingPayment ? <Loader className="animate-spin h-6 w-6" /> : 'Pay with M-Pesa'}
                                    </Button>
                                </form>
                            </>
                        ) : !pollTimedOut ? (
                            <div className="text-center py-8">
                                <div className="bg-green-100 text-green-600 rounded-full w-20 h-20 flex items-center justify-center mx-auto mb-6">
                                    <Check className="h-10 w-10" />
                                </div>
                                <h2 className="text-2xl font-bold text-foreground mb-2">Check your phone!</h2>
                                <p className="text-muted-foreground mb-2">Enter your M-Pesa PIN to complete the payment.</p>
                                <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground mb-6">
                                    <Loader className="h-4 w-4 animate-spin" />
                                    Connecting you automatically once it's received...
                                </div>
                                <Button
                                    variant="secondary"
                                    onClick={() => { setSelectedPlan(null); setPaymentSuccess(false); setPollTimedOut(false); }}
                                    className="w-full"
                                >
                                    Close (keeps checking in the background)
                                </Button>
                            </div>
                        ) : (
                            <div className="text-center py-8">
                                <div className="bg-amber-100 text-amber-600 rounded-full w-20 h-20 flex items-center justify-center mx-auto mb-6">
                                    <Loader className="h-10 w-10" />
                                </div>
                                <h2 className="text-2xl font-bold text-foreground mb-2">Still waiting...</h2>
                                <p className="text-muted-foreground mb-6">
                                    This is taking longer than usual. If you've already entered your M-Pesa PIN, check again below --
                                    otherwise the STK prompt may have expired and you can try paying again.
                                </p>
                                <div className="flex gap-3">
                                    <Button
                                        onClick={() => { setPollTimedOut(false); checkStatus(); }}
                                        className="flex-1"
                                    >
                                        Check Again
                                    </Button>
                                    <Button
                                        variant="secondary"
                                        onClick={() => { setSelectedPlan(null); setPaymentSuccess(false); setPollTimedOut(false); }}
                                        className="flex-1"
                                    >
                                        Close
                                    </Button>
                                </div>
                            </div>
                        )}
                    </Card>
                </div>
            )}
        </div>
    );
};

export default CaptivePortal;
