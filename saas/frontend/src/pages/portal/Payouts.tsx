import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Banknote, Download } from 'lucide-react';
import { Panel, PanelHeader, ShellHeader, bandCtaClass, formatKES } from '@/components/savanna';
import { Button, Notice, Pager, Pill, Table, Td } from '~/components/ui';
import { api, download, errorText } from '~/lib/api';
import { dateTime } from '~/lib/format';
import { usePortal } from './usePortal';

export default function Payouts() {
    const qc = useQueryClient();
    const { data: t } = usePortal();
    const [page, setPage] = useState(1);
    const statement = useQuery({ queryKey: ['portal-statement', page], queryFn: async () => (await api.get('/portal/statement/', { params: { page } })).data });
    const payouts = useQuery({ queryKey: ['portal-settlements'], queryFn: async () => (await api.get('/portal/settlements/')).data });
    const request = useMutation({
        mutationFn: async () => (await api.post('/portal/settlements/', {})).data,
        onSuccess: (s) => { toast.success(s.status === 'pending_approval' ? 'Requested -- we will approve it shortly' : 'Payout on its way'); qc.invalidateQueries({ queryKey: ['portal-settlements'] }); qc.invalidateQueries({ queryKey: ['portal'] }); },
        onError: (err) => toast.error(errorText(err)),
    });
    const noDetails = t && !t.settlement_method;
    return (
        <>
            <ShellHeader title="Payouts" subtitle={t ? `${formatKES(t.balance)} held for you · ${formatKES(t.available_to_pay_out)} ready to pay out` : undefined}
                actions={<button className={bandCtaClass} disabled={!!noDetails || request.isPending} onClick={() => request.mutate()}><Banknote className="h-4 w-4" />Pay me now</button>} />
            {noDetails && <Notice className="mb-5">Add where to send your money on the Settings page first.</Notice>}
            <div className="grid gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
                <Panel>
                    <PanelHeader title="Statement" subtitle="Every shilling in and out"
                        action={<Button size="sm" variant="outline" onClick={() => download('/portal/statement/?export=csv', 'statement.csv').catch((e) => toast.error(errorText(e)))}><Download />CSV</Button>} />
                    <Table loading={statement.isLoading} head={['Date', 'What', 'Amount']} empty="Nothing yet. Customer payments appear here as they arrive.">
                        {statement.data?.results?.map((e: any) => (
                            <tr key={e.id}>
                                <Td className="text-[12.5px] text-muted-foreground">{dateTime(e.created_at)}</Td>
                                <Td className="max-w-[360px] truncate">{e.kind_label}<span className="block truncate text-[12px] text-muted-foreground">{e.description}</span></Td>
                                <Td className={`num text-right font-semibold ${Number(e.amount) < 0 ? 'text-bad' : 'text-ok'}`}>{formatKES(e.amount)}</Td>
                            </tr>
                        ))}
                    </Table>
                    <Pager page={page} count={statement.data?.count || 0} onPage={setPage} />
                </Panel>
                <Panel>
                    <PanelHeader title="Payouts" subtitle={t?.settlement_method ? `To ${t.settlement_method === 'phone' ? 'phone' : t.settlement_method} ${t.settlement_account}` : undefined} />
                    <Table loading={payouts.isLoading} head={['Date', 'Amount', 'Status']} empty="No payouts yet.">
                        {payouts.data?.results?.map((s: any) => (
                            <tr key={s.id}><Td className="text-[12.5px]">{dateTime(s.created_at)}</Td><Td className="num font-semibold">{formatKES(s.amount)}</Td>
                                <Td><Pill status={s.status} label={s.status_label} />{s.mpesa_receipt && <span className="block pt-1 font-mono text-[11.5px] text-muted-foreground">{s.mpesa_receipt}</span>}</Td></tr>
                        ))}
                    </Table>
                </Panel>
            </div>
        </>
    );
}
