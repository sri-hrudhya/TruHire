import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, Users } from 'lucide-react';
import { candidatesApi } from '../lib/api';
import './candidate-detail.css';
import { formatIst } from '../lib/datetime';

const PAGE_SIZE = 25;

export default function CandidateHistoryPage() {
  const [query, setQuery] = useState('');
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async (needle, start, append = false) => {
    setLoading(true);
    setError('');
    try {
      const response = await candidatesApi.list({ q: needle, offset: start, limit: PAGE_SIZE, with_requirements: true });
      setRows((previous) => append ? [...previous, ...(response.data.candidates || [])] : (response.data.candidates || []));
      setTotal(response.data.total || 0);
      setOffset(start);
    } catch {
      setError('Could not load candidates. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => load(query.trim(), 0), 250);
    return () => window.clearTimeout(timer);
  }, [query, load]);

  return (
    <div className="page-body">
      <div className="page-header">
        <div>
          <h1>Candidate History</h1>
          <p className="dek">All candidates ingested into TruHire, and the requirement each one was submitted to, with its current status.</p>
        </div>
        <span className="badge badge-neutral"><Users size={14} /> {total} candidates</span>
      </div>

      <label className="candidate-directory-search">
        <Search size={18} aria-hidden="true" />
        <input className="input-field" value={query} onChange={(event) => setQuery(event.target.value)}
          placeholder="Search name, contact, email, company or candidate ID" aria-label="Search candidates" />
      </label>

      {error && <div role="alert" className="badge-danger" style={{ padding: '0.75rem 1rem', marginTop: '1rem' }}>{error}</div>}
      <div className="card" style={{ marginTop: '1rem' }}>
        <div className="table-container">
          <table className="data-table">
            <thead><tr><th>Candidate</th><th>Email</th><th>Phone</th><th>Current company</th><th>Submitted to - Current status</th><th>Availability</th></tr></thead>
            <tbody>
              {rows.map((candidate) => <tr key={candidate.id}>
                <td><Link to={`/candidates/${candidate.id}`} style={{ fontWeight: 700 }}>{candidate.candidate_name}</Link>
                  <div className="text-subtle" style={{ fontSize: '0.75rem' }}>{candidate.display_id}</div></td>
                <td>{candidate.email || '—'}</td>
                <td>{candidate.phone || '—'}</td>
                <td>{candidate.current_company || '—'}</td>
                <td>{candidate.requirements?.length ? <ul className="candidate-requirement-history">
                  {candidate.requirements.map((item) => <li key={item.id}>
                    <strong>{item.client_name || item.display_id || item.title} - {item.status}</strong>
                    {item.last_modified && <small>Last modified {formatIst(item.last_modified)}{item.modified_by ? ` | Modified by ${item.modified_by}` : ''}</small>}
                  </li>)}
                </ul> : <span className="text-subtle">Not submitted yet</span>}</td>
                <td><span className={`badge ${candidate.availability_status === 'Not Active' ? 'badge-neutral' : 'badge-success'}`}>{candidate.availability_status || 'Active'}</span></td>
              </tr>)}
              {!loading && rows.length === 0 && <tr><td colSpan="6" style={{ textAlign: 'center', padding: '2rem' }}>No candidates found.</td></tr>}
              {loading && rows.length === 0 && <tr><td colSpan="6" style={{ textAlign: 'center', padding: '2rem' }}>Loading candidates…</td></tr>}
            </tbody>
          </table>
        </div>
        {rows.length < total && <div style={{ padding: '1rem', textAlign: 'center' }}>
          <button type="button" className="btn btn-secondary" disabled={loading}
            onClick={() => load(query.trim(), offset + PAGE_SIZE, true)}>{loading ? 'Loading…' : 'Load more'}</button>
        </div>}
      </div>
    </div>
  );
}
