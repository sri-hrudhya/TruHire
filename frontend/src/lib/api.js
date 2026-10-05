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
  upload: (formData) => api.post('/job-descriptions/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  extractText: (formData) => api.post('/job-descriptions/extract-text', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
};

export const retentionApi = {
  getStatus: () => api.get('/retention/status'),
  cleanup: (retentionDays = null) => {
    const url = retentionDays ? `/retention/cleanup?retention_days=${retentionDays}` : '/retention/cleanup';
    return api.post(url);
  },
};

export const candidatesApi = {
  list: (limit = 20, offset = 0) => api.get(`/candidates?limit=${limit}&offset=${offset}`),
  get: (id) => api.get(`/candidates/${id}`),
  updateStatus: (id, status) => api.patch(`/candidates/${id}/status`, { status }),
  getMatches: (id) => api.get(`/candidates/${id}/matches`),
};

export const searchApi = {
  search: (payload) => api.post('/search', payload),
  getState: () => api.get('/search/state'),
  clearState: () => api.delete('/search/state'),
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
  listConversations: () => api.get('/chat/conversations'),
  getConversation: (id) => api.get(`/chat/conversations/${id}`),
};

export const exportApi = {
  getExportUrl: (format = 'xlsx', positionId = null, status = null) => {
    const token = localStorage.getItem('truhire_token');
    let url = `/api/export/candidates?format=${format}`;
    if (positionId) url += `&position_id=${positionId}`;
    if (status) url += `&status=${status}`;
    if (token) url += `&token=${encodeURIComponent(token)}`;
    return url;
  },
  downloadCandidates: async (format = 'xlsx', positionId = null, status = null) => {
    const response = await api.get('/export/candidates', {
      params: {
        format,
        position_id: positionId || undefined,
        status: status || undefined,
      },
      responseType: 'blob',
    });

    let filename = format === 'csv' ? 'truhire_candidates.csv' : 'truhire_candidates.xlsx';
    const disposition = response.headers['content-disposition'];
    if (disposition && disposition.indexOf('filename=') !== -1) {
      const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(disposition);
      if (matches != null && matches[1]) {
        filename = matches[1].replace(/['"]/g, '');
      }
    }

    const contentType = response.headers['content-type'] || 
      (format === 'csv' ? 'text/csv;charset=utf-8;' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    const blob = new Blob([response.data], { type: contentType });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
    return true;
  }
};

export default api;


// TruHire API debugging helper: preserves backend error details in development.
export const getApiError = (error) => ({
  status: error?.response?.status ?? null,
  data: error?.response?.data ?? null,
  message: error?.message ?? 'Unknown API error',
});
