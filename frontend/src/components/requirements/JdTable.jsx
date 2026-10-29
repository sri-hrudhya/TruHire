import { useState } from 'react';
import { Copy, Plus, Search, Trash2 } from 'lucide-react';
import { filterDemands, formatDate, formatExperience, formatLocations, formatPositions } from '../../lib/requirements';
import JdStatusBadge from './JdStatusBadge';
import './requirements.css';

// Spreadsheet-style view of demands: one row per demand, one column per detail.
// `practiceName` maps a demand's practice id to its name (shown as a column, since the rows can span practices).
export default function JdTable({ jds, loading, practiceName, onOpen, onDelete, onDuplicate, onCreate }) {
  const [query, setQuery] = useState('');
  const shown = filterDemands(jds, query);

  return (
    <div className="stack">
      <div className="cluster cluster-between">
        <div className="folder-search">
          <Search size={16} aria-hidden="true" />
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by demand ID or title" aria-label="Search demands by ID or title" />
          <span className="slug" role="status">{query ? `${shown.length} of ${jds.length}` : `${jds.length} ${jds.length === 1 ? 'demand' : 'demands'}`}</span>
        </div>
        <button type="button" className="btn btn-primary btn-compact" onClick={onCreate}><Plus size={14} /> New demand</button>
      </div>

      {jds.length === 0 ? (
        <p className="req-empty">{loading ? 'Loading demands…' : 'No demands yet.'}</p>
      ) : shown.length === 0 ? (
        <p className="req-empty">No demands match “{query.trim()}”.</p>
      ) : (
        <div className="req-table-wrap" tabIndex={0} role="region" aria-label="Demands table">
          <table className="req-table">
            <thead>
              <tr>
                <th scope="col">Demand ID</th>
                <th scope="col">Title</th>
                <th scope="col">Practice</th>
                <th scope="col">Client</th>
                <th scope="col">Locations</th>
                <th scope="col">Experience</th>
                <th scope="col" className="num">Positions</th>
                <th scope="col">Status</th>
                <th scope="col">Start Date</th>
                <th scope="col">End Date</th>
                <th scope="col">Created By</th>
                <th scope="col">Created On</th>
                <th scope="col">Last Modified</th>
                <th scope="col"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((jd) => (
                <tr key={jd.id}>
                  <td className="nowrap">{jd.display_id || '—'}</td>
                  <td className="req-table-title"><button type="button" className="link-btn" onClick={() => onOpen(jd)}>{jd.title}</button></td>
                  <td className="nowrap">{practiceName(jd.demand_id) || '—'}</td>
                  <td>{jd.client_name || '—'}</td>
                  <td>{formatLocations(jd)}</td>
                  <td className="nowrap">{formatExperience(jd.experience_years, jd.experience_max_years)}</td>
                  <td className="num">{formatPositions(jd.no_of_positions)}</td>
                  <td className="nowrap"><JdStatusBadge status={jd.status} /></td>
                  <td className="nowrap">{formatDate(jd.start_date)}</td>
                  <td className="nowrap">{formatDate(jd.end_date)}</td>
                  <td>{jd.created_by_name || '—'}</td>
                  <td className="nowrap">{formatDate(jd.created_at)}</td>
                  <td className="nowrap">{formatDate(jd.last_modified_at || jd.created_at)}{jd.last_modified_by ? ` · ${jd.last_modified_by}` : ''}</td>
                  <td className="nowrap req-table-actions">
                    <span className="cluster cluster-tight">
                      <button type="button" className="icon-btn" onClick={() => onDuplicate(jd)} aria-label={`Duplicate ${jd.title}`} title="Duplicate this demand"><Copy size={14} /></button>
                      <button type="button" className="icon-btn" onClick={() => onDelete(jd)} aria-label={`Remove ${jd.title}`} title="Remove this demand"><Trash2 size={14} /></button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
