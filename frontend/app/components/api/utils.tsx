import axios from 'axios';

// Test stack slots N >= 1 set this so their cookies don't collide on `localhost`.
export const CSRF_COOKIE_NAME: string = import.meta.env.VITE_CSRF_COOKIE_NAME || 'csrftoken';

export function readCookie(cookieHeader: string, name: string): string {
  for (const part of cookieHeader.split(';')) {
    const eq = part.indexOf('=');
    if (eq !== -1 && part.slice(0, eq).trim() === name) return part.slice(eq + 1).trim();
  }
  return '';
}

export function getCsrfToken(): string {
  return readCookie(document.cookie, CSRF_COOKIE_NAME);
}

export const api = axios.create({
  baseURL: '/api', // your API base, e.g. 'http://localhost:8000'
  withCredentials: true, // send cookies like sessionid
});

export default api;
