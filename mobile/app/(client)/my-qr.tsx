import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StatusBar, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, QrCode, RefreshCw } from 'lucide-react-native';
import QRCode from 'react-native-qrcode-svg';
import api from '../../lib/api';
import { useAuthStore } from '../../lib/store';

async function fetchClientToken() {
  const res = await api.get('/client/qr-token');
  return res.data as { token?: string };
}

export default function MyQR() {
  const router = useRouter();
  const { user } = useAuthStore();

  const { data, isLoading, isRefetching, refetch, isError } = useQuery({
    queryKey: ['client-qr-token'],
    queryFn: fetchClientToken,
    staleTime: Infinity,   // the token is stable/permanent — never refetch needlessly
  });

  const token = data?.token;
  // Treat a missing/empty token as an error — never render <QRCode value=""/>.
  const showError = isError || (!isLoading && !token);

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* Header */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
        <TouchableOpacity
          onPress={() => router.back()}
          style={{ marginBottom: 14, flexDirection: 'row', alignItems: 'center', gap: 6 }}
        >
          <ArrowLeft size={18} color="rgba(255,255,255,0.70)" />
          <Text style={{ color: 'rgba(255,255,255,0.70)', fontSize: 14, fontWeight: '600' }}>Back</Text>
        </TouchableOpacity>
        <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800', letterSpacing: -0.3 }}>My QR Code</Text>
        <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 13, marginTop: 4 }}>
          Show this to staff at the counter
        </Text>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#0038A8" />}
      >
        {isLoading ? (
          <View style={{ alignItems: 'center', justifyContent: 'center', paddingVertical: 80 }}>
            <ActivityIndicator size="large" color="#0038A8" />
          </View>
        ) : showError ? (
          <View style={{
            backgroundColor: '#fff', borderRadius: 14, padding: 24,
            borderWidth: 0.5, borderColor: '#E2E8F0', alignItems: 'center',
          }}>
            <QrCode size={40} color="#CBD5E1" />
            <Text style={{ color: '#1E293B', fontSize: 15, fontWeight: '700', marginTop: 14, textAlign: 'center' }}>
              Your code isn&apos;t available right now
            </Text>
            <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 6, textAlign: 'center', paddingHorizontal: 8 }}>
              Pull down to refresh, or tap the button below to try again.
            </Text>
            <TouchableOpacity
              onPress={() => refetch()}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 8,
                backgroundColor: '#0038A8', borderRadius: 11,
                paddingHorizontal: 22, paddingVertical: 12, marginTop: 18,
              }}
            >
              <RefreshCw size={16} color="#fff" />
              <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>Try Again</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={{
            backgroundColor: '#fff', borderRadius: 14, padding: 20,
            borderWidth: 0.5, borderColor: '#E2E8F0', alignItems: 'center',
          }}>
            {/* Client identity — eyeballable by staff while scanning */}
            <Text style={{ color: '#1E293B', fontSize: 22, fontWeight: '800', textAlign: 'center', letterSpacing: -0.3 }}>
              {user?.full_name || user?.username || 'Client'}
            </Text>
            <Text style={{ color: '#64748B', fontSize: 14, marginTop: 4, marginBottom: 20 }}>
              @{user?.username}
            </Text>

            {/* QR — rendered on-device from the token string, on white padding so it scans well */}
            <View style={{
              backgroundColor: '#fff', padding: 20, borderRadius: 12,
              borderWidth: 1, borderColor: '#E2E8F0',
            }}>
              <QRCode value={token} size={260} />
            </View>

            <Text style={{ color: '#64748B', fontSize: 13, textAlign: 'center', marginTop: 20, paddingHorizontal: 8, lineHeight: 19 }}>
              Show this code to staff to submit or receive your documents.
            </Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
}
