import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, Loader2, RefreshCw } from 'lucide-react';
import { requirementHistoryApi } from '../../lib/api';
import { HISTORY_ACTION_LABELS, formatDateTime, historyChanges } from '../../lib/requirements';
import DateRangeFilter from './DateRangeFilter';
import './requirements.css';

const PAGE = 50;

// Persistent log of demand creations, updates, status changes and deletions, newest first.
export default function RequirementHistory() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [action, setAction] = useState('');
  const [range, setRange] = useState({ from: '', to: '' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async (offset = 0) => {
    setLoading(true);
    setError(null);
    try {
      // Whole local days: start of the From day to the end of the To day, sent as UTC instants.
      const res = await requirementHistoryApi.list({
        limit: PAGE, offset, action: action || undefined,
        date_from: range.from ? new Date(`${range.from}T00:00:00`).toISOString() : undefined,
        date_to: range.to ? new Date(`${range.to}T23:59:59.999`).toISOString() : undefined,
      });
      setTotal(res.data.total);
      setItems((prev) => (offset === 0 ? res.data.items : [...prev, ...res.data.items]));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not load requirement history.');
    } finally {
      setLoading(false);
    }
  }, [action, range]);

  useEffect(() => { load(0); }, [load]);

  return (
    <section className="stack stack-loose" aria-label="Requirement History">
      <div className="cluster cluster-between">
        <span className="cluster">
          <label className="match-status">
            <span className="input-label jd-status-label">Show</span>
            <select className="input-field match-status-select" value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="">All changes</option>
              {Object.entries(HISTORY_ACTION_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          </label>
          <DateRangeFilter from={range.from} to={range.to} onChange={setRange} />
        </span>
        <span className="cluster cluster-tight">
          <span className="slug">{total} {total === 1 ? 'entry' : 'entries'}</span>
          <button type="button" className="btn btn-secondary btn-compact" onClick={() => load(0)} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : undefined} /> Refresh
          </button>
        </span>
      </div>

      {error && <p className="req-error" role="alert">{error}</p>}

      <ol className="history-list">
        {items.map((entry) => {
          const changes = historyChanges(entry);
          return (
            <li key={entry.id} className="card history-item">
              <div className="cluster cluster-between">
                <span className="cluster cluster-tight">
                  <span className={`badge history-${entry.action}`}>{HISTORY_ACTION_LABELS[entry.action] || entry.action}</span>
                  <strong>{entry.item_title || 'Untitled'}</strong>
                </span>
                <span className="slug">{formatDateTime(entry.created_at)}</span>
              </div>
              <p className="slug history-meta">
                {entry.demand_display_id && <span>Demand ID: <strong>{entry.demand_display_id}</strong>{entry.demand_name ? ` · ${entry.demand_name}` : ''}</span>}
                {entry.item_display_id && <span>Demand ID: <strong>{entry.item_display_id}</strong></span>}
                <span>By {entry.user_name || 'System'}</span>
              </p>
              {changes.length > 0 && (
                <ul className="history-changes">
                  {changes.map((c) => (
                    <li key={c.field}>
                      <span className="history-field">{c.field}</span>
                      {c.from !== null && <span className="history-value history-old">{c.from}</span>}
                      {c.from !== null && c.to !== null && <ArrowRight size={12} aria-label="changed to" />}
                      {c.to !== null && <span className="history-value history-new">{c.to}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>

      {loading && items.length === 0 && <p className="req-empty"><Loader2 size={16} className="animate-spin" /> Loading history…</p>}
      {!loading && !error && items.length === 0 && <p className="req-empty">{range.from || range.to || action ? 'No changes match the current filters.' : 'No changes recorded yet.'}</p>}
      {items.length < total && (
        <p><button type="button" className="btn btn-secondary btn-compact" onClick={() => load(items.length)} disabled={loading}>Load older entries</button></p>
      )}
    </section>
  );
}
