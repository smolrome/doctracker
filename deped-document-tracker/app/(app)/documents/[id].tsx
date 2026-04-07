import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../../../lib/api';

const STATUS_COLORS: Record<string, string> = {
  Pending:     '#F59E0B',
  Received:    '#10B981',
  Released:    '#3B82F6',
  Routed:      '#8B5CF6',
  'In Review': '#6366F1',
  Transferred: '#06B6D4',
  'On Hold':   '#EF4444',
};

const STATUS_OPTIONS = [
  'Pending', 'Received', 'Released',
  'Routed', 'In Review', 'Transferred', 'On Hold'
];

async function fetchDocument(id: string) {
  const res = await api.get(`/documents/${id}`);
  return res.data;
}

export default function DocumentDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: doc, isLoading } = useQuery({
    queryKey: ['document', id],
    queryFn: () => fetchDocument(id),
    enabled: !!id,
  });

  const statusMutation = useMutation({
    mutationFn: (newStatus: string) =>
      api.patch(`/documents/${id}/status`, { status: newStatus }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['document', id] });
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      Alert.alert('Success', 'Status updated successfully');
    },
    onError: () => Alert.alert('Error', 'Failed to update status'),
  });

  const handleStatusChange = (newStatus: string) => {
    Alert.alert(
      'Update Status',
      `Change status to "${newStatus}"?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Confirm', onPress: () => statusMutation.mutate(newStatus) },
      ]
    );
  };

  if (isLoading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator size="large" color="#0038A8" />
      </View>
    );
  }

  if (!doc) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
        <Text style={{ color: '#9CA3AF' }}>Document not found</Text>
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: '#F3F4F6' }}>

      <View style={{
        backgroundColor: '#0038A8',
        paddingTop: 56,
        paddingBottom: 20,
        paddingHorizontal: 16,
      }}>
        <TouchableOpacity onPress={() => router.back()} style={{ marginBottom: 12 }}>
          <Text style={{ color: '#93C5FD', fontSize: 14 }}>← Back</Text>
        </TouchableOpacity>
        <Text style={{ color: '#fff', fontSize: 18, fontWeight: 'bold' }} numberOfLines={2}>
          {doc.doc_name || doc.description || 'No subject'}
        </Text>
        <View style={{
          marginTop: 8,
          alignSelf: 'flex-start',
          backgroundColor: STATUS_COLORS[doc.status] ?? '#9CA3AF',
          borderRadius: 20,
          paddingHorizontal: 12,
          paddingVertical: 4,
        }}>
          <Text style={{ color: '#fff', fontWeight: '600', fontSize: 13 }}>
            {doc.status}
          </Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16 }}>

        <View style={{
          backgroundColor: '#fff',
          borderRadius: 12,
          padding: 16,
          marginBottom: 12,
        }}>
          <Text style={{ fontWeight: '700', color: '#0038A8', marginBottom: 12, fontSize: 15 }}>
            Document Info
          </Text>
          {[
            ['Reference', doc.doc_id || '—'],
            ['Document Name', doc.doc_name || '—'],
            ['Category', doc.category || '—'],
            ['From Office', doc.from_office || '—'],
            ['Sender Org', doc.sender_org || '—'],
            ['Sender Name', doc.sender_name || '—'],
            ['Referred To', doc.referred_to || '—'],
            ['Logged By', doc.logged_by || '—'],
            ['Date', doc.doc_date || '—'],
            ['Date Received', doc.date_received || '—'],
            ['Date Released', doc.date_released || '—'],
          ].map(([label, value]) => (
            <View key={label} style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              paddingVertical: 6,
              borderBottomWidth: 1,
              borderBottomColor: '#F3F4F6',
            }}>
              <Text style={{ color: '#6B7280', fontSize: 13 }}>{label}</Text>
              <Text style={{ color: '#111', fontSize: 13, fontWeight: '500', maxWidth: '60%', textAlign: 'right' }}>
                {value}
              </Text>
            </View>
          ))}
        </View>

        {doc.remarks ? (
          <View style={{
            backgroundColor: '#fff',
            borderRadius: 12,
            padding: 16,
            marginBottom: 12,
          }}>
            <Text style={{ fontWeight: '700', color: '#0038A8', marginBottom: 8, fontSize: 15 }}>
              Remarks
            </Text>
            <Text style={{ color: '#374151', fontSize: 14, lineHeight: 20 }}>
              {doc.remarks}
            </Text>
          </View>
        ) : null}

        <View style={{
          backgroundColor: '#fff',
          borderRadius: 12,
          padding: 16,
          marginBottom: 24,
        }}>
          <Text style={{ fontWeight: '700', color: '#0038A8', marginBottom: 12, fontSize: 15 }}>
            Update Status
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {STATUS_OPTIONS.map((status) => (
              <TouchableOpacity
                key={status}
                onPress={() => handleStatusChange(status)}
                disabled={doc.status === status || statusMutation.isPending}
                style={{
                  paddingHorizontal: 14,
                  paddingVertical: 8,
                  borderRadius: 20,
                  backgroundColor: doc.status === status ? STATUS_COLORS[status] : '#F3F4F6',
                  opacity: doc.status === status ? 0.6 : 1,
                }}
              >
                <Text style={{
                  color: doc.status === status ? '#fff' : '#374151',
                  fontSize: 13,
                  fontWeight: '500',
                }}>
                  {status}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

      </ScrollView>
    </View>
  );
}