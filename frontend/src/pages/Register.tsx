import { useState, useEffect } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { authAPI } from '../services/api';
import { useAuthStore } from '../store/authStore';
import toast from 'react-hot-toast';
import { UserPlus } from 'lucide-react';
import { useSiteSettings } from '../hooks/useSiteSettings';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';

export default function Register() {
    const navigate = useNavigate();
    const setAuth = useAuthStore((state) => state.setAuth);
    const { data: siteSettings } = useSiteSettings();
    const [formData, setFormData] = useState({
        username: '',
        email: '',
        password: '',
        password2: '',
        phone_number: '',
        first_name: '',
        last_name: '',
        service_type: 'pppoe',
    });
    const [loading, setLoading] = useState(false);

    // Capture MAC from URL if present (from Captive Portal)
    const [searchParams] = useSearchParams();
    useEffect(() => {
        const mac = searchParams.get('mac');
        if (mac) {
            localStorage.setItem('hotspot_mac', mac);
        }
    }, [searchParams]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (formData.password !== formData.password2) {
            toast.error('Passwords do not match');
            return;
        }

        setLoading(true);

        try {
            const response = await authAPI.register(formData);
            const { customer, tokens } = response.data;

            setAuth(customer, tokens.access, tokens.refresh);
            toast.success('Registration successful!');
            navigate('/dashboard');
        } catch (error: any) {
            const errors = error.response?.data;
            if (errors) {
                Object.values(errors).forEach((err: any) => {
                    toast.error(Array.isArray(err) ? err[0] : err);
                });
            } else {
                toast.error('Registration failed');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-secondary flex items-center justify-center p-4 py-10">
            <Card className="shadow-lg p-8 w-full max-w-2xl">
                <div className="text-center mb-8">
                    {siteSettings?.logo ? (
                        <img
                            src={siteSettings.logo}
                            alt={siteSettings.company_name}
                            className="w-16 h-16 rounded-2xl object-contain bg-accent mx-auto mb-4"
                        />
                    ) : (
                        <div className="inline-flex items-center justify-center w-16 h-16 bg-primary/10 rounded-2xl mb-4">
                            <UserPlus className="w-8 h-8 text-primary" />
                        </div>
                    )}
                    {siteSettings?.company_name && (
                        <p className="text-xs font-semibold text-primary uppercase tracking-wide mb-1">{siteSettings.company_name}</p>
                    )}
                    <h1 className="text-2xl font-bold text-foreground">Create Account</h1>
                    <p className="text-muted-foreground mt-1.5 text-sm">Register for ISP services</p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="first_name">First Name</Label>
                            <Input
                                id="first_name"
                                type="text"
                                required
                                value={formData.first_name}
                                onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="last_name">Last Name</Label>
                            <Input
                                id="last_name"
                                type="text"
                                required
                                value={formData.last_name}
                                onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="username">Username</Label>
                        <Input
                            id="username"
                            type="text"
                            required
                            value={formData.username}
                            onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                        />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="email">Email</Label>
                            <Input
                                id="email"
                                type="email"
                                required
                                value={formData.email}
                                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="phone_number">Phone Number</Label>
                            <Input
                                id="phone_number"
                                type="tel"
                                required
                                placeholder="0712345678"
                                value={formData.phone_number}
                                onChange={(e) => setFormData({ ...formData, phone_number: e.target.value })}
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="service_type">Service Type</Label>
                        <select
                            id="service_type"
                            className="flex h-10 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                            value={formData.service_type}
                            onChange={(e) => setFormData({ ...formData, service_type: e.target.value })}
                        >
                            <option value="pppoe">PPPoE</option>
                            <option value="hotspot">Hotspot</option>
                            <option value="both">Both</option>
                        </select>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="password">Password</Label>
                            <Input
                                id="password"
                                type="password"
                                required
                                value={formData.password}
                                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="password2">Confirm Password</Label>
                            <Input
                                id="password2"
                                type="password"
                                required
                                value={formData.password2}
                                onChange={(e) => setFormData({ ...formData, password2: e.target.value })}
                            />
                        </div>
                    </div>

                    <Button type="submit" disabled={loading} className="w-full mt-2" size="lg">
                        {loading ? 'Creating account...' : 'Register'}
                    </Button>
                </form>

                <p className="text-center text-muted-foreground mt-6 text-sm">
                    Already have an account?{' '}
                    <Link to="/login" className="text-primary font-semibold hover:underline">
                        Login
                    </Link>
                </p>
            </Card>
        </div>
    );
}
