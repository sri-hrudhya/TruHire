import { ExternalLink, Pencil } from 'lucide-react';
import { useMeta } from '../../context/MetaContext';
import { formatDate, formatExperience, showRole } from '../../lib/requirements';
import JdBody from './JdBody';
import './requirements.css';

const Group = ({ title, rows }) => (
  <section className="detail-group" aria-label={title}>
    <h3 className="detail-heading">{title}</h3>
    <dl className="detail-grid">
      {rows.filter(Boolean).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
    </dl>
  </section>
);

// Complete details of one JD, grouped: overview, schedule, record; then summary and full text.
// The single Edit button lives here (the page has no separate Edit tab).
export default function JdDetails({ jd, demandName, onStatus, onEdit, onOpenFile }) {
  const { jd_statuses: statuses } = useMeta();

  return (
    <div className="stack stack-loose">
      <div className="detail-toolbar">
        <label className="match-status">
          <span className="input-label jd-status-label">JD Status</span>
          <select className="input-field match-status-select" value={jd.status || 'Open'} onChange={(e) => onStatus(e.target.value)} aria-label="JD status">
            {statuses.map((st) => <option key={st} value={st}>{st}</option>)}
          </select>
        </label>
        <button type="button" className="btn btn-secondary btn-compact" onClick={onEdit}><Pencil size={14} /> Edit</button>
      </div>

      <div className="detail-groups">
        <Group title="Overview" rows={[
          ['JD ID', `${jd.display_id || '—'} · v${jd.jd_version}`],
          ['Demand', demandName || '—'],
          showRole(jd) && ['Role', jd.role],
          ['Location', jd.location || '—'],
          ['Experience', formatExperience(jd.experience_years)],
        ]} />
        <Group title="Schedule" rows={[
          ['Start Date', formatDate(jd.start_date)],
          ['End Date', formatDate(jd.end_date)],
        ]} />
        <Group title="Record" rows={[
          ['Created By', jd.created_by_name || '—'],
          ['Created On', formatDate(jd.created_at)],
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
        <h3 className="detail-heading">Job Description</h3>
        <JdBody text={jd.jd_text} />
      </section>
    </div>
  );
}
