import axios from 'axios';

import { readCookie } from '~/lib/cookies';
import { getLogger } from '~/lib/logger';

const log = getLogger('csrf');

// Test stack slots N >= 1 set this so their cookies don't collide on `localhost`.
export const CSRF_COOKIE_NAME: string = import.meta.env.VITE_CSRF_COOKIE_NAME || 'csrftoken';
export const CSRF_COOKIE_NAME_HEADER = 'x-csrf-cookie-name';

let csrfCookieName = CSRF_COOKIE_NAME;

export function getCsrfCookieName(): string {
  return csrfCookieName;
}

export function syncCsrfCookieName(backendName: unknown): void {
  if (typeof backendName !== 'string' || !backendName || backendName === csrfCookieName) return;
  log.warn('CSRF cookie name from the backend differs from the frontend build; using the backend name', {
    configured: CSRF_COOKIE_NAME,
    previous: csrfCookieName,
    backend: backendName,
  });
  csrfCookieName = backendName;
}

export function getCsrfToken(): string {
  return readCookie(document.cookie, csrfCookieName) ?? '';
}

export const api = axios.create({
  baseURL: '/api', // relative; nginx proxies it to the backend
  withCredentials: true, // send cookies like sessionid
});

export default api;
