import { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  Vibration,
  StyleSheet,
  Modal,
  ScrollView,
  TextInput,
} from 'react-native';
import { CameraView, Camera } from 'expo-camera';
import { useRouter } from 'expo-router';
import api from '../../lib/api';
import { useAuthStore } from '../../lib/store';
import { useQueryClient } from '@tanstack/react-query';

type ScanState = 'scanning' | 'loading' | 'error';

interface ScannedDoc {
  id: string;
  title: string;
  doc_name?: string;
  doc_id?: string;
  tracking_number?: string;
  status?: string;
  transfer_status?: string;
  pending_at_staff?: string;
  pending_at_office?: string;
  source?: string;
  office?: string;
  from_office?: string;
  category?: string;
  sender_name?: string;
  referred_to?: string;
  remarks?: string;
  logged_by?: string;
  submitted_by_name?: string;
}

export default function Scanner() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);

  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [scanState, setScanState] = useState<ScanState>('scanning');
  const [torchOn, setTorchOn] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Quick-receive overlay state
  const [scannedDoc, setScannedDoc] = useState<ScannedDoc | null>(null);
  const [accepting, setAccepting] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [rejectModal, setRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [acceptedDocTitle, setAcceptedDocTitle] = useState<string | null>(null);

  const lastScanned = useRef<string>('');
  const cooldown = useRef<boolean>(false);

  useEffect(() => {
    Camera.requestCameraPermissionsAsync().then(({ status }) => {
      setHasPermission(status === 'granted');
    });
  }, []);

  // ── Can this user act on an incoming transfer? ────────────────────────────

  const canReceive = (doc: ScannedDoc): boolean => {
    if (doc.transfer_status !== 'pending') return false;
    return (
      user?.role === 'admin'
      || doc.pending_at_staff === user?.username
      || (
        !doc.pending_at_staff
        && !!doc.pending_at_office
        && doc.pending_at_office.trim().toLowerCase() ===
           (user?.office || '').trim().toLowerCase()
      )
    );
  };

  // ── Core lookup — returns full doc object ─────────────────────────────────

  const lookupQRData = async (data: string): Promise<ScannedDoc> => {
    let docId = data;
    if (data.includes('/')) {
      const parts = data.split('/');
      docId = parts[parts.length - 1];
    }

    // Try direct doc ID lookup first
    try {
      const res = await api.get(`/documents/${docId}`);
      if (res.data?.id) {
        return {
          ...res.data,
          title: res.data.doc_name || res.data.title,
          tracking_number: res.data.doc_id || res.data.tracking_number,
          from_office: res.data.from_office,
          category: res.data.category,
          sender_name: res.data.sender_name,
          referred_to: res.data.referred_to,
        } as ScannedDoc;
      }
    } catch {
      // Not a direct doc ID — fall through to token scan
    }

    // Try QR token lookup
    const tokenRes = await api.post('/qr/scan', { token: data });
    if (tokenRes.data?.doc?.id) {
      const d = tokenRes.data.doc;
      return {
        ...d,
        title: d.doc_name || d.title,
        tracking_number: d.doc_id || d.tracking_number,
        from_office: d.from_office,
        category: d.category,
        sender_name: d.sender_name,
        referred_to: d.referred_to,
      } as ScannedDoc;
    }

    throw new Error('Document not found');
  };

  // ── Reset scanner to ready state ──────────────────────────────────────────

  const resetScanner = (delay = 0) => {
    setTimeout(() => {
      cooldown.current = false;
      lastScanned.current = '';
      setScanState('scanning');
      setScannedDoc(null);
      setAcceptedDocTitle(null);
    }, delay);
  };

  // ── Camera scan ───────────────────────────────────────────────────────────

  const handleScan = async ({ data }: { data: string }) => {
    if (cooldown.current || data === lastScanned.current) return;
    cooldown.current = true;
    lastScanned.current = data;

    Vibration.vibrate(100);
    setScanState('loading');

    try {
      const doc = await lookupQRData(data);
      setScanState('scanning');

      if (canReceive(doc)) {
        // Show quick-receive overlay instead of navigating
        setScannedDoc(doc);
      } else {
        // Not a pending transfer for this user — go straight to detail
        router.push(`/(app)/documents/${doc.id}`);
        resetScanner(3000);
      }
    } catch (err: any) {
      setScanState('error');
      const msg = err.response?.data?.error || 'Could not find document for this QR code.';
      Alert.alert('Scan Failed', msg, [{
        text: 'Try Again',
        onPress: () => resetScanner(1000),
      }]);
    }
  };

  // ── Upload from gallery ───────────────────────────────────────────────────

  const handleUploadQR = async () => {
    setUploading(true);
    try {
      let ImagePicker: typeof import('expo-image-picker');
      try {
        ImagePicker = await import('expo-image-picker');
      } catch {
        Alert.alert(
          'Rebuild Required',
          'QR upload needs a one-time app rebuild.\n\nRun: npx expo run:android  (or run:ios)',
        );
        return;
      }

      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Required', 'Please allow access to your photo library.');
        return;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        quality: 1,
        allowsEditing: false,
      });

      if (result.canceled || !result.assets?.[0]) return;

      const uri = result.assets[0].uri;
      const scanned = await Camera.scanFromURLAsync(uri, ['qr']);

      if (!scanned || scanned.length === 0) {
        Alert.alert('No QR Found', 'Could not detect a QR code in the selected image. Make sure the QR code is clearly visible.');
        return;
      }

      const data = scanned[0].data;
      Vibration.vibrate(100);

      const doc = await lookupQRData(data);

      if (canReceive(doc)) {
        setScannedDoc(doc);
      } else {
        router.push(`/(app)/documents/${doc.id}`);
      }
    } catch (err: any) {
      const msg = err?.response?.data?.error || err?.message || 'Could not read QR code from image.';
      Alert.alert('Upload Failed', msg);
    } finally {
      setUploading(false);
    }
  };

  // ── Quick accept ──────────────────────────────────────────────────────────

  const handleQuickAccept = async () => {
    if (!scannedDoc) return;
    setAccepting(true);
    console.log('ACCEPT DEBUG:', JSON.stringify({
      id: scannedDoc.id,
      transfer_status: scannedDoc.transfer_status,
      pending_at_staff: scannedDoc.pending_at_staff,
      pending_at_office: scannedDoc.pending_at_office,
      status: scannedDoc.status
    }));
    try {
      await api.post(`/documents/${scannedDoc.id}/accept`);
      Vibration.vibrate([0, 80, 60, 80]);

      // Invalidate relevant caches
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['pending-count'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });

      setAcceptedDocTitle(scannedDoc.title || scannedDoc.tracking_number || 'Document');
      setScannedDoc(null);

      // Show success briefly, then auto-reset for next scan
      resetScanner(2500);
    } catch (err: any) {
      const msg = err?.response?.data?.error || 'Could not accept document. Please try again.';
      Alert.alert('Accept Failed', msg);
    } finally {
      setAccepting(false);
    }
  };

  // ── Quick reject ──────────────────────────────────────────────────────────

  const handleQuickReject = () => {
    if (!scannedDoc) return;
    setRejectReason('');
    setRejectModal(true);
  };

  const confirmQuickReject = async () => {
    if (!rejectReason.trim()) {
      Alert.alert('Required', 'Reason is required.');
      return;
    }
    if (!scannedDoc) return;
    setRejecting(true);
    try {
      await api.post(`/documents/${scannedDoc.id}/reject`, { reason: rejectReason.trim() });
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['pending-count'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      setRejectModal(false);
      setRejectReason('');
      setScannedDoc(null);
      resetScanner(500);
      Alert.alert('Rejected', 'Document rejected.');
    } catch (err: any) {
      const msg = err?.response?.data?.error || 'Could not reject document. Please try again.';
      Alert.alert('Reject Failed', msg);
    } finally {
      setRejecting(false);
    }
  };

  const handleViewDetails = () => {
    if (!scannedDoc) return;
    const id = scannedDoc.id;
    setScannedDoc(null);
    resetScanner(3000);
    router.push(`/(app)/documents/${id}`);
  };

  const handleDismiss = () => {
    setScannedDoc(null);
    resetScanner(500);
  };

  // ── Permission screens ────────────────────────────────────────────────────

  if (hasPermission === false) {
    return (
      <View style={styles.centered}>
        <Text style={{ fontSize: 40, marginBottom: 16 }}>📷</Text>
        <Text style={{ fontSize: 18, fontWeight: 'bold', color: '#111', marginBottom: 8 }}>
          Camera Permission Required
        </Text>
        <Text style={{ color: '#6B7280', textAlign: 'center', paddingHorizontal: 32, marginBottom: 24 }}>
          Please enable camera access in your phone settings to scan QR codes.
        </Text>
        <TouchableOpacity
          onPress={() => Camera.requestCameraPermissionsAsync()}
          style={styles.permissionBtn}
        >
          <Text style={{ color: '#fff', fontWeight: '600' }}>Grant Permission</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={handleUploadQR} style={[styles.permissionBtn, { backgroundColor: '#475569', marginTop: 12 }]}>
          <Text style={{ color: '#fff', fontWeight: '600' }}>📁 Upload QR from Gallery</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (hasPermission === null) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#0038A8" />
        <Text style={{ color: '#6B7280', marginTop: 12 }}>Requesting camera access...</Text>
      </View>
    );
  }

  // ── Main scanner ──────────────────────────────────────────────────────────

  return (
    <View style={{ flex: 1, backgroundColor: '#000', paddingBottom: 100 }}>

      <CameraView
        style={StyleSheet.absoluteFillObject}
        facing="back"
        enableTorch={torchOn}
        onBarcodeScanned={scanState === 'scanning' && !scannedDoc ? handleScan : undefined}
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
      />

      {/* Top overlay */}
      <View style={styles.topOverlay}>
        <Text style={styles.headerText}>Scan Document QR</Text>
        <Text style={styles.subText}>Point camera at a QR code, or upload from gallery</Text>
      </View>

      {/* Scan frame */}
      <View style={styles.frameContainer}>
        <View style={styles.frame}>
          <View style={[styles.corner, styles.topLeft]} />
          <View style={[styles.corner, styles.topRight]} />
          <View style={[styles.corner, styles.bottomLeft]} />
          <View style={[styles.corner, styles.bottomRight]} />

          {(scanState === 'loading' || uploading) && (
            <View style={styles.loadingOverlay}>
              <ActivityIndicator size="large" color="#fff" />
              <Text style={{ color: '#fff', marginTop: 8, fontWeight: '600' }}>
                {uploading ? 'Reading QR from image…' : 'Looking up document…'}
              </Text>
            </View>
          )}

          {scanState === 'error' && !uploading && (
            <View style={styles.loadingOverlay}>
              <Text style={{ fontSize: 32 }}>❌</Text>
              <Text style={{ color: '#fff', marginTop: 8, fontWeight: '600' }}>
                Not found
              </Text>
            </View>
          )}
        </View>
      </View>

      {/* Bottom controls */}
      <View style={styles.bottomOverlay}>
        <TouchableOpacity onPress={() => setTorchOn(!torchOn)} style={styles.controlBtn}>
          <Text style={{ fontSize: 24 }}>{torchOn ? '🔦' : '🔆'}</Text>
          <Text style={styles.controlLabel}>{torchOn ? 'Torch On' : 'Torch Off'}</Text>
        </TouchableOpacity>

        <TouchableOpacity
          onPress={handleUploadQR}
          disabled={uploading}
          style={styles.controlBtn}
        >
          {uploading
            ? <ActivityIndicator color="#fff" size="small" />
            : <Text style={{ fontSize: 24 }}>🖼️</Text>
          }
          <Text style={styles.controlLabel}>Upload QR</Text>
        </TouchableOpacity>

        <TouchableOpacity
          onPress={() => {
            setScanState('scanning');
            cooldown.current = false;
            lastScanned.current = '';
          }}
          style={styles.controlBtn}
        >
          <Text style={{ fontSize: 24 }}>🔄</Text>
          <Text style={styles.controlLabel}>Reset</Text>
        </TouchableOpacity>
      </View>

      {/* ── Quick-receive overlay ─────────────────────────────────────────── */}
      <Modal
        visible={!!scannedDoc}
        transparent
        animationType="slide"
        onRequestClose={handleDismiss}
      >
        <View style={styles.overlayBackdrop}>
          <View style={styles.overlaySheet}>
            {/* Handle */}
            <View style={styles.overlayHandle} />

            {/* Header */}
            <View style={styles.overlayHeader}>
              <Text style={styles.overlayTitle}>📦 Incoming Document</Text>
              <TouchableOpacity onPress={handleDismiss} style={styles.overlayClose}>
                <Text style={{ color: '#6B7280', fontSize: 16 }}>✕</Text>
              </TouchableOpacity>
            </View>

            <ScrollView showsVerticalScrollIndicator={false}>
              {/* Document info */}
              <View style={styles.docCard}>
                <Text style={styles.docTitle} numberOfLines={2}>
                  {scannedDoc?.title || 'Untitled Document'}
                </Text>

                {scannedDoc?.tracking_number && (
                  <View style={styles.docMetaRow}>
                    <Text style={styles.docMetaLabel}>Tracking #</Text>
                    <Text style={styles.docMetaValue}>{scannedDoc.tracking_number}</Text>
                  </View>
                )}

                {scannedDoc?.status && (
                  <View style={styles.docMetaRow}>
                    <Text style={styles.docMetaLabel}>Status</Text>
                    <View style={[styles.statusPill, { backgroundColor: '#FEF3C7' }]}>
                      <Text style={{ color: '#92400E', fontSize: 12, fontWeight: '600' }}>
                        {scannedDoc.status}
                      </Text>
                    </View>
                  </View>
                )}

                {(scannedDoc?.doc_id || scannedDoc?.tracking_number) && (
                  <View style={styles.docMetaRow}>
                    <Text style={styles.docMetaLabel}>Reference</Text>
                    <Text style={styles.docMetaValue}>
                      {scannedDoc.doc_id || scannedDoc.tracking_number}
                    </Text>
                  </View>
                )}

                {scannedDoc?.category && (
                  <View style={styles.docMetaRow}>
                    <Text style={styles.docMetaLabel}>Category</Text>
                    <Text style={styles.docMetaValue}>{scannedDoc.category}</Text>
                  </View>
                )}

                {scannedDoc?.from_office && (
                  <View style={styles.docMetaRow}>
                    <Text style={styles.docMetaLabel}>From Office</Text>
                    <Text style={styles.docMetaValue}>{scannedDoc.from_office}</Text>
                  </View>
                )}

                {scannedDoc?.sender_name && (
                  <View style={styles.docMetaRow}>
                    <Text style={styles.docMetaLabel}>Sender</Text>
                    <Text style={styles.docMetaValue}>{scannedDoc.sender_name}</Text>
                  </View>
                )}

                {scannedDoc?.referred_to && (
                  <View style={styles.docMetaRow}>
                    <Text style={styles.docMetaLabel}>Referred To</Text>
                    <Text style={styles.docMetaValue}>{scannedDoc.referred_to}</Text>
                  </View>
                )}

                {scannedDoc?.office && (
                  <View style={styles.docMetaRow}>
                    <Text style={styles.docMetaLabel}>Office</Text>
                    <Text style={styles.docMetaValue}>{scannedDoc.office}</Text>
                  </View>
                )}

                {(scannedDoc?.logged_by || scannedDoc?.submitted_by_name) && (
                  <View style={styles.docMetaRow}>
                    <Text style={styles.docMetaLabel}>Logged By</Text>
                    <Text style={styles.docMetaValue}>
                      {scannedDoc.logged_by || scannedDoc.submitted_by_name}
                    </Text>
                  </View>
                )}
              </View>

              {/* Prompt */}
              <Text style={styles.receivePrompt}>
                This document is waiting to be received. Confirm receipt to mark it as accepted in the system.
              </Text>

              {/* Action buttons */}
              <TouchableOpacity
                style={[styles.acceptBtn, accepting && { opacity: 0.7 }]}
                onPress={handleQuickAccept}
                disabled={accepting}
              >
                {accepting
                  ? <ActivityIndicator color="#fff" size="small" />
                  : <Text style={styles.acceptBtnText}>✓  Accept & Receive Document</Text>
                }
              </TouchableOpacity>

              {scannedDoc?.transfer_status === 'pending' && (
                <TouchableOpacity
                  style={[styles.rejectBtn, rejecting && { opacity: 0.7 }]}
                  onPress={handleQuickReject}
                  disabled={rejecting}
                >
                  {rejecting
                    ? <ActivityIndicator color="#fff" size="small" />
                    : <Text style={styles.rejectBtnText}>✕  Reject Document</Text>
                  }
                </TouchableOpacity>
              )}

              <TouchableOpacity
                style={styles.detailsBtn}
                onPress={handleViewDetails}
              >
                <Text style={styles.detailsBtnText}>View Full Details</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.cancelBtn}
                onPress={handleDismiss}
              >
                <Text style={styles.cancelBtnText}>Cancel — Scan Again</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* ── Success flash ─────────────────────────────────────────────────── */}
      {acceptedDocTitle && (
        <View style={styles.successFlash}>
          <Text style={styles.successIcon}>✓</Text>
          <Text style={styles.successText}>Received!</Text>
          <Text style={styles.successSubText} numberOfLines={1}>{acceptedDocTitle}</Text>
        </View>
      )}

      {/* ── Reject modal ──────────────────────────────────────────────────── */}
      <Modal visible={rejectModal} transparent animationType="fade" onRequestClose={() => setRejectModal(false)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}>
          <TouchableOpacity style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }} onPress={() => setRejectModal(false)} activeOpacity={1} />
          <View style={{ backgroundColor: '#F8FAFC', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, paddingBottom: 40 }}>
            <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: '#CBD5E1', alignSelf: 'center', marginBottom: 20 }} />
            <Text style={{ fontSize: 17, fontWeight: '800', color: '#1E293B', marginBottom: 6 }}>Reject Document</Text>
            <Text style={{ color: '#64748B', fontSize: 13.5, marginBottom: 20 }}>
              Provide a reason — it will be sent back to the original logger.
            </Text>
            <Text style={{ fontSize: 11, fontWeight: '700', color: '#EF4444', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 }}>
              Reason <Text style={{ color: '#EF4444' }}>*</Text>
            </Text>
            <TextInput
              value={rejectReason}
              onChangeText={setRejectReason}
              placeholder="Why is this document being rejected?"
              placeholderTextColor="#CBD5E1"
              multiline
              autoFocus
              style={{
                backgroundColor: '#fff', borderRadius: 12,
                borderWidth: 1.5, borderColor: rejectReason ? '#E2E8F0' : '#FECACA',
                paddingHorizontal: 14, paddingVertical: 12,
                fontSize: 14, color: '#1E293B', height: 100, textAlignVertical: 'top', marginBottom: 20,
              }}
            />
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity
                onPress={() => { setRejectModal(false); setRejectReason(''); }}
                style={{ flex: 1, borderWidth: 1.5, borderColor: '#E2E8F0', borderRadius: 12, paddingVertical: 13, alignItems: 'center', backgroundColor: '#fff' }}
              >
                <Text style={{ color: '#64748B', fontWeight: '600', fontSize: 14 }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={confirmQuickReject}
                disabled={rejecting || !rejectReason.trim()}
                style={{ flex: 1, backgroundColor: rejectReason.trim() ? '#EF4444' : '#FCA5A5', borderRadius: 12, paddingVertical: 13, alignItems: 'center' }}
              >
                {rejecting
                  ? <ActivityIndicator color="#fff" size="small" />
                  : <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>Confirm Reject</Text>
                }
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

    </View>
  );
}

