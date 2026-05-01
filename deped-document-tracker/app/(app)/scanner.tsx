import { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  Vibration,
  StyleSheet,
} from 'react-native';
import { CameraView, Camera } from 'expo-camera';
import { useRouter } from 'expo-router';
import api from '../../lib/api';

type ScanState = 'scanning' | 'loading' | 'error';

export default function Scanner() {
  const router = useRouter();
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [scanState, setScanState] = useState<ScanState>('scanning');
  const [torchOn, setTorchOn] = useState(false);
  const [uploading, setUploading] = useState(false);
  const lastScanned = useRef<string>('');
  const cooldown = useRef<boolean>(false);

  useEffect(() => {
    Camera.requestCameraPermissionsAsync().then(({ status }) => {
      setHasPermission(status === 'granted');
    });
  }, []);

  // ── Core lookup ──────────────────────────────────────────────────────────

  const lookupQRData = async (data: string) => {
    let docId = data;
    if (data.includes('/')) {
      const parts = data.split('/');
      docId = parts[parts.length - 1];
    }

    // Try direct doc ID lookup first
    try {
      const res = await api.get(`/documents/${docId}`);
      if (res.data?.id) {
        return res.data.id as string;
      }
    } catch {
      // Not a direct doc ID — fall through to token scan
    }

    // Try QR token lookup
    const tokenRes = await api.post('/qr/scan', { token: data });
    if (tokenRes.data?.doc?.id) {
      return tokenRes.data.doc.id as string;
    }

    throw new Error('Document not found');
  };

  // ── Camera scan ──────────────────────────────────────────────────────────

  const handleScan = async ({ data }: { data: string }) => {
    if (cooldown.current || data === lastScanned.current) return;
    cooldown.current = true;
    lastScanned.current = data;

    Vibration.vibrate(100);
    setScanState('loading');

    try {
      const id = await lookupQRData(data);
      setScanState('scanning');
      router.push(`/(app)/documents/${id}`);
      setTimeout(() => {
        cooldown.current = false;
        lastScanned.current = '';
      }, 3000);
    } catch (err: any) {
      setScanState('error');
      const msg = err.response?.data?.error || 'Could not find document for this QR code.';
      Alert.alert('Scan Failed', msg, [{
        text: 'Try Again',
        onPress: () => {
          setScanState('scanning');
          setTimeout(() => {
            cooldown.current = false;
            lastScanned.current = '';
          }, 1000);
        },
      }]);
    }
  };

  // ── Upload from gallery ──────────────────────────────────────────────────
  // Dynamic import keeps the native module load deferred — the scanner
  // screen stays functional even before the app is rebuilt with the new module.

  const handleUploadQR = async () => {
    setUploading(true);
    try {
      // Lazy-load expo-image-picker so a missing native module doesn't crash
      // the whole scanner screen on first launch before a rebuild.
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

      // Decode QR from the image using Camera.scanFromURLAsync
      const scanned = await Camera.scanFromURLAsync(uri, ['qr']);

      if (!scanned || scanned.length === 0) {
        Alert.alert('No QR Found', 'Could not detect a QR code in the selected image. Make sure the QR code is clearly visible.');
        return;
      }

      const data = scanned[0].data;
      Vibration.vibrate(100);

      const id = await lookupQRData(data);
      router.push(`/(app)/documents/${id}`);

    } catch (err: any) {
      const msg = err?.response?.data?.error || err?.message || 'Could not read QR code from image.';
      Alert.alert('Upload Failed', msg);
    } finally {
      setUploading(false);
    }
  };

  // ── Permission screens ───────────────────────────────────────────────────

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

  // ── Main scanner ─────────────────────────────────────────────────────────

  return (
    <View style={{ flex: 1, backgroundColor: '#000', paddingBottom: 100 }}>

      <CameraView
        style={StyleSheet.absoluteFillObject}
        facing="back"
        enableTorch={torchOn}
        onBarcodeScanned={scanState === 'scanning' ? handleScan : undefined}
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
        {/* Torch */}
        <TouchableOpacity onPress={() => setTorchOn(!torchOn)} style={styles.controlBtn}>
          <Text style={{ fontSize: 24 }}>{torchOn ? '🔦' : '🔆'}</Text>
          <Text style={styles.controlLabel}>{torchOn ? 'Torch On' : 'Torch Off'}</Text>
        </TouchableOpacity>

        {/* Upload from gallery */}
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

        {/* Reset */}
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
});
