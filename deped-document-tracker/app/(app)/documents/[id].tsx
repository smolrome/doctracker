import { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Image,
  Modal,
  TextInput,
  StatusBar,
  Platform,
  KeyboardAvoidingView,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, QrCode, Clock, CheckCircle, XCircle,
  AlertCircle, ArrowRightLeft, X,
} from 'lucide-react-native';
import api from '../../../lib/api';
import { useAuthStore } from '../../../lib/store';
import { useStaff, useOffices } from '../../../hooks/useDropdownOptions';
import { SelectField } from '../../../components/ui/SelectField';

// ── Config ────────────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  Pending:     '#F59E0B',
  Received:    '#10B981',
  Released:    '#3B82F6',
  Routed:      '#8B5CF6',
  'In Review': '#6366F1',
  Transferred: '#06B6D4',
  'On Hold':   '#EF4444',
  Returned:    '#DC2626',
};

const STATUS_OPTIONS = [
  'Pending', 'Received', 'Released',
  'Routed', 'In Review', 'Transferred', 'On Hold',
];

function travelColor(action: string) {
  if (action?.includes('Accepted')) return '#10B981';
  if (action?.includes('Rejected')) return '#EF4444';
  if (action?.includes('Released')) return '#3B82F6';
  if (action?.includes('Received')) return '#8B5CF6';
  if (action?.includes('Transfer')) return '#06B6D4';
  return '#0038A8';
}

function formatDate(ts: string | undefined) {
  if (!ts) return '—';
  return ts.replace('T', ' ').slice(0, 16);
}

// ── Fetchers ──────────────────────────────────────────────────────────────────

async function fetchDocument(id: string) {
  const res = await api.get(`/documents/${id}`);
  return res.data;
}

