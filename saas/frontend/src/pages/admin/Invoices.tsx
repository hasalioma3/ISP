import { Fragment, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Panel, SegmentedControl, ShellHeader, formatKES } from '@/components/savanna';
import { Button, Pager, Pill, Table, Td } from '~/components/ui';
import { api, errorText } from '~/lib/api';
import { useAuth } from '~/lib/auth';
import { dateTime } from '~/lib/format';

export default function Invoices() {
    const [params] = useSearchParams();
    const isAdmin = useAuth((s) => s.user?.is_platform_admin);
    const qc = useQueryClient();
    const [status, setStatus] = useState(params.get('status') || '');
    const [page, setPage] = useState(1);
    const [open, setOpen] = useState<number | null>(null);
    const { data, isLoading } = useQuery({
        queryKey: ['invoices', status, page],
        queryFn: async () => (await api.get('/admin/invoices/', { params: { status: status || undefined, page } })).data,
    });
    const act = useMutation({
        mutationFn: async ({ id, ...body }: any) => (await api.post(`/admin/invoices/${id}/action/`, body)).data,
        onSuccess: () => { toast.success('Updated'); qc.invalidateQueries({ queryKey: ['invoices'] }); },
        onError: (err) => toast.error(errorText(err)),
    });
    return (
        <>
            <ShellHeader title="Invoices" subtitle="Monthly platform bills. Issued automatically and paid from each ISP's collections when they cover it." />
            <Panel>
                <div className="mb-4"><SegmentedControl aria-label="Status" value={status} onChange={(v) => { setStatus(v); setPage(1); }}
                    options={[{ value: '', label: 'All' }, { value: 'open', label: 'Unpaid' }, { value: 'paid', label: 'Paid' }, { value: 'void', label: 'Void' }]} /></div>
                <Table loading={isLoading} head={['Invoice', 'ISP', 'Period', 'Subscribers', 'Amount', 'Status', 'Due / paid', '']} empty="No invoices.">
                    {data?.results?.map((i: any) => (
                        <Fragment key={i.id}>
                            <tr className="cursor-pointer hover:bg-secondary/60" onClick={() => setOpen(open === i.id ? null : i.id)}>
                                <Td className="font-mono text-[12.5px]">{i.number}</Td>
                                <Td><Link onClick={(e) => e.stopPropagation()} className="font-semibold hover:text-primary" to={`/admin/tenants/${i.tenant}`}>{i.tenant_name}</Link></Td>
                                <Td className="text-[12.5px]">{i.period_start} – {i.period_end}</Td>
                                <Td className="num">{i.subscriber_count}</Td>
                                <Td className="num font-semibold">{formatKES(i.amount)}</Td>
                                <Td><Pill status={i.status} label={i.status_label} /></Td>
                                <Td className="text-[12.5px] text-muted-foreground">{i.status === 'paid' ? `${dateTime(i.paid_at)} · ${i.paid_via}` : dateTime(i.due_at)}</Td>
                                <Td className="text-right" onClick={(e) => e.stopPropagation()}>
                                    {isAdmin && i.status === 'open' && <>
                                        <Button size="sm" variant="outline" onClick={() => act.mutate({ id: i.id, action: 'deduct' })}>Pay from balance</Button>
                                        <Button size="sm" variant="outline" className="ml-1" onClick={() => { const ref = window.prompt('Payment reference (receipt, bank ref...)'); if (ref !== null) act.mutate({ id: i.id, action: 'mark_paid', ref }); }}>Mark paid</Button>
                                        <Button size="sm" variant="ghost" className="ml-1 text-bad" onClick={() => window.confirm(`Void ${i.number}?`) && act.mutate({ id: i.id, action: 'void' })}>Void</Button>
                                    </>}
                                </Td>
                            </tr>
                            {open === i.id && (
                                <tr><td colSpan={8} className="bg-secondary/60 px-[22px] py-3">
                                    <ul className="max-w-lg space-y-1 text-[13px]">{i.lines.map((l: any, n: number) => <li key={n} className="flex justify-between gap-4"><span>{l.label}</span><span className="num">{formatKES(l.amount)}</span></li>)}</ul>
                                    <p className="mt-2 text-[12px] text-muted-foreground">{i.plan_name} · counted {i.count_detail?.service_types?.join(', ')} ({i.count_detail?.method}, {i.count_detail?.days_measured} days measured)</p>
                                </td></tr>
                            )}
                        </Fragment>
                    ))}
                </Table>
                <Pager page={page} count={data?.count || 0} onPage={setPage} />
            </Panel>
        </>
    );
}
