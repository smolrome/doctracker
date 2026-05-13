import { Modal, View, Text, TouchableOpacity, StyleSheet } from 'react-native';

interface Props {
  visible: boolean;
  progress: number;
  onCancel?: () => void;
}

export function DownloadProgressModal({ visible, progress, onCancel }: Props) {
  const pct = Math.round(Math.min(Math.max(progress, 0), 1) * 100);

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      statusBarTranslucent
      onRequestClose={onCancel}
    >
      <View style={styles.backdrop} pointerEvents="box-none">
        <View style={styles.card}>

          {/* Icon bubble */}
          <View style={styles.iconBubble}>
            <Text style={styles.iconText}>⬇️</Text>
          </View>

          {/* Title */}
          <Text style={styles.title}>Downloading Update</Text>

          {/* Subtitle */}
          <Text style={styles.subtitle}>
            Please wait while the update is downloaded to your device.
          </Text>

          {/* Progress bar */}
          <View style={styles.barTrack}>
            <View style={[styles.barFill, { width: `${pct}%` }]} />
          </View>

          {/* Percentage */}
          <Text style={styles.pct}>{pct}%</Text>

          {/* Cancel button */}
          {onCancel ? (
            <TouchableOpacity style={styles.cancelBtn} onPress={onCancel} activeOpacity={0.82}>
              <Text style={styles.cancelText}>Cancel</Text>
            </TouchableOpacity>
          ) : null}

        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.55)',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  card: {
    width: '100%',
    backgroundColor: '#fff',
    borderRadius: 24,
    paddingTop: 28,
    paddingHorizontal: 24,
    paddingBottom: 20,
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.18,
    shadowRadius: 32,
    elevation: 20,
    alignItems: 'center',
  },
  iconBubble: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#0038A818',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  iconText: {
    fontSize: 30,
  },
  title: {
    fontSize: 18,
    fontWeight: '800',
    color: '#0F172A',
    textAlign: 'center',
    marginBottom: 10,
    letterSpacing: -0.3,
  },
  subtitle: {
    fontSize: 14,
    color: '#64748B',
    textAlign: 'center',
    lineHeight: 21,
    marginBottom: 20,
  },
  barTrack: {
    alignSelf: 'stretch',
    height: 8,
    borderRadius: 4,
    backgroundColor: '#E2E8F0',
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    borderRadius: 4,
    backgroundColor: '#0038A8',
  },
  pct: {
    alignSelf: 'flex-end',
    fontSize: 13,
    color: '#64748B',
    marginTop: 6,
    marginBottom: 20,
  },
  cancelBtn: {
    alignSelf: 'stretch',
    borderRadius: 14,
    paddingVertical: 13,
    backgroundColor: '#F1F5F9',
    alignItems: 'center',
    justifyContent: 'center',
  },
  cancelText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#475569',
  },
});
