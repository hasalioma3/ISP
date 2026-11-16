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
    // { plan_totals, totals }: current plan period and all-time usage.
    getUsageSummary: () => api.get('/billing/usage/summary/'),
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
    generate: (data: { quantity: number; value?: number; plan_id?: number | string; note?: string }) =>
        api.post('/billing/vouchers/generate/', data),
    redeem: (code: string, macAddress?: string) =>
        api.post('/billing/vouchers/redeem/', { code, mac_address: macAddress }),
    send: (voucherId: number, data: { recipient: string; channel: 'sms' | 'whatsapp' | 'telegram' }) =>
        api.post(`/billing/vouchers/${voucherId}/send/`, data),
    salesContacts: () => api.get('/billing/batches/sales-contacts/'),
    sendBatch: (batchId: number, data: { phones: string[]; emails: string[]; channels: string[] }) =>
        api.post(`/billing/batches/${batchId}/send/`, data),
};

// Backups, Google Drive, migration checks (superadmins only)
export const backupAPI = {
    list: () => api.get('/backups/'),
    runNow: () => api.post('/backups/'),
    download: (id: number) => api.get(`/backups/${id}/`, { responseType: 'blob', timeout: 0 }),
    remove: (id: number, remote = false) => api.delete(`/backups/${id}/`, { params: remote ? { remote: 1 } : undefined }),
    upload: (id: number, target: 'gdrive' | 'nas' = 'gdrive') => api.post(`/backups/${id}/upload/`, { target }),
    getSettings: () => api.get('/backups/settings/'),
    updateSettings: (data: Record<string, unknown>) => api.patch('/backups/settings/', data),
    connectDrive: () => api.post('/backups/gdrive/'),
    pollDrive: () => api.put('/backups/gdrive/'),
    disconnectDrive: () => api.delete('/backups/gdrive/'),
    testDrive: () => api.post('/backups/gdrive/test/'),
    // Takes the unsaved form values so the NAS can be tested before saving.
    testNas: (data: Record<string, unknown>) => api.post('/backups/nas/test/', data, { timeout: 120000 }),
    migrationCheck: () => api.get('/backups/migration-check/', { timeout: 120000 }),
};

// Audit log (superadmins only)
export const auditAPI = {
    getLogs: (params: Record<string, string | number | undefined>) => api.get('/audit/logs/', { params }),
    getFacets: (params: Record<string, string | number | undefined>) => api.get('/audit/logs/facets/', { params }),
};

// Notifications (SMS/WhatsApp/Telegram settings, test-send, promo broadcast)
export const notificationAPI = {
    getSettings: () => api.get('/notifications/settings/'),
    updateSettings: (data: any) => api.patch('/notifications/settings/', data),
    // Message templates: system wording overrides + saved promotional texts.
    getTemplates: () => api.get('/notifications/templates/'),
    saveSystemTemplate: (key: string, body: string) => api.put(`/notifications/templates/system/${key}/`, { body }),
    resetSystemTemplate: (key: string) => api.delete(`/notifications/templates/system/${key}/`),
    createPromoTemplate: (data: { name: string; body: string }) => api.post('/notifications/templates/promo/', data),
    updatePromoTemplate: (id: number, data: { name?: string; body?: string }) => api.patch(`/notifications/templates/promo/${id}/`, data),
    deletePromoTemplate: (id: number) => api.delete(`/notifications/templates/promo/${id}/`),
    previewTemplate: (body: string) => api.post('/notifications/templates/preview/', { body }),
    sendDailyReportNow: () => api.post('/notifications/daily-report/send-now/'),
    // Delivery report over every outgoing message, and resending one.
    getReport: (params: Record<string, string | number | undefined>) => api.get('/notifications/report/', { params }),
    resendMessage: (id: number) => api.post(`/notifications/log/${id}/resend/`),
    testSend: (data: { channel: 'sms' | 'whatsapp' | 'telegram' | 'email'; recipient: string; message?: string }) =>
        api.post('/notifications/test-send/', data),
    getWhatsAppStatus: () => api.get('/notifications/whatsapp/status/'),
    broadcast: (data: { message: string; channels: string[]; service_type?: string; dry_run?: boolean }) =>
        api.post('/notifications/promo-broadcast/', data),
};

