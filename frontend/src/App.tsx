import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { useAuthStore } from './store/authStore';
import { useSiteSettings } from './hooks/useSiteSettings';

// Pages
import Login from './pages/Login';
import Register from './pages/Register';
import CustomerDashboard from './pages/customer/Dashboard';
import Plans from './pages/customer/Plans';
import Payment from './pages/customer/Payment';
import Usage from './pages/customer/Usage';
import CaptivePortal from './pages/portal/CaptivePortal';
import AdminLayout from './components/AdminLayout';
import AdminDashboard from './pages/admin/Dashboard';
import Subscribers from './pages/admin/Subscribers';
import Reports from './pages/admin/Reports';
import Settings from './pages/admin/Settings';
import VoucherManager from './pages/admin/VoucherManager';
import MikroTikSync from './pages/admin/MikroTikSync';
import OnlineUsers from './pages/admin/OnlineUsers';
import BillingPlans from './pages/admin/BillingPlans';
import DataUsage from './pages/admin/DataUsage';

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
        <Routes>
          <Route path="/portal" element={<CaptivePortal />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />

          <Route
            path="/dashboard"
            element={
              <PrivateRoute>
                <CustomerDashboard />
              </PrivateRoute>
            }
          />
          <Route path="/plans" element={<Plans />} />
          <Route path="/payment" element={<Payment />} />
          <Route
            path="/usage"
            element={
              <PrivateRoute>
                <Usage />
              </PrivateRoute>
            }
          />

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
            <Route path="reports" element={<Reports />} />
            <Route path="settings" element={<Settings />} />
            <Route path="vouchers" element={<VoucherManager />} />
            <Route path="mikrotik" element={<MikroTikSync />} />
            <Route path="billing-plans" element={<BillingPlans />} />
            <Route index element={<Navigate to="dashboard" />} />
          </Route>

          <Route path="/" element={<Navigate to="/dashboard" />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
