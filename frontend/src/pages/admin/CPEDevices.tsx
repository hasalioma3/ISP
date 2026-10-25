import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cpeDeviceAPI, adminAPI } from '../../services/api';
import toast from 'react-hot-toast';
import { format } from 'date-fns';
import {
    Router, Search, RefreshCw, Power, Wifi, Loader2, UserPlus, UserMinus, X, Activity,
} from 'lucide-react';
import { Card } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { getErrorMessage } from '../../utils/getErrorMessage';

const BRAND_LABEL: Record<string, string> = { huawei: 'Huawei', tenda: 'Tenda', tplink: 'TP-Link', other: 'Other' };

export default function CPEDevices() {
    const [search, setSearch] = useState('');
    const [brandFilter, setBrandFilter] = useState('');
    const [unlinkedOnly, setUnlinkedOnly] = useState(false);
    const [selectedId, setSelectedId] = useState<number | null>(null);

    const { data, isLoading, isError, error } = useQuery({
        queryKey: ['cpe-devices', search, brandFilter, unlinkedOnly],
        queryFn: async () => {
            const res = await cpeDeviceAPI.getDevices({
                search: search || undefined,
                brand: brandFilter || undefined,
                unlinked: unlinkedOnly || undefined,
            });
            return res.data.results || res.data;
        },
    });

    const devices = data || [];

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6 text-foreground flex items-center gap-2">
                <Router className="h-6 w-6 text-primary" /> CPE Devices
            </h1>

            <Card padding={false} className="overflow-hidden">
                <div className="flex flex-wrap items-center gap-3 p-4 border-b border-border">
                    <div className="relative flex-1 min-w-[220px]">
                        <input
                            type="text"
                            placeholder="Search by serial number..."
                            className="pl-10 pr-4 py-2 border border-input rounded-lg w-full bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                        />
                        <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                    </div>
                    <select
                        value={brandFilter}
                        onChange={(e) => setBrandFilter(e.target.value)}
                        className="border border-input rounded-lg px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                    >
                        <option value="">All Brands</option>
                        {Object.entries(BRAND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                    <label className="flex items-center gap-2 text-sm text-foreground/80">
                        <input type="checkbox" checked={unlinkedOnly} onChange={(e) => setUnlinkedOnly(e.target.checked)} />
                        Unlinked only
                    </label>
                </div>

                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-border">
                        <thead className="bg-secondary">
                            <tr>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Serial Number</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Brand</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Customer</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Status</th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Last Inform</th>
                                <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Manage</th>
                            </tr>
                        </thead>
                        <tbody className="bg-card divide-y divide-border">
                            {isLoading ? (
                                <tr><td colSpan={6} className="px-6 py-8 text-center text-muted-foreground">
                                    <Loader2 className="h-5 w-5 animate-spin inline mr-2" /> Loading devices...
                                </td></tr>
                            ) : isError ? (
                                <tr><td colSpan={6} className="px-6 py-8 text-center text-red-600">Error: {(error as Error).message}</td></tr>
                            ) : devices.length === 0 ? (
                                <tr><td colSpan={6} className="px-6 py-8 text-center text-muted-foreground">No devices found.</td></tr>
                            ) : devices.map((d: any) => (
                                <tr key={d.id} className="hover:bg-secondary/60 cursor-pointer" onClick={() => setSelectedId(d.id)}>
                                    <td className="px-4 py-4 text-sm font-medium text-foreground font-mono">{d.serial_number}</td>
                                    <td className="px-4 py-4 text-sm text-muted-foreground">{d.brand_display}</td>
                                    <td className="px-4 py-4 text-sm">
                                        {d.customer_username ? (
                                            <span className="text-foreground">{d.customer_username}</span>
                                        ) : (
                                            <span className="text-muted-foreground italic">Unlinked</span>
                                        )}
                                    </td>
                                    <td className="px-4 py-4">
                                        <Badge variant={d.is_online ? 'success' : 'secondary'}>{d.is_online ? 'Online' : 'Offline'}</Badge>
                                    </td>
                                    <td className="px-4 py-4 text-sm text-muted-foreground">
                                        {d.last_inform ? format(new Date(d.last_inform), 'MMM d, yyyy HH:mm') : 'Never'}
                                    </td>
                                    <td className="px-4 py-4 text-right">
                                        <Button size="sm" variant="secondary" onClick={(e) => { e.stopPropagation(); setSelectedId(d.id); }}>
                                            Manage
                                        </Button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </Card>

            {selectedId !== null && (
                <DeviceDetailDialog deviceId={selectedId} onClose={() => setSelectedId(null)} />
            )}
        </div>
    );
}

function DeviceDetailDialog({ deviceId, onClose }: { deviceId: number; onClose: () => void }) {
    const queryClient = useQueryClient();
    const [wifiForm, setWifiForm] = useState({ ssid: '', password: '' });
    const [customerSearch, setCustomerSearch] = useState('');
    const [showLinkPanel, setShowLinkPanel] = useState(false);
    const [diagnostics, setDiagnostics] = useState<any>(null);

    const { data: device, isLoading } = useQuery({
        queryKey: ['cpe-device', deviceId],
        queryFn: async () => (await cpeDeviceAPI.getDevice(deviceId)).data,
    });

    const invalidate = () => {
        queryClient.invalidateQueries({ queryKey: ['cpe-devices'] });
        queryClient.invalidateQueries({ queryKey: ['cpe-device', deviceId] });
    };

    const rebootMutation = useMutation({
        mutationFn: () => cpeDeviceAPI.reboot(deviceId),
        onSuccess: (res) => toast.success(res.data.queued_only ? 'Reboot queued -- device is offline, will apply when it next checks in' : 'Reboot sent'),
        onError: (err: any) => toast.error(getErrorMessage(err, 'Reboot failed')),
    });

    const factoryResetMutation = useMutation({
        mutationFn: () => cpeDeviceAPI.factoryReset(deviceId),
        onSuccess: (res) => toast.success(res.data.queued_only ? 'Factory reset queued -- device is offline' : 'Factory reset sent'),
        onError: (err: any) => toast.error(getErrorMessage(err, 'Factory reset failed')),
    });

    const setWifiMutation = useMutation({
        mutationFn: () => cpeDeviceAPI.setWifi(deviceId, wifiForm),
        onSuccess: (res) => {
            toast.success(res.data.queued_only ? 'WiFi change queued -- device is offline' : 'WiFi updated');
            invalidate();
        },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Failed to update WiFi')),
    });

    const diagnosticsMutation = useMutation({
        mutationFn: () => cpeDeviceAPI.getDiagnostics(deviceId),
        onSuccess: (res) => setDiagnostics(res.data),
        onError: (err: any) => toast.error(getErrorMessage(err, 'Diagnostics failed')),
    });

    const unlinkMutation = useMutation({
        mutationFn: () => cpeDeviceAPI.unlinkCustomer(deviceId),
        onSuccess: () => { toast.success('Customer unlinked'); invalidate(); },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Failed to unlink')),
    });

    const { data: customerResults } = useQuery({
        queryKey: ['cpe-link-customer-search', customerSearch],
        queryFn: async () => {
            const res = await adminAPI.getSubscribers({ search: customerSearch || undefined, page_size: 8 });
            return res.data.results || [];
        },
        enabled: showLinkPanel,
    });

    const linkMutation = useMutation({
        mutationFn: (customerId: number) => cpeDeviceAPI.linkCustomer(deviceId, customerId),
        onSuccess: () => { toast.success('Device linked to customer'); setShowLinkPanel(false); invalidate(); },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Failed to link device')),
    });

    return (
        <Dialog open onOpenChange={(open) => !open && onClose()}>
            <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Router className="h-5 w-5 text-primary" />
                        {device?.serial_number || 'Device'}
                    </DialogTitle>
                </DialogHeader>

                {isLoading || !device ? (
                    <div className="py-8 text-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin inline mr-2" /> Loading...</div>
                ) : (
                    <div className="space-y-5">
                        <div className="flex items-center justify-between">
                            <Badge variant={device.is_online ? 'success' : 'secondary'}>{device.is_online ? 'Online' : 'Offline'}</Badge>
                            <span className="text-xs text-muted-foreground">
                                {device.last_inform ? `Last seen ${format(new Date(device.last_inform), 'MMM d, HH:mm')}` : 'Never checked in'}
                            </span>
                        </div>

                        <div className="grid grid-cols-2 gap-3 text-sm">
                            <div><span className="text-muted-foreground">Brand</span><p className="font-medium text-foreground">{device.brand_display}</p></div>
                            <div><span className="text-muted-foreground">Model</span><p className="font-medium text-foreground">{device.model_name || '-'}</p></div>
                            <div><span className="text-muted-foreground">Software</span><p className="font-medium text-foreground">{device.software_version || '-'}</p></div>
                            <div><span className="text-muted-foreground">MAC</span><p className="font-medium text-foreground">{device.mac_address || '-'}</p></div>
                        </div>

                        {/* Customer link */}
                        <div className="border-t border-border pt-4">
                            <Label className="mb-2 block">Customer</Label>
                            {device.customer_username ? (
                                <div className="flex items-center justify-between bg-secondary rounded-lg px-3 py-2">
                                    <span className="text-sm text-foreground">{device.customer_username} {device.customer_full_name && `(${device.customer_full_name})`}</span>
                                    <Button size="sm" variant="ghost" onClick={() => unlinkMutation.mutate()} disabled={unlinkMutation.isPending}>
                                        <UserMinus className="h-4 w-4" /> Unlink
                                    </Button>
                                </div>
                            ) : showLinkPanel ? (
                                <div className="space-y-2">
                                    <Input placeholder="Search customer..." value={customerSearch} onChange={(e) => setCustomerSearch(e.target.value)} autoFocus />
                                    <ul className="border border-border rounded-lg divide-y divide-border max-h-40 overflow-y-auto">
                                        {(customerResults || []).map((c: any) => (
                                            <li key={c.id}>
                                                <button
                                                    disabled={linkMutation.isPending}
                                                    onClick={() => linkMutation.mutate(c.id)}
                                                    className="w-full text-left px-3 py-2 text-sm hover:bg-secondary disabled:opacity-50"
                                                >
                                                    {c.username} <span className="text-muted-foreground">({c.phone_number})</span>
                                                </button>
                                            </li>
                                        ))}
                                        {customerResults?.length === 0 && <li className="px-3 py-2 text-sm text-muted-foreground">No matches</li>}
                                    </ul>
                                    <Button size="sm" variant="ghost" onClick={() => setShowLinkPanel(false)}><X className="h-4 w-4" /> Cancel</Button>
                                </div>
                            ) : (
                                <Button size="sm" variant="secondary" onClick={() => setShowLinkPanel(true)}>
                                    <UserPlus className="h-4 w-4" /> Link to customer
                                </Button>
                            )}
                        </div>

                        {/* WiFi */}
                        <div className="border-t border-border pt-4 space-y-2">
                            <Label className="flex items-center gap-1.5"><Wifi className="h-4 w-4" /> WiFi</Label>
                            <Input placeholder="SSID" value={wifiForm.ssid} onChange={(e) => setWifiForm({ ...wifiForm, ssid: e.target.value })} />
                            <Input type="password" placeholder="Password (min 8 characters)" value={wifiForm.password} onChange={(e) => setWifiForm({ ...wifiForm, password: e.target.value })} />
                            <Button
                                size="sm"
                                disabled={setWifiMutation.isPending || !wifiForm.ssid || wifiForm.password.length < 8}
                                onClick={() => setWifiMutation.mutate()}
                            >
                                {setWifiMutation.isPending ? 'Applying...' : 'Update WiFi'}
                            </Button>
                        </div>

                        {/* Diagnostics */}
                        <div className="border-t border-border pt-4 space-y-2">
                            <Button size="sm" variant="secondary" onClick={() => diagnosticsMutation.mutate()} disabled={diagnosticsMutation.isPending}>
                                <Activity className="h-4 w-4" /> {diagnosticsMutation.isPending ? 'Running...' : 'Run Diagnostics'}
                            </Button>
                            {diagnostics && (
                                <pre className="bg-secondary rounded-lg p-3 text-xs overflow-x-auto text-foreground/80">{JSON.stringify(diagnostics.data, null, 2)}</pre>
                            )}
                        </div>

                        {/* Destructive actions */}
                        <div className="border-t border-border pt-4 flex gap-2">
                            <Button
                                size="sm" variant="secondary"
                                disabled={rebootMutation.isPending}
                                onClick={() => { if (confirm(`Reboot ${device.serial_number}? The customer will briefly lose connectivity.`)) rebootMutation.mutate(); }}
                            >
                                <RefreshCw className="h-4 w-4" /> Reboot
                            </Button>
                            <Button
                                size="sm" variant="destructive"
                                disabled={factoryResetMutation.isPending}
                                onClick={() => { if (confirm(`Factory reset ${device.serial_number}? This erases ALL settings on the device, including WiFi. This cannot be undone.`)) factoryResetMutation.mutate(); }}
                            >
                                <Power className="h-4 w-4" /> Factory Reset
                            </Button>
                        </div>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
