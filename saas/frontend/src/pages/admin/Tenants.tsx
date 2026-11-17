import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Plus, Search } from 'lucide-react';
import { Panel, SegmentedControl, ShellHeader, bandCtaClass, formatCount, formatKES } from '@/components/savanna';
import { Button, Field, Input, Modal, Pager, Pill, Spinner, Table, Td, TenantStatus } from '~/components/ui';
import { api, errorText } from '~/lib/api';
import { dateTime, duration } from '~/lib/format';

const FILTERS = [
    { value: '', label: 'All' }, { value: 'trial', label: 'Trial' }, { value: 'active', label: 'Active' },
    { value: 'past_due', label: 'Overdue' }, { value: 'suspended', label: 'Suspended' },
    { value: 'provisioning,pending,failed', label: 'Setting up' }, { value: 'cancelled,deleted', label: 'Closed' },
];

export default function Tenants() {
    const [params, setParams] = useSearchParams();
    const status = params.get('status') || '';
    const [search, setSearch] = useState(params.get('search') || '');
    const [page, setPage] = useState(1);
    const [adding, setAdding] = useState(false);
    const { data, isLoading } = useQuery({
        queryKey: ['tenants', status, params.get('search'), page],
        queryFn: async () => (await api.get('/admin/tenants/', { params: { status, search: params.get('search') || undefined, page } })).data,
        refetchInterval: (q) => (q.state.data?.results?.some((t: any) => ['pending', 'provisioning'].includes(t.status)) ? 4000 : false),
    });
    const update = (k: string, v: string) => {
        const next = new URLSearchParams(params);
        if (v) next.set(k, v); else next.delete(k);
        setParams(next);
        setPage(1);
    };

    return (
        <>
            <ShellHeader title="ISPs" subtitle="Every ISP on the platform and its instance."
                actions={<button className={bandCtaClass} onClick={() => setAdding(true)}><Plus className="h-4 w-4" />Add ISP</button>} />
            <Panel>
                <div className="mb-4 flex flex-wrap items-center gap-3">
                    <SegmentedControl aria-label="Status" options={FILTERS} value={status} onChange={(v) => update('status', v)} />
                    <form className="relative ml-auto w-full sm:w-72" onSubmit={(e) => { e.preventDefault(); update('search', search.trim()); }}>
                        <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                        <Input className="pl-9" placeholder="Name, ID, email, phone" value={search} onChange={(e) => setSearch(e.target.value)} />
                    </form>
                </div>
                <Table loading={isLoading} head={['ISP', 'Status', 'Plan', 'Subscribers', 'Held', 'Instance', 'Since']} empty="No ISPs match.">
                    {data?.results?.map((t: any) => (
                        <tr key={t.id} className="hover:bg-secondary/60">
                            <Td>
                                <Link to={`/admin/tenants/${t.id}`} className="block">
                                    <span className="font-semibold text-foreground hover:text-primary">{t.name}</span>
                                    <span className="block text-[12.5px] text-muted-foreground">{t.slug} · {t.contact_email}</span>
                                </Link>
                            </Td>
                            <Td>
                                <TenantStatus status={t.status} label={t.status_label} />
                                {t.status === 'trial' && <span className="block pt-1 text-[12px] text-muted-foreground">{duration(t.trial_seconds_left)}</span>}
                            </Td>
                            <Td>{t.plan_name || '—'}</Td>
                            <Td className="num">{formatCount(t.subscribers?.active)} <span className="text-muted-foreground">/ {formatCount(t.subscribers?.all)}</span></Td>
                            <Td className="num">{formatKES(t.balance)}</Td>
                            <Td>{t.instance_state ? <Pill status={t.instance_state} label={t.instance_label} /> : <span className="text-muted-foreground">—</span>}</Td>
                            <Td className="text-[12.5px] text-muted-foreground">{dateTime(t.created_at)}</Td>
                        </tr>
                    ))}
                </Table>
                <Pager page={page} count={data?.count || 0} onPage={setPage} />
            </Panel>
            <AddTenant open={adding} onClose={() => setAdding(false)} />
        </>
    );
}

/** Onboard an ISP for them: same flow as the public sign-up. */
function AddTenant({ open, onClose }: { open: boolean; onClose: () => void }) {
    const qc = useQueryClient();
    const navigate = useNavigate();
    const [form, setForm] = useState({ company_name: '', full_name: '', email: '', phone: '', password: '' });
    const [busy, setBusy] = useState(false);
    const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
    const submit = async (e: React.FormEvent) => {
        e.preventDefault();
        setBusy(true);
        try {
            const { data } = await api.post('/public/signup/', { ...form, accept_terms: true });
            toast.success(`${data.tenant.name} is being set up`);
            qc.invalidateQueries({ queryKey: ['tenants'] });
            onClose();
            navigate(`/admin/tenants/${data.tenant.id}`);
        } catch (err) {
            toast.error(errorText(err, 'Could not create the ISP'));
        } finally {
            setBusy(false);
        }
    };
    return (
        <Modal open={open} onClose={onClose} title="Add an ISP" description="Creates the owner's account and sets up their instance on a free trial. Share the password with the owner; they can change it.">
            <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
                <Field label="Company name"><Input required value={form.company_name} onChange={(e) => set('company_name', e.target.value)} /></Field>
                <Field label="Owner's name"><Input required value={form.full_name} onChange={(e) => set('full_name', e.target.value)} /></Field>
                <Field label="Owner's email"><Input required type="email" value={form.email} onChange={(e) => set('email', e.target.value)} /></Field>
                <Field label="Owner's phone"><Input required value={form.phone} onChange={(e) => set('phone', e.target.value)} /></Field>
                <Field label="Initial password" className="sm:col-span-2"><Input required type="text" value={form.password} onChange={(e) => set('password', e.target.value)} /></Field>
                <div className="flex justify-end gap-2 sm:col-span-2">
                    <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
                    <Button type="submit" disabled={busy}>{busy && <Spinner />}Create</Button>
                </div>
            </form>
        </Modal>
    );
}
