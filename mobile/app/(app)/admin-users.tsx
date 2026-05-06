import { useState, useMemo } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView, Alert,
  Modal, FlatList, Platform, KeyboardAvoidingView, ActivityIndicator,
  StatusBar, Clipboard,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../lib/store';
import api from '../../lib/api';
import { SelectField } from '../../components/ui/SelectField';
import {
  ArrowLeft, Plus, Pencil, Trash2, X, Search,
  UserCheck, UserX, KeyRound, Users, Mail, Send,
  UserPlus, RefreshCw,
} from 'lucide-react-native';

// ── Types ──────────────────────────────────────────────────────────────────────

type User = {
  username: string;
  full_name: string;
  role: string;
  office: string;
  active: boolean;
  approved: boolean;
  email?: string;
  created_at?: string;
  last_login?: string;
  documents_handled?: string[];
};

// ── Constants ──────────────────────────────────────────────────────────────────

const ROLES = ['staff', 'admin', 'client'];
const ROLE_COLORS: Record<string, string> = {
  admin: '#CE1126',
  staff: '#0038A8',
  client: '#6B7280',
};

const EMPTY_CREATE = { username: '', full_name: '', password: '', role: 'staff', office: '', email: '' };
const EMPTY_EDIT   = { newUsername: '', full_name: '', email: '', role: 'staff', office: '', documentsHandled: '', newPassword: '' };

// ── Helpers ────────────────────────────────────────────────────────────────────

