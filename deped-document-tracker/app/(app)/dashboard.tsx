import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  Animated,
  StatusBar,
  Dimensions,
} from 'react-native';
import { useRef, useEffect } from 'react';
import { useRouter } from 'expo-router';
import { useAuthStore } from '../../lib/store';
import { useStats, useDocuments } from '../../hooks/useDocuments';
import { useNetwork } from '../../hooks/useNetwork';
import { OfflineBanner } from '../../components/ui/OfflineBanner';

const { width } = Dimensions.get('window');

// Status badge config
const STATUS_CONFIG: Record<string, { bg: string; text: string; label: string }> = {
  pending:    { bg: '#FEF3C7', text: '#B45309', label: 'Pending' },
  approved:   { bg: '#D1FAE5', text: '#065F46', label: 'Approved' },
  rejected:   { bg: '#FEE2E2', text: '#991B1B', label: 'Rejected' },
  forwarded:  { bg: '#EDE9FE', text: '#5B21B6', label: 'Forwarded' },
  received:   { bg: '#DBEAFE', text: '#1E40AF', label: 'Received' },
  released:   { bg: '#D1FAE5', text: '#065F46', label: 'Released' },
};

// Stat card accent colors (blue-first, PH palette-aware)
const STAT_ACCENTS = [
  '#0038A8', '#10B981', '#F59E0B', '#8B5CF6',
  '#3B82F6', '#EC4899', '#06B6D4', '#EF4444',
];

function getStatusStyle(status: string) {
  const key = status?.toLowerCase();
  return STATUS_CONFIG[key] ?? { bg: '#F1F5F9', text: '#475569', label: status };
}

