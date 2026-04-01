import { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Alert
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../../lib/api';
import { authStorage } from '../../lib/auth';
import { useAuthStore } from '../../lib/store';

export default function Login() {
  const router = useRouter();
  const setUser = useAuthStore((s) => s.setUser);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async () => {
    if (!username.trim() || !password.trim()) {
      setError('Please enter username and password');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await api.post('/auth/login', {
        username,
        password,
      });

      const { access_token, refresh_token, user } = response.data;

      await authStorage.saveTokens(access_token, refresh_token);
      await authStorage.saveUser(user);

      setUser(user);

      router.replace('/(app)/dashboard');

    } catch (err: any) {
      const msg = err.response?.data?.error || 'Login failed. Check your connection.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={{ flexGrow: 1 }}
        keyboardShouldPersistTaps="handled"
      >
        <View style={{
          flex: 1,
          backgroundColor: '#fff',
          paddingHorizontal: 28,
          justifyContent: 'center',
        }}>

          <View style={{ alignItems: 'center', marginBottom: 48 }}>
            <View style={{
              width: 72,
              height: 72,
              borderRadius: 36,
              backgroundColor: '#0038A8',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: 16,
            }}>
              <Text style={{ fontSize: 28 }}>📄</Text>
            </View>
            <Text style={{
              fontSize: 22,
              fontWeight: 'bold',
              color: '#0038A8',
              textAlign: 'center',
            }}>
              DepEd Leyte
            </Text>
            <Text style={{
              fontSize: 14,
              color: '#666',
              marginTop: 4,
              textAlign: 'center',
            }}>
              Document Tracker — Personnel Unit
            </Text>
          </View>

          {error ? (
            <View style={{
              backgroundColor: '#FEE2E2',
              borderRadius: 8,
              padding: 12,
              marginBottom: 16,
            }}>
              <Text style={{ color: '#DC2626', fontSize: 13 }}>
                {error}
              </Text>
            </View>
          ) : null}

          <Text style={{
            fontSize: 13,
            fontWeight: '600',
            color: '#374151',
            marginBottom: 6,
          }}>
            Username
          </Text>
          <TextInput
            value={username}
            onChangeText={setUsername}
            placeholder="Enter your username"
            placeholderTextColor="#9CA3AF"
            autoCapitalize="none"
            autoCorrect={false}
            style={{
              borderWidth: 1,
              borderColor: '#D1D5DB',
              borderRadius: 10,
              paddingHorizontal: 14,
              paddingVertical: 12,
              fontSize: 15,
              color: '#111',
              backgroundColor: '#F9FAFB',
              marginBottom: 16,
            }}
          />

          <Text style={{
            fontSize: 13,
            fontWeight: '600',
            color: '#374151',
            marginBottom: 6,
          }}>
            Password
          </Text>
          <TextInput
            value={password}
            onChangeText={setPassword}
            placeholder="Enter your password"
            placeholderTextColor="#9CA3AF"
            secureTextEntry
            style={{
              borderWidth: 1,
              borderColor: '#D1D5DB',
              borderRadius: 10,
              paddingHorizontal: 14,
              paddingVertical: 12,
              fontSize: 15,
              color: '#111',
              backgroundColor: '#F9FAFB',
              marginBottom: 24,
            }}
          />

          <TouchableOpacity
            onPress={handleLogin}
            disabled={loading}
            style={{
              backgroundColor: loading ? '#93C5FD' : '#0038A8',
              borderRadius: 10,
              paddingVertical: 14,
              alignItems: 'center',
            }}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={{
                color: '#fff',
                fontSize: 16,
                fontWeight: '600',
              }}>
                Sign In
              </Text>
            )}
          </TouchableOpacity>

          <Text style={{
            textAlign: 'center',
            color: '#9CA3AF',
            fontSize: 12,
            marginTop: 32,
          }}>
            DepEd Division of Leyte — Personnel Unit
          </Text>

        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}