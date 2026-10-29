import { Layers, Plus } from 'lucide-react';
import './requirements.css';

// The landing grid: the New Requirement tile followed by the five practices, sized to fill the screen.
// Client names belong to individual demands, not to the practice cards.
// A practice counts only live demands (Cancelled ones stay on record but are left out).
export default function DemandCards({ demands, loading, onOpen, onCreate }) {
  return (
    <ul className="landing-grid" aria-label="Demand practices">
      <li>
        <button type="button" className="new-req-card" onClick={onCreate}>
          <span className="new-req-icon" aria-hidden="true"><Plus size={28} /></span>
          <span className="new-req-text">
            <span className="new-req-title">New Requirement</span>
            <span className="new-req-hint">Upload a demand file or write one. Choose its practice: Java, GenAI, Camunda, Pega or Others.</span>
          </span>
        </button>
      </li>
      {demands.length === 0 && <li className="landing-note"><p className="req-empty">{loading ? 'Loading demands…' : 'No demand practices are available.'}</p></li>}
      {demands.map((d) => (
        <li key={d.id}>
          <button type="button" className="card card-hover info-card folder-card" onClick={() => onOpen(d.id)} aria-label={`${d.name}, ${d.position_count || 0} demand${d.position_count === 1 ? '' : 's'}`}>
            <span className="info-card-title folder-card-title"><Layers size={20} aria-hidden="true" /> {d.name}</span>
            <dl className="info-card-facts">
              {d.created_by_name && <div><dt>Created By</dt><dd>{d.created_by_name}</dd></div>}
            </dl>
            <span className="info-card-count"><span className="info-card-count-num">{d.position_count || 0}</span> {d.position_count === 1 ? 'demand' : 'demands'}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
