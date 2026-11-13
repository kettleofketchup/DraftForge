import axios from 'axios';

import { readCookie } from '~/lib/cookies';

const CSRF_COOKIE_NAME = 'csrftoken';

export function getCsrfToken(): string {
  return readCookie(document.cookie, CSRF_COOKIE_NAME) ?? '';
}

export const api = axios.create({
  baseURL: '/api', // relative; nginx proxies it to the backend
  withCredentials: true, // send cookies like sessionid
});

export default api;
