import { Trash2 } from 'lucide-react';
import { formatDate, formatExperience, showRole } from '../../lib/requirements';
import JdStatusBadge from './JdStatusBadge';
import './requirements.css';

const Fact = ({ label, children }) => <div><dt>{label}</dt><dd>{children}</dd></div>;

// One card per JD of the chosen demand. The whole card opens the JD; the bin removes it.
export default function JdCards({ jds, loading, onOpen, onDelete, onCreate }) {
  if (jds.length === 0) {
    return (
      <p className="req-empty">
        {loading ? 'Loading requirements…' : 'No JDs under this demand yet.'}
        {!loading && <button type="button" className="link-btn" onClick={onCreate}>Create one</button>}
      </p>
    );
  }

  return (
    <ul className="card-grid card-grid-wide" aria-label="Job descriptions">
      {jds.map((jd) => (
        <li key={jd.id} className="info-card-wrap">
          <button type="button" className="card card-hover info-card" onClick={() => onOpen(jd)}>
            <span className="cluster cluster-between">
              <span className="slug">{jd.display_id || 'TRU-JD-????'} · v{jd.jd_version}</span>
              <JdStatusBadge status={jd.status} />
            </span>
            <span className="info-card-title">{jd.title}</span>
            <dl className="info-card-rows">
              {showRole(jd) && <Fact label="Role">{jd.role}</Fact>}
              <div className="info-card-row">
                <Fact label="Location">{jd.location || '—'}</Fact>
                <Fact label="Experience">{formatExperience(jd.experience_years)}</Fact>
              </div>
              <div className="info-card-row">
                <Fact label="Start Date">{formatDate(jd.start_date)}</Fact>
                <Fact label="End Date">{formatDate(jd.end_date)}</Fact>
              </div>
              <div className="info-card-row">
                <Fact label="Created By">{jd.created_by_name || '—'}</Fact>
                <Fact label="Created On">{formatDate(jd.created_at)}</Fact>
              </div>
            </dl>
          </button>
          <button type="button" className="icon-btn info-card-remove" onClick={() => onDelete(jd)} aria-label={`Remove ${jd.title}`}>
            <Trash2 size={14} />
          </button>
        </li>
      ))}
    </ul>
  );
}
