import { useState, useCallback } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, TextInput,
  ActivityIndicator, StatusBar, RefreshControl, Alert,
} from 'react-native';
import { offlineQueue, QueuedSubmission } from '../../lib/offlineQueue';
import { useRouter } from 'expo-router';
import { useFocusEffect } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Search, FileText, Clock, Trash2, QrCode } from 'lucide-react-native';
import api from '../../lib/api';
import { useAuthStore } from '../../lib/store';
import { authStorage } from '../../lib/auth';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';

const STATUS_CONFIG: Record<string, { bg: string; text: string; accent: string }> = {
  pending:     { bg: '#FEF3C7', text: '#B45309',  accent: '#F59E0B' },
  received:    { bg: '#DBEAFE', text: '#1E40AF',  accent: '#3B82F6' },
  released:    { bg: '#D1FAE5', text: '#065F46',  accent: '#10B981' },
  routed:      { bg: '#EDE9FE', text: '#5B21B6',  accent: '#8B5CF6' },
  'in review': { bg: '#E0E7FF', text: '#3730A3',  accent: '#6366F1' },
  'on hold':   { bg: '#FEE2E2', text: '#991B1B',  accent: '#EF4444' },
  rejected:    { bg: '#FEE2E2', text: '#991B1B',  accent: '#EF4444' },
};
function getStatus(s: string) {
  return STATUS_CONFIG[s?.toLowerCase()] ?? { bg: '#F1F5F9', text: '#475569', accent: '#94A3B8' };
}

const STATUS_FILTERS = ['All', 'Pending', 'Received', 'Released', 'Routed', 'On Hold', 'Rejected', 'In Review', 'Transferred', 'Returned'];

type Doc = {
  id: string;
  doc_id?: string;
  doc_name?: string;
  status?: string;
  category?: string;
  created_at?: string;
  remarks?: string;
  office_name?: string;
  _isQueued?: boolean;
};

