import axios from 'axios';

export function getCsrfToken(): string {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }


export const api = axios.create({
  baseURL: '/api', // your API base, e.g. 'http://localhost:8000'
  withCredentials: true, // send cookies like sessionid
});

export default api;
