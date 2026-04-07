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
} from 'react-native';
import { useRouter } from 'expo-router';
import { Search } from 'lucide-react-native';
import { useDocuments } from '../../../hooks/useDocuments';
import { useNetwork } from '../../../hooks/useNetwork';
import { OfflineBanner } from '../../../components/ui/OfflineBanner';

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

function getStatus(status: string) {
  const key = status?.toLowerCase();
  return STATUS_CONFIG[key] ?? { bg: '#F1F5F9', text: '#475569', accent: '#94A3B8' };
}

const STATUS_FILTERS = ['All', 'Pending', 'Received', 'Released', 'Routed', 'On Hold'];

export default function Documents() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [activeFilter, setActiveFilter] = useState('All');
  const [searchInput, setSearchInput] = useState('');
  const { isOnline } = useNetwork();

  const { data, isLoading, isRefetching, refetch, isFromCache } = useDocuments(search, activeFilter);
  const docs = data?.documents ?? [];

  const handleSearch = () => setSearch(searchInput);

  const renderDoc = ({ item }: { item: any }) => {
    const s = getStatus(item.status);
    return (
      <TouchableOpacity
        onPress={() => router.push(`/(app)/documents/${item.id}`)}
        activeOpacity={0.75}
        style={{
          backgroundColor: '#fff',
          borderRadius: 14,
          padding: 16,
          marginBottom: 10,
          borderWidth: 0.5,
          borderColor: '#E2E8F0',
          flexDirection: 'row',
          alignItems: 'center',
          gap: 12,
        }}
      >
        {/* Left accent bar */}
        <View style={{
          width: 3, height: 44, borderRadius: 2,
          backgroundColor: s.accent, opacity: 0.6,
        }} />

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

        <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4, marginBottom: 14 }}>
          Documents
        </Text>

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

      {/* ── Result count ── */}
      <View style={{ paddingHorizontal: 20, paddingTop: 14, paddingBottom: 6, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={{ fontSize: 11, fontWeight: '700', color: '#0038A8', textTransform: 'uppercase', letterSpacing: 0.8 }}>
          {isLoading ? 'Loading...' : `${data?.total ?? 0} documents found`}
        </Text>
        {!isOnline && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
            <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: '#F87171' }} />
            <Text style={{ color: '#F87171', fontSize: 12, fontWeight: '600' }}>Offline</Text>
          </View>
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
          contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 4, paddingBottom: 16 }}
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
    </View>
  );
}