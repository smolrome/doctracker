import { useState, useRef } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView, Alert,
  ActivityIndicator, StatusBar, Platform, FlatList, Clipboard,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useMutation } from '@tanstack/react-query';
import * as FileSystem from 'expo-file-system';
import api from '../../lib/api';
import { SelectField } from '../../components/ui/SelectField';
import {
  ArrowLeft, UserPlus, Plus, Trash2, Check, X, Copy, ChevronDown, ChevronUp,
  FileSpreadsheet,
} from 'lucide-react-native';

// ── Types ──────────────────────────────────────────────────────────────────────

type UserRow = { id: string; full_name: string; email: string; documents_handled: string };

type CreateResult = {
  username: string;
  full_name: string;
  email: string;
  ok: boolean;
  updated: boolean;
  email_sent: boolean;
  password?: string;
  msg: string;
};

const ROLES = ['staff', 'admin', 'client'];

function uid() { return `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`; }
function emptyRow(): UserRow { return { id: uid(), full_name: '', email: '', documents_handled: '' }; }

// ── Component ──────────────────────────────────────────────────────────────────

const EXCEL_MIME_TYPES = [
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel',
  '*/*',
];
const EXCEL_EXTENSIONS = ['xlsx', 'xls', 'xlsm'];
const TEN_MB = 10 * 1024 * 1024;

