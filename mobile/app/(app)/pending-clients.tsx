import { useState } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, Alert,
  ActivityIndicator, StatusBar, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, UserCheck, UserX, Users, Clock } from 'lucide-react-native';
import api from '../../lib/api';

type PendingClient = {
  username: string;
  full_name: string;
  email?: string;
  created_at?: string;
  role: string;
};

function formatDate(ts?: string) {
  if (!ts) return '—';
  return ts.replace('T', ' ').slice(0, 16);
}

export default function PendingClients() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data, isLoading, isRefetching, refetch } = useQuery({
    queryKey: ['pending-clients'],
    queryFn: async () => {
      const res = await api.get('/clients/pending');
      return (res.data ?? []) as PendingClient[];
    },
    staleTime: 1000 * 30,
  });

  const clients = data ?? [];

  // ── Mutations ────────────────────────────────────────────────────────────

  const approveMutation = useMutation({
    mutationFn: (username: string) => api.post(`/clients/${username}/approve`),
    onSuccess: (_, username) => {
      queryClient.invalidateQueries({ queryKey: ['pending-clients'] });
      queryClient.invalidateQueries({ queryKey: ['users'] });
      Alert.alert('Approved', `${username} can now log in as a client.`);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to approve.'),
  });

  const rejectMutation = useMutation({
    mutationFn: (username: string) => api.delete(`/clients/${username}/reject`),
    onSuccess: (_, username) => {
      queryClient.invalidateQueries({ queryKey: ['pending-clients'] });
      Alert.alert('Rejected', `${username}'s registration has been removed.`);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to reject.'),
  });

  // ── Handlers ─────────────────────────────────────────────────────────────

  const handleApprove = (client: PendingClient) => {
    Alert.alert(
      'Approve Client',
      `Allow "${client.full_name}" (@${client.username}) to access the client portal?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Approve', onPress: () => approveMutation.mutate(client.username) },
      ],
    );
  };

  const handleReject = (client: PendingClient) => {
    Alert.alert(
      'Reject Registration',
      `Permanently remove "${client.full_name}" (@${client.username})'s pending registration?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Reject',
          style: 'destructive',
          onPress: () => rejectMutation.mutate(client.username),
        },
      ],
    );
  };

  // ── Item ──────────────────────────────────────────────────────────────────

  const renderItem = ({ item }: { item: PendingClient }) => (
    <View style={{
      backgroundColor: '#fff',
      borderRadius: 14,
      padding: 16,
      marginBottom: 10,
      borderWidth: 0.5,
      borderColor: '#E2E8F0',
    }}>
      {/* Name + username */}
      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6, gap: 10 }}>
        <View style={{
          width: 42, height: 42, borderRadius: 21,
          backgroundColor: '#EFF6FF',
          alignItems: 'center', justifyContent: 'center',
        }}>
          <Text style={{ fontSize: 18, fontWeight: '700', color: '#0038A8' }}>
            {item.full_name?.charAt(0)?.toUpperCase() || '?'}
          </Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 14 }}>
            {item.full_name}
          </Text>
          <Text style={{ color: '#64748B', fontSize: 12 }}>@{item.username}</Text>
        </View>
        <View style={{
          backgroundColor: '#FEF3C7',
          borderRadius: 10, paddingHorizontal: 8, paddingVertical: 3,
          flexDirection: 'row', alignItems: 'center', gap: 4,
        }}>
          <Clock size={11} color="#B45309" />
          <Text style={{ color: '#B45309', fontSize: 11, fontWeight: '700' }}>Pending</Text>
        </View>
      </View>

      {/* Email + date */}
      <View style={{ gap: 3, marginBottom: 14 }}>
        {item.email ? (
          <Text style={{ fontSize: 12, color: '#64748B' }}>✉️ {item.email}</Text>
        ) : null}
        <Text style={{ fontSize: 12, color: '#94A3B8' }}>
          📅 Registered {formatDate(item.created_at)}
        </Text>
      </View>

      {/* Action buttons */}
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <TouchableOpacity
          onPress={() => handleApprove(item)}
          disabled={approveMutation.isPending || rejectMutation.isPending}
          style={{
            flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
            gap: 6, backgroundColor: '#F0FDF4',
            borderRadius: 10, paddingVertical: 10,
            borderWidth: 1, borderColor: '#BBF7D0',
          }}
        >
          <UserCheck size={15} color="#16A34A" />
          <Text style={{ color: '#16A34A', fontWeight: '700', fontSize: 13 }}>Approve</Text>
        </TouchableOpacity>

        <TouchableOpacity
          onPress={() => handleReject(item)}
          disabled={approveMutation.isPending || rejectMutation.isPending}
          style={{
            flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
            gap: 6, backgroundColor: '#FEF2F2',
            borderRadius: 10, paddingVertical: 10,
            borderWidth: 1, borderColor: '#FECACA',
          }}
        >
          <UserX size={15} color="#DC2626" />
          <Text style={{ color: '#DC2626', fontWeight: '700', fontSize: 13 }}>Reject</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  // ── Screen ─────────────────────────────────────────────────────────────────

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
          <Users size={20} color="#fff" />
          <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>
            Pending Clients
          </Text>
        </View>
        <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 13, marginTop: 4 }}>
          {clients.length} registration{clients.length !== 1 ? 's' : ''} awaiting approval
        </Text>
      </View>

      {isLoading ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator size="large" color="#0038A8" />
          <Text style={{ color: '#94A3B8', marginTop: 12, fontSize: 13 }}>Loading pending clients…</Text>
        </View>
      ) : (
        <FlatList
          data={clients}
          keyExtractor={(item) => item.username}
          renderItem={renderItem}
          contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#0038A8" />
          }
          ListEmptyComponent={
            <View style={{ alignItems: 'center', paddingTop: 72 }}>
              <UserCheck size={48} color="#E2E8F0" />
              <Text style={{ color: '#1E293B', fontSize: 15, fontWeight: '700', marginTop: 14 }}>
                No pending registrations
              </Text>
              <Text style={{ color: '#94A3B8', fontSize: 13, marginTop: 6, textAlign: 'center', paddingHorizontal: 40 }}>
                New client registrations will appear here for approval.
              </Text>
            </View>
          }
        />
      )}
    </View>
  );
}
