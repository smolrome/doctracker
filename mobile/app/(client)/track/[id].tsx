import { useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StatusBar, Alert, RefreshControl, Image,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Trash2, Download, QrCode } from 'lucide-react-native';
import * as Sharing from 'expo-sharing';
import * as Print from 'expo-print';
import api from '../../../lib/api';
import { ConfirmDialog } from '../../../components/ui/ConfirmDialog';

async function fetchQR(docId: string) {
  const res = await api.get(`/qr/generate/${docId}`);
  return res.data as { qr_base64: string };
}

const STATUS_CONFIG: Record<string, { bg: string; text: string }> = {
  pending:     { bg: '#FEF3C7', text: '#B45309' },
  received:    { bg: '#DBEAFE', text: '#1E40AF' },
  released:    { bg: '#D1FAE5', text: '#065F46' },
  routed:      { bg: '#EDE9FE', text: '#5B21B6' },
  'in review': { bg: '#E0E7FF', text: '#3730A3' },
  'on hold':   { bg: '#FEE2E2', text: '#991B1B' },
  rejected:    { bg: '#FEE2E2', text: '#991B1B' },
};
function getStatus(s: string) {
  return STATUS_CONFIG[s?.toLowerCase()] ?? { bg: '#F1F5F9', text: '#475569' };
}

function formatDate(ts?: string) {
  if (!ts) return '—';
  return ts.replace('T', ' ').slice(0, 16);
}

