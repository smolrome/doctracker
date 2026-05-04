import api from './config';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { User, LoginResponse } from '../types';

export const authService = {
  async login(username: string, password: string): Promise<LoginResponse> {
    const response = await api.post<LoginResponse>('/auth/login', {
      username,
      password,
    });
    
    await AsyncStorage.setItem('access_token', response.data.access_token);
    await AsyncStorage.setItem('refresh_token', response.data.refresh_token);
    await AsyncStorage.setItem('user', JSON.stringify(response.data.user));
    
    return response.data;
  },

  async refreshToken(): Promise<{ access_token: string }> {
    const refreshToken = await AsyncStorage.getItem('refresh_token');
    if (!refreshToken) {
      throw new Error('No refresh token available');
    }

    const response = await api.post<{ access_token: string }>('/auth/refresh', {}, {
      headers: {
        Authorization: `Bearer ${refreshToken}`,
      },
    });

    await AsyncStorage.setItem('access_token', response.data.access_token);
    return response.data;
  },

  async getCurrentUser(): Promise<User | null> {
    try {
      const userJson = await AsyncStorage.getItem('user');
      return userJson ? JSON.parse(userJson) : null;
    } catch {
      return null;
    }
  },

  async logout(): Promise<void> {
    await AsyncStorage.multiRemove(['access_token', 'refresh_token', 'user']);
  },

  async isLoggedIn(): Promise<boolean> {
    const token = await AsyncStorage.getItem('access_token');
    return !!token;
  },
};

export default authService;