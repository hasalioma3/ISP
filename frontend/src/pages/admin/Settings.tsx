import { useState, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminAPI, billingAPI, siteSettingsAPI } from '../../services/api';
import { Users as UsersIcon, CreditCard, Plus, Pencil, Trash2, X, Copy, ShieldCheck, Image as ImageIcon, Building2, Download, Upload, UploadCloud } from 'lucide-react';
import toast from 'react-hot-toast';
import { useSiteSettings } from '../../hooks/useSiteSettings';
import { downloadBlob } from '../../utils/downloadBlob';

const ROLES = [
    { value: 'admin', label: 'Admin' },
    { value: 'technician', label: 'Technician' },
    { value: 'sales', label: 'Sales Person' },
];

const ROLE_BADGE: Record<string, string> = {
    admin: 'bg-purple-100 text-purple-800',
    technician: 'bg-blue-100 text-blue-800',
    sales: 'bg-emerald-100 text-emerald-800',
};

export default function Settings() {
    const [urlParams] = useSearchParams();
    const [activeTab, setActiveTab] = useState(urlParams.get('tab') || 'branding');

    return (
        <div>
            <h1 className="text-2xl font-bold mb-6">System Settings</h1>

            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden min-h-[500px]">
                {/* Tabs */}
                <div className="flex border-b">
                    <button
                        onClick={() => setActiveTab('branding')}
                        className={`flex items-center px-6 py-4 text-sm font-medium border-b-2 transition-colors ${activeTab === 'branding'
                            ? 'border-blue-500 text-blue-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                            }`}
                    >
                        <Building2 className="h-4 w-4 mr-2" />
                        General Settings
                    </button>
                    <button
                        onClick={() => setActiveTab('staff')}
                        className={`flex items-center px-6 py-4 text-sm font-medium border-b-2 transition-colors ${activeTab === 'staff'
                            ? 'border-blue-500 text-blue-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                            }`}
                    >
                        <UsersIcon className="h-4 w-4 mr-2" />
                        Staff
                    </button>
                    <button
                        onClick={() => setActiveTab('manual')}
                        className={`flex items-center px-6 py-4 text-sm font-medium border-b-2 transition-colors ${activeTab === 'manual'
                            ? 'border-blue-500 text-blue-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                            }`}
                    >
                        <CreditCard className="h-4 w-4 mr-2" />
                        Manual Customer
                    </button>
                    <button
                        onClick={() => setActiveTab('bulk-import')}
                        className={`flex items-center px-6 py-4 text-sm font-medium border-b-2 transition-colors ${activeTab === 'bulk-import'
                            ? 'border-blue-500 text-blue-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                            }`}
                    >
                        <UploadCloud className="h-4 w-4 mr-2" />
                        Bulk Import
                    </button>
                </div>

                {/* Content */}
                <div className="p-6">
                    {activeTab === 'branding' && <BrandingTab />}
                    {activeTab === 'staff' && <StaffTab />}
                    {activeTab === 'manual' && <ManualUserTab />}
                    {activeTab === 'bulk-import' && <BulkImportTab />}
                </div>
            </div>
        </div>
    );
}

