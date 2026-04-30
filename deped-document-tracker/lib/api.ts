import axios from 'axios';
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
    if (status !== 404 && status !== 401) {
      console.log('API ERROR:', error.message, error.config?.url);
    }
    const original = error.config;

    if (error.response?.status === 401 && !original._retry) {
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