function RoleBadge({ role }: { role: string }) {
  return (
    <View style={{ backgroundColor: ROLE_COLORS[role] ?? '#6B7280', borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2 }}>
      <Text style={{ color: '#fff', fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {role}
      </Text>
    </View>
  );
}

function StatusBadge({ active, approved }: { active: boolean; approved: boolean }) {
  if (!active) return (
    <View style={{ backgroundColor: '#F1F5F9', borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2 }}>
      <Text style={{ color: '#94A3B8', fontSize: 10, fontWeight: '700' }}>INACTIVE</Text>
    </View>
  );
  if (!approved) return (
    <View style={{ backgroundColor: '#FEF9C3', borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2 }}>
      <Text style={{ color: '#92400E', fontSize: 10, fontWeight: '700' }}>PENDING</Text>
    </View>
  );
  return (
    <View style={{ backgroundColor: '#DCFCE7', borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2 }}>
      <Text style={{ color: '#166534', fontSize: 10, fontWeight: '700' }}>ACTIVE</Text>
    </View>
  );
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function AdminUsers() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user: me } = useAuthStore();

  const [search, setSearch]   = useState('');
  const [filter, setFilter]   = useState<'all' | 'active' | 'inactive' | 'pending'>('all');

  // Create modal
  const [createVisible, setCreateVisible] = useState(false);
  const [createForm, setCreateForm]       = useState(EMPTY_CREATE);

  // Edit modal
  const [editVisible, setEditVisible] = useState(false);
  const [editTarget, setEditTarget]   = useState<User | null>(null);
  const [editForm, setEditForm]       = useState(EMPTY_EDIT);

  // ── Data ───────────────────────────────────────────────────────────────────

  const { data: users = [], isLoading } = useQuery<User[]>({
    queryKey: ['admin-users'],
    queryFn: async () => {
      const res = await api.get('/admin/users');
      return res.data ?? [];
    },
    retry: false,
  });

  const filtered = useMemo(() => {
    let list = users;
    if (filter === 'active')   list = list.filter((u) => u.active && u.approved);
    if (filter === 'inactive') list = list.filter((u) => !u.active);
    if (filter === 'pending')  list = list.filter((u) => u.active && !u.approved);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(
        (u) => u.username.toLowerCase().includes(q) ||
               (u.full_name || '').toLowerCase().includes(q) ||
               (u.office || '').toLowerCase().includes(q),
      );
    }
    return list;
  }, [users, filter, search]);

  // ── Mutations ──────────────────────────────────────────────────────────────

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['admin-users'] });

  const createMutation = useMutation({
    mutationFn: (body: typeof EMPTY_CREATE) => api.post('/admin/users', body),
    onSuccess: () => {
      invalidate();
      setCreateVisible(false);
      setCreateForm(EMPTY_CREATE);
      Alert.alert('Created', 'User account created successfully.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to create user.'),
  });

  const updateMutation = useMutation({
    mutationFn: ({ username, body }: { username: string; body: object }) =>
      api.patch(`/admin/users/${username}`, body),
    onSuccess: () => {
      invalidate();
      setEditVisible(false);
      setEditTarget(null);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to update user.'),
  });

  const deleteMutation = useMutation({
    mutationFn: (username: string) => api.delete(`/admin/users/${username}`),
    onSuccess: () => invalidate(),
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to delete user.'),
  });

  const resendMutation = useMutation({
    mutationFn: (username: string) => api.post(`/admin/users/${username}/resend-credentials`),
    onSuccess: (res: any) => {
      const data = res.data;
      if (data.email_sent === false && data.temp_password) {
        Alert.alert(
          'Email Failed',
          `Password was reset but the email could not be sent.\n\nTemp password:\n${data.temp_password}\n\nShare this manually.`,
          [
            { text: 'Copy Password', onPress: () => Clipboard.setString(data.temp_password) },
            { text: 'OK' },
          ],
        );
      } else {
        Alert.alert('Sent', data.message || 'Credentials sent successfully.');
      }
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to resend credentials.'),
  });

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleCreate = () => {
    if (!createForm.username.trim() || !createForm.password.trim()) {
      Alert.alert('Required', 'Username and password are required.');
      return;
    }
    if (createForm.password.length < 8) {
      Alert.alert('Too short', 'Password must be at least 8 characters.');
      return;
    }
    createMutation.mutate(createForm);
  };

  const openEdit = (u: User) => {
    setEditTarget(u);
    setEditForm({
      newUsername:      u.username,
      full_name:        u.full_name || '',
      email:            u.email || '',
      role:             u.role,
      office:           u.office || '',
      documentsHandled: (u.documents_handled || []).join(', '),
      newPassword:      '',
    });
    setEditVisible(true);
  };

  const handleSaveEdit = () => {
    if (!editTarget) return;
    const body: Record<string, any> = {
      full_name:         editForm.full_name,
      role:              editForm.role,
      office:            editForm.office,
      email:             editForm.email,
      new_username:      editForm.newUsername.trim().toLowerCase() || editTarget.username,
      documents_handled: editForm.documentsHandled
        .split(',').map((s) => s.trim()).filter(Boolean),
    };
    if (editForm.newPassword.trim()) {
      if (editForm.newPassword.length < 8) {
        Alert.alert('Too short', 'New password must be at least 8 characters.');
        return;
      }
      body.password = editForm.newPassword.trim();
    }
    updateMutation.mutate({ username: editTarget.username, body });
  };

  const handleToggleActive = (u: User) => {
    const next = !u.active;
    Alert.alert(
      next ? 'Activate User' : 'Deactivate User',
      `${next ? 'Activate' : 'Deactivate'} ${u.full_name || u.username}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: next ? 'Activate' : 'Deactivate',
          onPress: () => updateMutation.mutate({ username: u.username, body: { active: next } }) },
      ],
    );
  };

  const handleApprove = (u: User) => {
    Alert.alert('Approve Account', `Approve ${u.full_name || u.username}?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Approve', onPress: () => updateMutation.mutate({ username: u.username, body: { approved: true } }) },
    ]);
  };

  const handleDelete = (u: User) => {
    if (u.username === me?.username) {
      Alert.alert('Error', 'You cannot delete your own account.');
      return;
    }
    Alert.alert(
      'Delete User',
      `Permanently delete ${u.full_name || u.username}? This cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: () => deleteMutation.mutate(u.username) },
      ],
    );
  };

  const handleResendCredentials = (u: User) => {
    if (!u.email) {
      Alert.alert('No Email', 'This user has no email address on record. Edit the user to add one first.');
      return;
    }
    Alert.alert(
      'Resend Credentials',
      `Reset password and email new credentials to ${u.email}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Resend', onPress: () => resendMutation.mutate(u.username) },
      ],
    );
  };

  // ── Render item ────────────────────────────────────────────────────────────

  const renderUser = ({ item: u }: { item: User }) => (
    <View style={{
      backgroundColor: '#fff', borderRadius: 14, padding: 14, marginBottom: 10,
      borderWidth: 0.5, borderColor: u.active ? '#E2E8F0' : '#F1F5F9', opacity: u.active ? 1 : 0.75,
    }}>
      {/* Top row */}
      <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12, marginBottom: 10 }}>
        <View style={{
          width: 40, height: 40, borderRadius: 20,
          backgroundColor: ROLE_COLORS[u.role] ?? '#6B7280',
          alignItems: 'center', justifyContent: 'center',
        }}>
          <Text style={{ color: '#fff', fontSize: 16, fontWeight: '800' }}>
            {(u.full_name || u.username).charAt(0).toUpperCase()}
          </Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 14.5, fontWeight: '700', color: '#1E293B' }} numberOfLines={1}>
            {u.full_name || u.username}
          </Text>
          <Text style={{ fontSize: 12, color: '#94A3B8', marginTop: 1 }}>@{u.username}</Text>
          {u.email ? (
            <Text style={{ fontSize: 11, color: '#64748B', marginTop: 2 }} numberOfLines={1}>✉ {u.email}</Text>
          ) : null}
          {u.office ? (
            <Text style={{ fontSize: 12, color: '#64748B', marginTop: 2 }} numberOfLines={1}>{u.office}</Text>
          ) : null}
          {u.documents_handled && u.documents_handled.length > 0 ? (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
              {u.documents_handled.map((d) => (
                <View key={d} style={{ backgroundColor: '#EFF6FF', borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 }}>
                  <Text style={{ fontSize: 10, color: '#1D4ED8', fontWeight: '600' }}>{d}</Text>
                </View>
              ))}
            </View>
          ) : null}
        </View>
        <View style={{ gap: 4, alignItems: 'flex-end' }}>
          <RoleBadge role={u.role} />
          <StatusBadge active={u.active} approved={u.approved} />
        </View>
      </View>

      {/* Actions */}
      <View style={{ flexDirection: 'row', gap: 7, flexWrap: 'wrap' }}>
        {/* Edit */}
        <TouchableOpacity onPress={() => openEdit(u)}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: '#EFF6FF', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7 }}>
          <Pencil size={12} color="#0038A8" />
          <Text style={{ color: '#0038A8', fontSize: 12, fontWeight: '700' }}>Edit</Text>
        </TouchableOpacity>

        {/* Approve pending */}
        {u.active && !u.approved && (
          <TouchableOpacity onPress={() => handleApprove(u)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: '#F0FDF4', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7 }}>
            <UserCheck size={12} color="#16A34A" />
            <Text style={{ color: '#16A34A', fontSize: 12, fontWeight: '700' }}>Approve</Text>
          </TouchableOpacity>
        )}

        {/* Toggle active */}
        {u.username !== me?.username && (
          <TouchableOpacity onPress={() => handleToggleActive(u)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 5,
              backgroundColor: u.active ? '#FEF2F2' : '#F0FDF4',
              borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7 }}>
            {u.active
              ? <><UserX size={12} color="#EF4444" /><Text style={{ color: '#EF4444', fontSize: 12, fontWeight: '700' }}>Disable</Text></>
              : <><UserCheck size={12} color="#16A34A" /><Text style={{ color: '#16A34A', fontSize: 12, fontWeight: '700' }}>Enable</Text></>}
          </TouchableOpacity>
        )}

        {/* Resend Credentials */}
        {u.username !== me?.username && (
          <TouchableOpacity onPress={() => handleResendCredentials(u)}
            disabled={resendMutation.isPending}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: '#FFFBEB', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7,
              borderWidth: 1, borderColor: '#FDE68A' }}>
            <RefreshCw size={12} color="#B45309" />
            <Text style={{ color: '#B45309', fontSize: 12, fontWeight: '700' }}>Resend Creds</Text>
          </TouchableOpacity>
        )}

        {/* Delete */}
        {u.username !== me?.username && (
          <TouchableOpacity onPress={() => handleDelete(u)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: '#FEF2F2', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7 }}>
            <Trash2 size={12} color="#EF4444" />
            <Text style={{ color: '#EF4444', fontSize: 12, fontWeight: '700' }}>Delete</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );

  // ── Main render ────────────────────────────────────────────────────────────

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* Header */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
        <TouchableOpacity onPress={() => router.back()}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 14 }}>
          <ArrowLeft size={18} color="#93C5FD" />
          <Text style={{ color: '#93C5FD', fontSize: 14, fontWeight: '600' }}>Back</Text>
        </TouchableOpacity>

        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Users size={22} color="#fff" />
            <View>
              <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800' }}>Manage Users</Text>
              <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 12, marginTop: 2 }}>
                {users.length} account{users.length !== 1 ? 's' : ''}
              </Text>
            </View>
          </View>
          {/* Quick-nav buttons */}
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity onPress={() => router.push('/(app)/send-invite' as any)}
              style={{ backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 10, padding: 8, borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' }}>
              <Mail size={18} color="#fff" />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => router.push('/(app)/bulk-create-users' as any)}
              style={{ backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 10, padding: 8, borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' }}>
              <UserPlus size={18} color="#fff" />
            </TouchableOpacity>
          </View>
        </View>

        {/* Search */}
        <View style={{ flexDirection: 'row', alignItems: 'center',
          backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 12, paddingHorizontal: 12,
          borderWidth: 1, borderColor: 'rgba(255,255,255,0.20)' }}>
          <Search size={15} color="rgba(255,255,255,0.60)" />
          <TextInput
            value={search} onChangeText={setSearch}
            placeholder="Search by name, username, or office…"
            placeholderTextColor="rgba(255,255,255,0.45)"
            style={{ flex: 1, color: '#fff', fontSize: 14, paddingVertical: 10, marginLeft: 8 }}
          />
          {search.length > 0 && (
            <TouchableOpacity onPress={() => setSearch('')}>
              <X size={14} color="rgba(255,255,255,0.60)" />
            </TouchableOpacity>
          )}
        </View>
      </View>

      {/* Filter chips */}
      <View style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 12, gap: 8 }}>
        {(['all', 'active', 'inactive', 'pending'] as const).map((f) => (
          <TouchableOpacity key={f} onPress={() => setFilter(f)}
            style={{ paddingHorizontal: 14, paddingVertical: 6, borderRadius: 20,
              backgroundColor: filter === f ? '#0038A8' : '#fff',
              borderWidth: 1, borderColor: filter === f ? '#0038A8' : '#E2E8F0' }}>
            <Text style={{ fontSize: 12.5, fontWeight: '700', textTransform: 'capitalize',
              color: filter === f ? '#fff' : '#64748B' }}>{f}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* User list */}
      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
        </View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(u) => u.username}
          renderItem={renderUser}
          contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 120 }}
          showsVerticalScrollIndicator={false}
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 60 }}>
              <Users size={40} color="#CBD5E1" />
              <Text style={{ color: '#94A3B8', fontSize: 14, marginTop: 12 }}>
                {search ? 'No users match your search' : 'No users found'}
              </Text>
            </View>
          }
        />
      )}

      {/* FAB — Add user */}
      <TouchableOpacity
        onPress={() => { setCreateForm(EMPTY_CREATE); setCreateVisible(true); }}
        activeOpacity={0.85}
        style={{
          position: 'absolute', bottom: 32, right: 20,
          width: 56, height: 56, borderRadius: 28,
          backgroundColor: '#0038A8', alignItems: 'center', justifyContent: 'center',
          shadowColor: '#0038A8', shadowOffset: { width: 0, height: 6 },
          shadowOpacity: 0.35, shadowRadius: 10, elevation: 10,
          borderWidth: 3, borderColor: '#fff',
        }}>
        <Plus size={24} color="#fff" />
      </TouchableOpacity>

      {/* ══════════════════════════════════════════════════════════════════
          CREATE USER MODAL
      ══════════════════════════════════════════════════════════════════ */}
      <Modal visible={createVisible} animationType="slide" transparent onRequestClose={() => setCreateVisible(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
            <TouchableOpacity style={{ position: 'absolute', inset: 0 } as any} onPress={() => setCreateVisible(false)} activeOpacity={1} />
            <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 28, borderTopRightRadius: 28, maxHeight: '92%', overflow: 'hidden' }}>
              <View style={{ backgroundColor: '#0038A8', paddingTop: 20, paddingBottom: 16, paddingHorizontal: 20 }}>
                <View style={{ position: 'absolute', top: 10, left: 0, right: 0, alignItems: 'center' }}>
                  <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.30)' }} />
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
                  <View>
                    <Text style={{ fontSize: 18, fontWeight: '800', color: '#fff' }}>Add User</Text>
                    <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.60)', marginTop: 2 }}>Create a new account</Text>
                  </View>
                  <TouchableOpacity onPress={() => setCreateVisible(false)}
                    style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' }}>
                    <X size={18} color="#fff" />
                  </TouchableOpacity>
                </View>
              </View>

              <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 8 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
                <Text style={S.label}>Username <Text style={S.req}>*</Text></Text>
                <TextInput value={createForm.username}
                  onChangeText={(v) => setCreateForm((f) => ({ ...f, username: v.toLowerCase().trim() }))}
                  placeholder="e.g. jdelacruz" autoCapitalize="none" style={S.input} placeholderTextColor="#CBD5E1" />

                <Text style={S.labelMuted}>Full Name & Designation</Text>
                <TextInput value={createForm.full_name}
                  onChangeText={(v) => setCreateForm((f) => ({ ...f, full_name: v }))}
                  placeholder="e.g. Juan dela Cruz, Administrative Officer" style={S.input} placeholderTextColor="#CBD5E1" />

                <Text style={S.label}>Password <Text style={S.req}>*</Text></Text>
                <TextInput value={createForm.password}
                  onChangeText={(v) => setCreateForm((f) => ({ ...f, password: v }))}
                  placeholder="At least 8 characters" secureTextEntry style={S.input} placeholderTextColor="#CBD5E1" />

                <Text style={S.labelMuted}>Role</Text>
                <SelectField value={createForm.role} onChange={(v) => setCreateForm((f) => ({ ...f, role: v }))}
                  options={ROLES} placeholder="Select role…" label="Role" />

                <Text style={S.labelMuted}>Office / Unit</Text>
                <TextInput value={createForm.office}
                  onChangeText={(v) => setCreateForm((f) => ({ ...f, office: v }))}
                  placeholder="e.g. Personnel Unit" style={S.input} placeholderTextColor="#CBD5E1" />

                <Text style={S.labelMuted}>Email</Text>
                <TextInput value={createForm.email}
                  onChangeText={(v) => setCreateForm((f) => ({ ...f, email: v }))}
                  placeholder="e.g. jdelacruz@deped.gov.ph"
                  keyboardType="email-address" autoCapitalize="none" style={S.input} placeholderTextColor="#CBD5E1" />
              </ScrollView>

              <View style={S.footer}>
                <TouchableOpacity onPress={handleCreate} disabled={createMutation.isPending} activeOpacity={0.85}
                  style={[S.btnPrimary, createMutation.isPending && { backgroundColor: '#93C5FD' }]}>
                  {createMutation.isPending
                    ? <><ActivityIndicator color="#fff" size="small" /><Text style={S.btnPrimaryText}>Creating…</Text></>
                    : <><Plus size={18} color="#fff" /><Text style={S.btnPrimaryText}>Create User</Text></>}
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setCreateVisible(false)} style={S.btnSecondary}>
                  <Text style={S.btnSecondaryText}>Cancel</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* ══════════════════════════════════════════════════════════════════
          EDIT USER MODAL
      ══════════════════════════════════════════════════════════════════ */}
      <Modal visible={editVisible} animationType="slide" transparent onRequestClose={() => setEditVisible(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
            <TouchableOpacity style={{ position: 'absolute', inset: 0 } as any} onPress={() => setEditVisible(false)} activeOpacity={1} />
            <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 28, borderTopRightRadius: 28, maxHeight: '92%', overflow: 'hidden' }}>
              <View style={{ backgroundColor: '#0038A8', paddingTop: 20, paddingBottom: 16, paddingHorizontal: 20 }}>
                <View style={{ position: 'absolute', top: 10, left: 0, right: 0, alignItems: 'center' }}>
                  <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.30)' }} />
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
                  <View>
                    <Text style={{ fontSize: 18, fontWeight: '800', color: '#fff' }}>Edit User</Text>
                    <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.60)', marginTop: 2 }}>
                      @{editTarget?.username}
                    </Text>
                  </View>
                  <TouchableOpacity onPress={() => setEditVisible(false)}
                    style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' }}>
                    <X size={18} color="#fff" />
                  </TouchableOpacity>
                </View>
              </View>

              <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 8 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
                <Text style={S.label}>Username</Text>
                <TextInput value={editForm.newUsername}
                  onChangeText={(v) => setEditForm((f) => ({ ...f, newUsername: v.toLowerCase() }))}
                  placeholder="Login username" autoCapitalize="none" autoCorrect={false} style={S.input} placeholderTextColor="#CBD5E1" />
                <Text style={S.hint}>Changing the username updates the login name.</Text>

                <Text style={S.labelMuted}>Full Name & Designation</Text>
                <TextInput value={editForm.full_name}
                  onChangeText={(v) => setEditForm((f) => ({ ...f, full_name: v }))}
                  placeholder="e.g. Juan dela Cruz, Principal II" style={S.input} placeholderTextColor="#CBD5E1" />

                <Text style={S.labelMuted}>Email Address</Text>
                <TextInput value={editForm.email}
                  onChangeText={(v) => setEditForm((f) => ({ ...f, email: v }))}
                  placeholder="e.g. juan@deped.gov.ph"
                  keyboardType="email-address" autoCapitalize="none" style={S.input} placeholderTextColor="#CBD5E1" />

                <Text style={S.labelMuted}>Role</Text>
                <SelectField value={editForm.role} onChange={(v) => setEditForm((f) => ({ ...f, role: v }))}
                  options={ROLES} placeholder="Select role…" label="Role" />

                <Text style={S.labelMuted}>Office / Unit</Text>
                <TextInput value={editForm.office}
                  onChangeText={(v) => setEditForm((f) => ({ ...f, office: v }))}
                  placeholder="e.g. Personnel Unit" style={S.input} placeholderTextColor="#CBD5E1" />

                <Text style={S.labelMuted}>Documents Handled</Text>
                <TextInput value={editForm.documentsHandled}
                  onChangeText={(v) => setEditForm((f) => ({ ...f, documentsHandled: v }))}
                  placeholder="e.g. Memorandum, Letter, Report" style={S.input} placeholderTextColor="#CBD5E1" />
                <Text style={S.hint}>Separate multiple types with a comma. Leave blank to clear.</Text>

                <Text style={S.labelMuted}>
                  Reset Password{' '}
                  <Text style={{ color: '#94A3B8', fontWeight: '400', fontSize: 10 }}>(leave blank to keep)</Text>
                </Text>
                <View style={{ position: 'relative', marginBottom: 16 }}>
                  <TextInput value={editForm.newPassword}
                    onChangeText={(v) => setEditForm((f) => ({ ...f, newPassword: v }))}
                    placeholder="New password (min. 8 characters)"
                    secureTextEntry style={[S.input, { marginBottom: 0 }]} placeholderTextColor="#CBD5E1" />
                  {editForm.newPassword.length > 0 && (
                    <View style={{ position: 'absolute', right: 12, top: 14 }}>
                      <KeyRound size={16} color={editForm.newPassword.length >= 8 ? '#10B981' : '#EF4444'} />
                    </View>
                  )}
                </View>
              </ScrollView>

              <View style={S.footer}>
                <TouchableOpacity onPress={handleSaveEdit} disabled={updateMutation.isPending} activeOpacity={0.85}
                  style={[S.btnPrimary, updateMutation.isPending && { backgroundColor: '#93C5FD' }]}>
                  {updateMutation.isPending
                    ? <><ActivityIndicator color="#fff" size="small" /><Text style={S.btnPrimaryText}>Saving…</Text></>
                    : <Text style={S.btnPrimaryText}>Save Changes</Text>}
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setEditVisible(false)} style={S.btnSecondary}>
                  <Text style={S.btnSecondaryText}>Cancel</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────────

