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
  Image,
  // FIX 1: useWindowDimensions updates on rotation; Dimensions.get is static
  useWindowDimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import { User, Lock, Eye, EyeOff, LogIn, Fingerprint, AlertCircle } from 'lucide-react-native';
import api from '../../lib/api';
import { authStorage } from '../../lib/auth';
import { useAuthStore } from '../../lib/store';

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
  // FIX 1: Dynamic dimensions — updates on orientation change
  const { width, height } = useWindowDimensions();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [usernameFocused, setUsernameFocused] = useState(false);
  const [passwordFocused, setPasswordFocused] = useState(false);
  // FIX 2: Track logo load failure for initials fallback
  const [logoError, setLogoError] = useState(false);

  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(30)).current;
  const logoScale = useRef(new Animated.Value(0.85)).current;
  const shakeAnim = useRef(new Animated.Value(0)).current;
  const errorFade = useRef(new Animated.Value(0)).current;
  const accentScale1 = useRef(new Animated.Value(1)).current;
  const accentScale2 = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, { toValue: 1, duration: 600, useNativeDriver: true }),
      Animated.spring(slideAnim, { toValue: 0, tension: 65, friction: 11, useNativeDriver: true }),
      Animated.spring(logoScale, { toValue: 1, tension: 50, friction: 8, useNativeDriver: true }),
    ]).start();

    Animated.loop(
      Animated.sequence([
        Animated.timing(accentScale1, { toValue: 1.12, duration: 4000, useNativeDriver: true }),
        Animated.timing(accentScale1, { toValue: 1, duration: 4000, useNativeDriver: true }),
      ])
    ).start();
    Animated.loop(
      Animated.sequence([
        Animated.timing(accentScale2, { toValue: 1.08, duration: 5000, useNativeDriver: true }),
        Animated.timing(accentScale2, { toValue: 1, duration: 5000, useNativeDriver: true }),
      ])
    ).start();
  }, []);

  const shakeError = () => {
    Animated.sequence([
      Animated.timing(shakeAnim, { toValue: 10, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -10, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 8, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -8, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 0, duration: 60, useNativeDriver: true }),
    ]).start();
    Animated.timing(errorFade, { toValue: 1, duration: 300, useNativeDriver: true }).start();
  };

  const dismissError = useCallback(() => {
    Animated.timing(errorFade, { toValue: 0, duration: 200, useNativeDriver: true })
      .start(() => setError(''));
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
    if (!err.response) return 'Unable to connect. Check your internet';
    return 'Login failed. Please try again';
  };

  const handleLogin = async () => {
    // FIX 3: Only trim username — never trim password (spaces may be intentional)
    const trimmedUsername = username.trim();

    if (!trimmedUsername || !password) {
      setError('Please enter username and password');
      shakeError();
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await api.post('/auth/login', {
        username: trimmedUsername,
        password, // raw, untrimmed
      });

      const { access_token, refresh_token, user } = response.data;
      await authStorage.saveTokens(access_token, refresh_token);
      await authStorage.saveUser(user);
      setUser(user);
      // Route based on role: clients go to client portal, staff/admin to dashboard
      if (user?.role === 'client') {
        router.replace('/(client)/my-docs');
      } else {
        router.replace('/(app)/dashboard');
      }
    } catch (err) {
      // FIX 6: Use the typed ApiError cast instead of `any`
      const msg = parseError(err as ApiError);
      setError(msg);
      shakeError();
    } finally {
      setLoading(false);
    }
  };

  const HERO_HEIGHT = height * 0.42;

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: '#0038A8' }}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <StatusBar barStyle="light-content" backgroundColor="#0038A8" />

      {/* Hero zone */}
      <View style={{ height: HERO_HEIGHT, backgroundColor: '#0038A8', overflow: 'hidden' }}>
        <Animated.View style={{
          position: 'absolute', top: -48, right: -48,
          width: 200, height: 200, borderRadius: 100,
          backgroundColor: '#FCD116', opacity: 0.10,
          transform: [{ scale: accentScale1 }],
        }} />
        <Animated.View style={{
          position: 'absolute', bottom: 0, left: -40,
          width: 160, height: 160, borderRadius: 80,
          backgroundColor: '#CE1126', opacity: 0.10,
          transform: [{ scale: accentScale2 }],
        }} />
        {[...Array(5)].map((_, i) => (
          <View key={`h${i}`} style={{
            position: 'absolute', top: (i + 1) * (HERO_HEIGHT / 6),
            left: 0, right: 0, height: 1,
            backgroundColor: '#fff', opacity: 0.05,
          }} />
        ))}
        {[...Array(5)].map((_, i) => (
          <View key={`v${i}`} style={{
            position: 'absolute', left: (i + 1) * (width / 6),
            top: 0, bottom: 0, width: 1,
            backgroundColor: '#fff', opacity: 0.05,
          }} />
        ))}

        <Animated.View style={{
          flex: 1, alignItems: 'center', justifyContent: 'center',
          opacity: fadeAnim,
          transform: [{ scale: logoScale }],
        }}>
          <View style={{
            width: 108, height: 108, borderRadius: 54,
            backgroundColor: 'rgba(255,255,255,0.12)',
            alignItems: 'center', justifyContent: 'center',
            marginBottom: 14,
          }}>
            <View style={{
              width: 108, height: 108, borderRadius: 54,
              backgroundColor: '#fff',
              alignItems: 'center', justifyContent: 'center',
              overflow: 'hidden',
            }}>
              {logoError ? (
                <Text style={{ fontSize: 28, fontWeight: '700', color: '#0038A8' }}>DL</Text>
              ) : (
                <Image
                  source={require('../../assets/wow.png')}
                  style={{ width: 108, height: 108, resizeMode: 'cover' }}
                  onError={() => setLogoError(true)}
                />
              )}
            </View>
          </View>

          <Text style={{
            fontSize: 26, fontWeight: '900', color: '#fff',
            letterSpacing: -0.5, textAlign: 'center',
          }}>
            DepEd Leyte
          </Text>
          <Text style={{
            fontSize: 12.5, color: 'rgba(255,255,255,0.72)',
            marginTop: 5, textAlign: 'center', letterSpacing: 0.3,
          }}>
            Document Tracker — Personnel Unit
          </Text>
        </Animated.View>
      </View>

      {/* Form zone */}
      <Animated.View style={{
        flex: 1,
        backgroundColor: '#F8FAFC',
        borderTopLeftRadius: 24,
        borderTopRightRadius: 24,
        marginTop: -20,
        opacity: fadeAnim,
        transform: [{ translateY: slideAnim }],
      }}>
        <ScrollView
          contentContainerStyle={{ paddingHorizontal: 24, paddingTop: 28, paddingBottom: 40 }}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <Text style={{ fontSize: 20, fontWeight: '800', color: '#1E293B', marginBottom: 4 }}>
            Welcome back
          </Text>
          <Text style={{ fontSize: 13, color: '#94A3B8', marginBottom: 24 }}>
            Sign in to your Personnel Unit account.
          </Text>

          {error ? (
            <Animated.View style={{ opacity: errorFade, transform: [{ translateX: shakeAnim }] }}>
              <TouchableOpacity
                onPress={dismissError}
                activeOpacity={0.8}
                style={{
                  backgroundColor: '#FEF2F2', borderRadius: 10, padding: 12,
                  marginBottom: 20, borderWidth: 1, borderColor: '#FECACA',
                  flexDirection: 'row', alignItems: 'flex-start',
                }}
              >
                <View style={{ marginRight: 8 }}>
                  <AlertCircle color="#DC2626" size={18} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: '#DC2626', fontSize: 13, fontWeight: '600' }}>{error}</Text>
                  <Text style={{ color: '#EF4444', fontSize: 11, marginTop: 2 }}>Tap to dismiss</Text>
                </View>
              </TouchableOpacity>
            </Animated.View>
          ) : null}

          {/* FIX 5: Both labels now use the same color — #475569 */}
          <Text style={{
            fontSize: 11, fontWeight: '700', color: '#475569',
            marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.8,
          }}>
            Username
          </Text>
          <View style={{
            borderWidth: 1.5,
            borderColor: usernameFocused ? '#0038A8' : error ? '#FCA5A5' : '#E2E8F0',
            borderRadius: 12,
            backgroundColor: '#fff',
            marginBottom: 18,
            flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14,
          }}>
            <User color={usernameFocused ? '#0038A8' : '#94A3B8'} size={18} style={{ marginRight: 10 }} />
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
              style={{ flex: 1, paddingVertical: 13, fontSize: 15, color: '#1E293B' }}
            />
          </View>

          <Text style={{
            fontSize: 11, fontWeight: '700', color: '#475569',
            marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.8,
          }}>
            Password
          </Text>
          <View style={{
            borderWidth: 1.5,
            borderColor: passwordFocused ? '#0038A8' : error ? '#FCA5A5' : '#E2E8F0',
            borderRadius: 12,
            backgroundColor: '#fff',
            marginBottom: 28,
            flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14,
          }}>
            <Lock color={passwordFocused ? '#0038A8' : '#94A3B8'} size={18} style={{ marginRight: 10 }} />
            <TextInput
              value={password}
              onChangeText={(text) => { setPassword(text); if (error) setError(''); }}
              onFocus={() => setPasswordFocused(true)}
              onBlur={() => setPasswordFocused(false)}
              placeholder="Enter your password"
              placeholderTextColor="#CBD5E1"
              secureTextEntry={!showPassword}
              editable={!loading}
              style={{ flex: 1, paddingVertical: 13, fontSize: 15, color: '#1E293B' }}
            />
            <TouchableOpacity
              onPress={() => setShowPassword(!showPassword)}
              hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
            >
              {showPassword
                ? <EyeOff color="#94A3B8" size={18} />
                : <Eye color="#94A3B8" size={18} />}
            </TouchableOpacity>
          </View>

          <TouchableOpacity
            onPress={handleLogin}
            disabled={loading}
            activeOpacity={0.85}
            style={{
              backgroundColor: loading ? '#93C5FD' : '#0038A8',
              borderRadius: 13,
              paddingVertical: 15,
              alignItems: 'center',
              marginBottom: 20,
            }}
          >
            {loading ? (
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <ActivityIndicator color="#fff" size="small" />
                <Text style={{ color: '#fff', fontSize: 16, fontWeight: '700', marginLeft: 10 }}>
                  Signing in...
                </Text>
              </View>
            ) : (
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <LogIn color="#fff" size={19} />
                <Text style={{ color: '#fff', fontSize: 15, fontWeight: '700', marginLeft: 10, letterSpacing: 0.3 }}>
                  Sign In & Continue
                </Text>
              </View>
            )}
          </TouchableOpacity>

          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16 }}>
            <View style={{ flex: 1, height: 1, backgroundColor: '#E2E8F0' }} />
            <Text style={{ color: '#CBD5E1', fontSize: 12, marginHorizontal: 12 }}>or</Text>
            <View style={{ flex: 1, height: 1, backgroundColor: '#E2E8F0' }} />
          </View>

          {/* Register as Client */}
          <TouchableOpacity
            onPress={() => router.push('/(auth)/register')}
            activeOpacity={0.8}
            style={{
              borderWidth: 1.5,
              borderColor: '#BFDBFE',
              borderRadius: 13,
              paddingVertical: 13,
              alignItems: 'center',
              flexDirection: 'row',
              justifyContent: 'center',
              backgroundColor: '#EFF6FF',
              marginBottom: 32,
            }}
          >
            <Fingerprint color="#0038A8" size={18} />
            <Text style={{ color: '#0038A8', fontSize: 15, fontWeight: '700', marginLeft: 8 }}>
              Register as Client
            </Text>
          </TouchableOpacity>

          <Text style={{
            textAlign: 'center', color: '#94A3B8',
            fontSize: 11, marginBottom: 10, letterSpacing: 0.3,
          }}>
            DepEd Division of Leyte — Personnel Unit
          </Text>

          <View style={{ flexDirection: 'row', justifyContent: 'center' }}>
            <View style={{ width: 20, height: 3, backgroundColor: '#0038A8', borderRadius: 1 }} />
            <View style={{ width: 20, height: 3, backgroundColor: '#CE1126' }} />
            <View style={{ width: 20, height: 3, backgroundColor: '#FCD116', borderRadius: 1 }} />
          </View>

        </ScrollView>
      </Animated.View>
    </KeyboardAvoidingView>
  );
}
