import { useState } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, TextInput,
  ActivityIndicator, StatusBar, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Building2, Search, ChevronRight, FileText } from 'lucide-react-native';
import api from '../../lib/api';

type OfficeSummary = { office: string; count: number; documents: any[] };
type DocumentItem = { id: string; doc_id?: string; doc_name?: string; status?: string; created_at?: string };

const STATUS_CONFIG: Record<string, { bg: string; text: string }> = {
  pending:    { bg: '#FEF3C7', text: '#B45309' },
  received:   { bg: '#DBEAFE', text: '#1E40AF' },
  released:   { bg: '#D1FAE5', text: '#065F46' },
  routed:     { bg: '#EDE9FE', text: '#5B21B6' },
  'in review':{ bg: '#E0E7FF', text: '#3730A3' },
  transferred:{ bg: '#CFFAFE', text: '#155E75' },
  'on hold':  { bg: '#FEE2E2', text: '#991B1B' },
};
function getStatus(s: string) {
  return STATUS_CONFIG[s?.toLowerCase()] ?? { bg: '#F1F5F9', text: '#475569' };
}

export default function OfficeDocs() {
  const router = useRouter();
  const [selectedOffice, setSelectedOffice] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  // ── Grouped offices view ──────────────────────────────────────────────────

  const { data: grouped, isLoading: loadingGrouped, refetch: refetchGrouped, isRefetching: refetchingGrouped } = useQuery({
    queryKey: ['office-docs-grouped'],
    queryFn: async () => {
      const res = await api.get('/offices/documents');
      return (res.data?.offices ?? []) as OfficeSummary[];
    },
    staleTime: 1000 * 60,
    enabled: selectedOffice === null,
  });

  // ── Single office view ────────────────────────────────────────────────────

  const { data: officeDocs, isLoading: loadingOffice, refetch: refetchOffice, isRefetching: refetchingOffice } = useQuery({
    queryKey: ['office-docs', selectedOffice],
    queryFn: async () => {
      const res = await api.get(`/offices/documents?office=${encodeURIComponent(selectedOffice ?? '')}`);
      return (res.data?.documents ?? []) as DocumentItem[];
    },
    staleTime: 1000 * 60,
    enabled: selectedOffice !== null,
  });

  // ── Filtered data ─────────────────────────────────────────────────────────

  const filteredOffices = (grouped ?? []).filter((o) =>
    !search.trim() || o.office.toLowerCase().includes(search.toLowerCase())
  );

  const filteredDocs = (officeDocs ?? []).filter((d) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (d.doc_name?.toLowerCase().includes(q) || d.doc_id?.toLowerCase().includes(q));
  });

  // ── Render ─────────────────────────────────────────────────────────────────

  const renderOfficeCard = ({ item }: { item: OfficeSummary }) => (
    <TouchableOpacity
      onPress={() => { setSearch(''); setSelectedOffice(item.office); }}
      style={{
        backgroundColor: '#fff', borderRadius: 14, padding: 16,
        marginBottom: 10, borderWidth: 0.5, borderColor: '#E2E8F0',
        flexDirection: 'row', alignItems: 'center', gap: 14,
      }}
    >
      <View style={{
        width: 48, height: 48, borderRadius: 12,
        backgroundColor: '#EFF6FF', alignItems: 'center', justifyContent: 'center',
      }}>
        <Building2 size={22} color="#0038A8" />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 14 }} numberOfLines={1}>
          {item.office}
        </Text>
        <Text style={{ color: '#64748B', fontSize: 12, marginTop: 2 }}>
          {item.count} document{item.count !== 1 ? 's' : ''}
        </Text>
      </View>
      <ChevronRight size={18} color="#CBD5E1" />
    </TouchableOpacity>
  );

  const renderDocCard = ({ item }: { item: DocumentItem }) => {
    const s = getStatus(item.status ?? '');
    return (
      <TouchableOpacity
        onPress={() => router.push(`/(app)/documents/${item.id}`)}
        style={{
          backgroundColor: '#fff', borderRadius: 14, padding: 16,
          marginBottom: 10, borderWidth: 0.5, borderColor: '#E2E8F0',
          flexDirection: 'row', alignItems: 'center', gap: 12,
        }}
      >
        <FileText size={18} color="#0038A8" />
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <Text style={{ fontWeight: '700', color: '#1E293B', fontSize: 13 }} numberOfLines={1}>
              {item.doc_id || item.id?.slice(0, 8).toUpperCase()}
            </Text>
            {item.status && (
              <View style={{ backgroundColor: s.bg, borderRadius: 20, paddingHorizontal: 8, paddingVertical: 3 }}>
                <Text style={{ color: s.text, fontSize: 11, fontWeight: '700' }}>{item.status}</Text>
              </View>
            )}
          </View>
          <Text style={{ color: '#475569', fontSize: 13 }} numberOfLines={2}>
            {item.doc_name || 'No name'}
          </Text>
          <Text style={{ color: '#94A3B8', fontSize: 11, marginTop: 4 }}>
            {item.created_at?.slice(0, 10) || '—'}
          </Text>
        </View>
      </TouchableOpacity>
    );
  };

  const isLoading = selectedOffice ? loadingOffice : loadingGrouped;
  const isRefetching = selectedOffice ? refetchingOffice : refetchingGrouped;
  const refetch = selectedOffice ? refetchOffice : refetchGrouped;

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#1E3A5F" />

      {/* Header */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
        <TouchableOpacity
          onPress={() => {
            if (selectedOffice) { setSelectedOffice(null); setSearch(''); }
            else router.back();
          }}
          style={{ marginBottom: 14, flexDirection: 'row', alignItems: 'center', gap: 6 }}
        >
          <ArrowLeft size={18} color="rgba(255,255,255,0.70)" />
          <Text style={{ color: 'rgba(255,255,255,0.70)', fontSize: 14, fontWeight: '600' }}>
            {selectedOffice ? 'All Offices' : 'Back'}
          </Text>
        </TouchableOpacity>

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <Building2 size={20} color="#fff" />
          <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>
            {selectedOffice ? selectedOffice : 'Office Documents'}
          </Text>
        </View>

        {/* Search bar */}
        <View style={{
          flexDirection: 'row', alignItems: 'center', gap: 10,
          backgroundColor: 'rgba(255,255,255,0.15)',
          borderRadius: 12, paddingHorizontal: 12, paddingVertical: 8,
          borderWidth: 1, borderColor: 'rgba(255,255,255,0.20)',
        }}>
          <Search size={15} color="rgba(255,255,255,0.60)" />
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder={selectedOffice ? 'Search documents…' : 'Search offices…'}
            placeholderTextColor="rgba(255,255,255,0.45)"
            style={{ flex: 1, color: '#fff', fontSize: 14 }}
          />
        </View>
      </View>

      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
          <Text style={{ color: '#94A3B8', marginTop: 12, fontSize: 13 }}>Loading…</Text>
        </View>
      ) : selectedOffice ? (
        <FlatList
          data={filteredDocs}
          keyExtractor={(item, i) => item.id || String(i)}
          renderItem={renderDocCard}
          contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#0038A8" />}
          ListHeaderComponent={
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#64748B', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 12 }}>
              {filteredDocs.length} document{filteredDocs.length !== 1 ? 's' : ''}
            </Text>
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 72 }}>
              <FileText size={48} color="#E2E8F0" />
              <Text style={{ color: '#1E293B', fontSize: 15, fontWeight: '700', marginTop: 14 }}>No documents found</Text>
              <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 6, textAlign: 'center', paddingHorizontal: 40 }}>
                {search ? 'Try a different search.' : 'No documents from this office.'}
              </Text>
            </View>
          }
        />
      ) : (
        <FlatList
          data={filteredOffices}
          keyExtractor={(item) => item.office}
          renderItem={renderOfficeCard}
          contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#0038A8" />}
          ListHeaderComponent={
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#64748B', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 12 }}>
              {filteredOffices.length} office{filteredOffices.length !== 1 ? 's' : ''}
            </Text>
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 72 }}>
              <Building2 size={48} color="#E2E8F0" />
              <Text style={{ color: '#1E293B', fontSize: 15, fontWeight: '700', marginTop: 14 }}>No offices found</Text>
              <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 6 }}>
                {search ? 'Try a different search term.' : 'No documents have been logged yet.'}
              </Text>
            </View>
          }
        />
      )}
    </View>
  );
}