export default function TrackDocument() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [confirmVisible, setConfirmVisible] = useState(false);

  const { data: doc, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['client-doc', id],
    queryFn: async () => {
      const res = await api.get(`/documents/${id}`);
      return res.data;
    },
    staleTime: 1000 * 30,
  });

  const { data: qrData, isLoading: qrLoading } = useQuery({
    queryKey: ['qr', id],
    queryFn: () => fetchQR(id!),
    enabled: !!id,
    staleTime: 1000 * 60 * 10,
  });

  const docStatus = (doc?.status || '').toLowerCase();
  const isRejected = docStatus === 'rejected';
  const isPending  = docStatus === 'pending';
  const canDelete  = isRejected || isPending;

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/client/documents/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['client-docs'] });
      queryClient.invalidateQueries({ queryKey: ['client-docs-all'] });
      router.back();
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to remove document.'),
  });

  const handleDownloadQR = async () => {
    if (!qrData?.qr_base64) { Alert.alert('No QR', 'QR code not available yet.'); return; }
    try {
      const dataUri = qrData.qr_base64.startsWith('data:')
        ? qrData.qr_base64
        : `data:image/png;base64,${qrData.qr_base64}`;

      const { uri } = await Print.printToFileAsync({
        html: `
          <html>
            <body style="margin:0;padding:40px;text-align:center;font-family:sans-serif;background:#fff;">
              <p style="color:#0038A8;font-size:11px;font-weight:700;text-transform:uppercase;
                        letter-spacing:1px;margin:0 0 8px;">DepEd LAKAD</p>
              <h2 style="color:#1E293B;font-size:18px;margin:0 0 6px;line-height:1.4;">
                ${doc?.doc_name || 'Document'}
              </h2>
              <p style="color:#0038A8;font-size:13px;font-weight:700;
                        letter-spacing:1px;margin:0 0 24px;">#${doc?.doc_id || id}</p>
              <img src="${dataUri}" width="220" height="220"
                   style="display:block;margin:0 auto 20px;" />
              <p style="color:#64748B;font-size:12px;margin:0;">
                Scan this QR code to track your document
              </p>
            </body>
          </html>
        `,
      });

      const canShare = await Sharing.isAvailableAsync();
      if (canShare) {
        await Sharing.shareAsync(uri, {
          mimeType: 'application/pdf',
          dialogTitle: `QR Code — ${doc?.doc_id || id}`,
          UTI: 'com.adobe.pdf',
        });
      } else {
        Alert.alert('Saved', `QR code saved to: ${uri}`);
      }
    } catch (err: any) {
      console.error('[QR Save]', err);
      Alert.alert('Error', err?.message || 'Could not save QR code. Please try again.');
    }
  };

  const status = getStatus(doc?.status ?? '');
  const travelLog: any[] = doc?.travel_log ?? [];

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
          <Text style={{ color: 'rgba(255,255,255,0.70)', fontSize: 14, fontWeight: '600' }}>My Documents</Text>
        </TouchableOpacity>
        <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800', letterSpacing: -0.3 }}>Track Document</Text>
        {doc?.doc_id ? (
          <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 13, marginTop: 4 }}>Ref: #{doc.doc_id}</Text>
        ) : null}
      </View>

      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
        </View>
      ) : !doc ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <Text style={{ color: '#94A3B8', fontSize: 15 }}>Document not found.</Text>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#0038A8" />}
        >
          {/* Status card */}
          <View style={{
            backgroundColor: '#fff', borderRadius: 14, padding: 20,
            borderWidth: 0.5, borderColor: '#E2E8F0', marginBottom: 12,
          }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
              <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 16, flex: 1, marginRight: 10 }}>
                {doc.doc_name}
              </Text>
              <View style={{ backgroundColor: status.bg, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 6 }}>
                <Text style={{ color: status.text, fontWeight: '800', fontSize: 13 }}>{doc.status}</Text>
              </View>
            </View>

            <View style={{ gap: 8 }}>
              {[
                ['Reference', `#${doc.doc_id || '—'}`],
                ['Type', doc.category || '—'],
                ['Referred To', doc.referred_to || '—'],
                ['From Office', doc.sender_org || '—'],
                ['Submitted', formatDate(doc.created_at)],
                ['Last Updated', formatDate(doc.updated_at)],
                ...(doc.remarks ? [['Remarks', doc.remarks]] : []),
                ...(doc.description ? [['Description', doc.description]] : []),
                ...(doc.notes ? [['Notes', doc.notes]] : []),
              ].map(([label, value]) => (
                <View key={label} style={{ flexDirection: 'row' }}>
                  <Text style={{ color: '#94A3B8', fontSize: 13, width: 110 }}>{label}</Text>
                  <Text style={{ color: '#1E293B', fontSize: 13, fontWeight: '600', flex: 1 }}>{String(value)}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* QR Code card */}
          <View style={{
            backgroundColor: '#fff', borderRadius: 14, padding: 20,
            borderWidth: 0.5, borderColor: '#E2E8F0', marginBottom: 12,
            alignItems: 'center',
          }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, alignSelf: 'flex-start', marginBottom: 16 }}>
              <QrCode size={16} color="#0038A8" />
              <Text style={{ fontWeight: '700', color: '#0038A8', fontSize: 14 }}>Document QR Code</Text>
            </View>
            {qrLoading ? (
              <ActivityIndicator size="large" color="#0038A8" style={{ marginVertical: 24 }} />
            ) : qrData?.qr_base64 ? (
              <>
                <Image
                  source={{ uri: qrData.qr_base64 }}
                  style={{ width: 180, height: 180, borderRadius: 8, marginBottom: 14 }}
                  resizeMode="contain"
                />
                <Text style={{ color: '#64748B', fontSize: 12, textAlign: 'center', marginBottom: 14 }}>
                  Show this QR code at the office to quickly locate your document.
                </Text>
                <TouchableOpacity
                  onPress={handleDownloadQR}
                  style={{
                    flexDirection: 'row', alignItems: 'center', gap: 8,
                    backgroundColor: '#EFF6FF', borderRadius: 10,
                    paddingHorizontal: 20, paddingVertical: 10,
                    borderWidth: 1, borderColor: '#BFDBFE',
                  }}
                >
                  <Download size={15} color="#1E40AF" />
                  <Text style={{ color: '#1E40AF', fontWeight: '700', fontSize: 13 }}>Save QR Code</Text>
                </TouchableOpacity>
              </>
            ) : (
              <Text style={{ color: '#94A3B8', fontSize: 13, marginVertical: 16 }}>QR code not available.</Text>
            )}
          </View>

          {/* Travel log */}
          {travelLog.length > 0 && (
            <View style={{
              backgroundColor: '#fff', borderRadius: 14, padding: 20,
              borderWidth: 0.5, borderColor: '#E2E8F0', marginBottom: 12,
            }}>
              <Text style={{ fontWeight: '700', color: '#0038A8', fontSize: 14, marginBottom: 14 }}>
                Document History
              </Text>
              {[...travelLog].reverse().map((entry, i) => (
                <View key={i} style={{ flexDirection: 'row', gap: 12, marginBottom: i < travelLog.length - 1 ? 16 : 0 }}>
                  <View style={{ alignItems: 'center' }}>
                    <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: i === 0 ? '#0038A8' : '#CBD5E1', marginTop: 3 }} />
                    {i < travelLog.length - 1 && (
                      <View style={{ width: 1, flex: 1, backgroundColor: '#E2E8F0', marginTop: 4 }} />
                    )}
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: '700', color: '#1E293B', fontSize: 13 }}>{entry.action}</Text>
                    {entry.office ? <Text style={{ color: '#64748B', fontSize: 12 }}>{entry.office}</Text> : null}
                    {entry.remarks ? <Text style={{ color: '#94A3B8', fontSize: 12 }}>{entry.remarks}</Text> : null}
                    <Text style={{ color: '#CBD5E1', fontSize: 11, marginTop: 3 }}>{formatDate(entry.timestamp)}</Text>
                  </View>
                </View>
              ))}
            </View>
          )}

          {/* Delete / Cancel button */}
          {canDelete && (
            <TouchableOpacity
              onPress={() => setConfirmVisible(true)}
              disabled={deleteMutation.isPending}
              style={{
                backgroundColor: isPending ? '#FFF7ED' : '#FEF2F2',
                borderRadius: 13,
                paddingVertical: 14, alignItems: 'center',
                borderWidth: 1,
                borderColor: isPending ? '#FED7AA' : '#FECACA',
                flexDirection: 'row', justifyContent: 'center', gap: 8,
              }}
            >
              <Trash2 size={16} color={isPending ? '#EA580C' : '#DC2626'} />
              <Text style={{ color: isPending ? '#EA580C' : '#DC2626', fontWeight: '700', fontSize: 14 }}>
                {deleteMutation.isPending
                  ? 'Removing…'
                  : isPending
                    ? 'Cancel Submission'
                    : 'Move to Trash'}
              </Text>
            </TouchableOpacity>
          )}
        </ScrollView>
      )}

      {/* ── Confirmation dialog ────────────────────────────────────────────── */}
      <ConfirmDialog
        visible={confirmVisible}
        onClose={() => setConfirmVisible(false)}
        icon={isPending ? '⚠️' : '🗑️'}
        accentColor={isPending ? '#EA580C' : '#DC2626'}
        title={isPending ? 'Cancel Submission?' : 'Move to Trash?'}
        message={
          isPending
            ? `"${doc?.doc_name || 'This document'}" is still pending and hasn't been received by staff yet. Cancelling will permanently remove it.`
            : `"${doc?.doc_name || 'This document'}" will be moved to your trash.`
        }
        buttons={[
          {
            label: 'Keep',
            variant: 'ghost',
            onPress: () => {},
          },
          {
            label: isPending ? 'Yes, Cancel' : 'Move to Trash',
            variant: 'danger',
            onPress: () => deleteMutation.mutate(),
          },
        ]}
      />
    </View>
  );
}
