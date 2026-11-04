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

// Builds a multipart form from a plain data object plus an attachment file
// -- only used where a record can carry a file (expenses, inventory
// purchases), and only when a file is actually attached (plain JSON is
// lighter and keeps working for every other edit).
function toFormData(data: Record<string, any>, file?: File | null) {
    const form = new FormData();
    Object.entries(data).forEach(([key, value]) => {
        if (value !== undefined && value !== null) form.append(key, value as any);
    });
    if (file) form.append('attachment', file);
    return form;
}

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
    purchaseWithBalance: (planId: number) => api.post('/billing/purchase-with-balance/', { plan_id: planId }),
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
    send: (voucherId: number, data: { recipient: string; channel: 'sms' | 'whatsapp' | 'telegram' }) =>
        api.post(`/billing/vouchers/${voucherId}/send/`, data),
};

// Notifications (SMS/WhatsApp/Telegram settings, test-send, promo broadcast)
export const notificationAPI = {
    getSettings: () => api.get('/notifications/settings/'),
    updateSettings: (data: any) => api.patch('/notifications/settings/', data),
    testSend: (data: { channel: 'sms' | 'whatsapp' | 'telegram'; recipient: string; message?: string }) =>
        api.post('/notifications/test-send/', data),
    getWhatsAppStatus: () => api.get('/notifications/whatsapp/status/'),
    broadcast: (data: { message: string; channels: string[]; service_type?: string; dry_run?: boolean }) =>
        api.post('/notifications/promo-broadcast/', data),
};

