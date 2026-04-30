import { useEffect, useRef, useState } from 'react';
import { Tabs } from 'expo-router';
import { useRouter } from 'expo-router';
import {
  View, TouchableOpacity, Modal, Text, TextInput,
  ScrollView, Alert, ActivityIndicator, FlatList, Platform,
  KeyboardAvoidingView,
} from 'react-native';
import { useAuthStore } from '../../lib/store';
import {
  FileText, QrCode, LayoutDashboard, User, Plus, X,
  ShoppingCart, Pencil, Trash2, CheckCheck,
} from 'lucide-react-native';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../../lib/api';
import { useDropdownOptions, usePendingCount } from '../../hooks/useDropdownOptions';
import { SelectField } from '../../components/ui/SelectField';
import { useModalStore } from '../../lib/modalStore';

// ── Styles ────────────────────────────────────────────────────────────────────
const fieldLabel: any = {
  fontSize: 11, fontWeight: '700', color: '#0038A8',
  marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.8,
};
const fieldLabelMuted: any = { ...fieldLabel, color: '#475569' };
const req: any = { color: '#EF4444' };
const input: any = {
  backgroundColor: '#fff', borderRadius: 12,
  paddingHorizontal: 14, paddingVertical: 13, marginBottom: 16,
  borderWidth: 1.5, borderColor: '#E2E8F0', fontSize: 14.5, color: '#1E293B',
};

// ── Types ─────────────────────────────────────────────────────────────────────
type CartItem = {
  tmpId: string;
  fromOffice: string;
  senderName: string;
  docName: string;
  category: string;
  referredTo: string;
  remarks: string;
};

