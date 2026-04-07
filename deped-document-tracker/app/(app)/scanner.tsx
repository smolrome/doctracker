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
  const lastScanned = useRef<string>('');
  const cooldown = useRef<boolean>(false);

  useEffect(() => {
    Camera.requestCameraPermissionsAsync().then(({ status }) => {
      setHasPermission(status === 'granted');
    });
  }, []);

  const handleScan = async ({ data }: { data: string }) => {
    if (cooldown.current || data === lastScanned.current) return;
    cooldown.current = true;
    lastScanned.current = data;

    Vibration.vibrate(100);
    setScanState('loading');

    try {
      let docId = data;

      if (data.includes('/')) {
        const parts = data.split('/');
        docId = parts[parts.length - 1];
      }

      try {
        const res = await api.get(`/documents/${docId}`);
        if (res.data?.id) {
          setScanState('scanning');
          router.push(`/(app)/documents/${res.data.id}`);
          setTimeout(() => {
            cooldown.current = false;
            lastScanned.current = '';
          }, 3000);
          return;
        }
      } catch {
        // Not a direct doc ID
      }

      const tokenRes = await api.post('/qr/scan', { token: data });
      if (tokenRes.data?.doc?.id) {
        setScanState('scanning');
        router.push(`/(app)/documents/${tokenRes.data.doc.id}`);
        setTimeout(() => {
          cooldown.current = false;
          lastScanned.current = '';
        }, 3000);
        return;
      }

      throw new Error('Document not found');

    } catch (err: any) {
      setScanState('error');
      const msg = err.response?.data?.error || 'Could not find document for this QR code.';
      Alert.alert(
        'Scan Failed',
        msg,
        [{
          text: 'Try Again',
          onPress: () => {
            setScanState('scanning');
            setTimeout(() => {
              cooldown.current = false;
              lastScanned.current = '';
            }, 1000);
          }
        }]
      );
    }
  };

  if (hasPermission === false) {
    return (
      <View style={styles.centered}>
        <Text style={{ fontSize: 40, marginBottom: 16 }}>📷</Text>
        <Text style={{ fontSize: 18, fontWeight: 'bold', color: '#111', marginBottom: 8 }}>
          Camera Permission Required
        </Text>
        <Text style={{ color: '#6B7280', textAlign: 'center', paddingHorizontal: 32 }}>
          Please enable camera access in your phone settings to scan QR codes.
        </Text>
        <TouchableOpacity
          onPress={() => Camera.requestCameraPermissionsAsync()}
          style={styles.permissionBtn}
        >
          <Text style={{ color: '#fff', fontWeight: '600' }}>Grant Permission</Text>
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

  return (
    <View style={{ flex: 1, backgroundColor: '#000', paddingBottom: 100 }}>

      <CameraView
        style={StyleSheet.absoluteFillObject}
        facing="back"
        enableTorch={torchOn}
        onBarcodeScanned={scanState === 'scanning' ? handleScan : undefined}
        barcodeScannerSettings={{
          barcodeTypes: ['qr'],
        }}
      />

      <View style={styles.topOverlay}>
        <Text style={styles.headerText}>Scan Document QR</Text>
        <Text style={styles.subText}>Point camera at a document QR code</Text>
      </View>

      <View style={styles.frameContainer}>
        <View style={styles.frame}>
          <View style={[styles.corner, styles.topLeft]} />
          <View style={[styles.corner, styles.topRight]} />
          <View style={[styles.corner, styles.bottomLeft]} />
          <View style={[styles.corner, styles.bottomRight]} />

          {scanState === 'loading' && (
            <View style={styles.loadingOverlay}>
              <ActivityIndicator size="large" color="#fff" />
              <Text style={{ color: '#fff', marginTop: 8, fontWeight: '600' }}>
                Looking up document...
              </Text>
            </View>
          )}

          {scanState === 'error' && (
            <View style={styles.loadingOverlay}>
              <Text style={{ fontSize: 32 }}>❌</Text>
              <Text style={{ color: '#fff', marginTop: 8, fontWeight: '600' }}>
                Not found
              </Text>
            </View>
          )}
        </View>
      </View>

      <View style={styles.bottomOverlay}>
        <TouchableOpacity
          onPress={() => setTorchOn(!torchOn)}
          style={styles.controlBtn}
        >
          <Text style={{ fontSize: 24 }}>{torchOn ? '🔦' : '🔆'}</Text>
          <Text style={styles.controlLabel}>
            {torchOn ? 'Torch On' : 'Torch Off'}
          </Text>
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

    </View>
  );
}

const styles = StyleSheet.create({
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
  },
  permissionBtn: {
    marginTop: 24,
    backgroundColor: '#0038A8',
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 10,
  },
  topOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    paddingTop: 60,
    paddingBottom: 20,
    backgroundColor: 'rgba(0,0,0,0.6)',
    alignItems: 'center',
  },
  headerText: {
    color: '#fff',
    fontSize: 20,
    fontWeight: 'bold',
  },
  subText: {
    color: 'rgba(255,255,255,0.7)',
    fontSize: 13,
    marginTop: 4,
  },
  frameContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  frame: {
    width: 260,
    height: 260,
    position: 'relative',
    alignItems: 'center',
    justifyContent: 'center',
  },
  corner: {
    position: 'absolute',
    width: 40,
    height: 40,
    borderColor: '#fff',
    borderWidth: 4,
  },
  topLeft: {
    top: 0,
    left: 0,
    borderRightWidth: 0,
    borderBottomWidth: 0,
    borderTopLeftRadius: 8,
  },
  topRight: {
    top: 0,
    right: 0,
    borderLeftWidth: 0,
    borderBottomWidth: 0,
    borderTopRightRadius: 8,
  },
  bottomLeft: {
    bottom: 0,
    left: 0,
    borderRightWidth: 0,
    borderTopWidth: 0,
    borderBottomLeftRadius: 8,
  },
  bottomRight: {
    bottom: 0,
    right: 0,
    borderLeftWidth: 0,
    borderTopWidth: 0,
    borderBottomRightRadius: 8,
  },
  loadingOverlay: {
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0,0,0,0.6)',
    borderRadius: 12,
    padding: 20,
  },
  bottomOverlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    paddingBottom: 48,
    paddingTop: 20,
    backgroundColor: 'rgba(0,0,0,0.6)',
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 48,
  },
  controlBtn: {
    alignItems: 'center',
  },
  controlLabel: {
    color: 'rgba(255,255,255,0.8)',
    fontSize: 12,
    marginTop: 4,
  },
});