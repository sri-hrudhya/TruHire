import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, Mail, Search } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import Notice from '../ui/Notice';
import MatchRow from './MatchRow';
import './requirements.css';

export default function RequirementMatches({
  jd, matches, loading, minScore, coverage, statusError, assignments, users, shortlistedCount,
  onStatus, onAssign, onPreview, onEmail,
}) {
  const { user } = useAuth();
  const [mineOnly, setMineOnly] = useState(false);
  const shown = mineOnly ? matches.filter((m) => assignments[m.candidate.id]?.assignee?.id === user?.id) : matches;

  return (
    <div className="stack stack-loose">
      <div className="cluster cluster-end">
        <span className="cluster cluster-tight">
          <label className="cluster cluster-tight dek">
            <input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} /> Assigned to me
          </label>
          <button type="button" className="btn btn-primary btn-compact" onClick={onEmail} disabled={loading || shortlistedCount === 0}
            title={shortlistedCount ? 'Draft emails for shortlisted candidates' : 'Shortlist a candidate first'}>
            <Mail size={14} /> Email shortlisted ({shortlistedCount})
          </button>
          <Link to="/search" className="btn btn-secondary btn-compact"><Search size={14} /> Search</Link>
        </span>
      </div>

      {!loading && coverage && (coverage.unindexed > 0 || coverage.lexicalDown) && (
        <Notice type="warning">
          {coverage.unindexed > 0 && `${coverage.unindexed} resume(s) are not in the search index and cannot be scored until they are reindexed. `}
          {coverage.lexicalDown && 'Keyword search is unavailable, so scores rely on meaning alone and read lower than usual.'}
        </Notice>
      )}
      {statusError && <Notice type="error">{statusError}</Notice>}

      {loading ? (
        <p className="req-empty"><Loader2 size={18} className="animate-spin" /> Scoring candidates against this requirement…</p>
      ) : shown.length === 0 ? (
        <p className="req-empty">
          {mineOnly ? 'Nothing is assigned to you for this requirement.' : `No candidates at or above ${minScore ?? 'the minimum'}%. Ingest more resumes, or use Search to see every score.`}
        </p>
      ) : (
        <ul className="match-list">
          {shown.map((item) => (
            <MatchRow
              key={item.candidate.id}
              item={item}
              positionId={jd.id}
              assignment={assignments[item.candidate.id]}
              users={users}
              onStatus={onStatus}
              onAssign={onAssign}
              onPreview={onPreview}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
