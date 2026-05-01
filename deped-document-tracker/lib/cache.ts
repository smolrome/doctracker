import AsyncStorage from '@react-native-async-storage/async-storage';
import * as FileSystem from 'expo-file-system';

const CACHE_KEYS = {
  DOCUMENTS: 'cache:documents',
  STATS: 'cache:stats',
  OFFICES: 'cache:offices',
  LAST_SYNC: 'cache:last_sync',
  USER_ID: 'cache:user_id',
};

// Keys whose data is too large for AsyncStorage (SQLite 6MB limit).
// These are stored as JSON files on the filesystem instead.
const FILE_BASED_KEYS = new Set([CACHE_KEYS.DOCUMENTS]);

const CACHE_DIR = `${FileSystem.documentDirectory}cache/`;
const CACHE_EXPIRY_MS = 1000 * 60 * 30; // 30 minutes

function filePathForKey(key: string): string {
  const safe = key.replace(/[^a-zA-Z0-9_-]/g, '_');
  return `${CACHE_DIR}${safe}.json`;
}

async function ensureCacheDir() {
  const info = await FileSystem.getInfoAsync(CACHE_DIR);
  if (!info.exists) {
    await FileSystem.makeDirectoryAsync(CACHE_DIR, { intermediates: true });
  }
}

export const cache = {
  async set(key: string, data: any) {
    try {
      const payload = { data, timestamp: Date.now() };

      if (FILE_BASED_KEYS.has(key)) {
        await ensureCacheDir();
        await FileSystem.writeAsStringAsync(
          filePathForKey(key),
          JSON.stringify(payload)
        );
      } else {
        await AsyncStorage.setItem(key, JSON.stringify(payload));
      }
    } catch (err) {
      console.warn('Cache set failed:', err);
    }
  },

  async get(key: string): Promise<any | null> {
    try {
      let raw: string | null = null;

      if (FILE_BASED_KEYS.has(key)) {
        const path = filePathForKey(key);
        const info = await FileSystem.getInfoAsync(path);
        if (!info.exists) return null;
        raw = await FileSystem.readAsStringAsync(path);
      } else {
        raw = await AsyncStorage.getItem(key);
      }

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
      let raw: string | null = null;

      if (FILE_BASED_KEYS.has(key)) {
        const path = filePathForKey(key);
        const info = await FileSystem.getInfoAsync(path);
        if (!info.exists) return null;
        raw = await FileSystem.readAsStringAsync(path);
      } else {
        raw = await AsyncStorage.getItem(key);
      }

      if (!raw) return null;
      const payload = JSON.parse(raw);
      return payload.data;
    } catch {
      return null;
    }
  },

  async clear(key: string) {
    try {
      if (FILE_BASED_KEYS.has(key)) {
        const path = filePathForKey(key);
        const info = await FileSystem.getInfoAsync(path);
        if (info.exists) await FileSystem.deleteAsync(path);
      } else {
        await AsyncStorage.removeItem(key);
      }
    } catch (err) {
      console.warn('Cache clear failed:', err);
    }
  },

  async clearAll() {
    try {
      // Clear AsyncStorage keys
      const asyncKeys = Object.values(CACHE_KEYS).filter(
        (k) => !FILE_BASED_KEYS.has(k)
      );
      await AsyncStorage.multiRemove(asyncKeys);

      // Clear file-based cache directory
      const info = await FileSystem.getInfoAsync(CACHE_DIR);
      if (info.exists) {
        await FileSystem.deleteAsync(CACHE_DIR, { idempotent: true });
      }
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
