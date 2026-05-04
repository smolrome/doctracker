import { useState } from 'react';
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
import { ArrowLeft, Clock } from 'lucide-react-native';
import api from '../../lib/api';

async function fetchActivityLog(limit: number) {
  const res = await api.get('/activity-log', { params: { limit } });
  return (res.data ?? []) as any[];
}

const ACTION_COLORS: Record<string, string> = {
  create: '#10B981',
  add:    '#10B981',
  update: '#3B82F6',
  status: '#8B5CF6',
  delete: '#EF4444',
  login:  '#F59E0B',
  accept: '#10B981',
  reject: '#EF4444',
  transfer: '#06B6D4',
};

function dotColor(action: string) {
  const lower = (action || '').toLowerCase();
  for (const [key, color] of Object.entries(ACTION_COLORS)) {
    if (lower.includes(key)) return color;
  }
  return '#94A3B8';
}

function formatDate(ts: string | undefined) {
  if (!ts) return '—';
  return ts.replace('T', ' ').slice(0, 16);
}

export default function ActivityLog() {
  const router = useRouter();
  const [limit, setLimit] = useState(50);

  const { data: logs, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['activity-log-full', limit],
    queryFn: () => fetchActivityLog(limit),
    staleTime: 1000 * 60,
  });

  const items = logs ?? [];

  const renderItem = ({ item, index }: { item: any; index: number }) => {
    const color = dotColor(item.action || item.event || '');
    const isLast = index === items.length - 1;
    return (
      <View style={{ flexDirection: 'row', gap: 12, paddingHorizontal: 20 }}>
        {/* Spine */}
        <View style={{ alignItems: 'center', width: 18 }}>
          <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: color, marginTop: 4 }} />
          {!isLast && <View style={{ width: 2, flex: 1, backgroundColor: '#E2E8F0', marginVertical: 3 }} />}
        </View>

        {/* Body */}
        <View style={{ flex: 1, paddingBottom: isLast ? 20 : 16 }}>
          <Text style={{ fontWeight: '700', color: '#1E293B', fontSize: 13.5, marginBottom: 2 }}>
            {item.action || item.event || '—'}
          </Text>
          {item.username && (
            <Text style={{ color: '#64748B', fontSize: 12, marginBottom: 2 }}>
              by {item.username}
            </Text>
          )}
          {item.doc_name && (
            <Text style={{ color: '#475569', fontSize: 12, marginBottom: 2 }} numberOfLines={1}>
              {item.doc_name}
            </Text>
          )}
          <Text style={{ color: '#94A3B8', fontSize: 11.5 }}>
            {formatDate(item.timestamp || item.created_at)}
          </Text>
        </View>
      </View>
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
          <Clock size={20} color="#fff" />
          <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>Activity Log</Text>
        </View>
        <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 13, marginTop: 4 }}>
          {items.length} recent events
        </Text>
      </View>

      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
          <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 12 }}>Loading activity…</Text>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(_, i) => String(i)}
          renderItem={renderItem}
          contentContainerStyle={{ paddingTop: 20, paddingBottom: 40 }}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#0038A8" />
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 72 }}>
              <Text style={{ fontSize: 36 }}>📋</Text>
              <Text style={{ color: '#1E293B', fontSize: 15, fontWeight: '700', marginTop: 14 }}>No activity yet</Text>
              <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 6 }}>Events will appear here as actions are taken.</Text>
            </View>
          }
          ListFooterComponent={
            items.length >= limit ? (
              <TouchableOpacity
                onPress={() => setLimit((l) => l + 50)}
                style={{ marginHorizontal: 20, marginTop: 8, backgroundColor: '#EFF6FF', borderRadius: 12, paddingVertical: 13, alignItems: 'center' }}
              >
                <Text style={{ color: '#0038A8', fontWeight: '700', fontSize: 14 }}>Load more</Text>
              </TouchableOpacity>
            ) : null
          }
        />
      )}
    </View>
  );
}
