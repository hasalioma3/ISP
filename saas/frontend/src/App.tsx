import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import {
    Banknote, CreditCard, FileText, LayoutGrid, Receipt, Server, Settings, SlidersHorizontal, Tags, Users, Wallet,
} from 'lucide-react';
import Shell, { type NavItem } from '~/components/Shell';
import { Spinner } from '~/components/ui';
import { homeFor, useAuth } from '~/lib/auth';

const Login = lazy(() => import('~/pages/public/Login'));
const Signup = lazy(() => import('~/pages/public/Signup'));
const Dashboard = lazy(() => import('~/pages/admin/Dashboard'));
const Tenants = lazy(() => import('~/pages/admin/Tenants'));
const TenantDetail = lazy(() => import('~/pages/admin/TenantDetail'));
const Pricing = lazy(() => import('~/pages/admin/Pricing'));
const Payments = lazy(() => import('~/pages/admin/Payments'));
const Invoices = lazy(() => import('~/pages/admin/Invoices'));
const Payouts = lazy(() => import('~/pages/admin/Payouts'));
const PlatformSettings = lazy(() => import('~/pages/admin/Settings'));
const Team = lazy(() => import('~/pages/admin/Team'));
const PortalOverview = lazy(() => import('~/pages/portal/Overview'));
const PortalBilling = lazy(() => import('~/pages/portal/Billing'));
const PortalPayouts = lazy(() => import('~/pages/portal/Payouts'));
const PortalSettings = lazy(() => import('~/pages/portal/AccountSettings'));

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 } } });

const ADMIN_NAV: NavItem[] = [
    { name: 'Overview', href: '/admin', icon: LayoutGrid },
    { name: 'ISPs', href: '/admin/tenants', icon: Server },
    { name: 'Payments', href: '/admin/payments', icon: CreditCard },
    { name: 'Invoices', href: '/admin/invoices', icon: FileText },
    { name: 'Payouts', href: '/admin/payouts', icon: Banknote },
    { name: 'Pricing', href: '/admin/pricing', icon: Tags },
    { name: 'Team', href: '/admin/team', icon: Users, adminOnly: true },
    { name: 'Settings', href: '/admin/settings', icon: Settings },
];

const PORTAL_NAV: NavItem[] = [
    { name: 'My system', href: '/account', icon: LayoutGrid },
    { name: 'Billing', href: '/account/billing', icon: Receipt },
    { name: 'Payouts', href: '/account/payouts', icon: Wallet },
    { name: 'Settings', href: '/account/settings', icon: SlidersHorizontal },
];

function Guard({ platform, children }: { platform: boolean; children: React.ReactNode }) {
    const user = useAuth((s) => s.user);
    if (!user) return <Navigate to="/login" replace />;
    if (platform !== user.is_platform) return <Navigate to={homeFor(user)} replace />;
    return <>{children}</>;
}

function Home() {
    return <Navigate to={homeFor(useAuth.getState().user)} replace />;
}

const Loading = () => <div className="grid min-h-[40vh] place-items-center text-muted-foreground"><Spinner className="h-6 w-6" /></div>;

export default function App() {
    return (
        <QueryClientProvider client={queryClient}>
            <BrowserRouter>
                <Suspense fallback={<Loading />}>
                    <Routes>
                        <Route path="/" element={<Home />} />
                        <Route path="/login" element={<Login />} />
                        <Route path="/signup" element={<Signup />} />
                        <Route path="/admin" element={<Guard platform><Shell nav={ADMIN_NAV} brand="ISP Cloud" home="/admin" /></Guard>}>
                            <Route index element={<Dashboard />} />
                            <Route path="tenants" element={<Tenants />} />
                            <Route path="tenants/:id" element={<TenantDetail />} />
                            <Route path="payments" element={<Payments />} />
                            <Route path="invoices" element={<Invoices />} />
                            <Route path="payouts" element={<Payouts />} />
                            <Route path="pricing" element={<Pricing />} />
                            <Route path="team" element={<Team />} />
                            <Route path="settings" element={<PlatformSettings />} />
                        </Route>
                        <Route path="/account" element={<Guard platform={false}><Shell nav={PORTAL_NAV} brand="ISP Cloud" home="/account" /></Guard>}>
                            <Route index element={<PortalOverview />} />
                            <Route path="billing" element={<PortalBilling />} />
                            <Route path="payouts" element={<PortalPayouts />} />
                            <Route path="settings" element={<PortalSettings />} />
                        </Route>
                        <Route path="*" element={<Home />} />
                    </Routes>
                </Suspense>
            </BrowserRouter>
            <Toaster position="top-right" toastOptions={{ style: { fontSize: 14, borderRadius: 14 } }} />
        </QueryClientProvider>
    );
}