export default function BulkCreateUsers() {
  const router = useRouter();
  const scrollRef = useRef<ScrollView>(null);

  const [rows, setRows]         = useState<UserRow[]>([emptyRow()]);
  const [role, setRole]         = useState('staff');
  const [office, setOffice]     = useState('');
  const [results, setResults]   = useState<CreateResult[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [importing, setImporting] = useState(false);

  // ── Mutations ──────────────────────────────────────────────────────────────

  const createMutation = useMutation({
    mutationFn: () => {
      const users = rows
        .filter((r) => r.email.trim())
        .map((r) => ({
          full_name:        r.full_name.trim(),
          email:            r.email.trim(),
          documents_handled: r.documents_handled.trim(),
        }));
      if (users.length === 0) throw new Error('Add at least one user with an email address.');
      return api.post('/admin/bulk-create-users', { users, role, office: office.trim() });
    },
    onSuccess: (res) => {
      setResults(res.data.results ?? []);
    },
    onError: (e: any) => Alert.alert('Error', e?.message || e?.response?.data?.error || 'Failed to create users.'),
  });

  const handleSubmit = () => {
    const valid = rows.filter((r) => r.email.trim());
    if (valid.length === 0) { Alert.alert('No users', 'Add at least one email address.'); return; }
    Alert.alert(
      'Create Accounts',
      `Create ${valid.length} user account(s) with role "${role}"?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Create', onPress: () => { setResults([]); createMutation.mutate(); } },
      ],
    );
  };

  // ── Excel import ──────────────────────────────────────────────────────────

  const handleImportExcel = async () => {
    let DocumentPicker: any;
    try {
      DocumentPicker = require('expo-document-picker');
    } catch {
      Alert.alert('Not Available', 'File import requires the full app build. Please use the EAS build instead of Expo Go.');
      return;
    }

    const result = await DocumentPicker.getDocumentAsync({
      type: EXCEL_MIME_TYPES,
      copyToCacheDirectory: true,
    });

    if (result.canceled || !result.assets?.[0]) return;

    const asset = result.assets[0];
    const fileName = asset.name ?? 'upload.xlsx';
    const ext = fileName.split('.').pop()?.toLowerCase() ?? '';

    if (!EXCEL_EXTENSIONS.includes(ext)) {
      Alert.alert('Invalid File', `Only .xlsx, .xls, and .xlsm files are supported.\n\nSelected: .${ext}`);
      return;
    }

    if (asset.size && asset.size > TEN_MB) {
      Alert.alert(
        'Large File',
        `This file is ${(asset.size / (1024 * 1024)).toFixed(1)} MB. The server may reject files over 10 MB, but we'll try anyway.`,
      );
    }

    setImporting(true);
    try {
      const base64 = await FileSystem.readAsStringAsync(asset.uri, {
        encoding: FileSystem.EncodingType.Base64,
      });

      const mimeType = asset.mimeType || 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
      const fd = new FormData();
      fd.append('file', { uri: asset.uri, name: fileName, type: mimeType } as any);

      const res = await api.post('/parse-excel-users', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      const imported: UserRow[] = (res.data?.rows ?? []).map((row: any) => ({
        id:               uid(),
        full_name:        String(row.name ?? '').trim(),
        email:            String(row.email ?? '').trim(),
        documents_handled: String(row.documents ?? '').trim(),
      }));

      if (imported.length === 0) {
        Alert.alert('No Rows Found', 'The file was parsed but contained no user rows. Check that your sheet has Name, Email, and Documents columns.');
        return;
      }

      setRows(imported);
      setResults([]);
      scrollRef.current?.scrollTo({ y: 0, animated: true });
      Alert.alert('Imported', `${imported.length} row${imported.length !== 1 ? 's' : ''} loaded from "${fileName}".`);
    } catch (e: any) {
      const msg = e?.response?.data?.error || e?.message || 'Could not parse the Excel file.';
      Alert.alert('Import Failed', msg);
    } finally {
      setImporting(false);
    }
  };

  // ── Row helpers ────────────────────────────────────────────────────────────

  const addRow = () => setRows((r) => [...r, emptyRow()]);

  const removeRow = (id: string) => {
    if (rows.length === 1) { setRows([emptyRow()]); return; }
    setRows((r) => r.filter((row) => row.id !== id));
  };

  const updateRow = (id: string, field: keyof Omit<UserRow, 'id'>, value: string) =>
    setRows((r) => r.map((row) => row.id === id ? { ...row, [field]: value } : row));

  const copyPassword = (pw: string) => {
    Clipboard.setString(pw);
    Alert.alert('Copied', 'Temporary password copied to clipboard.');
  };

  // ── Render ────────────────────────────────────────────────────────────────

  const okCount   = results.filter((r) => r.ok).length;
  const failCount = results.filter((r) => !r.ok).length;

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
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <UserPlus size={22} color="#fff" />
          <View>
            <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800' }}>Bulk Create Accounts</Text>
            <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 12, marginTop: 2 }}>
              Create multiple staff accounts at once
            </Text>
          </View>
        </View>
      </View>

      <ScrollView ref={scrollRef} contentContainerStyle={{ padding: 20, paddingBottom: 60 }} keyboardShouldPersistTaps="handled">

        {/* Import from Excel */}
        <TouchableOpacity
          onPress={handleImportExcel}
          disabled={importing}
          activeOpacity={0.8}
          style={{
            flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10,
            backgroundColor: importing ? '#F1F5F9' : '#F0FDF4',
            borderRadius: 14, paddingVertical: 15, marginBottom: 16,
            borderWidth: 1.5, borderColor: importing ? '#E2E8F0' : '#86EFAC',
          }}
        >
          {importing
            ? <><ActivityIndicator size="small" color="#16A34A" /><Text style={{ color: '#15803D', fontSize: 14, fontWeight: '700' }}>Importing…</Text></>
            : <><FileSpreadsheet size={18} color="#16A34A" /><Text style={{ color: '#15803D', fontSize: 14, fontWeight: '700' }}>📂 Import from Excel</Text></>}
        </TouchableOpacity>

        {/* Global settings */}
        <View style={{ backgroundColor: '#fff', borderRadius: 16, padding: 20, marginBottom: 16, borderWidth: 0.5, borderColor: '#E2E8F0' }}>
          <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 14, marginBottom: 14 }}>
            Default Settings
          </Text>

          <Text style={S.labelMuted}>Role (applies to all)</Text>
          <SelectField value={role} onChange={setRole} options={ROLES} placeholder="Select role…" label="Role" />

          <Text style={S.labelMuted}>Office / Unit (applies to all)</Text>
          <TextInput value={office} onChangeText={setOffice}
            placeholder="e.g. Personnel Unit (leave blank to skip)"
            style={S.input} placeholderTextColor="#CBD5E1" />
        </View>

        {/* User rows */}
        <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 14, marginBottom: 12 }}>
          Users to Create ({rows.filter((r) => r.email.trim()).length} with email)
        </Text>

        {rows.map((row, idx) => (
          <View key={row.id} style={{
            backgroundColor: '#fff', borderRadius: 14, padding: 16, marginBottom: 10,
            borderWidth: 0.5, borderColor: '#E2E8F0',
          }}>
            {/* Row header */}
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <View style={{
                width: 28, height: 28, borderRadius: 14,
                backgroundColor: row.email.trim() ? '#0038A8' : '#E2E8F0',
                alignItems: 'center', justifyContent: 'center',
              }}>
                <Text style={{ color: row.email.trim() ? '#fff' : '#94A3B8', fontSize: 12, fontWeight: '800' }}>
                  {idx + 1}
                </Text>
              </View>
              <TouchableOpacity onPress={() => removeRow(row.id)}
                style={{ backgroundColor: '#FEF2F2', borderRadius: 8, padding: 6 }}>
                <Trash2 size={14} color="#EF4444" />
              </TouchableOpacity>
            </View>

            <Text style={S.label}>Email <Text style={S.req}>*</Text></Text>
            <TextInput value={row.email} onChangeText={(v) => updateRow(row.id, 'email', v)}
              placeholder="e.g. juan@deped.gov.ph"
              keyboardType="email-address" autoCapitalize="none"
              style={S.input} placeholderTextColor="#CBD5E1" />

            <Text style={S.labelMuted}>Full Name</Text>
            <TextInput value={row.full_name} onChangeText={(v) => updateRow(row.id, 'full_name', v)}
              placeholder="e.g. Juan dela Cruz"
              style={S.input} placeholderTextColor="#CBD5E1" />

            <Text style={S.labelMuted}>Documents Handled</Text>
            <TextInput value={row.documents_handled} onChangeText={(v) => updateRow(row.id, 'documents_handled', v)}
              placeholder="e.g. Memorandum, Letter"
              style={S.input} placeholderTextColor="#CBD5E1" />
          </View>
        ))}

        {/* Add row */}
        <TouchableOpacity onPress={addRow}
          style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
            backgroundColor: '#EFF6FF', borderRadius: 12, paddingVertical: 13,
            borderWidth: 1.5, borderColor: '#BFDBFE', marginBottom: 20 }}>
          <Plus size={16} color="#0038A8" />
          <Text style={{ color: '#0038A8', fontSize: 14, fontWeight: '700' }}>Add Another User</Text>
        </TouchableOpacity>

        {/* Submit */}
        <TouchableOpacity onPress={handleSubmit} disabled={createMutation.isPending} activeOpacity={0.85}
          style={[S.btnPrimary, createMutation.isPending && { backgroundColor: '#93C5FD' }]}>
          {createMutation.isPending
            ? <><ActivityIndicator color="#fff" size="small" /><Text style={S.btnPrimaryText}>Creating accounts…</Text></>
            : <><UserPlus size={18} color="#fff" /><Text style={S.btnPrimaryText}>
                Create {rows.filter((r) => r.email.trim()).length} Account{rows.filter((r) => r.email.trim()).length !== 1 ? 's' : ''}
              </Text></>}
        </TouchableOpacity>

        {/* ── Results ── */}
        {results.length > 0 && (
          <View style={{ marginTop: 24 }}>
            {/* Summary */}
            <View style={{ flexDirection: 'row', gap: 10, marginBottom: 14 }}>
              <View style={{ flex: 1, backgroundColor: '#F0FDF4', borderRadius: 12, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: '#BBF7D0' }}>
                <Text style={{ fontSize: 24, fontWeight: '800', color: '#166534' }}>{okCount}</Text>
                <Text style={{ fontSize: 12, color: '#16A34A', fontWeight: '600' }}>Created / Updated</Text>
              </View>
              {failCount > 0 && (
                <View style={{ flex: 1, backgroundColor: '#FEF2F2', borderRadius: 12, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: '#FECACA' }}>
                  <Text style={{ fontSize: 24, fontWeight: '800', color: '#DC2626' }}>{failCount}</Text>
                  <Text style={{ fontSize: 12, color: '#EF4444', fontWeight: '600' }}>Failed</Text>
                </View>
              )}
            </View>

            <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 14, marginBottom: 10 }}>Details</Text>
            {results.map((r, i) => {
              const isOpen = !!expanded[r.username + i];
              return (
                <View key={i} style={{
                  backgroundColor: '#fff', borderRadius: 12, marginBottom: 8,
                  borderWidth: 0.5, borderColor: r.ok ? '#BBF7D0' : '#FECACA', overflow: 'hidden',
                }}>
                  {/* Result header */}
                  <TouchableOpacity
                    onPress={() => setExpanded((e) => ({ ...e, [r.username + i]: !isOpen }))}
                    style={{ flexDirection: 'row', alignItems: 'center', padding: 14, gap: 10 }}>
                    <View style={{
                      width: 28, height: 28, borderRadius: 14,
                      backgroundColor: r.ok ? '#DCFCE7' : '#FEF2F2',
                      alignItems: 'center', justifyContent: 'center',
                    }}>
                      {r.ok
                        ? <Check size={14} color="#16A34A" />
                        : <X size={14} color="#DC2626" />}
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontWeight: '700', color: '#1E293B', fontSize: 13 }}>
                        {r.full_name || r.username}
                      </Text>
                      <Text style={{ fontSize: 11, color: '#64748B' }}>{r.email}</Text>
                    </View>
                    {r.updated && (
                      <View style={{ backgroundColor: '#FEF3C7', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
                        <Text style={{ fontSize: 10, fontWeight: '700', color: '#92400E' }}>UPDATED</Text>
                      </View>
                    )}
                    {isOpen ? <ChevronUp size={16} color="#94A3B8" /> : <ChevronDown size={16} color="#94A3B8" />}
                  </TouchableOpacity>

                  {isOpen && (
                    <View style={{ padding: 14, paddingTop: 0, borderTopWidth: 0.5, borderTopColor: '#F1F5F9' }}>
                      <Text style={{ fontSize: 12, color: '#64748B', marginBottom: 4 }}>
                        Username: <Text style={{ color: '#1E293B', fontWeight: '700' }}>@{r.username}</Text>
                      </Text>
                      {r.email_sent ? (
                        <Text style={{ fontSize: 12, color: '#16A34A' }}>✅ Credentials emailed successfully</Text>
                      ) : r.password ? (
                        <View>
                          <Text style={{ fontSize: 12, color: '#B45309', marginBottom: 6 }}>
                            ⚠️ Email failed. Share temp password manually:
                          </Text>
                          <View style={{ backgroundColor: '#FFF7ED', borderRadius: 8, padding: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                            <Text style={{ fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace', fontSize: 15, fontWeight: '700', color: '#1E293B' }}>
                              {r.password}
                            </Text>
                            <TouchableOpacity onPress={() => copyPassword(r.password!)}>
                              <Copy size={16} color="#B45309" />
                            </TouchableOpacity>
                          </View>
                        </View>
                      ) : null}
                      {r.msg ? (
                        <Text style={{ fontSize: 12, color: r.ok ? '#64748B' : '#DC2626', marginTop: 4 }}>{r.msg}</Text>
                      ) : null}
                    </View>
                  )}
                </View>
              );
            })}
          </View>
        )}
      </ScrollView>
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
  input: {
    backgroundColor: '#F8FAFC', borderRadius: 12,
    paddingHorizontal: 14, paddingVertical: 13, marginBottom: 16,
    borderWidth: 1.5, borderColor: '#E2E8F0', fontSize: 14.5, color: '#1E293B',
  },
  btnPrimary: {
    backgroundColor: '#0038A8', borderRadius: 13, paddingVertical: 15,
    alignItems: 'center' as const, flexDirection: 'row' as const,
    justifyContent: 'center' as const, gap: 8,
  },
  btnPrimaryText: { color: '#fff', fontSize: 15, fontWeight: '700' as const },
};