const styles = StyleSheet.create({
  centered: {
    flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff',
  },
  permissionBtn: {
    backgroundColor: '#0038A8', paddingHorizontal: 24, paddingVertical: 12, borderRadius: 10,
  },
  topOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0,
    paddingTop: 60, paddingBottom: 20,
    backgroundColor: 'rgba(0,0,0,0.6)', alignItems: 'center',
  },
  headerText: { color: '#fff', fontSize: 20, fontWeight: 'bold' },
  subText: { color: 'rgba(255,255,255,0.7)', fontSize: 13, marginTop: 4, textAlign: 'center', paddingHorizontal: 20 },
  frameContainer: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  frame: { width: 260, height: 260, position: 'relative', alignItems: 'center', justifyContent: 'center' },
  corner: { position: 'absolute', width: 40, height: 40, borderColor: '#fff', borderWidth: 4 },
  topLeft:     { top: 0,    left: 0,  borderRightWidth: 0, borderBottomWidth: 0, borderTopLeftRadius: 8 },
  topRight:    { top: 0,    right: 0, borderLeftWidth: 0,  borderBottomWidth: 0, borderTopRightRadius: 8 },
  bottomLeft:  { bottom: 0, left: 0,  borderRightWidth: 0, borderTopWidth: 0,    borderBottomLeftRadius: 8 },
  bottomRight: { bottom: 0, right: 0, borderLeftWidth: 0,  borderTopWidth: 0,    borderBottomRightRadius: 8 },
  loadingOverlay: {
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: 12, padding: 20,
  },
  bottomOverlay: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    paddingBottom: 112, paddingTop: 20,
    backgroundColor: 'rgba(0,0,0,0.6)',
    flexDirection: 'row', justifyContent: 'center', gap: 40,
  },
  controlBtn: { alignItems: 'center' },
  controlLabel: { color: 'rgba(255,255,255,0.8)', fontSize: 12, marginTop: 4 },

  // Quick-receive overlay
  overlayBackdrop: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(0,0,0,0.55)',
  },
  overlaySheet: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingHorizontal: 20,
    paddingBottom: 40,
    maxHeight: '80%',
  },
  overlayHandle: {
    width: 40, height: 4,
    backgroundColor: '#D1D5DB',
    borderRadius: 2,
    alignSelf: 'center',
    marginTop: 12, marginBottom: 4,
  },
  overlayHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
    marginBottom: 16,
  },
  overlayTitle: {
    fontSize: 17, fontWeight: '700', color: '#1E293B',
  },
  overlayClose: {
    width: 32, height: 32,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#F1F5F9', borderRadius: 16,
  },

  // Document card inside overlay
  docCard: {
    backgroundColor: '#F8FAFC',
    borderRadius: 14,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  docTitle: {
    fontSize: 15, fontWeight: '700', color: '#0F172A', marginBottom: 12,
  },
  docMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  docMetaLabel: {
    fontSize: 12, color: '#64748B', fontWeight: '500',
  },
  docMetaValue: {
    fontSize: 13, color: '#1E293B', fontWeight: '600', flexShrink: 1, textAlign: 'right', marginLeft: 8,
  },
  statusPill: {
    paddingHorizontal: 10, paddingVertical: 3,
    borderRadius: 20,
  },

  receivePrompt: {
    fontSize: 13, color: '#64748B', textAlign: 'center',
    marginBottom: 20, lineHeight: 19, paddingHorizontal: 4,
  },

  acceptBtn: {
    backgroundColor: '#16A34A',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    marginBottom: 10,
  },
  acceptBtnText: {
    color: '#fff', fontSize: 16, fontWeight: '700',
  },
  rejectBtn: {
    backgroundColor: '#DC2626',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    marginBottom: 10,
  },
  rejectBtnText: {
    color: '#fff', fontSize: 16, fontWeight: '700',
  },
  detailsBtn: {
    backgroundColor: '#0038A8',
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
    marginBottom: 10,
  },
  detailsBtnText: {
    color: '#fff', fontSize: 15, fontWeight: '600',
  },
  cancelBtn: {
    backgroundColor: '#F1F5F9',
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
  },
  cancelBtnText: {
    color: '#475569', fontSize: 15, fontWeight: '500',
  },

  // Success flash
  successFlash: {
    position: 'absolute',
    top: '35%',
    alignSelf: 'center',
    backgroundColor: 'rgba(22, 163, 74, 0.92)',
    borderRadius: 20,
    paddingVertical: 20,
    paddingHorizontal: 36,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 10,
  },
  successIcon: {
    fontSize: 40, color: '#fff',
  },
  successText: {
    fontSize: 22, fontWeight: '800', color: '#fff', marginTop: 4,
  },
  successSubText: {
    fontSize: 13, color: 'rgba(255,255,255,0.85)', marginTop: 6, maxWidth: 220, textAlign: 'center',
  },
});
