import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Play } from 'lucide-react';
import { Panel, SegmentedControl, ShellHeader, bandCtaClass, formatKES } from '@/components/savanna';
import { Button, Pager, Pill, Table, Td } from '~/components/ui';
import { api, errorText } from '~/lib/api';
import { useAuth } from '~/lib/auth';
import { dateTime } from '~/lib/format';

export default function Payouts() {
    const [params] = useSearchParams();
    const isAdmin = useAuth((s) => s.user?.is_platform_admin);
    const qc = useQueryClient();
    const [status, setStatus] = useState(params.get('status') || '');
    const [page, setPage] = useState(1);
    const { data, isLoading } = useQuery({
        queryKey: ['settlements', status, page],
        queryFn: async () => (await api.get('/admin/settlements/', { params: { status: status || undefined, page } })).data,
        refetchInterval: (q) => (q.state.data?.results?.some((s: any) => ['queued', 'processing'].includes(s.status)) ? 5000 : false),
    });
    const refresh = () => qc.invalidateQueries({ queryKey: ['settlements'] });
    const act = useMutation({
        mutationFn: async ({ id, action }: any) => (await api.post(`/admin/settlements/${id}/action/`, { action })).data,
        onSuccess: refresh, onError: (err) => toast.error(errorText(err)),
    });
    const runAll = useMutation({
        mutationFn: async () => (await api.post('/admin/settlements/', { all: true })).data,
        onSuccess: (d) => { toast.success(`${d.created} payout(s) created`); refresh(); },
        onError: (err) => toast.error(errorText(err)),
    });
    return (
        <>
            <ShellHeader title="Payouts" subtitle="Money sent to ISPs: B2B to their paybill or till, or B2C to a phone."
                actions={isAdmin && <button className={bandCtaClass} onClick={() => window.confirm('Create payouts now for every ISP with money available?') && runAll.mutate()}><Play className="h-4 w-4" />Run payouts now</button>} />
            <Panel>
                <div className="mb-4"><SegmentedControl aria-label="Status" value={status} onChange={(v) => { setStatus(v); setPage(1); }}
                    options={[{ value: '', label: 'All' }, { value: 'pending_approval', label: 'To approve' }, { value: 'queued,processing', label: 'In progress' }, { value: 'succeeded', label: 'Paid' }, { value: 'failed', label: 'Failed' }]} /></div>
                <Table loading={isLoading} head={['Created', 'ISP', 'Amount', 'Fee', 'To', 'Status', 'M-Pesa', '']} empty="No payouts.">
                    {data?.results?.map((s: any) => (
                        <tr key={s.id}>
                            <Td className="text-[12.5px] text-muted-foreground">{dateTime(s.created_at)}{s.requested_by && <span className="block">by {s.requested_by}</span>}</Td>
                            <Td><Link className="font-semibold hover:text-primary" to={`/admin/tenants/${s.tenant}`}>{s.tenant_name}</Link></Td>
                            <Td className="num font-semibold">{formatKES(s.amount)}</Td>
                            <Td className="num text-muted-foreground">{formatKES(s.fee)}</Td>
                            <Td className="text-[12.5px]">{s.method === 'phone' ? 'Phone' : s.method === 'till' ? 'Till' : 'Paybill'} {s.destination}{s.account_ref && ` · ${s.account_ref}`}</Td>
                            <Td><Pill status={s.status} label={s.status_label} />{s.result_desc && s.status !== 'succeeded' && <span className="block max-w-[220px] truncate pt-1 text-[12px] text-muted-foreground" title={s.result_desc}>{s.result_desc}</span>}</Td>
                            <Td className="font-mono text-[12.5px]">{s.mpesa_receipt || '—'}</Td>
                            <Td className="text-right">
                                {isAdmin && s.status === 'pending_approval' && <Button size="sm" onClick={() => act.mutate({ id: s.id, action: 'approve' })}>Approve</Button>}
                                {isAdmin && ['pending_approval', 'queued'].includes(s.status) && <Button size="sm" variant="ghost" className="ml-1" onClick={() => act.mutate({ id: s.id, action: 'cancel' })}>Cancel</Button>}
                                {isAdmin && s.status === 'failed' && <Button size="sm" variant="outline" onClick={() => act.mutate({ id: s.id, action: 'retry' })}>Retry</Button>}
                            </Td>
                        </tr>
                    ))}
                </Table>
                <Pager page={page} count={data?.count || 0} onPage={setPage} />
            </Panel>
        </>
    );
}
