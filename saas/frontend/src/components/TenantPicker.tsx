import { useQuery } from '@tanstack/react-query';
import { Select } from '~/components/ui';
import { api } from '~/lib/api';

/** Pick an ISP (the ones that can still receive money). */
export default function TenantPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
    const { data } = useQuery({
        queryKey: ['tenants', 'picker'],
        queryFn: async () => (await api.get('/admin/tenants/', { params: { status: 'trial,active,past_due,suspended', page_size: 500 } })).data,
    });
    return (
        <Select value={value} onChange={(e) => onChange(e.target.value)}>
            <option value="">Choose an ISP…</option>
            {data?.results?.map((t: any) => <option key={t.id} value={t.id}>{t.name} ({t.slug})</option>)}
        </Select>
    );
}
