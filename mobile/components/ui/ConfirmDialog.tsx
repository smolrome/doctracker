import { useEffect, useRef } from 'react';
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Animated,
  Pressable,
} from 'react-native';

export interface ConfirmDialogButton {
  label: string;
  onPress: () => void;
  /** 'default' = filled primary colour, 'ghost' = outlined/muted, 'danger' = filled red/orange */
  variant?: 'default' | 'ghost' | 'danger';
}

interface Props {
  visible: boolean;
  onClose: () => void;
  /** When true, tapping the backdrop does NOT close the dialog. Use for force-update. */
  dismissable?: boolean;

  /** Large emoji or single character shown above the title */
  icon?: string;
  /** Accent colour used for the icon circle background and primary button. Default: #0038A8 */
  accentColor?: string;

  title: string;
  message: string;

  /** Up to 2 buttons. Right-most is the primary/confirm action. */
  buttons: [ConfirmDialogButton] | [ConfirmDialogButton, ConfirmDialogButton];
}


export function ConfirmDialog({
  visible,
  onClose,
  dismissable = true,
  icon,
  accentColor = '#0038A8',
  title,
  message,
  buttons,
}: Props) {
  const scale = useRef(new Animated.Value(0.85)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      Animated.parallel([
        Animated.spring(scale, {
          toValue: 1,
          useNativeDriver: true,
          damping: 18,
          stiffness: 280,
        }),
        Animated.timing(opacity, {
          toValue: 1,
          duration: 180,
          useNativeDriver: true,
        }),
      ]).start();
    } else {
      Animated.parallel([
        Animated.timing(scale, {
          toValue: 0.85,
          duration: 150,
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 0,
          duration: 150,
          useNativeDriver: true,
        }),
      ]).start();
    }
  }, [visible]);

  // Derive a light tint of accentColor for the icon backdrop
  const iconBg = `${accentColor}18`; // ~10% opacity hex

  const getButtonStyle = (variant: ConfirmDialogButton['variant'] = 'default') => {
    switch (variant) {
      case 'danger':
        return {
          container: [styles.btn, { backgroundColor: accentColor }],
          text: [styles.btnText, { color: '#fff' }],
        };
      case 'ghost':
        return {
          container: [styles.btn, styles.btnGhost],
          text: [styles.btnText, styles.btnGhostText],
        };
      default:
        return {
          container: [styles.btn, { backgroundColor: accentColor }],
          text: [styles.btnText, { color: '#fff' }],
        };
    }
  };

  if (!visible) return null;

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      statusBarTranslucent
      onRequestClose={onClose}
    >
      {/* Backdrop */}
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Animated.View
          style={[styles.backdrop, { opacity }]}
        />
      </Pressable>

      {/* Card */}
      <View style={styles.centeredContainer} pointerEvents="box-none">
        <Animated.View
          style={[
            styles.card,
            { transform: [{ scale }], opacity },
          ]}
        >
          {/* Icon bubble */}
          {icon ? (
            <View style={[styles.iconBubble, { backgroundColor: iconBg }]}>
              <Text style={styles.iconText}>{icon}</Text>
            </View>
          ) : null}

          {/* Title */}
          <Text style={styles.title}>{title}</Text>

          {/* Message */}
          <Text style={styles.message}>{message}</Text>

          {/* Divider */}
          <View style={styles.divider} />

          {/* Buttons */}
          <View style={[styles.btnRow, buttons.length === 1 && { justifyContent: 'center' }]}>
            {buttons.map((btn, i) => {
              const s = getButtonStyle(btn.variant);
              return (
                <TouchableOpacity
                  key={i}
                  style={[s.container, buttons.length === 2 && { flex: 1 }]}
                  onPress={() => {
                    onClose();
                    btn.onPress();
                  }}
                  activeOpacity={0.82}
                >
                  <Text style={s.text} numberOfLines={1}>{btn.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </Animated.View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(15, 23, 42, 0.55)',
  },
  centeredContainer: {
    flex: 1,
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
  message: {
    fontSize: 14,
    color: '#64748B',
    textAlign: 'center',
    lineHeight: 21,
    marginBottom: 4,
  },
  divider: {
    height: 1,
    backgroundColor: '#F1F5F9',
    alignSelf: 'stretch',
    marginVertical: 20,
  },
  btnRow: {
    flexDirection: 'row',
    alignSelf: 'stretch',
    gap: 10,
  },
  btn: {
    borderRadius: 14,
    paddingVertical: 13,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnText: {
    fontSize: 14,
    fontWeight: '700',
  },
  btnGhost: {
    backgroundColor: '#F1F5F9',
  },
  btnGhostText: {
    color: '#475569',
  },
});
