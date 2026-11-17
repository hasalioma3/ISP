import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Check, CheckCircle2, XCircle } from 'lucide-react';
import { Panel, formatKES } from '@/components/savanna';
import { cn } from '@/lib/utils';
import { Button, Field, Input, Notice, Spinner } from '~/components/ui';
import { api, errorText } from '~/lib/api';
import { useAuth } from '~/lib/auth';
import AuthLayout from './AuthLayout';

const SIZES = [50, 200, 500, 1000];

export default function Signup() {
    const navigate = useNavigate();
    const setAuth = useAuth((s) => s.setAuth);
    const { data: cfg } = useQuery({ queryKey: ['public-config'], queryFn: async () => (await api.get('/public/config/')).data });
    const [form, setForm] = useState({ company_name: '', slug: '', full_name: '', email: '', phone: '', password: '', plan: '', accept_terms: false });
    const [slugEdited, setSlugEdited] = useState(false);
    const [slugState, setSlugState] = useState<'idle' | 'checking' | 'ok' | 'taken'>('idle');
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);
    const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

    useEffect(() => {
        if (cfg?.plans?.length && !form.plan) set('plan', (cfg.plans.find((p: any) => p.is_default) || cfg.plans[0]).code);
    }, [cfg]);  // eslint-disable-line react-hooks/exhaustive-deps

    // Suggest the instance ID from the company name until the user edits it.
    useEffect(() => {
        if (slugEdited || !form.company_name.trim()) return;
        const t = setTimeout(async () => {
            const { data } = await api.get('/public/slug/', { params: { name: form.company_name } });
            setForm((f) => ({ ...f, slug: data.slug }));
            setSlugState('ok');
        }, 350);
        return () => clearTimeout(t);
    }, [form.company_name, slugEdited]);

    useEffect(() => {
        if (!slugEdited || !form.slug) return;
        setSlugState('checking');
        const t = setTimeout(async () => {
            const { data } = await api.get('/public/slug/', { params: { slug: form.slug } });
            setSlugState(data.available ? 'ok' : 'taken');
        }, 350);
        return () => clearTimeout(t);
    }, [form.slug, slugEdited]);

    const plan = useMemo(() => cfg?.plans?.find((p: any) => p.code === form.plan), [cfg, form.plan]);

    const submit = async (e: React.FormEvent) => {
        e.preventDefault();
        setBusy(true);
        setErrors({});
        setError('');
        try {
            const { data } = await api.post('/public/signup/', form);
            setAuth(data.user, data.access, data.refresh);
            navigate('/account');
        } catch (err: any) {
            const body = err?.response?.data;
            if (err?.response?.status === 400 && body && typeof body === 'object') {
                setErrors(Object.fromEntries(Object.entries(body).map(([k, v]) => [k, Array.isArray(v) ? String(v[0]) : String(v)])));
            } else {
                setError(errorText(err, 'Sign-up failed'));
            }
        } finally {
            setBusy(false);
        }
    };

    const trialDays = cfg?.trial_days ?? 2;
    return (
        <AuthLayout wide title={`Try it free for ${trialDays} day${trialDays === 1 ? '' : 's'}.`} pitch={
            <ul className="space-y-2.5">
                {['Your own private system and database, ready in minutes', 'M-Pesa STK and paybill payments, settled to your paybill, till or phone',
                    'PPPoE, hotspot and static IP on your MikroTik routers', 'Vouchers, data caps, SMS and WhatsApp reminders',
                    'Every feature on during the trial. No card needed.'].map((t) => (
                    <li key={t} className="flex gap-2.5"><Check className="mt-0.5 h-4 w-4 shrink-0 text-sunset" />{t}</li>
                ))}
            </ul>
        }>
            <Panel>
                <h2 className="text-[22px] font-extrabold">Create your ISP system</h2>
                <p className="mt-1 text-[13.5px] text-muted-foreground">
                    Already have one? <Link to="/login" className="font-semibold text-primary hover:underline">Sign in</Link>
                </p>
                {cfg && !cfg.signup_enabled && <Notice className="mt-4">Sign-ups are closed right now. Please contact us.</Notice>}
                <form onSubmit={submit} className="mt-6 space-y-4">
                    <div className="grid gap-4 sm:grid-cols-2">
                        <Field label="Company name" error={errors.company_name}>
                            <Input required value={form.company_name} onChange={(e) => set('company_name', e.target.value)} placeholder="Acme Wireless" />
                        </Field>
                        <Field label="System ID" error={errors.slug} hint={
                            slugState === 'taken' ? <span className="text-bad"><XCircle className="mr-1 inline h-3.5 w-3.5" />Taken</span>
                                : slugState === 'ok' && form.slug ? <span className="text-ok"><CheckCircle2 className="mr-1 inline h-3.5 w-3.5" />Available</span>
                                    : 'Lowercase letters and digits'}>
                            <Input value={form.slug} onChange={(e) => { setSlugEdited(true); set('slug', e.target.value.toLowerCase().replace(/[^a-z0-9]/g, '')); }} placeholder="acmewireless" />
                        </Field>
                        <Field label="Your name" error={errors.full_name}>
                            <Input required autoComplete="name" value={form.full_name} onChange={(e) => set('full_name', e.target.value)} />
                        </Field>
                        <Field label="Phone (M-Pesa)" error={errors.phone}>
                            <Input required type="tel" autoComplete="tel" value={form.phone} onChange={(e) => set('phone', e.target.value)} placeholder="0712 345 678" />
                        </Field>
                        <Field label="Email" error={errors.email}>
                            <Input required type="email" autoComplete="email" value={form.email} onChange={(e) => set('email', e.target.value)} />
                        </Field>
                        <Field label="Password" error={errors.password} hint="At least 8 characters. You'll also use it for your system's admin account.">
                            <Input required type="password" autoComplete="new-password" value={form.password} onChange={(e) => set('password', e.target.value)} />
                        </Field>
                    </div>

                    {cfg?.plans?.length > 0 && (
                        <div>
                            <p className="mb-2 text-[13px] font-semibold text-foreground/85">Plan after the trial (you can change it later)</p>
                            <div className="grid gap-3 sm:grid-cols-2">
                                {cfg.plans.map((p: any) => (
                                    <button type="button" key={p.code} onClick={() => set('plan', p.code)}
                                        className={cn('rounded-2xl border p-4 text-left transition-colors', form.plan === p.code ? 'border-primary bg-accent' : 'border-border hover:border-border-strong')}>
                                        <p className="font-bold">{p.name}</p>
                                        {p.description && <p className="mt-0.5 text-[12.5px] text-muted-foreground">{p.description}</p>}
                                        <p className="mt-2 text-[12.5px] text-muted-foreground">
                                            {SIZES.map((n, i) => <span key={n}>{i ? ' · ' : ''}{n} subs: <b className="text-foreground">{formatKES(p.examples?.[i]?.amount)}</b></span>)}
                                            {' '}per month
                                        </p>
                                    </button>
                                ))}
                            </div>
                            {plan && <PriceExplainer plan={plan} />}
                        </div>
                    )}

                    <label className="flex items-start gap-2.5 text-[13.5px]">
                        <input type="checkbox" className="mt-1" checked={form.accept_terms} onChange={(e) => set('accept_terms', e.target.checked)} />
                        <span>
                            I agree to the {cfg?.terms_url ? <a href={cfg.terms_url} target="_blank" rel="noreferrer" className="font-semibold text-primary underline">terms of service</a> : 'terms of service'},
                            {' '}including the platform collecting my customers' M-Pesa payments and paying them out to me less the platform fees.
                        </span>
                    </label>
                    {errors.accept_terms && <p className="text-[12.5px] text-bad">{errors.accept_terms}</p>}
                    {error && <Notice tone="bad">{error}</Notice>}
                    <Button type="submit" size="lg" variant="sunset" className="w-full" disabled={busy || slugState === 'taken' || (cfg && !cfg.signup_enabled)}>
                        {busy && <Spinner />}Start my free trial
                    </Button>
                </form>
            </Panel>
        </AuthLayout>
    );
}

