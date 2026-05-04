import {
  View, Text, FlatList, TouchableOpacity, Alert,
  ActivityIndicator, StatusBar, RefreshControl, TextInput,
} from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Trash2, RotateCcw, Search, Inbox } from 'lucide-react-native';
import { useState } from 'react';
import api from '../../lib/api';

type DeletedDoc = {
  id: string;
  doc_id?: string;
  doc_name?: string;
  category?: string;
  status?: string;
  deleted_at?: string;
};

function formatDate(ts?: string) {
  if (!ts) return '—';
  return ts.replace('T', ' ').slice(0, 16);
}

export default function ClientTrash() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');

  const { data, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['client-trash'],
    queryFn: async () => {
      const res = await api.get('/client/trash');
      return (res.data ?? []) as DeletedDoc[];
    },
    staleTime: 1000 * 60,
  });

  const docs = (data ?? []).filter((d) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return d.doc_name?.toLowerCase().includes(q) || d.doc_id?.toLowerCase().includes(q);
  });

  const restoreMutation = useMutation({
    mutationFn: (docId: string) => api.post(`/client/documents/${docId}/restore`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['client-trash'] });
      queryClient.invalidateQueries({ queryKey: ['client-docs'] });
      queryClient.invalidateQueries({ queryKey: ['client-docs-all'] });
      Alert.alert('Restored', 'Document restored to My Docs.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to restore.'),
  });

  const emptyTrashMutation = useMutation({
    mutationFn: () => api.delete('/client/trash/empty'),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['client-trash'] });
      queryClient.invalidateQueries({ queryKey: ['client-docs'] });
      queryClient.invalidateQueries({ queryKey: ['client-docs-all'] });
      const count = res.data?.count ?? 0;
      Alert.alert('Trash Emptied', `Permanently deleted ${count} document${count !== 1 ? 's' : ''}.`);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to empty trash.'),
  });

  const permanentDeleteMutation = useMutation({
    mutationFn: (docId: string) => api.delete(`/client/documents/${docId}/permanent`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['client-trash'] });
      queryClient.invalidateQueries({ queryKey: ['client-docs'] });
      queryClient.invalidateQueries({ queryKey: ['client-docs-all'] });
      Alert.alert('Deleted', 'Document permanently deleted.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to delete.'),
  });

  const handleRestore = (doc: DeletedDoc) => {
    Alert.alert('Restore', `Restore "${doc.doc_name || 'this document'}"?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Restore', onPress: () => restoreMutation.mutate(doc.id) },
    ]);
  };

  const handleEmptyTrash = () => {
    if ((data ?? []).length === 0) return;
    Alert.alert(
      'Empty All Trash',
      `Permanently delete all ${(data ?? []).length} document${(data ?? []).length !== 1 ? 's' : ''} in trash? This cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Empty Trash', style: 'destructive', onPress: () => emptyTrashMutation.mutate() },
      ],
    );
  };

  const handlePermanentDelete = (doc: DeletedDoc) => {
    Alert.alert('Permanently Delete', `Erase "${doc.doc_name || 'this document'}" forever? This cannot be undone.`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete Forever', style: 'destructive', onPress: () => permanentDeleteMutation.mutate(doc.id) },
    ]);
  };

  const renderItem = ({ item }: { item: DeletedDoc }) => (
    <View style={{
      backgroundColor: '#fff', borderRadius: 14, padding: 16, marginBottom: 10,
      borderWidth: 0.5, borderColor: '#E2E8F0',
    }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
        <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 14, flex: 1, marginRight: 8 }}>
          {item.doc_name || 'Untitled Document'}
        </Text>
        {item.doc_id && <Text style={{ fontSize: 11, color: '#94A3B8' }}>#{item.doc_id}</Text>}
      </View>
      <Text style={{ fontSize: 12, color: '#94A3B8', marginBottom: 14 }}>
        🗑️ Deleted {formatDate(item.deleted_at)}
        {item.category ? ` · ${item.category}` : ''}
      </Text>
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <TouchableOpacity
          onPress={() => handleRestore(item)}
          disabled={restoreMutation.isPending}
          style={{
            flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
            gap: 6, backgroundColor: '#F0FDF4', borderRadius: 10, paddingVertical: 10,
            borderWidth: 1, borderColor: '#BBF7D0',
          }}
        >
          <RotateCcw size={15} color="#16A34A" />
          <Text style={{ color: '#16A34A', fontWeight: '700', fontSize: 13 }}>Restore</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => handlePermanentDelete(item)}
          disabled={permanentDeleteMutation.isPending}
          style={{
            flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
            gap: 6, backgroundColor: '#FEF2F2', borderRadius: 10, paddingVertical: 10,
            borderWidth: 1, borderColor: '#FECACA',
          }}
        >
          <Trash2 size={15} color="#DC2626" />
          <Text style={{ color: '#DC2626', fontWeight: '700', fontSize: 13 }}>Delete Forever</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#7F1D1D" />
      <View style={{ backgroundColor: '#991B1B', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Trash2 size={20} color="#fff" />
            <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>Trash</Text>
          </View>
          {(data ?? []).length > 0 && (
            <TouchableOpacity
              onPress={handleEmptyTrash}
              disabled={emptyTrashMutation.isPending}
              style={{
                backgroundColor: 'rgba(255,255,255,0.20)', borderRadius: 10,
                paddingHorizontal: 12, paddingVertical: 6,
              }}
            >
              <Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>
                {emptyTrashMutation.isPending ? 'Emptying…' : 'Empty All'}
              </Text>
            </TouchableOpacity>
          )}
        </View>
        <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 13, marginTop: 4 }}>
          {docs.length} deleted document{docs.length !== 1 ? 's' : ''}
        </Text>
      </View>

      {/* Search */}
      <View style={{ paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#fff', borderBottomWidth: 0.5, borderBottomColor: '#E2E8F0' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#F1F5F9', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 }}>
          <Search size={16} color="#94A3B8" />
          <TextInput
            value={search} onChangeText={setSearch}
            placeholder="Search deleted documents…"
            placeholderTextColor="#94A3B8"
            style={{ flex: 1, fontSize: 14, color: '#1E293B' }}
          />
        </View>
      </View>

      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#991B1B" />
        </View>
      ) : (
        <FlatList
          data={docs} keyExtractor={(item, i) => item.id || String(i)} renderItem={renderItem}
          contentContainerStyle={{ padding: 16, paddingBottom: 100 }}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#991B1B" />}
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 72 }}>
              <Inbox size={48} color="#E2E8F0" />
              <Text style={{ color: '#1E293B', fontSize: 15, fontWeight: '700', marginTop: 14 }}>
                {search ? 'No results found' : 'Trash is empty'}
              </Text>
              <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 6 }}>
                {search ? 'Try a different search.' : 'Deleted documents appear here.'}
              </Text>
            </View>
          }
        />
      )}
    </View>
  );
}
