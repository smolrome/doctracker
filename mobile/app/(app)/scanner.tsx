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
  Image,
} from 'react-native';
import { CameraView, Camera } from 'expo-camera';
import { useRouter } from 'expo-router';
import api from '../../lib/api';
import { CheckCircle } from 'lucide-react-native';
import { useAuthStore } from '../../lib/store';
import { useQuery, useQueryClient } from '@tanstack/react-query';

type ScanState = 'scanning' | 'loading' | 'error';

interface SlipScanResult {
  slip: { slip_no?: string; [key: string]: any };
  docs_updated: any[];
  token_type: 'SLIP_RECEIVE' | 'SLIP_RELEASE';
  next_qr_b64: string | null;
}

interface SlipPreview {
  slip: { slip_no?: string; destination?: string; from_office?: string; [key: string]: any };
  token_type: 'SLIP_RECEIVE' | 'SLIP_RELEASE';
  docs_count: number;
  token: string;
}

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

// A single doc in a client-QR batch. Same server shape as /pending-documents.
interface ClientBatchDoc {
  id: string;
  doc_id?: string;
  doc_name?: string;
  category?: string;
  from_office?: string;
  sender_name?: string;
  status?: string;
  pending_at_staff?: string;
  pending_at_staff_name?: string;
  pending_at_office?: string;
  intended_for_username?: string;
  intended_for_name?: string;
  // Slug of the office the client submitted to — added per-doc by
  // /staff/resolve-client-qr so we can populate the handler picker via
  // GET /offices/{slug}/staff.
  office_slug?: string;
}

interface ClientBatchResult {
  client_username: string;
  client_name: string;
  documents: ClientBatchDoc[];
}

// Handler option from GET /offices/{slug}/staff (same shape submit.tsx uses).
interface StaffMember {
  username: string;
  full_name: string;
  is_primary?: boolean;
}

