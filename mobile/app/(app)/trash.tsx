import { useState } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, Alert,
  ActivityIndicator, StatusBar, RefreshControl, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Trash2, RotateCcw, Search, Inbox } from 'lucide-react-native';
import api from '../../lib/api';
import { useAuthStore } from '../../lib/store';

type DeletedDoc = {
  id: string;
  doc_id?: string;
  doc_name?: string;
  category?: string;
  from_office?: string;
  status?: string;
  deleted_by?: string;
  deleted_at?: string;
  logged_by?: string;
};

function formatDate(ts?: string) {
  if (!ts) return '—';
  return ts.replace('T', ' ').slice(0, 16);
}

export default function Trash() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin';

  const [search, setSearch] = useState('');

  // ── Data ──────────────────────────────────────────────────────────────────

  const { data, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['trash'],
    queryFn: async () => {
      const res = await api.get('/trash');
      return (res.data ?? []) as DeletedDoc[];
    },
    staleTime: 1000 * 60,
  });

  const docs = (data ?? []).filter((d) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      d.doc_name?.toLowerCase().includes(q) ||
      d.doc_id?.toLowerCase().includes(q) ||
      d.from_office?.toLowerCase().includes(q) ||
      d.deleted_by?.toLowerCase().includes(q)
    );
  });

  // ── Mutations ─────────────────────────────────────────────────────────────

  const restoreMutation = useMutation({
    mutationFn: (docId: string) => api.post(`/documents/${docId}/restore`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trash'] });
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      Alert.alert('Restored', 'Document has been restored successfully.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to restore.'),
  });

  const permanentDeleteMutation = useMutation({
    mutationFn: (docId: string) => api.delete(`/documents/${docId}/permanent`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trash'] });
      Alert.alert('Deleted', 'Document permanently deleted.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to delete.'),
  });

  const emptyTrashMutation = useMutation({
    mutationFn: () => api.delete('/trash/empty'),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['trash'] });
      Alert.alert('Trash Emptied', res.data?.message || 'All deleted documents have been permanently removed.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to empty trash.'),
  });

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleEmptyTrash = () => {
    const total = data?.length ?? 0;
    if (total === 0) {
      Alert.alert('Trash Empty', 'There are no deleted documents to remove.');
      return;
    }
    Alert.alert(
      '⚠️ Empty All Trash',
      `This will permanently erase ALL ${total} deleted document${total !== 1 ? 's' : ''}. This CANNOT be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Empty Trash',
          style: 'destructive',
          onPress: () => emptyTrashMutation.mutate(),
        },
      ],
    );
  };

  const handleRestore = (doc: DeletedDoc) => {
    Alert.alert(
      'Restore Document',
      `Restore "${doc.doc_name || 'this document'}" back to the active list?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Restore', onPress: () => restoreMutation.mutate(doc.id) },
      ],
    );
  };

  const handlePermanentDelete = (doc: DeletedDoc) => {
    Alert.alert(
      'Permanently Delete',
      `This will permanently erase "${doc.doc_name || 'this document'}" and cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete Forever',
          style: 'destructive',
          onPress: () => permanentDeleteMutation.mutate(doc.id),
        },
      ],
    );
  };

  // ── Render item ───────────────────────────────────────────────────────────

  const renderItem = ({ item }: { item: DeletedDoc }) => (
    <View style={{
      backgroundColor: '#fff',
      borderRadius: 14,
      padding: 16,
      marginBottom: 10,
      borderWidth: 0.5,
      borderColor: '#E2E8F0',
    }}>
      {/* Doc name + ref */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
        <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 14, flex: 1, marginRight: 8 }}>
          {item.doc_name || 'Untitled Document'}
        </Text>
        {item.doc_id && (
          <Text style={{ fontSize: 11, color: '#94A3B8', fontWeight: '600' }}>
            #{item.doc_id}
          </Text>
        )}
      </View>

      {/* Meta */}
      <View style={{ gap: 3, marginBottom: 12 }}>
        {item.from_office && (
          <Text style={{ fontSize: 12, color: '#64748B' }}>
            📁 {item.from_office}
          </Text>
        )}
        {item.category && (
          <Text style={{ fontSize: 12, color: '#64748B' }}>
            🏷️ {item.category}
          </Text>
        )}
        {item.status && (
          <Text style={{ fontSize: 12, color: '#64748B' }}>
            Status when deleted: <Text style={{ fontWeight: '600', color: '#475569' }}>{item.status}</Text>
          </Text>
        )}
        <Text style={{ fontSize: 12, color: '#94A3B8', marginTop: 2 }}>
          🗑️ Deleted by {item.deleted_by || '—'} · {formatDate(item.deleted_at)}
        </Text>
      </View>

      {/* Action buttons */}
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <TouchableOpacity
          onPress={() => handleRestore(item)}
          disabled={restoreMutation.isPending}
          style={{
            flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
            gap: 6, backgroundColor: '#F0FDF4',
            borderRadius: 10, paddingVertical: 10,
            borderWidth: 1, borderColor: '#BBF7D0',
          }}
        >
          <RotateCcw size={15} color="#16A34A" />
          <Text style={{ color: '#16A34A', fontWeight: '700', fontSize: 13 }}>Restore</Text>
        </TouchableOpacity>

        {isAdmin && (
          <TouchableOpacity
            onPress={() => handlePermanentDelete(item)}
            disabled={permanentDeleteMutation.isPending}
            style={{
              flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
              gap: 6, backgroundColor: '#FEF2F2',
              borderRadius: 10, paddingVertical: 10,
              borderWidth: 1, borderColor: '#FECACA',
            }}
          >
            <Trash2 size={15} color="#DC2626" />
            <Text style={{ color: '#DC2626', fontWeight: '700', fontSize: 13 }}>Delete Forever</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );

  // ── Screen ────────────────────────────────────────────────────────────────

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#7F1D1D" />

      {/* Header */}
      <View style={{ backgroundColor: '#991B1B', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
        <TouchableOpacity
          onPress={() => router.back()}
          style={{ marginBottom: 14, flexDirection: 'row', alignItems: 'center', gap: 6 }}
        >
          <ArrowLeft size={18} color="#FCA5A5" />
          <Text style={{ color: '#FCA5A5', fontSize: 14, fontWeight: '600' }}>Back</Text>
        </TouchableOpacity>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Trash2 size={20} color="#fff" />
            <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>Trash</Text>
          </View>
          {isAdmin && (data?.length ?? 0) > 0 && (
            <TouchableOpacity
              onPress={handleEmptyTrash}
              disabled={emptyTrashMutation.isPending}
              style={{
                backgroundColor: 'rgba(255,255,255,0.18)',
                borderRadius: 10, paddingHorizontal: 12, paddingVertical: 7,
                borderWidth: 1, borderColor: 'rgba(255,255,255,0.30)',
              }}
            >
              <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>
                {emptyTrashMutation.isPending ? 'Emptying…' : 'Empty All'}
              </Text>
            </TouchableOpacity>
          )}
        </View>
        <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 13, marginTop: 4 }}>
          {docs.length} deleted document{docs.length !== 1 ? 's' : ''}
        </Text>
      </View>

      {/* Search bar */}
      <View style={{ paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#fff', borderBottomWidth: 0.5, borderBottomColor: '#E2E8F0' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#F1F5F9', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 }}>
          <Search size={16} color="#94A3B8" />
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Search deleted documents…"
            placeholderTextColor="#94A3B8"
            style={{ flex: 1, fontSize: 14, color: '#1E293B' }}
          />
        </View>
      </View>

      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#991B1B" />
          <Text style={{ color: '#94A3B8', marginTop: 12, fontSize: 13 }}>Loading trash…</Text>
        </View>
      ) : (
        <FlatList
          data={docs}
          keyExtractor={(item, i) => item.id || String(i)}
          renderItem={renderItem}
          contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#991B1B" />
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 72 }}>
              <Inbox size={48} color="#E2E8F0" />
              <Text style={{ color: '#1E293B', fontSize: 15, fontWeight: '700', marginTop: 14 }}>
                {search ? 'No results found' : 'Trash is empty'}
              </Text>
              <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 6, textAlign: 'center', paddingHorizontal: 40 }}>
                {search ? 'Try a different search term.' : 'Deleted documents will appear here.'}
              </Text>
            </View>
          }
        />
      )}
    </View>
  );
}
