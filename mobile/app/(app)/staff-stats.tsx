import { useState, useMemo } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  StatusBar,
  TextInput,
  ScrollView,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Users, Search } from 'lucide-react-native';
import api from '../../lib/api';
import { useAuthStore } from '../../lib/store';

type StaffStat = {
  username: string;
  full_name: string;
  office: string;
  total: number;
  pending: number;
  received: number;
  released: number;
  other: number;
};

async function fetchStaffStats() {
  const res = await api.get('/staff-stats');
  return (res.data ?? []) as StaffStat[];
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

  const [search, setSearch] = useState('');
  const [officeFilter, setOfficeFilter] = useState('All');

  const { data, isLoading, isRefetching, refetch, error } = useQuery({
    queryKey: ['staff-stats'],
    queryFn: fetchStaffStats,
    enabled: isAdmin,
    staleTime: 1000 * 60 * 5,
  });

  const allItems = data ?? [];

  // Unique sorted office list for pills
  const offices = useMemo(() => {
    const seen = new Set<string>();
    const list: string[] = [];
    for (const item of allItems) {
      const o = item.office?.trim() || '';
      if (o && !seen.has(o)) { seen.add(o); list.push(o); }
    }
    return list.sort();
  }, [allItems]);

  // Apply search + office filter
  const items = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allItems.filter((item) => {
      const matchOffice = officeFilter === 'All' || (item.office?.trim() || '') === officeFilter;
      if (!matchOffice) return false;
      if (!q) return true;
      return (
        (item.full_name || '').toLowerCase().includes(q) ||
        item.username.toLowerCase().includes(q) ||
        (item.office || '').toLowerCase().includes(q)
      );
    });
  }, [allItems, search, officeFilter]);

  const totalDocs = allItems.reduce((s, i) => s + i.total, 0);

  const renderItem = ({ item }: { item: StaffStat }) => {
    const pct = totalDocs > 0 ? Math.round((item.total / totalDocs) * 100) : 0;
    const displayName = item.full_name || item.username;
    const officeLabel = item.office?.trim() || 'No office assigned';

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
          <View style={{ flex: 1, marginRight: 12 }}>
            <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 14 }}>{displayName}</Text>
            <Text style={{ color: '#64748B', fontSize: 12, marginTop: 2 }}>{officeLabel}</Text>
            <Text style={{ color: '#94A3B8', fontSize: 11, marginTop: 1 }}>{pct}% of all documents</Text>
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
          {totalDocs} total documents · {allItems.length} staff member{allItems.length !== 1 ? 's' : ''}
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
          ListHeaderComponent={
            <View style={{ marginBottom: 14 }}>
              {/* Search bar */}
              <View style={{
                flexDirection: 'row', alignItems: 'center', gap: 10,
                backgroundColor: '#fff', borderRadius: 12,
                borderWidth: 1, borderColor: '#E2E8F0',
                paddingHorizontal: 12, marginBottom: 10,
              }}>
                <Search size={15} color="#94A3B8" />
                <TextInput
                  value={search}
                  onChangeText={setSearch}
                  placeholder="Search by name, username, or office…"
                  placeholderTextColor="#CBD5E1"
                  style={{ flex: 1, paddingVertical: 11, fontSize: 14, color: '#1E293B' }}
                />
              </View>

              {/* Office filter pills */}
              {offices.length > 0 && (
                <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 4 }}>
                  <View style={{ flexDirection: 'row', gap: 8, paddingRight: 4 }}>
                    {['All', ...offices].map((office) => {
                      const active = officeFilter === office;
                      return (
                        <TouchableOpacity
                          key={office}
                          onPress={() => setOfficeFilter(office)}
                          style={{
                            paddingHorizontal: 14, paddingVertical: 7,
                            borderRadius: 20,
                            backgroundColor: active ? '#0038A8' : '#fff',
                            borderWidth: 1,
                            borderColor: active ? '#0038A8' : '#E2E8F0',
                          }}
                        >
                          <Text style={{
                            fontSize: 12.5, fontWeight: '600',
                            color: active ? '#fff' : '#64748B',
                          }}>
                            {office}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </ScrollView>
              )}

              {/* Result count when filtering */}
              {(search.trim() || officeFilter !== 'All') && (
                <Text style={{ color: '#94A3B8', fontSize: 12, marginTop: 6 }}>
                  {items.length} result{items.length !== 1 ? 's' : ''}
                </Text>
              )}
            </View>
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 48 }}>
              <Text style={{ fontSize: 36 }}>📊</Text>
              <Text style={{ color: '#1E293B', fontSize: 15, fontWeight: '700', marginTop: 14 }}>
                {search.trim() || officeFilter !== 'All' ? 'No results found' : 'No data yet'}
              </Text>
              <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 6, textAlign: 'center' }}>
                {search.trim() || officeFilter !== 'All'
                  ? 'Try a different search or office filter.'
                  : 'Stats will appear once documents are logged.'}
              </Text>
            </View>
          }
        />
      )}
    </View>
  );
}
