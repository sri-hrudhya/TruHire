import { useId, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronDown, ChevronUp, FileText } from 'lucide-react';
import { fromState } from '../../lib/navigation';
import { explainScore, skillComparison } from '../../lib/scoreExplanation';
import { useMeta } from '../../context/MetaContext';

function SkillGroup({ title, skills, tone, empty }) {
  return (
    <div className="skill-group">
      <h4 className="skill-group-title">{title} <span className="slug">{skills.length}</span></h4>
      {skills.length > 0
        ? <p className="result-skills">{skills.map((skill) => <span key={skill} className={`skill skill-${tone}`}>{skill}</span>)}</p>
        : <p className="slug">{empty}</p>}
    </div>
  );
}

// Collapsed: candidate name and match percentage only. Opened: skills, gaps and why the score is what it is.
export default function ResultRow({ item, onStatus, onPreview }) {
  const location = useLocation();
  const panelId = useId();
  const { candidate_statuses: statuses } = useMeta();
  const [open, setOpen] = useState(false);
  const cand = item.candidate;
  const score = item.match_score;
  const tone = score >= 80 ? 'high' : score >= 60 ? 'mid' : 'low';
  const skills = skillComparison(cand.extracted_skills, item.score_breakdown);
  const explanation = explainScore(item.score_breakdown);

  return (
    <li className={`match-card${open ? ' is-open' : ''}`}>
      <button type="button" className="match-toggle" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-controls={panelId}>
        <span className="match-toggle-name">{cand.candidate_name}</span>
        <span className={`match-score match-score-${tone}`} aria-label={`Match ${score.toFixed(1)} percent`}>
          <span className="match-score-num">{Math.round(score)}</span>
          <span className="match-score-unit">%</span>
        </span>
        {open ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
      </button>

      {open && (
        <div id={panelId} className="match-panel">
          <div className="match-panel-actions">
            <label className="match-status">
              <span className="sr-only">Pipeline status of {cand.candidate_name}</span>
              <select className="input-field match-status-select" value={cand.status} onChange={(e) => onStatus(cand.id, e.target.value)}>
                {statuses.map((st) => <option key={st} value={st}>{st}</option>)}
              </select>
            </label>
            <button type="button" className="btn btn-secondary btn-compact" onClick={() => onPreview(cand)}><FileText size={14} /> Resume</button>
            <Link className="btn btn-secondary btn-compact" to={`/candidates/${cand.id}`} state={fromState(location, 'Search')}>Full profile</Link>
          </div>

          <div className="skill-groups">
            <SkillGroup title="Resume skills" skills={skills.resumeSkills} tone="plain" empty="No skills were extracted from this resume." />
            {skills.hasJdSkills ? (
              <>
                <SkillGroup title="Matched demand skills" skills={skills.matched} tone="hit" empty="None of the requirement's skills were found." />
                <SkillGroup title="Missing required demand skills" skills={skills.missing} tone="miss" empty="Every required skill was found." />
              </>
            ) : (
              <p className="slug">Pick a requirement to compare this resume with its required skills.</p>
            )}
          </div>

          <div className="result-why">
            <h4 className="skill-group-title">How the {score.toFixed(1)}% was calculated</h4>
            <dl className="kv score-kv">
              {explanation.map((row) => (
                <div key={row.key}>
                  <dt>{row.label}<span className="slug score-detail">{row.detail}</span></dt>
                  <dd className={row.points < 0 ? 'score-neg' : undefined}>{row.text}</dd>
                </div>
              ))}
              <div className="score-total"><dt>Match score</dt><dd>{score.toFixed(1)}%</dd></div>
            </dl>
            {item.llm_summary && <p className="dek">{item.llm_summary}</p>}
            {item.cited_quote && (
              <p className="match-cite">“{item.cited_quote}” <span className="slug">from the requirement, {item.cited_section || 'Requirements'}</span></p>
            )}
          </div>
        </div>
      )}
    </li>
  );
}
