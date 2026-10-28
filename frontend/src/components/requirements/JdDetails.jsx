import { useState } from 'react';
import { Check, ExternalLink, Pencil, X } from 'lucide-react';
import { formatDate, formatDateTime, formatExperience, showRole } from '../../lib/requirements';
import JdBody from './JdBody';
import JdStatusBadge from './JdStatusBadge';
import StatusNote from './StatusNote';
import StatusSelect from './StatusSelect';
import './requirements.css';

const Group = ({ title, rows }) => (
  <section className="detail-group" aria-label={title}>
    <h3 className="detail-heading">{title}</h3>
    <dl className="detail-grid">
      {rows.filter(Boolean).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
    </dl>
  </section>
);

// Complete details of one demand, grouped: overview, schedule, record; then summary and full text.
// The single Edit button lives here (the page has no separate Edit tab).
// The end date is tentative: change or clear it in place, without opening the full editor.
function EndDate({ jd, onSave }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const save = async (next) => {
    setBusy(true);
    const ok = await onSave(next);
    setBusy(false);
    if (ok) setEditing(false);
  };
  if (!editing) {
    return (
      <span className="cluster cluster-tight">
        {formatDate(jd.end_date)}
        <button type="button" className="link-btn" onClick={() => { setValue(jd.end_date || ''); setEditing(true); }}>{jd.end_date ? 'Edit' : 'Set'}</button>
        {jd.end_date && <button type="button" className="link-btn" disabled={busy} onClick={() => save(null)}>Clear</button>}
      </span>
    );
  }
  return (
    <span className="cluster cluster-tight">
      <input type="date" className="input-field end-date-input" value={value} min={jd.start_date || undefined} onChange={(e) => setValue(e.target.value)} aria-label="Tentative end date" />
      <button type="button" className="icon-btn" disabled={busy || !value} onClick={() => save(value)} aria-label="Save end date"><Check size={14} /></button>
      <button type="button" className="icon-btn" disabled={busy} onClick={() => setEditing(false)} aria-label="Cancel"><X size={14} /></button>
    </span>
  );
}

export default function JdDetails({ jd, demandName, onStatus, onEdit, onOpenFile, onEndDate }) {
  return (
    <div className="stack stack-loose">
      <div className="detail-toolbar">
        <div className="match-status">
          <span className="input-label jd-status-label">Demand Status</span>
          <StatusSelect className="input-field match-status-select" ariaLabel="Demand status" value={jd.status || 'Open'}
            reason={jd.cancellation_reason || ''} resumes={jd.mapped_resumes || []}
            onChange={(status, extras) => onStatus(status, extras)} />
          <StatusNote jd={jd} />
        </div>
        <button type="button" className="btn btn-secondary btn-compact" onClick={onEdit}><Pencil size={14} /> Edit</button>
      </div>

      <div className="detail-groups">
        <Group title="Overview" rows={[
          ['Demand ID', `${jd.display_id || '—'} · v${jd.jd_version}`],
          ['Folder', demandName || '—'],
          ['Client', jd.client_name || '—'],
          showRole(jd) && ['Role', jd.role],
          ['Location', jd.location || '—'],
          ['Experience', formatExperience(jd.experience_years, jd.experience_max_years)],
        ]} />
        <Group title="Schedule" rows={[
          ['Start Date', formatDate(jd.start_date)],
          ['End Date (tentative)', <EndDate key="end" jd={jd} onSave={onEndDate} />],
        ]} />
        <Group title="Record" rows={[
          ['Created By', jd.created_by_name || '—'],
          ['Created On', formatDate(jd.created_at)],
          ['Last Modified On', formatDateTime(jd.last_modified_at || jd.created_at)],
          ['Last Modified By', jd.last_modified_by || jd.created_by_name || '—'],
          jd.file_url && ['Source file', (
            <button type="button" className="link-btn" onClick={onOpenFile}>{jd.original_filename || 'Open file'} <ExternalLink size={11} aria-hidden="true" /></button>
          )],
        ]} />
      </div>

      {jd.jd_summary && (
        <div className="req-summary">
          <h3>Summary · version {jd.jd_version}</h3>
          <p>{jd.jd_summary}</p>
        </div>
      )}

      <section>
        <h3 className="detail-heading">Demand description</h3>
        <JdBody text={jd.jd_text} />
      </section>
    </div>
  );
}
