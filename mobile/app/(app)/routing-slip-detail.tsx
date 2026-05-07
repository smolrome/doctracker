import { useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity,
  ActivityIndicator, StatusBar, Alert, Modal,
  TextInput, Platform, KeyboardAvoidingView,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, FileText, MapPin, User, Calendar,
  Archive, RefreshCw, ListChecks, X,
} from 'lucide-react-native';
import api from '../../lib/api';
import { useAuthStore } from '../../lib/store';
import { useOffices } from '../../hooks/useDropdownOptions';
import { SelectField } from '../../components/ui/SelectField';

// ── Types ─────────────────────────────────────────────────────────────────────

type SlipDoc = {
  id: string;
  doc_id?: string;
  doc_name?: string;
  status?: string;
  category?: string;
  from_office?: string;
};

type RoutingSlip = {
  id: string;
  slip_id?: string;
  doc_name?: string;
  from_office?: string;
  to_office?: string;
  routed_by?: string;
  created_by?: string;
  created_at?: string;
  routed_at?: string;
  status?: string;
  remarks?: string;
  doc_ids?: string[];
  documents?: SlipDoc[];
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(ts?: string) {
  if (!ts) return '—';
  return ts.replace('T', ' ').slice(0, 16);
}

const STATUS_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  pending:   { bg: '#FEF3C7', text: '#B45309', dot: '#F59E0B' },
  accepted:  { bg: '#D1FAE5', text: '#065F46', dot: '#10B981' },
  rejected:  { bg: '#FEE2E2', text: '#991B1B', dot: '#EF4444' },
  completed: { bg: '#DBEAFE', text: '#1E40AF', dot: '#3B82F6' },
  archived:  { bg: '#F1F5F9', text: '#475569', dot: '#94A3B8' },
  active:    { bg: '#EDE9FE', text: '#5B21B6', dot: '#8B5CF6' },
};

function slipStatusStyle(status: string) {
  return STATUS_COLORS[(status || '').toLowerCase()] ?? { bg: '#F1F5F9', text: '#475569', dot: '#94A3B8' };
}

const DOC_STATUS_COLORS: Record<string, string> = {
  Pending:     '#F59E0B',
  Received:    '#10B981',
  Released:    '#3B82F6',
  Routed:      '#8B5CF6',
  'In Review': '#6366F1',
  Transferred: '#06B6D4',
  'On Hold':   '#EF4444',
  Returned:    '#DC2626',
};

// ── Component ─────────────────────────────────────────────────────────────────

const STATUS_OPTIONS = ['Pending', 'Received', 'Released', 'Routed', 'In Review', 'Transferred', 'On Hold'];

