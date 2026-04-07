import { useState, useCallback, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Animated,
  StatusBar,
  Dimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../../lib/api';
import { authStorage } from '../../lib/auth';
import { useAuthStore } from '../../lib/store';

const { width } = Dimensions.get('window');

interface ApiError {
  response?: {
    data?: { error?: string };
    status?: number;
  };
  message?: string;
  code?: string;
}

export default function Login() {
  const router = useRouter();
  const setUser = useAuthStore((s) => s.setUser);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [usernameFocused, setUsernameFocused] = useState(false);
  const [passwordFocused, setPasswordFocused] = useState(false);

  // Animations
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(40)).current;
  const logoScale = useRef(new Animated.Value(0.8)).current;
  const shakeAnim = useRef(new Animated.Value(0)).current;
  const errorFade = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 700,
        useNativeDriver: true,
      }),
      Animated.spring(slideAnim, {
        toValue: 0,
        tension: 60,
        friction: 10,
        useNativeDriver: true,
      }),
      Animated.spring(logoScale, {
        toValue: 1,
        tension: 50,
        friction: 8,
        useNativeDriver: true,
      }),
    ]).start();
  }, []);

  const shakeError = () => {
    Animated.sequence([
      Animated.timing(shakeAnim, { toValue: 10, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -10, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 8, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -8, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 0, duration: 60, useNativeDriver: true }),
    ]).start();

    Animated.timing(errorFade, {
      toValue: 1,
      duration: 300,
      useNativeDriver: true,
    }).start();
  };

  const dismissError = useCallback(() => {
    Animated.timing(errorFade, {
      toValue: 0,
      duration: 200,
      useNativeDriver: true,
    }).start(() => setError(''));
  }, []);

  const parseError = (err: ApiError): string => {
    if (err.response) {
      const status = err.response.status;
      const serverMsg = err.response.data?.error;
      if (status === 401) return 'Invalid username or password';
      if (status === 403) return 'Account is locked or inactive';
      if (status === 429) return serverMsg || 'Too many attempts. Please wait.';
      if (status === 500) return 'Server error. Please try again later';
      if (serverMsg) return serverMsg;
    }
    if (err.code === 'ECONNABORTED' || err.message?.includes('timeout'))
      return 'Request timed out. Check your connection';
    if (!err.response)
      return 'Unable to connect. Check your internet';
    return 'Login failed. Please try again';
  };

  const handleLogin = async () => {
    const trimmedUsername = username.trim();
    const trimmedPassword = password.trim();

    if (!trimmedUsername || !trimmedPassword) {
      setError('Please enter username and password');
      shakeError();
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await api.post('/auth/login', {
        username: trimmedUsername,
        password: trimmedPassword,
      });

      const { access_token, refresh_token, user } = response.data;
      await authStorage.saveTokens(access_token, refresh_token);
      await authStorage.saveUser(user);
      setUser(user);
      router.replace('/(app)/dashboard');
    } catch (err: any) {
      const msg = parseError(err);
      setError(msg);
      shakeError();
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: '#F0F4FF' }}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <StatusBar barStyle="dark-content" backgroundColor="#F0F4FF" />

      {/* Background decorative circles */}
      <View style={{
        position: 'absolute', top: -60, right: -60,
        width: 220, height: 220, borderRadius: 110,
        backgroundColor: '#0038A8', opacity: 0.06,
      }} />
      <View style={{
        position: 'absolute', top: 80, right: -30,
        width: 120, height: 120, borderRadius: 60,
        backgroundColor: '#FCD116', opacity: 0.12,
      }} />
      <View style={{
        position: 'absolute', bottom: -80, left: -50,
        width: 260, height: 260, borderRadius: 130,
        backgroundColor: '#0038A8', opacity: 0.05,
      }} />
      <View style={{
        position: 'absolute', bottom: 120, left: -20,
        width: 100, height: 100, borderRadius: 50,
        backgroundColor: '#CE1126', opacity: 0.06,
      }} />

      <ScrollView
        contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', paddingHorizontal: 24, paddingVertical: 48 }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Animated.View style={{ opacity: fadeAnim, transform: [{ translateY: slideAnim }] }}>

          {/* Header — Logo + Title */}
          <Animated.View style={{
            alignItems: 'center',
            marginBottom: 36,
            transform: [{ scale: logoScale }],
          }}>
            {/* Logo circle with PH flag colors accent */}
            <View style={{
              width: 88, height: 88, borderRadius: 44,
              backgroundColor: '#0038A8',
              alignItems: 'center', justifyContent: 'center',
              marginBottom: 6,
              shadowColor: '#0038A8',
              shadowOffset: { width: 0, height: 8 },
              shadowOpacity: 0.35,
              shadowRadius: 16,
              elevation: 12,
            }}>
              <Text style={{ fontSize: 38 }}>📄</Text>
            </View>

            {/* PH flag color bar */}
            <View style={{ flexDirection: 'row', marginBottom: 16, borderRadius: 2, overflow: 'hidden' }}>
              <View style={{ width: 28, height: 4, backgroundColor: '#0038A8' }} />
              <View style={{ width: 28, height: 4, backgroundColor: '#CE1126' }} />
              <View style={{ width: 28, height: 4, backgroundColor: '#FCD116' }} />
            </View>

            <Text style={{
              fontSize: 26, fontWeight: '900',
              color: '#0038A8', letterSpacing: -0.5,
              textAlign: 'center',
            }}>
              DepEd Leyte
            </Text>
            <Text style={{
              fontSize: 13, color: '#64748B',
              marginTop: 4, textAlign: 'center',
              letterSpacing: 0.3,
            }}>
              Document Tracker — Personnel Unit
            </Text>
          </Animated.View>

          {/* Card */}
          <View style={{
            backgroundColor: '#fff',
            borderRadius: 20,
            padding: 24,
            shadowColor: '#0038A8',
            shadowOffset: { width: 0, height: 4 },
            shadowOpacity: 0.10,
            shadowRadius: 20,
            elevation: 6,
          }}>
            <Text style={{
              fontSize: 20, fontWeight: '800',
              color: '#1E293B', marginBottom: 4,
            }}>
              Sign In
            </Text>
            <Text style={{
              fontSize: 13, color: '#94A3B8',
              marginBottom: 24,
            }}>
              Log in to submit and track your documents.
            </Text>

            {/* Error box */}
            {error ? (
              <Animated.View style={{
                opacity: errorFade,
                transform: [{ translateX: shakeAnim }],
              }}>
                <TouchableOpacity
                  onPress={dismissError}
                  activeOpacity={0.8}
                  style={{
                    backgroundColor: '#FEF2F2',
                    borderRadius: 10,
                    padding: 12,
                    marginBottom: 20,
                    borderWidth: 1,
                    borderColor: '#FECACA',
                    flexDirection: 'row',
                    alignItems: 'flex-start',
                  }}
                >
                  <Text style={{ fontSize: 14, marginRight: 8 }}>❌</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: '#DC2626', fontSize: 13, fontWeight: '600' }}>
                      {error}
                    </Text>
                    <Text style={{ color: '#EF4444', fontSize: 11, marginTop: 2 }}>
                      Tap to dismiss
                    </Text>
                  </View>
                </TouchableOpacity>
              </Animated.View>
            ) : null}

            {/* Username field */}
            <Text style={{
              fontSize: 12, fontWeight: '700',
              color: '#475569', marginBottom: 6,
              textTransform: 'uppercase', letterSpacing: 0.8,
            }}>
              Username
            </Text>
            <View style={{
              borderWidth: 1.5,
              borderColor: usernameFocused ? '#0038A8' : error ? '#FCA5A5' : '#E2E8F0',
              borderRadius: 12,
              backgroundColor: usernameFocused ? '#F8FAFF' : '#F8FAFC',
              marginBottom: 18,
              flexDirection: 'row',
              alignItems: 'center',
              paddingHorizontal: 14,
            }}>
              <Text style={{ fontSize: 16, marginRight: 8 }}>👤</Text>
              <TextInput
                value={username}
                onChangeText={(text) => { setUsername(text); if (error) setError(''); }}
                onFocus={() => setUsernameFocused(true)}
                onBlur={() => setUsernameFocused(false)}
                placeholder="Enter your username"
                placeholderTextColor="#CBD5E1"
                autoCapitalize="none"
                autoCorrect={false}
                editable={!loading}
                style={{
                  flex: 1,
                  paddingVertical: 13,
                  fontSize: 15,
                  color: '#1E293B',
                }}
              />
            </View>

            {/* Password field */}
            <Text style={{
              fontSize: 12, fontWeight: '700',
              color: '#475569', marginBottom: 6,
              textTransform: 'uppercase', letterSpacing: 0.8,
            }}>
              Password
            </Text>
            <View style={{
              borderWidth: 1.5,
              borderColor: passwordFocused ? '#0038A8' : error ? '#FCA5A5' : '#E2E8F0',
              borderRadius: 12,
              backgroundColor: passwordFocused ? '#F8FAFF' : '#F8FAFC',
              marginBottom: 24,
              flexDirection: 'row',
              alignItems: 'center',
              paddingHorizontal: 14,
            }}>
              <Text style={{ fontSize: 16, marginRight: 8 }}>🔒</Text>
              <TextInput
                value={password}
                onChangeText={(text) => { setPassword(text); if (error) setError(''); }}
                onFocus={() => setPasswordFocused(true)}
                onBlur={() => setPasswordFocused(false)}
                placeholder="Enter your password"
                placeholderTextColor="#CBD5E1"
                secureTextEntry={!showPassword}
                editable={!loading}
                style={{
                  flex: 1,
                  paddingVertical: 13,
                  fontSize: 15,
                  color: '#1E293B',
                }}
              />
              <TouchableOpacity
                onPress={() => setShowPassword(!showPassword)}
                hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
              >
                <Text style={{ fontSize: 18 }}>{showPassword ? '🙈' : '👁️'}</Text>
              </TouchableOpacity>
            </View>

            {/* Sign In button */}
            <TouchableOpacity
              onPress={handleLogin}
              disabled={loading}
              activeOpacity={0.85}
              style={{
                backgroundColor: loading ? '#93C5FD' : '#0038A8',
                borderRadius: 12,
                paddingVertical: 15,
                alignItems: 'center',
                shadowColor: '#0038A8',
                shadowOffset: { width: 0, height: 4 },
                shadowOpacity: loading ? 0 : 0.3,
                shadowRadius: 8,
                elevation: loading ? 0 : 4,
              }}
            >
              {loading ? (
                <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                  <ActivityIndicator color="#fff" size="small" />
                  <Text style={{
                    color: '#fff', fontSize: 16,
                    fontWeight: '700', marginLeft: 10,
                  }}>
                    Signing in...
                  </Text>
                </View>
              ) : (
                <Text style={{
                  color: '#fff', fontSize: 16,
                  fontWeight: '700', letterSpacing: 0.3,
                }}>
                  🔑 Sign In & Continue
                </Text>
              )}
            </TouchableOpacity>
          </View>

          {/* Footer links */}
          <View style={{
            flexDirection: 'row',
            justifyContent: 'center',
            marginTop: 28,
            gap: 24,
          }}>
            <TouchableOpacity>
              <Text style={{ color: '#0038A8', fontSize: 13, fontWeight: '600' }}>
                🔐 Staff Login
              </Text>
            </TouchableOpacity>
            <Text style={{ color: '#CBD5E1', fontSize: 13 }}>|</Text>
            <TouchableOpacity>
              <Text style={{ color: '#0038A8', fontSize: 13, fontWeight: '600' }}>
                👁 Dashboard
              </Text>
            </TouchableOpacity>
          </View>

          <Text style={{
            textAlign: 'center', color: '#94A3B8',
            fontSize: 11, marginTop: 24, letterSpacing: 0.3,
          }}>
            DepEd Division of Leyte — Personnel Unit
          </Text>

        </Animated.View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}