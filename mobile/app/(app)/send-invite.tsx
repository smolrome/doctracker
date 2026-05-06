import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView, Alert,
  ActivityIndicator, StatusBar, Platform, Clipboard, Switch,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useMutation } from '@tanstack/react-query';
import api from '../../lib/api';
import { ArrowLeft, Mail, Send, Link, Copy, Users } from 'lucide-react-native';

// ── Types ──────────────────────────────────────────────────────────────────────

type InviteResult = {
  email: string;
  ok: boolean;
  link: string;
  msg: string;
};

// ── Component ──────────────────────────────────────────────────────────────────

export default function SendInvite() {
  const router = useRouter();

  const [isBatch, setIsBatch]       = useState(false);
  const [email, setEmail]           = useState('');
  const [name, setName]             = useState('');
  const [batchEmails, setBatchEmails] = useState('');
  const [results, setResults]       = useState<InviteResult[]>([]);
  const [singleResult, setSingleResult] = useState<{ ok: boolean; link: string; message: string; mail_sent: boolean } | null>(null);

  // ── Mutations ──────────────────────────────────────────────────────────────

  const singleMutation = useMutation({
    mutationFn: () => api.post('/admin/send-invite', { mode: 'single', email: email.trim(), name: name.trim() }),
    onSuccess: (res) => {
      setSingleResult(res.data);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Failed to send invite.'),
  });

  const batchMutation = useMutation({
    mutationFn: () => {
      const emails = batchEmails
        .split(/[\n,]+/)
        .map((e) => e.trim())
        .filter(Boolean);
      if (emails.length === 0) throw new Error('No valid emails found.');
      return api.post('/admin/send-invite', { mode: 'batch', emails });
    },
    onSuccess: (res) => {
      setResults(res.data.results ?? []);
    },
    onError: (e: any) => Alert.alert('Error', e?.message || e?.response?.data?.error || 'Failed.'),
  });

  const handleSend = () => {
    if (isBatch) {
      const count = batchEmails.split(/[\n,]+/).map((e) => e.trim()).filter(Boolean).length;
      if (count === 0) { Alert.alert('No emails', 'Enter at least one email address.'); return; }
      Alert.alert('Send Batch Invites', `Send invite links to ${count} email(s)?`, [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Send', onPress: () => { setResults([]); batchMutation.mutate(); } },
      ]);
    } else {
      if (!email.trim()) { Alert.alert('Required', 'Email address is required.'); return; }
      setSingleResult(null);
      singleMutation.mutate();
    }
  };

  const copyLink = (link: string) => {
    Clipboard.setString(link);
    Alert.alert('Copied', 'Invite link copied to clipboard.');
  };

  const isPending = singleMutation.isPending || batchMutation.isPending;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* Header */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
        <TouchableOpacity onPress={() => router.back()}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 14 }}>
          <ArrowLeft size={18} color="#93C5FD" />
          <Text style={{ color: '#93C5FD', fontSize: 14, fontWeight: '600' }}>Back</Text>
        </TouchableOpacity>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Mail size={22} color="#fff" />
          <View>
            <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800' }}>Send Invite</Text>
            <Text style={{ color: 'rgba(255,255,255,0.60)', fontSize: 12, marginTop: 2 }}>
              Generate registration links for new staff
            </Text>
          </View>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 60 }} keyboardShouldPersistTaps="handled">

        {/* Mode toggle */}
        <View style={{
          backgroundColor: '#fff', borderRadius: 16, padding: 16, marginBottom: 20,
          borderWidth: 0.5, borderColor: '#E2E8F0',
          flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            {isBatch ? <Users size={18} color="#0038A8" /> : <Mail size={18} color="#0038A8" />}
            <View>
              <Text style={{ fontWeight: '700', color: '#1E293B', fontSize: 14 }}>
                {isBatch ? 'Batch Mode' : 'Single Invite'}
              </Text>
              <Text style={{ color: '#94A3B8', fontSize: 12 }}>
                {isBatch ? 'Multiple emails at once' : 'One recipient'}
              </Text>
            </View>
          </View>
          <Switch
            value={isBatch}
            onValueChange={(v) => { setIsBatch(v); setSingleResult(null); setResults([]); }}
            trackColor={{ false: '#E2E8F0', true: '#BFDBFE' }}
            thumbColor={isBatch ? '#0038A8' : '#94A3B8'}
          />
        </View>

        {!isBatch ? (
          /* ── Single invite ── */
          <View style={{ backgroundColor: '#fff', borderRadius: 16, padding: 20, borderWidth: 0.5, borderColor: '#E2E8F0', marginBottom: 16 }}>
            <Text style={S.label}>Email Address <Text style={S.req}>*</Text></Text>
            <TextInput value={email} onChangeText={setEmail}
              placeholder="e.g. juan@deped.gov.ph"
              keyboardType="email-address" autoCapitalize="none"
              style={S.input} placeholderTextColor="#CBD5E1" />

            <Text style={S.labelMuted}>Name (optional)</Text>
            <TextInput value={name} onChangeText={setName}
              placeholder="e.g. Juan dela Cruz"
              style={S.input} placeholderTextColor="#CBD5E1" />
          </View>
        ) : (
          /* ── Batch invite ── */
          <View style={{ backgroundColor: '#fff', borderRadius: 16, padding: 20, borderWidth: 0.5, borderColor: '#E2E8F0', marginBottom: 16 }}>
            <Text style={S.label}>Email Addresses <Text style={S.req}>*</Text></Text>
            <TextInput value={batchEmails} onChangeText={setBatchEmails}
              placeholder={'One per line or comma-separated:\nana@deped.gov.ph\njose@deped.gov.ph'}
              multiline numberOfLines={6}
              style={[S.input, { height: 140, textAlignVertical: 'top' }]}
              placeholderTextColor="#CBD5E1" />
            <Text style={S.hint}>
              {batchEmails.split(/[\n,]+/).map((e) => e.trim()).filter(Boolean).length} email(s) entered
            </Text>
          </View>
        )}

        {/* Send button */}
        <TouchableOpacity onPress={handleSend} disabled={isPending} activeOpacity={0.85}
          style={[S.btnPrimary, isPending && { backgroundColor: '#93C5FD' }]}>
          {isPending
            ? <><ActivityIndicator color="#fff" size="small" /><Text style={S.btnPrimaryText}>Sending…</Text></>
            : <><Send size={18} color="#fff" /><Text style={S.btnPrimaryText}>
                {isBatch ? 'Send Batch Invites' : 'Send Invite'}
              </Text></>}
        </TouchableOpacity>

        {/* ── Single result ── */}
        {singleResult && (
          <View style={{
            marginTop: 20, backgroundColor: singleResult.ok ? '#F0FDF4' : '#FFFBEB',
            borderRadius: 14, padding: 16,
            borderWidth: 1, borderColor: singleResult.ok ? '#BBF7D0' : '#FDE68A',
          }}>
            <Text style={{ fontWeight: '800', color: singleResult.ok ? '#166534' : '#92400E', fontSize: 14, marginBottom: 6 }}>
              {singleResult.ok ? '✅ Success' : '⚠️ Partial'}
            </Text>
            <Text style={{ color: '#475569', fontSize: 13, marginBottom: 12 }}>{singleResult.message}</Text>

            {singleResult.link ? (
              <View style={{ backgroundColor: '#fff', borderRadius: 10, padding: 12, borderWidth: 1, borderColor: '#E2E8F0' }}>
                <Text style={{ fontSize: 11, color: '#94A3B8', marginBottom: 4 }}>INVITE LINK</Text>
                <Text style={{ fontSize: 12, color: '#1E293B', marginBottom: 10 }} numberOfLines={3}>
                  {singleResult.link}
                </Text>
                <TouchableOpacity onPress={() => copyLink(singleResult.link)}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#EFF6FF', borderRadius: 8, paddingHorizontal: 14, paddingVertical: 8, alignSelf: 'flex-start' }}>
                  <Copy size={14} color="#0038A8" />
                  <Text style={{ color: '#0038A8', fontSize: 13, fontWeight: '700' }}>Copy Link</Text>
                </TouchableOpacity>
              </View>
            ) : null}
          </View>
        )}

        {/* ── Batch results ── */}
        {results.length > 0 && (
          <View style={{ marginTop: 20 }}>
            <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 15, marginBottom: 12 }}>
              Results ({results.filter((r) => r.ok).length}/{results.length} successful)
            </Text>
            {results.map((r, i) => (
              <View key={i} style={{
                backgroundColor: '#fff', borderRadius: 12, padding: 14, marginBottom: 10,
                borderWidth: 0.5, borderColor: r.ok ? '#BBF7D0' : '#FCA5A5',
              }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                  <Text style={{ fontWeight: '700', color: '#1E293B', fontSize: 13 }}>{r.email}</Text>
                  <View style={{
                    backgroundColor: r.ok ? '#DCFCE7' : '#FEF2F2',
                    borderRadius: 8, paddingHorizontal: 8, paddingVertical: 2,
                  }}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: r.ok ? '#166534' : '#DC2626' }}>
                      {r.ok ? 'OK' : 'FAILED'}
                    </Text>
                  </View>
                </View>
                <Text style={{ fontSize: 12, color: '#64748B', marginBottom: r.link ? 8 : 0 }}>{r.msg}</Text>
                {r.link ? (
                  <TouchableOpacity onPress={() => copyLink(r.link)}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 5, alignSelf: 'flex-start' }}>
                    <Link size={12} color="#0038A8" />
                    <Text style={{ fontSize: 12, color: '#0038A8', fontWeight: '600' }}>Copy Link</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────────

const S = {
  label: {
    fontSize: 11, fontWeight: '700' as const, color: '#0038A8',
    marginBottom: 6, textTransform: 'uppercase' as const, letterSpacing: 0.8,
  },
  labelMuted: {
    fontSize: 11, fontWeight: '700' as const, color: '#475569',
    marginBottom: 6, textTransform: 'uppercase' as const, letterSpacing: 0.8,
  },
  req: { color: '#EF4444' },
  hint: { fontSize: 11, color: '#94A3B8', marginTop: -10, marginBottom: 14 },
  input: {
    backgroundColor: '#F8FAFC', borderRadius: 12,
    paddingHorizontal: 14, paddingVertical: 13, marginBottom: 16,
    borderWidth: 1.5, borderColor: '#E2E8F0', fontSize: 14.5, color: '#1E293B',
  },
  btnPrimary: {
    backgroundColor: '#0038A8', borderRadius: 13, paddingVertical: 15,
    alignItems: 'center' as const, flexDirection: 'row' as const,
    justifyContent: 'center' as const, gap: 8,
  },
  btnPrimaryText: { color: '#fff', fontSize: 15, fontWeight: '700' as const },
};
