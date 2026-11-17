import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { useAuth } from './auth';

export const api = axios.create({ baseURL: '/api', timeout: 60000 });

api.interceptors.request.use((config) => {
    const token = useAuth.getState().access;
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

// One refresh in flight at a time; queued requests reuse it.
let refreshing: Promise<string | null> | null = null;

async function refreshAccess(): Promise<string | null> {
    const refresh = useAuth.getState().refresh;
    if (!refresh) return null;
    try {
        const { data } = await axios.post('/api/auth/refresh/', { refresh });
        useAuth.getState().setTokens(data.access, data.refresh);
        return data.access;
    } catch {
        return null;
    }
}

api.interceptors.response.use(undefined, async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    if (error.response?.status === 401 && original && !original._retried && !original.url?.includes('/auth/')) {
        original._retried = true;
        refreshing = refreshing || refreshAccess().finally(() => { refreshing = null; });
        const token = await refreshing;
        if (token) {
            original.headers.Authorization = `Bearer ${token}`;
            return api(original);
        }
        useAuth.getState().logout();
        if (!location.pathname.startsWith('/login')) location.assign('/login');
    }
    return Promise.reject(error);
});

/** First readable message from a DRF error body, else a fallback. */
export function errorText(err: any, fallback = 'Something went wrong. Please try again.'): string {
    const data = err?.response?.data;
    if (!err?.response) return 'Network error -- check your connection.';
    if (err.response.status >= 500) return 'Server error -- please try again in a moment.';
    if (typeof data === 'string') return fallback;
    if (data?.error) return data.error;
    if (data?.detail) return data.detail;
    if (data && typeof data === 'object') {
        const key = Object.keys(data)[0];
        const v = data[key];
        const msg = Array.isArray(v) ? v[0] : typeof v === 'string' ? v : null;
        if (msg) return key === 'non_field_errors' ? msg : `${key.replace(/_/g, ' ')}: ${msg}`;
    }
    return fallback;
}

export type Paged<T> = { count: number; next: string | null; previous: string | null; results: T[] } & Record<string, any>;

/** Download an authenticated file (CSV exports). */
export async function download(path: string, name: string) {
    const { data } = await api.get(path, { responseType: 'blob' });
    const url = URL.createObjectURL(data);
    Object.assign(document.createElement('a'), { href: url, download: name }).click();
    URL.revokeObjectURL(url);
}
