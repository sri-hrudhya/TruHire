import React, { useState, useEffect, useCallback } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { History, Search, RefreshCw, CheckCircle2, Copy, XCircle, Clock } from 'lucide-react';
import { ingestionApi } from '../lib/api';
import PageBreadcrumbs from '../components/PageBreadcrumbs';
import { fromState, useBackNavigation, HISTORY_QUERY_KEY } from '../lib/navigation';
import { POLL_MS } from '../config/env';
import { useMeta } from '../context/MetaContext';

const WINDOWS = [
  { label: '10 min', minutes: 10 },
  { label: '1 hour', minutes: 60 },
  { label: '1 day', minutes: 1440 },
  { label: '7 days', minutes: 10080 },
  { label: '30 days', minutes: 43200 },
  { label: 'All time', minutes: null },
];

const STATUS_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'indexed', label: 'Indexed' },
  { key: 'duplicate', label: 'Duplicates' },
  { key: 'failed', label: 'Failed' },
];

const STATUS_META = {
  indexed: { label: 'Indexed', badge: 'badge-success', Icon: CheckCircle2 },
  pending_index: { label: 'Not indexed', badge: 'badge-warning', Icon: Clock },
  duplicate: { label: 'Duplicate', badge: 'badge-warning', Icon: Copy },
  failed: { label: 'Failed', badge: 'badge-danger', Icon: XCircle },
};

const DEFAULT_MINUTES = 1440;

// Filters live in the URL (?window=&status=&q=&page=) so browser Back/Forward, refresh and
// direct links all reopen the same view.
function minutesFromParam(value) {
  if (value === 'all') return null;
  const match = WINDOWS.find(w => w.minutes != null && String(w.minutes) === value);
  return match ? match.minutes : DEFAULT_MINUTES;
}