const EMPTY_FORM = {
  fromOffice: '', senderName: '', docName: '',
  category: '', referredTo: '', remarks: '',
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

// ── Component ─────────────────────────────────────────────────────────────────
export default function AppLayout() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuthStore();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace('/(auth)/login');
    }
  }, [isAuthenticated, isLoading]);

  // Form state
  const [modalVisible, setModalVisible] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingTmpId, setEditingTmpId] = useState<string | null>(null);
  const [duplicateWarning, setDuplicateWarning] = useState<{ id: string; doc_id: string; doc_name: string; status: string }[]>([]);

  // Cart state
  const [cart, setCart] = useState<CartItem[]>([]);
  const [cartVisible, setCartVisible] = useState(false);

  const { data: dropdownOptions } = useDropdownOptions();
  const { data: pendingCount } = usePendingCount();

  // Sync cart count to global store so dashboard can read it
  const { setCartCount, addModalTrigger, cartOpenTrigger } = useModalStore();
  const prevAddTrigger = useRef(0);
  const prevCartTrigger = useRef(0);

  useEffect(() => { setCartCount(cart.length); }, [cart.length]);
  useEffect(() => {
    if (addModalTrigger > prevAddTrigger.current) {
      prevAddTrigger.current = addModalTrigger;
      openForm();
    }
  }, [addModalTrigger]);
  useEffect(() => {
    if (cartOpenTrigger > prevCartTrigger.current) {
      prevCartTrigger.current = cartOpenTrigger;
      setModalVisible(false);
      setCartVisible(true);
    }
  }, [cartOpenTrigger]);

  const categoryOptions = dropdownOptions?.category ?? [];
  const staffNames = dropdownOptions?.referred_to ?? [];

  const setField = (key: keyof typeof EMPTY_FORM) => (val: string) =>
    setForm((f) => ({ ...f, [key]: val }));

  // ── Form handlers ─────────────────────────────────────────────────────────

  const openForm = () => {
    setForm(EMPTY_FORM);
    setEditingTmpId(null);
    setDuplicateWarning([]);
    setModalVisible(true);
  };

  const closeForm = () => {
    setModalVisible(false);
    setForm(EMPTY_FORM);
    setEditingTmpId(null);
    setDuplicateWarning([]);
  };

  const handleDocNameBlur = async () => {
    const dupes = await checkDuplicateName(form.docName);
    setDuplicateWarning(dupes);
  };

  const handleAddToCart = () => {
    if (!form.fromOffice.trim() || !form.docName.trim()) {
      Alert.alert('Required Fields', 'Please fill in Unit/Office and Content/Particulars.');
      return;
    }

    if (editingTmpId) {
      // Update existing cart item
      setCart((c) => c.map((item) =>
        item.tmpId === editingTmpId ? { ...form, tmpId: editingTmpId } : item
      ));
      setEditingTmpId(null);
    } else {
      // Add new item
      const tmpId = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setCart((c) => [...c, { ...form, tmpId }]);
    }

    setForm(EMPTY_FORM);
    setDuplicateWarning([]);
    // Keep modal open so user can add another document
  };

  const handleEditCartItem = (item: CartItem) => {
    setCartVisible(false);
    setForm({
      fromOffice: item.fromOffice,
      senderName: item.senderName,
      docName: item.docName,
      category: item.category,
      referredTo: item.referredTo,
      remarks: item.remarks,
    });
    setEditingTmpId(item.tmpId);
    setDuplicateWarning([]);
    setModalVisible(true);
  };

  const handleRemoveCartItem = (tmpId: string) => {
    Alert.alert('Remove', 'Remove this document from the log list?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: () => setCart((c) => c.filter((i) => i.tmpId !== tmpId)) },
    ]);
  };

  // ── Submit all mutation ───────────────────────────────────────────────────

  const { mutate: submitAll, isPending: submittingAll } = useMutation({
    mutationFn: async () => {
      const results = [];
      for (const item of cart) {
        const res = await api.post('/documents', {
          doc_name: item.docName.trim(),
          category: item.category.trim(),
          from_office: item.fromOffice.trim(),
          sender_org: item.fromOffice.trim(),
          sender_name: item.senderName.trim(),
          referred_to: item.referredTo.trim(),
          remarks: item.remarks.trim(),
        });
        results.push(res.data);
      }
      return results;
    },
    onSuccess: (results) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      setCart([]);
      setCartVisible(false);
      closeForm();
      Alert.alert('Success', `${results.length} document${results.length !== 1 ? 's' : ''} logged successfully.`);
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.error || 'Failed to log documents. Please try again.';
      Alert.alert('Error', msg);
    },
  });

  const handleSubmitAll = () => {
    if (cart.length === 0) return;
    Alert.alert(
      'Log All Documents',
      `Save all ${cart.length} document${cart.length !== 1 ? 's' : ''} to the system?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Log All', onPress: () => submitAll() },
      ]
    );
  };

  // ── Cart item renderer ────────────────────────────────────────────────────

  const renderCartItem = ({ item, index }: { item: CartItem; index: number }) => (
    <View style={{
      backgroundColor: '#fff',
      borderRadius: 14,
      padding: 14,
      marginBottom: 10,
      borderWidth: 0.5,
      borderColor: '#E2E8F0',
    }}>
      {/* Number + doc name */}
      <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginBottom: 8 }}>
        <View style={{
          width: 24, height: 24, borderRadius: 12,
          backgroundColor: '#0038A8', alignItems: 'center', justifyContent: 'center',
          marginTop: 1,
        }}>
          <Text style={{ color: '#fff', fontSize: 11, fontWeight: '800' }}>{index + 1}</Text>
        </View>
        <Text style={{ flex: 1, fontSize: 14, fontWeight: '700', color: '#1E293B', lineHeight: 20 }}>
          {item.docName}
        </Text>
      </View>

      {/* Details */}
      <View style={{ gap: 3, marginLeft: 34, marginBottom: 12 }}>
        {item.fromOffice ? (
          <Text style={{ fontSize: 12, color: '#475569' }}>
            <Text style={{ color: '#94A3B8' }}>From: </Text>{item.fromOffice}
          </Text>
        ) : null}
        {item.senderName ? (
          <Text style={{ fontSize: 12, color: '#475569' }}>
            <Text style={{ color: '#94A3B8' }}>Sender: </Text>{item.senderName}
          </Text>
        ) : null}
        {item.category ? (
          <Text style={{ fontSize: 12, color: '#475569' }}>
            <Text style={{ color: '#94A3B8' }}>Type: </Text>{item.category}
          </Text>
        ) : null}
        {item.referredTo ? (
          <Text style={{ fontSize: 12, color: '#475569' }}>
            <Text style={{ color: '#94A3B8' }}>Referred To: </Text>{item.referredTo}
          </Text>
        ) : null}
        {item.remarks ? (
          <Text style={{ fontSize: 12, color: '#94A3B8', fontStyle: 'italic' }} numberOfLines={1}>
            {item.remarks}
          </Text>
        ) : null}
      </View>

      {/* Actions */}
      <View style={{ flexDirection: 'row', gap: 8, marginLeft: 34 }}>
        <TouchableOpacity
          onPress={() => handleEditCartItem(item)}
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 5,
            backgroundColor: '#EFF6FF', borderRadius: 8,
            paddingHorizontal: 12, paddingVertical: 7,
          }}
        >
          <Pencil size={13} color="#0038A8" />
          <Text style={{ color: '#0038A8', fontSize: 12, fontWeight: '700' }}>Edit</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => handleRemoveCartItem(item.tmpId)}
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 5,
            backgroundColor: '#FEF2F2', borderRadius: 8,
            paddingHorizontal: 12, paddingVertical: 7,
          }}
        >
          <Trash2 size={13} color="#EF4444" />
          <Text style={{ color: '#EF4444', fontSize: 12, fontWeight: '700' }}>Remove</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: '#0038A8',
          tabBarInactiveTintColor: '#94A3B8',
          tabBarStyle: {
            position: 'absolute',
            bottom: 28, left: 20, right: 20,
            height: 64, borderRadius: 32,
            backgroundColor: '#FFFFFF', borderTopWidth: 0,
            elevation: 10,
            shadowColor: '#0038A8',
            shadowOffset: { width: 0, height: 6 },
            shadowOpacity: 0.12, shadowRadius: 16,
            paddingBottom: 0, paddingHorizontal: 8,
            overflow: 'visible',
            borderWidth: 0.5, borderColor: '#E2E8F0',
          },
          tabBarLabelStyle: { fontSize: 10.5, fontWeight: '700', marginTop: -2, letterSpacing: 0.2 },
          tabBarItemStyle: { paddingVertical: 4 },
        }}
      >
        <Tabs.Screen
          name="dashboard"
          options={{ title: 'Dashboard', tabBarIcon: ({ color }) => <LayoutDashboard size={22} color={color} /> }}
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
                  onPress={openForm}
                  activeOpacity={0.85}
                  style={{
                    position: 'absolute', top: -26,
                    width: 56, height: 56, borderRadius: 28,
                    backgroundColor: '#0038A8',
                    alignItems: 'center', justifyContent: 'center',
                    borderWidth: 3, borderColor: '#fff',
                    shadowColor: '#0038A8',
                    shadowOffset: { width: 0, height: 6 },
                    shadowOpacity: 0.35, shadowRadius: 10, elevation: 10,
                  }}
                >
                  <Plus size={26} color="#fff" />
                  {cart.length > 0 && (
                    <View style={{
                      position: 'absolute', top: -4, right: -4,
                      width: 18, height: 18, borderRadius: 9,
                      backgroundColor: '#EF4444',
                      alignItems: 'center', justifyContent: 'center',
                      borderWidth: 2, borderColor: '#fff',
                    }}>
                      <Text style={{ color: '#fff', fontSize: 9, fontWeight: '800' }}>
                        {cart.length > 9 ? '9+' : cart.length}
                      </Text>
                    </View>
                  )}
                </TouchableOpacity>
              </View>
            ),
          }}
        />

        <Tabs.Screen
          name="scanner"
          options={{ title: 'Scan', tabBarIcon: ({ color }) => <QrCode size={22} color={color} /> }}
        />
        <Tabs.Screen
          name="profile"
          options={{ title: 'Profile', tabBarIcon: ({ color }) => <User size={22} color={color} /> }}
        />
        <Tabs.Screen name="documents/[id]" options={{ href: null }} />
        <Tabs.Screen name="documents/new" options={{ href: null }} />
        <Tabs.Screen name="notifications" options={{ href: null }} />
        <Tabs.Screen name="activity-log" options={{ href: null }} />
        <Tabs.Screen name="routing-slips" options={{ href: null }} />
        <Tabs.Screen name="staff-stats" options={{ href: null }} />
        <Tabs.Screen name="admin-users" options={{ href: null }} />
        <Tabs.Screen name="receive-docs" options={{ href: null }} />
      </Tabs>

      {/* ══════════════════════════════════════════════════════════════════
          ADD / EDIT DOCUMENT FORM MODAL
      ══════════════════════════════════════════════════════════════════ */}
      <Modal visible={modalVisible} animationType="slide" transparent onRequestClose={closeForm}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={{ flex: 1 }}
        >
          <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
            <TouchableOpacity
              style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
              onPress={closeForm}
              activeOpacity={1}
            />

            <View style={{
              backgroundColor: '#F8FAFC',
              borderTopLeftRadius: 28, borderTopRightRadius: 28,
              maxHeight: '92%', overflow: 'hidden',
            }}>

              {/* Header */}
              <View style={{
                backgroundColor: '#0038A8',
                paddingTop: 20, paddingBottom: 16, paddingHorizontal: 20,
              }}>
                {/* Drag handle */}
                <View style={{ position: 'absolute', top: 10, left: 0, right: 0, alignItems: 'center' }}>
                  <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.30)' }} />
                </View>

                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 18, fontWeight: '800', color: '#fff', letterSpacing: -0.3 }}>
                      {editingTmpId ? 'Edit Document' : 'New Document'}
                    </Text>
                    <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.60)', marginTop: 2 }}>
                      {editingTmpId ? 'Update this entry in the log list' : 'Fill in the document details below'}
                    </Text>
                  </View>

                  {/* Cart badge button */}
                  {cart.length > 0 && (
                    <TouchableOpacity
                      onPress={() => { setModalVisible(false); setCartVisible(true); }}
                      style={{
                        flexDirection: 'row', alignItems: 'center', gap: 6,
                        backgroundColor: 'rgba(255,255,255,0.18)',
                        borderRadius: 20, paddingHorizontal: 12, paddingVertical: 6,
                        marginRight: 10, borderWidth: 1, borderColor: 'rgba(255,255,255,0.25)',
                      }}
                    >
                      <ShoppingCart size={14} color="#fff" />
                      <Text style={{ color: '#fff', fontSize: 12, fontWeight: '800' }}>{cart.length}</Text>
                    </TouchableOpacity>
                  )}

                  <TouchableOpacity
                    onPress={closeForm}
                    style={{
                      width: 34, height: 34, borderRadius: 17,
                      backgroundColor: 'rgba(255,255,255,0.15)',
                      alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    <X size={18} color="#fff" />
                  </TouchableOpacity>
                </View>
              </View>

              {/* Form */}
              <ScrollView
                contentContainerStyle={{ padding: 20, paddingBottom: 8 }}
                showsVerticalScrollIndicator={false}
                keyboardShouldPersistTaps="handled"
                keyboardDismissMode="interactive"
              >
                <Text style={fieldLabel}>Unit / Office / School <Text style={req}>*</Text></Text>
                <TextInput
                  value={form.fromOffice}
                  onChangeText={setField('fromOffice')}
                  placeholder="e.g. Palo Central School, Leyte District I"
                  style={input}
                  placeholderTextColor="#CBD5E1"
                />

                <Text style={fieldLabelMuted}>Sender Name & Designation</Text>
                <TextInput
                  value={form.senderName}
                  onChangeText={setField('senderName')}
                  placeholder="e.g. Juan dela Cruz, Principal II"
                  style={input}
                  placeholderTextColor="#CBD5E1"
                />

                <Text style={fieldLabel}>Content / Particulars <Text style={req}>*</Text></Text>
                <TextInput
                  value={form.docName}
                  onChangeText={(v) => { setField('docName')(v); setDuplicateWarning([]); }}
                  onBlur={handleDocNameBlur}
                  placeholder="e.g. Plantilla of Personnel"
                  style={input}
                  placeholderTextColor="#CBD5E1"
                />

                {duplicateWarning.length > 0 && (
                  <View style={{
                    backgroundColor: '#FFF7ED', borderRadius: 10, padding: 12,
                    marginTop: -10, marginBottom: 16,
                    borderWidth: 1, borderColor: '#FED7AA',
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
                />

                <Text style={fieldLabelMuted}>Referred To</Text>
                <SelectField
                  value={form.referredTo}
                  onChange={setField('referredTo')}
                  options={staffNames}
                  placeholder="Search staff name…"
                  label="Referred To"
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
                />
              </ScrollView>

              {/* Footer */}
              <View style={{
                padding: 16, paddingBottom: Platform.OS === 'ios' ? 32 : 20,
                borderTopWidth: 0.5, borderTopColor: '#E2E8F0',
                backgroundColor: '#F8FAFC', gap: 10,
              }}>
                {/* Primary: Add to cart */}
                <TouchableOpacity
                  onPress={handleAddToCart}
                  activeOpacity={0.85}
                  style={{
                    backgroundColor: '#0038A8', borderRadius: 13,
                    paddingVertical: 15, alignItems: 'center',
                    flexDirection: 'row', justifyContent: 'center', gap: 8,
                  }}
                >
                  <Plus size={18} color="#fff" />
                  <Text style={{ color: '#fff', fontSize: 15, fontWeight: '700', letterSpacing: 0.2 }}>
                    {editingTmpId ? 'Save Changes' : 'Add to Log List'}
                  </Text>
                </TouchableOpacity>

                {/* View cart (shown when cart has items and not editing) */}
                {cart.length > 0 && !editingTmpId && (
                  <TouchableOpacity
                    onPress={() => { setModalVisible(false); setCartVisible(true); }}
                    activeOpacity={0.85}
                    style={{
                      backgroundColor: '#F0FDF4', borderRadius: 13,
                      paddingVertical: 14, alignItems: 'center',
                      flexDirection: 'row', justifyContent: 'center', gap: 8,
                      borderWidth: 1.5, borderColor: '#BBF7D0',
                    }}
                  >
                    <ShoppingCart size={17} color="#16A34A" />
                    <Text style={{ color: '#16A34A', fontSize: 14, fontWeight: '700' }}>
                      View Log List ({cart.length})
                    </Text>
                  </TouchableOpacity>
                )}

                <TouchableOpacity
                  onPress={closeForm}
                  style={{
                    borderWidth: 1.5, borderColor: '#E2E8F0',
                    borderRadius: 13, paddingVertical: 13,
                    alignItems: 'center', backgroundColor: '#fff',
                  }}
                >
                  <Text style={{ color: '#64748B', fontSize: 14, fontWeight: '600' }}>
                    {editingTmpId ? 'Cancel Edit' : 'Cancel'}
                  </Text>
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

      {/* ══════════════════════════════════════════════════════════════════
          CART / LOG LIST REVIEW MODAL
      ══════════════════════════════════════════════════════════════════ */}
      <Modal visible={cartVisible} animationType="slide" transparent onRequestClose={() => setCartVisible(false)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
          <TouchableOpacity
            style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
            onPress={() => setCartVisible(false)}
            activeOpacity={1}
          />

          <View style={{
            backgroundColor: '#F8FAFC',
            borderTopLeftRadius: 28, borderTopRightRadius: 28,
            maxHeight: '92%', overflow: 'hidden',
          }}>

            {/* Header */}
            <View style={{
              backgroundColor: '#0038A8',
              paddingTop: 20, paddingBottom: 16, paddingHorizontal: 20,
            }}>
              <View style={{ position: 'absolute', top: 10, left: 0, right: 0, alignItems: 'center' }}>
                <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.30)' }} />
              </View>

              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
                <View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <ShoppingCart size={18} color="#fff" />
                    <Text style={{ fontSize: 18, fontWeight: '800', color: '#fff' }}>Log List</Text>
                    <View style={{
                      backgroundColor: '#EF4444', borderRadius: 12,
                      paddingHorizontal: 8, paddingVertical: 2,
                    }}>
                      <Text style={{ color: '#fff', fontSize: 12, fontWeight: '800' }}>{cart.length}</Text>
                    </View>
                  </View>
                  <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.60)', marginTop: 2 }}>
                    Review before logging to the system
                  </Text>
                </View>

                <TouchableOpacity
                  onPress={() => setCartVisible(false)}
                  style={{
                    width: 34, height: 34, borderRadius: 17,
                    backgroundColor: 'rgba(255,255,255,0.15)',
                    alignItems: 'center', justifyContent: 'center',
                  }}
                >
                  <X size={18} color="#fff" />
                </TouchableOpacity>
              </View>
            </View>

            {/* Cart items */}
            <FlatList
              data={cart}
              keyExtractor={(item) => item.tmpId}
              renderItem={renderCartItem}
              contentContainerStyle={{ padding: 16, paddingBottom: 8 }}
              showsVerticalScrollIndicator={false}
              ListEmptyComponent={
                <View style={{ alignItems: 'center', paddingVertical: 48 }}>
                  <Text style={{ color: '#94A3B8', fontSize: 14 }}>No documents in the log list.</Text>
                </View>
              }
            />

            {/* Footer */}
            <View style={{
              padding: 16, paddingBottom: Platform.OS === 'ios' ? 32 : 20,
              borderTopWidth: 0.5, borderTopColor: '#E2E8F0',
              backgroundColor: '#F8FAFC', gap: 10,
            }}>
              {/* Submit all */}
              <TouchableOpacity
                onPress={handleSubmitAll}
                disabled={submittingAll || cart.length === 0}
                activeOpacity={0.85}
                style={{
                  backgroundColor: submittingAll ? '#93C5FD' : '#0038A8',
                  borderRadius: 13, paddingVertical: 15,
                  alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8,
                }}
              >
                {submittingAll ? (
                  <>
                    <ActivityIndicator color="#fff" size="small" />
                    <Text style={{ color: '#fff', fontSize: 15, fontWeight: '700' }}>
                      Logging documents…
                    </Text>
                  </>
                ) : (
                  <>
                    <CheckCheck size={18} color="#fff" />
                    <Text style={{ color: '#fff', fontSize: 15, fontWeight: '700', letterSpacing: 0.2 }}>
                      Log All {cart.length} Document{cart.length !== 1 ? 's' : ''}
                    </Text>
                  </>
                )}
              </TouchableOpacity>

              {/* Add another */}
              <TouchableOpacity
                onPress={() => { setCartVisible(false); openForm(); }}
                disabled={submittingAll}
                style={{
                  borderWidth: 1.5, borderColor: '#BFDBFE',
                  borderRadius: 13, paddingVertical: 13,
                  alignItems: 'center', backgroundColor: '#EFF6FF',
                  flexDirection: 'row', justifyContent: 'center', gap: 8,
                }}
              >
                <Plus size={16} color="#0038A8" />
                <Text style={{ color: '#0038A8', fontSize: 14, fontWeight: '700' }}>Add Another Document</Text>
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
      </Modal>
    </>
  );
}
