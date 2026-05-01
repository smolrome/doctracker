import { useState } from 'react';
import {
  View,
  Text,
  FlatList,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  StatusBar,
  Dimensions,
  Modal,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Search, CheckSquare, Square, X, Trash2, RefreshCw } from 'lucide-react-native';
import { useDocuments } from '../../../hooks/useDocuments';
import { useNetwork } from '../../../hooks/useNetwork';
import { OfflineBanner } from '../../../components/ui/OfflineBanner';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../../lib/store';
import api from '../../../lib/api';

const { width } = Dimensions.get('window');

// Status badge config — semantic bg/text pairs (matches Dashboard)
const STATUS_CONFIG: Record<string, { bg: string; text: string; accent: string }> = {
  pending:    { bg: '#FEF3C7', text: '#B45309', accent: '#F59E0B' },
  received:   { bg: '#DBEAFE', text: '#1E40AF', accent: '#3B82F6' },
  released:   { bg: '#D1FAE5', text: '#065F46', accent: '#10B981' },
  routed:     { bg: '#EDE9FE', text: '#5B21B6', accent: '#8B5CF6' },
  'in review':{ bg: '#E0E7FF', text: '#3730A3', accent: '#6366F1' },
  transferred:{ bg: '#CFFAFE', text: '#155E75', accent: '#06B6D4' },
  'on hold':  { bg: '#FEE2E2', text: '#991B1B', accent: '#EF4444' },
};

const ALL_STATUSES = ['Pending', 'Received', 'Released', 'Routed', 'In Review', 'Transferred', 'On Hold', 'Returned', 'Archived'];

function getStatus(status: string) {
  const key = status?.toLowerCase();
  return STATUS_CONFIG[key] ?? { bg: '#F1F5F9', text: '#475569', accent: '#94A3B8' };
}

const STATUS_FILTERS = ['All', 'Pending', 'Received', 'Released', 'Routed', 'On Hold'];

