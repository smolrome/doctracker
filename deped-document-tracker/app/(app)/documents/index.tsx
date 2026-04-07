import { useState } from 'react';
import {
  View,
  Text,
  FlatList,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useDocuments } from '../../../hooks/useDocuments';
import { useNetwork } from '../../../hooks/useNetwork';
import { OfflineBanner } from '../../../components/ui/OfflineBanner';

const STATUS_COLORS: Record<string, string> = {
  Pending:     '#F59E0B',
  Received:    '#10B981',
  Released:    '#3B82F6',
  Routed:      '#8B5CF6',
  'In Review': '#6366F1',
  Transferred: '#06B6D4',
  'On Hold':   '#EF4444',
};

const STATUS_FILTERS = [
  'All', 'Pending', 'Received', 'Released', 'Routed', 'On Hold'
];

export default function Documents() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [activeFilter, setActiveFilter] = useState('All');
  const [searchInput, setSearchInput] = useState('');
  const { isOnline } = useNetwork();

  const {
    data,
    isLoading,
    isRefetching,
    refetch,
    isFromCache,
  } = useDocuments(search, activeFilter);

  const docs = data?.documents ?? [];

  const handleSearch = () => {
    setSearch(searchInput);
  };

  const renderDoc = ({ item }: { item: any }) => (
    <TouchableOpacity
      onPress={() => router.push(`/(app)/documents/${item.id}`)}
      style={{
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 16,
        marginBottom: 10,
        shadowColor: '#000',
        shadowOpacity: 0.05,
        shadowRadius: 4,
        elevation: 2,
      }}
    >
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
        <Text style={{ fontWeight: '700', color: '#111', fontSize: 13 }}>
          {item.doc_id || item.id?.slice(0, 8).toUpperCase()}
        </Text>
        <View style={{
          backgroundColor: STATUS_COLORS[item.status] ?? '#9CA3AF',
          borderRadius: 20,
          paddingHorizontal: 10,
          paddingVertical: 2,
        }}>
          <Text style={{ color: '#fff', fontSize: 11, fontWeight: '600' }}>
            {item.status}
          </Text>
        </View>
      </View>

      <Text style={{ color: '#374151', fontSize: 14, marginBottom: 4 }} numberOfLines={2}>
        {item.doc_name || 'No name'}
      </Text>

      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 }}>
        <Text style={{ color: '#9CA3AF', fontSize: 12 }}>
          {item.from_office || item.sender_org || '—'}
        </Text>
        <Text style={{ color: '#9CA3AF', fontSize: 12 }}>
          {item.doc_date || item.created_at?.slice(0, 10) || '—'}
        </Text>
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={{ flex: 1, backgroundColor: '#F3F4F6', paddingBottom: 100 }}>
      <OfflineBanner />

      <View style={{
        backgroundColor: '#0038A8',
        paddingTop: 56,
        paddingBottom: 16,
        paddingHorizontal: 16,
      }}>
        <Text style={{ color: '#fff', fontSize: 20, fontWeight: 'bold', marginBottom: 12 }}>
          Documents
        </Text>

        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TextInput
            value={searchInput}
            onChangeText={setSearchInput}
            onSubmitEditing={handleSearch}
            placeholder="Search..."
            placeholderTextColor="#93C5FD"
            style={{
              flex: 1,
              backgroundColor: 'rgba(255,255,255,0.15)',
              borderRadius: 10,
              paddingHorizontal: 14,
              paddingVertical: 10,
              color: '#fff',
              fontSize: 14,
            }}
          />
          <TouchableOpacity
            onPress={handleSearch}
            style={{
              backgroundColor: '#fff',
              borderRadius: 10,
              paddingHorizontal: 14,
              justifyContent: 'center',
            }}
          >
            <Text style={{ color: '#0038A8', fontWeight: '600' }}>Go</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={{ backgroundColor: '#fff', paddingVertical: 10 }}>
        <FlatList
          horizontal
          data={STATUS_FILTERS}
          keyExtractor={(i) => i}
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ paddingHorizontal: 12, gap: 8 }}
          renderItem={({ item }) => (
            <TouchableOpacity
              onPress={() => setActiveFilter(item)}
              style={{
                paddingHorizontal: 16,
                paddingVertical: 6,
                borderRadius: 20,
                backgroundColor: activeFilter === item ? '#0038A8' : '#F3F4F6',
              }}
            >
              <Text style={{
                color: activeFilter === item ? '#fff' : '#6B7280',
                fontWeight: '600',
                fontSize: 13,
              }}>
                {item}
              </Text>
            </TouchableOpacity>
          )}
        />
      </View>

      <View style={{ paddingHorizontal: 16, paddingVertical: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={{ color: '#6B7280', fontSize: 13 }}>
          {isLoading ? 'Loading...' : `${data?.total ?? 0} documents found`}
        </Text>
        {!isOnline && (
          <Text style={{ color: '#F59E0B', fontSize: 12 }}>Offline</Text>
        )}
      </View>

      {isFromCache && (
        <View style={{ paddingHorizontal: 16, paddingBottom: 8 }}>
          <Text style={{ color: '#FCD34D', fontSize: 12 }}>
            💾 Cached data — connect to refresh
          </Text>
        </View>
      )}

      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
        </View>
      ) : (
        <FlatList
          data={docs}
          keyExtractor={(item) => item.id}
          renderItem={renderDoc}
          contentContainerStyle={{ padding: 16, paddingTop: 4 }}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} />
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 60 }}>
              <Text style={{ fontSize: 40 }}>📄</Text>
              <Text style={{ color: '#9CA3AF', marginTop: 12, fontSize: 15 }}>
                No documents found
              </Text>
            </View>
          }
        />
      )}
    </View>
  );
}