export default function Scanner() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);

  const { data: offices = [] } = useQuery<any[]>({
    queryKey: ['offices'],
    queryFn: () => api.get('/offices').then((r: any) => r.data ?? []),
    staleTime: 1000 * 60 * 5,
  });

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
  const [forwardDoc, setForwardDoc] = useState<{ id: string; intendedUsername: string; intendedName: string } | null>(null);
  const [forwardLoading, setForwardLoading] = useState(false);
  const [flashHeading, setFlashHeading] = useState('Received!');

  // Release-to-collector state. releaseDoc holds the doc being released; the
  // collector form captures who physically collected it. collectorScanning
  // temporarily hides the form and re-arms the camera to read the collector's
  // CLI- QR (reusing the same CameraView, not a second scanner).
  const [releaseDoc, setReleaseDoc] = useState<ScannedDoc | null>(null);
  const [releasing, setReleasing] = useState(false);
  const [collectorScanning, setCollectorScanning] = useState(false);
  const [collectorResolving, setCollectorResolving] = useState(false);
  const [collectorName, setCollectorName]         = useState('');
  const [collectorUsername, setCollectorUsername] = useState(''); // only set when resolved from a QR
  const [collectorOrigin, setCollectorOrigin]     = useState('');
  const [collectorOffice, setCollectorOffice]     = useState('');
  const [collectorPosition, setCollectorPosition] = useState('');
  const [collectorContact, setCollectorContact]   = useState('');
  const [slipResult, setSlipResult]       = useState<SlipScanResult | null>(null);
  const [slipActioning, setSlipActioning] = useState(false);
  const [slipPreview, setSlipPreview]         = useState<SlipPreview | null>(null);

  // Client-QR batch-receive state
  const [clientResult, setClientResult]     = useState<ClientBatchResult | null>(null);
  const [clientLoading, setClientLoading]   = useState(false);
  // Intake routing state (Receive & Route). Every client-submitted doc MUST be
  // routed to a handler — there is no accept-without-routing here.
  const [routingId, setRoutingId]             = useState<string | null>(null); // per-doc route in flight
  const [routeAllBusy, setRouteAllBusy]       = useState(false);               // Route-all loop in flight
  const [routeSubmitting, setRouteSubmitting] = useState(false);               // picker confirm in flight
  const [routePicker, setRoutePicker]         = useState<{
    mode: 'single' | 'all';
    docIds: string[];
    officeSlug: string;
    officeName: string;
    note?: string; // optional banner, e.g. when an Intended-For handler is unavailable
  } | null>(null);

  const [adminOfficeOverride, setAdminOfficeOverride]       = useState('');
  const [adminRecipientOverride, setAdminRecipientOverride] = useState('');
  const [officePickerOpen, setOfficePickerOpen]             = useState(false);

  // Handler options for the office of the doc(s) being routed. Same queryKey as
  // submit.tsx (['office-staff', slug]) so the prefetched cache is reused.
  const { data: routeStaff = [], isLoading: routeStaffLoading } = useQuery<StaffMember[]>({
    queryKey: ['office-staff', routePicker?.officeSlug],
    queryFn: async () => {
      if (!routePicker?.officeSlug) return [];
      const res = await api.get(`/offices/${routePicker.officeSlug}/staff`);
      return (res.data ?? []) as StaffMember[];
    },
    enabled: !!routePicker?.officeSlug,
    staleTime: 1000 * 60 * 5,
  });

  // When a client-QR batch resolves, warm the ['office-staff', slug] cache for
  // every office in the batch. This lets the per-doc "Receive & Transfer" tap
  // pre-validate the Intended-For handler synchronously (queryClient.getQueryData)
  // and auto-transfer without a picker round-trip. Same key/staleTime the picker
  // uses, so nothing is fetched twice.
  useEffect(() => {
    if (!clientResult?.documents?.length) return;
    const slugs = Array.from(
      new Set(clientResult.documents.map((d) => d.office_slug || '').filter(Boolean))
    );
    for (const slug of slugs) {
      queryClient.prefetchQuery({
        queryKey: ['office-staff', slug],
        queryFn: async () => {
          const res = await api.get(`/offices/${slug}/staff`);
          return (res.data ?? []) as StaffMember[];
        },
        staleTime: 1000 * 60 * 5,
      });
    }
  }, [clientResult, queryClient]);

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

    // Routing slip tokens start with 'SLIP_' (SLIP_REC-… / SLIP_REL-…).
    // Detect before calling /qr/scan — that endpoint calls use_doc_token()
    // which shares the same token table and would consume the slip token,
    // making the subsequent /qr/slip-scan call fail with 401.
    if (docId.startsWith('SLIP_')) {
      const slipErr: any = new Error('Routing slip QR detected');
      slipErr.isSlipToken = true;
      slipErr.token = docId;
      throw slipErr;
    }

    // Client-identity QR tokens start with 'CLI-'. Detect before the doc-id GET
    // and /qr/scan fallback — a CLI- token is not a doc id, so those would just
    // waste two failing network calls before landing on the generic not-found.
    if (docId.startsWith('CLI-')) {
      const cliErr: any = new Error('Client QR detected');
      cliErr.isClientToken = true;
      cliErr.token = docId;
      throw cliErr;
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

  // ── Routing slip scan ───────────────────────────────────────────────────────

  const handleSlipPreview = async (token: string) => {
    setSlipActioning(true);
    try {
      const res = await api.post('/qr/slip-preview', { token });
      const destination = res.data.slip?.destination || '';
      const fromOffice  = res.data.slip?.from_office || '';
      setAdminOfficeOverride(
        res.data.token_type === 'SLIP_RECEIVE' ? destination : fromOffice
      );
      setSlipPreview({ ...res.data, token });
    } catch (err: any) {
      const msg = err?.response?.data?.error || 'Could not read routing slip QR.';
      Alert.alert('Slip Scan Failed', msg, [
        { text: 'Try Again', onPress: () => resetScanner(500) },
      ]);
      resetScanner(0);
    } finally {
      setSlipActioning(false);
    }
  };

  const handleSlipConfirm = async () => {
    if (!slipPreview) return;
    setSlipActioning(true);
    try {
      const payload: any = { token: slipPreview.token };
      if (user?.role === 'admin' && adminOfficeOverride.trim()) {
        payload.override_office = adminOfficeOverride.trim();
      }
      if (user?.role === 'admin' && adminRecipientOverride.trim()) {
        payload.override_recipient = adminRecipientOverride.trim();
      }
      const res = await api.post('/qr/slip-scan', payload);
      const result: SlipScanResult = res.data;
      Vibration.vibrate([0, 80, 60, 80]);
      queryClient.invalidateQueries({ queryKey: ['routing-slips'] });
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['document'] });
      setSlipPreview(null);
      setSlipResult(result);
    } catch (err: any) {
      const msg = err?.response?.data?.error || 'Could not process routing slip QR.';
      Alert.alert('Slip Scan Failed', msg, [
        { text: 'OK', onPress: () => resetScanner(500) },
      ]);
      resetScanner(0);
    } finally {
      setSlipActioning(false);
    }
  };

  // ── Client-QR batch receive ───────────────────────────────────────────────

  const invalidateReceiveCaches = () => {
    queryClient.invalidateQueries({ queryKey: ['documents'] });
    queryClient.invalidateQueries({ queryKey: ['pending-documents'] });
    queryClient.invalidateQueries({ queryKey: ['pending-count'] });
    queryClient.invalidateQueries({ queryKey: ['stats'] });
    // Prefix-match every ['document', <id>] detail entry so a just-mutated
    // doc's detail screen refetches instead of serving the 5-min stale cache.
    queryClient.invalidateQueries({ queryKey: ['document'] });
  };

  const handleClientTokenScan = async (token: string) => {
    setClientLoading(true);
    try {
      const res = await api.post('/staff/resolve-client-qr', { token });
      setClientResult(res.data as ClientBatchResult);
    } catch (err: any) {
      const status = err?.response?.status;
      const msg = status === 404
        ? 'Unknown or invalid code.'
        : (err?.response?.data?.error || 'Could not read this client QR. Please try again.');
      Alert.alert('Client QR', msg, [
        { text: 'OK', onPress: () => resetScanner(0) },
      ]);
    } finally {
      setClientLoading(false);
    }
  };

  // One atomic call receives AND forwards a pending client doc to a handler.
  // Same payload as the existing forward flow (handleForwardTransfer).
  const transferDocTo = (docId: string, toStaff: string) =>
    api.post(`/documents/${docId}/transfer`, { to_staff: toStaff, transfer_type: 'inside_office' });

  // Open the handler picker for a SINGLE doc, populated from that doc's office.
  const openRouteSingle = (doc: ClientBatchDoc, note?: string) => {
    if (routingId || routeAllBusy) return;
    const slug = doc.office_slug || '';
    if (!slug) {
      Alert.alert('Cannot Transfer', 'This document has no office on record to transfer within.');
      return;
    }
    setRoutePicker({
      mode: 'single',
      docIds: [doc.id],
      officeSlug: slug,
      officeName: doc.pending_at_office || doc.from_office || '',
      note,
    });
  };

  // Open the handler picker for ALL docs at once. Only valid when every doc
  // shares one office (guarded in the UI); "route all to one handler" is
  // meaningless across offices.
  const openRouteAll = () => {
    if (!clientResult || !clientResult.documents.length) return;
    if (routingId || routeAllBusy) return;
    const slugs = Array.from(
      new Set(clientResult.documents.map((d) => d.office_slug || '').filter(Boolean))
    );
    if (slugs.length !== 1) return; // mixed/missing offices — button is disabled anyway
    setRoutePicker({
      mode: 'all',
      docIds: clientResult.documents.map((d) => d.id),
      officeSlug: slugs[0],
      officeName: clientResult.documents[0].pending_at_office || '',
    });
  };

  // A handler was chosen in the picker — perform the transfer(s).
  const handleRouteSelect = async (staff: StaffMember) => {
    if (!routePicker || routeSubmitting) return;
    const { mode, docIds, officeName } = routePicker;
    const staffName = staff.full_name || staff.username;
    setRouteSubmitting(true);

    if (mode === 'single') {
      const docId = docIds[0];
      setRoutingId(docId);
      try {
        await transferDocTo(docId, staff.username);
        Vibration.vibrate([0, 60, 40, 60]);
        invalidateReceiveCaches();
        // Routed doc leaves the list — what remains still needs routing.
        setClientResult((prev) =>
          prev ? { ...prev, documents: prev.documents.filter((d) => d.id !== docId) } : prev
        );
        setRoutePicker(null);
      } catch (err: any) {
        Alert.alert('Transfer Failed', err?.response?.data?.error || 'Could not transfer this document.');
      } finally {
        setRoutingId(null);
        setRouteSubmitting(false);
      }
      return;
    }

    // mode === 'all' — loop the transfer over every doc to the one handler.
    setRouteAllBusy(true);
    const clientName = clientResult?.client_name || 'client';
    const total = docIds.length;
    let success = 0;
    let failed = 0;
    for (const id of docIds) {
      try {
        await transferDocTo(id, staff.username);
        success++;
      } catch {
        failed++;
      }
    }
    setRouteAllBusy(false);
    setRouteSubmitting(false);
    setRoutePicker(null);
    invalidateReceiveCaches();
    Vibration.vibrate([0, 80, 60, 80]);
    setClientResult(null);
    setAcceptedDocTitle(
      failed === 0
        ? `Transferred ${success} document${success !== 1 ? 's' : ''} to ${staffName}${officeName ? ' (' + officeName + ')' : ''} for ${clientName}`
        : `Transferred ${success} of ${total} to ${staffName}, ${failed} failed`
    );
    resetScanner(2500);
  };

  // Per-doc "Receive & Transfer" tap. When the doc carries a resolvable
  // Intended-For handler, transfer straight to that person WITHOUT the picker;
  // otherwise fall back to openRouteSingle. This is UI convenience layered on top
  // of the server's own self-transfer / validity guards — never a replacement.
  const handlePerDocReceive = async (doc: ClientBatchDoc) => {
    if (routingId || routeAllBusy) return;

    const intended = doc.intended_for_username || '';
    const slug = doc.office_slug || '';

    // No intended target, self-target (never auto self-transfer — picker excludes
    // self), or no office to validate against → defer to the manual picker.
    if (!intended || intended === user?.username || !slug) {
      openRouteSingle(doc);
      return;
    }

    setRoutingId(doc.id);

    // Pre-validate: the intended handler must still be registered staff in this
    // office. Prefer the cache the batch-sheet effect warmed; fetch on demand only
    // if it's cold (the button already shows a spinner via routingId).
    let staff = queryClient.getQueryData<StaffMember[]>(['office-staff', slug]);
    if (!staff) {
      try {
        staff = await queryClient.fetchQuery<StaffMember[]>({
          queryKey: ['office-staff', slug],
          queryFn: async () => {
            const res = await api.get(`/offices/${slug}/staff`);
            return (res.data ?? []) as StaffMember[];
          },
          staleTime: 1000 * 60 * 5,
        });
      } catch {
        staff = undefined;
      }
    }

    const isValid = !!staff && staff.some((s) => s.username === intended);
    if (!isValid) {
      // Intended handler left / was renamed / office unreadable → manual picker
      // with a note so the operator knows why auto-transfer didn't fire.
      setRoutingId(null);
      const who = doc.intended_for_name || intended;
      openRouteSingle(doc, `${who} is no longer available in this office — choose a handler.`);
      return;
    }

    // Valid intended handler → transfer directly, mirroring handleRouteSelect's
    // single-mode success handling (vibrate, cache invalidation incl. ['document'],
    // drop the doc). Success flash names the handler when the batch empties.
    const staffName = doc.intended_for_name || intended;
    try {
      await transferDocTo(doc.id, intended);
      Vibration.vibrate([0, 60, 40, 60]);
      invalidateReceiveCaches();
      let remaining = 0;
      setClientResult((prev) => {
        if (!prev) return prev;
        const documents = prev.documents.filter((d) => d.id !== doc.id);
        remaining = documents.length;
        return { ...prev, documents };
      });
      if (remaining === 0) {
        // Last doc in the batch — close the sheet and show the terminal flash,
        // as the "Transfer All" completion path does. Mid-batch we keep the sheet
        // open (matching the manual single-route UX) so remaining docs stay in view.
        setClientResult(null);
        setFlashHeading('Transferred!');
        setAcceptedDocTitle(`Transferred to ${staffName}`);
        resetScanner(2500);
      }
    } catch (err: any) {
      Alert.alert('Transfer Failed', err?.response?.data?.error || 'Could not transfer this document.');
    } finally {
      setRoutingId(null);
    }
  };

  const handleClientDismiss = () => {
    setClientResult(null);
    resetScanner(0);
  };

  // ── Reset scanner to ready state ──────────────────────────────────────────

  const resetScanner = (delay = 0) => {
    setTimeout(() => {
      cooldown.current = false;
      lastScanned.current = '';
      setScanState('scanning');
      setScannedDoc(null);
      setAcceptedDocTitle(null);
      setFlashHeading('Received!');
      setReleaseDoc(null);
      setCollectorScanning(false);
      resetCollectorForm();
      setSlipPreview(null);
      setAdminOfficeOverride('');
      setAdminRecipientOverride('');
      setOfficePickerOpen(false);
      setSlipResult(null);
      setClientResult(null);
      setRoutePicker(null);
      setRoutingId(null);
      setRouteAllBusy(false);
      setRouteSubmitting(false);
    }, delay);
  };

  useEffect(() => {
    if (!slipPreview || !offices.length) return;
    if (!slipPreview?.slip) return;
    const targetOfficeName = slipPreview.token_type === 'SLIP_RECEIVE'
      ? slipPreview.slip.destination
      : slipPreview.slip.from_office;
    const match = offices.find((o: any) =>
      o.office_name?.toLowerCase() === targetOfficeName?.toLowerCase()
    );
    if (match && (match as any).primary_recipient) {
      setAdminRecipientOverride((match as any).primary_recipient);
    }
  }, [slipPreview, offices]);

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

      // Show the action overlay for any resolved doc. Accept/Reject appear only
      // when this is a pending transfer for this user (canReceive); Release-to-
      // collector is always offered (the server enforces office authorization).
      setScannedDoc(doc);
    } catch (err: any) {
      if (err?.isSlipToken) {
        setScanState('scanning');
        handleSlipPreview(err.token);
        return;
      }
      if (err?.isClientToken) {
        setScanState('scanning');
        handleClientTokenScan(err.token);
        return;
      }
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

      // Same as the live-scan path — the overlay is the action hub for any doc.
      setScannedDoc(doc);
    } catch (err: any) {
      if (err?.isSlipToken) {
        handleSlipPreview(err.token);
        return;
      }
      if (err?.isClientToken) {
        handleClientTokenScan(err.token);
        return;
      }
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
      const response = await api.post(`/documents/${scannedDoc.id}/accept`);
      const doc = response.data;
      Vibration.vibrate([0, 80, 60, 80]);

      // Invalidate relevant caches
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['pending-documents'] });
      queryClient.invalidateQueries({ queryKey: ['pending-count'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      queryClient.invalidateQueries({ queryKey: ['document'] });

      const intendedUsername = doc?.intended_for_username || '';
      console.log('FORWARD DEBUG:', JSON.stringify({
        intended_for_username: doc?.intended_for_username,
        intended_for_name:     doc?.intended_for_name,
        intendedUsername,
        currentUser:           user?.username,
        shouldShowForward:     !!(intendedUsername && intendedUsername !== user?.username),
      }));

      // Always show the success flash first
      const docTitle = scannedDoc.title || scannedDoc.tracking_number || 'Document';
      setScannedDoc(null);
      setAcceptedDocTitle(docTitle);

      if (intendedUsername && intendedUsername !== user?.username) {
        setTimeout(() => {
          setForwardDoc({
            id: doc.id,
            intendedUsername,
            intendedName: doc?.intended_for_name || intendedUsername,
          });
        }, 800);
      } else {
        // No intended staff — flash and reset as before
        resetScanner(2500);
      }
    } catch (err: any) {
      const msg = err?.response?.data?.error || 'Could not accept document. Please try again.';
      Alert.alert('Accept Failed', msg);
    } finally {
      setAccepting(false);
    }
  };

  // ── Forward transfer ──────────────────────────────────────────────────────

  const handleForwardTransfer = async (toStaff: string, staffName: string) => {
    setForwardLoading(true);
    try {
      await api.post(`/documents/${forwardDoc!.id}/transfer`, {
        to_staff: toStaff,
        transfer_type: 'inside_office',
      });
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['document'] });
      setForwardDoc(null);
      setForwardLoading(false);
      setAcceptedDocTitle('Forwarded to ' + staffName);
      resetScanner(2500);
    } catch (e: any) {
      Alert.alert('Transfer Failed', e?.response?.data?.error || 'Could not transfer.');
      setForwardLoading(false);
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
      queryClient.invalidateQueries({ queryKey: ['document'] });
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

  // ── Release to collector ──────────────────────────────────────────────────

  const resetCollectorForm = () => {
    setCollectorName('');
    setCollectorUsername('');
    setCollectorOrigin('');
    setCollectorOffice('');
    setCollectorPosition('');
    setCollectorContact('');
  };

  // Open the collector-capture form for the currently scanned doc. Closes the
  // quick-action overlay so the two sheets never stack.
  const openReleaseForm = () => {
    if (!scannedDoc) return;
    const doc = scannedDoc;
    setScannedDoc(null);
    resetCollectorForm();
    setReleaseDoc(doc);
  };

  const closeReleaseForm = () => {
    setReleaseDoc(null);
    setCollectorScanning(false);
    resetCollectorForm();
    resetScanner(0);
  };

  // Re-arm the camera to read the collector's CLI- QR. The form modal hides
  // (visible gate below), the camera routes to handleCollectorScan.
  const enterCollectorScan = () => {
    cooldown.current = false;
    lastScanned.current = '';
    setCollectorScanning(true);
  };

  // Camera handler while collectorScanning — resolves a CLI- token to identity
  // and auto-fills the form, then returns to it. Non-CLI codes and 404s are
  // recoverable (staff can retry or type instead).
  const handleCollectorScan = async ({ data }: { data: string }) => {
    if (cooldown.current || data === lastScanned.current) return;
    cooldown.current = true;
    lastScanned.current = data;

    let token = data;
    if (token.includes('/')) token = token.split('/').pop() || token;
    if (!token.startsWith('CLI-')) {
      Vibration.vibrate(200);
      Alert.alert(
        'Not a Collector QR',
        "That isn't a collector's personal QR code. Scan the collector's own QR, or cancel and type their details.",
        [{ text: 'OK', onPress: () => { cooldown.current = false; lastScanned.current = ''; } }],
      );
      return;
    }

    setCollectorResolving(true);
    Vibration.vibrate(100);
    try {
      const res = await api.post('/staff/resolve-collector-identity', { token });
      const d = res.data || {};
      setCollectorName(d.full_name || '');
      setCollectorUsername(d.username || '');
      // Server returns email and/or phone only when present on the client record.
      setCollectorContact(d.email || d.phone || '');
      Vibration.vibrate([0, 60, 40, 60]);
      setCollectorScanning(false); // back to the form, now pre-filled
    } catch (err: any) {
      const status = err?.response?.status;
      const msg = status === 404
        ? 'Unknown or invalid code.'
        : (err?.response?.data?.error || 'Could not read this QR. Please try again.');
      Alert.alert('Collector QR', msg, [
        { text: 'Type Instead', onPress: () => setCollectorScanning(false) },
        { text: 'Try Again', onPress: () => { cooldown.current = false; lastScanned.current = ''; } },
      ]);
    } finally {
      setCollectorResolving(false);
    }
  };

  // Submit the release. On a 409 soft-warning the server withholds the release
  // and asks for confirmation; "Release Anyway" re-sends the same payload with
  // confirm_override:true.
  const submitRelease = async (confirmOverride = false) => {
    if (!releaseDoc) return;
    if (!collectorName.trim()) {
      Alert.alert('Required', "The collector's name is required.");
      return;
    }
    setReleasing(true);
    try {
      const payload: any = {
        collector_name: collectorName.trim(),
        collector_origin: collectorOrigin.trim(),
        collector_office: collectorOffice.trim(),
        collector_position: collectorPosition.trim(),
        collector_contact: collectorContact.trim(),
        confirm_override: confirmOverride,
      };
      // Only send collector_username when it came from a QR resolve — an
      // unregistered collector leaves it null.
      if (collectorUsername.trim()) payload.collector_username = collectorUsername.trim();

      await api.post(`/documents/${releaseDoc.id}/release-to-client`, payload);

      Vibration.vibrate([0, 80, 60, 80]);
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['pending-documents'] });
      queryClient.invalidateQueries({ queryKey: ['pending-count'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      queryClient.invalidateQueries({ queryKey: ['document'] });

      const name = collectorName.trim();
      setReleaseDoc(null);
      resetCollectorForm();
      setFlashHeading('Released!');
      setAcceptedDocTitle(`Released to ${name}`);
      resetScanner(2500);
    } catch (err: any) {
      const status = err?.response?.status;
      const respData = err?.response?.data || {};
      if (status === 409 && respData.requires_confirm) {
        // Mid-process soft warning — keep the form open, offer to override.
        Alert.alert(
          'Document Still In Process',
          `${respData.warning || 'This document may still be in process.'}\n\nRelease it to the collector anyway?`,
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Release Anyway', style: 'destructive', onPress: () => submitRelease(true) },
          ],
        );
      } else if (status === 403) {
        Alert.alert(
          'Not Authorized',
          "You're not authorized to release documents for this office.",
        );
      } else {
        // Keep the form open so typed input isn't lost.
        Alert.alert('Release Failed', respData.error || 'Could not release this document. Please try again.');
      }
    } finally {
      setReleasing(false);
    }
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

  // Mixed-office guard for "Route all": only offer it when every doc in the
  // batch shares exactly one office slug.
  const batchDocs = clientResult?.documents ?? [];
  const distinctBatchSlugs = Array.from(
    new Set(batchDocs.map((d) => d.office_slug || '').filter(Boolean))
  );
  const canRouteAll = distinctBatchSlugs.length === 1;

  // Handler options with the logged-in user removed — routing to yourself is a
  // no-op (also rejected server-side). Filtered here (not in the queryFn) so the
  // shared ['office-staff', slug] cache stays unfiltered for submit.tsx.
  const routeStaffOptions = routeStaff.filter((s) => s.username !== user?.username);

  // Is the scanned doc a pending transfer this user can Accept/Reject? Release-
  // to-collector is offered regardless (server authorizes by office).
  const scannedReceivable = !!scannedDoc && canReceive(scannedDoc);

  return (
    <View style={{ flex: 1, backgroundColor: '#000', paddingBottom: 100 }}>

      <CameraView
        style={StyleSheet.absoluteFillObject}
        facing="back"
        enableTorch={torchOn}
        onBarcodeScanned={
          collectorScanning
            ? (collectorResolving ? undefined : handleCollectorScan)
            : (scanState === 'scanning' && !scannedDoc && !releaseDoc && !slipPreview && !clientResult && !clientLoading && !routePicker ? handleScan : undefined)
        }
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

          {(scanState === 'loading' || uploading || slipActioning || clientLoading) && (
            <View style={styles.loadingOverlay}>
              <ActivityIndicator size="large" color="#fff" />
              <Text style={{ color: '#fff', marginTop: 8, fontWeight: '600' }}>
                {uploading ? 'Reading QR from image…'
                  : clientLoading ? 'Looking up client…'
                  : slipActioning ? (slipPreview ? 'Processing routing slip…' : 'Checking routing slip…')
                  : 'Looking up document…'}
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
              <Text style={styles.overlayTitle}>
                {scannedReceivable ? '📦 Incoming Document' : '📄 Scanned Document'}
              </Text>
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
                {scannedReceivable
                  ? 'This document is waiting to be received. Confirm receipt to mark it as accepted in the system.'
                  : 'Choose an action for this document.'}
              </Text>

              {/* Action buttons */}
              {scannedReceivable && (
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
              )}

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

              {/* Release to collector — always offered; server authorizes by
                  office and returns 403 if this staff isn't in the group. */}
              <TouchableOpacity
                style={styles.releaseActionBtn}
                onPress={openReleaseForm}
              >
                <Text style={styles.releaseActionBtnText}>🤝  Release to Collector</Text>
              </TouchableOpacity>

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

      {/* ── Release-to-collector form ─────────────────────────────────────── */}
      <Modal
        visible={!!releaseDoc && !collectorScanning}
        transparent
        animationType="slide"
        onRequestClose={closeReleaseForm}
      >
        <View style={styles.overlayBackdrop}>
          <View style={styles.overlaySheet}>
            <View style={styles.overlayHandle} />

            <View style={styles.overlayHeader}>
              <Text style={styles.overlayTitle}>🤝 Release Document</Text>
              <TouchableOpacity onPress={closeReleaseForm} style={styles.overlayClose}>
                <Text style={{ color: '#6B7280', fontSize: 16 }}>✕</Text>
              </TouchableOpacity>
            </View>

            <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
              {/* Doc being released — confirmation context */}
              <View style={styles.docCard}>
                <Text style={styles.docTitle} numberOfLines={2}>
                  {releaseDoc?.title || 'Untitled Document'}
                </Text>
                {(releaseDoc?.doc_id || releaseDoc?.tracking_number) ? (
                  <View style={styles.docMetaRow}>
                    <Text style={styles.docMetaLabel}>Reference</Text>
                    <Text style={styles.docMetaValue}>
                      {releaseDoc?.doc_id || releaseDoc?.tracking_number}
                    </Text>
                  </View>
                ) : null}
              </View>

              <Text style={styles.receivePrompt}>
                Record who is collecting this document. Scan the collector's QR to
                auto-fill, or type their details.
              </Text>

              {/* Scan collector QR — reuses the camera */}
              <TouchableOpacity style={styles.scanCollectorBtn} onPress={enterCollectorScan}>
                <Text style={styles.scanCollectorText}>📷  Scan Collector's QR</Text>
              </TouchableOpacity>
              {collectorUsername ? (
                <Text style={styles.collectorLinkedNote}>
                  ✓ Linked to registered collector @{collectorUsername}
                </Text>
              ) : null}

              {/* Collector fields — all editable, pre-filled if scanned */}
              <Text style={styles.fieldLabel}>Collector's Name <Text style={{ color: '#DC2626' }}>*</Text></Text>
              <TextInput
                value={collectorName}
                onChangeText={setCollectorName}
                placeholder="Full name of the person collecting"
                placeholderTextColor="#CBD5E1"
                style={[styles.fieldInput, !collectorName.trim() && { borderColor: '#FECACA' }]}
              />

              <Text style={styles.fieldLabel}>Origin</Text>
              <TextInput
                value={collectorOrigin}
                onChangeText={setCollectorOrigin}
                placeholder="Where they're from (e.g. school / barangay)"
                placeholderTextColor="#CBD5E1"
                style={styles.fieldInput}
              />

              <Text style={styles.fieldLabel}>Office / Designation</Text>
              <TextInput
                value={collectorOffice}
                onChangeText={setCollectorOffice}
                placeholder="Office or designation"
                placeholderTextColor="#CBD5E1"
                style={styles.fieldInput}
              />

              <Text style={styles.fieldLabel}>Position</Text>
              <TextInput
                value={collectorPosition}
                onChangeText={setCollectorPosition}
                placeholder="Position / role"
                placeholderTextColor="#CBD5E1"
                style={styles.fieldInput}
              />

              <Text style={styles.fieldLabel}>Contact</Text>
              <TextInput
                value={collectorContact}
                onChangeText={setCollectorContact}
                placeholder="Phone or email"
                placeholderTextColor="#CBD5E1"
                autoCapitalize="none"
                style={styles.fieldInput}
              />

              <TouchableOpacity
                style={[styles.releaseBtn, (releasing || !collectorName.trim()) && { opacity: 0.6 }]}
                onPress={() => submitRelease(false)}
                disabled={releasing || !collectorName.trim()}
              >
                {releasing
                  ? <ActivityIndicator color="#fff" size="small" />
                  : <Text style={styles.acceptBtnText}>🤝  Release Document</Text>
                }
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.cancelBtn, releasing && { opacity: 0.5 }]}
                onPress={closeReleaseForm}
                disabled={releasing}
              >
                <Text style={styles.cancelBtnText}>Cancel</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* ── Collector-QR scan banner (camera re-armed under the form) ──────── */}
      {collectorScanning && (
        <View style={styles.collectorScanBanner}>
          {collectorResolving ? (
            <>
              <ActivityIndicator color="#fff" />
              <Text style={styles.collectorScanText}>Looking up collector…</Text>
            </>
          ) : (
            <>
              <Text style={styles.collectorScanText}>Scan the collector's QR code</Text>
              <TouchableOpacity
                onPress={() => { setCollectorScanning(false); cooldown.current = false; lastScanned.current = ''; }}
                style={styles.collectorScanCancel}
              >
                <Text style={{ color: '#fff', fontWeight: '700' }}>Cancel — Type Instead</Text>
              </TouchableOpacity>
            </>
          )}
        </View>
      )}

      {/* ── Client-QR batch receive modal ─────────────────────────────────── */}
      <Modal
        visible={!!clientResult}
        transparent
        animationType="slide"
        onRequestClose={handleClientDismiss}
      >
        <View style={styles.overlayBackdrop}>
          <View style={styles.overlaySheet}>
            <View style={styles.overlayHandle} />

            {/* Header */}
            <View style={styles.overlayHeader}>
              <View style={{ flex: 1, paddingRight: 12 }}>
                <Text style={styles.overlayTitle} numberOfLines={1}>
                  👤 Receiving for {clientResult?.client_name || 'Client'}
                </Text>
                <Text style={{ color: '#64748B', fontSize: 12.5, marginTop: 2 }}>
                  @{clientResult?.client_username}
                  {clientResult && clientResult.documents.length > 0
                    ? ` · ${clientResult.documents.length} document${clientResult.documents.length !== 1 ? 's' : ''} to receive`
                    : ''}
                </Text>
              </View>
              <TouchableOpacity onPress={handleClientDismiss} style={styles.overlayClose}>
                <Text style={{ color: '#6B7280', fontSize: 16 }}>✕</Text>
              </TouchableOpacity>
            </View>

            {clientResult && clientResult.documents.length === 0 ? (
              // Empty state — a REAL case (docs pending with other staff), not an error.
              <View style={{ alignItems: 'center', paddingVertical: 36, paddingHorizontal: 12 }}>
                <View style={{
                  width: 64, height: 64, borderRadius: 32,
                  backgroundColor: '#EFF6FF', alignItems: 'center', justifyContent: 'center',
                  marginBottom: 16,
                }}>
                  <Text style={{ fontSize: 30 }}>📭</Text>
                </View>
                <Text style={{ color: '#1E293B', fontSize: 15.5, fontWeight: '700', marginBottom: 6 }}>
                  Nothing here for you to receive
                </Text>
                <Text style={{ color: '#64748B', fontSize: 13, textAlign: 'center', lineHeight: 19, maxWidth: 280 }}>
                  {clientResult.client_name}'s documents may be pending with other staff.
                </Text>
                <TouchableOpacity
                  style={[styles.cancelBtn, { marginTop: 24, alignSelf: 'stretch' }]}
                  onPress={handleClientDismiss}
                >
                  <Text style={styles.cancelBtnText}>Close — Scan Again</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <>
                {/* Primary action — Route All to one handler (single-office only) */}
                {canRouteAll ? (
                  <TouchableOpacity
                    style={[styles.acceptBtn, (routeAllBusy || !!routingId) && { opacity: 0.7 }]}
                    onPress={openRouteAll}
                    disabled={routeAllBusy || !!routingId}
                  >
                    {routeAllBusy
                      ? <ActivityIndicator color="#fff" size="small" />
                      : <Text style={styles.acceptBtnText}>
                          ➡️  Transfer All to…  ({batchDocs.length})
                        </Text>
                    }
                  </TouchableOpacity>
                ) : (
                  <View style={[styles.acceptBtn, { backgroundColor: '#EEF2F7' }]}>
                    <Text style={[styles.acceptBtnText, { color: '#64748B', fontSize: 13, fontWeight: '600' }]}>
                      Multiple offices — transfer each document below
                    </Text>
                  </View>
                )}

                <ScrollView showsVerticalScrollIndicator={false} style={{ marginTop: 4 }}>
                  {clientResult?.documents.map((doc) => (
                    <View key={doc.id} style={styles.docCard}>
                      <Text style={styles.docTitle} numberOfLines={2}>
                        {doc.doc_name || 'Untitled Document'}
                      </Text>

                      {doc.doc_id ? (
                        <View style={styles.docMetaRow}>
                          <Text style={styles.docMetaLabel}>Reference</Text>
                          <Text style={styles.docMetaValue}>{doc.doc_id}</Text>
                        </View>
                      ) : null}

                      {doc.category ? (
                        <View style={styles.docMetaRow}>
                          <Text style={styles.docMetaLabel}>Category</Text>
                          <Text style={styles.docMetaValue}>{doc.category}</Text>
                        </View>
                      ) : null}

                      {doc.from_office ? (
                        <View style={styles.docMetaRow}>
                          <Text style={styles.docMetaLabel}>From Office</Text>
                          <Text style={styles.docMetaValue}>{doc.from_office}</Text>
                        </View>
                      ) : null}

                      {doc.sender_name ? (
                        <View style={styles.docMetaRow}>
                          <Text style={styles.docMetaLabel}>Sender</Text>
                          <Text style={styles.docMetaValue}>{doc.sender_name}</Text>
                        </View>
                      ) : null}

                      {doc.intended_for_name ? (
                        <View style={styles.docMetaRow}>
                          <Text style={styles.docMetaLabel}>Intended For</Text>
                          <Text style={[styles.docMetaValue, { color: '#0038A8' }]}>
                            {doc.intended_for_name}
                          </Text>
                        </View>
                      ) : null}

                      <TouchableOpacity
                        style={[
                          styles.perDocAcceptBtn,
                          { backgroundColor: '#0038A8' },
                          (routingId === doc.id || routeAllBusy) && { opacity: 0.6 },
                        ]}
                        onPress={() => handlePerDocReceive(doc)}
                        disabled={!!routingId || routeAllBusy}
                      >
                        {routingId === doc.id
                          ? <ActivityIndicator color="#fff" size="small" />
                          : <Text style={styles.perDocAcceptText}>
                              {doc.intended_for_username && doc.intended_for_username !== user?.username
                                ? `➡️  Receive & Transfer → ${doc.intended_for_name || doc.intended_for_username}`
                                : '➡️  Receive & Transfer'}
                            </Text>
                        }
                      </TouchableOpacity>

                      {/* Override: when the tap would auto-transfer to the Intended
                          For, still let the operator pick a different handler. */}
                      {doc.intended_for_username && doc.intended_for_username !== user?.username ? (
                        <TouchableOpacity
                          onPress={() => openRouteSingle(doc)}
                          disabled={!!routingId || routeAllBusy}
                          style={{ paddingVertical: 8, alignItems: 'center' }}
                        >
                          <Text style={{ color: '#0038A8', fontSize: 12.5, fontWeight: '600' }}>
                            Choose someone else
                          </Text>
                        </TouchableOpacity>
                      ) : null}
                    </View>
                  ))}

                  <TouchableOpacity
                    style={[styles.cancelBtn, { marginTop: 4 }]}
                    onPress={handleClientDismiss}
                  >
                    <Text style={styles.cancelBtnText}>Cancel — Scan Again</Text>
                  </TouchableOpacity>
                </ScrollView>
              </>
            )}
          </View>
        </View>
      </Modal>

      {/* ── Handler picker (Receive & Transfer) ───────────────────────────── */}
      <Modal
        visible={!!routePicker}
        transparent
        animationType="slide"
        onRequestClose={() => { if (!routeSubmitting) setRoutePicker(null); }}
      >
        <View style={styles.overlayBackdrop}>
          <View style={styles.overlaySheet}>
            <View style={styles.overlayHandle} />

            <View style={styles.overlayHeader}>
              <View style={{ flex: 1, paddingRight: 12 }}>
                <Text style={styles.overlayTitle} numberOfLines={1}>
                  Transfer to handler
                </Text>
                <Text style={{ color: '#64748B', fontSize: 12.5, marginTop: 2 }}>
                  {routePicker?.mode === 'all'
                    ? `All ${routePicker?.docIds.length} document${routePicker && routePicker.docIds.length !== 1 ? 's' : ''}`
                    : '1 document'}
                  {routePicker?.officeName ? ` · ${routePicker.officeName}` : ''}
                </Text>
                {routePicker?.note ? (
                  <Text style={{ color: '#B45309', fontSize: 12, marginTop: 4 }}>
                    ⚠️ {routePicker.note}
                  </Text>
                ) : null}
              </View>
              <TouchableOpacity
                onPress={() => { if (!routeSubmitting) setRoutePicker(null); }}
                style={styles.overlayClose}
              >
                <Text style={{ color: '#6B7280', fontSize: 16 }}>✕</Text>
              </TouchableOpacity>
            </View>

            {routeStaffLoading ? (
              <View style={{ paddingVertical: 36, alignItems: 'center' }}>
                <ActivityIndicator size="large" color="#0038A8" />
                <Text style={{ color: '#64748B', marginTop: 12, fontSize: 13 }}>Loading staff…</Text>
              </View>
            ) : routeStaffOptions.length === 0 ? (
              <View style={{ paddingVertical: 36, alignItems: 'center', paddingHorizontal: 12 }}>
                <Text style={{ color: '#1E293B', fontSize: 15, fontWeight: '700', marginBottom: 6 }}>
                  No other staff to transfer to
                </Text>
                <Text style={{ color: '#64748B', fontSize: 13, textAlign: 'center', lineHeight: 19 }}>
                  {routeStaff.length > 0
                    ? 'You are the only registered staff in this office — there is no one else to transfer this to.'
                    : 'This office has no registered staff to transfer to.'}
                </Text>
                <TouchableOpacity
                  style={[styles.cancelBtn, { marginTop: 20, alignSelf: 'stretch' }]}
                  onPress={() => setRoutePicker(null)}
                >
                  <Text style={styles.cancelBtnText}>Back</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <ScrollView showsVerticalScrollIndicator={false}>
                {routeStaffOptions.map((s) => (
                  <TouchableOpacity
                    key={s.username}
                    onPress={() => handleRouteSelect(s)}
                    disabled={routeSubmitting}
                    style={[
                      styles.docCard,
                      {
                        flexDirection: 'row',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        opacity: routeSubmitting ? 0.6 : 1,
                      },
                    ]}
                  >
                    <View style={{ flex: 1, paddingRight: 12 }}>
                      <Text style={[styles.docTitle, { marginBottom: 2 }]} numberOfLines={1}>
                        {s.full_name || s.username}
                      </Text>
                      <Text style={{ color: '#64748B', fontSize: 12 }}>@{s.username}</Text>
                    </View>
                    {s.is_primary ? (
                      <View style={{ backgroundColor: '#EFF6FF', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 20 }}>
                        <Text style={{ color: '#0038A8', fontSize: 11, fontWeight: '700' }}>Primary</Text>
                      </View>
                    ) : null}
                  </TouchableOpacity>
                ))}
                <TouchableOpacity
                  style={[styles.cancelBtn, { marginTop: 4 }]}
                  onPress={() => setRoutePicker(null)}
                  disabled={routeSubmitting}
                >
                  <Text style={styles.cancelBtnText}>Cancel</Text>
                </TouchableOpacity>
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>

      {/* ── Forward dialog ────────────────────────────────────────────────── */}
      <Modal visible={!!forwardDoc} transparent animationType="slide" onRequestClose={() => { setForwardDoc(null); resetScanner(0); }}>
        <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' }}>
          <View style={{ backgroundColor: '#fff', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, paddingBottom: 40 }}>
            <View style={{ width: 36, height: 4, borderRadius: 2, backgroundColor: '#CBD5E1', alignSelf: 'center', marginBottom: 20 }} />
            <View style={{ width: 52, height: 52, borderRadius: 26, backgroundColor: '#DCFCE7', alignItems: 'center', justifyContent: 'center', alignSelf: 'center', marginBottom: 14 }}>
              <CheckCircle size={28} color="#16A34A" />
            </View>
            <Text style={{ fontSize: 17, fontWeight: '800', color: '#1E293B', textAlign: 'center', marginBottom: 8 }}>Forward to Intended Recipient?</Text>
            <Text style={{ fontSize: 13.5, color: '#64748B', textAlign: 'center', marginBottom: 24, lineHeight: 20 }}>
              {'This document was intended for '}
              <Text style={{ color: '#1E293B', fontWeight: '700' }}>{forwardDoc?.intendedName}</Text>
              {'. Transfer it to them now?'}
            </Text>
            <View style={{ gap: 10 }}>
              <TouchableOpacity
                onPress={() => handleForwardTransfer(forwardDoc!.intendedUsername, forwardDoc!.intendedName)}
                disabled={forwardLoading}
                style={{ backgroundColor: '#10B981', borderRadius: 12, paddingVertical: 14, alignItems: 'center', opacity: forwardLoading ? 0.7 : 1 }}
              >
                {forwardLoading
                  ? <ActivityIndicator color="#fff" size="small" />
                  : <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>Transfer to {forwardDoc?.intendedName}</Text>
                }
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => {
                  const docId = forwardDoc!.id;
                  setForwardDoc(null);
                  router.push({ pathname: '/(app)/documents/[id]', params: { id: docId } });
                  resetScanner(0);
                }}
                style={{ borderWidth: 1.5, borderColor: '#0038A8', borderRadius: 12, paddingVertical: 14, alignItems: 'center' }}
              >
                <Text style={{ color: '#0038A8', fontWeight: '700', fontSize: 14 }}>Choose Different Staff</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => { setForwardDoc(null); resetScanner(0); }}
                style={{ paddingVertical: 14, alignItems: 'center' }}
              >
                <Text style={{ color: '#94A3B8', fontSize: 14 }}>Skip — Keep in My Queue</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* ── Success flash ─────────────────────────────────────────────────── */}
      {acceptedDocTitle && (
        <View style={styles.successFlash}>
          <Text style={styles.successIcon}>✓</Text>
          <Text style={styles.successText}>{flashHeading}</Text>
          <Text style={styles.successSubText} numberOfLines={1}>{acceptedDocTitle}</Text>
        </View>
      )}

      {/* ── Routing slip confirmation modal ──────────────────────────────── */}
      <Modal
        visible={!!slipPreview}
        transparent
        animationType="slide"
        onRequestClose={() => resetScanner(0)}
      >
        <View style={styles.overlayBackdrop}>
          <View style={styles.overlaySheet}>
            <View style={styles.overlayHandle} />
            <View style={styles.overlayHeader}>
              <Text style={styles.overlayTitle}>
                {slipPreview?.token_type === 'SLIP_RECEIVE' ? '📦 Receive Routing Slip' : '✅ Release Routing Slip'}
              </Text>
              <TouchableOpacity onPress={() => resetScanner(0)} style={styles.overlayClose}>
                <Text style={{ color: '#6B7280', fontSize: 16 }}>✕</Text>
              </TouchableOpacity>
            </View>

            <ScrollView showsVerticalScrollIndicator={false}>
              <View style={styles.docCard}>
                <Text style={styles.docTitle}>Slip #{slipPreview?.slip?.slip_no || '—'}</Text>
                {slipPreview?.slip?.from_office ? (
                  <View style={styles.docMetaRow}>
                    <Text style={styles.docMetaLabel}>From Office</Text>
                    <Text style={styles.docMetaValue}>{slipPreview.slip.from_office}</Text>
                  </View>
                ) : null}
                {slipPreview?.slip?.destination ? (
                  <View style={styles.docMetaRow}>
                    <Text style={styles.docMetaLabel}>Destination</Text>
                    <Text style={styles.docMetaValue}>{slipPreview.slip.destination}</Text>
                  </View>
                ) : null}
                <View style={styles.docMetaRow}>
                  <Text style={styles.docMetaLabel}>Documents</Text>
                  <Text style={styles.docMetaValue}>{slipPreview?.docs_count ?? 0}</Text>
                </View>
                {user?.role === 'admin' && (
                  <View style={{ marginTop: 12 }}>
                    {/* Office picker */}
                    <Text style={[styles.docMetaLabel, { marginBottom: 6 }]}>
                      {slipPreview?.token_type === 'SLIP_RECEIVE' ? 'Receiving Office' : 'Releasing Office'}
                    </Text>
                    <TouchableOpacity
                      onPress={() => setOfficePickerOpen(v => !v)}
                      style={{
                        backgroundColor: '#fff',
                        borderRadius: 10,
                        borderWidth: 1.5,
                        borderColor: officePickerOpen ? '#0038A8' : '#E2E8F0',
                        paddingHorizontal: 12,
                        paddingVertical: 10,
                        flexDirection: 'row',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: 4,
                      }}
                    >
                      <Text style={{ fontSize: 13, color: adminOfficeOverride ? '#1E293B' : '#CBD5E1' }} numberOfLines={1}>
                        {adminOfficeOverride || 'Select office…'}
                      </Text>
                      <Text style={{ color: '#94A3B8', fontSize: 12 }}>{officePickerOpen ? '▲' : '▼'}</Text>
                    </TouchableOpacity>
                    {officePickerOpen && (
                      <ScrollView
                        style={{ maxHeight: 180, borderRadius: 10, borderWidth: 1, borderColor: '#E2E8F0', marginBottom: 8 }}
                        nestedScrollEnabled
                      >
                        {offices.map((o: any, i: number) => (
                          <TouchableOpacity
                            key={o.office_slug || i}
                            onPress={() => {
                              setAdminOfficeOverride(o.office_name);
                              setAdminRecipientOverride(o.primary_recipient || '');
                              setOfficePickerOpen(false);
                            }}
                            style={{
                              paddingHorizontal: 12,
                              paddingVertical: 10,
                              borderBottomWidth: i < offices.length - 1 ? 1 : 0,
                              borderBottomColor: '#F1F5F9',
                              backgroundColor: adminOfficeOverride === o.office_name ? '#EFF6FF' : '#fff',
                            }}
                          >
                            <Text style={{ fontSize: 13, color: '#1E293B', fontWeight: adminOfficeOverride === o.office_name ? '700' : '400' }}>
                              {o.office_name}
                            </Text>
                            {o.primary_recipient ? (
                              <Text style={{ fontSize: 11, color: '#64748B', marginTop: 2 }}>
                                📥 {o.primary_recipient}
                              </Text>
                            ) : null}
                          </TouchableOpacity>
                        ))}
                      </ScrollView>
                    )}
                    {/* Recipient override */}
                    <Text style={[styles.docMetaLabel, { marginBottom: 6, marginTop: 8 }]}>Received By</Text>
                    <TextInput
                      value={adminRecipientOverride}
                      onChangeText={setAdminRecipientOverride}
                      placeholder="Recipient name or username"
                      placeholderTextColor="#CBD5E1"
                      style={{
                        backgroundColor: '#fff',
                        borderRadius: 10,
                        borderWidth: 1.5,
                        borderColor: '#E2E8F0',
                        paddingHorizontal: 12,
                        paddingVertical: 9,
                        fontSize: 13,
                        color: '#1E293B',
                      }}
                    />
                  </View>
                )}
              </View>

              <Text style={styles.receivePrompt}>
                {slipPreview?.token_type === 'SLIP_RECEIVE'
                  ? `Confirm receipt of ${slipPreview?.docs_count ?? 0} document${(slipPreview?.docs_count ?? 0) !== 1 ? 's' : ''}. This will mark them as Received in the system.`
                  : `Confirm release of ${slipPreview?.docs_count ?? 0} document${(slipPreview?.docs_count ?? 0) !== 1 ? 's' : ''}. This will mark them as Released in the system.`
                }
              </Text>

              <TouchableOpacity
                style={[styles.acceptBtn, slipActioning && { opacity: 0.7 }]}
                onPress={handleSlipConfirm}
                disabled={slipActioning}
              >
                {slipActioning
                  ? <ActivityIndicator color="#fff" size="small" />
                  : <Text style={styles.acceptBtnText}>
                      {slipPreview?.token_type === 'SLIP_RECEIVE' ? '✓  Confirm Receive' : '✓  Confirm Release'}
                    </Text>
                }
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.cancelBtn, slipActioning && { opacity: 0.5 }]}
                onPress={() => resetScanner(0)}
                disabled={slipActioning}
              >
                <Text style={styles.cancelBtnText}>Cancel — Scan Again</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* ── Routing slip scan result ──────────────────────────────────────── */}
      <Modal
        visible={!!slipResult}
        transparent
        animationType="slide"
        onRequestClose={() => { setSlipResult(null); resetScanner(500); }}
      >
        <View style={styles.overlayBackdrop}>
          <View style={styles.overlaySheet}>
            <View style={styles.overlayHandle} />
            <View style={styles.overlayHeader}>
              <Text style={styles.overlayTitle}>
                {slipResult?.token_type === 'SLIP_RECEIVE' ? '📦 Routing Slip Received' : '✅ Routing Slip Released'}
              </Text>
              <TouchableOpacity
                onPress={() => { setSlipResult(null); resetScanner(500); }}
                style={styles.overlayClose}
              >
                <Text style={{ color: '#6B7280', fontSize: 16 }}>✕</Text>
              </TouchableOpacity>
            </View>

            <ScrollView showsVerticalScrollIndicator={false}>
              <View style={styles.docCard}>
                <Text style={styles.docTitle}>
                  Slip #{slipResult?.slip?.slip_no || '—'}
                </Text>
                <View style={styles.docMetaRow}>
                  <Text style={styles.docMetaLabel}>Documents Updated</Text>
                  <Text style={styles.docMetaValue}>{slipResult?.docs_updated?.length ?? 0}</Text>
                </View>
                <View style={styles.docMetaRow}>
                  <Text style={styles.docMetaLabel}>Action</Text>
                  <Text style={styles.docMetaValue}>
                    {slipResult?.token_type === 'SLIP_RECEIVE' ? 'Marked Received' : 'Marked Released'}
                  </Text>
                </View>
              </View>

              {/* Release QR — shown after RECEIVE so the office can scan-out later */}
              {slipResult?.token_type === 'SLIP_RECEIVE' && slipResult?.next_qr_b64 && (
                <View style={{ alignItems: 'center', marginBottom: 20 }}>
                  <Text style={{ fontSize: 13, fontWeight: '700', color: '#1E40AF', marginBottom: 10, textAlign: 'center' }}>
                    Save this QR to release documents later
                  </Text>
                  <Image
                    source={{ uri: slipResult.next_qr_b64.startsWith('data:')
                      ? slipResult.next_qr_b64
                      : `data:image/png;base64,${slipResult.next_qr_b64}` }}
                    style={{ width: 200, height: 200, borderRadius: 8 }}
                    resizeMode="contain"
                  />
                  <Text style={{ color: '#64748B', fontSize: 11, marginTop: 8, textAlign: 'center' }}>
                    Screenshot this QR — scan it when the documents leave your office
                  </Text>
                </View>
              )}

              <TouchableOpacity
                style={styles.acceptBtn}
                onPress={() => { setSlipResult(null); resetScanner(500); }}
              >
                <Text style={styles.acceptBtnText}>Done — Scan Next</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </View>
      </Modal>

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
  perDocAcceptBtn: {
    backgroundColor: '#16A34A',
    borderRadius: 10,
    paddingVertical: 11,
    alignItems: 'center',
    marginTop: 6,
  },
  perDocAcceptText: {
    color: '#fff', fontSize: 14, fontWeight: '700',
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

  // Release to collector
  releaseActionBtn: {
    backgroundColor: '#7C3AED',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    marginBottom: 10,
  },
  releaseActionBtnText: {
    color: '#fff', fontSize: 16, fontWeight: '700',
  },
  releaseBtn: {
    backgroundColor: '#7C3AED',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    marginBottom: 10,
    marginTop: 16,
  },
  scanCollectorBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#EFF6FF',
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: '#BFDBFE',
    paddingVertical: 13,
    marginBottom: 6,
  },
  scanCollectorText: {
    color: '#0038A8', fontSize: 14, fontWeight: '700',
  },
  collectorLinkedNote: {
    color: '#16A34A', fontSize: 12, fontWeight: '600',
    textAlign: 'center', marginBottom: 4,
  },
  fieldLabel: {
    fontSize: 11, fontWeight: '700', color: '#64748B',
    textTransform: 'uppercase', letterSpacing: 0.6,
    marginBottom: 6, marginTop: 12,
  },
  fieldInput: {
    backgroundColor: '#fff',
    borderRadius: 10,
    borderWidth: 1.5,
    borderColor: '#E2E8F0',
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    color: '#1E293B',
  },
  collectorScanBanner: {
    position: 'absolute',
    top: 120, left: 20, right: 20,
    backgroundColor: 'rgba(0,0,0,0.78)',
    borderRadius: 16,
    paddingVertical: 18,
    paddingHorizontal: 20,
    alignItems: 'center',
    gap: 12,
  },
  collectorScanText: {
    color: '#fff', fontSize: 15, fontWeight: '700', textAlign: 'center',
  },
  collectorScanCancel: {
    backgroundColor: 'rgba(255,255,255,0.18)',
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 18,
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
