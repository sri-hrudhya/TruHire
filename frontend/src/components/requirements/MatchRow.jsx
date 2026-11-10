import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { FileText, MessageSquare } from 'lucide-react';
import { fromState } from '../../lib/navigation';
import { useMeta } from '../../context/MetaContext';
import StatusMark from '../ui/StatusMark';
import { skillCoverage } from '../../lib/requirements';
import AssignmentPicker from '../review/AssignmentPicker';
import CommentThread from '../review/CommentThread';
import { EmailStatusBadge } from '../EmailComposer';
import './requirements.css';

// Skills as small chips, capped so a row stays one glance tall.
function Chips({ label, skills, tone, max = 6 }) {
  if (!skills.length) return null;
  return (
    <span className="match-chips">
      <strong>{label}</strong>
      {skills.slice(0, max).map((skill) => <span key={skill} className={`chip chip-${tone}`}>{skill}</span>)}
      {skills.length > max && <span className="slug">+{skills.length - max} more</span>}
    </span>
  );
}

// One ranked candidate for a requirement, kept compact: who, matching / not matching %, what matches and what is
// missing. Clicking the row opens the full candidate page; the review controls stay on the right.
export default function MatchRow({ item, positionId, assignment, users, onStatus, onAssign, onPreview }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { requirement_statuses: statuses, default_requirement_status: defaultStatus } = useMeta();
  const [open, setOpen] = useState(false);
  const cand = item.candidate;
  const score = item.match_score ?? 0;
  const tone = score >= 80 ? 'high' : score >= 60 ? 'mid' : 'low';
  const matched = item.score_breakdown?.matched_skills || [];
  const gaps = item.score_breakdown?.missing_skills || [];
  const coverage = skillCoverage(item.score_breakdown);
  const status = item.requirement_status || defaultStatus;
  const openCandidate = () => navigate(`/candidates/${cand.id}`, { state: fromState(location, 'Requirements') });

  return (
    <li className="match">
      <div className={`match-score match-score-${tone}`} aria-label={`Overall match score ${score.toFixed(1)} percent`} title="Overall score: resume-to-JD similarity (60%) plus required-skill coverage (40%)">
        <span className="match-score-num">{Math.round(score)}</span>
        <span className="match-score-unit">%</span>
      </div>

      <div className="match-body match-body-link" onClick={openCandidate}>
        <div className="cluster cluster-tight">
          <Link className="match-name" to={`/candidates/${cand.id}`} state={fromState(location, 'Requirements')} onClick={(e) => e.stopPropagation()}>{cand.candidate_name}</Link>
          <span className="slug">{cand.display_id || 'TRU-CN-????'} · {cand.years_experience} yrs</span>
          {item.last_email && <EmailStatusBadge status={item.last_email.status} />}
        </div>
        <p className="match-pct"><strong>Skills matched {coverage.matched} of {coverage.total}{coverage.pct !== null && ` (${coverage.pct}%)`}</strong> · <span>Missing {coverage.missing}{coverage.pct !== null && ` (${100 - coverage.pct}%)`}</span></p>
        <Chips label="Matches" skills={matched} tone="match" />
        <Chips label="Missing" skills={gaps} tone="gap" />
        {open && <div className="match-thread" onClick={(e) => e.stopPropagation()}><CommentThread candidateId={cand.id} positionId={positionId} /></div>}
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
