import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Panel, PanelHeader, ShellHeader } from '@/components/savanna';
import { Button, Field, Input, Notice, Select, Spinner, Textarea } from '~/components/ui';
import { api, errorText } from '~/lib/api';
import { dateTime } from '~/lib/format';
import { usePortal } from './usePortal';

export default function AccountSettings() {
    const qc = useQueryClient();
    const { data: t } = usePortal();
    const [form, setForm] = useState<any>(null);
    useEffect(() => {
        if (t) setForm({ name: t.name, contact_name: t.contact_name, contact_phone: t.contact_phone, settlement_method: t.settlement_method,
            settlement_account: t.settlement_account, settlement_account_ref: t.settlement_account_ref, settlement_name: t.settlement_name });
    }, [t]);
    const save = useMutation({
        mutationFn: async () => (await api.patch('/portal/tenant/', form)).data,
        onSuccess: () => { toast.success('Saved'); qc.invalidateQueries({ queryKey: ['portal'] }); },
        onError: (err) => toast.error(errorText(err)),
    });
    if (!t || !form) return <Panel><Spinner /></Panel>;
    const set = (k: string, v: string) => setForm((f: any) => ({ ...f, [k]: v }));
    return (
        <>
            <ShellHeader title="Settings" subtitle="Your company details and where we send your money." />
            <div className="grid gap-5 xl:grid-cols-2">
                <Panel>
                    <PanelHeader title="Company" />
                    <div className="grid gap-4 sm:grid-cols-2">
                        <Field label="Company name"><Input value={form.name} onChange={(e) => set('name', e.target.value)} /></Field>
                        <Field label="Contact name"><Input value={form.contact_name} onChange={(e) => set('contact_name', e.target.value)} /></Field>
                        <Field label="Contact phone"><Input value={form.contact_phone} onChange={(e) => set('contact_phone', e.target.value)} /></Field>
                        <Field label="Email" hint="Contact us to change it"><Input disabled value={t.contact_email} /></Field>
                    </div>
                    <PanelHeader className="mt-6" title="Where we send your money" subtitle="Payouts go here automatically on the payout schedule." />
                    <div className="grid gap-4 sm:grid-cols-2">
                        <Field label="Send to">
                            <Select value={form.settlement_method} onChange={(e) => set('settlement_method', e.target.value)}>
                                <option value="">Choose…</option><option value="paybill">A paybill</option><option value="till">A till (Buy Goods)</option><option value="phone">An M-Pesa phone</option>
                            </Select>
                        </Field>
                        <Field label={form.settlement_method === 'phone' ? 'Phone number' : 'Paybill / till number'}><Input value={form.settlement_account} onChange={(e) => set('settlement_account', e.target.value)} /></Field>
                        {form.settlement_method === 'paybill' && <Field label="Account number"><Input value={form.settlement_account_ref} onChange={(e) => set('settlement_account_ref', e.target.value)} /></Field>}
                        <Field label="Registered name" hint="As M-Pesa shows it -- we check it before the first payout"><Input value={form.settlement_name} onChange={(e) => set('settlement_name', e.target.value)} /></Field>
                    </div>
                    <div className="mt-5 flex justify-end"><Button onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending && <Spinner />}Save</Button></div>
                </Panel>
                <div className="space-y-5">
                    <PasswordPanel />
                    <CancelPanel requested={t.cancel_requested_at} />
                </div>
            </div>
        </>
    );
}

function PasswordPanel() {
    const [form, setForm] = useState({ current_password: '', new_password: '' });
    const save = useMutation({
        mutationFn: async () => (await api.post('/auth/password/', form)).data,
        onSuccess: () => { toast.success('Password changed'); setForm({ current_password: '', new_password: '' }); },
        onError: (err) => toast.error(errorText(err)),
    });
    return (
        <Panel>
            <PanelHeader title="Password" subtitle="For this account page. Your system's admin password is changed inside your system." />
            <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Current password"><Input type="password" autoComplete="current-password" value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} /></Field>
                <Field label="New password"><Input type="password" autoComplete="new-password" value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} /></Field>
            </div>
            <div className="mt-4 flex justify-end"><Button variant="outline" disabled={!form.current_password || !form.new_password || save.isPending} onClick={() => save.mutate()}>Change password</Button></div>
        </Panel>
    );
}

function CancelPanel({ requested }: { requested: string | null }) {
    const qc = useQueryClient();
    const [reason, setReason] = useState('');
    const cancel = useMutation({
        mutationFn: async () => (await api.post('/portal/cancel/', { reason })).data,
        onSuccess: () => { toast.success('We have your request and will be in touch'); qc.invalidateQueries({ queryKey: ['portal'] }); },
        onError: (err) => toast.error(errorText(err)),
    });
    return (
        <Panel>
            <PanelHeader title="Cancel" />
            {requested ? <Notice>You asked to cancel on {dateTime(requested)}. We'll settle your balance and contact you.</Notice> : (
                <>
                    <p className="text-[13.5px] text-muted-foreground">We'll pay out what we hold for you and stop your system. Tell us why, so we can do better:</p>
                    <Textarea className="mt-3" value={reason} onChange={(e) => setReason(e.target.value)} />
                    <div className="mt-3 flex justify-end"><Button variant="destructive" disabled={cancel.isPending} onClick={() => window.confirm('Request cancellation?') && cancel.mutate()}>Request cancellation</Button></div>
                </>
            )}
        </Panel>
    );
}
