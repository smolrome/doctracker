import { useState, useEffect } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, Alert,
  TextInput, ActivityIndicator, StatusBar, Switch,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useMutation } from '@tanstack/react-query';
import { useAuthStore } from '../../lib/store';
import { cache } from '../../lib/cache';
import api from '../../lib/api';
import { authStorage } from '../../lib/auth';
import * as Biometrics from '../../lib/biometrics';
import { User, Lock, ChevronRight, Eye, EyeOff, Fingerprint } from 'lucide-react-native';
import PasswordPrompt from '../../components/ui/PasswordPrompt';

// ── Types ──────────────────────────────────────────────────────────────────────

type Section = 'info' | 'password' | null;

// ── Helpers ────────────────────────────────────────────────────────────────────

function getRoleBadgeColor(role: string) {
  switch (role) {
    case 'admin':      return '#CE1126';
    case 'superadmin': return '#7C2D12';
    case 'staff':      return '#0038A8';
    default:           return '#6B7280';
  }
}

function SectionCard({ children, style }: { children: React.ReactNode; style?: object }) {
  return (
    <View style={{
      backgroundColor: '#fff', borderRadius: 14, padding: 20,
      marginBottom: 12, borderWidth: 0.5, borderColor: '#E2E8F0',
      ...style,
    }}>
      {children}
    </View>
  );
}

