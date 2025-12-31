import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { useAuthStore } from './store/authStore';

// Pages
import Login from './pages/Login';
import Register from './pages/Register';
import CustomerDashboard from './pages/customer/Dashboard';
import Plans from './pages/customer/Plans';
import Payment from './pages/customer/Payment';
import Usage from './pages/customer/Usage';
import CaptivePortal from './pages/portal/CaptivePortal';
import VoucherManager from './pages/admin/VoucherManager';
// MikroTikSync page moved to Django Admin

const queryClient = new QueryClient();

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" />;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Toaster position="top-right" />
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

          {/* Admin Routes - Migrated to Django Admin */}
          <Route
            path="/admin/vouchers"
            element={
              <PrivateRoute>
                <VoucherManager />
              </PrivateRoute>
            }
          />

          <Route path="/" element={<Navigate to="/dashboard" />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
