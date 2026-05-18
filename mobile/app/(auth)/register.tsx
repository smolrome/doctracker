import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView,
  ActivityIndicator, KeyboardAvoidingView, Platform, StatusBar, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { User, Mail, Lock, Eye, EyeOff, ArrowLeft, AlertCircle, Building2 } from 'lucide-react-native';
import api from '../../lib/api';

export default function Register() {
  const router = useRouter();

  const [fullName, setFullName]         = useState('');
  const [username, setUsername]         = useState('');
  const [email, setEmail]               = useState('');
  const [office, setOffice]             = useState('');
  const [password, setPassword]         = useState('');
  const [confirmPw, setConfirmPw]       = useState('');
  const [showPw, setShowPw]             = useState(false);
  const [showConfirm, setShowConfirm]   = useState(false);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState('');

  const inputStyle = {
    backgroundColor: '#fff',
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: '#E2E8F0',
    paddingHorizontal: 14,
    paddingVertical: 13,
    fontSize: 15,
    color: '#1E293B',
    marginBottom: 16,
    flex: 1,
  };

  const handleRegister = async () => {
    setError('');
    if (!fullName.trim() || !username.trim() || !password) {
      setError('Full name, username, and password are required.');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }
    if (password !== confirmPw) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      await api.post('/client/register', {
        full_name: fullName.trim(),
        username:  username.trim().toLowerCase(),
        email:     email.trim(),
        office:    office.trim(),
        password,
      });
      Alert.alert(
        'Registration Submitted',
        'Your account is pending admin approval. You will be notified once approved.',
        [{ text: 'OK', onPress: () => router.replace('/(auth)/login') }],
      );
    } catch (err: any) {
      const msg = err?.response?.data?.error || 'Registration failed. Please try again.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: '#0038A8' }}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* Top bar */}
      <View style={{ paddingTop: 56, paddingHorizontal: 20, paddingBottom: 24 }}>
        <TouchableOpacity
          onPress={() => router.back()}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 20 }}
        >
          <ArrowLeft size={18} color="rgba(255,255,255,0.75)" />
          <Text style={{ color: 'rgba(255,255,255,0.75)', fontSize: 14, fontWeight: '600' }}>Back to Login</Text>
        </TouchableOpacity>

        <Text style={{ fontSize: 26, fontWeight: '900', color: '#fff', letterSpacing: -0.5 }}>
          Create Account
        </Text>
        <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 13, marginTop: 6 }}>
          Register as a client to track your documents.{'\n'}An admin will approve your account.
        </Text>
      </View>

      {/* Form */}
      <View style={{
        flex: 1, backgroundColor: '#F8FAFC',
        borderTopLeftRadius: 24, borderTopRightRadius: 24,
      }}>
        <ScrollView
          contentContainerStyle={{ padding: 24, paddingBottom: 60 }}
          keyboardShouldPersistTaps="handled"
        >
          {/* Error */}
          {error ? (
            <View style={{
              backgroundColor: '#FEF2F2', borderRadius: 10, padding: 12,
              marginBottom: 20, borderWidth: 1, borderColor: '#FECACA',
              flexDirection: 'row', alignItems: 'flex-start', gap: 8,
            }}>
              <AlertCircle color="#DC2626" size={18} />
              <Text style={{ color: '#DC2626', fontSize: 13, fontWeight: '600', flex: 1 }}>{error}</Text>
            </View>
          ) : null}

          {/* Full Name */}
          <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
            Full Name <Text style={{ color: '#EF4444' }}>*</Text>
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16, backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: '#E2E8F0', paddingHorizontal: 14 }}>
            <User color="#94A3B8" size={18} style={{ marginRight: 10 }} />
            <TextInput
              value={fullName}
              onChangeText={setFullName}
              placeholder="Your full name"
              placeholderTextColor="#CBD5E1"
              style={{ flex: 1, paddingVertical: 13, fontSize: 15, color: '#1E293B' }}
            />
          </View>

          {/* Username */}
          <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
            Username <Text style={{ color: '#EF4444' }}>*</Text>
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16, backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: '#E2E8F0', paddingHorizontal: 14 }}>
            <Text style={{ color: '#94A3B8', fontSize: 15, marginRight: 6 }}>@</Text>
            <TextInput
              value={username}
              onChangeText={(t) => setUsername(t.replace(/\s/g, '').toLowerCase())}
              placeholder="choose_a_username"
              placeholderTextColor="#CBD5E1"
              autoCapitalize="none"
              autoCorrect={false}
              style={{ flex: 1, paddingVertical: 13, fontSize: 15, color: '#1E293B' }}
            />
          </View>

          {/* Email (optional) */}
          <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
            Email <Text style={{ color: '#94A3B8', fontWeight: '400', textTransform: 'none' }}>(optional)</Text>
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16, backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: '#E2E8F0', paddingHorizontal: 14 }}>
            <Mail color="#94A3B8" size={18} style={{ marginRight: 10 }} />
            <TextInput
              value={email}
              onChangeText={setEmail}
              placeholder="your@email.com"
              placeholderTextColor="#CBD5E1"
              keyboardType="email-address"
              autoCapitalize="none"
              style={{ flex: 1, paddingVertical: 13, fontSize: 15, color: '#1E293B' }}
            />
          </View>

          {/* School / Office (optional) */}
          <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
            School / Office <Text style={{ color: '#94A3B8', fontWeight: '400', textTransform: 'none' }}>(optional)</Text>
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16, backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: '#E2E8F0', paddingHorizontal: 14 }}>
            <Building2 color="#94A3B8" size={18} style={{ marginRight: 10 }} />
            <TextInput
              value={office}
              onChangeText={setOffice}
              placeholder="e.g. San Ricardo ES, Baybay City"
              placeholderTextColor="#CBD5E1"
              style={{ flex: 1, paddingVertical: 13, fontSize: 15, color: '#1E293B' }}
            />
          </View>

          {/* Password */}
          <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
            Password <Text style={{ color: '#EF4444' }}>*</Text>
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16, backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: '#E2E8F0', paddingHorizontal: 14 }}>
            <Lock color="#94A3B8" size={18} style={{ marginRight: 10 }} />
            <TextInput
              value={password}
              onChangeText={setPassword}
              placeholder="Min. 6 characters"
              placeholderTextColor="#CBD5E1"
              secureTextEntry={!showPw}
              style={{ flex: 1, paddingVertical: 13, fontSize: 15, color: '#1E293B' }}
            />
            <TouchableOpacity onPress={() => setShowPw(!showPw)} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
              {showPw ? <EyeOff color="#94A3B8" size={18} /> : <Eye color="#94A3B8" size={18} />}
            </TouchableOpacity>
          </View>

          {/* Confirm Password */}
          <Text style={{ fontSize: 11, fontWeight: '700', color: '#475569', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 6 }}>
            Confirm Password <Text style={{ color: '#EF4444' }}>*</Text>
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8, backgroundColor: '#fff', borderRadius: 12, borderWidth: 1.5, borderColor: confirmPw && confirmPw !== password ? '#FECACA' : '#E2E8F0', paddingHorizontal: 14 }}>
            <Lock color="#94A3B8" size={18} style={{ marginRight: 10 }} />
            <TextInput
              value={confirmPw}
              onChangeText={setConfirmPw}
              placeholder="Repeat password"
              placeholderTextColor="#CBD5E1"
              secureTextEntry={!showConfirm}
              style={{ flex: 1, paddingVertical: 13, fontSize: 15, color: '#1E293B' }}
            />
            <TouchableOpacity onPress={() => setShowConfirm(!showConfirm)} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
              {showConfirm ? <EyeOff color="#94A3B8" size={18} /> : <Eye color="#94A3B8" size={18} />}
            </TouchableOpacity>
          </View>
          {confirmPw.length > 0 && confirmPw !== password && (
            <Text style={{ color: '#EF4444', fontSize: 12, marginBottom: 12 }}>Passwords do not match</Text>
          )}

          {/* Submit */}
          <TouchableOpacity
            onPress={handleRegister}
            disabled={loading}
            style={{
              backgroundColor: loading ? '#93C5FD' : '#0038A8',
              borderRadius: 13, paddingVertical: 15,
              alignItems: 'center', marginTop: 12,
            }}
          >
            {loading ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <ActivityIndicator color="#fff" size="small" />
                <Text style={{ color: '#fff', fontWeight: '700', fontSize: 15 }}>Submitting…</Text>
              </View>
            ) : (
              <Text style={{ color: '#fff', fontWeight: '800', fontSize: 15 }}>Register</Text>
            )}
          </TouchableOpacity>

          {/* PH flag strip */}
          <View style={{ flexDirection: 'row', justifyContent: 'center', marginTop: 24 }}>
            <View style={{ width: 20, height: 3, backgroundColor: '#0038A8', borderRadius: 1 }} />
            <View style={{ width: 20, height: 3, backgroundColor: '#CE1126' }} />
            <View style={{ width: 20, height: 3, backgroundColor: '#FCD116', borderRadius: 1 }} />
          </View>
        </ScrollView>
      </View>
    </KeyboardAvoidingView>
  );
}
