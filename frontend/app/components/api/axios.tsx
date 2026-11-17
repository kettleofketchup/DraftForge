import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import {
  activityAuthorization,
  getActivityCredential,
  isActivityFrame,
  refreshActivityCredential,
} from '~/lib/activity-session';
import { Sentry } from '~/lib/sentry';

import {
  CSRF_COOKIE_NAME_HEADER,
  getCsrfToken,
  syncCsrfCookieName,
} from './utils';

declare module 'axios' {
  interface AxiosRequestConfig {
    skipActivityErrorHandling?: boolean;
    _activityToken?: string;
    _activityRetried?: boolean;
  }
}

interface ActivityErrorHandlers {
  onScopeLost(): void;
  onDisabled(): void;
}

let activityHandlers: ActivityErrorHandlers | null = null;

export function setActivityErrorHandlers(
  handlers: ActivityErrorHandlers | null,
): void {
  activityHandlers = handlers;
}

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
  const activityAuth = activityAuthorization(config.url || '');
  if (activityAuth) {
    config.headers.Authorization = activityAuth;
    config._activityToken = getActivityCredential()?.token;
  }
  const method = config.method?.toUpperCase();
  const needsCSRF = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method || '');

  if (needsCSRF) {
    config.headers['X-CSRFToken'] = getCsrfToken();
  }

  return config;
});

const isBrowser = typeof window !== 'undefined';

function activityToast(message: string, info = false): void {
  import('sonner').then(({ toast }) => {
    if (info) toast.info(message, { id: 'activity-reconnecting' });
    else toast.error(message);
  });
}

function retryActivity(config: InternalAxiosRequestConfig) {
  return api.request({ ...config, _activityRetried: true });
}

async function handleActivityError(error: AxiosError): Promise<unknown> {
  const status = error.response?.status;
  const data = (error.response?.data ?? {}) as {
    code?: unknown;
    error?: unknown;
    detail?: unknown;
  };
  const config = error.config;
  if (status === 403) {
    const text =
      typeof data.error === 'string'
        ? data.error
        : typeof data.detail === 'string'
          ? data.detail
          : 'You do not have permission to do that.';
    activityToast(text);
  } else if (status === 401) {
    switch (data.code) {
      case 'activity_session_ended': {
        if (!config || config._activityRetried) break;
        const current = getActivityCredential()?.token;
        if (current && current !== config._activityToken)
          return retryActivity(config);
        activityToast('Reconnecting…', true);
        if (await refreshActivityCredential()) return retryActivity(config);
        break;
      }
      case 'activity_out_of_scope':
        activityHandlers?.onScopeLost();
        break;
      case 'activity_disabled':
        activityHandlers?.onDisabled();
        break;
      case 'activity_path_not_allowed':
        activityToast('This action is not available in the Activity.');
        break;
      default:
        activityToast(
          'The Activity could not verify you. Reopen the Activity if this keeps happening.',
        );
    }
  }
  if (!status || status >= 500 || status === 429)
    Sentry.captureException(error);
  return Promise.reject(error);
}

api.interceptors.response.use(
  (response) => {
    if (isBrowser)
      syncCsrfCookieName(response.headers?.[CSRF_COOKIE_NAME_HEADER]);
    return response;
  },
  (error) => {
    if (error.config?.skipActivityErrorHandling) return Promise.reject(error);
    if (isBrowser)
      syncCsrfCookieName(error.response?.headers?.[CSRF_COOKIE_NAME_HEADER]);
    if (isActivityFrame()) return handleActivityError(error);
    const status = error.response?.status;

    // A coded 403 (feature_locked, not_permitted) is a permission answer, not an expired session.
    const coded403 =
      status === 403 && typeof error.response?.data?.code === 'string';

    // Session expired or not authenticated — notify user
    if (status === 401 || (status === 403 && !coded403)) {
      const url = error.config?.url || '';
      // Don't redirect on auth check endpoints (they're expected to 401)
      const isAuthCheck =
        url.includes('/auth/') || url.includes('/tests/login');
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
                onClick: () => {
                  window.location.href = '/login';
                },
              },
            });
          });
          // Reset after 30s so it can show again if needed
          setTimeout(() => {
            (window as unknown as Record<string, unknown>)[key] = false;
          }, 30000);
        }
      }
    }

    // Capture API errors in Sentry (skip 4xx client errors except 429)
    if (!status || status >= 500 || status === 429) {
      Sentry.captureException(error);
    }
    return Promise.reject(error);
  },
);

export default api;
