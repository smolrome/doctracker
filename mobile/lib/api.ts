import axios from 'axios';
import { router } from 'expo-router';
import { authStorage } from './auth';

export const BASE_URL = 'https://doctracker.depedleytepersonnelunit.com';
console.log('API connecting to:', BASE_URL);

const api = axios.create({
  baseURL: `${BASE_URL}/api`,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use(async (config) => {
  const token = await authStorage.getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status;
    // Only log unexpected errors — 404s on optional endpoints are handled by each hook
    if (status !== 404 && status !== 401 && status !== 429 && status !== 422) {
      console.log('API ERROR:', error.message, error.config?.url);
    }
    const original = error.config;

    // ── 429 Too Many Requests: back off and retry (max 3 times) ─────────────
    if (status === 429) {
      const retries = original._429retries ?? 0;
      if (retries < 3) {
        original._429retries = retries + 1;
        // Honour the server's Retry-After header when present; otherwise
        // use exponential back-off: 3 s → 6 s → 12 s
        const retryAfterHeader = error.response?.headers?.['retry-after'];
        const delay = retryAfterHeader
          ? parseInt(retryAfterHeader, 10) * 1000
          : 3000 * Math.pow(2, retries); // 3 s, 6 s, 12 s
        console.warn(
          `[API] 429 on ${original.url} — waiting ${delay / 1000}s before retry ${original._429retries}/3`
        );
        await new Promise((r) => setTimeout(r, delay));
        return api(original);
      }
      // Exhausted retries — log and reject so the hook falls back to cache
      console.warn(`[API] 429 on ${original.url} — all retries exhausted`);
      return Promise.reject(error);
    }

    // ── 422 Unprocessable: token is malformed — clear and force re-login ────
    if (error.response?.status === 422) {
      await authStorage.clearAll();
      router.replace('/(auth)/login');
      return Promise.reject(error);
    }

    // ── 401 Unauthorized: refresh token then retry once ──────────────────────
    if (status === 401 && !original._retry) {
      original._retry = true;
      try {
        const refresh = await authStorage.getRefreshToken();
        const res = await axios.post(`${BASE_URL}/api/auth/refresh`, {}, {
          headers: { Authorization: `Bearer ${refresh}` }
        });
        const newToken = res.data.access_token;
        await authStorage.saveTokens(newToken, refresh!);
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch {
        await authStorage.clearAll();
      }
    }

    return Promise.reject(error);
  }
);

export default api;