const S = {
  label: {
    fontSize: 11, fontWeight: '700' as const, color: '#0038A8',
    marginBottom: 6, textTransform: 'uppercase' as const, letterSpacing: 0.8,
  },
  labelMuted: {
    fontSize: 11, fontWeight: '700' as const, color: '#475569',
    marginBottom: 6, textTransform: 'uppercase' as const, letterSpacing: 0.8,
  },
  req: { color: '#EF4444' },
  hint: { fontSize: 11, color: '#94A3B8', marginTop: -10, marginBottom: 14 },
  input: {
    backgroundColor: '#fff', borderRadius: 12,
    paddingHorizontal: 14, paddingVertical: 13, marginBottom: 16,
    borderWidth: 1.5, borderColor: '#E2E8F0', fontSize: 14.5, color: '#1E293B',
  },
  footer: {
    padding: 16, paddingBottom: Platform.OS === 'ios' ? 32 : 20,
    borderTopWidth: 0.5, borderTopColor: '#E2E8F0', backgroundColor: '#F8FAFC', gap: 10,
  },
  btnPrimary: {
    backgroundColor: '#0038A8', borderRadius: 13, paddingVertical: 15,
    alignItems: 'center' as const, flexDirection: 'row' as const, justifyContent: 'center' as const, gap: 8,
  },
  btnPrimaryText: { color: '#fff', fontSize: 15, fontWeight: '700' as const },
  btnSecondary: {
    borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 13,
    paddingVertical: 13, alignItems: 'center' as const, backgroundColor: '#fff',
  },
  btnSecondaryText: { color: '#64748B', fontSize: 14, fontWeight: '600' as const },
};
