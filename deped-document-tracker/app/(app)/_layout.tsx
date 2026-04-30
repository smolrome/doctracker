import { useEffect, useState } from 'react';
import { Tabs } from 'expo-router';
import { useRouter } from 'expo-router';
import { View, TouchableOpacity, Modal, Text, TextInput, ScrollView, Alert, ActivityIndicator } from 'react-native';
import { useAuthStore } from '../../lib/store';
import { FileText, QrCode, LayoutDashboard, User, Plus, X } from 'lucide-react-native';
import { KeyboardAvoidingView, Platform } from 'react-native';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../../lib/api';
import { useDropdownOptions, usePendingCount } from '../../hooks/useDropdownOptions';
import { SelectField } from '../../components/ui/SelectField';

// ── Shared form styles (mirrors Login field language) ────────────────────────
const fieldLabel: any = {
  fontSize: 11,
  fontWeight: '700',
  color: '#0038A8',
  marginBottom: 6,
  textTransform: 'uppercase',
  letterSpacing: 0.8,
};

const fieldLabelMuted: any = {
  ...fieldLabel,
  color: '#475569',
};

const req: any = {
  color: '#EF4444',
};

const input: any = {
  backgroundColor: '#fff',
  borderRadius: 12,
  paddingHorizontal: 14,
  paddingVertical: 13,
  marginBottom: 16,
  borderWidth: 1.5,
  borderColor: '#E2E8F0',
  fontSize: 14.5,
  color: '#1E293B',
};

const EMPTY_FORM = {
  fromOffice: '',
  senderName: '',
  docName: '',
  category: '',
  referredTo: '',
  remarks: '',
};

async function checkDuplicateName(name: string): Promise<{ id: string; doc_id: string; doc_name: string; status: string }[]> {
  if (name.trim().length < 4) return [];
  try {
    const res = await api.get('/check-duplicate', { params: { q: name.trim() } });
    return res.data?.duplicates ?? [];
  } catch {
    return [];
  }
}