export default function MyDocs() {
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const queryClient = useQueryClient();

  const [search, setSearch]             = useState('');
  const [searchInput, setSearchInput]   = useState('');
  const [activeFilter, setActiveFilter] = useState('All');

  // Which doc is pending confirmation for deletion
  const [pendingDelete, setPendingDelete] = useState<Doc | null>(null);

  const { data, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['client-docs', search, activeFilter],
    queryFn: async () => {
      const params: any = {};
      if (search) params.search = search;
      if (activeFilter !== 'All') params.status = activeFilter;
      const res = await api.get('/client/documents', { params });
      return (res.data?.documents ?? []) as Doc[];
    },
    staleTime: 1000 * 30,
  });

  const docs = data ?? [];

  // ── Offline queue overlay ──────────────────────────────────────────────────
  // Reactive: invalidated by _layout.tsx after each queue item syncs, so the
  // amber "Queued" cards disappear the moment the server confirms success.
  const { data: queueItems = [] } = useQuery<QueuedSubmission[]>({
    queryKey: ['offline-queue'],
    queryFn:  () => offlineQueue.getAll(),
    staleTime: 0,
    refetchOnMount: true,
    refetchOnWindowFocus: true,
  });

  const queuedDocs: Doc[] = queueItems.map((item) => ({
    id:          item.queueId,
    doc_id:      'Pending Sync',
    doc_name:    item.payload.items[0]?.doc_name ?? 'Queued Document',
    status:      'Queued',
    created_at:  new Date(item.queuedAt).toISOString(),
    category:    item.payload.items[0]?.category ?? '',
    office_name: item.payload.office_name,
    _isQueued:   true,
  }));

  const combinedDocs = [...queuedDocs, ...docs];

  // Stats computed from full (unfiltered) list
  const { data: allDocs = [], refetch: refetchAll } = useQuery({
    queryKey: ['client-docs-all'],
    queryFn: async () => {
      const res = await api.get('/client/documents');
      return (res.data?.documents ?? []) as Doc[];
    },
    staleTime: 1000 * 30,
  });

  useFocusEffect(
    useCallback(() => {
      refetchAll();
      queryClient.invalidateQueries({ queryKey: ['offline-queue'] });
    }, [refetchAll, queryClient])
  );

  const statTotal    = allDocs.length;
  const statPending  = allDocs.filter((d) => d.status?.toLowerCase() === 'pending').length;
  const statReceived = allDocs.filter((d) => d.status?.toLowerCase() === 'received').length;
  const statReleased = allDocs.filter((d) => d.status?.toLowerCase() === 'released').length;

  // ── Delete / cancel mutation ──────────────────────────────────────────────
  const deleteMutation = useMutation({
    mutationFn: (docId: string) => api.delete(`/client/documents/${docId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['client-docs'] });
      queryClient.invalidateQueries({ queryKey: ['client-docs-all'] });
      setPendingDelete(null);
    },
    onError: (e: any) => {
      Alert.alert('Error', e?.response?.data?.error || 'Failed to remove document.');
      setPendingDelete(null);
    },
  });

  const handleLogout = async () => {
    Alert.alert('Logout', 'Are you sure you want to logout?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Logout', style: 'destructive',
        onPress: async () => {
          await authStorage.clearAll();
          logout();
          queryClient.clear();
          router.replace('/(auth)/login');
        },
      },
    ]);
  };

  // ── List item ─────────────────────────────────────────────────────────────
  const renderItem = ({ item }: { item: Doc }) => {
    // ── Offline-queued row (not yet on server) ──────────────────────────────
    if (item._isQueued) {
      return (
        <View
          style={{
            backgroundColor: '#FFFBEB', borderRadius: 14, padding: 16,
            marginBottom: 10, borderWidth: 1, borderColor: '#FDE68A',
            flexDirection: 'row', alignItems: 'center', gap: 12,
          }}
        >
          {/* Amber left accent bar */}
          <View style={{ width: 3, height: 52, borderRadius: 2, backgroundColor: '#F59E0B' }} />
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
              <Text style={{ fontWeight: '800', color: '#92400E', fontSize: 13 }}>
                Pending Sync
              </Text>
              <View style={{ backgroundColor: '#FEF3C7', borderRadius: 20, paddingHorizontal: 9, paddingVertical: 3 }}>
                <Text style={{ color: '#B45309', fontSize: 11, fontWeight: '700' }}>⏳ Queued</Text>
              </View>
            </View>
            <Text style={{ color: '#334155', fontSize: 13, marginBottom: 3 }} numberOfLines={2}>
              {item.doc_name}
            </Text>
            <Text style={{ color: '#B45309', fontSize: 11, fontStyle: 'italic', marginBottom: 4 }}>
              Waiting to sync when you reconnect
            </Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <Clock size={11} color="#94A3B8" />
              <Text style={{ color: '#94A3B8', fontSize: 11 }}>
                {item.created_at?.slice(0, 10) || '—'}
              </Text>
              {item.category ? (
                <Text style={{ color: '#CBD5E1', fontSize: 11 }}> · {item.category}</Text>
              ) : null}
            </View>
          </View>
        </View>
      );
    }

    // ── Normal server doc row ───────────────────────────────────────────────
    const s          = getStatus(item.status ?? '');
    const docStatus  = (item.status || '').toLowerCase();
    const isPending  = docStatus === 'pending';
    const isRejected = docStatus === 'rejected';
    const canDelete  = isPending || isRejected;

    return (
      <TouchableOpacity
        onPress={() => router.push(`/(client)/track/${item.id}` as any)}
        activeOpacity={0.75}
        style={{
          backgroundColor: '#fff', borderRadius: 14, padding: 16,
          marginBottom: 10, borderWidth: 0.5, borderColor: '#E2E8F0',
          flexDirection: 'row', alignItems: 'center', gap: 12,
        }}
      >
        {/* Left accent bar */}
        <View style={{ width: 3, height: 44, borderRadius: 2, backgroundColor: s.accent, opacity: 0.7 }} />

        {/* Content */}
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
            <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 13 }}>
              {item.doc_id || item.id?.slice(0, 8).toUpperCase()}
            </Text>
            <View style={{ backgroundColor: s.bg, borderRadius: 20, paddingHorizontal: 9, paddingVertical: 3 }}>
              <Text style={{ color: s.text, fontSize: 11, fontWeight: '700' }}>{item.status || 'Pending'}</Text>
            </View>
          </View>
          <Text style={{ color: '#334155', fontSize: 13, marginBottom: 4 }} numberOfLines={2}>
            {item.doc_name || 'Untitled'}
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Clock size={11} color="#94A3B8" />
            <Text style={{ color: '#94A3B8', fontSize: 11 }}>
              {item.created_at?.slice(0, 10) || '—'}
            </Text>
            {item.category ? (
              <Text style={{ color: '#CBD5E1', fontSize: 11 }}> · {item.category}</Text>
            ) : null}
          </View>
        </View>

        {/* Delete / cancel quick-action */}
        {canDelete && (
          <TouchableOpacity
            onPress={(e) => {
              e.stopPropagation();
              setPendingDelete(item);
            }}
            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
            style={{
              width: 34, height: 34, borderRadius: 10,
              alignItems: 'center', justifyContent: 'center',
              backgroundColor: isPending ? '#FFF7ED' : '#FEF2F2',
              borderWidth: 1,
              borderColor: isPending ? '#FED7AA' : '#FECACA',
            }}
          >
            <Trash2 size={15} color={isPending ? '#EA580C' : '#DC2626'} />
          </TouchableOpacity>
        )}
      </TouchableOpacity>
    );
  };

  // Dialog values derived from the doc being confirmed
  const dialogIsPending = (pendingDelete?.status || '').toLowerCase() === 'pending';

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC', paddingBottom: 100 }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* Header */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20, overflow: 'hidden' }}>
        <View style={{ position: 'absolute', top: -40, right: -40, width: 130, height: 130, borderRadius: 65, backgroundColor: '#FCD116', opacity: 0.10 }} />
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>My Documents</Text>
          <TouchableOpacity onPress={handleLogout}>
            <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 13, fontWeight: '600' }}>Logout</Text>
          </TouchableOpacity>
        </View>
        <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 13, marginBottom: 14 }}>
          Welcome, {user?.full_name || user?.username}
        </Text>

        {/* Stats row */}
        {statTotal > 0 && (
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 14 }}>
            {[
              { label: 'Total',    value: statTotal,    bg: 'rgba(255,255,255,0.20)', text: '#fff' },
              { label: 'Pending',  value: statPending,  bg: 'rgba(251,191,36,0.25)', text: '#FDE68A' },
              { label: 'Received', value: statReceived, bg: 'rgba(59,130,246,0.25)', text: '#BFDBFE' },
              { label: 'Released', value: statReleased, bg: 'rgba(16,185,129,0.25)', text: '#A7F3D0' },
            ].map((s) => (
              <View key={s.label} style={{
                flex: 1, backgroundColor: s.bg, borderRadius: 10,
                paddingVertical: 8, alignItems: 'center',
              }}>
                <Text style={{ color: s.text, fontWeight: '900', fontSize: 18 }}>{s.value}</Text>
                <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 10, fontWeight: '600' }}>{s.label}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Search */}
        <View style={{
          flexDirection: 'row', alignItems: 'center', gap: 10,
          backgroundColor: 'rgba(255,255,255,0.15)',
          borderRadius: 13, paddingHorizontal: 14, paddingVertical: 2,
          borderWidth: 1, borderColor: 'rgba(255,255,255,0.20)',
        }}>
          <Search size={16} color="rgba(255,255,255,0.60)" />
          <TextInput
            value={searchInput}
            onChangeText={setSearchInput}
            onSubmitEditing={() => setSearch(searchInput)}
            returnKeyType="search"
            placeholder="Search your documents…"
            placeholderTextColor="rgba(255,255,255,0.45)"
            style={{ flex: 1, paddingVertical: 11, color: '#fff', fontSize: 14 }}
          />
          <TouchableOpacity
            onPress={() => setSearch(searchInput)}
            style={{ backgroundColor: '#fff', borderRadius: 9, paddingHorizontal: 14, paddingVertical: 7 }}
          >
            <Text style={{ color: '#0038A8', fontWeight: '700', fontSize: 13 }}>Search</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Show My QR — prominent entry point to the counter QR screen */}
      <View style={{ backgroundColor: '#fff', paddingHorizontal: 20, paddingTop: 14, borderBottomWidth: 0.5, borderBottomColor: '#E2E8F0' }}>
        <TouchableOpacity
          onPress={() => router.push('/(client)/my-qr' as any)}
          activeOpacity={0.85}
          style={{
            flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10,
            backgroundColor: '#0038A8', borderRadius: 13, paddingVertical: 15,
          }}
        >
          <QrCode size={20} color="#fff" />
          <Text style={{ color: '#fff', fontWeight: '800', fontSize: 15.5, letterSpacing: 0.2 }}>
            Show My QR Code
          </Text>
        </TouchableOpacity>
      </View>

      {/* Filter pills */}
      <View style={{ backgroundColor: '#fff', borderBottomWidth: 0.5, borderBottomColor: '#E2E8F0' }}>
        <FlatList
          horizontal data={STATUS_FILTERS} keyExtractor={(i) => i}
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ paddingHorizontal: 16, paddingVertical: 10, gap: 8 }}
          renderItem={({ item }) => (
            <TouchableOpacity
              onPress={() => setActiveFilter(item)}
              style={{
                paddingHorizontal: 16, paddingVertical: 6, borderRadius: 20,
                backgroundColor: activeFilter === item ? '#0038A8' : '#F1F5F9',
              }}
            >
              <Text style={{ color: activeFilter === item ? '#fff' : '#64748B', fontWeight: '700', fontSize: 12.5 }}>
                {item}
              </Text>
            </TouchableOpacity>
          )}
        />
      </View>

      {/* Count */}
      <View style={{ paddingHorizontal: 20, paddingTop: 14, paddingBottom: 6 }}>
        <Text style={{ fontSize: 11, fontWeight: '700', color: '#0038A8', textTransform: 'uppercase', letterSpacing: 0.8 }}>
          {isLoading ? 'Loading…' : `${docs.length} document${docs.length !== 1 ? 's' : ''}`}
        </Text>
      </View>

      {/* List */}
      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
        </View>
      ) : (
        <FlatList
          data={combinedDocs} keyExtractor={(d) => d.id} renderItem={renderItem}
          contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: 16 }}
          refreshControl={
            <RefreshControl
              refreshing={isRefetching}
              onRefresh={() => { refetch(); refetchAll(); }}
              tintColor="#0038A8"
            />
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 72 }}>
              <FileText size={48} color="#E2E8F0" />
              <Text style={{ color: '#1E293B', fontSize: 15, fontWeight: '700', marginTop: 14 }}>No documents yet</Text>
              <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 6, textAlign: 'center', paddingHorizontal: 40 }}>
                {search ? 'No matching documents.' : 'Submit your first document using the Submit tab.'}
              </Text>
            </View>
          }
        />
      )}

      {/* ── Confirmation dialog ──────────────────────────────────────────────── */}
      <ConfirmDialog
        visible={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        icon={dialogIsPending ? '⚠️' : '🗑️'}
        accentColor={dialogIsPending ? '#EA580C' : '#DC2626'}
        title={dialogIsPending ? 'Cancel Submission?' : 'Move to Trash?'}
        message={
          dialogIsPending
            ? `"${pendingDelete?.doc_name || 'This document'}" hasn't been received by staff yet. Cancelling will permanently remove it.`
            : `"${pendingDelete?.doc_name || 'This document'}" will be moved to your trash.`
        }
        buttons={[
          {
            label: 'Keep',
            variant: 'ghost',
            onPress: () => {},
          },
          {
            label: dialogIsPending ? 'Yes, Cancel' : 'Move to Trash',
            variant: 'danger',
            onPress: () => pendingDelete && deleteMutation.mutate(pendingDelete.id),
          },
        ]}
      />
    </View>
  );
}
