import { useState, useEffect } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput,
  Alert, ActivityIndicator, StatusBar, Switch,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../lib/store';
import { authStorage } from '../../lib/auth';
import * as Biometrics from '../../lib/biometrics';
import { User, Lock, Eye, EyeOff, LogOut, Fingerprint } from 'lucide-react-native';
import PasswordPrompt from '../../components/ui/PasswordPrompt';
import api from '../../lib/api';

function Label({ text }: { text: string }) {
  return (
    <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
      {text}
    </Text>
  );
}

export default function ClientProfile() {
  const router = useRouter();
  const { user, setUser, logout } = useAuthStore();
  const queryClient = useQueryClient();

  const [fullName, setFullName] = useState(user?.full_name || '');
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [showNew, setShowNew] = useState(false);
  const [showCurrent, setShowCurrent] = useState(false);

  // Biometric state
  const [bioAvailable, setBioAvailable]         = useState(false);
  const [bioEnabled, setBioEnabled]             = useState(false);
  const [bioPromptVisible, setBioPromptVisible] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const hasHardware = await Biometrics.hasHardwareAsync();
        const isEnrolled  = await Biometrics.isEnrolledAsync();
        const enabled     = await authStorage.isBiometricEnabled();
        setBioAvailable(hasHardware && isEnrolled);
        setBioEnabled(hasHardware && isEnrolled && enabled);
      } catch {}
    })();
  }, []);

  const handleToggleBiometric = async (value: boolean) => {
    if (value) {
      const result = await Biometrics.authenticateAsync({
        promptMessage: 'Confirm your identity to enable fingerprint login',
        cancelLabel: 'Cancel',
      });
      if (!result.success) return;
      setBioPromptVisible(true);
    } else {
      Alert.alert(
        'Disable Fingerprint Login',
        'Remove fingerprint sign-in from this device?',
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Remove', style: 'destructive',
            onPress: async () => {
              await authStorage.clearBiometricCredentials();
              setBioEnabled(false);
            },
          },
        ],
      );
    }
  };

  const handleBioPasswordConfirm = async (pw: string) => {
    setBioPromptVisible(false);
    if (!pw) return;
    await authStorage.saveBiometricCredentials(user?.username || '', pw);
    setBioEnabled(true);
    Alert.alert('✅ Enabled', 'Fingerprint login is now active.');
  };

  const inputStyle = {
    backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5,
    borderColor: '#E2E8F0', paddingHorizontal: 14, paddingVertical: 13,
    fontSize: 14, color: '#1E293B', marginBottom: 16,
  };

  const updateProfileMutation = useMutation({
    mutationFn: () => api.patch('/profile', { full_name: fullName.trim() }),
    onSuccess: (res) => {
      const updated = res.data?.user || { ...user, full_name: fullName.trim() };
      setUser(updated);
      authStorage.saveUser(updated);
      Alert.alert('Saved', 'Profile updated successfully.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Update failed.'),
  });

  const changePasswordMutation = useMutation({
    mutationFn: () => api.post('/auth/change-password', { current_password: currentPw, new_password: newPw }),
    onSuccess: () => {
      setCurrentPw(''); setNewPw(''); setConfirmPw('');
      Alert.alert('Password Changed', 'Your password has been updated.');
    },
    onError: (e: any) => Alert.alert('Error', e?.response?.data?.error || 'Password change failed.'),
  });

  const handleChangePassword = () => {
    if (!currentPw || !newPw || !confirmPw) {
      Alert.alert('Required', 'Please fill all password fields.'); return;
    }
    if (newPw !== confirmPw) {
      Alert.alert('Mismatch', 'New passwords do not match.'); return;
    }
    if (newPw.length < 6) {
      Alert.alert('Too Short', 'Password must be at least 6 characters.'); return;
    }
    changePasswordMutation.mutate();
  };

  const handleLogout = () => {
    Alert.alert('Logout', 'Are you sure?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Logout', style: 'destructive',
        onPress: async () => {
          await authStorage.clearAll();
          logout();
          queryClient.clear();
          router.replace('/(auth)/login');
        },
      },
    ]);
  };

  return (
    <View style={{ flex: 1, backgroundColor: '#F8FAFC' }}>
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* Header */}
      <View style={{ backgroundColor: '#0038A8', paddingTop: 56, paddingBottom: 28, paddingHorizontal: 20, alignItems: 'center' }}>
        <View style={{
          width: 72, height: 72, borderRadius: 36,
          backgroundColor: 'rgba(255,255,255,0.20)',
          alignItems: 'center', justifyContent: 'center', marginBottom: 12,
        }}>
          <Text style={{ fontSize: 30, fontWeight: '700', color: '#fff' }}>
            {user?.full_name?.charAt(0)?.toUpperCase() || '?'}
          </Text>
        </View>
        <Text style={{ color: '#fff', fontSize: 18, fontWeight: '800' }}>{user?.full_name}</Text>
        <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 13, marginTop: 4 }}>@{user?.username}</Text>
        <View style={{ backgroundColor: '#EFF6FF', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 4, marginTop: 8 }}>
          <Text style={{ color: '#0038A8', fontSize: 12, fontWeight: '700' }}>Client</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 120 }}>

        {/* Profile info */}
        <View style={{ backgroundColor: '#fff', borderRadius: 14, padding: 20, marginBottom: 12, borderWidth: 0.5, borderColor: '#E2E8F0' }}>
          <Text style={{ fontWeight: '700', color: '#0038A8', fontSize: 14, marginBottom: 16 }}>Profile</Text>
          <Label text="Full Name" />
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16, backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: '#E2E8F0', paddingHorizontal: 14 }}>
            <User color="#94A3B8" size={16} style={{ marginRight: 10 }} />
            <TextInput
              value={fullName} onChangeText={setFullName}
              placeholder="Your full name"
              placeholderTextColor="#CBD5E1"
              style={{ flex: 1, paddingVertical: 13, fontSize: 14, color: '#1E293B' }}
            />
          </View>
          <Label text="Username (read-only)" />
          <View style={{ backgroundColor: '#F8FAFC', borderRadius: 12, borderWidth: 1.5, borderColor: '#E2E8F0', paddingHorizontal: 14, paddingVertical: 13, marginBottom: 16 }}>
            <Text style={{ color: '#64748B', fontSize: 14 }}>@{user?.username}</Text>
          </View>
          <TouchableOpacity
            onPress={() => updateProfileMutation.mutate()}
            disabled={updateProfileMutation.isPending || fullName.trim() === user?.full_name}
            style={{
              backgroundColor: (updateProfileMutation.isPending || fullName.trim() === user?.full_name) ? '#93C5FD' : '#0038A8',
              borderRadius: 11, paddingVertical: 12, alignItems: 'center',
            }}
          >
            <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>
              {updateProfileMutation.isPending ? 'Saving…' : 'Save Changes'}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Change password */}
        <View style={{ backgroundColor: '#fff', borderRadius: 14, padding: 20, marginBottom: 12, borderWidth: 0.5, borderColor: '#E2E8F0' }}>
          <Text style={{ fontWeight: '700', color: '#0038A8', fontSize: 14, marginBottom: 16 }}>Change Password</Text>

          <Label text="Current Password" />
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16, backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: '#E2E8F0', paddingHorizontal: 14 }}>
            <Lock color="#94A3B8" size={16} style={{ marginRight: 10 }} />
            <TextInput
              value={currentPw} onChangeText={setCurrentPw}
              placeholder="Current password" placeholderTextColor="#CBD5E1"
              secureTextEntry={!showCurrent}
              style={{ flex: 1, paddingVertical: 13, fontSize: 14, color: '#1E293B' }}
            />
            <TouchableOpacity onPress={() => setShowCurrent(!showCurrent)}>
              {showCurrent ? <EyeOff size={16} color="#94A3B8" /> : <Eye size={16} color="#94A3B8" />}
            </TouchableOpacity>
          </View>

          <Label text="New Password" />
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16, backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: '#E2E8F0', paddingHorizontal: 14 }}>
            <Lock color="#94A3B8" size={16} style={{ marginRight: 10 }} />
            <TextInput
              value={newPw} onChangeText={setNewPw}
              placeholder="At least 6 characters" placeholderTextColor="#CBD5E1"
              secureTextEntry={!showNew}
              style={{ flex: 1, paddingVertical: 13, fontSize: 14, color: '#1E293B' }}
            />
            <TouchableOpacity onPress={() => setShowNew(!showNew)}>
              {showNew ? <EyeOff size={16} color="#94A3B8" /> : <Eye size={16} color="#94A3B8" />}
            </TouchableOpacity>
          </View>

          <Label text="Confirm New Password" />
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: confirmPw && confirmPw !== newPw ? 4 : 16, backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: confirmPw && confirmPw !== newPw ? '#FECACA' : '#E2E8F0', paddingHorizontal: 14 }}>
            <Lock color="#94A3B8" size={16} style={{ marginRight: 10 }} />
            <TextInput
              value={confirmPw} onChangeText={setConfirmPw}
              placeholder="Repeat new password" placeholderTextColor="#CBD5E1"
              secureTextEntry style={{ flex: 1, paddingVertical: 13, fontSize: 14, color: '#1E293B' }}
            />
          </View>
          {confirmPw.length > 0 && confirmPw !== newPw && (
            <Text style={{ color: '#EF4444', fontSize: 12, marginBottom: 12 }}>Passwords do not match</Text>
          )}

          <TouchableOpacity
            onPress={handleChangePassword}
            disabled={changePasswordMutation.isPending}
            style={{
              backgroundColor: changePasswordMutation.isPending ? '#FCD34D' : '#D97706',
              borderRadius: 11, paddingVertical: 12, alignItems: 'center',
            }}
          >
            <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>
              {changePasswordMutation.isPending ? 'Updating…' : 'Change Password'}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Fingerprint Login */}
        {bioAvailable && (
          <View style={{
            backgroundColor: '#fff', borderRadius: 14, padding: 20,
            marginBottom: 12, borderWidth: 0.5, borderColor: '#E2E8F0',
            flexDirection: 'row', alignItems: 'center', gap: 14,
          }}>
            <View style={{
              width: 40, height: 40, borderRadius: 20,
              backgroundColor: bioEnabled ? '#EFF6FF' : '#F1F5F9',
              alignItems: 'center', justifyContent: 'center',
            }}>
              <Fingerprint size={20} color={bioEnabled ? '#0038A8' : '#94A3B8'} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '700', color: '#1E293B', fontSize: 15 }}>
                Fingerprint Login
              </Text>
              <Text style={{ color: '#94A3B8', fontSize: 12, marginTop: 2 }}>
                {bioEnabled ? 'Tap your sensor to sign in next time' : 'Sign in faster with your fingerprint'}
              </Text>
            </View>
            <Switch
              value={bioEnabled}
              onValueChange={handleToggleBiometric}
              trackColor={{ false: '#E2E8F0', true: '#BFDBFE' }}
              thumbColor={bioEnabled ? '#0038A8' : '#94A3B8'}
            />
          </View>
        )}

        {/* Logout */}
        <TouchableOpacity
          onPress={handleLogout}
          style={{
            backgroundColor: '#FEE2E2', borderRadius: 13, padding: 16,
            alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8,
            marginBottom: 20,
          }}
        >
          <LogOut size={18} color="#DC2626" />
          <Text style={{ color: '#DC2626', fontWeight: '700', fontSize: 15 }}>Logout</Text>
        </TouchableOpacity>
      </ScrollView>

      <PasswordPrompt
        visible={bioPromptVisible}
        title="Enter Your Password"
        message="Stored securely on this device so fingerprint can sign you in automatically next time."
        onConfirm={handleBioPasswordConfirm}
        onCancel={() => setBioPromptVisible(false)}
      />
    </View>
  );
}
