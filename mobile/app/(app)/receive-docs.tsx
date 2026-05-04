import { useState } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, Alert,
  ActivityIndicator, StatusBar, TextInput, Modal,
  RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, CheckCircle, XCircle, Inbox, Clock,
} from 'lucide-react-native';
import api from '../../lib/api';
import { useAuthStore } from '../../lib/store';

type PendingDoc = {
  id: string;
  doc_id?: string;
  doc_name?: string;
  from_office?: string;
  sender_name?: string;
  referred_to?: string;
  category?: string;
  status?: string;
  pending_at_staff?: string;
  pending_at_office?: string;
  updated_at?: string;
  updated_by?: string;
  travel_log?: { officer?: string; office?: string; timestamp?: string; action?: string }[];
};

function formatDate(ts?: string) {
  if (!ts) return '—';
  return ts.replace('T', ' ').slice(0, 16);
}

function lastTransferEntry(doc: PendingDoc) {
  const log = doc.travel_log ?? [];
  return [...log].reverse().find((e) => e.action?.toLowerCase().includes('transfer'));
}

export default function ReceiveDocs() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();

  const [rejectTarget, setRejectTarget] = useState<PendingDoc | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  // ── Data ──────────────────────────────────────────────────────────────────

  const { data: docs = [], isLoading, refetch, isRefetching } = useQuery<PendingDoc[]>({
    queryKey: ['pending-documents'],
    queryFn: async () => {
      const res = await api.get('/pending-documents');
      return res.data ?? [];
    },
    retry: false,
  });

  // ── Mutations ─────────────────────────────────────────────────────────────

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['pending-documents'] });
    queryClient.invalidateQueries({ queryKey: ['pending-count'] });
    queryClient.invalidateQueries({ queryKey: ['documents'] });
    queryClient.invalidateQueries({ queryKey: ['stats'] });
  };

  const acceptMutation = useMutation({
    mutationFn: (docId: string) => api.post(`/documents/${docId}/accept`),
    onSuccess: () => {
      invalidate();
      Alert.alert('Accepted', 'Document accepted and marked as Received.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to accept.'),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ docId, reason }: { docId: string; reason: string }) =>
      api.post(`/documents/${docId}/reject`, { reason }),
    onSuccess: () => {
      invalidate();
      setRejectTarget(null);
      setRejectReason('');
      Alert.alert('Rejected', 'Document returned to sender.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to reject.'),
  });

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleAccept = (doc: PendingDoc) => {
    Alert.alert(
      'Accept Document',
      `Mark "${doc.doc_name || doc.doc_id}" as received?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Accept', onPress: () => acceptMutation.mutate(doc.id) },
      ],
    );
  };

  const openReject = (doc: PendingDoc) => {
    setRejectTarget(doc);
    setRejectReason('');
  };

  const confirmReject = () => {
    if (!rejectTarget) return;
    if (!rejectReason.trim()) {
      Alert.alert('Required', 'Please provide a rejection reason.');
      return;
    }
    rejectMutation.mutate({ docId: rejectTarget.id, reason: rejectReason.trim() });
  };

  // ── Render item ───────────────────────────────────────────────────────────

  const renderDoc = ({ item: doc }: { item: PendingDoc }) => {
    const transfer = lastTransferEntry(doc);
    const isBusy = acceptMutation.isPending || rejectMutation.isPending;

    return (
      <View style={{
        backgroundColor: '#fff',
        borderRadius: 14,
        padding: 16,
        marginBottom: 12,
        borderWidth: 1,
        borderColor: '#FED7AA',
        borderLeftWidth: 4,
        borderLeftColor: '#F97316',
      }}>
        {/* Doc name + ref */}
        <View style={{ marginBottom: 10 }}>
          <Text style={{ fontSize: 14.5, fontWeight: '700', color: '#1E293B', marginBottom: 3 }} numberOfLines={2}>
            {doc.doc_name || 'Untitled Document'}
          </Text>
          {doc.doc_id && (
            <Text style={{ fontSize: 12, color: '#94A3B8' }}>#{doc.doc_id}</Text>
          )}
        </View>

        {/* Meta */}
        <View style={{ gap: 4, marginBottom: 12 }}>
          {doc.from_office ? (
            <Text style={{ fontSize: 12.5, color: '#475569' }}>
              <Text style={{ color: '#94A3B8' }}>From: </Text>{doc.from_office}
            </Text>
          ) : null}
          {doc.category ? (
            <Text style={{ fontSize: 12.5, color: '#475569' }}>
              <Text style={{ color: '#94A3B8' }}>Type: </Text>{doc.category}
            </Text>
          ) : null}
          {transfer ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 2 }}>
              <Clock size={11} color="#F97316" />
              <Text style={{ fontSize: 11.5, color: '#EA580C' }}>
                Transferred by {transfer.officer || doc.updated_by || '—'} · {formatDate(transfer.timestamp)}
              </Text>
            </View>
          ) : null}
          {doc.pending_at_staff && doc.pending_at_staff !== user?.username ? (
            <Text style={{ fontSize: 11.5, color: '#64748B' }}>
              <Text style={{ color: '#94A3B8' }}>For: </Text>{doc.pending_at_staff}
            </Text>
          ) : null}
          {doc.pending_at_office && !doc.pending_at_staff ? (
            <Text style={{ fontSize: 11.5, color: '#64748B' }}>
              <Text style={{ color: '#94A3B8' }}>For office: </Text>{doc.pending_at_office}
            </Text>
          ) : null}
        </View>

        {/* Actions */}
        <View style={{ flexDirection: 'row', gap: 10 }}>
          <TouchableOpacity
            onPress={() => handleAccept(doc)}
            disabled={isBusy}
            style={{
              flex: 1, backgroundColor: '#10B981', borderRadius: 10,
              paddingVertical: 11, alignItems: 'center',
              flexDirection: 'row', justifyContent: 'center', gap: 6,
              opacity: isBusy ? 0.6 : 1,
            }}
          >
            <CheckCircle size={15} color="#fff" />
            <Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>Accept</Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => openReject(doc)}
            disabled={isBusy}
            style={{
              flex: 1, backgroundColor: '#EF4444', borderRadius: 10,
              paddingVertical: 11, alignItems: 'center',
              flexDirection: 'row', justifyContent: 'center', gap: 6,
              opacity: isBusy ? 0.6 : 1,
            }}
          >
            <XCircle size={15} color="#fff" />
            <Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>Reject</Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => router.push(`/(app)/documents/${doc.id}`)}
            style={{
              backgroundColor: '#F1F5F9', borderRadius: 10,
              paddingVertical: 11, paddingHorizontal: 14,
              alignItems: 'center', justifyContent: 'center',
            }}
          >
            <Text style={{ color: '#64748B', fontSize: 12, fontWeight: '600' }}>View</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* Header */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
        <TouchableOpacity onPress={() => router.back()} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 14 }}>
          <ArrowLeft size={18} color="#93C5FD" />
          <Text style={{ color: '#93C5FD', fontSize: 14, fontWeight: '600' }}>Back</Text>
        </TouchableOpacity>

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Inbox size={22} color="#fff" />
          <View>
            <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800' }}>Receive Documents</Text>
            <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 12, marginTop: 2 }}>
              {docs.length > 0
                ? `${docs.length} document${docs.length !== 1 ? 's' : ''} awaiting acceptance`
                : 'No pending transfers'}
            </Text>
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
          data={docs}
          keyExtractor={(d) => d.id}
          renderItem={renderDoc}
          contentContainerStyle={{ padding: 16, paddingBottom: 100 }}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#0038A8" />
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 80 }}>
              <View style={{
                width: 72, height: 72, borderRadius: 36,
                backgroundColor: '#EFF6FF', alignItems: 'center', justifyContent: 'center',
                marginBottom: 16,
              }}>
                <Inbox size={32} color="#BFDBFE" />
              </View>
              <Text style={{ color: '#1E293B', fontSize: 16, fontWeight: '700', marginBottom: 6 }}>
                All caught up!
              </Text>
              <Text style={{ color: '#94A3B8', fontSize: 13.5, textAlign: 'center', maxWidth: 260 }}>
                No documents are pending your acceptance right now.
              </Text>
            </View>
          }
        />
      )}

      {/* ── Reject Reason Modal ──────────────────────────────────────────── */}
      <Modal visible={!!rejectTarget} transparent animationType="fade" onRequestClose={() => setRejectTarget(null)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
          <TouchableOpacity style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }} onPress={() => setRejectTarget(null)} activeOpacity={1} />
          <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, paddingBottom: 40 }}>
            <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: '#CBD5E1', alignSelf: 'center', marginBottom: 20 }} />
            <Text style={{ fontSize: 17, fontWeight: '800', color: '#1E293B', marginBottom: 4 }}>Reject Document</Text>
            <Text style={{ color: '#64748B', fontSize: 13, marginBottom: 20 }} numberOfLines={1}>
              "{rejectTarget?.doc_name || rejectTarget?.doc_id}"
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
                fontSize: 14, color: '#1E293B',
                height: 100, textAlignVertical: 'top', marginBottom: 20,
              }}
            />
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity
                onPress={() => setRejectTarget(null)}
                style={{ flex: 1, borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 12, paddingVertical: 13, alignItems: 'center', backgroundColor: '#fff' }}
              >
                <Text style={{ color: '#64748B', fontWeight: '600', fontSize: 14 }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={confirmReject}
                disabled={rejectMutation.isPending || !rejectReason.trim()}
                style={{
                  flex: 1,
                  backgroundColor: rejectReason.trim() ? '#EF4444' : '#FCA5A5',
                  borderRadius: 12, paddingVertical: 13, alignItems: 'center',
                }}
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
    </View>
  );
}
