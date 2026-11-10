import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Download, Loader2 } from 'lucide-react';
import { trackerApi } from '../../lib/api';
import { formatIst } from '../../lib/datetime';
import { fromState } from '../../lib/navigation';
import Notice from '../ui/Notice';
import './tracker.css';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}T/;
const shown = (key, value) => (key === 'source_date' && ISO_DATE.test(value || '') ? formatIst(value) : value || '');

function exportCsv(columns, rows) {
  const quote = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const lines = [['Client', 'Demand', ...columns.map((c) => c.label)].map(quote).join(',')];
  rows.forEach((r) => lines.push([r.client_name, `${r.demand_id || ''} ${r.demand_title}`.trim(),
    ...columns.map((c) => shown(c.key, r.values[c.key]))].map(quote).join(',')));
  const url = URL.createObjectURL(new Blob([`﻿${lines.join('\r\n')}`], { type: 'text/csv;charset=utf-8' }));
  const link = Object.assign(document.createElement('a'), { href: url, download: 'requirement-tracker.csv' });
  link.click();
  URL.revokeObjectURL(url);
}

// The tracker table for one demand, one row per submitted candidate. Read-only: values come from the candidate record and resume.
export default function RequirementTracker({ positionId }) {
  const location = useLocation();
  const [data, setData] = useState({ columns: [], rows: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let live = true;
    setLoading(true);
    trackerApi.list({ position_id: positionId })
      .then((res) => { if (live) { setData(res.data); setError(''); } })
      .catch(() => { if (live) setError('Could not load the tracker. Please try again.'); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [positionId]);

  return (
    <div className="stack stack-loose">
      <div className="cluster cluster-between">
        <p className="dek">Candidates submitted to this demand. Values come from the candidate record and what the resume states; blank means not stated.</p>
        <button type="button" className="btn btn-secondary btn-compact" disabled={!data.rows.length} onClick={() => exportCsv(data.columns, data.rows)}>
          <Download size={14} /> Export CSV
        </button>
      </div>
      {error && <Notice type="error">{error}</Notice>}
      {loading ? <p className="req-empty"><Loader2 size={18} className="animate-spin" /> Loading tracker…</p>
        : !data.rows.length ? <p className="req-empty">No candidate has been submitted yet. Set a status for a candidate on a demand and it appears here.</p>
        : (
          <div className="tracker-scroll">
            <table className="tracker-table">
              <thead><tr>
                {data.columns.map((c) => <th key={c.key}>{c.label}</th>)}
              </tr></thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={`${row.position_id}:${row.candidate_id}`}>
                    {data.columns.map((c) => (
                      <td key={c.key}>
                        {c.key === 'candidate_name'
                          ? <Link to={`/candidates/${row.candidate_id}`} state={fromState(location, 'Tracker')} className="tracker-link">{row.values.candidate_name}</Link>
                          : shown(c.key, row.values[c.key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  );
}
