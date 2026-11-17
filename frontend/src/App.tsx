import { Suspense, lazy, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { useAuthStore } from './store/authStore';
import { useSiteSettings } from './hooks/useSiteSettings';

// The captive portal and login pages load eagerly; everything behind a
// login is split into its own chunk. The portal runs on hotspot phones
// behind a MikroTik walled garden, so it must not download Recharts, Radix
// or the admin pages just to show a package list.
import CaptivePortal from './pages/portal/CaptivePortal';

const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));

const CustomerDashboard = lazy(() => import('./pages/customer/Dashboard'));
const Plans = lazy(() => import('./pages/customer/Plans'));
const Payment = lazy(() => import('./pages/customer/Payment'));
const Usage = lazy(() => import('./pages/customer/Usage'));
const OrderHistory = lazy(() => import('./pages/customer/OrderHistory'));
const ActivationHistory = lazy(() => import('./pages/customer/ActivationHistory'));
const CustomerLayout = lazy(() => import('./components/CustomerLayout'));
const AdminLayout = lazy(() => import('./components/AdminLayout'));
const AdminDashboard = lazy(() => import('./pages/admin/Dashboard'));
const Subscribers = lazy(() => import('./pages/admin/Subscribers'));
const Reports = lazy(() => import('./pages/admin/Reports'));
const Settings = lazy(() => import('./pages/admin/Settings'));
const VoucherManager = lazy(() => import('./pages/admin/VoucherManager'));
const MikroTikSync = lazy(() => import('./pages/admin/MikroTikSync'));
const OnlineUsers = lazy(() => import('./pages/admin/OnlineUsers'));
const BillingPlans = lazy(() => import('./pages/admin/BillingPlans'));
const DataUsage = lazy(() => import('./pages/admin/DataUsage'));
const Payments = lazy(() => import('./pages/admin/Payments'));
const Accounting = lazy(() => import('./pages/admin/Accounting'));
const Inventory = lazy(() => import('./pages/admin/Inventory'));
const NetworkOps = lazy(() => import('./pages/admin/NetworkOps'));
const NotificationReport = lazy(() => import('./pages/admin/NotificationReport'));
const AuditLogs = lazy(() => import('./pages/admin/AuditLogs'));
const Invoices = lazy(() => import('./pages/admin/Invoices'));
const Loyalty = lazy(() => import('./pages/admin/Loyalty'));

/** Shown while a lazily loaded page's chunk downloads. */
function PageFallback() {
  return (
    <div className="grid min-h-[40vh] place-items-center" aria-busy="true" aria-label="Loading">
      <div className="h-8 w-8 animate-spin rounded-full border-[3px] border-chip border-t-primary" />
    </div>
  );
}

const queryClient = new QueryClient();

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" />;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  if (!isAuthenticated) return <Navigate to="/login" />;
  if (!user?.is_staff && !user?.is_superuser) return <Navigate to="/dashboard" />;

  return <>{children}</>;
}

function FaviconUpdater() {
  const { data } = useSiteSettings();

  useEffect(() => {
    if (data?.company_name) {
      document.title = data.company_name;
    }
  }, [data?.company_name]);

  useEffect(() => {
    if (!data?.favicon) return;
    let link = document.querySelector<HTMLLinkElement>("link[rel~='icon']");
    if (!link) {
      link = document.createElement('link');
      link.rel = 'icon';
      document.head.appendChild(link);
    }
    link.type = 'image/png';
    link.href = data.favicon;
  }, [data?.favicon]);

  return null;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Toaster position="top-right" />
        <FaviconUpdater />
        <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/portal" element={<CaptivePortal />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />

          <Route path="/plans" element={<Plans />} />
          <Route path="/payment" element={<Payment />} />

          {/* Customer Portal Routes */}
          <Route
            element={
              <PrivateRoute>
                <CustomerLayout />
              </PrivateRoute>
            }
          >
            <Route path="/dashboard" element={<CustomerDashboard />} />
            <Route path="/usage" element={<Usage />} />
            <Route path="/orders" element={<OrderHistory />} />
            <Route path="/activations" element={<ActivationHistory />} />
          </Route>

          {/* Admin Routes */}
          <Route
            path="/admin"
            element={
              <AdminRoute>
                <AdminLayout />
              </AdminRoute>
            }
          >
            <Route path="dashboard" element={<AdminDashboard />} />
            <Route path="subscribers" element={<Subscribers />} />
            <Route path="online-users" element={<OnlineUsers />} />
            <Route path="data-usage" element={<DataUsage />} />
            <Route path="network-ops" element={<NetworkOps />} />
            <Route path="payments" element={<Payments />} />
            <Route path="accounting" element={<Accounting />} />
            <Route path="inventory" element={<Inventory />} />
            <Route path="reports" element={<Reports />} />
            <Route path="settings" element={<Settings />} />
            <Route path="vouchers" element={<VoucherManager />} />
            <Route path="mikrotik" element={<MikroTikSync />} />
            <Route path="billing-plans" element={<BillingPlans />} />
            <Route path="messages" element={<NotificationReport />} />
            <Route path="logs" element={<AuditLogs />} />
            <Route path="invoices" element={<Invoices />} />
            <Route path="loyalty" element={<Loyalty />} />
            <Route index element={<Navigate to="dashboard" />} />
          </Route>

          <Route path="/" element={<Navigate to="/dashboard" />} />
        </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
