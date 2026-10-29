import { STORAGE_KEYS } from '../config/env.js';
// Client-side response cache for every page (installed once in lib/api.js).
//
//  * GET responses are served from memory while fresh (per-endpoint TTL), so revisiting a page or
//    switching tabs is instant and does not hit the API.
//  * Identical in-flight GETs are shared (one network call, many callers).
//  * Any successful write (POST/PUT/PATCH/DELETE) evicts exactly the cached reads it can change, so
//    a page never shows data older than the user's own last action.
//  * The cache is keyed per auth token and wiped on logout / 401.
//  * Pass headers { 'X-Cache-Bypass': '1' } to force a fresh read (used by Refresh buttons/polling).
import axios from 'axios';

const defaultAdapter = axios.getAdapter(axios.defaults.adapter);
const store = new Map();     // key -> { at, ttl, response }
const inflight = new Map();  // key -> Promise

// TTL in ms by URL (relative to the /api baseURL). First match wins; 0 = never cache.
const TTL_RULES = [
  [/^\/ingest\/batches\//, 0],            // live upload progress polling
  [/^\/ingest\/history/, 0],              // history has its own 5s auto-refresh + server cache
  [/\/(file|resume)$/, 0],                // binary downloads
  [/^\/export\//, 0],
  [/^\/ai-audit/, 15000],
  [/^\/email\/config/, 300000],           // static for the lifetime of the server
  [/^\/auth\/me/, 120000],
  [/^\/meta/, 300000],                    // enums and limits only change with a server deploy
  [/^\/analytics\//, 60000],
  [/^\/retention\/status/, 60000],
  [/^\/job-descriptions\/[^/]+\/matches/, 300000],
  [/^\/job-descriptions/, 60000],
  [/^\/candidates\/[^/]+\/matches/, 45000],
  [/^\/candidates/, 60000],
  [/^\/email\/history/, 30000],
  [/^\/search\/state/, 60000],
];
const DEFAULT_TTL = 0; // unknown endpoints are never cached by accident

// Which cached reads a successful write can change. Unlisted writes clear everything (safe default).
const INVALIDATION = [
  [/^\/ingest\//, [/^\/candidates/, /^\/analytics/, /^\/job-descriptions/, /^\/search\/state/, /^\/ingest\//]],
  [/^\/job-descriptions/, [/^\/job-descriptions/, /^\/analytics/, /^\/email\/history/, /^\/candidates/, /^\/search\/state/]],
  [/^\/candidates/, [/^\/candidates/, /^\/job-descriptions/, /^\/analytics/]],
  [/^\/search/, [/^\/search\/state/]],
  // sending/retrying emails changes last_email shown in the requirement match lists too
  [/^\/email/, [/^\/email\/history/, /^\/job-descriptions/]],
];

const ttlFor = (url) => {
  const path = (url || '').split('?')[0];
  for (const [re, ttl] of TTL_RULES) if (re.test(path)) return ttl;
  return DEFAULT_TTL;
};

const keyFor = (config) => {
  const token = typeof localStorage !== 'undefined' ? localStorage.getItem(STORAGE_KEYS.token) || '' : '';
  return `${token.slice(-16)}|${config.url}|${JSON.stringify(config.params || {})}`;
};

const urlOfKey = (key) => key.split('|')[1] || '';

export function clearRequestCache() {
  store.clear();
  inflight.clear();
}

function evictFor(writeUrl) {
  const path = (writeUrl || '').split('?')[0];
  const rule = INVALIDATION.find(([re]) => re.test(path));
  if (!rule) return clearRequestCache();
  for (const key of [...store.keys()]) {
    if (rule[1].some((re) => re.test(urlOfKey(key).split('?')[0]))) store.delete(key);
  }
}

const clone = (value) => (typeof structuredClone === 'function' ? structuredClone(value) : JSON.parse(JSON.stringify(value)));

export function cachingAdapter(config) {
  const method = (config.method || 'get').toLowerCase();

  if (method !== 'get') {
    return defaultAdapter(config).then((response) => {
      evictFor(config.url);
      return response;
    });
  }

  const bypass = config.headers && config.headers.get && config.headers.get('X-Cache-Bypass');
  if (config.headers && config.headers.delete) config.headers.delete('X-Cache-Bypass');
  const ttl = config.responseType === 'blob' ? 0 : ttlFor(config.url);
  if (!ttl) return defaultAdapter(config);

  const key = keyFor(config);
  const hit = store.get(key);
  if (!bypass && hit && Date.now() - hit.at < hit.ttl) {
    return Promise.resolve({ ...hit.response, data: clone(hit.response.data), config });
  }
  if (!bypass && inflight.has(key)) {
    return inflight.get(key).then((response) => ({ ...response, data: clone(response.data), config }));
  }

  const request = defaultAdapter(config)
    .then((response) => {
      // A scoring run where a retrieval source was down must not be pinned in the cache: the next
      // request should see the recovered service instead of a stale "keyword search unavailable" result.
      const r = response.data?.retrieval;
      if (r && !(r.vector && r.lexical)) return response;
      store.set(key, { at: Date.now(), ttl, response: { ...response, data: clone(response.data), request: undefined, config: undefined } });
      return response;
    })
    .finally(() => inflight.delete(key));
  inflight.set(key, request);
  return request;
}
