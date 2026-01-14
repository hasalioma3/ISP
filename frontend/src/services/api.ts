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
};

// Billing API
export const billingAPI = {
    getPlans: () => api.get('/billing/plans/'),
    createPlan: (data: any) => api.post('/billing/plans/', data),
    updatePlan: (id: number, data: any) => api.put(`/billing/plans/${id}/`, data),
    deletePlan: (id: number) => api.delete(`/billing/plans/${id}/`),
    getCurrentSubscription: () => api.get('/billing/subscriptions/current/'),
    getTransactions: () => api.get('/billing/transactions/'),
    getUsage: () => api.get('/billing/usage/'),
};

// Payment API
export const paymentAPI = {
    initiatePayment: (data: { plan_id: number; phone_number: string; mac_address?: string }) =>
        api.post('/payments/initiate/', data),
    getPaymentStatus: (paymentRequestId: number) =>
        api.get(`/payments/status/${paymentRequestId}/`),
    getPaymentRequests: () => api.get('/payments/requests/'),
};

// Voucher API
// Voucher API definition moved below to include batch details extension

// Analytics API
export const analyticsAPI = {
    getDashboardStats: () => api.get('/analytics/dashboard/'),
    getIncomeReport: (params?: any) => api.get('/analytics/income/', { params }),
    getUsageReport: (limit?: number) => api.get('/analytics/usage/', { params: { limit } }),
    getMonthlyAnalytics: () => api.get('/analytics/monthly/'),
};

// Admin Management API
export const adminAPI = {
    // Subscribers
    getSubscribers: (search?: string) => api.get('/customers/subscribers/', { params: { search } }),
    getSubscriber: (id: string | number) => api.get(`/customers/subscribers/${id}/`),

    // Staff
    getStaff: () => api.get('/customers/staff/'),
    createStaff: (data: any) => api.post('/customers/staff/', data),
    updateStaff: (id: number, data: any) => api.put(`/customers/staff/${id}/`, data),
    deleteStaff: (id: number) => api.delete(`/customers/staff/${id}/`),

    // Routers
    getRouters: () => api.get('/network/routers/'),
    getNetworkActivity: () => api.get('/network/routers/total_activity/'),
    createRouter: (data: any) => api.post('/network/routers/', data),
    updateRouter: (id: number, data: any) => api.put(`/network/routers/${id}/`, data),
    deleteRouter: (id: number) => api.delete(`/network/routers/${id}/`),
    configureRouter: (id: number) => api.post(`/network/routers/${id}/configure/`),

    // Manual Actions
    manualSubscribe: (data: any) => api.post('/billing/manual-subscribe/', data),
    toggleStatus: (id: number) => api.post(`/customers/subscribers/${id}/toggle_status/`),
};

// Update Voucher API to include batch details
export const voucherAPI = {
    getBatches: () => api.get('/billing/batches/'),
    getBatchVouchers: (id: number) => api.get(`/billing/batches/${id}/vouchers/`),
    generate: (data: { quantity: number; value: number; note?: string }) =>
        api.post('/billing/vouchers/generate/', data),
    redeem: (code: string) =>
        api.post('/billing/vouchers/redeem/', { code }),
};

// Core/Tenant API
export const coreAPI = {
    getConfig: () => api.get('/core/config/'),
    updateConfig: (data: FormData) => api.put('/core/config/', data, {
        headers: { 'Content-Type': 'multipart/form-data' }
    }),
    getBranding: () => api.get('/core/branding/'),
};

export default api;
