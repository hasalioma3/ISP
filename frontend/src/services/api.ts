import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

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
    initiatePayment: (data: { plan_id: number; phone_number: string }) =>
        api.post('/payments/initiate/', data),
    getPaymentStatus: (paymentRequestId: number) =>
        api.get(`/payments/status/${paymentRequestId}/`),
    getPaymentRequests: () => api.get('/payments/requests/'),
};

export default api;