// Analytics API
export const analyticsAPI = {
    getDashboardStats: () => api.get('/analytics/dashboard/'),
    getDashboardExtra: () => api.get('/analytics/dashboard/extra/'),
    getIncomeReport: (params?: any) => api.get('/analytics/income/', { params }),
    getVoucherUsageReport: (params?: any) => api.get('/analytics/voucher-usage/', { params }),
    downloadVoucherUsageReport: (params?: any) =>
        api.get('/analytics/voucher-usage/', { params: { ...params, export: 'csv' }, responseType: 'blob' }),
    getUsageReport: () => api.get('/analytics/usage/'),
    getUsageChart: () => api.get('/analytics/usage-chart/'),
    getExpiringToday: (page: number, pageSize?: number) =>
        api.get('/analytics/expiring-today/', { params: { page, page_size: pageSize } }),
    getRecentActivity: () => api.get('/analytics/recent-activity/'),
    getRecentPayments: (page: number, pageSize?: number) =>
        api.get('/analytics/recent-payments/', { params: { page, page_size: pageSize } }),
    getRouterBandwidthTrend: (params: { router: number; period?: string; date?: string }) =>
        api.get('/analytics/router-bandwidth/', { params }),
    getChurnForecast: (days?: number) =>
        api.get('/analytics/churn-forecast/', { params: { days } }),
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
    syncHotspotLoginPage: (id: number) => api.post(`/network/routers/${id}/sync_hotspot_login_page/`),
    backupRouter: (id: number) => api.post(`/network/routers/${id}/backup/`),
    syncRouterProfiles: (id: number) => api.post(`/network/routers/${id}/sync_profiles/`),
    syncRouterUsers: (id: number) => api.post(`/network/routers/${id}/sync_users/`),
    enableAcsProvisioning: (id: number) => api.post(`/network/routers/${id}/enable_acs_provisioning/`),
    enableWanAccess: (id: number) => api.post(`/network/routers/${id}/enable_wan_access/`),
    disableWanAccess: (id: number) => api.post(`/network/routers/${id}/disable_wan_access/`),
    restartRouter: (id: number) => api.post(`/network/routers/${id}/restart/`),
    getMaintenanceSchedule: (id: number) => api.get(`/network/routers/${id}/maintenance_schedule/`),
    setMaintenanceSchedule: (id: number, data: any) => api.post(`/network/routers/${id}/maintenance_schedule/`, data),
    getRouterHealth: (routerId?: number) => api.get('/network/routers/health/', { params: routerId ? { router: routerId } : undefined }),
    testRouterConnection: (data: { ip_address: string; username: string; password: string; port?: number; use_ssl?: boolean }) =>
        api.post('/network/routers/test_connection/', data),

    // Online Users
    getOnlineUsers: (type?: 'hotspot' | 'pppoe') => api.get('/network/online-users/', { params: { type } }),
    syncOnlineUsers: () => api.post('/network/online-users/'),
    disconnectUser: (sessionId: number) => api.post(`/network/online-users/${sessionId}/disconnect/`),

    // Manual Actions
    manualSubscribe: (data: any) => api.post('/billing/manual-subscribe/', data),

    // Payments
    assignC2BPayment: (paymentId: number, customerId: number) =>
        api.post(`/payments/c2b/${paymentId}/assign/`, { customer_id: customerId }),
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

// Accounting (expenses, other income, profit dashboard)
export const accountingAPI = {
    getExpenses: (params?: { search?: string; category?: string; ordering?: string; page?: number; page_size?: number }) =>
        api.get('/accounting/expenses/', { params }),
    createExpense: (data: any, file?: File | null) =>
        file
            ? api.post('/accounting/expenses/', toFormData(data, file), { headers: { 'Content-Type': 'multipart/form-data' } })
            : api.post('/accounting/expenses/', data),
    updateExpense: (id: number, data: any, file?: File | null) =>
        file
            ? api.patch(`/accounting/expenses/${id}/`, toFormData(data, file), { headers: { 'Content-Type': 'multipart/form-data' } })
            : api.patch(`/accounting/expenses/${id}/`, data),
    deleteExpense: (id: number) => api.delete(`/accounting/expenses/${id}/`),

    getOtherIncome: (params?: { search?: string; category?: string; ordering?: string; page?: number; page_size?: number }) =>
        api.get('/accounting/other-income/', { params }),
    createOtherIncome: (data: any) => api.post('/accounting/other-income/', data),
    updateOtherIncome: (id: number, data: any) => api.patch(`/accounting/other-income/${id}/`, data),
    deleteOtherIncome: (id: number) => api.delete(`/accounting/other-income/${id}/`),

    getDashboard: (startDate?: string, endDate?: string) =>
        api.get('/accounting/dashboard/', { params: { start_date: startDate, end_date: endDate } }),
};

// Inventory (items, purchases, usage, stock dashboard)
export const inventoryAPI = {
    getItems: (params?: { search?: string; category?: string; is_active?: boolean; ordering?: string; page?: number; page_size?: number }) =>
        api.get('/inventory/items/', { params }),
    createItem: (data: any) => api.post('/inventory/items/', data),
    updateItem: (id: number, data: any) => api.patch(`/inventory/items/${id}/`, data),
    deleteItem: (id: number) => api.delete(`/inventory/items/${id}/`),

    getPurchases: (params?: { search?: string; item?: number; ordering?: string; page?: number; page_size?: number }) =>
        api.get('/inventory/purchases/', { params }),
    createPurchase: (data: any, file?: File | null) =>
        file
            ? api.post('/inventory/purchases/', toFormData(data, file), { headers: { 'Content-Type': 'multipart/form-data' } })
            : api.post('/inventory/purchases/', data),
    updatePurchase: (id: number, data: any, file?: File | null) =>
        file
            ? api.patch(`/inventory/purchases/${id}/`, toFormData(data, file), { headers: { 'Content-Type': 'multipart/form-data' } })
            : api.patch(`/inventory/purchases/${id}/`, data),
    deletePurchase: (id: number) => api.delete(`/inventory/purchases/${id}/`),

    getUsages: (params?: { search?: string; item?: number; customer?: number; ordering?: string; page?: number; page_size?: number }) =>
        api.get('/inventory/usages/', { params }),
    createUsage: (data: any) => api.post('/inventory/usages/', data),
    updateUsage: (id: number, data: any) => api.patch(`/inventory/usages/${id}/`, data),
    deleteUsage: (id: number) => api.delete(`/inventory/usages/${id}/`),

    getDashboard: () => api.get('/inventory/dashboard/'),
};

// TR-069 CPE devices (Huawei/Tenda/TP-Link customer-premises routers)
export const cpeDeviceAPI = {
    getDevices: (params?: { brand?: string; is_online?: boolean; unlinked?: boolean; search?: string; page?: number; page_size?: number }) =>
        api.get('/tr069/devices/', { params }),
    getDevice: (id: number) => api.get(`/tr069/devices/${id}/`),
    createDevice: (data: { genieacs_device_id: string; serial_number: string; brand: string; customer?: number | null }) =>
        api.post('/tr069/devices/', data),
    updateDevice: (id: number, data: any) => api.patch(`/tr069/devices/${id}/`, data),
    deleteDevice: (id: number) => api.delete(`/tr069/devices/${id}/`),
    linkCustomer: (id: number, customerId: number) => api.post(`/tr069/devices/${id}/link_customer/`, { customer_id: customerId }),
    unlinkCustomer: (id: number) => api.post(`/tr069/devices/${id}/unlink_customer/`),
    reboot: (id: number) => api.post(`/tr069/devices/${id}/reboot/`),
    factoryReset: (id: number) => api.post(`/tr069/devices/${id}/factory_reset/`),
    setWifi: (id: number, data: { ssid: string; password: string }) => api.post(`/tr069/devices/${id}/set_wifi/`, data),
    getDiagnostics: (id: number) => api.get(`/tr069/devices/${id}/diagnostics/`),
    pushFirmware: (id: number, fileName: string) => api.post(`/tr069/devices/${id}/push_firmware/`, { file_name: fileName }),
};

export default api;
