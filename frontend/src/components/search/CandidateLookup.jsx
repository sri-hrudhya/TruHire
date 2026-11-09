import { Loader2, Search } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function CandidateLookup({ s }) {
  return (
    <section className="candidate-lookup card" aria-labelledby="candidate-lookup-title">
      <div>
        <h2 id="candidate-lookup-title">Find a candidate</h2>
        <p className="dek">Search names, email, phone number, or a stated current company.</p>
      </div>
      <form className="search-bar" onSubmit={s.lookupCandidates} role="search">
        <label className="search-input">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">Candidate name, email, phone, or current company</span>
          <input value={s.candidateLookup} onChange={(event) => s.setCandidateLookup(event.target.value)}
            placeholder="Name, email, phone, or company" autoComplete="off" />
        </label>
        <button type="submit" className="btn btn-secondary" disabled={s.candidateLookupLoading}>
          {s.candidateLookupLoading ? <><Loader2 size={15} className="animate-spin" /> Searching</> : 'Find'}
        </button>
      </form>
      {s.candidateLookupError && <p role="status" className="dek">{s.candidateLookupError}</p>}
      {!!s.candidateLookupResults.length && <ul className="candidate-lookup-list">
        {s.candidateLookupResults.map((candidate) => <li key={candidate.id}>
          <Link to={`/candidates/${candidate.id}`}>
            <strong>{candidate.candidate_name}</strong>
            <span>{[candidate.display_id, candidate.current_company, candidate.email, candidate.phone].filter(Boolean).join(' · ')}</span>
          </Link>
        </li>)}
      </ul>}
    </section>
  );
}