function BrandingTab() {
    const queryClient = useQueryClient();
    const { data: siteSettings } = useSiteSettings();
    const [companyName, setCompanyName] = useState('');
    const [logoFile, setLogoFile] = useState<File | null>(null);
    const [logoPreview, setLogoPreview] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (siteSettings) setCompanyName(siteSettings.company_name);
    }, [siteSettings]);

    const updateMutation = useMutation({
        mutationFn: () => siteSettingsAPI.update({
            company_name: companyName,
            ...(logoFile ? { logo: logoFile } : {}),
        }),
        onSuccess: () => {
            toast.success('Branding updated');
            queryClient.invalidateQueries({ queryKey: ['site-settings'] });
            setLogoFile(null);
            setLogoPreview(null);
        },
        onError: () => toast.error('Failed to update branding')
    });

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        setLogoFile(file);
        setLogoPreview(URL.createObjectURL(file));
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        updateMutation.mutate();
    };

    const displayedLogo = logoPreview || siteSettings?.logo;

    return (
        <div className="max-w-xl">
            <h3 className="text-lg font-bold mb-1">Company Branding</h3>
            <p className="text-sm text-gray-500 mb-4">
                Shown in the admin sidebar header and used as the browser tab icon (favicon).
            </p>
            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Company Name</label>
                    <input
                        type="text" required
                        className="w-full border rounded-lg px-3 py-2"
                        value={companyName}
                        onChange={e => setCompanyName(e.target.value)}
                    />
                    <p className="text-xs text-gray-500 mt-1">Shown next to the logo in the sidebar header.</p>
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Logo</label>
                    <div className="flex items-center gap-4">
                        <div className="h-16 w-16 rounded-lg border bg-gray-50 flex items-center justify-center overflow-hidden">
                            {displayedLogo ? (
                                <img src={displayedLogo} alt="Logo preview" className="h-full w-full object-contain" />
                            ) : (
                                <ImageIcon className="h-6 w-6 text-gray-300" />
                            )}
                        </div>
                        <div>
                            <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleFileChange} />
                            <button
                                type="button"
                                onClick={() => fileInputRef.current?.click()}
                                className="px-3 py-2 border rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50"
                            >
                                Choose file
                            </button>
                            <p className="text-xs text-gray-500 mt-1">PNG or SVG recommended, square works best.</p>
                        </div>
                    </div>
                </div>
                <button
                    type="submit"
                    disabled={updateMutation.isPending}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                >
                    {updateMutation.isPending ? 'Saving...' : 'Save Branding'}
                </button>
            </form>
        </div>
    );
}

