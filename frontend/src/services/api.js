import axios from 'axios';
import { store } from '../app/store';
import { tokenRefreshed, logout } from '../features/auth/authSlice';

const getBaseUrl = () => {
  // Local development: always use Vite's proxy (/api -> http://127.0.0.1:8000)
  if (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.port === '5173')) {
    return '/api';
  }
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl && envUrl.trim() && envUrl.trim() !== '/api') {
    const clean = envUrl.trim().replace(/\/+$/, '');
    return clean.endsWith('/api') ? clean : `${clean}/api`;
  }
  // Production CloudFront frontend domain connects to EC2 backend API domain
  if (typeof window !== 'undefined' && window.location.hostname.includes('marketinteldbapp.hikasimat.com')) {
    return 'https://marketintel.hikasimat.com/api';
  }
  return '/api';
};

const api = axios.create({
  baseURL: getBaseUrl(),
  timeout: 30000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(
  (config) => {
    const token = store.getState().auth.accessToken;
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    // If sending FormData, delete Content-Type so Axios and browser stream multipart/form-data with boundary
    if (config.data instanceof FormData) {
      if (config.headers) {
        if (typeof config.headers.delete === 'function') {
          config.headers.delete('Content-Type');
          config.headers.delete('content-type');
        } else {
          delete config.headers['Content-Type'];
          delete config.headers['content-type'];
        }
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const isAuthEndpoint = originalRequest?.url?.includes('/auth/login/') || originalRequest?.url?.includes('/auth/refresh/');
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      if (isRefreshing) {
        return new Promise(function(resolve, reject) {
          failedQueue.push({ resolve, reject });
        }).then(token => {
          originalRequest.headers['Authorization'] = `Bearer ${token}`;
          return api(originalRequest);
        }).catch(err => {
          return Promise.reject(err);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;
      
      try {
        const response = await axios.post(`${api.defaults.baseURL}/auth/refresh/`, {}, { withCredentials: true });
        
        store.dispatch(tokenRefreshed({ access: response.data.access }));
          
        const newToken = response.data.access;
        processQueue(null, newToken);
          
        originalRequest.headers['Authorization'] = `Bearer ${newToken}`;
        return api(originalRequest);
      } catch (refreshError) {
        // Fallback for catch if needed though we handle it inside try block, but just in case
        processQueue(refreshError, null);
        store.dispatch(logout());
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }
    return Promise.reject(error);
  }
);

export default api;
