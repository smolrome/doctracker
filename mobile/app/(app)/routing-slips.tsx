import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  StatusBar,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, FileText } from 'lucide-react-native';
import api from '../../lib/api';

async function fetchRoutingSlips() {
  const res = await api.get('/routing-slips');
  return (res.data ?? []) as any[];
}

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

  const { data: slips, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['routing-slips'],
    queryFn: fetchRoutingSlips,
    staleTime: 1000 * 60 * 5,
  });

  const items = slips ?? [];

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
        }}>
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
          {item.to_office && (
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <Text style={{ color: '#94A3B8', fontSize: 12, width: 60 }}>To</Text>
              <Text style={{ color: '#475569', fontSize: 12, flex: 1 }}>{item.to_office}</Text>
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

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* Header */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
        <TouchableOpacity onPress={() => router.back()} style={{ marginBottom: 14, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <ArrowLeft size={18} color="#93C5FD" />
          <Text style={{ color: '#93C5FD', fontSize: 14, fontWeight: '600' }}>Back</Text>
        </TouchableOpacity>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <FileText size={20} color="#fff" />
          <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>Routing Slips</Text>
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
    </View>
  );
}
