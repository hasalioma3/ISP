import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { AlertTriangle, CheckCircle2, Search } from 'lucide-react';
import { MpesaBadge, Panel, PanelHeader, SegmentedControl, ShellHeader, formatKES } from '@/components/savanna';
import TenantPicker from '~/components/TenantPicker';
import { Button, Field, Input, Modal, Notice, Pager, Table, Td } from '~/components/ui';
import { api, errorText } from '~/lib/api';
import { useAuth } from '~/lib/auth';
import { dateTime } from '~/lib/format';

type View = 'all' | 'unallocated' | 'problem';

export default function Payments() {
    const [params] = useSearchParams();
    const isAdmin = useAuth((s) => s.user?.is_platform_admin);
    const qc = useQueryClient();
    const [view, setView] = useState<View>(params.get('unallocated') ? 'unallocated' : 'all');
    const [search, setSearch] = useState('');
    const [q, setQ] = useState('');
    const [page, setPage] = useState(1);
    const [allocating, setAllocating] = useState<any>(null);
    const { data, isLoading } = useQuery({
        queryKey: ['collections', view, q, page],
        queryFn: async () => (await api.get('/admin/collections/', {
            params: { page, search: q || undefined, unallocated: view === 'unallocated' ? 1 : undefined, problem: view === 'problem' ? 1 : undefined },
        })).data,
    });
    const action = useMutation({
        mutationFn: async ({ id, ...body }: any) => (await api.post(`/admin/collections/${id}/action/`, body)).data,
        onSuccess: () => { toast.success('Done'); qc.invalidateQueries({ queryKey: ['collections'] }); },
        onError: (err) => toast.error(errorText(err)),
    });

    return (
        <>
            <ShellHeader title="Customer payments" subtitle="Every M-Pesa payment that reached the platform shortcode for an ISP." />
            <Panel>
                <PanelHeader leading={<MpesaBadge />} title={`${formatKES(data?.total_amount)} verified`} subtitle={`${data?.count ?? 0} payments in this view`} />
                <div className="mb-4 flex flex-wrap items-center gap-3">
                    <SegmentedControl<View> aria-label="View" value={view} onChange={(v) => { setView(v); setPage(1); }}
                        options={[{ value: 'all', label: 'All' }, { value: 'unallocated', label: 'Not matched' }, { value: 'problem', label: 'Needs a look' }]} />
                    <form className="relative ml-auto w-full sm:w-72" onSubmit={(e) => { e.preventDefault(); setQ(search.trim()); setPage(1); }}>
                        <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                        <Input className="pl-9" placeholder="Receipt, phone, account, name" value={search} onChange={(e) => setSearch(e.target.value)} />
                    </form>
                </div>
                {view === 'unallocated' && <Notice tone="info" className="mb-4">Paybill payments whose account number matched no ISP (or more than one). Assign each to the right ISP: it is credited to them and passed on to their system.</Notice>}
                <Table loading={isLoading} head={['Receipt', 'ISP', 'Amount', 'Payer', 'Account', 'Paid', 'Checks', '']} empty="No payments.">
                    {data?.results?.map((c: any) => (
                        <tr key={c.id}>
                            <Td className="font-mono text-[12.5px]">{c.receipt}<span className="block font-sans text-[11.5px] text-muted-foreground">{c.source_label}{c.routed_by && ` · by ${c.routed_by}`}</span></Td>
                            <Td>{c.tenant ? <Link className="font-semibold hover:text-primary" to={`/admin/tenants/${c.tenant}`}>{c.tenant_name}</Link> : <span className="text-warn">Not matched</span>}</Td>
                            <Td className="num font-semibold">{formatKES(c.amount)}</Td>
                            <Td className="text-[12.5px]">{c.payer_name || '—'}<span className="block text-muted-foreground">{c.phone}</span></Td>
                            <Td className="font-mono text-[12.5px]">{c.account || '—'}</Td>
                            <Td className="text-[12.5px] text-muted-foreground">{dateTime(c.paid_at)}</Td>
                            <Td className="text-[12.5px]">
                                {c.verified ? <span className="text-ok"><CheckCircle2 className="mr-1 inline h-3.5 w-3.5" />Verified</span>
                                    : <span className="text-warn" title={c.verify_error}><AlertTriangle className="mr-1 inline h-3.5 w-3.5" />Unverified</span>}
                                {c.tenant && <span className={`block ${c.forwarded ? 'text-muted-foreground' : 'text-bad'}`} title={c.forward_error}>{c.forwarded ? 'Passed to ISP' : 'Not passed to ISP yet'}</span>}
                            </Td>
                            <Td className="text-right">
                                {isAdmin && !c.tenant && <Button size="sm" onClick={() => setAllocating(c)}>Assign</Button>}
                                {isAdmin && c.tenant && !c.verified && <Button size="sm" variant="outline" onClick={() => action.mutate({ id: c.id, action: 'verify' })}>Re-check</Button>}
                                {isAdmin && c.tenant && c.verified && !c.forwarded && <Button size="sm" variant="outline" className="ml-1" onClick={() => action.mutate({ id: c.id, action: 'forward' })}>Resend</Button>}
                            </Td>
                        </tr>
                    ))}
                </Table>
                <Pager page={page} count={data?.count || 0} onPage={setPage} />
            </Panel>
            {allocating && <Allocate c={allocating} onClose={() => setAllocating(null)} onSave={(body) => action.mutate({ id: allocating.id, action: 'allocate', ...body }, { onSuccess: () => setAllocating(null) })} />}
        </>
    );
}

function Allocate({ c, onClose, onSave }: { c: any; onClose: () => void; onSave: (b: any) => void }) {
    const [tenant, setTenant] = useState('');
    const [account, setAccount] = useState(c.account || '');
    return (
        <Modal open onClose={onClose} title={`Assign ${c.receipt}`} description={`${formatKES(c.amount)} from ${c.payer_name || c.phone}, account "${c.account}".`}>
            <Field label="ISP"><TenantPicker value={tenant} onChange={setTenant} /></Field>
            <Field label="Their customer's username" hint="Passed to the ISP's system so it credits the right customer."><Input value={account} onChange={(e) => setAccount(e.target.value)} /></Field>
            <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button><Button disabled={!tenant} onClick={() => onSave({ tenant, account })}>Assign</Button></div>
        </Modal>
    );
}
