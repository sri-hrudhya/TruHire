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
  getBatch: (id) => api.get(`/ingest/batches/${id}`),
};

export const jdApi = {
  list: () => api.get('/job-descriptions'),
  create: (data) => api.post('/job-descriptions', data),
  update: (id, data) => api.put(`/job-descriptions/${id}`, data),
  delete: (id) => api.delete(`/job-descriptions/${id}`),
  getMatches: (id, top_n = 50) => api.get(`/job-descriptions/${id}/matches?top_n=${top_n}`),
  setCandidateStatus: (id, candidateId, status) => api.put(`/job-descriptions/${id}/candidates/${candidateId}/status`, { status }),
  summarize: (id) => api.post(`/job-descriptions/${id}/summarize`),
  getFile: (id) => api.get(`/job-descriptions/${id}/file`, { responseType: 'blob' }),
  extractText: (formData) => api.post('/job-descriptions/extract-text', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
};

// Shared by the Requirements page and the Email page so both write to the same history.
export const emailApi = {
  getConfig: () => api.get('/email/config'),
  // One LLM call per candidate; allow longer than the default timeout.
  generate: (positionId, candidateIds) => api.post('/email/generate', { position_id: positionId, candidate_ids: candidateIds }, { timeout: 180000 }),
  send: (positionId, emails, allowResend = false) => api.post('/email/send', { position_id: positionId, emails, allow_resend: allowResend }, { timeout: 120000 }),
  history: () => api.get('/email/history'),
  historyForRole: (positionId) => api.get(`/email/history/${positionId}`),
  retry: (id) => api.post(`/email/records/${id}/retry`),
};

export const retentionApi = {
  getStatus: () => api.get('/retention/status'),
  cleanup: (retentionDays = null) => {
    const url = retentionDays ? `/retention/cleanup?retention_days=${retentionDays}` : '/retention/cleanup';
    return api.post(url);
  },
};

export const candidatesApi = {
  get: (id) => api.get(`/candidates/${id}`),
  updateStatus: (id, status) => api.patch(`/candidates/${id}/status`, { status }),
  getMatches: (id) => api.get(`/candidates/${id}/matches`),
  getResumeFile: (id) => api.get(`/candidates/${id}/resume`, { responseType: 'blob' }),
};

export const searchApi = {
  search: (payload) => api.post('/search', payload),
  getState: () => api.get('/search/state'),
  clearState: () => api.delete('/search/state'),
};

export const analyticsApi = {
  getOverview: (positionId = null) => {
    const url = positionId ? `/analytics/overview?position_id=${positionId}` : '/analytics/overview';
    return api.get(url);
  },
};

export const aiAuditApi = {
  list: (params = {}) => api.get('/ai-audit', { params }),
};

export const chatApi = {
  sendMessage: (payload) => api.post('/chat', payload),
  listConversations: () => api.get('/chat/conversations'),
  getConversation: (id) => api.get(`/chat/conversations/${id}`),
};

export const exportApi = {
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
