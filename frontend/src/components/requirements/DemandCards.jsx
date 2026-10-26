import { Layers } from 'lucide-react';
import { formatDate } from '../../lib/requirements';
import './requirements.css';

// The five demands as cards: Demand ID, title, Created On, Created By. Opening one shows its JDs.
export default function DemandCards({ demands, loading, onOpen }) {
  if (loading && demands.length === 0) return <p className="req-empty">Loading demands…</p>;
  if (demands.length === 0) return <p className="req-empty">No demands are available.</p>;

  return (
    <ul className="card-grid" aria-label="Demands">
      {demands.map((d) => (
        <li key={d.id}>
          <button type="button" className="card card-hover info-card" onClick={() => onOpen(d.id)} aria-label={`${d.name}, ${d.jd_count} requirement${d.jd_count === 1 ? '' : 's'}`}>
            <span className="slug">{d.display_id || d.id}</span>
            <span className="info-card-title"><Layers size={16} aria-hidden="true" /> {d.name}</span>
            <dl className="info-card-facts">
              <div><dt>Created On</dt><dd>{formatDate(d.created_at)}</dd></div>
              {d.created_by_name && <div><dt>Created By</dt><dd>{d.created_by_name}</dd></div>}
            </dl>
            <span className="info-card-count">{d.jd_count} {d.jd_count === 1 ? 'JD' : 'JDs'}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
