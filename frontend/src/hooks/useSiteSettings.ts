import { useQuery } from '@tanstack/react-query';
import { siteSettingsAPI } from '../services/api';

export function useSiteSettings() {
    return useQuery({
        queryKey: ['site-settings'],
        queryFn: async () => {
            const res = await siteSettingsAPI.get();
            return res.data as { company_name: string; logo: string | null; favicon: string | null };
        },
        staleTime: 60000,
    });
}
