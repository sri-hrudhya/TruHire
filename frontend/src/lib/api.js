import axios from 'axios';
import { cachingAdapter, clearRequestCache } from './requestCache';
import { STORAGE_KEYS, TIMEOUTS_MS } from '../config/env';

const api = axios.create({
  baseURL: '/api',
  timeout: TIMEOUTS_MS.default,
  adapter: cachingAdapter,
});

// Request interceptor to inject JWT
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(STORAGE_KEYS.token);
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
        clearRequestCache();
        localStorage.removeItem(STORAGE_KEYS.token);
        localStorage.removeItem(STORAGE_KEYS.user);
        // Keep the current page so signing back in returns here instead of the default section.
        const next = `${window.location.pathname}${window.location.search}`;
        window.location.href = `/login?next=${encodeURIComponent(next)}`;
      }
    }
    return Promise.reject(error);
  }
);

// API Service Methods
export const metaApi = {
  get: () => api.get('/meta'),
};

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
  // history is polled / manually refreshed: always bypass the client cache (the server caches for 10s)
  history: (params = {}) => api.get('/ingest/history', { params, headers: { 'X-Cache-Bypass': '1' } }),
};

export const jdApi = {
  list: () => api.get('/job-descriptions'),
  create: (data) => api.post('/job-descriptions', data),
  update: (id, data) => api.put(`/job-descriptions/${id}`, data),
  delete: (id) => api.delete(`/job-descriptions/${id}`),
  // Scoring a requirement can take a while on a cold start (model loading), so allow more than the default.
  getMatches: (id, top_n = 50) => api.get(`/job-descriptions/${id}/matches?top_n=${top_n}`, { timeout: TIMEOUTS_MS.scoring }),
  // extras: { cancellation_reason } for Cancelled, { candidate_ids } for Mapped / Fulfilled.
  setStatus: (id, status, extras = {}) => api.put(`/job-descriptions/${id}/status`, { status, ...extras }),
  setCandidateStatus: (id, candidateId, status) => api.put(`/job-descriptions/${id}/candidates/${candidateId}/status`, { status }),
  summarize: (id) => api.post(`/job-descriptions/${id}/summarize`),
  // Location / role / work mode read from the JD (null where the JD does not state them).
  getSearchFilters: (id) => api.get(`/job-descriptions/${id}/search-filters`, { timeout: TIMEOUTS_MS.jdFilters }),
  getFile: (id) => api.get(`/job-descriptions/${id}/file`, { responseType: 'blob' }),
  // Location / experience / dates the JD text states (null where it does not), for pasted text.
  extractDetails: (payload) => api.post('/job-descriptions/extract-details', payload, { timeout: TIMEOUTS_MS.jdFilters }),
  extractText: (formData) => api.post('/job-descriptions/extract-text', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
};

// Demands group requirements; writes here clear the whole client cache (see requestCache INVALIDATION).
export const demandApi = {
  list: () => api.get('/demands'),
  // The five categories are fixed (Java, GenAI, Camunda, Pega, Others): read-only from the client.
  get: (id) => api.get(`/demands/${id}`),
  listJds: (id) => api.get(`/demands/${id}/job-descriptions`),
};

// Shared by the Requirements page and the Email page so both write to the same history.
export const emailApi = {
  getConfig: () => api.get('/email/config'),
  // One LLM call per candidate; allow longer than the default timeout.
  generate: (positionId, candidateIds) => api.post('/email/generate', { position_id: positionId, candidate_ids: candidateIds }, { timeout: TIMEOUTS_MS.emailDraft }),
  send: (positionId, emails, allowResend = false) => api.post('/email/send', { position_id: positionId, emails, allow_resend: allowResend }, { timeout: TIMEOUTS_MS.emailSend }),
  history: () => api.get('/email/history'),
  historyForRole: (positionId) => api.get(`/email/history/${positionId}`),
  retry: (id) => api.post(`/email/records/${id}/retry`),
};

// Shared review workflow: who reviews a candidate for a requirement, and the comment thread on a candidate.
export const reviewApi = {
  listAssignments: (jdId, mine = false) => api.get(`/job-descriptions/${jdId}/assignments`, { params: mine ? { mine: true } : {} }),
  assign: (jdId, candidateId, assigneeId) => api.put(`/job-descriptions/${jdId}/candidates/${candidateId}/assignment`, { assignee_id: assigneeId }),
  unassign: (jdId, candidateId) => api.delete(`/job-descriptions/${jdId}/candidates/${candidateId}/assignment`),
  listComments: (candidateId, positionId = null) => api.get(`/candidates/${candidateId}/comments`, { params: positionId ? { position_id: positionId } : {} }),
  addComment: (candidateId, payload) => api.post(`/candidates/${candidateId}/comments`, payload),
  updateComment: (commentId, payload) => api.patch(`/comments/${commentId}`, payload),
  deleteComment: (commentId) => api.delete(`/comments/${commentId}`),
};

export const usersApi = {
  list: () => api.get('/users'),
};

export const retentionApi = {
  getStatus: () => api.get('/retention/status'),
  cleanup: (retentionDays = null) => {
    const url = retentionDays ? `/retention/cleanup?retention_days=${retentionDays}` : '/retention/cleanup';
    return api.post(url);
  },
};

export const requirementHistoryApi = {
  list: (params = {}) => api.get('/requirement-history', { params }),
};

export const candidatesApi = {
  get: (id) => api.get(`/candidates/${id}`),
  // bypass: skip the client cache after uploads so new resumes show immediately
  list: (params = {}, bypass = false) => api.get('/candidates', { params, headers: bypass ? { 'X-Cache-Bypass': '1' } : {} }),
  setNoticePeriod: (id, value, unit) => api.patch(`/candidates/${id}/notice-period`, { value, unit }),
  updateStatus: (id, status) => api.patch(`/candidates/${id}/status`, { status }),
  getMatches: (id) => api.get(`/candidates/${id}/matches`),
  getResumeFile: (id) => api.get(`/candidates/${id}/resume`, { responseType: 'blob' }),
};

export const searchApi = {
  search: (payload) => api.post('/search', payload, { timeout: TIMEOUTS_MS.search }),
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
