import { useState, useEffect } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { authAPI } from '../services/api';
import { useAuthStore } from '../store/authStore';
import toast from 'react-hot-toast';
import { LogIn } from 'lucide-react';
import { useSiteSettings } from '../hooks/useSiteSettings';
import { Card } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';

export default function Login() {
    const navigate = useNavigate();
    const setAuth = useAuthStore((state) => state.setAuth);
    const { data: siteSettings } = useSiteSettings();
    const [formData, setFormData] = useState({
        username: '',
        password: '',
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
        setLoading(true);

        try {
            const response = await authAPI.login(formData);
            const { customer, tokens } = response.data;

            setAuth(customer, tokens.access, tokens.refresh);
            toast.success('Login successful!');
            navigate('/dashboard');
        } catch (error: any) {
            toast.error(error.response?.data?.error || 'Login failed');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-secondary flex items-center justify-center p-4">
            <Card className="shadow-lg p-8 w-full max-w-md">
                <div className="text-center mb-8">
                    {siteSettings?.logo ? (
                        <img
                            src={siteSettings.logo}
                            alt={siteSettings.company_name}
                            className="w-16 h-16 rounded-2xl object-contain bg-accent mx-auto mb-4"
                        />
                    ) : (
                        <div className="inline-flex items-center justify-center w-16 h-16 bg-primary/10 rounded-2xl mb-4">
                            <LogIn className="w-8 h-8 text-primary" />
                        </div>
                    )}
                    <h1 className="text-2xl font-bold text-foreground">{siteSettings?.company_name || 'ISP Billing'}</h1>
                    <p className="text-muted-foreground mt-1.5 text-sm">Login to your account</p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-5">
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

                    <Button type="submit" disabled={loading} className="w-full" size="lg">
                        {loading ? 'Logging in...' : 'Login'}
                    </Button>
                </form>

                <p className="text-center text-muted-foreground mt-6 text-sm">
                    Don't have an account?{' '}
                    <Link to="/register" className="text-primary font-semibold hover:underline">
                        Register
                    </Link>
                </p>
            </Card>
        </div>
    );
}
