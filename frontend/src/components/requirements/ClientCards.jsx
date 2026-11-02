import { Building2 } from 'lucide-react';
import './requirements.css';

// A demand practice opens into its client folders before showing individual requirements.
export default function ClientCards({ jds, loading, onOpen }) {
  const groups = new Map();
  for (const jd of jds) {
    const key = (jd.client_name || '').trim() || '';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(jd);
  }
  const clients = [...groups.entries()].sort(([a], [b]) => {
    if (!a) return 1;
    if (!b) return -1;
    return a.localeCompare(b, undefined, { sensitivity: 'base' });
  });

  if (!clients.length) {
    return <p className="req-empty">{loading ? 'Loading client folders…' : 'No demands in this practice yet.'}</p>;
  }

  return (
    <ul className="card-grid card-grid-wide" aria-label="Clients in this practice">
      {clients.map(([name, requirements]) => (
        <li key={name || '__unassigned'}>
          <button type="button" className="card card-hover info-card client-folder-card" onClick={() => onOpen(name)}>
            <span className="info-card-title"><Building2 size={18} aria-hidden="true" />{name || 'No client assigned'}</span>
            <span className="info-card-count"><span className="info-card-count-num">{requirements.length}</span> {requirements.length === 1 ? 'demand' : 'demands'}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
