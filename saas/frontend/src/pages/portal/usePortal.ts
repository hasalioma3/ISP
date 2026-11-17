import { useQuery } from '@tanstack/react-query';
import { api } from '~/lib/api';

export function usePortal() {
    return useQuery({
        queryKey: ['portal'],
        queryFn: async () => (await api.get('/portal/tenant/')).data,
        // Poll while the instance is being created.
        refetchInterval: (q) => (['pending', 'provisioning'].includes(q.state.data?.status) ? 3000 : 60_000),
    });
}
