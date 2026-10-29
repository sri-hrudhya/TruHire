import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { FileText, MessageSquare } from 'lucide-react';
import { fromState } from '../../lib/navigation';
import { useMeta } from '../../context/MetaContext';
import StatusMark from '../ui/StatusMark';
import AssignmentPicker from '../review/AssignmentPicker';
import CommentThread from '../review/CommentThread';
import { EmailStatusBadge } from '../EmailComposer';
import './requirements.css';

const MAX_GAPS_SHOWN = 8;

// One ranked candidate for a requirement: score, who, why it ranked, then the review controls.
export default function MatchRow({ item, positionId, assignment, users, onStatus, onAssign, onPreview }) {
  const location = useLocation();
  const { requirement_statuses: statuses, default_requirement_status: defaultStatus } = useMeta();
  const [open, setOpen] = useState(false);
  const cand = item.candidate;
  const score = item.match_score ?? 0;
  const tone = score >= 80 ? 'high' : score >= 60 ? 'mid' : 'low';
  const matched = item.score_breakdown?.matched_skills || [];
  const gaps = item.score_breakdown?.missing_skills || [];
  const status = item.requirement_status || defaultStatus;

  return (
    <li className="match">
      <div className={`match-score match-score-${tone}`} aria-label={`Match score ${score.toFixed(1)} percent`}>
        <span className="match-score-num">{Math.round(score)}</span>
        <span className="match-score-unit">%</span>
      </div>

      <div className="match-body">
        <div className="cluster cluster-tight">
          <Link className="match-name" to={`/candidates/${cand.id}`} state={fromState(location, 'Requirements')}>{cand.candidate_name}</Link>
          <span className="slug">{cand.display_id || 'TRU-CN-????'}</span>
          {item.last_email && <EmailStatusBadge status={item.last_email.status} />}
        </div>
        <p className="slug">
          {cand.years_experience} yrs · {cand.education || 'Education not stated'}{cand.email ? ` · ${cand.email}` : ''}
        </p>
        {item.llm_summary && <p className="dek">{item.llm_summary}</p>}
        {item.cited_quote && <p className="match-cite">“{item.cited_quote}”</p>}
        {(matched.length > 0 || gaps.length > 0) && (
          <p className="match-skills">
            {matched.length > 0 && <span><strong>Matches</strong> {matched.join(', ')}</span>}
            {gaps.length > 0 && (
              <span className="match-gaps"><strong>Gaps</strong> {gaps.slice(0, MAX_GAPS_SHOWN).join(', ')}{gaps.length > MAX_GAPS_SHOWN ? ` +${gaps.length - MAX_GAPS_SHOWN} more` : ''}</span>
            )}
          </p>
        )}
        {open && <div className="match-thread"><CommentThread candidateId={cand.id} positionId={positionId} /></div>}
      </div>

      <div className="match-controls">
        <label className="match-status">
          <StatusMark status={status} />
          <span className="sr-only">Status of {cand.candidate_name}</span>
          <select className="input-field match-status-select" value={status} onChange={(e) => onStatus(cand.id, e.target.value)}>
            {statuses.map((st) => <option key={st} value={st}>{st}</option>)}
          </select>
        </label>
        <AssignmentPicker candidateName={cand.candidate_name} assignment={assignment} users={users} onAssign={(assigneeId) => onAssign(cand.id, assigneeId)} />
        <span className="cluster cluster-tight">
          <button type="button" className="btn btn-secondary btn-compact" onClick={() => onPreview(cand)}>
            <FileText size={14} /> Resume
          </button>
          <button type="button" className="btn btn-secondary btn-compact" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            <MessageSquare size={14} /> {open ? 'Hide feedback' : 'Feedback'}
          </button>
        </span>
      </div>
    </li>
  );
}