export default function Dashboard() {
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const { isOnline } = useNetwork();

  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(16)).current;

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

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, { toValue: 1, duration: 500, useNativeDriver: true }),
      Animated.spring(slideAnim, { toValue: 0, tension: 65, friction: 12, useNativeDriver: true }),
    ]).start();
  }, []);

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
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />
      <OfflineBanner />

      {/* ── Hero header ── */}
      <View style={{
        backgroundColor: '#0038A8',
        paddingTop: 56,
        paddingBottom: 28,
        paddingHorizontal: 20,
        overflow: 'hidden',
      }}>
        {/* Subtle grid texture */}
        {[...Array(4)].map((_, i) => (
          <View key={`h${i}`} style={{
            position: 'absolute',
            top: (i + 1) * 28,
            left: 0, right: 0, height: 1,
            backgroundColor: '#fff', opacity: 0.05,
          }} />
        ))}
        {[...Array(4)].map((_, i) => (
          <View key={`v${i}`} style={{
            position: 'absolute',
            left: (i + 1) * (width / 5),
            top: 0, bottom: 0, width: 1,
            backgroundColor: '#fff', opacity: 0.05,
          }} />
        ))}

        {/* Yellow accent circle */}
        <View style={{
          position: 'absolute', top: -36, right: -36,
          width: 140, height: 140, borderRadius: 70,
          backgroundColor: '#FCD116', opacity: 0.10,
        }} />

        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <View style={{ flex: 1, marginRight: 12 }}>
            <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 12.5, marginBottom: 3 }}>
              Welcome back,
            </Text>
            <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800', letterSpacing: -0.3 }}>
              {user?.full_name || user?.username || 'User'}
            </Text>
            <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 12.5, marginTop: 3 }}>
              {user?.office || '—'}
            </Text>
          </View>

          <View style={{ alignItems: 'flex-end', gap: 8 }}>
            {/* Online / offline pill */}
            <View style={{
              flexDirection: 'row', alignItems: 'center', gap: 5,
              backgroundColor: 'rgba(255,255,255,0.15)',
              borderRadius: 20, paddingHorizontal: 10, paddingVertical: 5,
            }}>
              <View style={{
                width: 7, height: 7, borderRadius: 4,
                backgroundColor: isOnline ? '#34D399' : '#F87171',
              }} />
              <Text style={{ color: '#fff', fontSize: 11, fontWeight: '500' }}>
                {isOnline ? 'Online' : 'Offline'}
              </Text>
            </View>

            {/* Logout */}
            <TouchableOpacity
              onPress={handleLogout}
              style={{
                borderWidth: 1, borderColor: 'rgba(255,255,255,0.30)',
                borderRadius: 8, paddingHorizontal: 14, paddingVertical: 7,
              }}
            >
              <Text style={{ color: '#fff', fontSize: 12.5, fontWeight: '600' }}>Logout</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Cached data notice */}
        {(statsFromCache || docsFromCache) && (
          <View style={{
            marginTop: 14,
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

      {/* ── Content zone ── */}
      <Animated.View style={{
        flex: 1,
        opacity: fadeAnim,
        transform: [{ translateY: slideAnim }],
      }}>
        <ScrollView
          contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 24, paddingBottom: 120 }}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={statsLoading || docsLoading}
              onRefresh={handleRefresh}
              tintColor="#0038A8"
            />
          }
        >
          {/* Overview */}
          <Text style={{
            fontSize: 13, fontWeight: '700', color: '#0038A8',
            textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 14,
          }}>
            Overview
          </Text>

          <View style={{
            flexDirection: 'row', flexWrap: 'wrap',
            marginBottom: 28, gap: 10,
          }}>
            {statEntries.map(([key, value], index) => (
              <View key={key} style={{
                backgroundColor: '#fff',
                borderRadius: 14,
                padding: 16,
                width: (width - 50) / 2,
                borderLeftWidth: 4,
                borderLeftColor: STAT_ACCENTS[index % STAT_ACCENTS.length],
                borderWidth: 0.5,
                borderColor: '#E2E8F0',
              }}>
                <Text style={{
                  fontSize: 30, fontWeight: '800',
                  color: STAT_ACCENTS[index % STAT_ACCENTS.length],
                  letterSpacing: -1,
                }}>
                  {String(value)}
                </Text>
                <Text style={{
                  color: '#64748B', fontSize: 12.5, marginTop: 4,
                  textTransform: 'capitalize',
                }}>
                  {key.replace(/_/g, ' ')}
                </Text>
              </View>
            ))}
          </View>

          {/* Recent documents */}
          <View style={{
            flexDirection: 'row', justifyContent: 'space-between',
            alignItems: 'center', marginBottom: 14,
          }}>
            <Text style={{
              fontSize: 13, fontWeight: '700', color: '#0038A8',
              textTransform: 'uppercase', letterSpacing: 0.8,
            }}>
              Recent Documents
            </Text>
            <TouchableOpacity onPress={() => router.push('/(app)/documents')}>
              <Text style={{ color: '#0038A8', fontSize: 13, fontWeight: '700' }}>
                View All →
              </Text>
            </TouchableOpacity>
          </View>

          {recentDocs.map((doc: any) => (
            <TouchableOpacity
              key={doc.id}
              onPress={() => router.push(`/(app)/documents/${doc.id}`)}
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
                width: 3, height: 40, borderRadius: 2,
                backgroundColor: getStatusStyle(doc.status).text,
                opacity: 0.5,
              }} />

              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <Text style={{ fontWeight: '700', color: '#1E293B', fontSize: 13.5 }}>
                    {doc.doc_id || doc.id}
                  </Text>
                  {/* Status badge */}
                  <View style={{
                    backgroundColor: getStatusStyle(doc.status).bg,
                    borderRadius: 20, paddingHorizontal: 9, paddingVertical: 3,
                  }}>
                    <Text style={{
                      color: getStatusStyle(doc.status).text,
                      fontSize: 11, fontWeight: '700',
                    }}>
                      {getStatusStyle(doc.status).label}
                    </Text>
                  </View>
                </View>

                <Text style={{ color: '#475569', fontSize: 12.5, marginBottom: 2 }} numberOfLines={1}>
                  {doc.doc_name || '—'}
                </Text>
                <Text style={{ color: '#94A3B8', fontSize: 11.5 }}>
                  {doc.from_office || doc.sender_org || '—'}
                </Text>
              </View>
            </TouchableOpacity>
          ))}

        </ScrollView>
      </Animated.View>
    </View>
  );
}