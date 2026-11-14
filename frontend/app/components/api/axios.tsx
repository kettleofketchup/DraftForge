import { Sentry } from '~/lib/sentry';
import axios from 'axios';

import { CSRF_COOKIE_NAME_HEADER, getCsrfToken, syncCsrfCookieName } from './utils';

// Determine the API base URL based on environment
// On server (SSR): use internal URL (configurable via SSR_API_URL env var)
// On client: use relative /api path (proxied by nginx)
const getBaseURL = () => {
  // Check if we're on the server (no window object)
  if (typeof window === 'undefined') {
    // Server-side: use internal backend URL
    // Configure via SSR_API_URL env var for different deployments:
    //   - Docker Compose: http://backend:8000/api (default)
    //   - Kubernetes: http://backend-service:8000/api
    //   - Local dev: http://localhost:8000/api
    const ssrUrl = process.env.SSR_API_URL || 'http://backend:8000/api';
    return ssrUrl;
  }
  // Client-side: use relative path (handled by nginx proxy)
  return '/api';
};

export const api = axios.create({
  baseURL: getBaseURL(),
  withCredentials: true, // send cookies like sessionid
});

api.interceptors.request.use((config) => {
  const method = config.method?.toUpperCase();
  const needsCSRF = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method || '');

  if (needsCSRF) {
    config.headers['X-CSRFToken'] = getCsrfToken();
  }

  return config;
});

const isBrowser = typeof window !== 'undefined';

api.interceptors.response.use((response) => {
  if (isBrowser) syncCsrfCookieName(response.headers?.[CSRF_COOKIE_NAME_HEADER]);
  return response;
}, (error) => {
  if (isBrowser) syncCsrfCookieName(error.response?.headers?.[CSRF_COOKIE_NAME_HEADER]);
  const status = error.response?.status;

  // A coded 403 (feature_locked, not_permitted) is a permission answer, not an expired session.
  const coded403 = status === 403 && typeof error.response?.data?.code === 'string';

  // Session expired or not authenticated — notify user
  if (status === 401 || (status === 403 && !coded403)) {
    const url = error.config?.url || '';
    // Don't redirect on auth check endpoints (they're expected to 401)
    const isAuthCheck = url.includes('/auth/') || url.includes('/tests/login');
    if (!isAuthCheck && typeof window !== 'undefined') {
      // Only show once per session to avoid toast spam
      const key = '_auth_toast_shown';
      if (!(window as unknown as Record<string, unknown>)[key]) {
        (window as unknown as Record<string, unknown>)[key] = true;
        // Dynamic import to avoid circular deps
        import('sonner').then(({ toast }) => {
          toast.error('Session expired — please log in again', {
            duration: 10000,
            action: {
              label: 'Log In',
              onClick: () => { window.location.href = '/login'; },
            },
          });
        });
        // Reset after 30s so it can show again if needed
        setTimeout(() => { (window as unknown as Record<string, unknown>)[key] = false; }, 30000);
      }
    }
  }

  // Capture API errors in Sentry (skip 4xx client errors except 429)
  if (!status || status >= 500 || status === 429) {
    Sentry.captureException(error);
  }
  return Promise.reject(error);
});

export default api;
