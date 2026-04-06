import AsyncStorage from '@react-native-async-storage/async-storage';

const CACHE_KEYS = {
  DOCUMENTS: 'cache:documents',
  STATS: 'cache:stats',
  OFFICES: 'cache:offices',
  LAST_SYNC: 'cache:last_sync',
};

const CACHE_EXPIRY_MS = 1000 * 60 * 30; // 30 minutes

export const cache = {
  async set(key: string, data: any) {
    try {
      const payload = {
        data,
        timestamp: Date.now(),
      };
      await AsyncStorage.setItem(key, JSON.stringify(payload));
    } catch (err) {
      console.warn('Cache set failed:', err);
    }
  },

  async get(key: string): Promise<any | null> {
    try {
      const raw = await AsyncStorage.getItem(key);
      if (!raw) return null;

      const payload = JSON.parse(raw);
      const age = Date.now() - payload.timestamp;

      if (age > CACHE_EXPIRY_MS) return null;

      return payload.data;
    } catch (err) {
      console.warn('Cache get failed:', err);
      return null;
    }
  },

  async getStale(key: string): Promise<any | null> {
    try {
      const raw = await AsyncStorage.getItem(key);
      if (!raw) return null;
      const payload = JSON.parse(raw);
      return payload.data;
    } catch {
      return null;
    }
  },

  async clear(key: string) {
    try {
      await AsyncStorage.removeItem(key);
    } catch (err) {
      console.warn('Cache clear failed:', err);
    }
  },

  async clearAll() {
    try {
      const keys = Object.values(CACHE_KEYS);
      await AsyncStorage.multiRemove(keys);
    } catch (err) {
      console.warn('Cache clearAll failed:', err);
    }
  },

  async getLastSync(): Promise<string | null> {
    try {
      return await AsyncStorage.getItem(CACHE_KEYS.LAST_SYNC);
    } catch {
      return null;
    }
  },

  async updateLastSync() {
    try {
      await AsyncStorage.setItem(
        CACHE_KEYS.LAST_SYNC,
        new Date().toISOString()
      );
    } catch {
      // ignore
    }
  },

  KEYS: CACHE_KEYS,
};