function PriceExplainer({ plan }: { plan: any }) {
    const [count, setCount] = useState(200);
    const { data } = useQuery({
        queryKey: ['quote', plan.id, count],
        queryFn: async () => (await api.post('/public/quote/', { plan_id: plan.id, count })).data,
    });
    const types = plan.service_types.split(',').map((t: string) => ({ pppoe: 'PPPoE', hotspot: 'hotspot', static: 'static IP' } as any)[t]).join(', ');
    return (
        <div className="mt-3 rounded-2xl bg-secondary p-4 text-[13px]">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <span>With <b className="num">{count}</b> {plan.count_basis === 'active' ? 'active' : ''} subscribers</span>
                <span className="num text-[16px] font-extrabold">{data ? formatKES(data.amount) : '…'}<span className="text-[12px] font-medium text-muted-foreground"> / month</span></span>
            </div>
            <input type="range" min={0} max={3000} step={10} value={count} onChange={(e) => setCount(Number(e.target.value))} className="mt-2 w-full accent-[var(--sv-primary)]" aria-label="Number of subscribers" />
            <p className="mt-1 text-muted-foreground">Counts {types} subscribers{plan.count_basis === 'active' ? ' with an active plan' : ''}, using the {plan.count_method === 'peak' ? 'highest' : plan.count_method === 'average' ? 'average' : 'end-of-month'} count in the month.</p>
        </div>
    );
}
