import { useState, useEffect, useRef } from 'react';
import {
  View, Text, TouchableOpacity, Alert,
  ActivityIndicator, StyleSheet, Linking,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useRouter } from 'expo-router';
import { ScanLine, FlashlightOff, Flashlight } from 'lucide-react-native';

export default function ClientScanScreen() {
  const router = useRouter();
  const [permission, requestPermission] = useCameraPermissions();
  const [torch, setTorch] = useState(false);
  const [scanned, setScanned] = useState(false);
  const cooldown = useRef(false);

  const parseSubmissionQR = (value: string): { officeSlug: string; officeName: string } | null => {
    try {
      const match = value.match(/\/office-action\/([^?]+)-sub(\?|$)/);
      if (!match) return null;
      const rawSlug = match[1];
      const officeSlug = rawSlug.toLowerCase();
      const officeName = rawSlug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      return { officeSlug, officeName };
    } catch {
      return null;
    }
  };

  const handleScan = ({ data }: { data: string }) => {
    if (cooldown.current || scanned) return;
    cooldown.current = true;
    setScanned(true);

    const parsed = parseSubmissionQR(data);
    if (parsed) {
      router.push({
        pathname: '/(client)/submit',
        params: { officeSlug: parsed.officeSlug, officeName: parsed.officeName },
      });
      setTimeout(() => {
        cooldown.current = false;
        setScanned(false);
      }, 3000);
      return;
    }

    Alert.alert(
      'Unrecognized QR',
      'This QR code is not a document submission code. Please scan an office submission QR.',
      [{ text: 'OK', onPress: () => { cooldown.current = false; setScanned(false); } }],
    );
  };

  if (!permission) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color='#0038A8' />
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <ScanLine size={48} color='#94A3B8' />
        <Text style={styles.permTitle}>Camera Access Needed</Text>
        <Text style={styles.permSub}>Allow camera access to scan office QR codes.</Text>
        <TouchableOpacity style={styles.btn} onPress={requestPermission}>
          <Text style={styles.btnText}>Allow Camera</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.linkBtn} onPress={() => Linking.openSettings()}>
          <Text style={styles.linkText}>Open Settings</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        style={StyleSheet.absoluteFill}
        enableTorch={torch}
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={scanned ? undefined : handleScan}
      />
      <View style={styles.overlay}>
        <Text style={styles.title}>Scan Office QR</Text>
        <Text style={styles.sub}>Point at an office submission QR code</Text>
        <View style={styles.frame} />
        <TouchableOpacity style={styles.torchBtn} onPress={() => setTorch(t => !t)}>
          {torch
            ? <Flashlight size={24} color='#FFFFFF' />
            : <FlashlightOff size={24} color='#FFFFFF' />}
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, backgroundColor: '#F8FAFC' },
  overlay: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  title: { color: '#FFFFFF', fontSize: 18, fontWeight: '700', marginTop: 48 },
  sub: { color: '#CBD5E1', fontSize: 13 },
  frame: {
    width: 240, height: 240,
    borderWidth: 2, borderColor: '#0038A8', borderRadius: 16,
    backgroundColor: 'transparent', marginVertical: 24,
  },
  torchBtn: {
    marginTop: 16, backgroundColor: 'rgba(0,0,0,0.5)',
    borderRadius: 32, padding: 14,
  },
  permTitle: { fontSize: 18, fontWeight: '700', color: '#0F172A', marginTop: 16 },
  permSub: { fontSize: 14, color: '#64748B', textAlign: 'center', marginTop: 8, marginBottom: 24 },
  btn: { backgroundColor: '#0038A8', paddingHorizontal: 32, paddingVertical: 12, borderRadius: 10 },
  btnText: { color: '#FFFFFF', fontWeight: '700', fontSize: 15 },
  linkBtn: { marginTop: 12 },
  linkText: { color: '#0038A8', fontSize: 14 },
});
