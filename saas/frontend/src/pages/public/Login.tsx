import { useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { Panel } from '@/components/savanna';
import { Button, Field, Input, Notice, Spinner } from '~/components/ui';
import { api, errorText } from '~/lib/api';
import { homeFor, useAuth } from '~/lib/auth';
import AuthLayout from './AuthLayout';

export default function Login() {
    const user = useAuth((s) => s.user);
    const setAuth = useAuth((s) => s.setAuth);
    const navigate = useNavigate();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);
    if (user) return <Navigate to={homeFor(user)} replace />;

    const submit = async (e: React.FormEvent) => {
        e.preventDefault();
        setBusy(true);
        setError('');
        try {
            const { data } = await api.post('/auth/login/', { email, password });
            setAuth(data.user, data.access, data.refresh);
            navigate(homeFor(data.user));
        } catch (err) {
            setError(errorText(err, 'Could not sign in'));
        } finally {
            setBusy(false);
        }
    };

    return (
        <AuthLayout title="Run your ISP from one place." pitch="Billing, M-Pesa, MikroTik automation, vouchers and customer messaging, hosted for you.">
            <Panel>
                <h2 className="text-[22px] font-extrabold">Sign in</h2>
                <p className="mt-1 text-[13.5px] text-muted-foreground">ISP owners and the platform team sign in here.</p>
                <form onSubmit={submit} className="mt-6 space-y-4">
                    <Field label="Email"><Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
                    <Field label="Password"><Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
                    {error && <Notice tone="bad">{error}</Notice>}
                    <Button type="submit" size="lg" className="w-full" disabled={busy}>{busy && <Spinner />}Sign in</Button>
                </form>
                <p className="mt-5 text-center text-[13.5px] text-muted-foreground">
                    New here? <Link to="/signup" className="font-semibold text-primary hover:underline">Start a free trial</Link>
                </p>
            </Panel>
        </AuthLayout>
    );
}
