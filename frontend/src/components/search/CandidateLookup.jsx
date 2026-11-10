import { Link } from 'react-router-dom';

// Near matches for the single search box (name, email, phone number or current company).
export default function CandidateLookup({ matches }) {
  if (!matches.length) return null;
  return (
    <section className="candidate-lookup card" aria-labelledby="candidate-lookup-title">
      <h2 id="candidate-lookup-title">Matching candidates ({matches.length})</h2>
      <ul className="candidate-lookup-list">
        {matches.map((candidate) => <li key={candidate.id}>
          <Link to={`/candidates/${candidate.id}`}>
            <strong>{candidate.candidate_name}</strong>
            <span>{[candidate.display_id, candidate.current_company, candidate.email, candidate.phone].filter(Boolean).join(' · ')}</span>
          </Link>
        </li>)}
      </ul>
    </section>
  );
}