async function fetchQR(id: string) {
  const res = await api.get(`/qr/generate/${id}`);
  return res.data as { qr_base64: string };
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function DocumentDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);

  // Status update modal
  const [statusModal, setStatusModal] = useState(false);
  const [pendingStatus, setPendingStatus] = useState('');
  const [remarksText, setRemarksText] = useState('');

  // Reject modal
  const [rejectModal, setRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  // Transfer modal
  const [transferModal, setTransferModal] = useState(false);
  const [transferMode, setTransferMode] = useState<'staff' | 'office'>('staff');
  const [transferStaff, setTransferStaff] = useState('');       // full_name display
  const [transferOffice, setTransferOffice] = useState('');
  const [transferRemarks, setTransferRemarks] = useState('');

  // ── Data for transfer ─────────────────────────────────────────────────────

  const { data: staffList } = useStaff();
  const { data: offices } = useOffices();

  const staffNames = staffList?.map((s) => s.full_name) ?? [];
  const officeNames = offices?.map((o) => o.office_name) ?? [];

  // ── Queries ───────────────────────────────────────────────────────────────

  const { data: doc, isLoading } = useQuery({
    queryKey: ['document', id],
    queryFn: () => fetchDocument(id),
    enabled: !!id,
  });

  const { data: qrData, isLoading: qrLoading } = useQuery({
    queryKey: ['qr', id],
    queryFn: () => fetchQR(id),
    enabled: !!id && !!doc,
    staleTime: Infinity,
  });

  // ── Mutations ─────────────────────────────────────────────────────────────

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['document', id] });
    queryClient.invalidateQueries({ queryKey: ['documents'] });
    queryClient.invalidateQueries({ queryKey: ['stats'] });
  };

  const statusMutation = useMutation({
    mutationFn: ({ status, remarks }: { status: string; remarks: string }) =>
      api.patch(`/documents/${id}/status`, { status, remarks }),
    onSuccess: () => { invalidate(); Alert.alert('Updated', 'Status updated successfully.'); },
    onError: () => Alert.alert('Error', 'Failed to update status.'),
  });

  const acceptMutation = useMutation({
    mutationFn: () => api.post(`/documents/${id}/accept`),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ['pending-count'] });
      Alert.alert('Accepted', 'Document accepted successfully.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to accept.'),
  });

  const rejectMutation = useMutation({
    mutationFn: (reason: string) => api.post(`/documents/${id}/reject`, { reason }),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ['pending-count'] });
      setRejectModal(false);
      setRejectReason('');
      Alert.alert('Rejected', 'Document returned to sender.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to reject.'),
  });

  const transferMutation = useMutation({
    mutationFn: ({ to_staff, to_office, remarks }: { to_staff: string; to_office: string; remarks: string }) =>
      api.post(`/documents/${id}/transfer`, { to_staff, to_office, remarks }),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ['pending-count'] });
      closeTransferModal();
      Alert.alert('Transferred', 'Document has been routed successfully.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to transfer document.'),
  });

  // ── Handlers ──────────────────────────────────────────────────────────────

  const openStatusModal = (status: string) => {
    setPendingStatus(status);
    setRemarksText('');
    setStatusModal(true);
  };

  const confirmStatusUpdate = () => {
    setStatusModal(false);
    statusMutation.mutate({ status: pendingStatus, remarks: remarksText });
  };

  const handleAccept = () => {
    Alert.alert('Accept Document', 'Mark this document as received?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Accept', onPress: () => acceptMutation.mutate() },
    ]);
  };

  const handleReject = () => {
    if (!rejectReason.trim()) {
      Alert.alert('Required', 'Please provide a rejection reason.');
      return;
    }
    rejectMutation.mutate(rejectReason.trim());
  };

  const closeTransferModal = () => {
    setTransferModal(false);
    setTransferStaff('');
    setTransferOffice('');
    setTransferRemarks('');
    setTransferMode('staff');
  };

  const handleTransfer = () => {
    if (transferMode === 'staff' && !transferStaff.trim()) {
      Alert.alert('Required', 'Please select a staff member.');
      return;
    }
    if (transferMode === 'office' && !transferOffice.trim()) {
      Alert.alert('Required', 'Please select an office.');
      return;
    }

    const staffRecord = staffList?.find((s) => s.full_name === transferStaff);
    const to_staff = transferMode === 'staff' ? (staffRecord?.username || transferStaff) : '';
    const to_office = transferMode === 'office' ? transferOffice : '';

    transferMutation.mutate({ to_staff, to_office, remarks: transferRemarks.trim() });
  };

  // ── Pending transfer authorization ────────────────────────────────────────

  const isTransferPending = doc?.transfer_status === 'pending';
  const canActOnTransfer = isTransferPending && (
    user?.role === 'admin'
    || doc?.pending_at_staff === user?.username
    || (
      !doc?.pending_at_staff
      && doc?.pending_at_office
      && doc.pending_at_office.trim().toLowerCase() === (user?.office || '').trim().toLowerCase()
    )
  );

  const canTransfer = user?.role === 'admin' || user?.role === 'staff';

  // ── Loading / not found ───────────────────────────────────────────────────

  if (isLoading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F8FAFC' }}>
        <ActivityIndicator size="large" color="#0038A8" />
      </View>
    );
  }

  if (!doc) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F8FAFC' }}>
        <Text style={{ color: '#94A3B8', fontSize: 15 }}>Document not found</Text>
      </View>
    );
  }

  const travelLog: any[] = doc.travel_log || [];

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* Header */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
        <TouchableOpacity onPress={() => router.back()} style={{ marginBottom: 14, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <ArrowLeft size={18} color="#93C5FD" />
          <Text style={{ color: '#93C5FD', fontSize: 14, fontWeight: '600' }}>Back</Text>
        </TouchableOpacity>

        <Text style={{ color: '#fff', fontSize: 19, fontWeight: '800', letterSpacing: -0.3, marginBottom: 10 }} numberOfLines={2}>
          {doc.doc_name || doc.description || 'Untitled Document'}
        </Text>

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <View style={{
            backgroundColor: STATUS_COLORS[doc.status] ?? '#9CA3AF',
            borderRadius: 20, paddingHorizontal: 12, paddingVertical: 4,
          }}>
            <Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>{doc.status}</Text>
          </View>
          {doc.doc_id && (
            <Text style={{ color: 'rgba(255,255,255,0.55)', fontSize: 12.5 }}>#{doc.doc_id}</Text>
          )}
          {isTransferPending && (
            <View style={{ backgroundColor: '#F97316', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4 }}>
              <Text style={{ color: '#fff', fontWeight: '700', fontSize: 11 }}>Transfer Pending</Text>
            </View>
          )}
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 120 }} showsVerticalScrollIndicator={false}>

        {/* ── Pending Transfer Action Card ──────────────────────────────── */}
        {canActOnTransfer && (
          <View style={{
            backgroundColor: '#FFF7ED',
            borderRadius: 14,
            padding: 16,
            marginBottom: 12,
            borderWidth: 1.5,
            borderColor: '#FED7AA',
          }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <AlertCircle size={18} color="#EA580C" />
              <Text style={{ fontWeight: '800', color: '#EA580C', fontSize: 15 }}>Action Required</Text>
            </View>
            <Text style={{ color: '#92400E', fontSize: 13, marginBottom: 14, lineHeight: 19 }}>
              This document has been transferred to you and is awaiting your acceptance.
            </Text>
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity
                onPress={handleAccept}
                disabled={acceptMutation.isPending}
                style={{
                  flex: 1, backgroundColor: '#10B981', borderRadius: 10,
                  paddingVertical: 11, alignItems: 'center', flexDirection: 'row',
                  justifyContent: 'center', gap: 6,
                }}
              >
                {acceptMutation.isPending
                  ? <ActivityIndicator color="#fff" size="small" />
                  : <><CheckCircle size={16} color="#fff" /><Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>Accept</Text></>
                }
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => { setRejectReason(''); setRejectModal(true); }}
                disabled={rejectMutation.isPending}
                style={{
                  flex: 1, backgroundColor: '#EF4444', borderRadius: 10,
                  paddingVertical: 11, alignItems: 'center', flexDirection: 'row',
                  justifyContent: 'center', gap: 6,
                }}
              >
                <XCircle size={16} color="#fff" />
                <Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>Reject</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* ── Document Info ────────────────────────────────────────────── */}
        <View style={{ backgroundColor: '#fff', borderRadius: 14, padding: 16, marginBottom: 12, borderWidth: 0.5, borderColor: '#E2E8F0' }}>
          <Text style={{ fontWeight: '800', color: '#0038A8', marginBottom: 14, fontSize: 13, textTransform: 'uppercase', letterSpacing: 0.8 }}>
            Document Info
          </Text>
          {([
            ['Reference', doc.doc_id],
            ['Document Name', doc.doc_name],
            ['Category', doc.category],
            ['From Office', doc.from_office],
            ['Sender Name', doc.sender_name],
            ['Referred To', doc.referred_to],
            ['Logged By', doc.logged_by],
            ['Date', doc.doc_date],
            ['Date Received', doc.date_received],
            ['Date Released', doc.date_released],
          ] as [string, string | undefined][]).map(([label, value]) => (
            value ? (
              <View key={label} style={{
                flexDirection: 'row', justifyContent: 'space-between',
                paddingVertical: 7, borderBottomWidth: 0.5, borderBottomColor: '#F1F5F9',
              }}>
                <Text style={{ color: '#64748B', fontSize: 13, flex: 1 }}>{label}</Text>
                <Text style={{ color: '#1E293B', fontSize: 13, fontWeight: '600', maxWidth: '58%', textAlign: 'right' }}>
                  {value}
                </Text>
              </View>
            ) : null
          ))}
        </View>

        {/* ── QR Code ───────────────────────────────────────────────────── */}
        <View style={{ backgroundColor: '#fff', borderRadius: 14, padding: 16, marginBottom: 12, borderWidth: 0.5, borderColor: '#E2E8F0', alignItems: 'center' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 14, alignSelf: 'flex-start' }}>
            <QrCode size={16} color="#0038A8" />
            <Text style={{ fontWeight: '800', color: '#0038A8', fontSize: 13, textTransform: 'uppercase', letterSpacing: 0.8 }}>
              Document QR Code
            </Text>
          </View>
          {qrLoading ? (
            <ActivityIndicator color="#0038A8" style={{ marginVertical: 24 }} />
          ) : qrData?.qr_base64 ? (
            <>
              <Image
                source={{ uri: qrData.qr_base64 }}
                style={{ width: 200, height: 200, borderRadius: 8 }}
                resizeMode="contain"
              />
              <Text style={{ color: '#94A3B8', fontSize: 12, marginTop: 10, textAlign: 'center' }}>
                Scan to look up this document
              </Text>
            </>
          ) : (
            <Text style={{ color: '#94A3B8', fontSize: 13 }}>QR unavailable</Text>
          )}
        </View>

        {/* ── Remarks ───────────────────────────────────────────────────── */}
        {doc.remarks ? (
          <View style={{ backgroundColor: '#fff', borderRadius: 14, padding: 16, marginBottom: 12, borderWidth: 0.5, borderColor: '#E2E8F0' }}>
            <Text style={{ fontWeight: '800', color: '#0038A8', marginBottom: 8, fontSize: 13, textTransform: 'uppercase', letterSpacing: 0.8 }}>
              Remarks
            </Text>
            <Text style={{ color: '#334155', fontSize: 14, lineHeight: 21 }}>{doc.remarks}</Text>
          </View>
        ) : null}

        {/* ── Travel Log ────────────────────────────────────────────────── */}
        {travelLog.length > 0 && (
          <View style={{ backgroundColor: '#fff', borderRadius: 14, padding: 16, marginBottom: 12, borderWidth: 0.5, borderColor: '#E2E8F0' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 16 }}>
              <Clock size={16} color="#0038A8" />
              <Text style={{ fontWeight: '800', color: '#0038A8', fontSize: 13, textTransform: 'uppercase', letterSpacing: 0.8 }}>
                Travel Log
              </Text>
            </View>

            {[...travelLog].reverse().map((entry: any, i: number) => {
              const color = travelColor(entry.action);
              const isLast = i === travelLog.length - 1;
              return (
                <View key={i} style={{ flexDirection: 'row', gap: 12 }}>
                  <View style={{ alignItems: 'center', width: 20 }}>
                    <View style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: color, marginTop: 3 }} />
                    {!isLast && <View style={{ width: 2, flex: 1, backgroundColor: '#E2E8F0', marginVertical: 4 }} />}
                  </View>
                  <View style={{ flex: 1, paddingBottom: isLast ? 0 : 16 }}>
                    <Text style={{ fontWeight: '700', color: '#1E293B', fontSize: 13.5, marginBottom: 2 }}>
                      {entry.action}
                    </Text>
                    <Text style={{ color: '#64748B', fontSize: 12.5, marginBottom: 2 }}>
                      {entry.officer}{entry.office ? ` · ${entry.office}` : ''}
                    </Text>
                    <Text style={{ color: '#94A3B8', fontSize: 11.5, marginBottom: entry.remarks ? 6 : 0 }}>
                      {formatDate(entry.timestamp)}
                    </Text>
                    {entry.remarks ? (
                      <Text style={{ color: '#475569', fontSize: 12.5, lineHeight: 18, fontStyle: 'italic' }}>
                        {entry.remarks}
                      </Text>
                    ) : null}
                  </View>
                </View>
              );
            })}
          </View>
        )}

        {/* ── Transfer Document ─────────────────────────────────────────── */}
        {canTransfer && (
          <TouchableOpacity
            onPress={() => setTransferModal(true)}
            activeOpacity={0.8}
            style={{
              backgroundColor: '#EFF6FF',
              borderRadius: 14,
              padding: 16,
              marginBottom: 12,
              borderWidth: 1,
              borderColor: '#BFDBFE',
              flexDirection: 'row',
              alignItems: 'center',
              gap: 12,
            }}
          >
            <View style={{
              width: 40, height: 40, borderRadius: 20,
              backgroundColor: '#0038A8',
              alignItems: 'center', justifyContent: 'center',
            }}>
              <ArrowRightLeft size={18} color="#fff" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '800', color: '#0038A8', fontSize: 14 }}>Transfer Document</Text>
              <Text style={{ color: '#3B82F6', fontSize: 12.5, marginTop: 2 }}>
                Route to another staff member or office
              </Text>
            </View>
            <Text style={{ color: '#93C5FD', fontSize: 20 }}>›</Text>
          </TouchableOpacity>
        )}

        {/* ── Update Status ─────────────────────────────────────────────── */}
        <View style={{ backgroundColor: '#fff', borderRadius: 14, padding: 16, marginBottom: 24, borderWidth: 0.5, borderColor: '#E2E8F0' }}>
          <Text style={{ fontWeight: '800', color: '#0038A8', marginBottom: 14, fontSize: 13, textTransform: 'uppercase', letterSpacing: 0.8 }}>
            Update Status
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {STATUS_OPTIONS.map((status) => {
              const isActive = doc.status === status;
              return (
                <TouchableOpacity
                  key={status}
                  onPress={() => !isActive && openStatusModal(status)}
                  disabled={isActive || statusMutation.isPending}
                  style={{
                    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20,
                    backgroundColor: isActive ? (STATUS_COLORS[status] ?? '#94A3B8') : '#F1F5F9',
                    opacity: isActive ? 0.7 : 1,
                    borderWidth: isActive ? 0 : 0.5,
                    borderColor: '#E2E8F0',
                  }}
                >
                  <Text style={{
                    color: isActive ? '#fff' : '#334155',
                    fontSize: 13, fontWeight: isActive ? '700' : '500',
                  }}>
                    {status}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

      </ScrollView>

      {/* ── Status Update Modal ────────────────────────────────────────── */}
      <Modal visible={statusModal} transparent animationType="fade" onRequestClose={() => setStatusModal(false)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
          <TouchableOpacity style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }} onPress={() => setStatusModal(false)} activeOpacity={1} />
          <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, paddingBottom: 40 }}>
            <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: '#CBD5E1', alignSelf: 'center', marginBottom: 20 }} />
            <Text style={{ fontSize: 17, fontWeight: '800', color: '#1E293B', marginBottom: 4 }}>Update Status</Text>
            <Text style={{ color: '#64748B', fontSize: 13.5, marginBottom: 20 }}>
              Change to{' '}
              <Text style={{ color: STATUS_COLORS[pendingStatus] ?? '#0038A8', fontWeight: '700' }}>{pendingStatus}</Text>
            </Text>
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 }}>
              Remarks <Text style={{ color: '#94A3B8', fontWeight: '400', textTransform: 'none' }}>(optional)</Text>
            </Text>
            <TextInput
              value={remarksText}
              onChangeText={setRemarksText}
              placeholder="Add a note about this status change…"
              placeholderTextColor="#CBD5E1"
              multiline
              style={{
                backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: '#E2E8F0',
                paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, color: '#1E293B',
                height: 90, textAlignVertical: 'top', marginBottom: 20,
              }}
            />
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity onPress={() => setStatusModal(false)} style={{ flex: 1, borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 12, paddingVertical: 13, alignItems: 'center', backgroundColor: '#fff' }}>
                <Text style={{ color: '#64748B', fontWeight: '600', fontSize: 14 }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={confirmStatusUpdate} style={{ flex: 1, backgroundColor: STATUS_COLORS[pendingStatus] ?? '#0038A8', borderRadius: 12, paddingVertical: 13, alignItems: 'center' }}>
                <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>Confirm</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* ── Reject Reason Modal ────────────────────────────────────────── */}
      <Modal visible={rejectModal} transparent animationType="fade" onRequestClose={() => setRejectModal(false)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
          <TouchableOpacity style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }} onPress={() => setRejectModal(false)} activeOpacity={1} />
          <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, paddingBottom: 40 }}>
            <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: '#CBD5E1', alignSelf: 'center', marginBottom: 20 }} />
            <Text style={{ fontSize: 17, fontWeight: '800', color: '#1E293B', marginBottom: 6 }}>Reject Document</Text>
            <Text style={{ color: '#64748B', fontSize: 13.5, marginBottom: 20 }}>
              Provide a reason — it will be sent back to the original logger.
            </Text>
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#EF4444', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 }}>
              Reason <Text style={{ color: '#EF4444' }}>*</Text>
            </Text>
            <TextInput
              value={rejectReason}
              onChangeText={setRejectReason}
              placeholder="Why is this document being rejected?"
              placeholderTextColor="#CBD5E1"
              multiline
              autoFocus
              style={{
                backgroundColor: '#fff', borderRadius: 12,
                borderWidth: 1.5, borderColor: rejectReason ? '#E2E8F0' : '#FECACA',
                paddingHorizontal: 14, paddingVertical: 12,
                fontSize: 14, color: '#1E293B', height: 100, textAlignVertical: 'top', marginBottom: 20,
              }}
            />
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity onPress={() => setRejectModal(false)} style={{ flex: 1, borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 12, paddingVertical: 13, alignItems: 'center', backgroundColor: '#fff' }}>
                <Text style={{ color: '#64748B', fontWeight: '600', fontSize: 14 }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={handleReject}
                disabled={rejectMutation.isPending || !rejectReason.trim()}
                style={{ flex: 1, backgroundColor: rejectReason.trim() ? '#EF4444' : '#FCA5A5', borderRadius: 12, paddingVertical: 13, alignItems: 'center' }}
              >
                {rejectMutation.isPending
                  ? <ActivityIndicator color="#fff" size="small" />
                  : <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>Reject</Text>
                }
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* ── Transfer Modal ─────────────────────────────────────────────── */}
      <Modal visible={transferModal} animationType="slide" transparent onRequestClose={closeTransferModal}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
            <TouchableOpacity style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }} onPress={closeTransferModal} activeOpacity={1} />

            <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 28, borderTopRightRadius: 28, maxHeight: '88%', overflow: 'hidden' }}>

              {/* Header */}
              <View style={{ backgroundColor: '#0038A8', paddingTop: 20, paddingBottom: 20, paddingHorizontal: 20, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <View style={{ position: 'absolute', top: 10, left: 0, right: 0, alignItems: 'center' }}>
                  <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.30)' }} />
                </View>
                <View>
                  <Text style={{ fontSize: 17, fontWeight: '800', color: '#fff' }}>Transfer Document</Text>
                  <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.60)', marginTop: 2 }}>Route to staff or office</Text>
                </View>
                <TouchableOpacity onPress={closeTransferModal} style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' }}>
                  <X size={18} color="#fff" />
                </TouchableOpacity>
              </View>

              {/* Toggle: Staff vs Office */}
              <View style={{ flexDirection: 'row', margin: 16, marginBottom: 4, backgroundColor: '#E2E8F0', borderRadius: 12, padding: 4 }}>
                {(['staff', 'office'] as const).map((mode) => (
                  <TouchableOpacity
                    key={mode}
                    onPress={() => { setTransferMode(mode); setTransferStaff(''); setTransferOffice(''); }}
                    style={{
                      flex: 1, paddingVertical: 9, borderRadius: 10, alignItems: 'center',
                      backgroundColor: transferMode === mode ? '#0038A8' : 'transparent',
                    }}
                  >
                    <Text style={{ color: transferMode === mode ? '#fff' : '#64748B', fontWeight: '700', fontSize: 13 }}>
                      {mode === 'staff' ? 'To Staff' : 'To Office'}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 8 }} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">

                {transferMode === 'staff' ? (
                  <>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: '#0038A8', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
                      Staff Member <Text style={{ color: '#EF4444' }}>*</Text>
                    </Text>
                    <SelectField
                      value={transferStaff}
                      onChange={setTransferStaff}
                      options={staffNames}
                      placeholder="Select staff member…"
                      label="Staff Member"
                      disabled={transferMutation.isPending}
                      allowFreeText
                    />
                  </>
                ) : (
                  <>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: '#0038A8', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
                      Office / Unit <Text style={{ color: '#EF4444' }}>*</Text>
                    </Text>
                    <SelectField
                      value={transferOffice}
                      onChange={setTransferOffice}
                      options={officeNames}
                      placeholder="Select office…"
                      label="Office / Unit"
                      disabled={transferMutation.isPending}
                    />
                  </>
                )}

                <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
                  Remarks <Text style={{ color: '#94A3B8', fontWeight: '400', textTransform: 'none' }}>(optional)</Text>
                </Text>
                <TextInput
                  value={transferRemarks}
                  onChangeText={setTransferRemarks}
                  placeholder="Add routing notes or instructions…"
                  placeholderTextColor="#CBD5E1"
                  multiline
                  editable={!transferMutation.isPending}
                  style={{
                    backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: '#E2E8F0',
                    paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, color: '#1E293B',
                    height: 80, textAlignVertical: 'top', marginBottom: 16,
                  }}
                />
              </ScrollView>

              {/* Footer */}
              <View style={{ padding: 16, paddingBottom: Platform.OS === 'ios' ? 32 : 20, borderTopWidth: 0.5, borderTopColor: '#E2E8F0', backgroundColor: '#F8FAFC', gap: 10 }}>
                <TouchableOpacity
                  onPress={handleTransfer}
                  disabled={transferMutation.isPending}
                  activeOpacity={0.85}
                  style={{
                    backgroundColor: transferMutation.isPending ? '#93C5FD' : '#0038A8',
                    borderRadius: 13, paddingVertical: 15, alignItems: 'center',
                    flexDirection: 'row', justifyContent: 'center', gap: 8,
                  }}
                >
                  {transferMutation.isPending
                    ? <><ActivityIndicator color="#fff" size="small" /><Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>Transferring...</Text></>
                    : <><ArrowRightLeft size={18} color="#fff" /><Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>Transfer Document</Text></>
                  }
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={closeTransferModal}
                  disabled={transferMutation.isPending}
                  style={{ borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 13, paddingVertical: 13, alignItems: 'center', backgroundColor: '#fff' }}
                >
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
