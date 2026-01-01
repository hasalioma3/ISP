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
export const voucherAPI = {
    getBatches: () => api.get('/billing/batches/'),
    generate: (data: { quantity: number; value: number; note?: string }) =>
        api.post('/billing/vouchers/generate/', data),
    redeem: (code: string) =>
        api.post('/billing/vouchers/redeem/', { code }),
};

// Analytics API
export const analyticsAPI = {
    getDashboardStats: () => api.get('/analytics/dashboard/'),
    getIncomeReport: (params?: any) => api.get('/analytics/income/', { params }),
    getUsageReport: () => api.get('/analytics/usage/'),
};

// Admin Management API
export const adminAPI = {
    // Subscribers
    getSubscribers: (search?: string) => api.get('/customers/subscribers/', { params: { search } }),

    // Staff
    getStaff: () => api.get('/customers/staff/'),
    createStaff: (data: any) => api.post('/customers/staff/', data),
    updateStaff: (id: number, data: any) => api.put(`/customers/staff/${id}/`, data),
    deleteStaff: (id: number) => api.delete(`/customers/staff/${id}/`),

    // Routers
    getRouters: () => api.get('/network/routers/'),
    createRouter: (data: any) => api.post('/network/routers/', data),
    updateRouter: (id: number, data: any) => api.put(`/network/routers/${id}/`, data),
    deleteRouter: (id: number) => api.delete(`/network/routers/${id}/`),

    // Manual Actions
    manualSubscribe: (data: any) => api.post('/billing/manual-subscribe/', data),
};

export default api;
