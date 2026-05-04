import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, StatusBar, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Database, Server, CheckCircle, AlertCircle, Clock } from 'lucide-react-native';
import api from '../../lib/api';

type HealthData = {
  status: string;
  db_status: 'ok' | 'error' | 'json_fallback' | 'not_configured';
  db_error?: string;
  doc_count?: number;
  user_count?: number;
  server_time?: string;
};

function StatusBadge({ status }: { status: string }) {
  const ok = status === 'ok';
  const warn = status === 'json_fallback';
  const bg   = ok ? '#D1FAE5' : warn ? '#FEF3C7' : '#FEE2E2';
  const text = ok ? '#065F46' : warn ? '#B45309' : '#991B1B';
  const label = ok ? 'Connected' : warn ? 'JSON Mode' : status === 'not_configured' ? 'Not Configured' : 'Error';
  return (
    <View style={{ backgroundColor: bg, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 5 }}>
      <Text style={{ color: text, fontWeight: '700', fontSize: 12 }}>{label}</Text>
    </View>
  );
}

function StatCard({ label, value, icon }: { label: string; value: string | number | undefined; icon: React.ReactNode }) {
  return (
    <View style={{
      backgroundColor: '#fff', borderRadius: 14, padding: 16,
      borderWidth: 0.5, borderColor: '#E2E8F0', flex: 1,
      alignItems: 'center',
    }}>
      {icon}
      <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 26, marginTop: 8 }}>
        {value ?? '—'}
      </Text>
      <Text style={{ color: '#64748B', fontSize: 12, marginTop: 2 }}>{label}</Text>
    </View>
  );
}

export default function DbStatus() {
  const router = useRouter();

  const { data, isLoading, refetch, isRefetching, dataUpdatedAt } = useQuery({
    queryKey: ['db-health'],
    queryFn: async () => {
      const res = await api.get('/health');
      return res.data as HealthData;
    },
    staleTime: 1000 * 30,
    retry: 1,
  });

  const lastChecked = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : '—';

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#1E3A5F" />

      {/* Header */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
        <TouchableOpacity
          onPress={() => router.back()}
          style={{ marginBottom: 14, flexDirection: 'row', alignItems: 'center', gap: 6 }}
        >
          <ArrowLeft size={18} color="rgba(255,255,255,0.70)" />
          <Text style={{ color: 'rgba(255,255,255,0.70)', fontSize: 14, fontWeight: '600' }}>Back</Text>
        </TouchableOpacity>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Database size={20} color="#fff" />
          <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>
            System Status
          </Text>
        </View>
        <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 13, marginTop: 4 }}>
          Server & database health
        </Text>
      </View>

      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
          <Text style={{ color: '#94A3B8', marginTop: 12, fontSize: 13 }}>Checking server health…</Text>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#0038A8" />}
        >
          {/* API Status */}
          <View style={{
            backgroundColor: '#fff', borderRadius: 14, padding: 16,
            borderWidth: 0.5, borderColor: '#E2E8F0', marginBottom: 12,
          }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <Server size={18} color="#0038A8" />
                <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 15 }}>API Server</Text>
              </View>
              {data ? (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <CheckCircle size={16} color="#16A34A" />
                  <Text style={{ color: '#16A34A', fontWeight: '700', fontSize: 13 }}>Online</Text>
                </View>
              ) : (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <AlertCircle size={16} color="#DC2626" />
                  <Text style={{ color: '#DC2626', fontWeight: '700', fontSize: 13 }}>Offline</Text>
                </View>
              )}
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Clock size={13} color="#94A3B8" />
              <Text style={{ color: '#94A3B8', fontSize: 12 }}>
                Server time: {data?.server_time?.replace('T', ' ').slice(0, 19) || '—'}
              </Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 }}>
              <Clock size={13} color="#94A3B8" />
              <Text style={{ color: '#94A3B8', fontSize: 12 }}>Last checked: {lastChecked}</Text>
            </View>
          </View>

          {/* Database Status */}
          <View style={{
            backgroundColor: '#fff', borderRadius: 14, padding: 16,
            borderWidth: 0.5, borderColor: '#E2E8F0', marginBottom: 12,
          }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <Database size={18} color="#0038A8" />
                <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 15 }}>Database</Text>
              </View>
              {data && <StatusBadge status={data.db_status} />}
            </View>

            {data?.db_status === 'json_fallback' && (
              <View style={{
                backgroundColor: '#FFFBEB', borderRadius: 10, padding: 12,
                borderWidth: 1, borderColor: '#FDE68A', marginBottom: 12,
              }}>
                <Text style={{ color: '#B45309', fontSize: 12, fontWeight: '600' }}>
                  ⚠️ Running in JSON file mode — no PostgreSQL connection.
                </Text>
                <Text style={{ color: '#92400E', fontSize: 12, marginTop: 4 }}>
                  Data is stored in local JSON files. Configure DATABASE_URL for full database support.
                </Text>
              </View>
            )}

            {data?.db_status === 'error' && data?.db_error && (
              <View style={{
                backgroundColor: '#FEF2F2', borderRadius: 10, padding: 12,
                borderWidth: 1, borderColor: '#FECACA', marginBottom: 12,
              }}>
                <Text style={{ color: '#DC2626', fontSize: 12, fontWeight: '600' }}>Database Error:</Text>
                <Text style={{ color: '#991B1B', fontSize: 12, marginTop: 4, fontFamily: 'monospace' }}>
                  {data.db_error}
                </Text>
              </View>
            )}
          </View>

          {/* Stats cards */}
          <View style={{ flexDirection: 'row', gap: 12, marginBottom: 12 }}>
            <StatCard
              label="Active Documents"
              value={data?.doc_count}
              icon={<Text style={{ fontSize: 24 }}>📄</Text>}
            />
            <StatCard
              label="Active Users"
              value={data?.user_count}
              icon={<Text style={{ fontSize: 24 }}>👥</Text>}
            />
          </View>

          {/* Refresh button */}
          <TouchableOpacity
            onPress={() => refetch()}
            disabled={isRefetching}
            style={{
              backgroundColor: '#EFF6FF', borderRadius: 13,
              paddingVertical: 14, alignItems: 'center',
              borderWidth: 1, borderColor: '#BFDBFE',
            }}
          >
            <Text style={{ color: '#1E40AF', fontWeight: '700', fontSize: 14 }}>
              {isRefetching ? 'Refreshing…' : '↺  Refresh Status'}
            </Text>
          </TouchableOpacity>
        </ScrollView>
      )}
    </View>
  );
}
