import { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '../../lib/store';
import { cache } from '../../lib/cache';
import api from '../../lib/api';

async function fetchActivityLog() {
  const res = await api.get('/activity-log', { params: { limit: 10 } });
  return res.data;
}

export default function Profile() {
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const [lastSync, setLastSync] = useState<string | null>(null);

  useEffect(() => {
    cache.getLastSync().then(setLastSync);
  }, []);

  const handleClearCache = async () => {
    Alert.alert(
      'Clear Cache',
      'This will remove all offline data. You need internet to reload.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Clear',
          style: 'destructive',
          onPress: async () => {
            await cache.clearAll();
            setLastSync(null);
            Alert.alert('Done', 'Cache cleared successfully');
          }
        }
      ]
    );
  };

  const { data: logs } = useQuery({
    queryKey: ['activity-log'],
    queryFn: fetchActivityLog,
  });

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'Are you sure you want to logout?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Logout',
          style: 'destructive',
          onPress: async () => {
            await logout();
            router.replace('/(auth)/login');
          }
        }
      ]
    );
  };

  const getRoleBadgeColor = (role: string) => {
    switch (role) {
      case 'admin': return '#CE1126';
      case 'staff': return '#0038A8';
      default: return '#6B7280';
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: '#F3F4F6', paddingBottom: 100 }}>

      {/* Header */}
      <View style={{
        backgroundColor: '#0038A8',
        paddingTop: 56,
        paddingBottom: 30,
        paddingHorizontal: 16,
        alignItems: 'center',
      }}>
        {/* Avatar */}
        <View style={{
          width: 72,
          height: 72,
          borderRadius: 36,
          backgroundColor: 'rgba(255,255,255,0.2)',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 12,
        }}>
          <Text style={{ fontSize: 28, color: '#fff', fontWeight: 'bold' }}>
            {user?.full_name?.charAt(0)?.toUpperCase() || 'U'}
          </Text>
        </View>

        <Text style={{ color: '#fff', fontSize: 20, fontWeight: 'bold' }}>
          {user?.full_name || user?.username}
        </Text>

        <Text style={{ color: '#93C5FD', fontSize: 13, marginTop: 4 }}>
          {user?.office || '—'}
        </Text>

        {/* Role badge */}
        <View style={{
          marginTop: 8,
          backgroundColor: getRoleBadgeColor(user?.role || ''),
          borderRadius: 20,
          paddingHorizontal: 14,
          paddingVertical: 4,
        }}>
          <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700', textTransform: 'uppercase' }}>
            {user?.role || 'user'}
          </Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16 }}>

        {/* Account Info */}
        <View style={{
          backgroundColor: '#fff',
          borderRadius: 12,
          padding: 16,
          marginBottom: 12,
        }}>
          <Text style={{ fontWeight: '700', color: '#0038A8', fontSize: 15, marginBottom: 12 }}>
            Account Info
          </Text>
          {[
            ['Username', user?.username || '—'],
            ['Full Name', user?.full_name || '—'],
            ['Role', user?.role || '—'],
            ['Office', user?.office || '—'],
          ].map(([label, value]) => (
            <View key={label} style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              paddingVertical: 8,
              borderBottomWidth: 1,
              borderBottomColor: '#F3F4F6',
            }}>
              <Text style={{ color: '#6B7280', fontSize: 13 }}>{label}</Text>
              <Text style={{
                color: '#111',
                fontSize: 13,
                fontWeight: '500',
                maxWidth: '60%',
                textAlign: 'right',
              }}>
                {value}
              </Text>
            </View>
          ))}
        </View>

        {/* Quick Actions */}
        <View style={{
          backgroundColor: '#fff',
          borderRadius: 12,
          padding: 16,
          marginBottom: 12,
        }}>
          <Text style={{ fontWeight: '700', color: '#0038A8', fontSize: 15, marginBottom: 12 }}>
            Quick Actions
          </Text>

          <TouchableOpacity
            onPress={() => router.push('/(app)/documents')}
            style={styles.actionRow}
          >
            <Text style={{ fontSize: 20 }}>📄</Text>
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={{ fontWeight: '600', color: '#111', fontSize: 14 }}>
                All Documents
              </Text>
              <Text style={{ color: '#6B7280', fontSize: 12 }}>
                Browse and search documents
              </Text>
            </View>
            <Text style={{ color: '#9CA3AF' }}>›</Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => router.push('/(app)/scanner')}
            style={styles.actionRow}
          >
            <Text style={{ fontSize: 20 }}>📷</Text>
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={{ fontWeight: '600', color: '#111', fontSize: 14 }}>
                Scan QR Code
              </Text>
              <Text style={{ color: '#6B7280', fontSize: 12 }}>
                Quick document lookup
              </Text>
            </View>
            <Text style={{ color: '#9CA3AF' }}>›</Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => router.push('/(app)/dashboard')}
            style={[styles.actionRow, { borderBottomWidth: 0 }]}
          >
            <Text style={{ fontSize: 20 }}>📊</Text>
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={{ fontWeight: '600', color: '#111', fontSize: 14 }}>
                Dashboard
              </Text>
              <Text style={{ color: '#6B7280', fontSize: 12 }}>
                View stats overview
              </Text>
            </View>
            <Text style={{ color: '#9CA3AF' }}>›</Text>
          </TouchableOpacity>
        </View>

        {/* Recent Activity */}
        {logs && logs.length > 0 && (
          <View style={{
            backgroundColor: '#fff',
            borderRadius: 12,
            padding: 16,
            marginBottom: 12,
          }}>
            <Text style={{ fontWeight: '700', color: '#0038A8', fontSize: 15, marginBottom: 12 }}>
              Recent Activity
            </Text>
            {logs.slice(0, 5).map((log: any, index: number) => (
              <View key={index} style={{
                paddingVertical: 8,
                borderBottomWidth: index < 4 ? 1 : 0,
                borderBottomColor: '#F3F4F6',
              }}>
                <Text style={{ color: '#111', fontSize: 13, fontWeight: '500' }}>
                  {log.action || log.event || '—'}
                </Text>
                <Text style={{ color: '#9CA3AF', fontSize: 11, marginTop: 2 }}>
                  {log.timestamp?.slice(0, 16)?.replace('T', ' ') || '—'}
                </Text>
              </View>
            ))}
          </View>
        )}

        {/* App Info */}
        <View style={{
          backgroundColor: '#fff',
          borderRadius: 12,
          padding: 16,
          marginBottom: 12,
        }}>
          <Text style={{ fontWeight: '700', color: '#0038A8', fontSize: 15, marginBottom: 12 }}>
            App Info
          </Text>
          {[
            ['App', 'DepEd Document Tracker'],
            ['Division', 'DepEd Leyte Division'],
            ['Unit', 'Personnel Unit'],
            ['Version', '1.0.0'],
          ].map(([label, value]) => (
            <View key={label} style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              paddingVertical: 6,
              borderBottomWidth: 1,
              borderBottomColor: '#F3F4F6',
            }}>
              <Text style={{ color: '#6B7280', fontSize: 13 }}>{label}</Text>
              <Text style={{ color: '#111', fontSize: 13 }}>{value}</Text>
            </View>
          ))}
        </View>

        {/* Offline Cache */}
        <View style={{
          backgroundColor: '#fff',
          borderRadius: 12,
          padding: 16,
          marginBottom: 12,
        }}>
          <Text style={{ fontWeight: '700', color: '#0038A8', fontSize: 15, marginBottom: 12 }}>
            Offline Cache
          </Text>
          <View style={{
            flexDirection: 'row',
            justifyContent: 'space-between',
            paddingVertical: 8,
            borderBottomWidth: 1,
            borderBottomColor: '#F3F4F6',
          }}>
            <Text style={{ color: '#6B7280', fontSize: 13 }}>Last Synced</Text>
            <Text style={{ color: '#111', fontSize: 13 }}>
              {lastSync
                ? new Date(lastSync).toLocaleString()
                : 'Never'}
            </Text>
          </View>
          <TouchableOpacity
            onPress={handleClearCache}
            style={{
              marginTop: 12,
              backgroundColor: '#FEE2E2',
              borderRadius: 8,
              padding: 10,
              alignItems: 'center',
            }}
          >
            <Text style={{ color: '#DC2626', fontWeight: '600', fontSize: 13 }}>
              Clear Offline Cache
            </Text>
          </TouchableOpacity>
        </View>

        {/* Logout Button */}
        <TouchableOpacity
          onPress={handleLogout}
          style={{
            backgroundColor: '#FEE2E2',
            borderRadius: 12,
            padding: 16,
            alignItems: 'center',
            marginBottom: 32,
          }}
        >
          <Text style={{ color: '#DC2626', fontWeight: '700', fontSize: 15 }}>
            Logout
          </Text>
        </TouchableOpacity>

      </ScrollView>
    </View>
  );
}

const styles = {
  actionRow: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#F3F4F6',
  },
};