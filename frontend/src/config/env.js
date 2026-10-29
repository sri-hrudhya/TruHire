// Client-side constants that are configuration rather than design: storage keys, timeouts and polling.
// Business enums and limits (statuses, page sizes, top_n bounds) come from the backend via /api/meta.

export const STORAGE_KEYS = Object.freeze({
  token: 'truhire_token',
  user: 'truhire_user',
  theme: 'truhire_theme',
  sidebarCollapsed: 'truhire_sidebar_collapsed',
  searchCategory: 'truhire_search_demand',
  emailDraft: 'truhire_email_draft',
  lastUploadBatch: 'truhire_last_upload_batch',
  ingestionHistoryQuery: 'truhire_ingestion_history_query',
});

export const TIMEOUTS_MS = Object.freeze({
  default: 30_000,
  scoring: 180_000,     // scoring a requirement can include a cold model start
  search: 300_000,      // reranking and Laya scoring run on the local machine and can take minutes on a CPU
  emailDraft: 180_000,  // one LLM call per candidate
  emailSend: 120_000,
  jdFilters: 60_000,
  objectUrlRevoke: 60_000,
});

export const POLL_MS = Object.freeze({
  uploadProgress: 800,
  ingestionHistory: 5_000,
});

export const DEFAULT_ROUTE = '/ingestion';

// Result-size shortcuts offered in Search, together with the server's default and maximum (see /api/meta).
export const TOP_N_PRESETS = Object.freeze([10, 50]);
