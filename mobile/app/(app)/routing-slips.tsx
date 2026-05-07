import { useState } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  StatusBar,
  Modal,
  TextInput,
  ScrollView,
  Platform,
  KeyboardAvoidingView,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, FileText, Plus, X, Search, CheckSquare, Square } from 'lucide-react-native';
import api from '../../lib/api';
import { useAuthStore } from '../../lib/store';
import { useOffices } from '../../hooks/useDropdownOptions';
import { SelectField } from '../../components/ui/SelectField';

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  pending:    { bg: '#FEF3C7', text: '#B45309' },
  accepted:   { bg: '#D1FAE5', text: '#065F46' },
  rejected:   { bg: '#FEE2E2', text: '#991B1B' },
  completed:  { bg: '#DBEAFE', text: '#1E40AF' },
};

function slipStatus(status: string) {
  return STATUS_COLORS[(status || '').toLowerCase()] ?? { bg: '#F1F5F9', text: '#475569' };
}

function formatDate(ts: string | undefined) {
  if (!ts) return '—';
  return ts.replace('T', ' ').slice(0, 16);
}

export default function RoutingSlips() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const canCreate = user?.role === 'admin' || user?.role === 'superadmin' || user?.role === 'staff';

  // ── Routing slips list ────────────────────────────────────────────────────

  const { data: slips, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['routing-slips'],
    queryFn: async () => {
      const res = await api.get('/routing-slips');
      return (res.data ?? []) as any[];
    },
    staleTime: 1000 * 60 * 5,
  });

  const items = slips ?? [];

  // ── Create modal state ────────────────────────────────────────────────────

  const [createModal, setCreateModal] = useState(false);
  const [docSearch, setDocSearch] = useState('');
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set());
  const [destination, setDestination] = useState('');
  const [remarks, setRemarks] = useState('');

  const { data: offices = [] } = useOffices();
  const officeNames = offices.map((o) => o.office_name);

  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: ['routing-slip-doc-picker'],
    queryFn: async () => {
      const res = await api.get('/documents', { params: { limit: 200, page: 1 } });
      return (res.data?.documents ?? []) as any[];
    },
    enabled: createModal,
    staleTime: 0,
  });

  const allDocs = docsData ?? [];
  const filteredDocs = docSearch
    ? allDocs.filter((d: any) =>
        (d.doc_name || '').toLowerCase().includes(docSearch.toLowerCase()) ||
        (d.doc_id || '').toLowerCase().includes(docSearch.toLowerCase()),
      )
    : allDocs;

  const resetCreateForm = () => {
    setDocSearch('');
    setSelectedDocIds(new Set());
    setDestination('');
    setRemarks('');
  };

  const toggleDoc = (id: string) => {
    setSelectedDocIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const createMutation = useMutation({
    mutationFn: (payload: { doc_ids: string[]; destination: string; notes: string }) =>
      api.post('/routing-slips', payload),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['routing-slips'] });
      setCreateModal(false);
      resetCreateForm();
      Alert.alert('Created', `Routing slip ${res.data?.slip_no || ''} created successfully.`);
    },
    onError: (e: any) =>
      Alert.alert('Error', e?.response?.data?.error || 'Failed to create routing slip.'),
  });

  const handleCreate = () => {
    if (selectedDocIds.size === 0) {
      Alert.alert('Required', 'Select at least one document.');
      return;
    }
    if (!destination.trim()) {
      Alert.alert('Required', 'Please select a destination office.');
      return;
    }
    createMutation.mutate({
      doc_ids: Array.from(selectedDocIds),
      destination: destination.trim(),
      notes: remarks.trim(),
    });
  };

  // ── Render slip card ──────────────────────────────────────────────────────

  const renderItem = ({ item }: { item: any }) => {
    const s = slipStatus(item.status);
    return (
      <TouchableOpacity
        onPress={() => router.push({ pathname: '/(app)/routing-slip-detail', params: { id: item.id } })}
        activeOpacity={0.75}
        style={{
          backgroundColor: '#fff',
          borderRadius: 14,
          padding: 16,
          marginBottom: 10,
          borderWidth: 0.5,
          borderColor: '#E2E8F0',
        }}
      >
        {/* Top row */}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 13.5 }}>
            {item.slip_id || item.id?.slice(0, 8).toUpperCase() || 'Routing Slip'}
          </Text>
          <View style={{ backgroundColor: s.bg, borderRadius: 20, paddingHorizontal: 10, paddingVertical: 3 }}>
            <Text style={{ color: s.text, fontSize: 11, fontWeight: '700' }}>
              {(item.status || 'Unknown').toUpperCase()}
            </Text>
          </View>
        </View>

        {/* Document name */}
        {item.doc_name && (
          <Text style={{ color: '#334155', fontSize: 13.5, fontWeight: '600', marginBottom: 8 }}>
            {item.doc_name}
          </Text>
        )}

        {/* Route details */}
        <View style={{ gap: 4 }}>
          {item.from_office && (
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <Text style={{ color: '#94A3B8', fontSize: 12, width: 60 }}>From</Text>
              <Text style={{ color: '#475569', fontSize: 12, flex: 1 }}>{item.from_office}</Text>
            </View>
          )}
          {(item.to_office || item.destination) && (
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <Text style={{ color: '#94A3B8', fontSize: 12, width: 60 }}>To</Text>
              <Text style={{ color: '#475569', fontSize: 12, flex: 1 }}>{item.to_office || item.destination}</Text>
            </View>
          )}
          {(item.routed_by || item.created_by) && (
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <Text style={{ color: '#94A3B8', fontSize: 12, width: 60 }}>By</Text>
              <Text style={{ color: '#475569', fontSize: 12, flex: 1 }}>{item.routed_by || item.created_by}</Text>
            </View>
          )}
          {(item.created_at || item.routed_at) && (
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <Text style={{ color: '#94A3B8', fontSize: 12, width: 60 }}>Date</Text>
              <Text style={{ color: '#94A3B8', fontSize: 12 }}>{formatDate(item.created_at || item.routed_at)}</Text>
            </View>
          )}
        </View>

        {/* Remarks */}
        {item.remarks && (
          <Text style={{ color: '#64748B', fontSize: 12, fontStyle: 'italic', marginTop: 8, lineHeight: 18 }}>
            {item.remarks}
          </Text>
        )}

        {/* Tap hint */}
        <View style={{ flexDirection: 'row', justifyContent: 'flex-end', marginTop: 8 }}>
          <Text style={{ color: '#CBD5E1', fontSize: 12 }}>Tap to view documents ›</Text>
        </View>
      </TouchableOpacity>
    );
  };

  // ── Screen ────────────────────────────────────────────────────────────────

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
          <Text style={{ color: '#93C5FD', fontSize: 14, fontWeight: '600' }}>Back</Text>
        </TouchableOpacity>

        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <FileText size={20} color="#fff" />
            <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>Routing Slips</Text>
          </View>

          {canCreate && (
            <TouchableOpacity
              onPress={() => setCreateModal(true)}
              style={{
                backgroundColor: 'rgba(255,255,255,0.18)',
                borderRadius: 10, paddingHorizontal: 12, paddingVertical: 7,
                borderWidth: 1, borderColor: 'rgba(255,255,255,0.25)',
                flexDirection: 'row', alignItems: 'center', gap: 5,
              }}
            >
              <Plus size={14} color="#fff" />
              <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>New Slip</Text>
            </TouchableOpacity>
          )}
        </View>

        <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 13, marginTop: 4 }}>
          {items.length} slip{items.length !== 1 ? 's' : ''} found
        </Text>
      </View>

      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
          <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 12 }}>Loading routing slips…</Text>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item, i) => item.id || String(i)}
          renderItem={renderItem}
          contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#0038A8" />
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 72 }}>
              <Text style={{ fontSize: 36 }}>📋</Text>
              <Text style={{ color: '#1E293B', fontSize: 15, fontWeight: '700', marginTop: 14 }}>No routing slips</Text>
              <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 6, textAlign: 'center', paddingHorizontal: 40 }}>
                Routing slips will appear here when documents are transferred.
              </Text>
            </View>
          }
        />
      )}

      {/* ── Create Routing Slip Modal ──────────────────────────────────────── */}
      <Modal
        visible={createModal}
        transparent
        animationType="slide"
        onRequestClose={() => { setCreateModal(false); resetCreateForm(); }}
      >
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
            <TouchableOpacity
              style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
              onPress={() => { setCreateModal(false); resetCreateForm(); }}
              activeOpacity={1}
            />
            <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: '92%' }}>

              {/* Modal header */}
              <View style={{
                backgroundColor: '#0038A8',
                borderTopLeftRadius: 24, borderTopRightRadius: 24,
                paddingTop: 20, paddingBottom: 16, paddingHorizontal: 20,
              }}>
                <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.30)', alignSelf: 'center', marginBottom: 12 }} />
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={{ fontSize: 17, fontWeight: '800', color: '#fff' }}>Create Routing Slip</Text>
                  <TouchableOpacity
                    onPress={() => { setCreateModal(false); resetCreateForm(); }}
                    style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' }}
                  >
                    <X size={16} color="#fff" />
                  </TouchableOpacity>
                </View>
                <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 12, marginTop: 4 }}>
                  Select documents and a destination office
                </Text>
              </View>

              <ScrollView
                contentContainerStyle={{ padding: 20, paddingBottom: 8 }}
                keyboardShouldPersistTaps="handled"
                showsVerticalScrollIndicator={false}
              >
                {/* Destination */}
                <Text style={fieldLabel}>
                  Destination Office <Text style={{ color: '#EF4444' }}>*</Text>
                </Text>
                <SelectField
                  value={destination}
                  onChange={setDestination}
                  options={officeNames}
                  placeholder="Select destination office…"
                  label="Destination"
                  disabled={createMutation.isPending}
                />

                {/* Documents */}
                <Text style={[fieldLabel, { marginTop: 8 }]}>
                  Documents <Text style={{ color: '#EF4444' }}>*</Text>
                </Text>
                <Text style={{ color: '#64748B', fontSize: 12, marginBottom: 8 }}>
                  {selectedDocIds.size} selected
                </Text>

                {/* Doc search */}
                <View style={{
                  flexDirection: 'row', alignItems: 'center', gap: 8,
                  backgroundColor: '#fff', borderRadius: 10,
                  borderWidth: 1, borderColor: '#E2E8F0',
                  paddingHorizontal: 12, marginBottom: 10,
                }}>
                  <Search size={14} color="#94A3B8" />
                  <TextInput
                    value={docSearch}
                    onChangeText={setDocSearch}
                    placeholder="Search by name or ID…"
                    placeholderTextColor="#CBD5E1"
                    style={{ flex: 1, paddingVertical: 9, fontSize: 13, color: '#1E293B' }}
                  />
                  {docSearch !== '' && (
                    <TouchableOpacity onPress={() => setDocSearch('')} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                      <X size={13} color="#94A3B8" />
                    </TouchableOpacity>
                  )}
                </View>

                {/* Doc list */}
                {docsLoading ? (
                  <ActivityIndicator color="#0038A8" style={{ marginVertical: 16 }} />
                ) : filteredDocs.length === 0 ? (
                  <Text style={{ color: '#94A3B8', textAlign: 'center', marginVertical: 16, fontSize: 13 }}>
                    No documents found
                  </Text>
                ) : (
                  filteredDocs.slice(0, 50).map((doc: any) => {
                    const isSelected = selectedDocIds.has(doc.id);
                    return (
                      <TouchableOpacity
                        key={doc.id}
                        onPress={() => toggleDoc(doc.id)}
                        style={{
                          flexDirection: 'row', alignItems: 'center', gap: 10,
                          backgroundColor: isSelected ? '#EFF6FF' : '#fff',
                          borderRadius: 10, padding: 12, marginBottom: 6,
                          borderWidth: isSelected ? 1.5 : 0.5,
                          borderColor: isSelected ? '#0038A8' : '#E2E8F0',
                        }}
                      >
                        {isSelected
                          ? <CheckSquare size={18} color="#0038A8" />
                          : <Square size={18} color="#CBD5E1" />}
                        <View style={{ flex: 1 }}>
                          <Text style={{ color: '#1E293B', fontWeight: '600', fontSize: 13 }} numberOfLines={1}>
                            {doc.doc_name || 'Untitled'}
                          </Text>
                          <Text style={{ color: '#94A3B8', fontSize: 11.5 }}>
                            {doc.doc_id || doc.id?.slice(0, 8)}
                          </Text>
                        </View>
                      </TouchableOpacity>
                    );
                  })
                )}

                {/* Remarks */}
                <Text style={[fieldLabel, { marginTop: 8 }]}>
                  Remarks{' '}
                  <Text style={{ color: '#94A3B8', fontWeight: '400', textTransform: 'none' }}>(optional)</Text>
                </Text>
                <TextInput
                  value={remarks}
                  onChangeText={setRemarks}
                  placeholder="Notes about this routing…"
                  placeholderTextColor="#CBD5E1"
                  multiline
                  editable={!createMutation.isPending}
                  style={{
                    backgroundColor: '#fff', borderRadius: 12,
                    borderWidth: 1.5, borderColor: '#E2E8F0',
                    paddingHorizontal: 14, paddingVertical: 12,
                    fontSize: 14, color: '#1E293B',
                    height: 80, textAlignVertical: 'top', marginBottom: 16,
                  }}
                />
              </ScrollView>

              {/* Footer */}
              <View style={{
                padding: 16,
                paddingBottom: Platform.OS === 'ios' ? 32 : 20,
                borderTopWidth: 0.5, borderTopColor: '#E2E8F0',
                gap: 10,
              }}>
                <TouchableOpacity
                  onPress={handleCreate}
                  disabled={createMutation.isPending}
                  style={{
                    backgroundColor: createMutation.isPending ? '#93C5FD' : '#0038A8',
                    borderRadius: 13, paddingVertical: 15,
                    alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8,
                  }}
                >
                  {createMutation.isPending
                    ? (
                      <>
                        <ActivityIndicator color="#fff" size="small" />
                        <Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>Creating…</Text>
                      </>
                    ) : (
                      <>
                        <FileText size={18} color="#fff" />
                        <Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>Create Routing Slip</Text>
                      </>
                    )}
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => { setCreateModal(false); resetCreateForm(); }}
                  disabled={createMutation.isPending}
                  style={{
                    borderWidth: 1.5, borderColor: '#E2E8F0',
                    borderRadius: 13, paddingVertical: 13,
                    alignItems: 'center', backgroundColor: '#fff',
                  }}
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

const fieldLabel: any = {
  fontSize: 11, fontWeight: '700', color: '#0038A8',
  textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6,
};
