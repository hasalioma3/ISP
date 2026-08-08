import axios from 'axios';

// Use relative path by default to leverage Nginx proxy
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

// Create axios instance
const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Request interceptor to add auth token
api.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('access_token');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => Promise.reject(error)
);

// Response interceptor for error handling
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        if (error.response?.status === 401) {
            // Clear tokens and redirect to login
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            window.location.href = '/login';
        }
        return Promise.reject(error);
    }
);

// Auth API
export const authAPI = {
    register: (data: any) => api.post('/customers/register/', data),
    login: (data: any) => api.post('/customers/login/', data),
    getProfile: () => api.get('/customers/profile/'),
    updateProfile: (data: any) => api.put('/customers/profile/update/', data),
    changePassword: (data: { old_password: string; new_password: string }) =>
        api.post('/customers/profile/change-password/', data),
};

// Billing API
export const billingAPI = {
    getPlans: () => api.get('/billing/plans/'),
    createPlan: (data: any) => api.post('/billing/plans/', data),
    updatePlan: (id: number, data: any) => api.patch(`/billing/plans/${id}/`, data),
    deletePlan: (id: number) => api.delete(`/billing/plans/${id}/`),
    getCurrentSubscription: () => api.get('/billing/subscriptions/current/'),
    getSubscriptions: () => api.get('/billing/subscriptions/'),
    getTransactions: () => api.get('/billing/transactions/'),
    getUsage: () => api.get('/billing/usage/'),
    downloadPlanTemplate: () => api.get('/billing/plans/csv-template/', { responseType: 'blob' }),
    importPlansCSV: (file: File) => {
        const formData = new FormData();
        formData.append('file', file);
        return api.post('/billing/plans/import-csv/', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
    },
    downloadPppoeTemplate: () => api.get('/billing/pppoe-import-template/', { responseType: 'blob' }),
    importPppoeCSV: (file: File) => {
        const formData = new FormData();
        formData.append('file', file);
        return api.post('/billing/pppoe-import/', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
    },
};

// Network API (customer-facing subset)
export const networkAPI = {
    getMySession: () => api.get('/network/my-session/'),
};

// Payment API
export const paymentAPI = {
    initiatePayment: (data: { plan_id: number; phone_number: string; mac_address?: string }) =>
        api.post('/payments/initiate/', data),
    getPaymentStatus: (paymentRequestId: number) =>
        api.get(`/payments/status/${paymentRequestId}/`),
    getPaymentRequests: () => api.get('/payments/requests/'),
    reactivateSession: (mpesaCode: string, macAddress?: string) =>
        api.post('/payments/reactivate/', { mpesa_code: mpesaCode, mac_address: macAddress }),
};

// Voucher API
export const voucherAPI = {
    getBatches: () => api.get('/billing/batches/'),
    generate: (data: { quantity: number; value: number; note?: string }) =>
        api.post('/billing/vouchers/generate/', data),
    redeem: (code: string, macAddress?: string) =>
        api.post('/billing/vouchers/redeem/', { code, mac_address: macAddress }),
};

// Analytics API
export const analyticsAPI = {
    getDashboardStats: () => api.get('/analytics/dashboard/'),
    getDashboardExtra: () => api.get('/analytics/dashboard/extra/'),
    getIncomeReport: (params?: any) => api.get('/analytics/income/', { params }),
    getUsageReport: () => api.get('/analytics/usage/'),
    getUsageChart: () => api.get('/analytics/usage-chart/'),
    getExpiringToday: (page: number, pageSize?: number) =>
        api.get('/analytics/expiring-today/', { params: { page, page_size: pageSize } }),
    getRecentActivity: () => api.get('/analytics/recent-activity/'),
    getRecentPayments: (page: number, pageSize?: number) =>
        api.get('/analytics/recent-payments/', { params: { page, page_size: pageSize } }),
    getDataUsage: (params: {
        period?: string; date?: string; search?: string; router?: string;
        type?: string; sort?: string; limit?: number;
    }) => api.get('/analytics/data-usage/', { params }),
};

// Admin Management API
export const adminAPI = {
    // Subscribers
    getSubscribers: (params?: { search?: string; service_type?: string; status?: string; ordering?: string; router?: string; is_new?: string; page?: number; page_size?: number }) =>
        api.get('/customers/subscribers/', { params }),
    getSubscriber: (id: number) => api.get(`/customers/subscribers/${id}/`),
    updateSubscriber: (id: number, data: any) => api.patch(`/customers/subscribers/${id}/`, data),
    getSubscriberUsage: (id: number) => api.get(`/customers/subscribers/${id}/usage/`),
    topUpSubscriber: (id: number, planId: number, staticIpAddress?: string) =>
        api.post(`/customers/subscribers/${id}/topup/`, { plan_id: planId, static_ip_address: staticIpAddress }),
    addSubscriberBalance: (id: number, amount: number) =>
        api.post(`/customers/subscribers/${id}/add_balance/`, { amount }),
    switchSubscriberPlan: (id: number, planId: number) =>
        api.post(`/customers/subscribers/${id}/switch_plan/`, { plan_id: planId }),

    // Staff
    getStaff: () => api.get('/customers/staff/'),
    createStaff: (data: any) => api.post('/customers/staff/', data),
    updateStaff: (id: number, data: any) => api.patch(`/customers/staff/${id}/`, data),
    deleteStaff: (id: number) => api.delete(`/customers/staff/${id}/`),

    // Routers
    getRouters: () => api.get('/network/routers/'),
    createRouter: (data: any) => api.post('/network/routers/', data),
    updateRouter: (id: number, data: any) => api.patch(`/network/routers/${id}/`, data),
    deleteRouter: (id: number) => api.delete(`/network/routers/${id}/`),
    provisionRouter: (id: number, username: string, password: string, portalUrl?: string) =>
        api.post(`/network/routers/${id}/provision/`, { username, password, portal_url: portalUrl }),
    backupRouter: (id: number) => api.post(`/network/routers/${id}/backup/`),
    syncRouterProfiles: (id: number) => api.post(`/network/routers/${id}/sync_profiles/`),
    syncRouterUsers: (id: number) => api.post(`/network/routers/${id}/sync_users/`),
    getRouterHealth: () => api.get('/network/routers/health/'),
    testRouterConnection: (data: { ip_address: string; username: string; password: string; port?: number; use_ssl?: boolean }) =>
        api.post('/network/routers/test_connection/', data),

    // Online Users
    getOnlineUsers: (type?: 'hotspot' | 'pppoe') => api.get('/network/online-users/', { params: { type } }),
    syncOnlineUsers: () => api.post('/network/online-users/'),
    disconnectUser: (sessionId: number) => api.post(`/network/online-users/${sessionId}/disconnect/`),

    // Manual Actions
    manualSubscribe: (data: any) => api.post('/billing/manual-subscribe/', data),
};

// Site Settings (branding: company name + logo)
export const siteSettingsAPI = {
    get: () => api.get('/settings/site/'),
    update: (data: { company_name?: string; logo?: File }) => {
        const form = new FormData();
        if (data.company_name !== undefined) form.append('company_name', data.company_name);
        if (data.logo) form.append('logo', data.logo);
        return api.patch('/settings/site/', form, { headers: { 'Content-Type': 'multipart/form-data' } });
    },
};

export default api;