function FieldLabel({ children, required }: { children: string; required?: boolean }) {
  return (
    <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.7, marginBottom: 6 }}>
      {children}{required && <Text style={{ color: '#EF4444' }}> *</Text>}
    </Text>
  );
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function Profile() {
  const router = useRouter();
  const { user, setUser, logout } = useAuthStore();
  const [lastSync, setLastSync] = useState<string | null>(null);

  // Personal info form
  const [fullName, setFullName] = useState(user?.full_name || '');
  const [office, setOffice]     = useState(user?.office || '');

  // Password form
  const [currentPw, setCurrentPw]   = useState('');
  const [newPw, setNewPw]           = useState('');
  const [confirmPw, setConfirmPw]   = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew]         = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  // Expanded section
  const [expanded, setExpanded] = useState<Section>(null);

  // Biometric state
  const [bioAvailable, setBioAvailable]       = useState(false);
  const [bioEnabled, setBioEnabled]           = useState(false);
  const [bioLoading, setBioLoading]           = useState(false);
  const [bioPromptVisible, setBioPromptVisible] = useState(false);

  useEffect(() => {
    cache.getLastSync().then(setLastSync);
    initBiometrics();
  }, []);

  const initBiometrics = async () => {
    try {
      const hasHardware = await Biometrics.hasHardwareAsync();
      const isEnrolled  = await Biometrics.isEnrolledAsync();
      const enabled     = await authStorage.isBiometricEnabled();
      setBioAvailable(hasHardware && isEnrolled);
      setBioEnabled(hasHardware && isEnrolled && enabled);
    } catch {}
  };

  const handleToggleBiometric = async (value: boolean) => {
    if (value) {
      // First verify their biometric identity
      const result = await Biometrics.authenticateAsync({
        promptMessage: 'Confirm your identity to enable fingerprint login',
        cancelLabel: 'Cancel',
      });
      if (!result.success) return;
      // Then ask for their password via the cross-platform modal
      setBioPromptVisible(true);
    } else {
      Alert.alert(
        'Disable Fingerprint Login',
        'Remove fingerprint sign-in from this device?',
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Remove', style: 'destructive',
            onPress: async () => {
              await authStorage.clearBiometricCredentials();
              setBioEnabled(false);
            },
          },
        ],
      );
    }
  };

  const handleBioPasswordConfirm = async (pw: string) => {
    setBioPromptVisible(false);
    if (!pw) return;
    await authStorage.saveBiometricCredentials(user?.username || '', pw);
    setBioEnabled(true);
    Alert.alert('✅ Fingerprint Login Enabled', 'You can now sign in with your fingerprint.');
  };

  // Sync form when user changes
  useEffect(() => {
    setFullName(user?.full_name || '');
    setOffice(user?.office || '');
  }, [user]);

  // ── Mutations ──────────────────────────────────────────────────────────────

  const updateInfoMutation = useMutation({
    mutationFn: () => api.patch('/profile', { full_name: fullName.trim(), office: office.trim() }),
    onSuccess: (res) => {
      const updated = res.data;
      setUser({ ...user!, full_name: updated.full_name, office: updated.office });
      Alert.alert('Saved', 'Profile updated successfully.');
      setExpanded(null);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to update profile.'),
  });

  const changePasswordMutation = useMutation({
    mutationFn: () => api.post('/profile/password', {
      current_password: currentPw.trim(),
      new_password:     newPw.trim(),
      confirm_password: confirmPw.trim(),
    }),
    onSuccess: () => {
      setCurrentPw(''); setNewPw(''); setConfirmPw('');
      Alert.alert('Done', 'Password changed successfully.');
      setExpanded(null);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to change password.'),
  });

  const handleSaveInfo = () => {
    if (!fullName.trim()) {
      Alert.alert('Required', 'Display name cannot be empty.');
      return;
    }
    updateInfoMutation.mutate();
  };

  const handleChangePassword = () => {
    if (!currentPw || !newPw || !confirmPw) {
      Alert.alert('Required', 'All password fields are required.');
      return;
    }
    if (newPw !== confirmPw) {
      Alert.alert('Mismatch', 'New passwords do not match.');
      return;
    }
    if (newPw.length < 8) {
      Alert.alert('Too Short', 'New password must be at least 8 characters.');
      return;
    }
    changePasswordMutation.mutate();
  };

  const handleClearCache = async () => {
    Alert.alert('Clear Cache', 'This will remove all offline data. You need internet to reload.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Clear', style: 'destructive',
        onPress: async () => {
          await cache.clearAll();
          setLastSync(null);
          Alert.alert('Done', 'Cache cleared successfully');
        },
      },
    ]);
  };

  const handleLogout = () => {
    Alert.alert('Logout', 'Are you sure you want to logout?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Logout', style: 'destructive',
        onPress: async () => { await logout(); router.replace('/(auth)/login'); },
      },
    ]);
  };

  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin';

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <View style={{ flex: 1, backgroundColor: '#F3F4F6' }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <View style={{
        backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 30,
        paddingHorizontal: 20, alignItems: 'center',
      }}>
        <View style={{
          width: 72, height: 72, borderRadius: 36,
          backgroundColor: 'rgba(255,255,255,0.2)',
          alignItems: 'center', justifyContent: 'center', marginBottom: 12,
          borderWidth: 2, borderColor: 'rgba(255,255,255,0.35)',
        }}>
          <Text style={{ fontSize: 28, color: '#fff', fontWeight: '800' }}>
            {(user?.full_name || user?.username || 'U').charAt(0).toUpperCase()}
          </Text>
        </View>

        <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800' }}>
          {user?.full_name || user?.username}
        </Text>
        <Text style={{ color: '#93C5FD', fontSize: 13, marginTop: 3 }}>
          @{user?.username} · {user?.office || '—'}
        </Text>
        <View style={{
          marginTop: 10, borderRadius: 20, paddingHorizontal: 14, paddingVertical: 4,
          backgroundColor: getRoleBadgeColor(user?.role || ''),
        }}>
          <Text style={{ color: '#fff', fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 }}>
            {user?.role || 'user'}
          </Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 110 }}>

        {/* ── Personal Information ───────────────────────────────────────── */}
        <SectionCard>
          <TouchableOpacity
            onPress={() => setExpanded(expanded === 'info' ? null : 'info')}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}
            activeOpacity={0.7}
          >
            <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: '#EFF6FF', alignItems: 'center', justifyContent: 'center' }}>
              <User size={18} color="#0038A8" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '700', color: '#0038A8', fontSize: 15 }}>Personal Information</Text>
              <Text style={{ color: '#94A3B8', fontSize: 12, marginTop: 2 }}>Update your name and office</Text>
            </View>
            <ChevronRight
              size={18} color="#CBD5E1"
              style={{ transform: [{ rotate: expanded === 'info' ? '90deg' : '0deg' }] }}
            />
          </TouchableOpacity>

          {expanded === 'info' && (
            <View style={{ marginTop: 20 }}>
              {/* Read-only fields */}
              {[['Username', user?.username || '—'], ['Role', user?.role || '—']].map(([label, value]) => (
                <View key={label} style={{ marginBottom: 14 }}>
                  <FieldLabel>{label}</FieldLabel>
                  <View style={{ backgroundColor: '#F1F5F9', borderRadius: 10, paddingHorizontal: 13, paddingVertical: 12, borderWidth: 1.5, borderColor: '#E2E8F0' }}>
                    <Text style={{ color: '#64748B', fontSize: 14 }}>{value}</Text>
                  </View>
                </View>
              ))}

              {/* Editable: full name */}
              <FieldLabel required>Display Name</FieldLabel>
              <TextInput
                value={fullName}
                onChangeText={setFullName}
                placeholder="Your full name & designation"
                placeholderTextColor="#CBD5E1"
                style={inputStyle}
              />

              {/* Editable: office */}
              <FieldLabel>Office / Unit</FieldLabel>
              <TextInput
                value={office}
                onChangeText={setOffice}
                placeholder="e.g. Personnel Unit"
                placeholderTextColor="#CBD5E1"
                style={inputStyle}
              />

              <TouchableOpacity
                onPress={handleSaveInfo}
                disabled={updateInfoMutation.isPending}
                activeOpacity={0.85}
                style={{
                  backgroundColor: updateInfoMutation.isPending ? '#93C5FD' : '#0038A8',
                  borderRadius: 11, paddingVertical: 13,
                  alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 7, marginTop: 4,
                }}
              >
                {updateInfoMutation.isPending
                  ? <><ActivityIndicator color="#fff" size="small" /><Text style={{ color: '#fff', fontWeight: '700' }}>Saving…</Text></>
                  : <Text style={{ color: '#fff', fontSize: 14, fontWeight: '700' }}>Save Changes</Text>
                }
              </TouchableOpacity>
            </View>
          )}
        </SectionCard>

        {/* ── Change Password ────────────────────────────────────────────── */}
        <SectionCard>
          <TouchableOpacity
            onPress={() => setExpanded(expanded === 'password' ? null : 'password')}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}
            activeOpacity={0.7}
          >
            <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: '#FEF3C7', alignItems: 'center', justifyContent: 'center' }}>
              <Lock size={18} color="#D97706" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '700', color: '#92400E', fontSize: 15 }}>Change Password</Text>
              <Text style={{ color: '#94A3B8', fontSize: 12, marginTop: 2 }}>Update your account password</Text>
            </View>
            <ChevronRight
              size={18} color="#CBD5E1"
              style={{ transform: [{ rotate: expanded === 'password' ? '90deg' : '0deg' }] }}
            />
          </TouchableOpacity>

          {expanded === 'password' && (
            <View style={{ marginTop: 20 }}>
              {/* Current password */}
              <FieldLabel required>Current Password</FieldLabel>
              <View style={pwFieldWrap}>
                <TextInput
                  value={currentPw}
                  onChangeText={setCurrentPw}
                  placeholder="Enter current password"
                  placeholderTextColor="#CBD5E1"
                  secureTextEntry={!showCurrent}
                  style={[inputStyle, { marginBottom: 0, flex: 1, borderWidth: 0 }]}
                />
                <TouchableOpacity onPress={() => setShowCurrent(!showCurrent)} style={{ paddingRight: 4 }}>
                  {showCurrent ? <EyeOff size={18} color="#94A3B8" /> : <Eye size={18} color="#94A3B8" />}
                </TouchableOpacity>
              </View>

              <View style={{ height: 1, backgroundColor: '#F1F5F9', marginVertical: 14 }} />

              {/* New password */}
              <FieldLabel required>New Password</FieldLabel>
              <View style={pwFieldWrap}>
                <TextInput
                  value={newPw}
                  onChangeText={setNewPw}
                  placeholder="At least 8 characters"
                  placeholderTextColor="#CBD5E1"
                  secureTextEntry={!showNew}
                  style={[inputStyle, { marginBottom: 0, flex: 1, borderWidth: 0 }]}
                />
                <TouchableOpacity onPress={() => setShowNew(!showNew)} style={{ paddingRight: 4 }}>
                  {showNew ? <EyeOff size={18} color="#94A3B8" /> : <Eye size={18} color="#94A3B8" />}
                </TouchableOpacity>
              </View>

              {/* Confirm new password */}
              <FieldLabel required>Confirm New Password</FieldLabel>
              <View style={[pwFieldWrap, { borderColor: confirmPw && confirmPw !== newPw ? '#FECACA' : '#E2E8F0' }]}>
                <TextInput
                  value={confirmPw}
                  onChangeText={setConfirmPw}
                  placeholder="Repeat new password"
                  placeholderTextColor="#CBD5E1"
                  secureTextEntry={!showConfirm}
                  style={[inputStyle, { marginBottom: 0, flex: 1, borderWidth: 0 }]}
                />
                <TouchableOpacity onPress={() => setShowConfirm(!showConfirm)} style={{ paddingRight: 4 }}>
                  {showConfirm ? <EyeOff size={18} color="#94A3B8" /> : <Eye size={18} color="#94A3B8" />}
                </TouchableOpacity>
              </View>
              {confirmPw.length > 0 && confirmPw !== newPw && (
                <Text style={{ color: '#EF4444', fontSize: 12, marginTop: -10, marginBottom: 14 }}>
                  Passwords do not match
                </Text>
              )}

              <TouchableOpacity
                onPress={handleChangePassword}
                disabled={changePasswordMutation.isPending}
                activeOpacity={0.85}
                style={{
                  backgroundColor: changePasswordMutation.isPending ? '#FCD34D' : '#D97706',
                  borderRadius: 11, paddingVertical: 13,
                  alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 7, marginTop: 4,
                }}
              >
                {changePasswordMutation.isPending
                  ? <><ActivityIndicator color="#fff" size="small" /><Text style={{ color: '#fff', fontWeight: '700' }}>Updating…</Text></>
                  : <Text style={{ color: '#fff', fontSize: 14, fontWeight: '700' }}>Change Password</Text>
                }
              </TouchableOpacity>
            </View>
          )}
        </SectionCard>

        {/* ── Quick Actions ──────────────────────────────────────────────── */}
        <SectionCard>
          <Text style={sectionTitle}>Quick Actions</Text>

          {[
            { icon: '📄', label: 'All Documents',    sub: 'Browse and search documents',      route: '/(app)/documents' },
            { icon: '📷', label: 'Scan QR Code',     sub: 'Quick document lookup',             route: '/(app)/scanner' },
            { icon: '📋', label: 'Routing Slips',    sub: 'View document routing history',     route: '/(app)/routing-slips' },
            { icon: '🕐', label: 'Activity Log',     sub: 'Full system event history',         route: '/(app)/activity-log' },
            { icon: '📥', label: 'Receive Documents', sub: 'Documents pending your acceptance', route: '/(app)/receive-docs' },
          ].map(({ icon, label, sub, route }) => (
            <TouchableOpacity
              key={label}
              onPress={() => router.push(route as any)}
              style={actionRow}
            >
              <Text style={{ fontSize: 20 }}>{icon}</Text>
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={{ fontWeight: '600', color: '#111', fontSize: 14 }}>{label}</Text>
                <Text style={{ color: '#6B7280', fontSize: 12 }}>{sub}</Text>
              </View>
              <ChevronRight size={16} color="#CBD5E1" />
            </TouchableOpacity>
          ))}

          {isAdmin && (
            <>
              <TouchableOpacity onPress={() => router.push('/(app)/staff-stats')} style={actionRow}>
                <Text style={{ fontSize: 20 }}>👥</Text>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={{ fontWeight: '600', color: '#111', fontSize: 14 }}>Staff Statistics</Text>
                  <Text style={{ color: '#6B7280', fontSize: 12 }}>Per-staff document breakdown</Text>
                </View>
                <ChevronRight size={16} color="#CBD5E1" />
              </TouchableOpacity>

              <TouchableOpacity onPress={() => router.push('/(app)/trash')} style={actionRow}>
                <Text style={{ fontSize: 20 }}>🗑️</Text>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={{ fontWeight: '600', color: '#991B1B', fontSize: 14 }}>Trash</Text>
                  <Text style={{ color: '#6B7280', fontSize: 12 }}>View, restore, or permanently delete</Text>
                </View>
                <ChevronRight size={16} color="#CBD5E1" />
              </TouchableOpacity>

              <TouchableOpacity onPress={() => router.push('/(app)/pending-clients' as any)} style={actionRow}>
                <Text style={{ fontSize: 20 }}>⏳</Text>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={{ fontWeight: '600', color: '#0038A8', fontSize: 14 }}>Pending Clients</Text>
                  <Text style={{ color: '#6B7280', fontSize: 12 }}>Approve or reject client registrations</Text>
                </View>
                <ChevronRight size={16} color="#CBD5E1" />
              </TouchableOpacity>

              <TouchableOpacity onPress={() => router.push('/(app)/office-docs' as any)} style={actionRow}>
                <Text style={{ fontSize: 20 }}>🏢</Text>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={{ fontWeight: '600', color: '#111', fontSize: 14 }}>Office Documents</Text>
                  <Text style={{ color: '#6B7280', fontSize: 12 }}>Browse documents grouped by office</Text>
                </View>
                <ChevronRight size={16} color="#CBD5E1" />
              </TouchableOpacity>

              <TouchableOpacity onPress={() => router.push('/(app)/dropdown-options' as any)} style={actionRow}>
                <Text style={{ fontSize: 20 }}>⚙️</Text>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={{ fontWeight: '600', color: '#111', fontSize: 14 }}>Dropdown Options</Text>
                  <Text style={{ color: '#6B7280', fontSize: 12 }}>Manage custom field values</Text>
                </View>
                <ChevronRight size={16} color="#CBD5E1" />
              </TouchableOpacity>

              <TouchableOpacity onPress={() => router.push('/(app)/db-status' as any)} style={actionRow}>
                <Text style={{ fontSize: 20 }}>🖥️</Text>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={{ fontWeight: '600', color: '#111', fontSize: 14 }}>System Status</Text>
                  <Text style={{ color: '#6B7280', fontSize: 12 }}>Server & database health check</Text>
                </View>
                <ChevronRight size={16} color="#CBD5E1" />
              </TouchableOpacity>

              <TouchableOpacity onPress={() => router.push('/(app)/admin-users')} style={[actionRow, { borderBottomWidth: 0 }]}>
                <Text style={{ fontSize: 20 }}>🛡️</Text>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={{ fontWeight: '600', color: '#111', fontSize: 14 }}>Manage Users</Text>
                  <Text style={{ color: '#6B7280', fontSize: 12 }}>Create, edit, and manage accounts</Text>
                </View>
                <ChevronRight size={16} color="#CBD5E1" />
              </TouchableOpacity>
            </>
          )}

          {!isAdmin && (
            <TouchableOpacity onPress={() => router.push('/(app)/dashboard')} style={[actionRow, { borderBottomWidth: 0 }]}>
              <Text style={{ fontSize: 20 }}>📊</Text>
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={{ fontWeight: '600', color: '#111', fontSize: 14 }}>Dashboard</Text>
                <Text style={{ color: '#6B7280', fontSize: 12 }}>View stats overview</Text>
              </View>
              <ChevronRight size={16} color="#CBD5E1" />
            </TouchableOpacity>
          )}
        </SectionCard>

        {/* ── App Info ───────────────────────────────────────────────────── */}
        <SectionCard>
          <Text style={sectionTitle}>App Info</Text>
          {[
            ['App',      'DepEd Document Tracker'],
            ['Division', 'DepEd Leyte Division'],
            ['Unit',     'Personnel Unit'],
            ['Version',  '1.0.0'],
          ].map(([label, value]) => (
            <View key={label} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: '#F3F4F6' }}>
              <Text style={{ color: '#6B7280', fontSize: 13 }}>{label}</Text>
              <Text style={{ color: '#111', fontSize: 13 }}>{value}</Text>
            </View>
          ))}
        </SectionCard>

        {/* ── Fingerprint / Biometric Login ─────────────────────────────── */}
        {bioAvailable && (
          <SectionCard>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              <View style={{
                width: 36, height: 36, borderRadius: 18,
                backgroundColor: bioEnabled ? '#EFF6FF' : '#F1F5F9',
                alignItems: 'center', justifyContent: 'center',
              }}>
                <Fingerprint size={18} color={bioEnabled ? '#0038A8' : '#94A3B8'} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontWeight: '700', color: '#1E293B', fontSize: 15 }}>
                  Fingerprint Login
                </Text>
                <Text style={{ color: '#94A3B8', fontSize: 12, marginTop: 2 }}>
                  {bioEnabled ? 'Enabled — sign in with your fingerprint' : 'Sign in faster with your fingerprint'}
                </Text>
              </View>
              <Switch
                value={bioEnabled}
                onValueChange={handleToggleBiometric}
                trackColor={{ false: '#E2E8F0', true: '#BFDBFE' }}
                thumbColor={bioEnabled ? '#0038A8' : '#94A3B8'}
              />
            </View>
          </SectionCard>
        )}

        {/* ── Offline Cache ──────────────────────────────────────────────── */}
        <SectionCard>
          <Text style={sectionTitle}>Offline Cache</Text>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#F3F4F6' }}>
            <Text style={{ color: '#6B7280', fontSize: 13 }}>Last Synced</Text>
            <Text style={{ color: '#111', fontSize: 13 }}>
              {lastSync ? new Date(lastSync).toLocaleString() : 'Never'}
            </Text>
          </View>
          <TouchableOpacity
            onPress={handleClearCache}
            style={{ marginTop: 12, backgroundColor: '#FEE2E2', borderRadius: 8, padding: 10, alignItems: 'center' }}
          >
            <Text style={{ color: '#DC2626', fontWeight: '600', fontSize: 13 }}>Clear Offline Cache</Text>
          </TouchableOpacity>
        </SectionCard>

        {/* ── Logout ────────────────────────────────────────────────────── */}
        <TouchableOpacity
          onPress={handleLogout}
          style={{ backgroundColor: '#FEE2E2', borderRadius: 12, padding: 16, alignItems: 'center', marginBottom: 32 }}
        >
          <Text style={{ color: '#DC2626', fontWeight: '700', fontSize: 15 }}>Logout</Text>
        </TouchableOpacity>

      </ScrollView>

      {/* Cross-platform password prompt for biometric setup */}
      <PasswordPrompt
        visible={bioPromptVisible}
        title="Enter Your Password"
        message="Your password is stored securely on this device so fingerprint can sign you in automatically next time."
        onConfirm={handleBioPasswordConfirm}
        onCancel={() => setBioPromptVisible(false)}
      />
    </View>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const inputStyle: any = {
  backgroundColor: '#fff', borderRadius: 10,
  paddingHorizontal: 13, paddingVertical: 12, marginBottom: 14,
  borderWidth: 1.5, borderColor: '#E2E8F0', fontSize: 14, color: '#1E293B',
};

const pwFieldWrap: any = {
  flexDirection: 'row', alignItems: 'center',
  backgroundColor: '#fff', borderRadius: 10,
  borderWidth: 1.5, borderColor: '#E2E8F0',
  paddingHorizontal: 13, marginBottom: 14,
};

const sectionTitle: any = {
  fontWeight: '700', color: '#0038A8', fontSize: 15, marginBottom: 14,
};

const actionRow: any = {
  flexDirection: 'row', alignItems: 'center',
  paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#F3F4F6',
};
