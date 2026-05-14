import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, FlatList, Modal,
  ScrollView, Alert, ActivityIndicator, StatusBar, RefreshControl,
  Platform, KeyboardAvoidingView,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../lib/store';
import api from '../../lib/api';
import { ArrowLeft, Plus, X, Building2, Users, FileSpreadsheet, Pencil } from 'lucide-react-native';
import * as DocumentPicker from 'expo-document-picker';

const EMPTY_FORM = { office_name: '', primary_recipient: '' };

export default function ManageOffices() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();

  // Redirect non-admins
  if (user?.role !== 'admin') {
    router.replace('/(app)/dashboard');
    return null;
  }

  // ── State ────────────────────────────────────────────────────────────────
  const [addVisible, setAddVisible]       = useState(false);
  const [form, setForm]                   = useState(EMPTY_FORM);
  const [recipientOpen, setRecipientOpen] = useState(false);

  const [bulkVisible, setBulkVisible] = useState(false);
  const [bulkRows, setBulkRows]       = useState([{ office_name: '', primary_recipient: '' }]);
  const [bulkResult, setBulkResult]   = useState<string | null>(null);

  // Edit office
  const [editOffice, setEditOffice]           = useState<any | null>(null);
  const [editRecipient, setEditRecipient]     = useState('');
  const [editRecipientOpen, setEditRecipientOpen] = useState(false);

  // Excel import
  const [xlsVisible, setXlsVisible]       = useState(false);
  const [xlsParsedRows, setXlsParsedRows] = useState<{ office_name: string; primary_recipient: string }[]>([]);
  const [xlsStatus, setXlsStatus]         = useState<string | null>(null);
  const [xlsResult, setXlsResult]         = useState<string | null>(null);
  const [xlsUploading, setXlsUploading]   = useState(false);

  // ── Queries ──────────────────────────────────────────────────────────────
  const { data: offices = [], isLoading, isRefetching, refetch } = useQuery<any[]>({
    queryKey: ['offices'],
    queryFn: () => api.get('/offices').then((r: any) => r.data ?? []),
    staleTime: 1000 * 60 * 5,
  });

  const { data: allUsers = [] } = useQuery<any[]>({
    queryKey: ['admin-users'],
    queryFn: () => api.get('/admin/users').then((r: any) => r.data ?? []),
    staleTime: 1000 * 60 * 5,
  });

  const staff = allUsers.filter((u: any) => u.role === 'staff' || u.role === 'admin');

  // ── Mutations ────────────────────────────────────────────────────────────
  const invalidateOffices = () => queryClient.invalidateQueries({ queryKey: ['offices'] });

  const createMutation = useMutation({
    mutationFn: (body: typeof EMPTY_FORM) => api.post('/offices', body),
    onSuccess: () => {
      invalidateOffices();
      setAddVisible(false);
      setForm(EMPTY_FORM);
      Alert.alert('Created', 'Office saved successfully.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to create office.'),
  });

  const bulkMutation = useMutation({
    mutationFn: (rows: typeof bulkRows) => api.post('/offices/bulk', rows),
    onSuccess: (res: any) => {
      invalidateOffices();
      const d = res.data;
      let msg = `✅ ${d.created} office${d.created !== 1 ? 's' : ''} saved.`;
      if (d.skipped) msg += ` ${d.skipped} skipped.`;
      if (d.errors?.length) msg += ` ${d.errors.length} failed.`;
      setBulkResult(msg);
    },
    onError: (e: any) => setBulkResult('Error: ' + (e?.response?.data?.error || 'Failed.')),
  });

  const updateMutation = useMutation({
    mutationFn: ({ slug, primary_recipient }: { slug: string; primary_recipient: string }) =>
      api.patch(`/offices/${slug}`, { primary_recipient }),
    onSuccess: () => {
      invalidateOffices();
      setEditOffice(null);
      Alert.alert('Updated', 'Office updated successfully.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to update office.'),
  });

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleCreate = () => {
    if (!form.office_name.trim()) {
      Alert.alert('Required', 'Office name is required.');
      return;
    }
    createMutation.mutate(form);
  };

  const addBulkRow = () =>
    setBulkRows((rows) => [...rows, { office_name: '', primary_recipient: '' }]);

  const updateBulkRow = (i: number, field: string, value: string) =>
    setBulkRows((rows) => rows.map((r, idx) => idx === i ? { ...r, [field]: value } : r));

  const removeBulkRow = (i: number) =>
    setBulkRows((rows) => rows.filter((_, idx) => idx !== i));

  const handleBulkSave = () => {
    const payload = bulkRows.filter((r) => r.office_name.trim());
    if (!payload.length) { setBulkResult('No offices to save.'); return; }
    setBulkResult(null);
    bulkMutation.mutate(payload);
  };

  const openEdit = (o: any) => {
    setEditOffice(o);
    setEditRecipient(o.primary_recipient || '');
    setEditRecipientOpen(false);
  };

  const handleEdit = () => {
    if (!editOffice) return;
    updateMutation.mutate({ slug: editOffice.office_slug, primary_recipient: editRecipient });
  };

  const pickExcelFile = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: [
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'application/vnd.ms-excel',
          '*/*',
        ],
        copyToCacheDirectory: true,
      });
      if (result.canceled || !result.assets?.length) return;
      const file = result.assets[0];

      setXlsUploading(true);
      setXlsStatus('Uploading…');
      setXlsParsedRows([]);
      setXlsResult(null);

      const formData = new FormData();
      formData.append('file', {
        uri: file.uri,
        name: file.name || 'offices.xlsx',
        type: file.mimeType || 'application/octet-stream',
      } as any);

      const res = await api.post('/parse-excel-offices', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const rows: any[] = res.data?.rows ?? [];
      if (!rows.length) {
        setXlsStatus('No valid rows found. Make sure the file has an "office" column.');
      } else {
        setXlsParsedRows(rows);
        setXlsStatus(`Found ${rows.length} row${rows.length !== 1 ? 's' : ''}. Review and tap Import All.`);
      }
    } catch (e: any) {
      setXlsStatus('Error: ' + (e?.response?.data?.error || e?.message || 'Failed to parse file.'));
    } finally {
      setXlsUploading(false);
    }
  };

  const handleXlsImport = async () => {
    if (!xlsParsedRows.length) return;
    setXlsResult(null);
    try {
      const res = await api.post('/offices/bulk', xlsParsedRows);
      const d = res.data;
      let msg = `✅ ${d.created} office${d.created !== 1 ? 's' : ''} imported.`;
      if (d.skipped) msg += ` ${d.skipped} skipped.`;
      if (d.errors?.length) msg += ` ${d.errors.length} failed.`;
      setXlsResult(msg);
      invalidateOffices();
    } catch (e: any) {
      setXlsResult('Error: ' + (e?.response?.data?.error || 'Import failed.'));
    }
  };

  // ── Recipient label helper ────────────────────────────────────────────────
  const recipientLabel = (username: string) => {
    const u = staff.find((s: any) => s.username === username);
    return u ? (u.full_name || u.username) : username || '— None —';
  };

  // ── Render office row ─────────────────────────────────────────────────────
  const renderOffice = ({ item: o }: { item: any }) => (
    <TouchableOpacity
      onPress={() => openEdit(o)}
      activeOpacity={0.75}
      style={{
        backgroundColor: '#fff', borderRadius: 14, padding: 14, marginBottom: 10,
        borderWidth: 0.5, borderColor: '#E2E8F0',
        flexDirection: 'row', alignItems: 'center', gap: 12,
      }}
    >
      <View style={{
        width: 40, height: 40, borderRadius: 20,
        backgroundColor: '#EFF6FF', alignItems: 'center', justifyContent: 'center',
      }}>
        <Building2 size={20} color="#0038A8" />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ fontSize: 14.5, fontWeight: '700', color: '#1E293B' }} numberOfLines={1}>
          {o.office_name}
        </Text>
        {o.primary_recipient_name ? (
          <Text style={{ fontSize: 12, color: '#64748B', marginTop: 2 }}>
            📥 {o.primary_recipient_name}
          </Text>
        ) : (
          <Text style={{ fontSize: 12, color: '#CBD5E1', marginTop: 2 }}>No primary recipient</Text>
        )}
      </View>
      <Pencil size={15} color="#CBD5E1" />
    </TouchableOpacity>
  );

  // ── Main render ───────────────────────────────────────────────────────────
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
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Building2 size={22} color="#fff" />
            <View>
              <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800' }}>Manage Offices</Text>
              <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 12, marginTop: 2 }}>
                {offices.length} office{offices.length !== 1 ? 's' : ''}
              </Text>
            </View>
          </View>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity
              onPress={() => { setXlsParsedRows([]); setXlsStatus(null); setXlsResult(null); setXlsVisible(true); }}
              style={{ backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 10, padding: 8, borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' }}>
              <FileSpreadsheet size={18} color="#fff" />
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => { setBulkResult(null); setBulkRows([{ office_name: '', primary_recipient: '' }]); setBulkVisible(true); }}
              style={{ backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 10, padding: 8, borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' }}>
              <Users size={18} color="#fff" />
            </TouchableOpacity>
          </View>
        </View>
      </View>

      {/* List */}
      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
        </View>
      ) : (
        <FlatList
          data={offices}
          keyExtractor={(o) => o.office_slug || o.office_name}
          renderItem={renderOffice}
          contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 12, paddingBottom: 120 }}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} colors={['#0038A8']} tintColor="#0038A8" />
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 60 }}>
              <Building2 size={40} color="#CBD5E1" />
              <Text style={{ color: '#94A3B8', fontSize: 14, marginTop: 12 }}>No offices yet</Text>
            </View>
          }
        />
      )}

      {/* FAB */}
      <TouchableOpacity
        onPress={() => { setForm(EMPTY_FORM); setRecipientOpen(false); setAddVisible(true); }}
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

      {/* ── ADD OFFICE MODAL ─────────────────────────────────────────────── */}
      <Modal visible={addVisible} animationType="slide" transparent onRequestClose={() => setAddVisible(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
            <TouchableOpacity style={{ position: 'absolute', inset: 0 } as any} onPress={() => setAddVisible(false)} activeOpacity={1} />
            <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 28, borderTopRightRadius: 28, maxHeight: '85%', overflow: 'hidden' }}>
              <View style={{ backgroundColor: '#0038A8', paddingTop: 20, paddingBottom: 16, paddingHorizontal: 20 }}>
                <View style={{ position: 'absolute', top: 10, left: 0, right: 0, alignItems: 'center' }}>
                  <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.30)' }} />
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
                  <View>
                    <Text style={{ fontSize: 18, fontWeight: '800', color: '#fff' }}>Add Office</Text>
                    <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.60)', marginTop: 2 }}>Create a new office</Text>
                  </View>
                  <TouchableOpacity onPress={() => setAddVisible(false)}
                    style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' }}>
                    <X size={18} color="#fff" />
                  </TouchableOpacity>
                </View>
              </View>

              <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 8 }} keyboardShouldPersistTaps="handled">
                <Text style={S.label}>Office Name <Text style={{ color: '#EF4444' }}>*</Text></Text>
                <TextInput
                  value={form.office_name}
                  onChangeText={(v) => setForm((f) => ({ ...f, office_name: v }))}
                  placeholder="e.g. Personnel Unit, Budget Section"
                  style={S.input} placeholderTextColor="#CBD5E1"
                />

                <Text style={S.labelMuted}>Primary Recipient</Text>
                <TouchableOpacity
                  onPress={() => setRecipientOpen((v) => !v)}
                  style={{
                    backgroundColor: '#fff', borderRadius: 12,
                    paddingHorizontal: 14, paddingVertical: 13, marginBottom: 4,
                    borderWidth: 1.5, borderColor: recipientOpen ? '#0038A8' : '#E2E8F0',
                    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
                  }}
                >
                  <Text style={{ fontSize: 14.5, color: form.primary_recipient ? '#1E293B' : '#CBD5E1' }} numberOfLines={1}>
                    {form.primary_recipient ? recipientLabel(form.primary_recipient) : '— None —'}
                  </Text>
                  <Text style={{ color: '#94A3B8', fontSize: 12 }}>{recipientOpen ? '▲' : '▼'}</Text>
                </TouchableOpacity>
                {recipientOpen && (
                  <ScrollView style={{ maxHeight: 180, borderRadius: 10, borderWidth: 1, borderColor: '#E2E8F0', marginBottom: 12 }} nestedScrollEnabled>
                    <TouchableOpacity
                      onPress={() => { setForm((f) => ({ ...f, primary_recipient: '' })); setRecipientOpen(false); }}
                      style={{ paddingHorizontal: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#F1F5F9', backgroundColor: !form.primary_recipient ? '#EFF6FF' : '#fff' }}
                    >
                      <Text style={{ fontSize: 13, color: '#94A3B8' }}>— None —</Text>
                    </TouchableOpacity>
                    {staff.map((s: any, i: number) => (
                      <TouchableOpacity
                        key={s.username}
                        onPress={() => { setForm((f) => ({ ...f, primary_recipient: s.username })); setRecipientOpen(false); }}
                        style={{
                          paddingHorizontal: 12, paddingVertical: 10,
                          borderBottomWidth: i < staff.length - 1 ? 1 : 0, borderBottomColor: '#F1F5F9',
                          backgroundColor: form.primary_recipient === s.username ? '#EFF6FF' : '#fff',
                        }}
                      >
                        <Text style={{ fontSize: 13, color: '#1E293B', fontWeight: form.primary_recipient === s.username ? '700' : '400' }}>
                          {s.full_name || s.username}
                        </Text>
                        <Text style={{ fontSize: 11, color: '#94A3B8', marginTop: 1 }}>@{s.username}</Text>
                      </TouchableOpacity>
                    ))}
                  </ScrollView>
                )}
              </ScrollView>

              <View style={S.footer}>
                <TouchableOpacity onPress={handleCreate} disabled={createMutation.isPending} activeOpacity={0.85}
                  style={[S.btnPrimary, createMutation.isPending && { backgroundColor: '#93C5FD' }]}>
                  {createMutation.isPending
                    ? <><ActivityIndicator color="#fff" size="small" /><Text style={S.btnPrimaryText}>Saving…</Text></>
                    : <><Plus size={18} color="#fff" /><Text style={S.btnPrimaryText}>Save Office</Text></>}
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setAddVisible(false)} style={S.btnSecondary}>
                  <Text style={S.btnSecondaryText}>Cancel</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* ── BULK ADD MODAL ───────────────────────────────────────────────── */}
      <Modal visible={bulkVisible} animationType="slide" transparent onRequestClose={() => setBulkVisible(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
            <TouchableOpacity style={{ position: 'absolute', inset: 0 } as any} onPress={() => setBulkVisible(false)} activeOpacity={1} />
            <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 28, borderTopRightRadius: 28, maxHeight: '92%', overflow: 'hidden' }}>
              <View style={{ backgroundColor: '#0038A8', paddingTop: 20, paddingBottom: 16, paddingHorizontal: 20 }}>
                <View style={{ position: 'absolute', top: 10, left: 0, right: 0, alignItems: 'center' }}>
                  <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.30)' }} />
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
                  <View>
                    <Text style={{ fontSize: 18, fontWeight: '800', color: '#fff' }}>Bulk Add Offices</Text>
                    <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.60)', marginTop: 2 }}>Add multiple offices at once</Text>
                  </View>
                  <TouchableOpacity onPress={() => setBulkVisible(false)}
                    style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' }}>
                    <X size={18} color="#fff" />
                  </TouchableOpacity>
                </View>
              </View>

              <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 8 }} keyboardShouldPersistTaps="handled">
                {bulkRows.map((row, i) => (
                  <View key={i} style={{ backgroundColor: '#fff', borderRadius: 12, padding: 12, marginBottom: 10, borderWidth: 1, borderColor: '#E2E8F0' }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                      <Text style={{ fontSize: 12, fontWeight: '700', color: '#64748B' }}>ROW {i + 1}</Text>
                      {bulkRows.length > 1 && (
                        <TouchableOpacity onPress={() => removeBulkRow(i)}
                          style={{ backgroundColor: '#FEF2F2', borderRadius: 6, padding: 4 }}>
                          <X size={14} color="#EF4444" />
                        </TouchableOpacity>
                      )}
                    </View>
                    <TextInput
                      value={row.office_name}
                      onChangeText={(v) => updateBulkRow(i, 'office_name', v)}
                      placeholder="Office name"
                      style={[S.input, { marginBottom: 8 }]}
                      placeholderTextColor="#CBD5E1"
                    />
                    <View style={{
                      backgroundColor: '#F8FAFC', borderRadius: 8, borderWidth: 1.5, borderColor: '#E2E8F0',
                      paddingHorizontal: 10, paddingVertical: 4,
                    }}>
                      <ScrollView style={{ maxHeight: 120 }} nestedScrollEnabled>
                        <TouchableOpacity
                          onPress={() => updateBulkRow(i, 'primary_recipient', '')}
                          style={{ paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: '#F1F5F9' }}
                        >
                          <Text style={{ fontSize: 13, color: '#94A3B8' }}>— None —</Text>
                        </TouchableOpacity>
                        {staff.map((s: any) => (
                          <TouchableOpacity
                            key={s.username}
                            onPress={() => updateBulkRow(i, 'primary_recipient', s.username)}
                            style={{ paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: '#F1F5F9', backgroundColor: row.primary_recipient === s.username ? '#EFF6FF' : 'transparent' }}
                          >
                            <Text style={{ fontSize: 13, color: '#1E293B', fontWeight: row.primary_recipient === s.username ? '700' : '400' }}>
                              {s.full_name || s.username}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </ScrollView>
                    </View>
                    {row.primary_recipient ? (
                      <Text style={{ fontSize: 11, color: '#0038A8', marginTop: 4 }}>
                        Selected: {recipientLabel(row.primary_recipient)}
                      </Text>
                    ) : null}
                  </View>
                ))}

                <TouchableOpacity onPress={addBulkRow} style={[S.btnSecondary, { marginBottom: 8 }]}>
                  <Text style={S.btnSecondaryText}>+ Add Row</Text>
                </TouchableOpacity>

                {bulkResult ? (
                  <Text style={{ fontSize: 13, fontWeight: '600', color: bulkResult.startsWith('✅') ? '#16A34A' : '#EF4444', marginBottom: 8 }}>
                    {bulkResult}
                  </Text>
                ) : null}
              </ScrollView>

              <View style={S.footer}>
                <TouchableOpacity onPress={handleBulkSave} disabled={bulkMutation.isPending} activeOpacity={0.85}
                  style={[S.btnPrimary, bulkMutation.isPending && { backgroundColor: '#93C5FD' }]}>
                  {bulkMutation.isPending
                    ? <><ActivityIndicator color="#fff" size="small" /><Text style={S.btnPrimaryText}>Saving…</Text></>
                    : <Text style={S.btnPrimaryText}>💾 Save All</Text>}
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setBulkVisible(false)} style={S.btnSecondary}>
                  <Text style={S.btnSecondaryText}>Close</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* ── EDIT OFFICE MODAL ────────────────────────────────────────────── */}
      <Modal visible={!!editOffice} animationType="slide" transparent onRequestClose={() => setEditOffice(null)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
            <TouchableOpacity style={{ position: 'absolute', inset: 0 } as any} onPress={() => setEditOffice(null)} activeOpacity={1} />
            <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 28, borderTopRightRadius: 28, maxHeight: '80%', overflow: 'hidden' }}>
              {/* Modal header */}
              <View style={{ backgroundColor: '#0038A8', paddingTop: 20, paddingBottom: 16, paddingHorizontal: 20 }}>
                <View style={{ position: 'absolute', top: 10, left: 0, right: 0, alignItems: 'center' }}>
                  <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.30)' }} />
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
                  <View>
                    <Text style={{ fontSize: 18, fontWeight: '800', color: '#fff' }}>Edit Office</Text>
                    <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.60)', marginTop: 2 }} numberOfLines={1}>
                      {editOffice?.office_name}
                    </Text>
                  </View>
                  <TouchableOpacity onPress={() => setEditOffice(null)}
                    style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' }}>
                    <X size={18} color="#fff" />
                  </TouchableOpacity>
                </View>
              </View>

              <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 8 }} keyboardShouldPersistTaps="handled">
                {/* Read-only office name */}
                <Text style={S.label}>Office Name</Text>
                <View style={[S.input, { backgroundColor: '#F1F5F9', borderColor: '#E2E8F0', justifyContent: 'center' }]}>
                  <Text style={{ fontSize: 14.5, color: '#64748B' }}>{editOffice?.office_name}</Text>
                </View>

                {/* Recipient picker */}
                <Text style={S.labelMuted}>Primary Recipient</Text>
                <TouchableOpacity
                  onPress={() => setEditRecipientOpen((v) => !v)}
                  style={{
                    backgroundColor: '#fff', borderRadius: 12,
                    paddingHorizontal: 14, paddingVertical: 13, marginBottom: 4,
                    borderWidth: 1.5, borderColor: editRecipientOpen ? '#0038A8' : '#E2E8F0',
                    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
                  }}
                >
                  <Text style={{ fontSize: 14.5, color: editRecipient ? '#1E293B' : '#CBD5E1' }} numberOfLines={1}>
                    {editRecipient ? recipientLabel(editRecipient) : '— None —'}
                  </Text>
                  <Text style={{ color: '#94A3B8', fontSize: 12 }}>{editRecipientOpen ? '▲' : '▼'}</Text>
                </TouchableOpacity>
                {editRecipientOpen && (
                  <ScrollView style={{ maxHeight: 200, borderRadius: 10, borderWidth: 1, borderColor: '#E2E8F0', marginBottom: 12 }} nestedScrollEnabled>
                    <TouchableOpacity
                      onPress={() => { setEditRecipient(''); setEditRecipientOpen(false); }}
                      style={{ paddingHorizontal: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#F1F5F9', backgroundColor: !editRecipient ? '#EFF6FF' : '#fff' }}
                    >
                      <Text style={{ fontSize: 13, color: '#94A3B8' }}>— None —</Text>
                    </TouchableOpacity>
                    {staff.map((s: any, i: number) => (
                      <TouchableOpacity
                        key={s.username}
                        onPress={() => { setEditRecipient(s.username); setEditRecipientOpen(false); }}
                        style={{
                          paddingHorizontal: 12, paddingVertical: 10,
                          borderBottomWidth: i < staff.length - 1 ? 1 : 0, borderBottomColor: '#F1F5F9',
                          backgroundColor: editRecipient === s.username ? '#EFF6FF' : '#fff',
                        }}
                      >
                        <Text style={{ fontSize: 13, color: '#1E293B', fontWeight: editRecipient === s.username ? '700' : '400' }}>
                          {s.full_name || s.username}
                        </Text>
                        <Text style={{ fontSize: 11, color: '#94A3B8', marginTop: 1 }}>@{s.username}</Text>
                      </TouchableOpacity>
                    ))}
                  </ScrollView>
                )}
              </ScrollView>

              <View style={S.footer}>
                <TouchableOpacity onPress={handleEdit} disabled={updateMutation.isPending} activeOpacity={0.85}
                  style={[S.btnPrimary, updateMutation.isPending && { backgroundColor: '#93C5FD' }]}>
                  {updateMutation.isPending
                    ? <><ActivityIndicator color="#fff" size="small" /><Text style={S.btnPrimaryText}>Saving…</Text></>
                    : <><Pencil size={16} color="#fff" /><Text style={S.btnPrimaryText}>Save Changes</Text></>}
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setEditOffice(null)} style={S.btnSecondary}>
                  <Text style={S.btnSecondaryText}>Cancel</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* ── EXCEL IMPORT MODAL ───────────────────────────────────────────── */}
      <Modal visible={xlsVisible} animationType="slide" transparent onRequestClose={() => setXlsVisible(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
            <TouchableOpacity style={{ position: 'absolute', inset: 0 } as any} onPress={() => setXlsVisible(false)} activeOpacity={1} />
            <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 28, borderTopRightRadius: 28, maxHeight: '90%', overflow: 'hidden' }}>
              {/* Modal header */}
              <View style={{ backgroundColor: '#0038A8', paddingTop: 20, paddingBottom: 16, paddingHorizontal: 20 }}>
                <View style={{ position: 'absolute', top: 10, left: 0, right: 0, alignItems: 'center' }}>
                  <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.30)' }} />
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
                  <View>
                    <Text style={{ fontSize: 18, fontWeight: '800', color: '#fff' }}>Import from Excel</Text>
                    <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.60)', marginTop: 2 }}>Upload an .xlsx file with office data</Text>
                  </View>
                  <TouchableOpacity onPress={() => setXlsVisible(false)}
                    style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' }}>
                    <X size={18} color="#fff" />
                  </TouchableOpacity>
                </View>
              </View>

              <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 8 }} keyboardShouldPersistTaps="handled">
                {/* Info box */}
                <View style={{ backgroundColor: '#EFF6FF', borderRadius: 10, padding: 12, marginBottom: 16, borderWidth: 1, borderColor: '#BFDBFE' }}>
                  <Text style={{ fontSize: 12, color: '#1D4ED8', lineHeight: 18 }}>
                    Your Excel file should have a column named <Text style={{ fontWeight: '700' }}>office</Text> or <Text style={{ fontWeight: '700' }}>name</Text>.
                    Optionally include a <Text style={{ fontWeight: '700' }}>recipient</Text> or <Text style={{ fontWeight: '700' }}>staff</Text> column.
                  </Text>
                </View>

                {/* Pick file button */}
                <TouchableOpacity
                  onPress={pickExcelFile}
                  disabled={xlsUploading}
                  activeOpacity={0.8}
                  style={{
                    backgroundColor: xlsUploading ? '#93C5FD' : '#0038A8',
                    borderRadius: 13, paddingVertical: 15,
                    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
                    marginBottom: 14,
                  }}
                >
                  {xlsUploading
                    ? <><ActivityIndicator color="#fff" size="small" /><Text style={S.btnPrimaryText}>Uploading…</Text></>
                    : <><FileSpreadsheet size={18} color="#fff" /><Text style={S.btnPrimaryText}>Pick Excel File</Text></>}
                </TouchableOpacity>

                {/* Status */}
                {xlsStatus ? (
                  <Text style={{ fontSize: 13, color: xlsStatus.startsWith('Error') ? '#EF4444' : '#0038A8', fontWeight: '600', marginBottom: 12 }}>
                    {xlsStatus}
                  </Text>
                ) : null}

                {/* Preview table */}
                {xlsParsedRows.length > 0 && (
                  <View style={{ borderRadius: 10, borderWidth: 1, borderColor: '#E2E8F0', overflow: 'hidden', marginBottom: 14 }}>
                    {/* Table header */}
                    <View style={{ flexDirection: 'row', backgroundColor: '#0038A8', paddingHorizontal: 12, paddingVertical: 8 }}>
                      <Text style={{ flex: 2, fontSize: 11, fontWeight: '700', color: '#fff', textTransform: 'uppercase', letterSpacing: 0.5 }}>Office Name</Text>
                      <Text style={{ flex: 1, fontSize: 11, fontWeight: '700', color: '#fff', textTransform: 'uppercase', letterSpacing: 0.5 }}>Recipient</Text>
                    </View>
                    {xlsParsedRows.map((row, i) => (
                      <View key={i} style={{
                        flexDirection: 'row', paddingHorizontal: 12, paddingVertical: 9,
                        borderTopWidth: i > 0 ? 1 : 0, borderTopColor: '#F1F5F9',
                        backgroundColor: i % 2 === 0 ? '#fff' : '#F8FAFC',
                      }}>
                        <Text style={{ flex: 2, fontSize: 13, color: '#1E293B' }} numberOfLines={1}>{row.office_name}</Text>
                        <Text style={{ flex: 1, fontSize: 13, color: '#64748B' }} numberOfLines={1}>
                          {row.primary_recipient || '—'}
                        </Text>
                      </View>
                    ))}
                  </View>
                )}

                {/* Import result */}
                {xlsResult ? (
                  <Text style={{ fontSize: 13, fontWeight: '600', color: xlsResult.startsWith('✅') ? '#16A34A' : '#EF4444', marginBottom: 8 }}>
                    {xlsResult}
                  </Text>
                ) : null}
              </ScrollView>

              <View style={S.footer}>
                {xlsParsedRows.length > 0 && !xlsResult && (
                  <TouchableOpacity onPress={handleXlsImport} activeOpacity={0.85} style={S.btnPrimary}>
                    <FileSpreadsheet size={16} color="#fff" />
                    <Text style={S.btnPrimaryText}>Import All ({xlsParsedRows.length})</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity onPress={() => setXlsVisible(false)} style={S.btnSecondary}>
                  <Text style={S.btnSecondaryText}>Close</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const S = {
  label:          { fontSize: 11, fontWeight: '700' as const, color: '#0038A8', marginBottom: 6, textTransform: 'uppercase' as const, letterSpacing: 0.8 },
  labelMuted:     { fontSize: 11, fontWeight: '700' as const, color: '#475569', marginBottom: 6, textTransform: 'uppercase' as const, letterSpacing: 0.8 },
  input:          { backgroundColor: '#fff', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 13, marginBottom: 16, borderWidth: 1.5, borderColor: '#E2E8F0', fontSize: 14.5, color: '#1E293B' },
  footer:         { padding: 16, paddingBottom: Platform.OS === 'ios' ? 32 : 20, borderTopWidth: 0.5, borderTopColor: '#E2E8F0', backgroundColor: '#F8FAFC', gap: 10 },
  btnPrimary:     { backgroundColor: '#0038A8', borderRadius: 13, paddingVertical: 15, alignItems: 'center' as const, flexDirection: 'row' as const, justifyContent: 'center' as const, gap: 8 },
  btnPrimaryText: { color: '#fff', fontSize: 15, fontWeight: '700' as const },
  btnSecondary:   { borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 13, paddingVertical: 13, alignItems: 'center' as const, backgroundColor: '#fff' },
  btnSecondaryText: { color: '#64748B', fontSize: 14, fontWeight: '600' as const },
};
