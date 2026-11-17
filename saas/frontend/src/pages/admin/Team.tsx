import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Plus } from 'lucide-react';
import { Panel, ShellHeader, bandCtaClass } from '@/components/savanna';
import { Button, Field, Input, Modal, Pill, Select, Table, Td } from '~/components/ui';
import { api, errorText } from '~/lib/api';
import { useAuth } from '~/lib/auth';
import { dateTime } from '~/lib/format';

export default function Team() {
    const me = useAuth((s) => s.user);
    const qc = useQueryClient();
    const [adding, setAdding] = useState(false);
    const { data, isLoading } = useQuery({ queryKey: ['team'], queryFn: async () => (await api.get('/admin/team/')).data });
    const update = useMutation({
        mutationFn: async ({ id, ...body }: any) => (await api.patch(`/admin/team/${id}/`, body)).data,
        onSuccess: () => { toast.success('Updated'); qc.invalidateQueries({ queryKey: ['team'] }); },
        onError: (err) => toast.error(errorText(err)),
    });
    return (
        <>
            <ShellHeader title="Team" subtitle="People who run the platform. Support staff can view everything and add notes; admins can change settings and move money."
                actions={<button className={bandCtaClass} onClick={() => setAdding(true)}><Plus className="h-4 w-4" />Add member</button>} />
            <Panel>
                <Table loading={isLoading} head={['Name', 'Role', 'Status', 'Last sign-in', '']}>
                    {data?.map((u: any) => (
                        <tr key={u.id}>
                            <Td><b>{u.full_name}</b><span className="block text-[12.5px] text-muted-foreground">{u.email}</span></Td>
                            <Td>
                                <Select className="h-9 w-48" value={u.role} disabled={u.id === me?.id} onChange={(e) => update.mutate({ id: u.id, role: e.target.value })}>
                                    <option value="platform_admin">Platform admin</option><option value="platform_staff">Support</option>
                                </Select>
                            </Td>
                            <Td><Pill status={u.is_active ? 'ok' : 'void'} label={u.is_active ? 'Active' : 'Disabled'} /></Td>
                            <Td className="text-[12.5px] text-muted-foreground">{u.last_login ? dateTime(u.last_login) : 'never'}</Td>
                            <Td className="text-right">{u.id !== me?.id && <Button size="sm" variant="outline" onClick={() => update.mutate({ id: u.id, is_active: !u.is_active })}>{u.is_active ? 'Disable' : 'Enable'}</Button>}</Td>
                        </tr>
                    ))}
                </Table>
            </Panel>
            {adding && <AddMember onClose={() => setAdding(false)} />}
        </>
    );
}

function AddMember({ onClose }: { onClose: () => void }) {
    const qc = useQueryClient();
    const [form, setForm] = useState({ first_name: '', last_name: '', email: '', role: 'platform_staff', password: '' });
    const add = useMutation({
        mutationFn: async () => (await api.post('/admin/team/', form)).data,
        onSuccess: () => { toast.success('Added'); qc.invalidateQueries({ queryKey: ['team'] }); onClose(); },
        onError: (err) => toast.error(errorText(err)),
    });
    const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
    return (
        <Modal open onClose={onClose} title="Add a team member">
            <div className="grid gap-3 sm:grid-cols-2">
                <Field label="First name"><Input value={form.first_name} onChange={(e) => set('first_name', e.target.value)} /></Field>
                <Field label="Last name"><Input value={form.last_name} onChange={(e) => set('last_name', e.target.value)} /></Field>
                <Field label="Email" className="sm:col-span-2"><Input type="email" value={form.email} onChange={(e) => set('email', e.target.value)} /></Field>
                <Field label="Role">
                    <Select value={form.role} onChange={(e) => set('role', e.target.value)}><option value="platform_staff">Support</option><option value="platform_admin">Platform admin</option></Select>
                </Field>
                <Field label="Password"><Input type="text" value={form.password} onChange={(e) => set('password', e.target.value)} /></Field>
            </div>
            <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={() => add.mutate()} disabled={add.isPending}>Add</Button></div>
        </Modal>
    );
}
