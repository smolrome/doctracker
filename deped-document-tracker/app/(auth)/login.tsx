import { useState, useCallback } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
} from 'react-native';
import { useRouter } from 'expo-router';
import api, { BASE_URL } from '../../lib/api';
import { authStorage } from '../../lib/auth';
import { useAuthStore } from '../../lib/store';

interface ApiError {
  response?: {
    data?: {
      error?: string;
    };
    status?: number;
  };
  request?: {
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

  const parseError = (err: ApiError): string => {
    if (err.response) {
      const status = err.response.status;
      const serverMsg = err.response.data?.error;
      
      if (status === 401) {
        return 'Invalid username or password';
      }
      if (status === 403) {
        return 'Account is locked or inactive';
      }
      if (status === 404) {
        return 'Server not found. Please try again later';
      }
      if (status === 500) {
        return 'Server error. Please try again later';
      }
      if (serverMsg) {
        return serverMsg;
      }
    }
    
    if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
      return 'Request timed out. Please check your connection';
    }
    if (err.message?.includes('Network request failed') || !err.response) {
      return 'Unable to connect. Please check your internet';
    }
    
    return 'Login failed. Please try again';
  };

  const dismissError = useCallback(() => {
    setError('');
  }, []);

  const handleLogin = async () => {
    const trimmedUsername = username.trim();
    const trimmedPassword = password.trim();
    
    if (!trimmedUsername || !trimmedPassword) {
      setError('Please enter username and password');
      return;
    }

    if (trimmedUsername.length < 3) {
      setError('Username must be at least 3 characters');
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
      setError(parseError(err));
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
            <TouchableOpacity 
              onPress={dismissError}
              activeOpacity={0.7}
              style={{
                backgroundColor: '#FEE2E2',
                borderRadius: 8,
                padding: 12,
                marginBottom: 16,
                borderWidth: 1,
                borderColor: '#FECACA',
              }}
            >
              <Text style={{ color: '#DC2626', fontSize: 13 }}>
                {error}
              </Text>
              <Text style={{ color: '#991B1B', fontSize: 11, marginTop: 4 }}>
                Tap to dismiss
              </Text>
            </TouchableOpacity>
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
            onChangeText={(text) => {
              setUsername(text);
              if (error) setError('');
            }}
            placeholder="Enter your username"
            placeholderTextColor="#9CA3AF"
            autoCapitalize="none"
            autoCorrect={false}
            editable={!loading}
            style={{
              borderWidth: 1,
              borderColor: error ? '#EF4444' : '#D1D5DB',
              borderRadius: 10,
              paddingHorizontal: 14,
              paddingVertical: 12,
              fontSize: 15,
              color: '#111',
              backgroundColor: loading ? '#E5E7EB' : '#F9FAFB',
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
            onChangeText={(text) => {
              setPassword(text);
              if (error) setError('');
            }}
            placeholder="Enter your password"
            placeholderTextColor="#9CA3AF"
            secureTextEntry
            editable={!loading}
            style={{
              borderWidth: 1,
              borderColor: error ? '#EF4444' : '#D1D5DB',
              borderRadius: 10,
              paddingHorizontal: 14,
              paddingVertical: 12,
              fontSize: 15,
              color: '#111',
              backgroundColor: loading ? '#E5E7EB' : '#F9FAFB',
              marginBottom: 24,
            }}
          />

          <TouchableOpacity
            onPress={handleLogin}
            disabled={loading}
            activeOpacity={0.8}
            style={{
              backgroundColor: loading ? '#93C5FD' : '#0038A8',
              borderRadius: 10,
              paddingVertical: 14,
              alignItems: 'center',
            }}
          >
            {loading ? (
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <ActivityIndicator color="#fff" size="small" />
                <Text style={{
                  color: '#fff',
                  fontSize: 16,
                  fontWeight: '600',
                  marginLeft: 8,
                }}>
                  Signing in...
                </Text>
              </View>
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