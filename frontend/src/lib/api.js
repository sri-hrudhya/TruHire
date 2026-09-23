import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

// Request interceptor to inject JWT
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('truhire_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor to handle token expiration
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      if (!window.location.pathname.startsWith('/login')) {
        localStorage.removeItem('truhire_token');
        localStorage.removeItem('truhire_user');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// API Service Methods
export const authApi = {
  login: (credentials) => api.post('/auth/login', credentials),
  register: (data) => api.post('/auth/register', data),
  getMe: () => api.get('/auth/me'),
};

export const ingestionApi = {
  uploadResumes: (formData) => api.post('/ingest/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  getBatches: (limit = 20, offset = 0) => api.get(`/ingest/batches?limit=${limit}&offset=${offset}`),
  getBatch: (id) => api.get(`/ingest/batches/${id}`),
};

export const jdApi = {
  list: () => api.get('/job-descriptions'),
  get: (id) => api.get(`/job-descriptions/${id}`),
  create: (data) => api.post('/job-descriptions', data),
  update: (id, data) => api.put(`/job-descriptions/${id}`, data),
  summarize: (id) => api.post(`/job-descriptions/${id}/summarize`),
};

export const candidatesApi = {
  list: (limit = 20, offset = 0) => api.get(`/candidates?limit=${limit}&offset=${offset}`),
  get: (id) => api.get(`/candidates/${id}`),
  updateStatus: (id, status) => api.patch(`/candidates/${id}/status`, { status }),
  getMatches: (id) => api.get(`/candidates/${id}/matches`),
};

export const searchApi = {
  search: (payload) => api.post('/search', payload),
  parseQuery: (query, existing_skills = []) => api.post('/search/parse-query', { query, existing_skills }),
};

export const analyticsApi = {
  getOverview: (positionId = null) => {
    const url = positionId ? `/analytics/overview?position_id=${positionId}` : '/analytics/overview';
    return api.get(url);
  },
};

export const chatApi = {
  sendMessage: (payload) => api.post('/chat', payload),
};

export const exportApi = {
  getExportUrl: (format = 'csv', positionId = null, status = null) => {
    let url = `/api/export/candidates?format=${format}`;
    if (positionId) url += `&position_id=${positionId}`;
    if (status) url += `&status=${status}`;
    return url;
  }
};

export default api;


// TruHire API debugging helper: preserves backend error details in development.
export const getApiError = (error) => ({
  status: error?.response?.status ?? null,
  data: error?.response?.data ?? null,
  message: error?.message ?? 'Unknown API error',
});