export default function RoutingSlipDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin';
  const canAct   = isAdmin || user?.role === 'staff';

  const { data: offices } = useOffices();
  const officeNames = offices?.map((o) => o.office_name) ?? [];

  // Reroute modal
  const [rerouteModal, setRerouteModal]   = useState(false);
  const [rerouteDest, setRerouteDest]     = useState('');
  const [rerouteNotes, setRerouteNotes]   = useState('');

  // Batch status modal
  const [batchModal, setBatchModal]       = useState(false);
  const [batchStatus, setBatchStatus]     = useState('');
  const [batchRemarks, setBatchRemarks]   = useState('');

  // ── Query ─────────────────────────────────────────────────────────────────

  const { data: slip, isLoading } = useQuery<RoutingSlip>({
    queryKey: ['routing-slip', id],
    queryFn: async () => {
      const res = await api.get(`/routing-slips/${id}`);
      return res.data;
    },
    enabled: !!id,
    staleTime: 1000 * 60 * 5,
  });

  // ── Archive mutation ──────────────────────────────────────────────────────

  const archiveMutation = useMutation({
    mutationFn: () => api.post(`/routing-slips/${id}/archive`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['routing-slip', id] });
      queryClient.invalidateQueries({ queryKey: ['routing-slips'] });
      Alert.alert('Archived', 'Routing slip archived successfully.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to archive slip.'),
  });

  const rerouteMutation = useMutation({
    mutationFn: ({ destination, notes }: { destination: string; notes: string }) =>
      api.post(`/routing-slips/${id}/reroute`, { destination, notes }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['routing-slips'] });
      setRerouteModal(false);
      setRerouteDest('');
      setRerouteNotes('');
      const newNo = res.data?.slip_no || '';
      Alert.alert('Rerouted', `New routing slip ${newNo} created. Original archived.`, [
        { text: 'OK', onPress: () => router.back() },
      ]);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to reroute.'),
  });

  const batchStatusMutation = useMutation({
    mutationFn: ({ status, remarks }: { status: string; remarks: string }) =>
      api.patch(`/routing-slips/${id}/batch-status`, { status, remarks }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['routing-slip', id] });
      queryClient.invalidateQueries({ queryKey: ['routing-slips'] });
      setBatchModal(false);
      setBatchStatus('');
      setBatchRemarks('');
      Alert.alert('Updated', res.data?.message || 'All documents updated.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to update.'),
  });

  const handleArchive = () => {
    Alert.alert(
      'Archive Slip',
      'Archive this routing slip? It will be moved to the archive and removed from active view.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Archive', onPress: () => archiveMutation.mutate() },
      ],
    );
  };

  // ── Loading ───────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <View style={{ flex: 1, backgroundColor: '#F8FAFC', alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator size="large" color="#0038A8" />
        <Text style={{ color: '#94A3B8', marginTop: 12, fontSize: 13 }}>Loading slip…</Text>
      </View>
    );
  }

  if (!slip) {
    return (
      <View style={{ flex: 1, backgroundColor: '#F8FAFC', alignItems: 'center', justifyContent: 'center' }}>
        <Text style={{ fontSize: 40, marginBottom: 12 }}>📋</Text>
        <Text style={{ color: '#1E293B', fontWeight: '700', fontSize: 16 }}>Slip not found</Text>
        <TouchableOpacity onPress={() => router.back()} style={{ marginTop: 16 }}>
          <Text style={{ color: '#0038A8', fontWeight: '600' }}>← Go back</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const statusStyle = slipStatusStyle(slip.status || '');
  const docs = slip.documents ?? [];
  const slipLabel = slip.slip_id || slip.id?.slice(0, 8).toUpperCase() || 'Routing Slip';

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* Header */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
        <TouchableOpacity
          onPress={() => router.back()}
          style={{ marginBottom: 14, flexDirection: 'row', alignItems: 'center', gap: 6 }}
        >
          <ArrowLeft size={18} color="#93C5FD" />
          <Text style={{ color: '#93C5FD', fontSize: 14, fontWeight: '600' }}>Routing Slips</Text>
        </TouchableOpacity>

        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <FileText size={18} color="#fff" />
              <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800', letterSpacing: -0.3 }}>
                {slipLabel}
              </Text>
            </View>
            <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 13 }}>
              {docs.length} document{docs.length !== 1 ? 's' : ''} in this slip
            </Text>
          </View>

          {/* Status badge */}
          <View style={{ backgroundColor: statusStyle.bg, borderRadius: 20, paddingHorizontal: 14, paddingVertical: 6 }}>
            <Text style={{ color: statusStyle.text, fontWeight: '800', fontSize: 12 }}>
              {(slip.status || 'Unknown').toUpperCase()}
            </Text>
          </View>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>

        {/* ── Slip Info Card ──────────────────────────────────────────────── */}
        <View style={{
          backgroundColor: '#fff', borderRadius: 14, padding: 16,
          marginBottom: 12, borderWidth: 0.5, borderColor: '#E2E8F0',
        }}>
          <Text style={{
            fontWeight: '800', color: '#0038A8', fontSize: 12,
            textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 14,
          }}>
            Slip Details
          </Text>

          {[
            { icon: <MapPin size={14} color="#94A3B8" />, label: 'From', value: slip.from_office },
            { icon: <MapPin size={14} color="#94A3B8" />, label: 'To', value: slip.to_office },
            { icon: <User size={14} color="#94A3B8" />, label: 'Routed By', value: slip.routed_by || slip.created_by },
            { icon: <Calendar size={14} color="#94A3B8" />, label: 'Date', value: formatDate(slip.created_at || slip.routed_at) },
          ].map(({ icon, label, value }) =>
            value ? (
              <View key={label} style={{
                flexDirection: 'row', alignItems: 'center', gap: 10,
                paddingVertical: 8, borderBottomWidth: 0.5, borderBottomColor: '#F1F5F9',
              }}>
                {icon}
                <Text style={{ color: '#94A3B8', fontSize: 13, width: 80 }}>{label}</Text>
                <Text style={{ color: '#1E293B', fontSize: 13, fontWeight: '600', flex: 1 }}>{value}</Text>
              </View>
            ) : null,
          )}

          {slip.remarks ? (
            <View style={{ marginTop: 10 }}>
              <Text style={{ color: '#64748B', fontSize: 13, fontStyle: 'italic', lineHeight: 19 }}>
                "{slip.remarks}"
              </Text>
            </View>
          ) : null}
        </View>

        {/* ── Documents in slip ───────────────────────────────────────────── */}
        <Text style={{
          fontWeight: '800', color: '#475569', fontSize: 12,
          textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 10,
        }}>
          Documents ({docs.length})
        </Text>

        {docs.length === 0 ? (
          <View style={{
            backgroundColor: '#fff', borderRadius: 14, padding: 24,
            alignItems: 'center', borderWidth: 0.5, borderColor: '#E2E8F0', marginBottom: 12,
          }}>
            <Text style={{ color: '#94A3B8', fontSize: 13 }}>No documents found in this slip.</Text>
          </View>
        ) : (
          docs.map((doc) => {
            const statusColor = DOC_STATUS_COLORS[doc.status || ''] ?? '#94A3B8';
            return (
              <TouchableOpacity
                key={doc.id}
                onPress={() => router.push(`/(app)/documents/${doc.id}`)}
                activeOpacity={0.75}
                style={{
                  backgroundColor: '#fff', borderRadius: 14, padding: 14,
                  marginBottom: 10, borderWidth: 0.5, borderColor: '#E2E8F0',
                  flexDirection: 'row', alignItems: 'center', gap: 12,
                }}
              >
                {/* Status dot */}
                <View style={{
                  width: 10, height: 10, borderRadius: 5,
                  backgroundColor: statusColor, flexShrink: 0,
                }} />

                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: '700', color: '#1E293B', fontSize: 13.5, marginBottom: 3 }}>
                    {doc.doc_name || 'Untitled'}
                  </Text>
                  <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                    {doc.doc_id && (
                      <Text style={{ fontSize: 11, color: '#94A3B8', fontWeight: '600' }}>
                        #{doc.doc_id}
                      </Text>
                    )}
                    {doc.category && (
                      <Text style={{ fontSize: 11, color: '#94A3B8' }}>{doc.category}</Text>
                    )}
                  </View>
                </View>

                {/* Status badge */}
                <View style={{
                  backgroundColor: '#F1F5F9', borderRadius: 20,
                  paddingHorizontal: 10, paddingVertical: 4,
                }}>
                  <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569' }}>
                    {doc.status || '—'}
                  </Text>
                </View>

                <Text style={{ color: '#CBD5E1', fontSize: 18 }}>›</Text>
              </TouchableOpacity>
            );
          })
        )}

        {/* ── Actions ──────────────────────────────────────────────────────── */}
        {canAct && slip.status?.toLowerCase() !== 'archived' && (
          <>
            {/* Reroute */}
            <TouchableOpacity
              onPress={() => setRerouteModal(true)}
              activeOpacity={0.8}
              style={{
                backgroundColor: '#EFF6FF', borderRadius: 14, padding: 16,
                marginTop: 4, marginBottom: 10,
                borderWidth: 1, borderColor: '#BFDBFE',
                flexDirection: 'row', alignItems: 'center', gap: 12,
              }}
            >
              <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: '#0038A8', alignItems: 'center', justifyContent: 'center' }}>
                <RefreshCw size={18} color="#fff" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontWeight: '800', color: '#1E3A5F', fontSize: 14 }}>Reroute Slip</Text>
                <Text style={{ color: '#3B82F6', fontSize: 12.5, marginTop: 2 }}>
                  Change destination and create new slip
                </Text>
              </View>
              <Text style={{ color: '#93C5FD', fontSize: 20 }}>›</Text>
            </TouchableOpacity>

            {/* Batch Status Update */}
            <TouchableOpacity
              onPress={() => setBatchModal(true)}
              activeOpacity={0.8}
              style={{
                backgroundColor: '#FFFBEB', borderRadius: 14, padding: 16,
                marginBottom: 10,
                borderWidth: 1, borderColor: '#FDE68A',
                flexDirection: 'row', alignItems: 'center', gap: 12,
              }}
            >
              <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: '#D97706', alignItems: 'center', justifyContent: 'center' }}>
                <ListChecks size={18} color="#fff" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontWeight: '800', color: '#78350F', fontSize: 14 }}>Batch Update Status</Text>
                <Text style={{ color: '#B45309', fontSize: 12.5, marginTop: 2 }}>
                  Set the same status on all {docs.length} document{docs.length !== 1 ? 's' : ''}
                </Text>
              </View>
              <Text style={{ color: '#FCD34D', fontSize: 20 }}>›</Text>
            </TouchableOpacity>

            {/* Archive */}
            {canAct && (
              <TouchableOpacity
                onPress={handleArchive}
                disabled={archiveMutation.isPending}
                activeOpacity={0.8}
                style={{
                  backgroundColor: '#F8FAFC', borderRadius: 14, padding: 16,
                  marginBottom: 12,
                  borderWidth: 1, borderColor: '#E2E8F0',
                  flexDirection: 'row', alignItems: 'center', gap: 12,
                }}
              >
                <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: '#475569', alignItems: 'center', justifyContent: 'center' }}>
                  {archiveMutation.isPending
                    ? <ActivityIndicator size="small" color="#fff" />
                    : <Archive size={18} color="#fff" />}
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: '800', color: '#334155', fontSize: 14 }}>Archive Slip</Text>
                  <Text style={{ color: '#64748B', fontSize: 12.5, marginTop: 2 }}>
                    Move to archive — removes from active view
                  </Text>
                </View>
              </TouchableOpacity>
            )}
          </>
        )}

      </ScrollView>

      {/* ── Reroute Modal ─────────────────────────────────────────────────── */}
      <Modal visible={rerouteModal} transparent animationType="slide" onRequestClose={() => setRerouteModal(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
            <TouchableOpacity style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }} onPress={() => setRerouteModal(false)} activeOpacity={1} />
            <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: '80%' }}>
              <View style={{ backgroundColor: '#0038A8', borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingTop: 20, paddingBottom: 16, paddingHorizontal: 20 }}>
                <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.30)', alignSelf: 'center', marginBottom: 12 }} />
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={{ fontSize: 17, fontWeight: '800', color: '#fff' }}>Reroute Slip</Text>
                  <TouchableOpacity onPress={() => setRerouteModal(false)} style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' }}>
                    <X size={16} color="#fff" />
                  </TouchableOpacity>
                </View>
                <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 12, marginTop: 4 }}>
                  This will archive slip {slipLabel} and create a new one.
                </Text>
              </View>
              <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 8 }} keyboardShouldPersistTaps="handled">
                <Text style={{ fontSize: 11, fontWeight: '700', color: '#0038A8', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
                  New Destination <Text style={{ color: '#EF4444' }}>*</Text>
                </Text>
                <SelectField
                  value={rerouteDest}
                  onChange={setRerouteDest}
                  options={officeNames}
                  placeholder="Select new destination…"
                  label="Destination"
                  allowFreeText
                  disabled={rerouteMutation.isPending}
                />
                <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6, marginTop: 4 }}>
                  Notes <Text style={{ color: '#94A3B8', fontWeight: '400', textTransform: 'none' }}>(optional)</Text>
                </Text>
                <TextInput
                  value={rerouteNotes}
                  onChangeText={setRerouteNotes}
                  placeholder="Reason for rerouting…"
                  placeholderTextColor="#CBD5E1"
                  multiline
                  editable={!rerouteMutation.isPending}
                  style={{ backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: '#E2E8F0', paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, color: '#1E293B', height: 80, textAlignVertical: 'top', marginBottom: 16 }}
                />
              </ScrollView>
              <View style={{ padding: 16, paddingBottom: Platform.OS === 'ios' ? 32 : 20, borderTopWidth: 0.5, borderTopColor: '#E2E8F0', gap: 10 }}>
                <TouchableOpacity
                  onPress={() => {
                    if (!rerouteDest.trim()) { Alert.alert('Required', 'Please select a new destination.'); return; }
                    rerouteMutation.mutate({ destination: rerouteDest, notes: rerouteNotes });
                  }}
                  disabled={rerouteMutation.isPending}
                  style={{ backgroundColor: rerouteMutation.isPending ? '#93C5FD' : '#0038A8', borderRadius: 13, paddingVertical: 15, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8 }}
                >
                  {rerouteMutation.isPending
                    ? <><ActivityIndicator color="#fff" size="small" /><Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>Rerouting…</Text></>
                    : <><RefreshCw size={18} color="#fff" /><Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>Reroute</Text></>}
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setRerouteModal(false)} disabled={rerouteMutation.isPending} style={{ borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 13, paddingVertical: 13, alignItems: 'center', backgroundColor: '#fff' }}>
                  <Text style={{ color: '#64748B', fontSize: 14, fontWeight: '600' }}>Cancel</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* ── Batch Status Modal ────────────────────────────────────────────── */}
      <Modal visible={batchModal} transparent animationType="slide" onRequestClose={() => setBatchModal(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
            <TouchableOpacity style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }} onPress={() => setBatchModal(false)} activeOpacity={1} />
            <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: '80%' }}>
              <View style={{ backgroundColor: '#D97706', borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingTop: 20, paddingBottom: 16, paddingHorizontal: 20 }}>
                <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.30)', alignSelf: 'center', marginBottom: 12 }} />
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={{ fontSize: 17, fontWeight: '800', color: '#fff' }}>Batch Update Status</Text>
                  <TouchableOpacity onPress={() => setBatchModal(false)} style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' }}>
                    <X size={16} color="#fff" />
                  </TouchableOpacity>
                </View>
                <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 12, marginTop: 4 }}>
                  Updates all {docs.length} document{docs.length !== 1 ? 's' : ''} in this slip.
                </Text>
              </View>
              <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 8 }} keyboardShouldPersistTaps="handled">
                <Text style={{ fontSize: 11, fontWeight: '700', color: '#D97706', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 10 }}>
                  New Status <Text style={{ color: '#EF4444' }}>*</Text>
                </Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
                  {STATUS_OPTIONS.map((s) => (
                    <TouchableOpacity
                      key={s}
                      onPress={() => setBatchStatus(s)}
                      style={{
                        paddingHorizontal: 16, paddingVertical: 9, borderRadius: 20,
                        backgroundColor: batchStatus === s ? '#D97706' : '#F1F5F9',
                        borderWidth: batchStatus === s ? 0 : 0.5, borderColor: '#E2E8F0',
                      }}
                    >
                      <Text style={{ color: batchStatus === s ? '#fff' : '#475569', fontWeight: batchStatus === s ? '700' : '500', fontSize: 13 }}>
                        {s}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
                  Remarks <Text style={{ color: '#94A3B8', fontWeight: '400', textTransform: 'none' }}>(optional)</Text>
                </Text>
                <TextInput
                  value={batchRemarks}
                  onChangeText={setBatchRemarks}
                  placeholder="Notes about this status change…"
                  placeholderTextColor="#CBD5E1"
                  multiline
                  editable={!batchStatusMutation.isPending}
                  style={{ backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: '#E2E8F0', paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, color: '#1E293B', height: 80, textAlignVertical: 'top', marginBottom: 16 }}
                />
              </ScrollView>
              <View style={{ padding: 16, paddingBottom: Platform.OS === 'ios' ? 32 : 20, borderTopWidth: 0.5, borderTopColor: '#E2E8F0', gap: 10 }}>
                <TouchableOpacity
                  onPress={() => {
                    if (!batchStatus) { Alert.alert('Required', 'Please select a status.'); return; }
                    batchStatusMutation.mutate({ status: batchStatus, remarks: batchRemarks });
                  }}
                  disabled={batchStatusMutation.isPending}
                  style={{ backgroundColor: batchStatusMutation.isPending ? '#FCD34D' : '#D97706', borderRadius: 13, paddingVertical: 15, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8 }}
                >
                  {batchStatusMutation.isPending
                    ? <><ActivityIndicator color="#fff" size="small" /><Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>Updating…</Text></>
                    : <><ListChecks size={18} color="#fff" /><Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>Update All</Text></>}
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setBatchModal(false)} disabled={batchStatusMutation.isPending} style={{ borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 13, paddingVertical: 13, alignItems: 'center', backgroundColor: '#fff' }}>
                  <Text style={{ color: '#64748B', fontSize: 14, fontWeight: '600' }}>Cancel</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

    </View>
  );
}
