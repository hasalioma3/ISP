import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { X, Save, KeyRound } from 'lucide-react';
import toast from 'react-hot-toast';
import { authAPI } from '../services/api';
import { useAuthStore } from '../store/authStore';

export default function AccountModal({ initialTab = 'profile', onClose }: { initialTab?: 'profile' | 'password'; onClose: () => void }) {
    const [tab, setTab] = useState<'profile' | 'password'>(initialTab);
    const { user, updateUser } = useAuthStore();

    const [profileForm, setProfileForm] = useState({
        first_name: user?.first_name || '',
        last_name: user?.last_name || '',
        email: user?.email || '',
        phone_number: user?.phone_number || '',
    });

    const [passwordForm, setPasswordForm] = useState({ old_password: '', new_password: '', confirm_password: '' });

    const profileMutation = useMutation({
        mutationFn: () => authAPI.updateProfile(profileForm),
        onSuccess: (res) => {
            updateUser(res.data);
            toast.success('Profile updated');
        },
        onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to update profile'),
    });

    const passwordMutation = useMutation({
        mutationFn: () => authAPI.changePassword({ old_password: passwordForm.old_password, new_password: passwordForm.new_password }),
        onSuccess: () => {
            toast.success('Password changed');
            setPasswordForm({ old_password: '', new_password: '', confirm_password: '' });
        },
        onError: (err: any) => toast.error(err.response?.data?.error || 'Failed to change password'),
    });

    const handleProfileSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        profileMutation.mutate();
    };

    const handlePasswordSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (passwordForm.new_password !== passwordForm.confirm_password) {
            toast.error("New passwords don't match");
            return;
        }
        passwordMutation.mutate();
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
                <div className="flex justify-between items-center p-6 border-b">
                    <h3 className="text-lg font-bold text-gray-900">My Account</h3>
                    <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600">
                        <X className="h-5 w-5" />
                    </button>
                </div>

                <div className="flex border-b px-6">
                    {(['profile', 'password'] as const).map(t => (
                        <button
                            key={t}
                            onClick={() => setTab(t)}
                            className={`px-4 py-3 text-sm font-medium border-b-2 capitalize transition-colors ${tab === t
                                ? 'border-blue-500 text-blue-600'
                                : 'border-transparent text-gray-500 hover:text-gray-700'
                                }`}
                        >
                            {t === 'password' ? 'Change Password' : 'Edit Profile'}
                        </button>
                    ))}
                </div>

                <div className="p-6">
                    {tab === 'profile' ? (
                        <form onSubmit={handleProfileSubmit} className="space-y-4">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
                                    <input
                                        type="text" className="w-full border rounded-lg px-3 py-2"
                                        value={profileForm.first_name}
                                        onChange={e => setProfileForm({ ...profileForm, first_name: e.target.value })}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
                                    <input
                                        type="text" className="w-full border rounded-lg px-3 py-2"
                                        value={profileForm.last_name}
                                        onChange={e => setProfileForm({ ...profileForm, last_name: e.target.value })}
                                    />
                                </div>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                                <input
                                    type="email" className="w-full border rounded-lg px-3 py-2"
                                    value={profileForm.email}
                                    onChange={e => setProfileForm({ ...profileForm, email: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Phone Number</label>
                                <input
                                    type="text" className="w-full border rounded-lg px-3 py-2"
                                    value={profileForm.phone_number}
                                    onChange={e => setProfileForm({ ...profileForm, phone_number: e.target.value })}
                                />
                            </div>
                            <button
                                type="submit"
                                disabled={profileMutation.isPending}
                                className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                            >
                                <Save className="h-4 w-4 mr-2" />
                                {profileMutation.isPending ? 'Saving...' : 'Save Changes'}
                            </button>
                        </form>
                    ) : (
                        <form onSubmit={handlePasswordSubmit} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Current Password</label>
                                <input
                                    type="password" required className="w-full border rounded-lg px-3 py-2"
                                    value={passwordForm.old_password}
                                    onChange={e => setPasswordForm({ ...passwordForm, old_password: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">New Password</label>
                                <input
                                    type="password" required className="w-full border rounded-lg px-3 py-2"
                                    value={passwordForm.new_password}
                                    onChange={e => setPasswordForm({ ...passwordForm, new_password: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Confirm New Password</label>
                                <input
                                    type="password" required className="w-full border rounded-lg px-3 py-2"
                                    value={passwordForm.confirm_password}
                                    onChange={e => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })}
                                />
                            </div>
                            <button
                                type="submit"
                                disabled={passwordMutation.isPending}
                                className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                            >
                                <KeyRound className="h-4 w-4 mr-2" />
                                {passwordMutation.isPending ? 'Changing...' : 'Change Password'}
                            </button>
                        </form>
                    )}
                </div>
            </div>
        </div>
    );
}
