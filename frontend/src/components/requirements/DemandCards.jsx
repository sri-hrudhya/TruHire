import { Layers, Plus } from 'lucide-react';
import { clientSummary, formatDate } from '../../lib/requirements';
import './requirements.css';

// The landing grid: the New Requirement tile followed by the five folders, sized to fill the screen.
// A folder counts only live demands (Cancelled ones stay on record but are left out).
export default function DemandCards({ demands, loading, onOpen, onCreate }) {
  return (
    <ul className="landing-grid" aria-label="Demand folders">
      <li>
        <button type="button" className="new-req-card" onClick={onCreate}>
          <span className="new-req-icon" aria-hidden="true"><Plus size={28} /></span>
          <span className="new-req-text">
            <span className="new-req-title">New Requirement</span>
            <span className="new-req-hint">Upload a demand file or write one. It is filed under Java, GenAI, Camunda, Pega or Others automatically.</span>
          </span>
        </button>
      </li>
      {demands.length === 0 && <li className="landing-note"><p className="req-empty">{loading ? 'Loading demands…' : 'No demand folders are available.'}</p></li>}
      {demands.map((d) => (
        <li key={d.id}>
          <button type="button" className="card card-hover info-card folder-card" onClick={() => onOpen(d.id)} aria-label={`${d.name}, ${d.jd_count} demand${d.jd_count === 1 ? '' : 's'}`}>
            <span className="slug">{d.display_id || d.id}</span>
            <span className="info-card-title folder-card-title"><Layers size={20} aria-hidden="true" /> {d.name}</span>
            <dl className="info-card-facts">
              <div><dt>Client</dt><dd>{clientSummary(d.clients, d.unassigned_client_count)}</dd></div>
              <div><dt>Created On</dt><dd>{formatDate(d.created_at)}</dd></div>
              {d.created_by_name && <div><dt>Created By</dt><dd>{d.created_by_name}</dd></div>}
            </dl>
            <span className="info-card-count"><span className="info-card-count-num">{d.jd_count}</span> {d.jd_count === 1 ? 'demand' : 'demands'}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