// Analytics API
export const analyticsAPI = {
    getDashboardStats: () => api.get('/analytics/dashboard/'),
    getDashboardExtra: () => api.get('/analytics/dashboard/extra/'),
    // Just the live payments feed (cheap; polled every 15s on the dashboard).
    getDashboardFeed: () => api.get('/analytics/dashboard/extra/', { params: { section: 'payments' } }),
    getIncomeReport: (params?: any) => api.get('/analytics/income/', { params }),
    downloadIncomeReport: (params?: any) =>
        api.get('/analytics/income/', { params: { ...params, export: 'csv' }, responseType: 'blob' }),
    getVoucherUsageReport: (params?: any) => api.get('/analytics/voucher-usage/', { params }),
    downloadVoucherUsageReport: (params?: any) =>
        api.get('/analytics/voucher-usage/', { params: { ...params, export: 'csv' }, responseType: 'blob' }),
    getUsageReport: () => api.get('/analytics/usage/'),
    getUsageChart: () => api.get('/analytics/usage-chart/'),
    getDailyUsage: (params: { start_date: string; end_date: string }) => api.get('/analytics/usage-daily/', { params }),
    getDayBreakdown: (kind: 'revenue' | 'usage', date: string) =>
        api.get('/analytics/day-breakdown/', { params: { kind, date } }),
    getExpiringToday: (page: number, pageSize?: number) =>
        api.get('/analytics/expiring-today/', { params: { page, page_size: pageSize } }),
    getRecentActivity: () => api.get('/analytics/recent-activity/'),
    getRecentPayments: (page: number, pageSize?: number, range?: { start_date?: string; end_date?: string }) =>
        api.get('/analytics/recent-payments/', { params: { page, page_size: pageSize, ...range } }),
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
    getSubscribers: (params?: { search?: string; service_type?: string; status?: string; expiring?: string; plan?: string; ordering?: string; sort?: string; router?: string; is_new?: string; page?: number; page_size?: number }) =>
        api.get('/customers/subscribers/', { params }),
    // Tab counts (all/active/expiring/expired/suspended/new) under the same filters as the list.
    getSubscriberSummary: (params?: { search?: string; service_type?: string; plan?: string; router?: string }) =>
        api.get('/customers/subscribers/summary/', { params }),
    bulkStkReminder: (ids: number[]) => api.post('/customers/subscribers/bulk-stk-reminder/', { ids }),
    // Message subscribers on one or more channels: their payment reminder, or
    // `message` (with {first_name} etc.); preview=true returns the text without sending.
    bulkMessage: (ids: number[], channels: string[], opts: { message?: string; preview?: boolean } = {}) =>
        api.post('/customers/subscribers/bulk-reminder/', { ids, channels, ...opts }),
    // One subscriber's live session (byte counters) straight from their router.
    getSubscriberLive: (id: number) => api.get(`/customers/subscribers/${id}/live/`),
    getSubscriber: (id: number) => api.get(`/customers/subscribers/${id}/`),
    updateSubscriber: (id: number, data: any) => api.patch(`/customers/subscribers/${id}/`, data),
    getSubscriberUsage: (id: number) => api.get(`/customers/subscribers/${id}/usage/`),
    updatePppoeCredentials: (id: number, data: { pppoe_username: string; pppoe_password: string }) =>
        api.post(`/customers/subscribers/${id}/pppoe-credentials/`, data),
    topUpSubscriber: (id: number, planId: number, staticIpAddress?: string) =>
        api.post(`/customers/subscribers/${id}/topup/`, { plan_id: planId, static_ip_address: staticIpAddress }),
    // Superadmin only: move the latest subscription's expiry (reactivating it if expired).
    extendSubscriber: (id: number, expiryDate: string) =>
        api.post(`/customers/subscribers/${id}/extend/`, { expiry_date: expiryDate }),
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
    getSyncUsersStatus: (id: number) => api.get(`/network/routers/${id}/sync_users_status/`),
    enableWanAccess: (id: number) => api.post(`/network/routers/${id}/enable_wan_access/`),
    disableWanAccess: (id: number) => api.post(`/network/routers/${id}/disable_wan_access/`),
    enableMgmtVlan: (id: number) => api.post(`/network/routers/${id}/enable_mgmt_vlan/`),
    disableMgmtVlan: (id: number) => api.post(`/network/routers/${id}/disable_mgmt_vlan/`),
    restartRouter: (id: number) => api.post(`/network/routers/${id}/restart/`),
    getMaintenanceSchedule: (id: number) => api.get(`/network/routers/${id}/maintenance_schedule/`),
    setMaintenanceSchedule: (id: number, data: any) => api.post(`/network/routers/${id}/maintenance_schedule/`, data),
    getRouterHealth: (routerId?: number) => api.get('/network/routers/health/', { params: routerId ? { router: routerId } : undefined }),
    testRouterConnection: (data: { ip_address: string; username: string; password: string; port?: number; use_ssl?: boolean }) =>
        api.post('/network/routers/test_connection/', data),

    // Online Users
    getOnlineUsers: (type?: 'hotspot' | 'pppoe' | 'static') => api.get('/network/online-users/', { params: { type } }),
    syncOnlineUsers: () => api.post('/network/online-users/'),
    disconnectUser: (sessionId: number) => api.post(`/network/online-users/${sessionId}/disconnect/`),

    // Manual Actions
    manualSubscribe: (data: any) => api.post('/billing/manual-subscribe/', data),

    // Payments
    // Assign an open till payment; with planId the money activates that plan.
    assignC2BPayment: (paymentId: number, customerId: number, planId?: number) =>
        api.post(`/payments/c2b/${paymentId}/assign/`, { customer_id: customerId, plan_id: planId }),
};

// Site Settings (branding: company name + logo)
export const siteSettingsAPI = {
    get: () => api.get('/settings/site/'),
    update: (data: { company_name?: string; logo?: File; support_phone?: string }) => {
        const form = new FormData();
        if (data.company_name !== undefined) form.append('company_name', data.company_name);
        if (data.support_phone !== undefined) form.append('support_phone', data.support_phone);
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

export default api;
