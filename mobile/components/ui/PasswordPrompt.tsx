/**
 * Cross-platform password prompt modal.
 * Use this instead of Alert.prompt (which is iOS-only).
 *
 * Usage:
 *   <PasswordPrompt
 *     visible={visible}
 *     title="Enter Your Password"
 *     message="Stored securely so fingerprint can sign you in."
 *     onConfirm={(pw) => { ... }}
 *     onCancel={() => setVisible(false)}
 *   />
 */
import { useState } from 'react';
import {
  Modal, View, Text, TextInput, TouchableOpacity, Platform,
} from 'react-native';
import { Lock, Eye, EyeOff } from 'lucide-react-native';

type Props = {
  visible: boolean;
  title?: string;
  message?: string;
  onConfirm: (password: string) => void;
  onCancel: () => void;
};

export default function PasswordPrompt({ visible, title, message, onConfirm, onCancel }: Props) {
  const [pw, setPw] = useState('');
  const [show, setShow] = useState(false);

  const handleConfirm = () => {
    const val = pw.trim();
    setPw('');
    setShow(false);
    onConfirm(val);
  };

  const handleCancel = () => {
    setPw('');
    setShow(false);
    onCancel();
  };

  return (
    <Modal visible={visible} transparent animationType="fade">
      <View style={{
        flex: 1, backgroundColor: 'rgba(0,0,0,0.45)',
        alignItems: 'center', justifyContent: 'center', padding: 32,
      }}>
        <View style={{
          backgroundColor: '#fff', borderRadius: 16, padding: 24,
          width: '100%', maxWidth: 360,
          shadowColor: '#000', shadowOffset: { width: 0, height: 8 },
          shadowOpacity: 0.20, shadowRadius: 20, elevation: 12,
        }}>
          {/* Title */}
          {title ? (
            <Text style={{ fontWeight: '800', color: '#1E293B', fontSize: 16, marginBottom: 6 }}>
              {title}
            </Text>
          ) : null}

          {/* Message */}
          {message ? (
            <Text style={{ color: '#64748B', fontSize: 13, lineHeight: 19, marginBottom: 18 }}>
              {message}
            </Text>
          ) : null}

          {/* Password input */}
          <View style={{
            flexDirection: 'row', alignItems: 'center',
            backgroundColor: '#F8FAFC', borderRadius: 10,
            borderWidth: 1.5, borderColor: '#E2E8F0',
            paddingHorizontal: 14, marginBottom: 20,
          }}>
            <Lock size={16} color="#94A3B8" style={{ marginRight: 10 }} />
            <TextInput
              value={pw}
              onChangeText={setPw}
              placeholder="Enter your password"
              placeholderTextColor="#CBD5E1"
              secureTextEntry={!show}
              autoFocus
              style={{ flex: 1, paddingVertical: 12, fontSize: 14, color: '#1E293B' }}
            />
            <TouchableOpacity onPress={() => setShow(!show)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              {show ? <EyeOff size={16} color="#94A3B8" /> : <Eye size={16} color="#94A3B8" />}
            </TouchableOpacity>
          </View>

          {/* Buttons */}
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <TouchableOpacity
              onPress={handleCancel}
              style={{
                flex: 1, borderRadius: 10, paddingVertical: 12,
                backgroundColor: '#F1F5F9', alignItems: 'center',
              }}
            >
              <Text style={{ color: '#64748B', fontWeight: '700', fontSize: 14 }}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={handleConfirm}
              disabled={!pw.trim()}
              style={{
                flex: 1, borderRadius: 10, paddingVertical: 12,
                backgroundColor: pw.trim() ? '#0038A8' : '#93C5FD',
                alignItems: 'center',
              }}
            >
              <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>Enable</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}
