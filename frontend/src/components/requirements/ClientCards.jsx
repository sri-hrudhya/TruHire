import { Building2 } from 'lucide-react';
import { groupByClient } from '../../lib/requirements';
import './requirements.css';

// Client folders. Inside a practice they list that practice's clients; on the client-wise landing they list every
// client, and `practiceName` (when given) adds a "Java 2 · Pega 1" breakdown of where its demands are filed.
export default function ClientCards({ jds, loading, onOpen, practiceName, emptyText = 'No demands in this practice yet.', label = 'Clients in this practice' }) {
  const clients = groupByClient(jds);

  if (!clients.length) {
    return <p className="req-empty">{loading ? 'Loading client folders…' : emptyText}</p>;
  }

  return (
    <ul className="card-grid card-grid-wide" aria-label={label}>
      {clients.map(({ name, items, cancelled, practices }) => {
        const live = items.length - cancelled;
        const breakdown = practiceName
          ? [...practices.entries()].map(([id, n]) => `${practiceName(id) || 'No practice'} ${n}`).join(' · ')
          : '';
        return (
          <li key={name || '__unassigned'}>
            <button type="button" className="card card-hover info-card client-folder-card" onClick={() => onOpen(name)}>
              <span className="info-card-title"><Building2 size={18} aria-hidden="true" />{name || 'No client assigned'}</span>
              {breakdown && <span className="slug">{breakdown}</span>}
              <span className="info-card-count">
                <span className="info-card-count-num">{live}</span> {live === 1 ? 'demand' : 'demands'}
                {cancelled > 0 && <span className="slug"> · {cancelled} cancelled</span>}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
