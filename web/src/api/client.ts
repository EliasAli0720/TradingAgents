import axios, { AxiosError } from 'axios';
import { readCsrfToken } from './csrf';

const BASE = import.meta.env.VITE_API_BASE ?? '/api';

export const http = axios.create({
  baseURL: BASE,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

http.interceptors.request.use((config) => {
  const method = (config.method ?? 'get').toLowerCase();
  if (['post', 'put', 'patch', 'delete'].includes(method)) {
    const csrf = readCsrfToken();
    if (csrf) config.headers.set('X-CSRF-Token', csrf);
  }
  return config;
});

export type ApiError = {
  status: number;
  detail: string;
};

http.interceptors.response.use(
  (r) => r,
  (err: AxiosError<{ detail?: string }>) => {
    const status = err.response?.status ?? 0;
    const detail =
      (typeof err.response?.data?.detail === 'string' && err.response.data.detail) ||
      err.message ||
      'request failed';
    if (status === 401 && !location.pathname.startsWith('/login')) {
      const next = encodeURIComponent(location.pathname + location.search);
      location.replace(`/login?next=${next}`);
    }
    return Promise.reject({ status, detail } satisfies ApiError);
  },
);

export function apiUrl(path: string): string {
  return `${BASE}${path}`;
}

export function sseUrl(path: string): string {
  return apiUrl(path);
}
