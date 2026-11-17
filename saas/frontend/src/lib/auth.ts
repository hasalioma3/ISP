import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface User {
    id: number;
    email: string;
    first_name: string;
    last_name: string;
    full_name: string;
    phone: string;
    role: 'platform_admin' | 'platform_staff' | 'isp_owner';
    is_superuser: boolean;
    is_platform: boolean;
    is_platform_admin: boolean;
    tenant: number | null;
    tenant_slug: string | null;
}

interface AuthState {
    user: User | null;
    access: string | null;
    refresh: string | null;
    setAuth: (user: User, access: string, refresh: string) => void;
    setTokens: (access: string, refresh?: string) => void;
    setUser: (user: User) => void;
    logout: () => void;
}

export const useAuth = create<AuthState>()(
    persist(
        (set) => ({
            user: null,
            access: null,
            refresh: null,
            setAuth: (user, access, refresh) => set({ user, access, refresh }),
            setTokens: (access, refresh) => set((s) => ({ access, refresh: refresh ?? s.refresh })),
            setUser: (user) => set({ user }),
            logout: () => set({ user: null, access: null, refresh: null }),
        }),
        { name: 'isp-cloud-auth' },
    ),
);

export const homeFor = (user: User | null) => (!user ? '/login' : user.is_platform ? '/admin' : '/account');
