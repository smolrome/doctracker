import { create } from 'zustand';
import { User } from '../types';
import { authStorage } from './auth';
import api from './api';
import { cache } from './cache';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  setUser: (user: User) => void;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  loadFromStorage: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,

  setUser: (user) => set({ user, isAuthenticated: true, isLoading: false }),

  login: async (username: string, password: string) => {
    await cache.clearAll();
    const response = await api.post('/auth/login', { username, password });
    const { access_token, refresh_token, user } = response.data;
    await authStorage.saveTokens(access_token, refresh_token);
    await authStorage.saveUser(user);
    await cache.set(cache.KEYS.USER_ID, user.id || user.username);
    set({ user, isAuthenticated: true, isLoading: false });
  },

  logout: async () => {
    await authStorage.clearAll();
    await cache.clearAll();
    set({ user: null, isAuthenticated: false });
  },

  loadFromStorage: async () => {
    const user = await authStorage.getUser();
    const token = await authStorage.getAccessToken();
    if (user && token) {
      set({ user, isAuthenticated: true, isLoading: false });
    } else {
      set({ isLoading: false });
    }
  },
}));