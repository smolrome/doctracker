/**
 * Client Submit Screen — mirrors the web app's 3-step cart-based flow:
 *   Step 1 — Select Office (modal grid)
 *   Step 2 — Add Documents to cart (form) + review cart
 *   Step 3 — Submission confirmation with QR codes for each document
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { useFocusEffect, useLocalSearchParams } from 'expo-router';
import {
  View, Text, ScrollView, TextInput, TouchableOpacity, FlatList,
  Alert, ActivityIndicator, StatusBar, KeyboardAvoidingView, Platform,
  Modal, Image,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Building2, FileText, Plus, Trash2, Send, ChevronDown, ChevronUp,
  Search, CheckCircle, Download, QrCode, RotateCcw, X, WifiOff,
} from 'lucide-react-native';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import * as Print from 'expo-print';
import api from '../../lib/api';
import { useNetwork } from '../../hooks/useNetwork';
import { offlineQueue } from '../../lib/offlineQueue';

// ── Types ──────────────────────────────────────────────────────────────────────

type SavedOffice = {
  office_name: string;
  office_slug: string;
  primary_recipient?: string;
  primary_recipient_name?: string;
};

type StaffMember = {
  username: string;
  full_name: string;
  is_primary?: boolean;
};

type CartItem = {
  tmp_id: string;
  doc_name: string;
  unit_office: string;
  referred_to: string;
  category: string;
  description: string;
  notes: string;
};

type SubmittedDoc = {
  id: string;
  doc_id: string;
  doc_name: string;
  qr_base64?: string;
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function uid() { return Math.random().toString(36).slice(2, 10).toUpperCase(); }

// Matches backend DEFAULT_CATEGORY_OPTIONS — used only if the API call fails
const CATEGORIES = [
  'Letter', 'Memorandum', 'Report', 'Application', 'Voucher',
  'Plantilla', 'Payroll', 'Memo', 'Request', 'Endorsement',
  'Order', 'Notice', 'Circular', 'Certificate', 'Other',
];

function StepIndicator({ step }: { step: 1 | 2 | 3 }) {
  const steps = [
    { n: 1, label: 'Add Documents' },
    { n: 2, label: 'Review List' },
    { n: 3, label: 'Get QR Codes' },
  ];
  return (
    <View style={{ flexDirection: 'row', backgroundColor: '#fff', borderBottomWidth: 0.5, borderBottomColor: '#E2E8F0' }}>
      {steps.map((s, i) => {
        const done = step > s.n;
        const active = step === s.n;
        return (
          <View key={s.n} style={{
            flex: 1, alignItems: 'center', paddingVertical: 12,
            borderBottomWidth: 3,
            borderBottomColor: active ? '#0038A8' : done ? '#16A34A' : 'transparent',
          }}>
            <View style={{
              width: 26, height: 26, borderRadius: 13,
              backgroundColor: active ? '#0038A8' : done ? '#16A34A' : '#E2E8F0',
              alignItems: 'center', justifyContent: 'center', marginBottom: 4,
            }}>
              {done
                ? <CheckCircle size={14} color="#fff" />
                : <Text style={{ color: active ? '#fff' : '#94A3B8', fontWeight: '800', fontSize: 12 }}>{s.n}</Text>
              }
            </View>
            <Text style={{
              fontSize: 10.5, fontWeight: '700',
              color: active ? '#0038A8' : done ? '#16A34A' : '#94A3B8',
            }}>
              {s.label}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function Submit() {
  const router = useRouter();
  const { officeSlug: qrOfficeSlug, officeName: qrOfficeName } = useLocalSearchParams<{
    officeSlug?: string;
    officeName?: string;
  }>();
  const queryClient = useQueryClient();
  const { isOnline } = useNetwork();

  // ── Step state
  const [step, setStep] = useState<1 | 2 | 3>(1);

  // ── Office selection
  const [selectedOffice, setSelectedOffice]   = useState<SavedOffice | null>(null);
  const [selectedStaff, setSelectedStaff]     = useState<string>('');   // username or ''=auto
  const [officeModalVisible, setOfficeModalVisible] = useState(false);
  const [officeSearch, setOfficeSearch]       = useState('');
  const [staffDropdownOpen, setStaffDropdownOpen] = useState(false);
  const [catModalVisible, setCatModalVisible]  = useState(false);
  const [catSearch, setCatSearch]              = useState('');

  // ── Cart
  const [cart, setCart]       = useState<CartItem[]>([]);
  const [showForm, setShowForm] = useState(true);

  // ── Form fields
  const [unitOffice, setUnitOffice]   = useState('');
  const [docName, setDocName]         = useState('');
  const [category, setCategory]       = useState('');
  const [referredTo, setReferredTo]   = useState('');
  const [description, setDescription] = useState('');
  const [notes, setNotes] = useState('');

  // ── Submitted results
  const [submitted, setSubmitted] = useState<SubmittedDoc[]>([]);

  // Set to true after a successful submission so that the NEXT focus event
  // (i.e. the user leaves step 3 and comes back to the tab) resets the form.
  // Using a ref avoids the [step] dependency trap where changing step to 3
  // would cause useCallback to produce a new function, causing useFocusEffect
  // to re-fire while the screen is still focused and immediately reset step 3→1.
  const needsResetRef = useRef(false);

  useFocusEffect(
    useCallback(() => {
      if (needsResetRef.current) {
        needsResetRef.current = false;
        setStep(1);
        setSelectedOffice(null);
        setSelectedStaff('');
        setCart([]);
        setDocName('');
        setUnitOffice('');
        setReferredTo('');
        setCategory('');
        setDescription('');
        setNotes('');
        setShowForm(true);
        setSubmitted([]);
        setCatSearch('');
      }
    }, []) // empty deps — callback identity never changes, won't re-fire while focused
  );

  // ── Data queries
  const { data: offices = [], isLoading: officesLoading } = useQuery({
    queryKey: ['offices'],
    queryFn: async () => {
      const res = await api.get('/offices');
      return (res.data ?? []) as SavedOffice[];
    },
    staleTime: 1000 * 60 * 5,
  });

  useEffect(() => {
    if (!qrOfficeSlug) return;
    const match = offices.find(o => o.office_slug === qrOfficeSlug);
    if (match) {
      setSelectedOffice(match);
      setSelectedStaff(match.primary_recipient || '');
      setReferredTo(match.office_name);
    } else if (qrOfficeName) {
      const synthetic: SavedOffice = {
        office_name: qrOfficeName,
        office_slug: qrOfficeSlug,
        primary_recipient: '',
      };
      setSelectedOffice(synthetic);
      setReferredTo(qrOfficeName);
    }
  }, [offices, qrOfficeSlug]);

  const { data: staffList = [] } = useQuery({
    queryKey: ['office-staff', selectedOffice?.office_slug],
    queryFn: async () => {
      if (!selectedOffice?.office_slug) return [];
      const res = await api.get(`/offices/${selectedOffice.office_slug}/staff`);
      return (res.data ?? []) as StaffMember[];
    },
    enabled: !!selectedOffice?.office_slug,
    staleTime: 1000 * 60 * 5,
  });

  // queryKey matches prefetch.ts exactly so the prefetched cache is reused offline.
  // The stored shape is Record<string, string[]> — same normalization as prefetch.ts.
  const { data: dropdownOptions } = useQuery<Record<string, string[]>>({
    queryKey: ['dropdown-options'],
    queryFn: async () => {
      const res = await api.get('/dropdown-options');
      const raw: Record<string, unknown> = res.data ?? {};
      const normalized: Record<string, string[]> = {};
      for (const [key, val] of Object.entries(raw)) {
        if (Array.isArray(val)) {
          normalized[key] = val as string[];
        } else if (val && typeof val === 'object' && Array.isArray((val as any).options)) {
          normalized[key] = (val as any).options as string[];
        }
      }
      return normalized;
    },
    staleTime: 1000 * 60 * 10,
  });
  const categoryOptions = dropdownOptions?.category?.length ? dropdownOptions.category : CATEGORIES;

  // ── Submit mutation (offline-aware)
  const submitMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        office_slug:    selectedOffice?.office_slug || '',
        office_name:    selectedOffice?.office_name || '',
        selected_staff: selectedStaff || '',
        items: cart.map((item) => ({
          doc_name:    item.doc_name,
          referred_to: item.referred_to,
          unit_office: item.unit_office,
          category:    item.category,
          description: item.description,
          notes:       item.notes,
        })),
      };

      if (!isOnline) {
        // No internet — save to offline queue and return a sentinel value
        const queueId = await offlineQueue.enqueue(payload);
        return { _queued: true, queueId, submitted: [] as SubmittedDoc[] };
      }

      return api.post('/client/submit-mobile', payload);
    },
    onSuccess: async (res: any) => {
      // ── Offline path: document queued, not yet submitted
      if (res?._queued) {
        setCart([]);
        // Tell my-docs.tsx to re-read the queue immediately so the amber
        // "Queued" card appears without waiting for a manual screen refresh.
        queryClient.invalidateQueries({ queryKey: ['offline-queue'] });
        Alert.alert(
          '📵 Saved for Later',
          `You're offline. Your ${cart.length} document${cart.length !== 1 ? 's' : ''} will be automatically submitted once you reconnect.`,
          [{ text: 'OK', onPress: handleReset }],
        );
        return;
      }

      // ── Online path: normal submission
      queryClient.invalidateQueries({ queryKey: ['client-docs'] });
      queryClient.invalidateQueries({ queryKey: ['client-docs-all'] });
      const submittedDocs: SubmittedDoc[] = res.data?.submitted ?? [];

      // Fetch QR for each submitted doc
      const withQR = await Promise.all(
        submittedDocs.map(async (doc) => {
          try {
            const qrRes = await api.get(`/qr/generate/${doc.id}`);
            return { ...doc, qr_base64: qrRes.data?.qr_base64 || '' };
          } catch {
            return doc;
          }
        }),
      );
      setSubmitted(withQR);
      setCart([]);
      needsResetRef.current = true; // arm the reset — fires when user leaves & returns to tab
      setStep(3);
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Submission failed. Please try again.'),
  });

  // ── Handlers
  const handleSelectOffice = (office: SavedOffice) => {
    setSelectedOffice(office);
    // Pre-select the admin-assigned receiving staff (primary_recipient)
    setSelectedStaff(office.primary_recipient || '');
    setOfficeModalVisible(false);
    setOfficeSearch('');
    // Pre-fill referred_to with office name
    setReferredTo(office.office_name);
  };

  const handleAddToCart = () => {
    if (!docName.trim()) { Alert.alert('Required', 'Content / Particulars is required.'); return; }
    if (!referredTo.trim()) { Alert.alert('Required', '"Referred To" is required.'); return; }
    if (!selectedOffice) { Alert.alert('Required', 'Please select an office first.'); return; }
    if (cart.length >= 50) { Alert.alert('Limit Reached', 'Maximum 50 documents per submission.'); return; }
    setCart((prev) => [...prev, {
      tmp_id:      uid(),
      doc_name:    docName.trim(),
      unit_office: unitOffice.trim(),
      referred_to: referredTo.trim(),
      category:    category.trim(),
      description: description.trim(),
      notes:       notes.trim(),
    }]);
    // Reset doc fields but keep office-related ones
    setDocName('');
    setCategory('');
    setDescription('');
    setNotes('');
    setShowForm(false);
  };

  const handleRemove = (tmp_id: string) => {
    setCart((prev) => prev.filter((i) => i.tmp_id !== tmp_id));
  };

  const handleSubmitAll = () => {
    if (cart.length === 0) { Alert.alert('Empty Cart', 'Add at least one document first.'); return; }
    Alert.alert(
      'Submit Documents',
      `Submit ${cart.length} document${cart.length !== 1 ? 's' : ''} to ${selectedOffice?.office_name || 'the office'}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Submit All', onPress: () => submitMutation.mutate() },
      ],
    );
  };

  const handleDownloadQR = async (doc: SubmittedDoc) => {
    if (!doc.qr_base64) { Alert.alert('Not Ready', 'QR code not available.'); return; }
    try {
      // Ensure we have a proper data URI for embedding in HTML
      const dataUri = doc.qr_base64.startsWith('data:')
        ? doc.qr_base64
        : `data:image/png;base64,${doc.qr_base64}`;

      // Generate a PDF with the QR code embedded — more reliable than raw PNG
      // sharing on Android (no FileProvider / content URI issues).
      const { uri } = await Print.printToFileAsync({
        html: `
          <html>
            <body style="margin:0;padding:40px;text-align:center;font-family:sans-serif;background:#fff;">
              <p style="color:#0038A8;font-size:11px;font-weight:700;text-transform:uppercase;
                        letter-spacing:1px;margin:0 0 8px;">DepEd LAKAD</p>
              <h2 style="color:#1E293B;font-size:18px;margin:0 0 6px;line-height:1.4;">
                ${doc.doc_name || 'Document'}
              </h2>
              <p style="color:#0038A8;font-size:13px;font-weight:700;
                        letter-spacing:1px;margin:0 0 24px;">#${doc.doc_id}</p>
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
          dialogTitle: `QR Code — ${doc.doc_id}`,
          UTI: 'com.adobe.pdf',
        });
      } else {
        Alert.alert('Saved', `QR saved to: ${uri}`);
      }
    } catch (err: any) {
      console.error('[QR Download]', err);
      Alert.alert('Error', err?.message || 'Could not save QR code. Please try again.');
    }
  };

  const handleReset = () => {
    setStep(1);
    setSelectedOffice(null);
    setSelectedStaff('');
    setCart([]);
    setDocName('');
    setUnitOffice('');
    setReferredTo('');
    setCategory('');
    setDescription('');
    setNotes('');
    setShowForm(true);
    setSubmitted([]);
    setCatSearch('');
  };

  const filteredOffices = offices.filter((o) =>
    o.office_name.toLowerCase().includes(officeSearch.toLowerCase()),
  );

  // ── Selected staff display name
  const primaryRecipientName = selectedOffice?.primary_recipient_name || selectedOffice?.primary_recipient || '';
  const selectedStaffName =
    staffList.find((s) => s.username === selectedStaff)?.full_name
    || (primaryRecipientName ? primaryRecipientName : 'Auto-assign');

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 3 — Confirmation with QR codes
  // ═══════════════════════════════════════════════════════════════════════════

  if (step === 3) {
    return (
      <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
        <StatusBar barStyle="light-content" backgroundColor="#0038A8" />
        <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 20, paddingHorizontal: 20 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <CheckCircle size={22} color="#fff" />
            <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800' }}>
              {submitted.length === 1 ? 'Document Submitted!' : `${submitted.length} Documents Submitted!`}
            </Text>
          </View>
          <Text style={{ color: 'rgba(255,255,255,0.70)', fontSize: 13, marginTop: 4 }}>
            Save or print each QR code — you'll need them to track your documents
          </Text>
        </View>

        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 80 }}>
          {/* Instructions */}
          <View style={{
            backgroundColor: '#EFF6FF', borderRadius: 12, padding: 14,
            borderWidth: 1, borderColor: '#BFDBFE', marginBottom: 16,
          }}>
            <Text style={{ color: '#1E40AF', fontSize: 13, lineHeight: 20 }}>
              📌 Staff at the office will scan your QR when they receive each document. Track status anytime from <Text style={{ fontWeight: '700' }}>My Documents</Text>.
            </Text>
          </View>

          {/* QR cards for each submitted doc */}
          {submitted.map((doc, idx) => (
            <View key={doc.id} style={{
              backgroundColor: '#fff', borderRadius: 14, padding: 20,
              borderWidth: 0.5, borderColor: '#E2E8F0', marginBottom: 12,
            }}>
              {/* Card header */}
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <Text style={{ color: '#64748B', fontSize: 12, fontWeight: '700' }}>
                  Document {idx + 1} of {submitted.length}
                </Text>
                <View style={{ backgroundColor: '#FEF3C7', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 3 }}>
                  <Text style={{ color: '#B45309', fontSize: 11, fontWeight: '700' }}>⏳ Pending</Text>
                </View>
              </View>

              <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 15, marginBottom: 6 }} numberOfLines={3}>
                {doc.doc_name}
              </Text>
              <Text style={{ color: '#0038A8', fontWeight: '700', fontSize: 13, letterSpacing: 1, marginBottom: 14 }}>
                #{doc.doc_id}
              </Text>

              {/* QR code */}
              <View style={{ alignItems: 'center', marginBottom: 12 }}>
                {doc.qr_base64 ? (
                  <Image
                    source={{ uri: doc.qr_base64 }}
                    style={{ width: 160, height: 160, borderRadius: 8 }}
                    resizeMode="contain"
                  />
                ) : (
                  <View style={{ width: 160, height: 160, backgroundColor: '#F1F5F9', borderRadius: 8, alignItems: 'center', justifyContent: 'center' }}>
                    <QrCode size={40} color="#CBD5E1" />
                    <Text style={{ color: '#94A3B8', fontSize: 11, marginTop: 8 }}>Scan to track</Text>
                  </View>
                )}
                <Text style={{ color: '#94A3B8', fontSize: 11, marginTop: 8 }}>Scan to track</Text>
              </View>

              {/* Buttons */}
              <View style={{ flexDirection: 'row', gap: 10 }}>
                <TouchableOpacity
                  onPress={() => handleDownloadQR(doc)}
                  style={{
                    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
                    gap: 6, backgroundColor: '#EFF6FF', borderRadius: 10, paddingVertical: 10,
                    borderWidth: 1, borderColor: '#BFDBFE',
                  }}
                >
                  <Download size={14} color="#1E40AF" />
                  <Text style={{ color: '#1E40AF', fontWeight: '700', fontSize: 13 }}>Download QR</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => router.push(`/(client)/track/${doc.id}` as any)}
                  style={{
                    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
                    gap: 6, backgroundColor: '#F0FDF4', borderRadius: 10, paddingVertical: 10,
                    borderWidth: 1, borderColor: '#BBF7D0',
                  }}
                >
                  <FileText size={14} color="#16A34A" />
                  <Text style={{ color: '#16A34A', fontWeight: '700', fontSize: 13 }}>Track</Text>
                </TouchableOpacity>
              </View>
            </View>
          ))}
        </ScrollView>

        {/* Bottom actions */}
        <View style={{
          position: 'absolute', bottom: 76, left: 16, right: 16,
          flexDirection: 'row', gap: 10,
        }}>
          <TouchableOpacity
            onPress={() => router.replace('/(client)/my-docs' as any)}
            style={{
              flex: 1, backgroundColor: '#F1F5F9', borderRadius: 12,
              paddingVertical: 14, alignItems: 'center',
            }}
          >
            <Text style={{ color: '#475569', fontWeight: '700', fontSize: 14 }}>My Documents</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={handleReset}
            style={{
              flex: 1, backgroundColor: '#0038A8', borderRadius: 12,
              paddingVertical: 14, alignItems: 'center',
            }}
          >
            <Text style={{ color: '#fff', fontWeight: '800', fontSize: 14 }}>Submit More</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STEP 1 & 2 — Office picker + Add Docs form + Cart
  // ═══════════════════════════════════════════════════════════════════════════

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: '#F8FAFC' }}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 16, paddingHorizontal: 20 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <FileText size={20} color="#fff" />
            <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800', letterSpacing: -0.4 }}>Submit Documents</Text>
          </View>
          {cart.length > 0 && (
            <View style={{ backgroundColor: '#FCD116', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4 }}>
              <Text style={{ color: '#1E293B', fontWeight: '800', fontSize: 13 }}>{cart.length} in list</Text>
            </View>
          )}
        </View>
      </View>

      {/* ── Step indicator ──────────────────────────────────────────────────── */}
      <StepIndicator step={cart.length > 0 ? 2 : 1} />

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 140 }} keyboardShouldPersistTaps="handled">

        {/* ── OFFICE SELECTION BANNER ─────────────────────────────────────── */}
        {selectedOffice ? (
          <View style={{
            backgroundColor: '#0038A8', borderRadius: 14, padding: 16, marginBottom: 16,
          }}>
            <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 4 }}>
              Submitting Documents To:
            </Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flex: 1 }}>
                <View style={{ width: 38, height: 38, borderRadius: 19, backgroundColor: 'rgba(255,255,255,0.20)', alignItems: 'center', justifyContent: 'center' }}>
                  <Building2 size={18} color="#fff" />
                </View>
                <Text style={{ color: '#fff', fontSize: 17, fontWeight: '800', flex: 1 }} numberOfLines={2}>
                  {selectedOffice.office_name}
                </Text>
              </View>
              <TouchableOpacity
                onPress={() => setOfficeModalVisible(true)}
                style={{
                  backgroundColor: 'rgba(255,255,255,0.20)', borderRadius: 8,
                  paddingHorizontal: 12, paddingVertical: 7,
                }}
              >
                <Text style={{ color: '#fff', fontWeight: '700', fontSize: 13 }}>Change</Text>
              </TouchableOpacity>
            </View>

            {/* Staff selector */}
            <TouchableOpacity
              onPress={() => setStaffDropdownOpen(!staffDropdownOpen)}
              style={{
                backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 10,
                paddingHorizontal: 14, paddingVertical: 10,
                flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
              }}
            >
              {/* ── Receiving staff display ── */}
              {(() => {
                // Resolve the display name for whichever staff is currently selected
                const displayName =
                  staffList.find((s) => s.username === selectedStaff)?.full_name
                  || primaryRecipientName
                  || selectedStaff
                  || '';

                const hasPrimary = !!(selectedOffice?.primary_recipient || primaryRecipientName);

                if (hasPrimary && !staffDropdownOpen) {
                  // Primary recipient is set — show as a static info row (no dropdown needed)
                  return (
                    <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                      <View style={{ flex: 1 }}>
                        <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 10.5, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                          👤 Receiving Staff
                        </Text>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 }}>
                          <Text style={{ color: '#fff', fontSize: 14, fontWeight: '800' }} numberOfLines={1}>
                            {displayName || '—'}
                          </Text>
                          <View style={{ backgroundColor: 'rgba(252,209,22,0.30)', borderRadius: 10, paddingHorizontal: 7, paddingVertical: 2 }}>
                            <Text style={{ color: '#FCD116', fontSize: 10, fontWeight: '700' }}>Assigned</Text>
                          </View>
                        </View>
                      </View>
                      {/* Allow changing if more than 1 staff in list */}
                      {staffList.length > 1 && (
                        <TouchableOpacity
                          onPress={() => setStaffDropdownOpen(true)}
                          style={{ backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5 }}
                        >
                          <Text style={{ color: 'rgba(255,255,255,0.80)', fontSize: 12, fontWeight: '600' }}>Change</Text>
                        </TouchableOpacity>
                      )}
                    </View>
                  );
                }

                // No primary recipient or dropdown is open — show picker
                return (
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 10.5, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                      👤 Receiving Staff
                    </Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 2 }}>
                      <Text style={{ color: '#fff', fontSize: 13, fontWeight: '700' }} numberOfLines={1}>
                        {displayName || '— Select staff —'}
                      </Text>
                      {staffDropdownOpen
                        ? <ChevronUp size={16} color="rgba(255,255,255,0.70)" />
                        : <ChevronDown size={16} color="rgba(255,255,255,0.70)" />}
                    </View>
                  </View>
                );
              })()}
            </TouchableOpacity>

            {/* Staff dropdown items */}
            {staffDropdownOpen && (
              <View style={{
                backgroundColor: '#fff', borderRadius: 10, marginTop: 4,
                borderWidth: 1, borderColor: '#E2E8F0', overflow: 'hidden',
              }}>
                {staffList.map((s) => {
                  const isPrimary = !!s.is_primary;
                  const isSelected = selectedStaff === s.username;
                  return (
                    <TouchableOpacity
                      key={s.username}
                      onPress={() => { setSelectedStaff(s.username); setStaffDropdownOpen(false); }}
                      style={{
                        paddingHorizontal: 14, paddingVertical: 12,
                        borderBottomWidth: 0.5, borderBottomColor: '#F1F5F9',
                        backgroundColor: isSelected ? '#EFF6FF' : '#fff',
                        flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                      }}
                    >
                      <View style={{ flex: 1 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                          <Text style={{ color: isSelected ? '#0038A8' : '#1E293B', fontWeight: '600', fontSize: 14 }}>
                            {s.full_name || s.username}
                          </Text>
                          {isPrimary && (
                            <View style={{ backgroundColor: '#FEF3C7', borderRadius: 10, paddingHorizontal: 7, paddingVertical: 2 }}>
                              <Text style={{ color: '#B45309', fontSize: 10, fontWeight: '700' }}>Assigned</Text>
                            </View>
                          )}
                        </View>
                      </View>
                      {isSelected && <CheckCircle size={16} color="#0038A8" />}
                    </TouchableOpacity>
                  );
                })}
                {staffList.length === 0 && (
                  <View style={{ paddingHorizontal: 14, paddingVertical: 14 }}>
                    <Text style={{ color: '#94A3B8', fontSize: 13 }}>No staff found for this office.</Text>
                  </View>
                )}
              </View>
            )}
          </View>
        ) : (
          /* No office selected — prompt */
          <TouchableOpacity
            onPress={() => setOfficeModalVisible(true)}
            style={{
              backgroundColor: '#fff', borderRadius: 14, padding: 20,
              borderWidth: 2, borderColor: '#BFDBFE', borderStyle: 'dashed',
              alignItems: 'center', marginBottom: 16,
            }}
          >
            <Building2 size={36} color="#93C5FD" style={{ marginBottom: 10 }} />
            <Text style={{ fontWeight: '800', color: '#1E40AF', fontSize: 16, marginBottom: 4 }}>
              Select an Office
            </Text>
            <Text style={{ color: '#64748B', fontSize: 13, textAlign: 'center' }}>
              Tap to choose which office you're submitting documents to
            </Text>
          </TouchableOpacity>
        )}

        {/* ── ADD DOCUMENT FORM ───────────────────────────────────────────── */}
        {selectedOffice && (
          <View style={{
            backgroundColor: '#fff', borderRadius: 14, marginBottom: 16,
            borderWidth: 0.5, borderColor: '#E2E8F0', overflow: 'hidden',
          }}>
            {/* Collapsible toggle */}
            <TouchableOpacity
              onPress={() => setShowForm(!showForm)}
              style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16 }}
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Plus size={16} color="#0038A8" />
                <Text style={{ fontWeight: '800', color: '#0038A8', fontSize: 14 }}>Add Document</Text>
              </View>
              {showForm ? <ChevronUp size={18} color="#94A3B8" /> : <ChevronDown size={18} color="#94A3B8" />}
            </TouchableOpacity>

            {showForm && (
              <View style={{ paddingHorizontal: 16, paddingBottom: 16 }}>

                {/* Unit / Office / School / District */}
                <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
                  Unit / Office / School / District
                </Text>
                <TextInput
                  value={unitOffice}
                  onChangeText={setUnitOffice}
                  placeholder="e.g. Ormoc City Schools Division"
                  placeholderTextColor="#CBD5E1"
                  style={{
                    backgroundColor: '#F8FAFC', borderRadius: 10, borderWidth: 1.5,
                    borderColor: '#E2E8F0', paddingHorizontal: 14, paddingVertical: 12,
                    fontSize: 14, color: '#1E293B', marginBottom: 14,
                  }}
                />

                {/* Content / Particulars (required) */}
                <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
                  Content / Particulars <Text style={{ color: '#EF4444' }}>*</Text>
                </Text>
                <TextInput
                  value={docName}
                  onChangeText={setDocName}
                  placeholder="e.g. Plantilla of Personnel, Leave Application"
                  placeholderTextColor="#CBD5E1"
                  style={{
                    backgroundColor: '#F8FAFC', borderRadius: 10, borderWidth: 1.5,
                    borderColor: '#E2E8F0', paddingHorizontal: 14, paddingVertical: 12,
                    fontSize: 14, color: '#1E293B', marginBottom: 14,
                  }}
                />

                {/* Document Type + Referred To — side by side */}
                <View style={{ flexDirection: 'row', gap: 10, marginBottom: 14 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
                      Document Type
                    </Text>
                    <TouchableOpacity
                      onPress={() => { setCatSearch(''); setCatModalVisible(true); }}
                      style={{
                        backgroundColor: '#F8FAFC', borderRadius: 10, borderWidth: 1.5,
                        borderColor: category ? '#0038A8' : '#E2E8F0',
                        paddingHorizontal: 14, paddingVertical: 12,
                        flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                      }}
                    >
                      <Text style={{ color: category ? '#1E293B' : '#CBD5E1', fontSize: 14, flex: 1 }}>
                        {category || '— Select type —'}
                      </Text>
                      <ChevronDown size={14} color={category ? '#0038A8' : '#94A3B8'} />
                    </TouchableOpacity>
                  </View>

                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
                      Referred To <Text style={{ color: '#EF4444' }}>*</Text>
                    </Text>
                    <TextInput
                      value={referredTo}
                      onChangeText={setReferredTo}
                      placeholder="e.g. SDS, Budget Officer"
                      placeholderTextColor="#CBD5E1"
                      style={{
                        backgroundColor: '#F8FAFC', borderRadius: 10, borderWidth: 1.5,
                        borderColor: '#E2E8F0', paddingHorizontal: 14, paddingVertical: 12,
                        fontSize: 14, color: '#1E293B',
                      }}
                    />
                  </View>
                </View>

                {/* Description / Remarks */}
                <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
                  Description / Remarks
                </Text>
                <TextInput
                  value={description}
                  onChangeText={setDescription}
                  placeholder="Any additional details..."
                  placeholderTextColor="#CBD5E1"
                  multiline
                  style={{
                    backgroundColor: '#F8FAFC', borderRadius: 10, borderWidth: 1.5,
                    borderColor: '#E2E8F0', paddingHorizontal: 14, paddingVertical: 12,
                    fontSize: 14, color: '#1E293B', height: 80, textAlignVertical: 'top',
                    marginBottom: 14,
                  }}
                />

                {/* Notes */}
                <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
                  Notes
                </Text>
                <TextInput
                  value={notes}
                  onChangeText={setNotes}
                  placeholder="Optional notes..."
                  placeholderTextColor="#CBD5E1"
                  multiline
                  style={{
                    backgroundColor: '#F8FAFC', borderRadius: 10, borderWidth: 1.5,
                    borderColor: '#E2E8F0', paddingHorizontal: 14, paddingVertical: 12,
                    fontSize: 14, color: '#1E293B', height: 80, textAlignVertical: 'top',
                    marginBottom: 16,
                  }}
                />

                {/* Add to list button */}
                <TouchableOpacity
                  onPress={handleAddToCart}
                  style={{
                    backgroundColor: '#0038A8', borderRadius: 11,
                    paddingVertical: 13, flexDirection: 'row',
                    alignItems: 'center', justifyContent: 'center', gap: 8,
                  }}
                >
                  <Plus size={16} color="#fff" />
                  <Text style={{ color: '#fff', fontWeight: '800', fontSize: 14 }}>➕ Add to Submission List</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}

        {/* ── CART / REVIEW LIST ──────────────────────────────────────────── */}
        {cart.length > 0 && (
          <View style={{ marginBottom: 16 }}>
            <Text style={{
              fontSize: 11, fontWeight: '700', color: '#64748B',
              textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 10,
            }}>
              Submission List ({cart.length})
            </Text>

            {cart.map((item, idx) => (
              <View key={item.tmp_id} style={{
                backgroundColor: '#fff', borderRadius: 12, padding: 16,
                marginBottom: 8, borderWidth: 0.5, borderColor: '#E2E8F0',
              }}>
                <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}>
                  {/* Index bubble */}
                  <View style={{
                    width: 28, height: 28, borderRadius: 14, marginTop: 2,
                    backgroundColor: '#EFF6FF', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Text style={{ color: '#0038A8', fontWeight: '800', fontSize: 12 }}>{idx + 1}</Text>
                  </View>

                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: '700', color: '#1E293B', fontSize: 14, marginBottom: 4 }} numberOfLines={2}>
                      {item.doc_name}
                    </Text>
                    {item.category ? (
                      <View style={{
                        alignSelf: 'flex-start', backgroundColor: '#EFF6FF', borderRadius: 20,
                        paddingHorizontal: 8, paddingVertical: 2, marginBottom: 6,
                      }}>
                        <Text style={{ color: '#1E40AF', fontSize: 11, fontWeight: '600' }}>{item.category}</Text>
                      </View>
                    ) : null}
                    <View style={{ gap: 3 }}>
                      {item.unit_office ? (
                        <Text style={{ color: '#64748B', fontSize: 12 }}>
                          From: <Text style={{ color: '#1E293B' }}>{item.unit_office}</Text>
                        </Text>
                      ) : null}
                      <Text style={{ color: '#64748B', fontSize: 12 }}>
                        Referred To: <Text style={{ color: '#1E293B', fontWeight: '600' }}>{item.referred_to}</Text>
                      </Text>
                      {item.description ? (
                        <Text style={{ color: '#94A3B8', fontSize: 11 }} numberOfLines={2}>
                          {item.description}
                        </Text>
                      ) : null}
                    </View>
                  </View>

                  {/* Remove button */}
                  <TouchableOpacity
                    onPress={() => handleRemove(item.tmp_id)}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                    style={{ padding: 4 }}
                  >
                    <X size={18} color="#EF4444" />
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        )}

        {/* Empty state hint */}
        {!selectedOffice && (
          <View style={{
            backgroundColor: '#EFF6FF', borderRadius: 12, padding: 14,
            borderWidth: 1, borderColor: '#BFDBFE',
          }}>
            <Text style={{ color: '#1E40AF', fontSize: 13, lineHeight: 20 }}>
              📌 Select an office above, then add your documents one by one. When ready, tap <Text style={{ fontWeight: '700' }}>Submit All</Text> to send everything at once.
            </Text>
          </View>
        )}
      </ScrollView>

      {/* ── FLOATING SUBMIT ALL BUTTON ──────────────────────────────────────── */}
      {cart.length > 0 && (
        <View style={{
          position: 'absolute', bottom: 76, left: 16, right: 16,
          shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
          shadowOpacity: 0.18, shadowRadius: 12, elevation: 10,
        }}>
          <TouchableOpacity
            onPress={handleSubmitAll}
            disabled={submitMutation.isPending}
            style={{
              backgroundColor: submitMutation.isPending ? '#93C5FD' : '#0038A8',
              borderRadius: 14, paddingVertical: 16,
              flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10,
            }}
          >
            {submitMutation.isPending ? (
              <>
                <ActivityIndicator color="#fff" size="small" />
                <Text style={{ color: '#fff', fontWeight: '800', fontSize: 15 }}>Submitting…</Text>
              </>
            ) : isOnline ? (
              <>
                <Send size={18} color="#fff" />
                <Text style={{ color: '#fff', fontWeight: '800', fontSize: 15 }}>
                  🚀 Submit All {cart.length} Document{cart.length !== 1 ? 's' : ''}
                </Text>
              </>
            ) : (
              <>
                <WifiOff size={18} color="#fff" />
                <Text style={{ color: '#fff', fontWeight: '800', fontSize: 15 }}>
                  📵 Save for Later ({cart.length})
                </Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      )}

      {/* ══════════════════════════════════════════════════════════════════════
          OFFICE SELECTION MODAL
      ══════════════════════════════════════════════════════════════════════ */}
      <Modal visible={officeModalVisible} animationType="slide" presentationStyle="pageSheet">
        <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
          {/* Modal header */}
          <View style={{
            backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 16,
            paddingHorizontal: 20, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <View>
              <Text style={{ color: '#fff', fontSize: 18, fontWeight: '800' }}>📍 Select an Office</Text>
              <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 13, marginTop: 2 }}>
                Choose where you're submitting documents to
              </Text>
            </View>
            <TouchableOpacity onPress={() => { setOfficeModalVisible(false); setOfficeSearch(''); }}>
              <X size={22} color="#fff" />
            </TouchableOpacity>
          </View>

          {/* Search */}
          <View style={{ paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#fff', borderBottomWidth: 0.5, borderBottomColor: '#E2E8F0' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#F1F5F9', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 }}>
              <Search size={16} color="#94A3B8" />
              <TextInput
                value={officeSearch}
                onChangeText={setOfficeSearch}
                placeholder="Search offices…"
                placeholderTextColor="#94A3B8"
                style={{ flex: 1, fontSize: 14, color: '#1E293B' }}
                autoFocus
              />
              {officeSearch ? (
                <TouchableOpacity onPress={() => setOfficeSearch('')}>
                  <X size={14} color="#94A3B8" />
                </TouchableOpacity>
              ) : null}
            </View>
          </View>

          {officesLoading ? (
            <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
              <ActivityIndicator size="large" color="#0038A8" />
            </View>
          ) : filteredOffices.length === 0 ? (
            <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 }}>
              <Building2 size={48} color="#E2E8F0" />
              <Text style={{ color: '#64748B', fontSize: 15, fontWeight: '700', marginTop: 14 }}>
                {officeSearch ? 'No offices match your search' : 'No offices found'}
              </Text>
            </View>
          ) : (
            <FlatList
              data={filteredOffices}
              keyExtractor={(o) => o.office_slug || o.office_name}
              contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
              renderItem={({ item }) => (
                <TouchableOpacity
                  onPress={() => handleSelectOffice(item)}
                  style={{
                    backgroundColor: selectedOffice?.office_slug === item.office_slug ? '#EFF6FF' : '#fff',
                    borderRadius: 12, padding: 16, marginBottom: 10,
                    borderWidth: selectedOffice?.office_slug === item.office_slug ? 2 : 0.5,
                    borderColor: selectedOffice?.office_slug === item.office_slug ? '#0038A8' : '#E2E8F0',
                    flexDirection: 'row', alignItems: 'center', gap: 14,
                  }}
                >
                  <View style={{
                    width: 44, height: 44, borderRadius: 22,
                    backgroundColor: selectedOffice?.office_slug === item.office_slug ? '#0038A8' : '#F1F5F9',
                    alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Building2 size={20} color={selectedOffice?.office_slug === item.office_slug ? '#fff' : '#64748B'} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{
                      fontWeight: '800', fontSize: 15,
                      color: selectedOffice?.office_slug === item.office_slug ? '#0038A8' : '#1E293B',
                    }}>
                      {item.office_name}
                    </Text>
                    {item.primary_recipient_name || item.primary_recipient ? (
                      <Text style={{ color: '#64748B', fontSize: 12, marginTop: 2 }}>
                        📥 {item.primary_recipient_name || item.primary_recipient}
                      </Text>
                    ) : (
                      <Text style={{ color: '#94A3B8', fontSize: 12, marginTop: 2 }}>
                        Auto-assign staff
                      </Text>
                    )}
                  </View>
                  {selectedOffice?.office_slug === item.office_slug && (
                    <CheckCircle size={20} color="#0038A8" />
                  )}
                </TouchableOpacity>
              )}
            />
          )}
        </View>
      </Modal>

      {/* ══════════════════════════════════════════════════════════════════════
          DOCUMENT TYPE PICKER MODAL
      ══════════════════════════════════════════════════════════════════════ */}
      <Modal visible={catModalVisible} animationType="slide" presentationStyle="pageSheet">
        <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
          {/* Header */}
          <View style={{
            backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 16,
            paddingHorizontal: 20, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <View>
              <Text style={{ color: '#fff', fontSize: 18, fontWeight: '800' }}>📄 Document Type</Text>
              <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 13, marginTop: 2 }}>
                Select the type that best describes your document
              </Text>
            </View>
            <TouchableOpacity onPress={() => { setCatModalVisible(false); setCatSearch(''); }}>
              <X size={22} color="#fff" />
            </TouchableOpacity>
          </View>

          {/* Search */}
          <View style={{ paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#fff', borderBottomWidth: 0.5, borderBottomColor: '#E2E8F0' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#F1F5F9', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 }}>
              <Search size={16} color="#94A3B8" />
              <TextInput
                value={catSearch}
                onChangeText={setCatSearch}
                placeholder="Search types…"
                placeholderTextColor="#94A3B8"
                style={{ flex: 1, fontSize: 14, color: '#1E293B' }}
                autoFocus
              />
              {catSearch ? (
                <TouchableOpacity onPress={() => setCatSearch('')}>
                  <X size={14} color="#94A3B8" />
                </TouchableOpacity>
              ) : null}
            </View>
          </View>

          {/* Options list */}
          <FlatList
            data={categoryOptions.filter((c) =>
              c.toLowerCase().includes(catSearch.toLowerCase())
            )}
            keyExtractor={(c) => c}
            contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
            ListEmptyComponent={
              <View style={{ alignItems: 'center', paddingTop: 40 }}>
                <Text style={{ color: '#94A3B8', fontSize: 14 }}>No matching types found</Text>
              </View>
            }
            renderItem={({ item }) => {
              const isSelected = category === item;
              return (
                <TouchableOpacity
                  onPress={() => { setCategory(item); setCatModalVisible(false); setCatSearch(''); }}
                  style={{
                    backgroundColor: isSelected ? '#EFF6FF' : '#fff',
                    borderRadius: 12, padding: 16, marginBottom: 8,
                    borderWidth: isSelected ? 2 : 0.5,
                    borderColor: isSelected ? '#0038A8' : '#E2E8F0',
                    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                  }}
                >
                  <Text style={{
                    fontSize: 15, fontWeight: isSelected ? '800' : '500',
                    color: isSelected ? '#0038A8' : '#1E293B',
                  }}>
                    {item}
                  </Text>
                  {isSelected && <CheckCircle size={20} color="#0038A8" />}
                </TouchableOpacity>
              );
            }}
          />

          {/* Clear selection footer */}
          {category ? (
            <View style={{ paddingHorizontal: 16, paddingBottom: 32, paddingTop: 8 }}>
              <TouchableOpacity
                onPress={() => { setCategory(''); setCatModalVisible(false); setCatSearch(''); }}
                style={{
                  backgroundColor: '#FEE2E2', borderRadius: 12, paddingVertical: 13,
                  alignItems: 'center',
                }}
              >
                <Text style={{ color: '#DC2626', fontWeight: '700', fontSize: 14 }}>Clear Selection</Text>
              </TouchableOpacity>
            </View>
          ) : null}
        </View>
      </Modal>
    </KeyboardAvoidingView>
  );
}