function StaffTab() {
    const queryClient = useQueryClient();
    const [isFormOpen, setIsFormOpen] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [form, setForm] = useState({
        username: '', email: '', first_name: '', last_name: '', phone_number: '', password: '', role: 'sales',
    });

    const { data: staff, isLoading } = useQuery({
        queryKey: ['staff'],
        queryFn: async () => {
            const res = await adminAPI.getStaff();
            return res.data.results || res.data;
        }
    });

    const resetForm = () => {
        setForm({ username: '', email: '', first_name: '', last_name: '', phone_number: '', password: '', role: 'sales' });
        setEditingId(null);
        setIsFormOpen(false);
    };

    const createMutation = useMutation({
        mutationFn: (data: any) => adminAPI.createStaff(data),
        onSuccess: () => {
            toast.success('Staff member created');
            queryClient.invalidateQueries({ queryKey: ['staff'] });
            resetForm();
        },
        onError: (err: any) => toast.error(err.response?.data?.username?.[0] || err.response?.data?.detail || 'Failed to create staff member')
    });

    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: number; data: any }) => adminAPI.updateStaff(id, data),
        onSuccess: () => {
            toast.success('Staff member updated');
            queryClient.invalidateQueries({ queryKey: ['staff'] });
            resetForm();
        },
        onError: () => toast.error('Failed to update staff member')
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => adminAPI.deleteStaff(id),
        onSuccess: () => {
            toast.success('Staff member removed');
            queryClient.invalidateQueries({ queryKey: ['staff'] });
        },
        onError: () => toast.error('Failed to remove staff member')
    });

    const openEdit = (user: any) => {
        setForm({
            username: user.username, email: user.email || '', first_name: user.first_name || '',
            last_name: user.last_name || '', phone_number: user.phone_number || '', password: '', role: user.role || 'sales',
        });
        setEditingId(user.id);
        setIsFormOpen(true);
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const payload: any = { ...form };
        if (!payload.password) delete payload.password;
        if (editingId) {
            updateMutation.mutate({ id: editingId, data: payload });
        } else {
            createMutation.mutate(payload);
        }
    };

    return (
        <div>
            <div className="flex justify-between mb-4">
                <h3 className="text-lg font-bold">Staff Directory</h3>
                <button
                    onClick={() => { resetForm(); setIsFormOpen(true); }}
                    className="flex items-center px-3 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
                >
                    <Plus className="h-4 w-4 mr-2" /> Add Staff
                </button>
            </div>

            {isFormOpen && (
                <form onSubmit={handleSubmit} className="bg-gray-50 border rounded-lg p-4 mb-4 space-y-3">
                    <div className="flex items-center justify-between">
                        <h4 className="font-bold text-sm">{editingId ? 'Edit Staff Member' : 'New Staff Member'}</h4>
                        <button type="button" onClick={resetForm} className="text-gray-400 hover:text-gray-600">
                            <X className="h-4 w-4" />
                        </button>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <input required disabled={!!editingId} placeholder="Username" className="border rounded-lg px-3 py-2 text-sm disabled:bg-gray-100"
                            value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} />
                        <input type="email" placeholder="Email" className="border rounded-lg px-3 py-2 text-sm"
                            value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} />
                        <input placeholder="First Name" className="border rounded-lg px-3 py-2 text-sm"
                            value={form.first_name} onChange={e => setForm({ ...form, first_name: e.target.value })} />
                        <input placeholder="Last Name" className="border rounded-lg px-3 py-2 text-sm"
                            value={form.last_name} onChange={e => setForm({ ...form, last_name: e.target.value })} />
                        <input placeholder="Phone Number" className="border rounded-lg px-3 py-2 text-sm"
                            value={form.phone_number} onChange={e => setForm({ ...form, phone_number: e.target.value })} />
                        <select className="border rounded-lg px-3 py-2 text-sm" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}>
                            {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                        </select>
                        <input type="password" placeholder={editingId ? 'New Password (optional)' : 'Password'} required={!editingId}
                            className="border rounded-lg px-3 py-2 text-sm col-span-2"
                            value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} />
                    </div>
                    <button
                        type="submit"
                        disabled={createMutation.isPending || updateMutation.isPending}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
                    >
                        {editingId ? 'Save Changes' : 'Create Staff Member'}
                    </button>
                </form>
            )}

            {isLoading && <p className="text-gray-500 text-center py-4">Loading...</p>}
            <div className="space-y-3">
                {staff?.length === 0 && <p className="text-gray-500 text-center py-4">No staff members yet.</p>}
                {staff?.map((user: any) => (
                    <div key={user.id} className="flex items-center justify-between p-4 border rounded-lg">
                        <div>
                            <p className="font-bold">{user.username} {user.first_name && `(${user.first_name} ${user.last_name})`}</p>
                            <p className="text-sm text-gray-500">{user.email || 'No email'} &middot; {user.phone_number || 'No phone'}</p>
                        </div>
                        <div className="flex items-center gap-2">
                            {user.is_superuser ? (
                                <span className="flex items-center px-2 py-1 bg-gray-800 text-white rounded text-xs">
                                    <ShieldCheck className="h-3 w-3 mr-1" /> Superuser
                                </span>
                            ) : (
                                <span className={`px-2 py-1 rounded text-xs font-medium capitalize ${ROLE_BADGE[user.role] || 'bg-gray-100 text-gray-800'}`}>
                                    {user.role}
                                </span>
                            )}
                            {!user.is_superuser && (
                                <>
                                    <button onClick={() => openEdit(user)} className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded">
                                        <Pencil className="h-4 w-4" />
                                    </button>
                                    <button
                                        onClick={() => { if (confirm(`Remove staff member ${user.username}?`)) deleteMutation.mutate(user.id); }}
                                        className="p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded"
                                    >
                                        <Trash2 className="h-4 w-4" />
                                    </button>
                                </>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function ManualUserTab() {
    const [formData, setFormData] = useState({
        username: '', first_name: '', last_name: '', phone_number: '', email: '',
        password: '', plan_id: '', service_type: 'pppoe', static_ip_address: '',
    });
    const [issuedCredentials, setIssuedCredentials] = useState<any>(null);

    const { data: plans } = useQuery({
        queryKey: ['plans'],
        queryFn: async () => {
            const res = await billingAPI.getPlans();
            return res.data.results || res.data;
        }
    });

    const createMutation = useMutation({
        mutationFn: adminAPI.manualSubscribe,
        onSuccess: (res) => {
            toast.success(res.data.message || 'Customer activated successfully');
            if (res.data.credentials) {
                setIssuedCredentials(res.data.credentials);
            }
            setFormData({ username: '', first_name: '', last_name: '', phone_number: '', email: '', password: '', plan_id: '', service_type: 'pppoe', static_ip_address: '' });
        },
        onError: (err: any) => {
            toast.error(err.response?.data?.error || 'Failed to create customer');
        }
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setIssuedCredentials(null);
        createMutation.mutate(formData);
    };

    const copyCredentials = () => {
        if (!issuedCredentials) return;
        const text = [
            `Portal login: ${issuedCredentials.portal_username} / ${issuedCredentials.portal_password}`,
            issuedCredentials.pppoe_username && `PPPoE login: ${issuedCredentials.pppoe_username} / ${issuedCredentials.pppoe_password}`,
            issuedCredentials.hotspot_username && `Hotspot login: ${issuedCredentials.hotspot_username} / ${issuedCredentials.hotspot_password}`,
            issuedCredentials.static_ip_address && `Static IP: ${issuedCredentials.static_ip_address}`,
        ].filter(Boolean).join('\n');
        navigator.clipboard.writeText(text);
        toast.success('Credentials copied');
    };

    return (
        <div className="max-w-md">
            <h3 className="text-lg font-bold mb-1">Create PPPoE / Hotspot / Static Customer</h3>
            <p className="text-sm text-gray-500 mb-4">
                Create a customer manually and activate a plan for them (e.g. cash payment). If the username doesn't
                already exist, a new account is created and login credentials are issued below.
            </p>
            <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
                        <input
                            type="text" required
                            className="w-full border rounded-lg px-3 py-2"
                            value={formData.username}
                            onChange={e => setFormData({ ...formData, username: e.target.value })}
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Service Type</label>
                        <select
                            className="w-full border rounded-lg px-3 py-2"
                            value={formData.service_type}
                            onChange={e => setFormData({ ...formData, service_type: e.target.value })}
                        >
                            <option value="pppoe">PPPoE</option>
                            <option value="hotspot">Hotspot</option>
                            <option value="both">Both</option>
                            <option value="static">Static IP</option>
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
                        <input type="text" className="w-full border rounded-lg px-3 py-2"
                            value={formData.first_name} onChange={e => setFormData({ ...formData, first_name: e.target.value })} />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
                        <input type="text" className="w-full border rounded-lg px-3 py-2"
                            value={formData.last_name} onChange={e => setFormData({ ...formData, last_name: e.target.value })} />
                    </div>
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Phone Number</label>
                    <input
                        type="text"
                        className="w-full border rounded-lg px-3 py-2"
                        value={formData.phone_number}
                        onChange={e => setFormData({ ...formData, phone_number: e.target.value })}
                    />
                </div>
                {formData.service_type === 'static' && (
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Static IP Address</label>
                        <input
                            type="text" required placeholder="10.5.70.50"
                            className="w-full border rounded-lg px-3 py-2"
                            value={formData.static_ip_address}
                            onChange={e => setFormData({ ...formData, static_ip_address: e.target.value })}
                        />
                        <p className="text-xs text-gray-500 mt-1">
                            The fixed IP already configured on the customer's device. A bandwidth queue is created for it.
                        </p>
                    </div>
                )}
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Email (Optional)</label>
                    <input
                        type="email"
                        className="w-full border rounded-lg px-3 py-2"
                        value={formData.email}
                        onChange={e => setFormData({ ...formData, email: e.target.value })}
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Password (leave blank to auto-generate)</label>
                    <input
                        type="text"
                        className="w-full border rounded-lg px-3 py-2"
                        value={formData.password}
                        onChange={e => setFormData({ ...formData, password: e.target.value })}
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Plan</label>
                    <select
                        required
                        className="w-full border rounded-lg px-3 py-2"
                        value={formData.plan_id}
                        onChange={e => setFormData({ ...formData, plan_id: e.target.value })}
                    >
                        <option value="">Select a plan...</option>
                        {plans?.map((plan: any) => (
                            <option key={plan.id} value={plan.id}>{plan.name} - KES {plan.price}</option>
                        ))}
                    </select>
                </div>
                <button
                    type="submit"
                    disabled={createMutation.isPending}
                    className="w-full py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                >
                    {createMutation.isPending ? 'Activating...' : 'Create & Activate'}
                </button>
            </form>

            {issuedCredentials && (
                <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <div className="flex justify-between items-center mb-2">
                        <h4 className="font-bold text-sm text-blue-900">Issued Credentials</h4>
                        <button onClick={copyCredentials} className="flex items-center text-xs text-blue-700 hover:text-blue-900">
                            <Copy className="h-3 w-3 mr-1" /> Copy
                        </button>
                    </div>
                    <div className="text-sm space-y-1 font-mono">
                        <p>Portal: {issuedCredentials.portal_username} / {issuedCredentials.portal_password}</p>
                        {issuedCredentials.pppoe_username && (
                            <p>PPPoE: {issuedCredentials.pppoe_username} / {issuedCredentials.pppoe_password}</p>
                        )}
                        {issuedCredentials.hotspot_username && (
                            <p>Hotspot: {issuedCredentials.hotspot_username} / {issuedCredentials.hotspot_password}</p>
                        )}
                        {issuedCredentials.static_ip_address && (
                            <p>Static IP: {issuedCredentials.static_ip_address}</p>
                        )}
                    </div>
                    <p className="text-xs text-blue-700 mt-2">This is shown once -- copy it now to hand to the customer.</p>
                </div>
            )}
        </div>
    );
}

function BulkImportTab() {
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [importResult, setImportResult] = useState<any>(null);

    const importMutation = useMutation({
        mutationFn: (file: File) => billingAPI.importPppoeCSV(file),
        onSuccess: (res) => {
            setImportResult(res.data);
            if (res.data.created_count > 0) toast.success(`Imported ${res.data.created_count} PPPoE user(s)`);
            if (res.data.error_count > 0) toast.error(`${res.data.error_count} row(s) failed`);
        },
        onError: (err: any) => toast.error(err.response?.data?.error || 'Import failed'),
    });

    const handleDownloadTemplate = async () => {
        const res = await billingAPI.downloadPppoeTemplate();
        downloadBlob(res.data, 'pppoe_users_template.csv');
    };

    const handleFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) importMutation.mutate(file);
        e.target.value = '';
    };

    return (
        <div className="max-w-2xl">
            <h3 className="text-lg font-bold mb-1">Import PPPoE Users</h3>
            <p className="text-sm text-gray-500 mb-4">
                Bulk-create PPPoE customers from a CSV. Each row's username/password become both their
                portal login and PPPoE login, and they're activated on the router immediately -- same as
                creating one manually, just many at once. Existing usernames are rejected, not modified.
                Leave <code className="text-xs bg-gray-100 px-1 rounded">expiry_date</code> blank for a
                fresh subscription starting today, or set it to preserve a migrated customer's real
                remaining time.
            </p>
            <div className="flex gap-2 mb-6">
                <button
                    onClick={handleDownloadTemplate}
                    className="flex items-center px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition text-sm font-medium"
                >
                    <Download className="h-4 w-4 mr-2" /> Download Template
                </button>
                <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={handleFileSelected} />
                <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={importMutation.isPending}
                    className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition text-sm font-medium disabled:opacity-50"
                >
                    <Upload className="h-4 w-4 mr-2" /> {importMutation.isPending ? 'Importing...' : 'Import CSV'}
                </button>
            </div>

            {importResult && (
                <div className="bg-gray-50 border rounded-lg p-4">
                    <div className="flex justify-between items-start mb-2">
                        <h4 className="text-sm font-bold text-gray-900">
                            {importResult.created_count} created, {importResult.error_count} failed
                        </h4>
                        <button onClick={() => setImportResult(null)} className="text-gray-400 hover:text-gray-600">
                            <X className="h-4 w-4" />
                        </button>
                    </div>
                    {importResult.created?.length > 0 && (
                        <p className="text-sm text-green-700 mb-2">
                            Created: {importResult.created.map((c: any) => c.username).join(', ')}
                        </p>
                    )}
                    {importResult.errors?.length > 0 && (
                        <ul className="text-sm text-red-600 space-y-1">
                            {importResult.errors.map((e: any, idx: number) => (
                                <li key={idx}>Row {e.row} ({e.username}): {e.error}</li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </div>
    );
}
