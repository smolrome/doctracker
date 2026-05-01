import * as SecureStore from 'expo-secure-store';

const ACCESS_TOKEN_KEY  = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const USER_KEY          = 'user_data';

// Biometric credential keys — stored in SecureStore (OS-encrypted keychain)
const BIO_ENABLED_KEY  = 'biometric_enabled';   // 'true' | absent
const BIO_USERNAME_KEY = 'biometric_username';
const BIO_PASSWORD_KEY = 'biometric_password';  // stored with biometric protection

export const authStorage = {
  // ── Token / user session ────────────────────────────────────────────────────

  async saveTokens(access: string, refresh: string) {
    await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, access);
    await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refresh);
  },

  async getAccessToken(): Promise<string | null> {
    return await SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
  },

  async getRefreshToken(): Promise<string | null> {
    return await SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
  },

  async saveUser(user: object) {
    await SecureStore.setItemAsync(USER_KEY, JSON.stringify(user));
  },

  async getUser() {
    const raw = await SecureStore.getItemAsync(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  },

  async clearAll() {
    await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
    await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
    await SecureStore.deleteItemAsync(USER_KEY);
    // Do NOT clear biometric credentials on logout so the user can still
    // use their fingerprint to log back in on the next session.
  },

  // ── Biometric credentials ───────────────────────────────────────────────────

  /** Save username + password so biometric unlock can re-authenticate. */
  async saveBiometricCredentials(username: string, password: string) {
    await SecureStore.setItemAsync(BIO_USERNAME_KEY, username);
    await SecureStore.setItemAsync(BIO_PASSWORD_KEY, password);
    await SecureStore.setItemAsync(BIO_ENABLED_KEY, 'true');
  },

  async getBiometricCredentials(): Promise<{ username: string; password: string } | null> {
    const enabled  = await SecureStore.getItemAsync(BIO_ENABLED_KEY);
    if (enabled !== 'true') return null;
    const username = await SecureStore.getItemAsync(BIO_USERNAME_KEY);
    const password = await SecureStore.getItemAsync(BIO_PASSWORD_KEY);
    if (!username || !password) return null;
    return { username, password };
  },

  async isBiometricEnabled(): Promise<boolean> {
    const val = await SecureStore.getItemAsync(BIO_ENABLED_KEY);
    return val === 'true';
  },

  /** Disable biometric login and wipe saved credentials. */
  async clearBiometricCredentials() {
    await SecureStore.deleteItemAsync(BIO_ENABLED_KEY);
    await SecureStore.deleteItemAsync(BIO_USERNAME_KEY);
    await SecureStore.deleteItemAsync(BIO_PASSWORD_KEY);
  },
};

export default authStorage;