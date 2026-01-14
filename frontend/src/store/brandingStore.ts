import { create } from 'zustand';
import { coreAPI } from '../services/api';

interface BrandingState {
    company_name: string;
    primary_color: string;
    logo: string | null;
    favicon: string | null;
    fetchBranding: () => Promise<void>;
}

export const useBrandingStore = create<BrandingState>((set) => ({
    company_name: 'ISP Billing',
    primary_color: '#000000',
    logo: null,
    favicon: null,
    fetchBranding: async () => {
        try {
            const res = await coreAPI.getBranding();
            const { company_name, primary_color, logo, favicon } = res.data;
            set({ company_name, primary_color, logo, favicon });

            // Update document title and favicon
            document.title = company_name;
            if (favicon) {
                const link = document.querySelector("link[rel*='icon']") || document.createElement('link');
                link.type = 'image/x-icon';
                link.rel = 'shortcut icon';
                link.href = favicon;
                document.getElementsByTagName('head')[0].appendChild(link);
            }
        } catch (error) {
            console.error("Failed to fetch branding:", error);
        }
    },
}));
