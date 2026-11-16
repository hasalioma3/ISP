import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminAPI, billingAPI } from '../services/api';
import { X, Save, PlusCircle, Eye, EyeOff, KeyRound, Wallet, ArrowLeftRight, Pencil, CalendarClock } from 'lucide-react';
import { format } from 'date-fns';
import toast from 'react-hot-toast';
import UsageChartPanels from './UsageChartPanels';
import LiveActivity from './LiveActivity';
import { useAuthStore } from '../store/authStore';

export default function SubscriberDetailModal({ id, onClose, initialTab = 'details' }: { id: number; onClose: () => void; initialTab?: 'details' | 'usage' | 'plans' }) {
    const [tab, setTab] = useState<'details' | 'usage' | 'plans'>(initialTab);
    const [form, setForm] = useState<any | null>(null);
    const [topUpPlanId, setTopUpPlanId] = useState('');
    const [topUpStaticIp, setTopUpStaticIp] = useState('');
    const [balanceAmount, setBalanceAmount] = useState('');
    const [showPasswords, setShowPasswords] = useState(false);
    const [pppoeDraft, setPppoeDraft] = useState<{ pppoe_username: string; pppoe_password: string } | null>(null);
    const isSuperuser = useAuthStore((state) => state.user?.is_superuser);
    const role = useAuthStore((state) => state.user?.role);
    // Technicians can't extend subscriptions or add money (enforced by the API too).
    const canHandleMoney = !!isSuperuser || role !== 'technician';
    const [extendTo, setExtendTo] = useState('');
    const queryClient = useQueryClient();

    const { data: subscriber, isLoading } = useQuery({
        queryKey: ['subscriber', id],
        queryFn: async () => {
            const res = await adminAPI.getSubscriber(id);
            if (!form) setForm(res.data);
            return res.data;
        }
    });

    const { data: usageData, isLoading: usageLoading } = useQuery({
        queryKey: ['subscriber-usage', id],
        queryFn: async () => {
            const res = await adminAPI.getSubscriberUsage(id);
            return res.data;
        },
        enabled: tab === 'usage' || tab === 'plans'
    });

    const { data: plans } = useQuery({
        queryKey: ['plans'],
        queryFn: async () => {
            const res = await billingAPI.getPlans();
            return res.data.results || res.data;
        }
    });

    const saveMutation = useMutation({
        mutationFn: (data: any) => adminAPI.updateSubscriber(id, data),
        onSuccess: () => {
            toast.success('Subscriber updated');
            queryClient.invalidateQueries({ queryKey: ['admin-subscribers'] });
            queryClient.invalidateQueries({ queryKey: ['subscriber', id] });
            queryClient.invalidateQueries({ queryKey: ['online-users'] });
        },
        onError: () => toast.error('Failed to update subscriber')
    });

    const pppoeMutation = useMutation({
        mutationFn: (data: { pppoe_username: string; pppoe_password: string }) => adminAPI.updatePppoeCredentials(id, data),
        onSuccess: (res) => {
            const { router_synced, router_error, subscriber: updated } = res.data;
            if (router_synced) toast.success('PPPoE login updated on the router');
            else if (router_error) toast.error(`Saved, but NOT updated on the router: ${router_error}`, { duration: 8000 });
            else toast.success('Saved -- applied to the router when this customer is next activated');
            setForm({ ...form, pppoe_username: updated.pppoe_username, pppoe_password: updated.pppoe_password });
            setPppoeDraft(null);
            queryClient.invalidateQueries({ queryKey: ['admin-subscribers'] });
            queryClient.invalidateQueries({ queryKey: ['subscriber', id] });
            queryClient.invalidateQueries({ queryKey: ['online-users'] });
        },
        onError: (err: any) => toast.error(err.response?.data?.error || 'Failed to update PPPoE login')
    });

    const savePppoe = () => {
        if (!pppoeDraft) return;
        if (!window.confirm('This disconnects the customer. Their router must use the new login to reconnect. Continue?')) return;
        pppoeMutation.mutate(pppoeDraft);
    };

    const topUpMutation = useMutation({
        mutationFn: () => adminAPI.topUpSubscriber(id, parseInt(topUpPlanId), topUpStaticIp || undefined),
        onSuccess: (res) => {
            toast.success(res.data.message || 'Plan assigned');
            setTopUpPlanId('');
            setTopUpStaticIp('');
            queryClient.invalidateQueries({ queryKey: ['admin-subscribers'] });
            queryClient.invalidateQueries({ queryKey: ['subscriber', id] });
            queryClient.invalidateQueries({ queryKey: ['subscriber-usage', id] });
            queryClient.invalidateQueries({ queryKey: ['online-users'] });
        },
        onError: (err: any) => toast.error(err.response?.data?.error || 'Failed to assign plan')
    });

    const addBalanceMutation = useMutation({
        mutationFn: () => adminAPI.addSubscriberBalance(id, parseFloat(balanceAmount)),
        onSuccess: (res) => {
            toast.success(res.data.message || 'Balance added');
            setBalanceAmount('');
            queryClient.invalidateQueries({ queryKey: ['admin-subscribers'] });
            queryClient.invalidateQueries({ queryKey: ['subscriber', id] });
        },
        onError: (err: any) => toast.error(err.response?.data?.error || 'Failed to add balance')
    });

    const switchPlanMutation = useMutation({
        mutationFn: () => adminAPI.switchSubscriberPlan(id, parseInt(topUpPlanId)),
        onSuccess: (res) => {
            toast.success(res.data.message || 'Plan switched');
            setTopUpPlanId('');
            queryClient.invalidateQueries({ queryKey: ['admin-subscribers'] });
            queryClient.invalidateQueries({ queryKey: ['subscriber', id] });
            queryClient.invalidateQueries({ queryKey: ['subscriber-usage', id] });
            queryClient.invalidateQueries({ queryKey: ['online-users'] });
        },
        onError: (err: any) => toast.error(err.response?.data?.error || 'Failed to switch plan')
    });

    const extendMutation = useMutation({
        mutationFn: () => adminAPI.extendSubscriber(id, extendTo),
        onSuccess: (res) => {
            toast.success(res.data.message || 'Subscription extended');
            setExtendTo('');
            queryClient.invalidateQueries({ queryKey: ['admin-subscribers'] });
            queryClient.invalidateQueries({ queryKey: ['admin-subscriber-summary'] });
            queryClient.invalidateQueries({ queryKey: ['subscriber', id] });
            queryClient.invalidateQueries({ queryKey: ['subscriber-usage', id] });
        },
        onError: (err: any) => toast.error(err.response?.data?.error || 'Failed to extend subscription'),
    });
    const isExpired = !subscriber?.calculated_expiry || new Date(subscriber.calculated_expiry).getTime() <= Date.now()
        || subscriber?.current_plan_status !== 'active';
    const confirmExtend = () => {
        const when = new Date(extendTo).toLocaleString('en-GB', { timeZone: 'Africa/Nairobi', dateStyle: 'medium', timeStyle: 'short' });
        const what = isExpired ? 'Reactivate and extend' : 'Extend';
        if (window.confirm(`${what} ${subscriber?.current_plan_name || 'the plan'} until ${when}? No payment is recorded; the customer and the staff alert number are notified.`)) {
            extendMutation.mutate();
        }
    };

    const handleSave = (e: React.FormEvent) => {
        e.preventDefault();
        const { username, email, phone_number, first_name, last_name, service_type, address, id_number, notes, static_ip_address } = form;
        saveMutation.mutate({ username, email, phone_number, first_name, last_name, service_type, address, id_number, notes, static_ip_address });
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-card rounded-xl shadow-xl w-full max-w-4xl max-h-[85vh] flex flex-col">
                <div className="flex justify-between items-center p-6 border-b">
                    <div>
                        <h3 className="text-lg font-bold">{subscriber?.full_name || subscriber?.username || 'Subscriber'}</h3>
                        <p className="text-sm text-muted-foreground">{subscriber?.username} &middot; {subscriber?.phone_number}</p>
                    </div>
                    <button onClick={onClose} className="p-1 text-muted-foreground hover:text-muted-foreground">
                        <X className="h-5 w-5" />
                    </button>
                </div>

                <div className="flex border-b px-6">
                    {(['details', 'usage', 'plans'] as const).map(t => (
                        <button
                            key={t}
                            onClick={() => setTab(t)}
                            className={`px-4 py-3 text-sm font-medium border-b-2 capitalize transition-colors ${tab === t
                                ? 'border-ring text-primary'
                                : 'border-transparent text-muted-foreground hover:text-foreground/80'
                                }`}
                        >
                            {t === 'plans' ? 'Plans & Top-up' : t}
                        </button>
                    ))}
                </div>

                <div className="overflow-y-auto flex-1 p-6">
                    {isLoading || !form ? (
                        <div className="text-center py-8 text-muted-foreground">Loading...</div>
                    ) : tab === 'details' ? (
                        <form onSubmit={handleSave} className="space-y-4">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <Field label="First Name" value={form.first_name} onChange={v => setForm({ ...form, first_name: v })} />
                                <Field label="Last Name" value={form.last_name} onChange={v => setForm({ ...form, last_name: v })} />
                                <Field label="Username" value={form.username} onChange={v => setForm({ ...form, username: v })} />
                                <Field label="Email" value={form.email} onChange={v => setForm({ ...form, email: v })} />
                                <Field label="Phone Number" value={form.phone_number} onChange={v => setForm({ ...form, phone_number: v })} />
                                <div>
                                    <label className="block text-sm font-medium text-foreground/80 mb-1">Service Type</label>
                                    <select
                                        className="w-full border rounded-lg px-3 py-2"
                                        value={form.service_type}
                                        onChange={e => setForm({ ...form, service_type: e.target.value })}
                                    >
                                        <option value="pppoe">PPPoE</option>
                                        <option value="hotspot">Hotspot</option>
                                        <option value="both">Both</option>
                                        <option value="static">Static IP</option>
                                    </select>
                                </div>
                                <Field label="ID Number" value={form.id_number} onChange={v => setForm({ ...form, id_number: v })} />
                                <Field label="Address" value={form.address} onChange={v => setForm({ ...form, address: v })} />
                                {form.service_type === 'static' && (
                                    <Field label="Static IP Address" value={form.static_ip_address} onChange={v => setForm({ ...form, static_ip_address: v })} />
                                )}
                            </div>

                            {isSuperuser && (form.pppoe_username || form.hotspot_username || ['pppoe', 'both'].includes(form.service_type)) && (
                                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                                    <div className="flex justify-between items-center mb-2">
                                        <h4 className="text-sm font-bold text-amber-900 flex items-center gap-2">
                                            <KeyRound className="h-4 w-4" /> Credentials (Superuser Only)
                                        </h4>
                                        <button
                                            type="button"
                                            onClick={() => setShowPasswords(!showPasswords)}
                                            className="flex items-center text-xs text-amber-800 hover:text-amber-900"
                                        >
                                            {showPasswords ? <EyeOff className="h-3.5 w-3.5 mr-1" /> : <Eye className="h-3.5 w-3.5 mr-1" />}
                                            {showPasswords ? 'Hide' : 'Reveal'}
                                        </button>
                                    </div>
                                    <div className="space-y-1 font-mono text-sm text-amber-900">
                                        {pppoeDraft ? (
                                            <div className="font-sans space-y-2 py-1">
                                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                                    <input
                                                        className="w-full border border-amber-300 rounded-lg px-3 py-2 text-sm bg-white"
                                                        placeholder="PPPoE username" autoComplete="off"
                                                        value={pppoeDraft.pppoe_username}
                                                        onChange={e => setPppoeDraft({ ...pppoeDraft, pppoe_username: e.target.value })}
                                                    />
                                                    <input
                                                        className="w-full border border-amber-300 rounded-lg px-3 py-2 text-sm bg-white"
                                                        placeholder="PPPoE password" autoComplete="new-password"
                                                        value={pppoeDraft.pppoe_password}
                                                        onChange={e => setPppoeDraft({ ...pppoeDraft, pppoe_password: e.target.value })}
                                                    />
                                                </div>
                                                <div className="flex gap-2">
                                                    <button
                                                        type="button" onClick={savePppoe}
                                                        disabled={pppoeMutation.isPending || !pppoeDraft.pppoe_username || !pppoeDraft.pppoe_password}
                                                        className="flex items-center px-3 py-1.5 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 text-xs font-medium"
                                                    >
                                                        <Save className="h-3.5 w-3.5 mr-1" />
                                                        {pppoeMutation.isPending ? 'Saving...' : 'Save & Sync to Router'}
                                                    </button>
                                                    <button
                                                        type="button" onClick={() => setPppoeDraft(null)}
                                                        className="px-3 py-1.5 border border-amber-300 rounded-lg text-xs text-amber-900 hover:bg-amber-100"
                                                    >
                                                        Cancel
                                                    </button>
                                                </div>
                                            </div>
                                        ) : (form.pppoe_username || ['pppoe', 'both'].includes(form.service_type)) && (
                                            <p className="flex items-center gap-2">
                                                <span>PPPoE: {form.pppoe_username || '(not set)'} / {showPasswords ? (form.pppoe_password || '(not set)') : '••••••••'}</span>
                                                <button
                                                    type="button"
                                                    onClick={() => setPppoeDraft({ pppoe_username: form.pppoe_username || form.username, pppoe_password: form.pppoe_password || '' })}
                                                    className="flex items-center font-sans text-xs text-amber-800 hover:text-amber-900 underline"
                                                >
                                                    <Pencil className="h-3 w-3 mr-0.5" /> Edit
                                                </button>
                                            </p>
                                        )}
                                        {form.hotspot_username && (
                                            <p>Hotspot: {form.hotspot_username} / {showPasswords ? (form.hotspot_password || '(not set)') : '••••••••'}</p>
                                        )}
                                    </div>
                                    <p className="text-xs text-amber-700 mt-2">
                                        This is also their portal login password at the time it was set -- if they've since changed
                                        their portal password via "Change Password", it will have diverged from this value. The
                                        portal password itself can never be shown; it's a one-way hash, not stored anywhere.
                                    </p>
                                </div>
                            )}

                            <div>
                                <label className="block text-sm font-medium text-foreground/80 mb-1">Notes</label>
                                <textarea
                                    className="w-full border rounded-lg px-3 py-2"
                                    rows={3}
                                    value={form.notes || ''}
                                    onChange={e => setForm({ ...form, notes: e.target.value })}
                                />
                            </div>
                            <button
                                type="submit"
                                disabled={saveMutation.isPending}
                                className="flex items-center px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 disabled:opacity-50"
                            >
                                <Save className="h-4 w-4 mr-2" />
                                {saveMutation.isPending ? 'Saving...' : 'Save Changes'}
                            </button>
                        </form>
                    ) : tab === 'usage' ? (
                        usageLoading ? (
                            <div className="text-center py-8 text-muted-foreground">Loading usage...</div>
                        ) : (
                            <div>
                                <LiveActivity customerId={id} />
                                <div className="mb-6">
                                    <UsageChartPanels chart={usageData?.chart} loading={false} />
                                </div>
                                {/* Current plan period alongside all time. */}
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
                                    {[
                                        {
                                            title: usageData?.plan_totals ? `Current plan · ${usageData.plan_totals.plan_name}` : 'Current plan',
                                            note: usageData?.plan_totals
                                                ? `Since ${format(new Date(usageData.plan_totals.start_date), 'd MMM yyyy')}`
                                                  + (usageData.plan_totals.data_limit_gb ? ` · cap ${usageData.plan_totals.data_limit_gb} GB` : '')
                                                : 'No active plan',
                                            t: usageData?.plan_totals,
                                        },
                                        { title: 'All time', note: 'Everything recorded for this subscriber', t: usageData?.totals },
                                    ].map(({ title, note, t }) => (
                                        <div key={title} className="rounded-2xl border border-border bg-secondary/60 p-4">
                                            <p className="text-sm font-bold text-foreground">{title}</p>
                                            <p className="text-xs text-muted-foreground">{note}</p>
                                            <p className="num mt-3 text-2xl font-extrabold text-foreground">{t ? `${t.total_gb} GB` : '—'}</p>
                                            {t && (
                                                <p className="num mt-1 text-xs text-muted-foreground">↑ {t.upload_gb} GB · ↓ {t.download_gb} GB</p>
                                            )}
                                        </div>
                                    ))}
                                </div>
                                <h4 className="text-sm font-bold mb-2">Session History</h4>
                                <div className="overflow-x-auto">
                                    <table className="min-w-full divide-y divide-border text-sm">
                                        <thead>
                                            <tr className="text-left text-xs text-muted-foreground uppercase">
                                                <th className="py-2 pr-4">Date</th>
                                                <th className="py-2 pr-4">IP</th>
                                                <th className="py-2 text-right pr-4">Up (GB)</th>
                                                <th className="py-2 text-right">Down (GB)</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-border">
                                            {usageData?.usage_records?.length === 0 ? (
                                                <tr><td colSpan={4} className="py-6 text-center text-muted-foreground">No usage recorded yet.</td></tr>
                                            ) : usageData?.usage_records?.map((u: any) => (
                                                <tr key={u.id}>
                                                    <td className="py-2 pr-4 whitespace-nowrap">{format(new Date(u.created_at), 'MMM d, yyyy HH:mm')}</td>
                                                    <td className="py-2 pr-4 text-muted-foreground">{u.framed_ip_address || '-'}</td>
                                                    <td className="py-2 text-right pr-4">{(u.upload_bytes / (1024 ** 3)).toFixed(2)}</td>
                                                    <td className="py-2 text-right">{(u.download_bytes / (1024 ** 3)).toFixed(2)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )
                    ) : (
                        <div className="space-y-6">
                            {isSuperuser && (
                                <div className="rounded-lg border border-primary/30 bg-accent p-4">
                                    <h4 className="text-sm font-bold mb-1 flex items-center gap-2"><CalendarClock className="h-4 w-4" /> Extend to a date</h4>
                                    <p className="text-xs text-muted-foreground mb-3">
                                        {subscriber?.current_plan_name
                                            ? <>Current: <span className="font-semibold text-foreground">{subscriber.current_plan_name}</span>{' '}
                                                {subscriber.calculated_expiry ? `${isExpired ? 'expired' : 'expires'} ${format(new Date(subscriber.calculated_expiry), 'd MMM yyyy HH:mm')}` : ''}.
                                                {isExpired && ' Extending reactivates it on the router.'}</>
                                            : 'This subscriber has no plan yet; assign one first.'}
                                        {' '}Superadmin only. No payment is recorded.
                                    </p>
                                    <div className="flex flex-col sm:flex-row gap-2">
                                        <input
                                            type="datetime-local"
                                            aria-label="New expiry date and time"
                                            className="flex-1 border rounded-lg px-3 py-2 text-sm"
                                            min={format(new Date(), "yyyy-MM-dd'T'HH:mm")}
                                            value={extendTo}
                                            onChange={(e) => setExtendTo(e.target.value)}
                                        />
                                        <button
                                            disabled={!extendTo || !subscriber?.current_plan_name || extendMutation.isPending}
                                            onClick={confirmExtend}
                                            className="flex items-center justify-center px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 text-sm font-medium"
                                        >
                                            <CalendarClock className="h-4 w-4 mr-2" />
                                            {extendMutation.isPending ? 'Saving...' : isExpired ? 'Reactivate & extend' : 'Extend'}
                                        </button>
                                    </div>
                                </div>
                            )}

                            {canHandleMoney ? (
                                <>
                                <div className="bg-primary/10 rounded-lg p-4">
                                    <h4 className="text-sm font-bold mb-1 flex items-center gap-2"><Wallet className="h-4 w-4" /> Account Balance</h4>
                                    <p className="text-2xl font-bold text-primary mb-3">KES {Number(subscriber?.account_balance || 0).toLocaleString()}</p>
                                    <div className="flex flex-col sm:flex-row gap-2">
                                        <input
                                            type="number" min="0" step="0.01" placeholder="Amount to add"
                                            className="flex-1 border rounded-lg px-3 py-2 text-sm"
                                            value={balanceAmount}
                                            onChange={e => setBalanceAmount(e.target.value)}
                                        />
                                        <button
                                            disabled={!balanceAmount || addBalanceMutation.isPending}
                                            onClick={() => addBalanceMutation.mutate()}
                                            className="flex items-center px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 disabled:opacity-50 text-sm font-medium"
                                        >
                                            <PlusCircle className="h-4 w-4 mr-2" />
                                            {addBalanceMutation.isPending ? 'Adding...' : 'Add to Balance'}
                                        </button>
                                    </div>
                                </div>

                                <div className="bg-secondary rounded-lg p-4">
                                    <h4 className="text-sm font-bold mb-3">Assign / Top Up / Switch Plan</h4>
                                    <div className="flex flex-col sm:flex-row gap-2">
                                        <select
                                            className="flex-1 border rounded-lg px-3 py-2 text-sm"
                                            value={topUpPlanId}
                                            onChange={e => setTopUpPlanId(e.target.value)}
                                        >
                                            <option value="">Select a plan...</option>
                                            {plans?.map((plan: any) => (
                                                <option key={plan.id} value={plan.id}>{plan.name} - KES {plan.price}</option>
                                            ))}
                                        </select>
                                        <button
                                            disabled={!topUpPlanId || topUpMutation.isPending}
                                            onClick={() => topUpMutation.mutate()}
                                            title="Record a fresh cash payment for this plan"
                                            className="flex items-center px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium"
                                        >
                                            <PlusCircle className="h-4 w-4 mr-2" />
                                            {topUpMutation.isPending ? 'Assigning...' : 'Confirm (Cash)'}
                                        </button>
                                        <button
                                            disabled={!topUpPlanId || switchPlanMutation.isPending}
                                            onClick={() => switchPlanMutation.mutate()}
                                            title="Pay for this plan from the customer's existing account balance instead"
                                            className="flex items-center px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 disabled:opacity-50 text-sm font-medium"
                                        >
                                            <ArrowLeftRight className="h-4 w-4 mr-2" />
                                            {switchPlanMutation.isPending ? 'Switching...' : 'Switch (Use Balance)'}
                                        </button>
                                    </div>
                                    {plans?.find((p: any) => String(p.id) === topUpPlanId)?.service_type === 'static' && !subscriber?.static_ip_address && (
                                        <div className="mt-3">
                                            <label className="block text-sm font-medium text-foreground/80 mb-1">Static IP Address</label>
                                            <input
                                                type="text" placeholder="10.5.70.50"
                                                className="w-full border rounded-lg px-3 py-2 text-sm"
                                                value={topUpStaticIp}
                                                onChange={e => setTopUpStaticIp(e.target.value)}
                                            />
                                            <p className="text-xs text-muted-foreground mt-1">
                                                This customer has no static IP on file yet -- enter the fixed IP already configured on their device.
                                            </p>
                                        </div>
                                    )}
                                </div>
                                </>
                            ) : (
                                <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">
                                    Recharging plans and adding money are handled by admins and sales. Ask one of them, or the superadmin, to renew this subscriber.
                                </div>
                            )}

                            <div>
                                <h4 className="text-sm font-bold mb-2">Subscription History</h4>
                                <div className="overflow-x-auto">
                                    <table className="min-w-full divide-y divide-border text-sm">
                                        <thead>
                                            <tr className="text-left text-xs text-muted-foreground uppercase">
                                                <th className="py-2 pr-4">Plan</th>
                                                <th className="py-2 pr-4">Status</th>
                                                <th className="py-2">Expiry</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-border">
                                            {usageData?.subscriptions?.length === 0 ? (
                                                <tr><td colSpan={3} className="py-4 text-center text-muted-foreground">No subscriptions yet.</td></tr>
                                            ) : usageData?.subscriptions?.map((s: any) => (
                                                <tr key={s.id}>
                                                    <td className="py-2 pr-4 font-medium whitespace-nowrap">{s.plan?.name}</td>
                                                    <td className="py-2 pr-4 capitalize">{s.status}</td>
                                                    <td className="py-2 text-muted-foreground whitespace-nowrap">{format(new Date(s.expiry_date), 'MMM d, yyyy')}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>

                            <div>
                                <h4 className="text-sm font-bold mb-2">Recent Transactions</h4>
                                <div className="overflow-x-auto">
                                    <table className="min-w-full divide-y divide-border text-sm">
                                        <thead>
                                            <tr className="text-left text-xs text-muted-foreground uppercase">
                                                <th className="py-2 pr-4">Amount</th>
                                                <th className="py-2 pr-4">Method</th>
                                                <th className="py-2 pr-4">M-Pesa Code</th>
                                                <th className="py-2 pr-4">Status</th>
                                                <th className="py-2">Date</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-border">
                                            {usageData?.transactions?.length === 0 ? (
                                                <tr><td colSpan={5} className="py-4 text-center text-muted-foreground">No transactions yet.</td></tr>
                                            ) : usageData?.transactions?.map((t: any) => (
                                                <tr key={t.id}>
                                                    <td className="py-2 pr-4 font-medium whitespace-nowrap">KES {Number(t.amount).toLocaleString()}</td>
                                                    <td className="py-2 pr-4 uppercase">{t.payment_method}</td>
                                                    <td className="py-2 pr-4 font-mono text-xs">{t.mpesa_receipt_number || '-'}</td>
                                                    <td className="py-2 pr-4 capitalize">{t.status}</td>
                                                    <td className="py-2 text-muted-foreground whitespace-nowrap">{format(new Date(t.created_at), 'MMM d, yyyy')}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
    return (
        <div>
            <label className="block text-sm font-medium text-foreground/80 mb-1">{label}</label>
            <input
                type="text"
                className="w-full border rounded-lg px-3 py-2"
                value={value || ''}
                onChange={e => onChange(e.target.value)}
            />
        </div>
    );
}
