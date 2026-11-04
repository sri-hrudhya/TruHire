import { Building2 } from 'lucide-react';
import { groupByClient } from '../../lib/requirements';
import { NewRequirementTile } from './DemandCards';
import './requirements.css';

// Client folders, laid out and sized exactly like the practice folders (DemandCards). Inside a practice they list that
// practice's clients; on the client-wise landing they list every client. The big number is the positions opened
// (cancelled demands excluded).
export default function ClientCards({ jds, loading, onOpen, onCreate, emptyText = 'No demands in this practice yet.', label = 'Clients in this practice' }) {
  const clients = groupByClient(jds);

  if (!clients.length) {
    return <p className="req-empty">{loading ? 'Loading client folders…' : emptyText}</p>;
  }

  return (
    <ul className="landing-grid" aria-label={label}>
      {onCreate && <NewRequirementTile onCreate={onCreate} />}
      {clients.map(({ name, items, cancelled, positions }) => {
        const live = items.length - cancelled;
        return (
          <li key={name || '__unassigned'}>
            <button type="button" className="card card-hover info-card folder-card" onClick={() => onOpen(name)}
              aria-label={`${name || 'No client assigned'}, ${positions} position${positions === 1 ? '' : 's'}`}>
              <span className="info-card-title folder-card-title"><Building2 size={20} aria-hidden="true" /> {name || 'No client assigned'}</span>
              <dl className="info-card-facts">
                <div><dt>Demands</dt><dd>{live}{cancelled > 0 ? ` (+${cancelled} cancelled)` : ''}</dd></div>
              </dl>
              <span className="info-card-count"><span className="info-card-count-num">{positions}</span> {positions === 1 ? 'position' : 'positions'}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
