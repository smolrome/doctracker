import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAuthStore } from '../../lib/store';
import { useStats, useDocuments } from '../../hooks/useDocuments';
import { useNetwork } from '../../hooks/useNetwork';
import { OfflineBanner } from '../../components/ui/OfflineBanner';

const STAT_COLORS = [
  '#0038A8', '#F59E0B', '#10B981',
  '#3B82F6', '#8B5CF6', '#EC4899',
  '#06B6D4', '#EF4444',
];

export default function Dashboard() {
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const { isOnline } = useNetwork();

  const {
    data: stats,
    isLoading: statsLoading,
    refetch: refetchStats,
    isFromCache: statsFromCache,
  } = useStats();

  const {
    data: docsData,
    isLoading: docsLoading,
    refetch: refetchDocs,
    isFromCache: docsFromCache,
  } = useDocuments();

  const recentDocs = docsData?.documents?.slice(0, 5) ?? [];

  const handleLogout = async () => {
    await logout();
    router.replace('/(auth)/login');
  };

  const handleRefresh = () => {
    refetchStats();
    refetchDocs();
  };

  const statEntries = stats ? Object.entries(stats) : [];

  return (
    <View style={{ flex: 1, backgroundColor: '#F3F4F6', paddingBottom: 100 }}>
      <OfflineBanner />

      <View style={{
        backgroundColor: '#0038A8',
        paddingTop: 56,
        paddingBottom: 20,
        paddingHorizontal: 16,
      }}>
        <View style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}>
          <View>
            <Text style={{ color: '#93C5FD', fontSize: 13 }}>
              Welcome back,
            </Text>
            <Text style={{ color: '#fff', fontSize: 18, fontWeight: 'bold' }}>
              {user?.full_name || user?.username || 'User'}
            </Text>
            <Text style={{ color: '#93C5FD', fontSize: 12, marginTop: 2 }}>
              {user?.office || '—'}
            </Text>
          </View>
          <View style={{ alignItems: 'flex-end', gap: 6 }}>
            <View style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 4,
              backgroundColor: 'rgba(255,255,255,0.15)',
              borderRadius: 20,
              paddingHorizontal: 10,
              paddingVertical: 4,
            }}>
              <View style={{
                width: 8,
                height: 8,
                borderRadius: 4,
                backgroundColor: isOnline ? '#10B981' : '#EF4444',
              }} />
              <Text style={{ color: '#fff', fontSize: 11 }}>
                {isOnline ? 'Online' : 'Offline'}
              </Text>
            </View>
            <TouchableOpacity
              onPress={handleLogout}
              style={{
                backgroundColor: 'rgba(255,255,255,0.15)',
                borderRadius: 8,
                paddingHorizontal: 14,
                paddingVertical: 8,
              }}
            >
              <Text style={{ color: '#fff', fontSize: 13, fontWeight: '600' }}>
                Logout
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        {(statsFromCache || docsFromCache) && (
          <View style={{
            marginTop: 8,
            backgroundColor: 'rgba(255,255,255,0.1)',
            borderRadius: 8,
            padding: 8,
            flexDirection: 'row',
            alignItems: 'center',
            gap: 6,
          }}>
            <Text style={{ fontSize: 12 }}>💾</Text>
            <Text style={{ color: '#FCD34D', fontSize: 12 }}>
              Showing cached data — pull to refresh when online
            </Text>
          </View>
        )}
      </View>

      <ScrollView
        contentContainerStyle={{ padding: 16 }}
        refreshControl={
          <RefreshControl
            refreshing={statsLoading || docsLoading}
            onRefresh={handleRefresh}
          />
        }
      >
        <Text style={{
          fontWeight: '700',
          color: '#374151',
          fontSize: 15,
          marginBottom: 12,
        }}>
          Overview
        </Text>
        <View style={{
          flexDirection: 'row',
          flexWrap: 'wrap',
          marginBottom: 20,
          marginRight: -10,
        }}>
          {statEntries.map(([key, value], index) => (
            <View key={key} style={{
              backgroundColor: '#fff',
              borderRadius: 12,
              padding: 16,
              width: '47%',
              marginRight: 10,
              marginBottom: 10,
              borderLeftWidth: 4,
              borderLeftColor: STAT_COLORS[index % STAT_COLORS.length],
            }}>
              <Text style={{ fontSize: 28, fontWeight: 'bold', color: '#111' }}>
                {String(value)}
              </Text>
              <Text style={{
                color: '#6B7280',
                fontSize: 13,
                marginTop: 2,
                textTransform: 'capitalize',
              }}>
                {key.replace(/_/g, ' ')}
              </Text>
            </View>
          ))}
        </View>

        <View style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 12,
        }}>
          <Text style={{ fontWeight: '700', color: '#374151', fontSize: 15 }}>
            Recent Documents
          </Text>
          <TouchableOpacity onPress={() => router.push('/(app)/documents')}>
            <Text style={{ color: '#0038A8', fontSize: 13, fontWeight: '600' }}>
              View All →
            </Text>
          </TouchableOpacity>
        </View>

        {recentDocs.map((doc: any) => (
          <TouchableOpacity
            key={doc.id}
            onPress={() => router.push(`/(app)/documents/${doc.id}`)}
            style={{
              backgroundColor: '#fff',
              borderRadius: 12,
              padding: 14,
              marginBottom: 8,
            }}
          >
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ fontWeight: '600', color: '#111', fontSize: 13 }}>
                {doc.doc_id || doc.id}
              </Text>
              <Text style={{ color: '#6B7280', fontSize: 12 }}>
                {doc.status}
              </Text>
            </View>
            <Text style={{ color: '#6B7280', fontSize: 13, marginTop: 4 }} numberOfLines={1}>
              {doc.doc_name || '—'}
            </Text>
            <Text style={{ color: '#9CA3AF', fontSize: 11, marginTop: 2 }}>
              {doc.from_office || doc.sender_org || '—'}
            </Text>
          </TouchableOpacity>
        ))}

      </ScrollView>
    </View>
  );
}