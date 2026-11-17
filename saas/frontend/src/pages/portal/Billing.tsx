import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { CheckCircle2 } from 'lucide-react';
import { Panel, PanelHeader, ShellHeader, formatKES } from '@/components/savanna';
import { cn } from '@/lib/utils';
import { Button, Field, Input, Modal, Notice, Pill, Spinner, Table, Td } from '~/components/ui';
import { api, errorText } from '~/lib/api';
import { useAuth } from '~/lib/auth';
import { dateTime } from '~/lib/format';
import { usePortal } from './usePortal';

export default function Billing() {
    const qc = useQueryClient();
    const { data: t } = usePortal();
    const { data: cfg } = useQuery({ queryKey: ['public-config'], queryFn: async () => (await api.get('/public/config/')).data });
    const invoices = useQuery({ queryKey: ['portal-invoices'], queryFn: async () => (await api.get('/portal/invoices/')).data });
    const [plan, setPlan] = useState<string | null>(null);
    const [accept, setAccept] = useState(false);
    const [paying, setPaying] = useState<any>(null);
    const activate = useMutation({
        mutationFn: async () => (await api.post('/portal/activate/', { plan: plan || currentCode, accept_terms: accept })).data,
        onSuccess: () => { toast.success('Subscribed -- thank you!'); qc.invalidateQueries({ queryKey: ['portal'] }); },
        onError: (err) => toast.error(errorText(err)),
    });
    if (!t || !cfg) return <Panel><Spinner /></Panel>;
    const currentCode = cfg.plans.find((p: any) => p.name === t.plan_name)?.code;
    const chosen = plan || currentCode;
    const subscribed = !!t.activated_at && t.status !== 'cancelled';

    return (
        <>
            <ShellHeader title="Billing" subtitle="Your plan and invoices. Invoices are paid from your M-Pesa collections when they cover them." />
            <div className="grid gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
                <Panel>
                    <PanelHeader title={subscribed ? 'Your plan' : 'Choose a plan'} subtitle={subscribed ? `Subscribed since ${dateTime(t.activated_at)}` : t.status === 'trial' ? 'Your trial keeps running until it ends; billing starts when you subscribe.' : undefined} />
                    <div className="grid gap-3 sm:grid-cols-2">
                        {cfg.plans.map((p: any) => (
                            <button key={p.code} type="button" onClick={() => setPlan(p.code)}
                                className={cn('rounded-2xl border p-4 text-left transition-colors', chosen === p.code ? 'border-primary bg-accent' : 'border-border hover:border-border-strong')}>
                                <p className="flex items-center gap-2 font-bold">{p.name}{p.code === currentCode && subscribed && <CheckCircle2 className="h-4 w-4 text-ok" />}</p>
                                {p.description && <p className="mt-0.5 text-[12.5px] text-muted-foreground">{p.description}</p>}
                                <ul className="mt-2 space-y-0.5 text-[12.5px] text-muted-foreground">
                                    {p.examples.map((e: any) => <li key={e.subscribers} className="flex justify-between"><span>{e.subscribers} subscribers</span><b className="num text-foreground">{formatKES(e.amount)}/mo</b></li>)}
                                </ul>
                            </button>
                        ))}
                    </div>
                    {t.estimate && <p className="mt-4 text-[13.5px]">At today's {t.estimate.counted_subscribers} counted subscribers, this month comes to about <b className="num">{formatKES(t.estimate.amount)}</b>.</p>}
                    {(!subscribed || (plan && plan !== currentCode)) && (
                        <div className="mt-5 space-y-3">
                            <label className="flex items-start gap-2.5 text-[13.5px]">
                                <input type="checkbox" className="mt-1" checked={accept} onChange={(e) => setAccept(e.target.checked)} />
                                <span>I agree to the {cfg.terms_url ? <a className="font-semibold text-primary underline" href={cfg.terms_url} target="_blank" rel="noreferrer">terms</a> : 'terms'} and to being billed monthly by subscriber count.</span>
                            </label>
                            <Button variant="sunset" size="lg" disabled={!accept || !chosen || activate.isPending} onClick={() => activate.mutate()}>
                                {activate.isPending && <Spinner />}{subscribed ? 'Switch plan' : 'Subscribe'}
                            </Button>
                        </div>
                    )}
                </Panel>
                <Panel>
                    <PanelHeader title="How billing works" />
                    <ul className="space-y-2 text-[13.5px] text-muted-foreground">
                        <li>We count your subscribers every hour and bill monthly on the plan's rule (shown on each plan).</li>
                        <li>On the {cfg.trial_days ? '' : ''}invoice date, the bill is taken from the money your customers paid through us, if it covers it.</li>
                        <li>Otherwise you can pay it here by M-Pesa. Unpaid invoices pause your system after the grace period.</li>
                        <li>Everything left over is paid out to you on the payout schedule.</li>
                    </ul>
                </Panel>
            </div>
            <Panel className="mt-5">
                <PanelHeader title="Invoices" />
                <Table loading={invoices.isLoading} head={['Invoice', 'Period', 'Subscribers', 'Amount', 'Status', '']} empty="No invoices yet.">
                    {invoices.data?.results?.map((i: any) => (
                        <tr key={i.id}>
                            <Td className="font-mono text-[12.5px]">{i.number}</Td><Td className="text-[12.5px]">{i.period_start} – {i.period_end}</Td>
                            <Td className="num">{i.subscriber_count}</Td><Td className="num font-semibold">{formatKES(i.amount)}</Td>
                            <Td><Pill status={i.status} label={i.status_label} />{i.status === 'open' && <span className="block pt-1 text-[12px] text-muted-foreground">due {dateTime(i.due_at)}</span>}</Td>
                            <Td className="text-right">{i.status === 'open' && <Button size="sm" variant="mpesa" onClick={() => setPaying(i)}>Pay with M-Pesa</Button>}</Td>
                        </tr>
                    ))}
                </Table>
            </Panel>
            {paying && <PayModal invoice={paying} onClose={() => setPaying(null)} />}
        </>
    );
}

function PayModal({ invoice, onClose }: { invoice: any; onClose: () => void }) {
    const qc = useQueryClient();
    const user = useAuth((s) => s.user);
    const [phone, setPhone] = useState(user?.phone || '');
    const [sent, setSent] = useState(false);
    const pay = useMutation({
        mutationFn: async () => (await api.post(`/portal/invoices/${invoice.id}/pay/`, { phone })).data,
        onSuccess: () => { setSent(true); setTimeout(() => qc.invalidateQueries({ queryKey: ['portal-invoices'] }), 20000); },
        onError: (err) => toast.error(errorText(err)),
    });
    return (
        <Modal open onClose={onClose} title={`Pay ${invoice.number}`} description={`${formatKES(invoice.amount)} by M-Pesa`}>
            {sent ? <Notice tone="ok">Check your phone and enter your M-Pesa PIN. The invoice is marked paid as soon as M-Pesa confirms.</Notice> : (
                <>
                    <Field label="M-Pesa phone"><Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="0712 345 678" /></Field>
                    <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button><Button variant="mpesa" disabled={pay.isPending} onClick={() => pay.mutate()}>{pay.isPending && <Spinner />}Send prompt</Button></div>
                </>
            )}
        </Modal>
    );
}