export default function AppLayout() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuthStore();
  const [modalVisible, setModalVisible] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace('/(auth)/login');
    }
  }, [isAuthenticated, isLoading]);

  const [duplicateWarning, setDuplicateWarning] = useState<{ id: string; doc_id: string; doc_name: string; status: string }[]>([]);

  const { data: dropdownOptions } = useDropdownOptions();
  const { data: pendingCount } = usePendingCount();

  const categoryOptions = dropdownOptions?.category ?? [];
  const staffNames = dropdownOptions?.referred_to ?? [];

  const setField = (key: keyof typeof EMPTY_FORM) => (val: string) =>
    setForm((f) => ({ ...f, [key]: val }));

  const closeModal = () => {
    setModalVisible(false);
    setForm(EMPTY_FORM);
    setDuplicateWarning([]);
  };

  const handleDocNameBlur = async () => {
    const dupes = await checkDuplicateName(form.docName);
    setDuplicateWarning(dupes);
  };

  const { mutate: submitDoc, isPending: submitting } = useMutation({
    mutationFn: () =>
      api.post('/documents', {
        doc_name: form.docName.trim(),
        category: form.category.trim(),
        from_office: form.fromOffice.trim(),
        sender_org: form.fromOffice.trim(),
        sender_name: form.senderName.trim(),
        referred_to: form.referredTo.trim(),
        remarks: form.remarks.trim(),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      closeModal();
      Alert.alert('Success', 'Document added to the log list.');
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.error || 'Failed to add document. Please try again.';
      Alert.alert('Error', msg);
    },
  });

  const handleSubmit = () => {
    if (!form.fromOffice.trim() || !form.docName.trim()) {
      Alert.alert('Required Fields', 'Please fill in Unit/Office and Content/Particulars.');
      return;
    }
    submitDoc();
  };

  return (
    <>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: '#0038A8',
          tabBarInactiveTintColor: '#94A3B8',
          tabBarStyle: {
            position: 'absolute',
            bottom: 28,
            left: 20,
            right: 20,
            height: 64,
            borderRadius: 32,
            backgroundColor: '#FFFFFF',
            borderTopWidth: 0,
            elevation: 10,
            shadowColor: '#0038A8',
            shadowOffset: { width: 0, height: 6 },
            shadowOpacity: 0.12,
            shadowRadius: 16,
            paddingBottom: 0,
            paddingHorizontal: 8,
            overflow: 'visible',
            // Thin border for definition on light backgrounds
            borderWidth: 0.5,
            borderColor: '#E2E8F0',
          },
          tabBarLabelStyle: {
            fontSize: 10.5,
            fontWeight: '700',
            marginTop: -2,
            letterSpacing: 0.2,
          },
          tabBarItemStyle: {
            paddingVertical: 4,
          },
        }}
      >
        <Tabs.Screen
          name="dashboard"
          options={{
            title: 'Dashboard',
            tabBarIcon: ({ color }) => <LayoutDashboard size={22} color={color} />,
          }}
        />
        <Tabs.Screen
          name="documents/index"
          options={{
            title: 'Documents',
            tabBarIcon: ({ color }) => <FileText size={22} color={color} />,
            tabBarBadge: pendingCount && pendingCount > 0 ? pendingCount : undefined,
            tabBarBadgeStyle: { backgroundColor: '#EF4444', color: '#fff', fontSize: 10 },
          }}
        />

        {/* ── Centre FAB ── */}
        <Tabs.Screen
          name="add"
          options={{
            title: '',
            tabBarButton: () => (
              <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
                <TouchableOpacity
                  onPress={() => { setForm(EMPTY_FORM); setModalVisible(true); }}
                  activeOpacity={0.85}
                  style={{
                    position: 'absolute',
                    top: -26,
                    width: 56,
                    height: 56,
                    borderRadius: 28,
                    backgroundColor: '#0038A8',
                    alignItems: 'center',
                    justifyContent: 'center',
                    // Halo ring matching Login logo
                    borderWidth: 3,
                    borderColor: '#fff',
                    shadowColor: '#0038A8',
                    shadowOffset: { width: 0, height: 6 },
                    shadowOpacity: 0.35,
                    shadowRadius: 10,
                    elevation: 10,
                  }}
                >
                  <Plus size={26} color="#fff" />
                </TouchableOpacity>
              </View>
            ),
          }}
        />

        <Tabs.Screen
          name="scanner"
          options={{
            title: 'Scan',
            tabBarIcon: ({ color }) => <QrCode size={22} color={color} />,
          }}
        />
        <Tabs.Screen
          name="profile"
          options={{
            title: 'Profile',
            tabBarIcon: ({ color }) => <User size={22} color={color} />,
          }}
        />
        <Tabs.Screen name="documents/[id]" options={{ href: null }} />
        <Tabs.Screen name="documents/new" options={{ href: null }} />
        <Tabs.Screen name="notifications" options={{ href: null }} />
        <Tabs.Screen name="activity-log" options={{ href: null }} />
        <Tabs.Screen name="routing-slips" options={{ href: null }} />
        <Tabs.Screen name="staff-stats" options={{ href: null }} />
      </Tabs>

      {/* ── New Document Modal ── */}
      <Modal
        visible={modalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={closeModal}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={{ flex: 1 }}
        >
          <View style={{
            flex: 1,
            backgroundColor: 'rgba(0,0,0,0.45)',
            justifyContent: 'flex-end',
          }}>
            {/* Tap outside to close */}
            <TouchableOpacity
              style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
              onPress={closeModal}
              activeOpacity={1}
            />

            <View style={{
              backgroundColor: '#F8FAFC',
              borderTopLeftRadius: 28,
              borderTopRightRadius: 28,
              maxHeight: '92%',
              overflow: 'hidden',
            }}>

              {/* Modal header — blue hero strip */}
              <View style={{
                backgroundColor: '#0038A8',
                paddingTop: 20,
                paddingBottom: 20,
                paddingHorizontal: 20,
                flexDirection: 'row',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}>
                {/* Drag handle */}
                <View style={{
                  position: 'absolute',
                  top: 10,
                  left: 0, right: 0,
                  alignItems: 'center',
                }}>
                  <View style={{
                    width: 36, height: 4, borderRadius: 2,
                    backgroundColor: 'rgba(255,255,255,0.30)',
                  }} />
                </View>

                <View>
                  <Text style={{ fontSize: 18, fontWeight: '800', color: '#fff', letterSpacing: -0.3 }}>
                    New Document
                  </Text>
                  <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.60)', marginTop: 2 }}>
                    Fill in the document details below
                  </Text>
                </View>

                <TouchableOpacity
                  onPress={closeModal}
                  style={{
                    width: 34, height: 34, borderRadius: 17,
                    backgroundColor: 'rgba(255,255,255,0.15)',
                    alignItems: 'center', justifyContent: 'center',
                  }}
                >
                  <X size={18} color="#fff" />
                </TouchableOpacity>
              </View>

              {/* Form */}
              <ScrollView
                contentContainerStyle={{ padding: 20, paddingBottom: 8 }}
                showsVerticalScrollIndicator={false}
                keyboardShouldPersistTaps="handled"
                keyboardDismissMode="interactive"
              >
                <Text style={fieldLabel}>
                  Unit / Office / School <Text style={req}>*</Text>
                </Text>
                <TextInput
                  value={form.fromOffice}
                  onChangeText={setField('fromOffice')}
                  placeholder="e.g. Palo Central School, Leyte District I"
                  style={input}
                  placeholderTextColor="#CBD5E1"
                  editable={!submitting}
                />

                <Text style={fieldLabelMuted}>Sender Name & Designation</Text>
                <TextInput
                  value={form.senderName}
                  onChangeText={setField('senderName')}
                  placeholder="e.g. Juan dela Cruz, Principal II"
                  style={input}
                  placeholderTextColor="#CBD5E1"
                  editable={!submitting}
                />

                <Text style={fieldLabel}>
                  Content / Particulars <Text style={req}>*</Text>
                </Text>
                <TextInput
                  value={form.docName}
                  onChangeText={(v) => { setField('docName')(v); setDuplicateWarning([]); }}
                  onBlur={handleDocNameBlur}
                  placeholder="e.g. Plantilla of Personnel"
                  style={input}
                  placeholderTextColor="#CBD5E1"
                  editable={!submitting}
                />

                {/* Duplicate warning */}
                {duplicateWarning.length > 0 && (
                  <View style={{
                    backgroundColor: '#FFF7ED',
                    borderRadius: 10,
                    padding: 12,
                    marginTop: -10,
                    marginBottom: 16,
                    borderWidth: 1,
                    borderColor: '#FED7AA',
                  }}>
                    <Text style={{ fontSize: 12, fontWeight: '700', color: '#EA580C', marginBottom: 6 }}>
                      Similar document(s) already exist:
                    </Text>
                    {duplicateWarning.map((d) => (
                      <Text key={d.id} style={{ fontSize: 12, color: '#92400E', marginBottom: 2 }}>
                        • {d.doc_name} ({d.status}){d.doc_id ? ` — #${d.doc_id}` : ''}
                      </Text>
                    ))}
                    <Text style={{ fontSize: 11, color: '#B45309', marginTop: 6 }}>
                      You can still continue if this is a different document.
                    </Text>
                  </View>
                )}

                <Text style={fieldLabelMuted}>Document Type</Text>
                <SelectField
                  value={form.category}
                  onChange={setField('category')}
                  options={categoryOptions}
                  placeholder="Select document type…"
                  label="Document Type"
                  disabled={submitting}
                />

                <Text style={fieldLabelMuted}>Referred To</Text>
                <SelectField
                  value={form.referredTo}
                  onChange={setField('referredTo')}
                  options={staffNames}
                  placeholder="Search staff name…"
                  label="Referred To"
                  disabled={submitting}
                  allowFreeText
                />

                <Text style={fieldLabelMuted}>Description / Remarks</Text>
                <TextInput
                  value={form.remarks}
                  onChangeText={setField('remarks')}
                  placeholder="Additional details..."
                  style={[input, { height: 88, textAlignVertical: 'top' }]}
                  multiline
                  placeholderTextColor="#CBD5E1"
                  editable={!submitting}
                />
              </ScrollView>

              {/* Footer actions */}
              <View style={{
                padding: 16, paddingBottom: Platform.OS === 'ios' ? 32 : 20,
                borderTopWidth: 0.5, borderTopColor: '#E2E8F0',
                backgroundColor: '#F8FAFC',
                gap: 10,
              }}>
                {/* Primary CTA */}
                <TouchableOpacity
                  onPress={handleSubmit}
                  disabled={submitting}
                  activeOpacity={0.85}
                  style={{
                    backgroundColor: submitting ? '#93C5FD' : '#0038A8',
                    borderRadius: 13,
                    paddingVertical: 15,
                    alignItems: 'center',
                    flexDirection: 'row',
                    justifyContent: 'center',
                    gap: 8,
                  }}
                >
                  {submitting ? (
                    <>
                      <ActivityIndicator color="#fff" size="small" />
                      <Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>Saving...</Text>
                    </>
                  ) : (
                    <>
                      <Plus size={18} color="#fff" />
                      <Text style={{ color: '#fff', fontSize: 15, fontWeight: '700', letterSpacing: 0.2 }}>
                        Add to Log List
                      </Text>
                    </>
                  )}
                </TouchableOpacity>

                {/* Secondary cancel */}
                <TouchableOpacity
                  onPress={closeModal}
                  disabled={submitting}
                  style={{
                    borderWidth: 1.5, borderColor: '#E2E8F0',
                    borderRadius: 13, paddingVertical: 13,
                    alignItems: 'center', backgroundColor: '#fff',
                  }}
                >
                  <Text style={{ color: '#64748B', fontSize: 14, fontWeight: '600' }}>Cancel</Text>
                </TouchableOpacity>

                {/* PH flag strip */}
                <View style={{ flexDirection: 'row', justifyContent: 'center', marginTop: 4 }}>
                  <View style={{ width: 18, height: 3, backgroundColor: '#0038A8', borderRadius: 1 }} />
                  <View style={{ width: 18, height: 3, backgroundColor: '#CE1126' }} />
                  <View style={{ width: 18, height: 3, backgroundColor: '#FCD116', borderRadius: 1 }} />
                </View>
              </View>

            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </>
  );
}