export default function Documents() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin';

  const [search, setSearch] = useState('');
  const [activeFilter, setActiveFilter] = useState('All');
  const [searchInput, setSearchInput] = useState('');
  const { isOnline } = useNetwork();

  // ── Bulk select state ──────────────────────────────────────────────────────
  const [bulkMode, setBulkMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkStatusModal, setBulkStatusModal] = useState(false);
  const [bulkRemarks, setBulkRemarks] = useState('');

  const { data, isLoading, isRefetching, refetch, isFromCache } = useDocuments(search, activeFilter);
  const docs = data?.documents ?? [];

  const handleSearch = () => setSearch(searchInput);

  // ── Bulk mutations ─────────────────────────────────────────────────────────

  const bulkStatusMutation = useMutation({
    mutationFn: ({ status, remarks }: { status: string; remarks: string }) =>
      api.post('/documents/bulk-status', { doc_ids: Array.from(selected), status, remarks }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      setBulkStatusModal(false);
      setSelected(new Set());
      setBulkMode(false);
      setBulkRemarks('');
      Alert.alert('Updated', res.data?.message || `${selected.size} document(s) updated.`);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Bulk update failed.'),
  });

  const bulkDeleteMutation = useMutation({
    mutationFn: () => api.post('/documents/bulk-delete', { doc_ids: Array.from(selected) }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['trash'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      setSelected(new Set());
      setBulkMode(false);
      Alert.alert('Deleted', res.data?.message || `${selected.size} document(s) moved to trash.`);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Bulk delete failed.'),
  });

  // ── Handlers ───────────────────────────────────────────────────────────────

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelected(new Set(docs.map((d: any) => d.id)));
  const clearSelection = () => setSelected(new Set());

  const exitBulkMode = () => {
    setBulkMode(false);
    setSelected(new Set());
  };

  const handleBulkDelete = () => {
    if (selected.size === 0) return;
    Alert.alert(
      'Bulk Delete',
      `Move ${selected.size} document${selected.size !== 1 ? 's' : ''} to trash?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Move to Trash', style: 'destructive', onPress: () => bulkDeleteMutation.mutate() },
      ],
    );
  };

  // ── Render item ────────────────────────────────────────────────────────────

  const renderDoc = ({ item }: { item: any }) => {
    const s = getStatus(item.status);
    const isSelected = selected.has(item.id);

    return (
      <TouchableOpacity
        onPress={() => {
          if (bulkMode) toggleSelect(item.id);
          else router.push(`/(app)/documents/${item.id}`);
        }}
        onLongPress={() => {
          if (!bulkMode) {
            setBulkMode(true);
            setSelected(new Set([item.id]));
          }
        }}
        activeOpacity={0.75}
        style={{
          backgroundColor: isSelected ? '#EFF6FF' : '#fff',
          borderRadius: 14,
          padding: 16,
          marginBottom: 10,
          borderWidth: isSelected ? 1.5 : 0.5,
          borderColor: isSelected ? '#0038A8' : '#E2E8F0',
          flexDirection: 'row',
          alignItems: 'center',
          gap: 12,
        }}
      >
        {/* Checkbox (bulk mode) or accent bar */}
        {bulkMode ? (
          <View style={{ width: 24, alignItems: 'center' }}>
            {isSelected
              ? <CheckSquare size={22} color="#0038A8" />
              : <Square size={22} color="#CBD5E1" />}
          </View>
        ) : (
          <View style={{
            width: 3, height: 44, borderRadius: 2,
            backgroundColor: s.accent, opacity: 0.6,
          }} />
        )}

        <View style={{ flex: 1 }}>
          {/* Top row: doc ID + status badge */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
            <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 13.5, letterSpacing: -0.2 }}>
              {item.doc_id || item.id?.slice(0, 8).toUpperCase()}
            </Text>
            <View style={{ backgroundColor: s.bg, borderRadius: 20, paddingHorizontal: 9, paddingVertical: 3 }}>
              <Text style={{ color: s.text, fontSize: 11, fontWeight: '700' }}>
                {item.status}
              </Text>
            </View>
          </View>

          {/* Doc name */}
          <Text style={{ color: '#334155', fontSize: 13, marginBottom: 5, lineHeight: 18 }} numberOfLines={2}>
            {item.doc_name || 'No name'}
          </Text>

          {/* Footer row: office + date */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={{ color: '#94A3B8', fontSize: 11.5 }} numberOfLines={1}>
              {item.from_office || item.sender_org || '—'}
            </Text>
            <Text style={{ color: '#94A3B8', fontSize: 11.5 }}>
              {item.doc_date || item.created_at?.slice(0, 10) || '—'}
            </Text>
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  // ── Screen ──────────────────────────────────────────────────────────────────

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC', paddingBottom: 100 }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />
      <OfflineBanner />

      {/* ── Hero header ── */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20, overflow: 'hidden' }}>
        {/* Grid texture */}
        {[...Array(3)].map((_, i) => (
          <View key={`h${i}`} style={{
            position: 'absolute', top: (i + 1) * 28, left: 0, right: 0,
            height: 1, backgroundColor: '#fff', opacity: 0.05,
          }} />
        ))}
        {[...Array(4)].map((_, i) => (
          <View key={`v${i}`} style={{
            position: 'absolute', left: (i + 1) * (width / 5), top: 0, bottom: 0,
            width: 1, backgroundColor: '#fff', opacity: 0.05,
          }} />
        ))}
        {/* Yellow accent circle */}
        <View style={{
          position: 'absolute', top: -40, right: -40,
          width: 130, height: 130, borderRadius: 65,
          backgroundColor: '#FCD116', opacity: 0.10,
        }} />

        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>
            Documents
          </Text>
          {/* Bulk mode toggle */}
          <TouchableOpacity
            onPress={() => bulkMode ? exitBulkMode() : setBulkMode(true)}
            style={{
              backgroundColor: bulkMode ? '#EF4444' : 'rgba(255,255,255,0.18)',
              borderRadius: 10, paddingHorizontal: 12, paddingVertical: 7,
              borderWidth: 1, borderColor: bulkMode ? '#EF4444' : 'rgba(255,255,255,0.25)',
            }}
          >
            <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>
              {bulkMode ? 'Exit Bulk' : 'Bulk Select'}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Search bar */}
        <View style={{
          flexDirection: 'row', gap: 8,
          backgroundColor: 'rgba(255,255,255,0.15)',
          borderRadius: 13, paddingHorizontal: 14, paddingVertical: 2,
          borderWidth: 1, borderColor: 'rgba(255,255,255,0.20)',
          alignItems: 'center',
        }}>
          <Search size={16} color="rgba(255,255,255,0.60)" />
          <TextInput
            value={searchInput}
            onChangeText={setSearchInput}
            onSubmitEditing={handleSearch}
            returnKeyType="search"
            placeholder="Search documents..."
            placeholderTextColor="rgba(255,255,255,0.45)"
            style={{ flex: 1, paddingVertical: 11, color: '#fff', fontSize: 14 }}
          />
          <TouchableOpacity
            onPress={handleSearch}
            style={{
              backgroundColor: '#fff',
              borderRadius: 9,
              paddingHorizontal: 14,
              paddingVertical: 7,
            }}
          >
            <Text style={{ color: '#0038A8', fontWeight: '700', fontSize: 13 }}>Search</Text>
          </TouchableOpacity>
        </View>

        {/* Cached data notice */}
        {isFromCache && (
          <View style={{
            marginTop: 12,
            backgroundColor: 'rgba(255,255,255,0.10)',
            borderRadius: 10, padding: 10,
            flexDirection: 'row', alignItems: 'center', gap: 8,
            borderWidth: 1, borderColor: 'rgba(255,255,255,0.15)',
          }}>
            <Text style={{ fontSize: 13 }}>💾</Text>
            <Text style={{ color: '#FCD34D', fontSize: 12, flex: 1 }}>
              Showing cached data — pull to refresh when online
            </Text>
          </View>
        )}
      </View>

      {/* ── Filter pills ── */}
      <View style={{ backgroundColor: '#fff', borderBottomWidth: 0.5, borderBottomColor: '#E2E8F0' }}>
        <FlatList
          horizontal
          data={STATUS_FILTERS}
          keyExtractor={(i) => i}
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ paddingHorizontal: 16, paddingVertical: 10, gap: 8 }}
          renderItem={({ item }) => (
            <TouchableOpacity
              onPress={() => setActiveFilter(item)}
              style={{
                paddingHorizontal: 16,
                paddingVertical: 6,
                borderRadius: 20,
                backgroundColor: activeFilter === item ? '#0038A8' : '#F1F5F9',
                borderWidth: activeFilter === item ? 0 : 0.5,
                borderColor: '#E2E8F0',
              }}
            >
              <Text style={{
                color: activeFilter === item ? '#fff' : '#64748B',
                fontWeight: '700',
                fontSize: 12.5,
              }}>
                {item}
              </Text>
            </TouchableOpacity>
          )}
        />
      </View>

      {/* ── Result count / Bulk bar ── */}
      <View style={{ paddingHorizontal: 20, paddingTop: 14, paddingBottom: 6, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        {bulkMode ? (
          <>
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#0038A8', textTransform: 'uppercase', letterSpacing: 0.8 }}>
              {selected.size} selected
            </Text>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity
                onPress={selected.size === docs.length ? clearSelection : selectAll}
                style={{ backgroundColor: '#EFF6FF', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5 }}
              >
                <Text style={{ color: '#0038A8', fontSize: 12, fontWeight: '700' }}>
                  {selected.size === docs.length ? 'Deselect All' : 'Select All'}
                </Text>
              </TouchableOpacity>
            </View>
          </>
        ) : (
          <>
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#0038A8', textTransform: 'uppercase', letterSpacing: 0.8 }}>
              {isLoading ? 'Loading...' : `${data?.total ?? 0} documents found`}
            </Text>
            {!isOnline && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: '#F87171' }} />
                <Text style={{ color: '#F87171', fontSize: 12, fontWeight: '600' }}>Offline</Text>
              </View>
            )}
          </>
        )}
      </View>

      {/* ── List ── */}
      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
          <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 12 }}>Loading documents...</Text>
        </View>
      ) : (
        <FlatList
          data={docs}
          keyExtractor={(item) => item.id}
          renderItem={renderDoc}
          contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 4, paddingBottom: bulkMode ? 100 : 16 }}
          refreshControl={
            <RefreshControl
              refreshing={isRefetching}
              onRefresh={refetch}
              tintColor="#0038A8"
            />
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 72 }}>
              <View style={{
                width: 72, height: 72, borderRadius: 36,
                backgroundColor: '#EFF6FF',
                alignItems: 'center', justifyContent: 'center',
                marginBottom: 16,
              }}>
                <Text style={{ fontSize: 32 }}>📄</Text>
              </View>
              <Text style={{ color: '#1E293B', fontSize: 16, fontWeight: '700', marginBottom: 6 }}>
                No documents found
              </Text>
              <Text style={{ color: '#94A3B8', fontSize: 13, textAlign: 'center', paddingHorizontal: 40 }}>
                Try adjusting your search or filter to find what you're looking for.
              </Text>
            </View>
          }
        />
      )}

      {/* ── Bulk Action Bar (shown when in bulk mode) ── */}
      {bulkMode && (
        <View style={{
          position: 'absolute', bottom: 100, left: 16, right: 16,
          backgroundColor: '#1E293B', borderRadius: 16, padding: 14,
          flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
          shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
          shadowOpacity: 0.25, shadowRadius: 12, elevation: 8,
        }}>
          <TouchableOpacity
            onPress={exitBulkMode}
            style={{ padding: 4 }}
          >
            <X size={20} color="#94A3B8" />
          </TouchableOpacity>

          <Text style={{ color: '#fff', fontSize: 13, fontWeight: '700', flex: 1, marginLeft: 10 }}>
            {selected.size > 0 ? `${selected.size} selected` : 'Tap items to select'}
          </Text>

          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TouchableOpacity
              onPress={() => {
                if (selected.size === 0) { Alert.alert('No Selection', 'Select at least one document.'); return; }
                setBulkStatusModal(true);
              }}
              disabled={selected.size === 0}
              style={{
                backgroundColor: selected.size > 0 ? '#3B82F6' : '#374151',
                borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8,
                flexDirection: 'row', alignItems: 'center', gap: 5,
              }}
            >
              <RefreshCw size={14} color="#fff" />
              <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>Status</Text>
            </TouchableOpacity>

            {isAdmin && (
              <TouchableOpacity
                onPress={handleBulkDelete}
                disabled={selected.size === 0 || bulkDeleteMutation.isPending}
                style={{
                  backgroundColor: selected.size > 0 ? '#EF4444' : '#374151',
                  borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8,
                  flexDirection: 'row', alignItems: 'center', gap: 5,
                }}
              >
                <Trash2 size={14} color="#fff" />
                <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>Delete</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
      )}

      {/* ── Bulk Status Modal ── */}
      <Modal visible={bulkStatusModal} animationType="slide" transparent>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' }}>
          <TouchableOpacity
            style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
            onPress={() => setBulkStatusModal(false)}
            activeOpacity={1}
          />
          <View style={{
            backgroundColor: '#F8FAFC', borderTopLeftRadius: 24, borderTopRightRadius: 24,
            padding: 20, paddingBottom: 40,
          }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 17 }}>
                Update Status · {selected.size} doc{selected.size !== 1 ? 's' : ''}
              </Text>
              <TouchableOpacity onPress={() => setBulkStatusModal(false)}>
                <X size={20} color="#94A3B8" />
              </TouchableOpacity>
            </View>

            {/* Status pills */}
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
              {ALL_STATUSES.map((s) => {
                const cfg = getStatus(s);
                return (
                  <TouchableOpacity
                    key={s}
                    onPress={() => {
                      setBulkStatusModal(false);
                      bulkStatusMutation.mutate({ status: s, remarks: bulkRemarks });
                    }}
                    disabled={bulkStatusMutation.isPending}
                    style={{
                      backgroundColor: cfg.bg, borderRadius: 20,
                      paddingHorizontal: 14, paddingVertical: 8,
                    }}
                  >
                    <Text style={{ color: cfg.text, fontWeight: '700', fontSize: 13 }}>{s}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Remarks */}
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 }}>
              Remarks (optional)
            </Text>
            <TextInput
              value={bulkRemarks}
              onChangeText={setBulkRemarks}
              placeholder="Add a note about this status change…"
              placeholderTextColor="#94A3B8"
              multiline
              style={{
                backgroundColor: '#fff', borderRadius: 12, padding: 12,
                borderWidth: 1, borderColor: '#E2E8F0', fontSize: 14, color: '#1E293B',
                height: 80, textAlignVertical: 'top',
              }}
            />
          </View>
        </View>
      </Modal>
    </View>
  );
}
