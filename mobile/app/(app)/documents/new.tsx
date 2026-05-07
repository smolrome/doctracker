import { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  StatusBar,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { SelectField } from '../../../components/ui/SelectField';
import api from '../../../lib/api';

const CATEGORY_OPTIONS = [
  'Letter', 'Memorandum', 'Report', 'Application', 'Voucher',
  'Plantilla', 'Payroll', 'Memo', 'Request', 'Endorsement',
  'Order', 'Notice', 'Circular', 'Certificate', 'Other',
];

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

export default function NewDocument() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [doc_name, setDocName]       = useState('');
  const [category, setCategory]       = useState('');
  const [from_office, setFromOffice] = useState('');
  const [sender_name, setSenderName] = useState('');
  const [referred_to, setReferredTo] = useState('');
  const [doc_date, setDocDate]       = useState(todayStr());
  const [remarks, setRemarks]         = useState('');
  const [nameError, setNameError]     = useState(false);

  const createMutation = useMutation({
    mutationFn: () =>
      api.post('/documents', {
        doc_name:    doc_name.trim(),
        category:    category.trim(),
        from_office: from_office.trim(),
        sender_name: sender_name.trim(),
        referred_to: referred_to.trim(),
        doc_date:    doc_date.trim(),
        remarks:     remarks.trim(),
      }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      router.replace(`/(app)/documents/${res.data.id}`);
    },
    onError: (e: any) => {
      Alert.alert('Error', e?.response?.data?.error || 'Failed to create document.');
    },
  });

  const handleSave = () => {
    if (!doc_name.trim()) {
      setNameError(true);
      return;
    }
    setNameError(false);
    createMutation.mutate();
  };

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* ── Header ── */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <TouchableOpacity
            onPress={() => router.back()}
            disabled={createMutation.isPending}
            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
          >
            <Text style={{ color: '#93C5FD', fontSize: 15, fontWeight: '600' }}>Cancel</Text>
          </TouchableOpacity>

          <Text style={{ color: '#fff', fontSize: 18, fontWeight: '800', letterSpacing: -0.3 }}>
            New Document
          </Text>

          <TouchableOpacity
            onPress={handleSave}
            disabled={createMutation.isPending}
            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
          >
            {createMutation.isPending
              ? <ActivityIndicator size="small" color="#fff" />
              : <Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>Save</Text>}
          </TouchableOpacity>
        </View>
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <ScrollView
          contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* ── Document Details Card ── */}
          <View style={{
            backgroundColor: '#fff', borderRadius: 14, padding: 16,
            marginBottom: 12, borderWidth: 0.5, borderColor: '#E2E8F0',
          }}>
            <Text style={{
              fontWeight: '800', color: '#0038A8', marginBottom: 16,
              fontSize: 13, textTransform: 'uppercase', letterSpacing: 0.8,
            }}>
              Document Details
            </Text>

            {/* doc_name — required */}
            <Text style={[S.label, { color: '#92400E' }]}>
              Document Name <Text style={{ color: '#EF4444' }}>*</Text>
            </Text>
            <TextInput
              value={doc_name}
              onChangeText={(v) => { setDocName(v); if (v.trim()) setNameError(false); }}
              placeholder="e.g. Plantilla of Personnel"
              placeholderTextColor="#CBD5E1"
              style={[S.input, nameError && { borderColor: '#EF4444', borderWidth: 1.5 }]}
            />
            {nameError && (
              <Text style={{ color: '#EF4444', fontSize: 12, marginTop: -10, marginBottom: 12 }}>
                Document name is required.
              </Text>
            )}

            {/* category */}
            <Text style={S.label}>Category</Text>
            <SelectField
              value={category}
              onChange={setCategory}
              options={CATEGORY_OPTIONS}
              placeholder="Select document type…"
              label="Category"
            />

            {/* from_office */}
            <Text style={S.label}>From Office</Text>
            <TextInput
              value={from_office}
              onChangeText={setFromOffice}
              placeholder="e.g. Palo Central School"
              placeholderTextColor="#CBD5E1"
              style={S.input}
            />

            {/* sender_name */}
            <Text style={S.label}>Sender Name</Text>
            <TextInput
              value={sender_name}
              onChangeText={setSenderName}
              placeholder="e.g. Juan dela Cruz, Principal II"
              placeholderTextColor="#CBD5E1"
              style={S.input}
            />

            {/* referred_to */}
            <Text style={S.label}>Referred To</Text>
            <TextInput
              value={referred_to}
              onChangeText={setReferredTo}
              placeholder="e.g. Maria Santos"
              placeholderTextColor="#CBD5E1"
              style={S.input}
            />

            {/* doc_date */}
            <Text style={S.label}>Date</Text>
            <TextInput
              value={doc_date}
              onChangeText={setDocDate}
              placeholder="YYYY-MM-DD"
              placeholderTextColor="#CBD5E1"
              keyboardType="numeric"
              style={S.input}
            />

            {/* remarks */}
            <Text style={S.label}>Remarks</Text>
            <TextInput
              value={remarks}
              onChangeText={setRemarks}
              placeholder="Additional details…"
              placeholderTextColor="#CBD5E1"
              multiline
              style={[S.input, { height: 80, textAlignVertical: 'top', marginBottom: 0 }]}
            />
          </View>

          {/* ── Submit Button ── */}
          <TouchableOpacity
            onPress={handleSave}
            disabled={createMutation.isPending}
            activeOpacity={0.85}
            style={{
              backgroundColor: createMutation.isPending ? '#93C5FD' : '#0038A8',
              borderRadius: 13, paddingVertical: 15,
              alignItems: 'center', flexDirection: 'row',
              justifyContent: 'center', gap: 8,
            }}
          >
            {createMutation.isPending
              ? <><ActivityIndicator color="#fff" size="small" /><Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>Saving…</Text></>
              : <Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>Create Document</Text>}
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

// ── Styles (copied from [id].tsx edit form) ───────────────────────────────────

const S = {
  label: {
    fontSize: 11,
    fontWeight: '700' as const,
    color: '#475569',
    marginBottom: 6,
    textTransform: 'uppercase' as const,
    letterSpacing: 0.8,
  },
  input: {
    backgroundColor: '#fff',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 13,
    marginBottom: 16,
    borderWidth: 1.5,
    borderColor: '#E2E8F0',
    fontSize: 14.5,
    color: '#1E293B',
  },
};
