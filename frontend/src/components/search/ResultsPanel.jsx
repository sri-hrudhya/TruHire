import { Loader2 } from 'lucide-react';
import ResultRow from './ResultRow';
import Notice from '../ui/Notice';
import { emptyResultMessage, resultsViewState } from '../../lib/categories';
import './search.css';

export default function ResultsPanel({ s, onPreview }) {
  const { results, loading } = s;
  const view = resultsViewState(results, loading);

  return (
    <section className="results" aria-live="polite">
      {results && (
        <p className="results-summary">
          <strong>{results.total_matches.toLocaleString()}</strong> {results.total_matches === 1 ? 'match' : 'matches'}
          {results.total_matches > results.top_n && <> (showing the top {results.top_n})</>}
          {results.filters && (
            <> · filtered{results.filters.role ? <> by title <strong>{results.filters.role}</strong></> : null}{results.filters.location ? <> in <strong>{results.filters.location}</strong></> : null}</>
          )}
          {results.scored_against_jd && <> · scored against <strong>{results.scored_against_jd.title}</strong></>}
        </p>
      )}
      {results?.warnings?.length > 0 && <Notice type="warning">{results.warnings.join(' ')}</Notice>}

      {view === 'loading' && <p className="req-empty"><Loader2 size={18} className="animate-spin" /> Scoring candidates…</p>}
      {view === 'results' && (
        <ul className="match-list">
          {results.results.map((item) => (
            <ResultRow key={item.candidate.id} item={item} onStatus={s.setCandidateStatus} onPreview={onPreview} />
          ))}
        </ul>
      )}
      {view === 'empty' && (
        <div className="stack stack-tight">
          <p>{emptyResultMessage(results)}</p>
          {results.filters?.excluded_missing_metadata > 0 && (
            <p className="dek">
              {results.filters.excluded_missing_metadata} candidate(s) were left out because their resume does not state the {[results.filters.location && 'location', results.filters.role && 'job title'].filter(Boolean).join(' / ')} being filtered on.
            </p>
          )}
          {results.filters && (
            <p><button type="button" className="btn btn-secondary btn-compact" onClick={s.clearRoleLocation}>Search without title and location</button></p>
          )}
        </div>
      )}
    </section>
  );
}