function timeAgo(iso) {
  if (!iso) return '';
  const secs = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)} h ago`;
  return `${Math.floor(secs / 86400)} d ago`;
}

export default function IngestionHistoryPage() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { goBack, backLabel } = useBackNavigation('/ingestion', 'Ingestion');
  const PAGE_SIZE = useMeta().page_sizes.history;

  const minutes = minutesFromParam(searchParams.get('window'));
  const statusParam = searchParams.get('status');
  const status = STATUS_FILTERS.some(f => f.key === statusParam) ? statusParam : 'all';
  const debouncedQuery = (searchParams.get('q') || '').trim();
  const page = Math.max(0, (parseInt(searchParams.get('page'), 10) || 1) - 1);

  const [query, setQuery] = useState(debouncedQuery);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Filter changes replace the current history entry (no duplicate entries per click/keystroke)
  // and keep the router state so "Back to ..." still knows where the user came from.
  const updateFilters = useCallback((changes) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      Object.entries(changes).forEach(([key, value]) => {
        if (value == null || value === '') next.delete(key);
        else next.set(key, String(value));
      });
      return next;
    }, { replace: true, state: location.state });
  }, [setSearchParams, location.state]);

  const setMinutes = (m) => updateFilters({ window: m === null ? 'all' : (m === DEFAULT_MINUTES ? null : m), page: null });
  const setStatus = (key) => updateFilters({ status: key === 'all' ? null : key, page: null });
  const setPage = (updater) => {
    const nextPage = typeof updater === 'function' ? updater(page) : updater;
    updateFilters({ page: nextPage > 0 ? nextPage + 1 : null });
  };

  useEffect(() => {
    const t = setTimeout(() => {
      if (query.trim() !== debouncedQuery) updateFilters({ q: query.trim() || null, page: null });
    }, 300);
    return () => clearTimeout(t);
  }, [query, debouncedQuery, updateFilters]);

  // Keep the search box in sync when the URL changes from outside (e.g. browser Back/Forward).
  useEffect(() => {
    setQuery(q => (q.trim() === debouncedQuery ? q : debouncedQuery));
  }, [debouncedQuery]);

  // Remember the current filters so the "Ingestion History" button reopens this view.
  useEffect(() => {
    try { sessionStorage.setItem(HISTORY_QUERY_KEY, location.search); } catch { /* storage unavailable */ }
  }, [location.search]);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await ingestionApi.history({
        minutes: minutes ?? undefined, status, q: debouncedQuery || undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE,
      });
      setData(res.data);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load ingestion history.');
    } finally {
      setLoading(false);
    }
  }, [minutes, status, debouncedQuery, page, PAGE_SIZE]);

  useEffect(() => { load(); }, [load]);

  // Keep the list live while an upload is being processed in another tab.
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => load(true), POLL_MS.ingestionHistory);
    return () => clearInterval(id);
  }, [autoRefresh, load]);

  const counts = data?.counts || { indexed: 0, duplicate: 0, failed: 0 };
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // A stale ?page= (e.g. after records were removed) falls back to the last page that exists.
  useEffect(() => {
    if (data && page > 0 && page >= pages) setPage(pages - 1);
  }, [data, page, pages]); // eslint-disable-line react-hooks/exhaustive-deps

  const chip = (active) => ({
    padding: '0.4rem 0.85rem', borderRadius: '999px', fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer',
    border: `1px solid ${active ? 'var(--primary)' : 'var(--border-color)'}`,
    backgroundColor: active ? 'var(--primary-light)' : 'var(--bg-surface)',
    color: active ? 'var(--primary)' : 'var(--text-muted)',
  });

  return (
    <div className="page-body">
      <PageBreadcrumbs
        onBack={goBack}
        backLabel={backLabel}
        items={[{ label: 'Ingestion', to: '/ingestion' }, { label: 'Ingestion History' }]}
      />
      <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 className="page-header-title" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <History size={26} color="var(--primary)" /> Ingestion History
          </h1>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <label style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer' }}>
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} /> Auto-refresh
          </label>
          <button className="btn" onClick={() => load()} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : undefined} /> Refresh
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="card" style={{ marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center', marginBottom: '0.9rem' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginRight: '0.25rem' }}>Ingested in the last</span>
          {WINDOWS.map(w => (
            <button key={w.label} onClick={() => setMinutes(w.minutes)} style={chip(minutes === w.minutes)}>{w.label}</button>
          ))}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: '220px' }}>
            <Search size={16} color="var(--text-subtle)" style={{ position: 'absolute', left: '12px', top: '11px' }} />
            <input
              className="input-field" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="Search file name, candidate or ID..." style={{ paddingLeft: '36px' }}
            />
          </div>
          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            {STATUS_FILTERS.map(f => (
              <button key={f.key} onClick={() => setStatus(f.key)} style={chip(status === f.key)}>
                {f.label}{f.key !== 'all' ? ` (${counts[f.key] ?? 0})` : ''}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div style={{ padding: '0.75rem 1rem', marginBottom: '1rem', borderRadius: '6px', fontSize: '0.8125rem', backgroundColor: 'var(--danger-bg)', color: 'var(--danger-text)' }}>{error}</div>
      )}

      {/* Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
            <thead>
              <tr style={{ textAlign: 'left', backgroundColor: 'var(--bg-subtle)', color: 'var(--text-muted)', fontSize: '0.72rem', textTransform: 'uppercase' }}>
                <th style={{ padding: '0.7rem 1rem' }}>When</th>
                <th style={{ padding: '0.7rem 1rem' }}>File</th>
                <th style={{ padding: '0.7rem 1rem' }}>Candidate</th>
                <th style={{ padding: '0.7rem 1rem' }}>Experience</th>
                <th style={{ padding: '0.7rem 1rem' }}>Skills</th>
                <th style={{ padding: '0.7rem 1rem' }}>Status</th>
                <th style={{ padding: '0.7rem 1rem' }}>By</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((row, i) => {
                const meta = STATUS_META[row.status] || STATUS_META.failed;
                return (
                  <tr key={`${row.batch_id}-${row.filename}-${i}`} style={{ borderTop: '1px solid var(--border-color)' }}>
                    <td style={{ padding: '0.7rem 1rem', whiteSpace: 'nowrap' }} title={row.uploaded_at ? new Date(row.uploaded_at).toLocaleString() : ''}>
                      <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{timeAgo(row.uploaded_at)}</div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-subtle)' }}>{row.uploaded_at ? new Date(row.uploaded_at).toLocaleString() : ''}</div>
                    </td>
                    <td style={{ padding: '0.7rem 1rem', maxWidth: '280px' }}>
                      <div style={{ fontWeight: 600, color: 'var(--text-main)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.filename}</div>
                      {row.detail && <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{row.detail}</div>}
                    </td>
                    <td style={{ padding: '0.7rem 1rem' }}>
                      {row.candidate_id ? (
                        <Link to={`/candidates/${row.candidate_id}`} state={fromState(location, 'Ingestion History')} style={{ color: 'var(--primary)', fontWeight: 600, textDecoration: 'none' }}>
                          {row.candidate_name}
                          <span style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-subtle)', fontWeight: 500 }}>{row.display_id}</span>
                        </Link>
                      ) : <span style={{ color: 'var(--text-subtle)' }}>-</span>}
                    </td>
                    <td style={{ padding: '0.7rem 1rem' }}>{row.years_experience != null ? `${row.years_experience} yrs` : '-'}</td>
                    <td style={{ padding: '0.7rem 1rem' }}>{row.skill_count != null ? row.skill_count : '-'}</td>
                    <td style={{ padding: '0.7rem 1rem' }}>
                      <span className={`badge ${meta.badge}`} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
                        <meta.Icon size={12} /> {meta.label}
                      </span>
                    </td>
                    <td style={{ padding: '0.7rem 1rem', color: 'var(--text-muted)' }}>{row.uploaded_by || '-'}</td>
                  </tr>
                );
              })}
              {data && data.items.length === 0 && (
                <tr><td colSpan={7} style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                  No ingested documents match these filters.
                </td></tr>
              )}
              {!data && loading && (
                <tr><td colSpan={7} style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--text-muted)' }}>Loading history...</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem 1rem', borderTop: '1px solid var(--border-color)', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          <span>{total} document{total === 1 ? '' : 's'}</span>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <button className="btn" disabled={page === 0} onClick={() => setPage(p => Math.max(0, p - 1))}>Previous</button>
            <span>Page {page + 1} of {pages}</span>
            <button className="btn" disabled={page + 1 >= pages} onClick={() => setPage(p => p + 1)}>Next</button>
          </div>
        </div>
      </div>
    </div>
  );
}
