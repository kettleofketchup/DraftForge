import axios from 'axios';

import { getCsrfToken } from './utils';

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

export default api;
