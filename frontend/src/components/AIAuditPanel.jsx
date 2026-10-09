import { Fragment, useEffect, useState } from 'react';
import { ShieldCheck, ChevronDown, ChevronRight, RefreshCw } from 'lucide-react';
import { aiAuditApi } from '../lib/api';

const FEATURES = [
  'chat', 'search_summary', 'jd_summary', 'jd_skills', 'resume_parse', 'resume_screen',
  'email_draft', 'laya_rerank', 'chat_intent', 'interview_decision', 'guardrail',
];
const STATUSES = ['ok', 'blocked', 'error'];
const PAGE_SIZE = 25;

const statusBadge = { ok: 'badge-success', blocked: 'badge-warning', error: 'badge-danger' };

export default function AIAuditPanel() {
  const [filters, setFilters] = useState({ feature: '', status: '' });
  const [page, setPage] = useState(0);
  const [data, setData] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await aiAuditApi.list({
        feature: filters.feature || undefined,
        status: filters.status || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setData(res.data);
    } catch (err) {
      setError('Could not load the AI audit trail.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filters, page]);

  const setFilter = (key, value) => {
    setPage(0);
    setFilters((f) => ({ ...f, [key]: value }));
  };

  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));

  return (
    <div className="card" style={{ marginTop: '2rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
        <div>
          <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <ShieldCheck size={16} color="var(--primary)" /> AI Audit Trail
          </h3>
          <p style={{ margin: '0.2rem 0 0', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            Every model call, guardrail verdict and resume screening decision. Prompts and outputs are shown PII-redacted.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <select className="input-field" value={filters.feature} onChange={(e) => setFilter('feature', e.target.value)} style={{ fontSize: '0.8125rem', padding: '0.4rem 0.6rem' }}>
            <option value="">All features</option>
            {FEATURES.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          <select className="input-field" value={filters.status} onChange={(e) => setFilter('status', e.target.value)} style={{ fontSize: '0.8125rem', padding: '0.4rem 0.6rem' }}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button type="button" className="btn btn-secondary" onClick={load} disabled={loading} style={{ fontSize: '0.75rem', padding: '0.4rem 0.7rem' }}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      {error && <div style={{ color: 'var(--danger-text)', fontSize: '0.8125rem', marginBottom: '0.75rem' }}>{error}</div>}

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th />
              <th>Time</th>
              <th>Feature</th>
              <th>Provider / model</th>
              <th>Status</th>
              <th>Latency</th>
              <th>Tokens</th>
            </tr>
          </thead>
          <tbody>
            {data.items.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>{loading ? 'Loading…' : 'No AI activity recorded for these filters.'}</td></tr>
            )}
            {data.items.map((e) => {
              const open = expanded === e.id;
              return (
                <Fragment key={e.id}>
                  <tr onClick={() => setExpanded(open ? null : e.id)} style={{ cursor: 'pointer' }}>
                    <td>{open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>{e.created_at ? new Date(`${e.created_at}Z`).toLocaleString() : '—'}</td>
                    <td><code>{e.feature}</code></td>
                    <td>{e.provider}{e.model ? ` · ${e.model}` : ''}</td>
                    <td><span className={`badge ${statusBadge[e.status] || 'badge-neutral'}`}>{e.status}</span></td>
                    <td>{typeof e.latency_ms === 'number' ? `${Math.round(e.latency_ms)} ms` : '—'}</td>
                    <td>{e.prompt_tokens != null ? `${e.prompt_tokens} / ${e.completion_tokens ?? '—'}` : '—'}</td>
                  </tr>
                  {open && (
                    <tr>
                      <td colSpan={7} style={{ backgroundColor: 'var(--bg-subtle)' }}>
                        <div style={{ display: 'grid', gap: '0.6rem', fontSize: '0.75rem' }}>
                          <div><strong>Trace:</strong> {e.trace_id || '—'} · <strong>User:</strong> {e.user_id || 'system'}</div>
                          {e.error && <div style={{ color: 'var(--danger-text)' }}><strong>Error:</strong> {e.error}</div>}
                          {Object.keys(e.details || {}).length > 0 && (
                            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{JSON.stringify(e.details, null, 2)}</pre>
                          )}
                          {e.prompt_preview && (
                            <div><strong>Prompt (redacted preview):</strong><pre style={{ margin: '0.25rem 0 0', whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: '220px', overflowY: 'auto' }}>{e.prompt_preview}</pre></div>
                          )}
                          {e.output_preview && (
                            <div><strong>Output (redacted preview):</strong><pre style={{ margin: '0.25rem 0 0', whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: '220px', overflowY: 'auto' }}>{e.output_preview}</pre></div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.75rem', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
        <span>{data.total.toLocaleString()} event(s)</span>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button type="button" className="btn btn-secondary" disabled={page === 0 || loading} onClick={() => setPage((p) => p - 1)} style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem' }}>Previous</button>
          <span>Page {page + 1} of {pages}</span>
          <button type="button" className="btn btn-secondary" disabled={page + 1 >= pages || loading} onClick={() => setPage((p) => p + 1)} style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem' }}>Next</button>
        </div>
      </div>
    </div>
  );
}
