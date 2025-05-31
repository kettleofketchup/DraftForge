import axios from 'axios';

import { getCsrfToken } from './utils';
export const api = axios.create({
  baseURL: '/api', // your API base, e.g. 'http://localhost:8000'
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

export default api;
