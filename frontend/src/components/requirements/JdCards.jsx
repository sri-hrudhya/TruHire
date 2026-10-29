import { useState } from 'react';
import { Copy, Search, Trash2 } from 'lucide-react';
import { filterDemands, formatDate, formatExperience, formatLocations, formatPositions, showRole } from '../../lib/requirements';
import JdStatusBadge from './JdStatusBadge';
import StatusNote from './StatusNote';
import './requirements.css';

const Fact = ({ label, children }) => <div><dt>{label}</dt><dd>{children}</dd></div>;

// One card per demand of the chosen practice, already in status order. The whole card opens the demand; the copy icon
// starts a new demand from it and the bin removes it. The search box filters this practice only, by demand ID or title (partial, any case).
export default function JdCards({ jds, loading, onOpen, onDelete, onDuplicate, onCreate }) {
  const [query, setQuery] = useState('');
  const shown = filterDemands(jds, query);

  if (jds.length === 0) {
    return (
      <p className="req-empty">
        {loading ? 'Loading demands…' : 'No demands in this practice yet.'}
        {!loading && <button type="button" className="link-btn" onClick={onCreate}>Create one</button>}
      </p>
    );
  }

  return (
    <div className="stack">
      <div className="folder-search">
        <Search size={16} aria-hidden="true" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search this practice by demand ID or title"
          aria-label="Search demands in this practice by ID or title"
        />
        {query && <span className="slug" role="status">{shown.length} of {jds.length}</span>}
      </div>
      {shown.length === 0 ? (
        <p className="req-empty">No demands match “{query.trim()}”.</p>
      ) : (
        <ul className="card-grid card-grid-wide" aria-label="Demands">
          {shown.map((jd) => (
            <li key={jd.id} className={`info-card-wrap${['Cancelled', 'Mapped', 'Fulfilled'].includes(jd.status) ? ' has-note' : ''}`}>
              <button type="button" className="card card-hover info-card" onClick={() => onOpen(jd)}>
                <span className="cluster cluster-between">
                  <span className="slug">{jd.display_id || 'DM-????'}</span>
                  <JdStatusBadge status={jd.status} />
                </span>
                <span className="info-card-title">{jd.title}</span>
                <dl className="info-card-rows">
                  <div className="info-card-row">
                    <Fact label="Client">{jd.client_name || '—'}</Fact>
                    <Fact label="Positions">{formatPositions(jd.no_of_positions)}</Fact>
                  </div>
                  {showRole(jd) && <div className="info-card-row"><Fact label="Role">{jd.role}</Fact></div>}
                  <div className="info-card-row">
                    <Fact label="Locations">{formatLocations(jd)}</Fact>
                    <Fact label="Experience">{formatExperience(jd.experience_years, jd.experience_max_years)}</Fact>
                  </div>
                  <div className="info-card-row">
                    <Fact label="Start Date">{formatDate(jd.start_date)}</Fact>
                    <Fact label="End Date (tentative)">{formatDate(jd.end_date)}</Fact>
                  </div>
                  <div className="info-card-row">
                    <Fact label="Created By">{jd.created_by_name || '—'}</Fact>
                    <Fact label="Created On">{formatDate(jd.created_at)}</Fact>
                  </div>
                  <div className="info-card-row">
                    <Fact label="Last Modified On">{formatDate(jd.last_modified_at || jd.created_at)}</Fact>
                    <Fact label="Last Modified By">{jd.last_modified_by || jd.created_by_name || '—'}</Fact>
                  </div>
                </dl>
              </button>
              <span className="info-card-note"><StatusNote jd={jd} /></span>
              <button type="button" className="icon-btn info-card-copy" onClick={() => onDuplicate(jd)} aria-label={`Duplicate ${jd.title}`} title="Duplicate this demand">
                <Copy size={14} />
              </button>
              <button type="button" className="icon-btn info-card-remove" onClick={() => onDelete(jd)} aria-label={`Remove ${jd.title}`}>
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
