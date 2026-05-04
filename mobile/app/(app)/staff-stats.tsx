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
import { ArrowLeft, Users } from 'lucide-react-native';
import api from '../../lib/api';
import { useAuthStore } from '../../lib/store';

async function fetchStaffStats() {
  const res = await api.get('/staff-stats');
  return (res.data ?? []) as Array<{
    username: string;
    total: number;
    pending: number;
    received: number;
    released: number;
    other: number;
  }>;
}

function StatPill({ label, value, bg, text }: { label: string; value: number; bg: string; text: string }) {
  return (
    <View style={{ alignItems: 'center', backgroundColor: bg, borderRadius: 10, paddingVertical: 7, paddingHorizontal: 10, minWidth: 56 }}>
      <Text style={{ color: text, fontSize: 16, fontWeight: '800' }}>{value}</Text>
      <Text style={{ color: text, fontSize: 9.5, fontWeight: '600', opacity: 0.75 }}>{label}</Text>
    </View>
  );
}

export default function StaffStats() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin';

  const { data, isLoading, isRefetching, refetch, error } = useQuery({
    queryKey: ['staff-stats'],
    queryFn: fetchStaffStats,
    enabled: isAdmin,
    staleTime: 1000 * 60 * 5,
  });

  const items = data ?? [];
  const totalDocs = items.reduce((s, i) => s + i.total, 0);

  const renderItem = ({ item, index }: { item: typeof items[0]; index: number }) => {
    const pct = totalDocs > 0 ? Math.round((item.total / totalDocs) * 100) : 0;
    return (
      <View style={{
        backgroundColor: '#fff',
        borderRadius: 14,
        padding: 16,
        marginBottom: 10,
        borderWidth: 0.5,
        borderColor: '#E2E8F0',
      }}>
        {/* Top row */}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 14 }}>{item.username}</Text>
            <Text style={{ color: '#94A3B8', fontSize: 12, marginTop: 2 }}>{pct}% of all documents</Text>
          </View>
          <View style={{ backgroundColor: '#EFF6FF', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 5 }}>
            <Text style={{ color: '#0038A8', fontWeight: '800', fontSize: 16 }}>{item.total}</Text>
          </View>
        </View>

        {/* Progress bar */}
        <View style={{ backgroundColor: '#F1F5F9', borderRadius: 4, height: 6, marginBottom: 12 }}>
          <View style={{ backgroundColor: '#0038A8', borderRadius: 4, height: 6, width: `${pct}%` as any }} />
        </View>

        {/* Stat pills */}
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          <StatPill label="PENDING"  value={item.pending}  bg="#FEF3C7" text="#B45309" />
          <StatPill label="RECEIVED" value={item.received} bg="#DBEAFE" text="#1E40AF" />
          <StatPill label="RELEASED" value={item.released} bg="#D1FAE5" text="#065F46" />
          <StatPill label="OTHER"    value={item.other}    bg="#F1F5F9" text="#475569" />
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
          <Users size={20} color="#fff" />
          <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>Staff Statistics</Text>
        </View>
        <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 13, marginTop: 4 }}>
          {totalDocs} total documents · {items.length} staff member{items.length !== 1 ? 's' : ''}
        </Text>
      </View>

      {!isAdmin ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 40 }}>
          <Text style={{ fontSize: 36 }}>🔒</Text>
          <Text style={{ color: '#1E293B', fontSize: 16, fontWeight: '700', marginTop: 14, textAlign: 'center' }}>
            Admin Access Required
          </Text>
          <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 6, textAlign: 'center' }}>
            This screen is only available to administrators.
          </Text>
        </View>
      ) : isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
          <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 12 }}>Loading statistics…</Text>
        </View>
      ) : (error as any) ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 40 }}>
          <Text style={{ color: '#EF4444', fontSize: 14, textAlign: 'center' }}>Failed to load staff stats. Pull down to retry.</Text>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.username}
          renderItem={renderItem}
          contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#0038A8" />
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 72 }}>
              <Text style={{ fontSize: 36 }}>📊</Text>
              <Text style={{ color: '#1E293B', fontSize: 15, fontWeight: '700', marginTop: 14 }}>No data yet</Text>
              <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 6 }}>
                Stats will appear once documents are logged.
              </Text>
            </View>
          }
        />
      )}
    </View>
  );
}
