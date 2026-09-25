import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { 
  Search, 
  X, 
  Sparkles, 
  Filter, 
  Briefcase, 
  ChevronDown, 
  ChevronUp, 
  Quote, 
  User, 
  CheckCircle,
  Clock,
  ArrowRight,
  Download
} from 'lucide-react';
import { searchApi, jdApi, candidatesApi, exportApi } from '../lib/api';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [filterChips, setFilterChips] = useState([]);
  const [minExp, setMinExp] = useState('');
  const [selectedJdId, setSelectedJdId] = useState('');
  const [topN, setTopN] = useState(20);

  // Options & Data
  const [jds, setJds] = useState([]);
  const [searchResults, setSearchResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expandedRow, setExpandedRow] = useState(null);
  const [modifierNotice, setModifierNotice] = useState(null);

  const hydratedRef = useRef(false);

  // Restore the last search from the persistent server-side search state.
  // This prevents the query/results disappearing when navigating to a resume and back.
  useEffect(() => {
    const restoreSearch = async () => {
      try {
        const [jdRes, stateRes] = await Promise.all([jdApi.list(), searchApi.getState()]);
        setJds(jdRes.data);
        const state = stateRes.data?.state;
        if (state) {
          setQuery(state.query || '');
          setFilterChips(state.filter_skills || []);
          setMinExp(state.min_experience ?? '');
          setSelectedJdId(state.position_id || '');
          setTopN(state.top_n || 20);
          setSearchResults({
            total_matches: state.total_matches || 0,
            top_n: state.top_n || 20,
            results: state.results || [],
            retrieval: state.retrieval || {},
            scored_against_jd: state.position_id ? { id: state.position_id, title: (jdRes.data.find(j => j.id === state.position_id)?.title || 'Selected JD'), version: (jdRes.data.find(j => j.id === state.position_id)?.jd_version || '') } : null,
            active_filter_chips: state.filter_skills || [],
            min_experience: state.min_experience ?? null,
            query: state.query || ''
          });
        } else {
          await handleSearch();
        }
      } catch (err) {
        console.error('Failed to restore persistent search state:', err);
        try { await handleSearch(); } catch (_) {}
      } finally {
        hydratedRef.current = true;
      }
    };
    restoreSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = async (overrideChips = null, overrideJd = null) => {
    setLoading(true);
    setModifierNotice(null);

    const activeSkills = overrideChips !== null ? overrideChips : filterChips;
    const activeJd = overrideJd !== null ? overrideJd : selectedJdId;

    try {
      const res = await searchApi.search({
        query: query.trim(),
        filter_skills: activeSkills,
        min_experience: minExp ? parseFloat(minExp) : null,
        position_id: activeJd || null,
        top_n: parseInt(topN, 10)
      });

      setSearchResults(res.data);
      if (res.data.active_filter_chips) {
        setFilterChips(res.data.active_filter_chips);
      }
      if (res.data.modifier_mode && res.data.modifier_mode !== 'neutral') {
        setModifierNotice(
          res.data.modifier_mode === 'replace'
            ? 'Applied "replace" modifier: updated active filters.'
            : 'Applied "append" modifier: added to active filters.'
        );
      }
    } catch (err) {
      console.error('Search error:', err);
    } finally {
      setLoading(false);
    }
  };

  const removeChip = (skillToRemove) => {
    const updated = filterChips.filter(s => s !== skillToRemove);
    setFilterChips(updated);
    handleSearch(updated);
  };

  const handleClearAll = async () => {
    setQuery('');
    setFilterChips([]);
    setMinExp('');
    setSelectedJdId('');
    try { await searchApi.clearState(); } catch (err) { console.error('Failed to clear saved search state:', err); }
    handleSearch([], '');
  };

  const handleStatusChange = async (candidateId, newStatus) => {
    try {
      await candidatesApi.updateStatus(candidateId, newStatus);
      // Update local state
      setSearchResults(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          results: prev.results.map(item => {
            if (item.candidate.id === candidateId) {
              return {
                ...item,
                candidate: { ...item.candidate, status: newStatus }
              };
            }
            return item;
          })
        };
      });
    } catch (err) {
      console.error('Failed to update status:', err);
    }
  };

  return (
    <div className="page-body">
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2rem' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-main)' }}>
            Candidate Search & Ranking
          </h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Query the entire talent pool with natural language, modifier words, and optional JD scoring.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <a
            href={exportApi.getExportUrl('csv', selectedJdId || null)}
            download
            className="btn btn-secondary"
            style={{ fontSize: '0.8125rem' }}
          >
            <Download size={15} /> Export CSV
          </a>
        </div>
      </div>

      {/* Unified Search Console */}
      <div className="card" style={{ marginBottom: '2rem', padding: '1.5rem' }}>
        {/* Main Search Bar */}
        <form onSubmit={(e) => { e.preventDefault(); handleSearch(); }} style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search size={18} color="var(--text-subtle)" style={{ position: 'absolute', left: '14px', top: '13px' }} />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search skills, experience, or query (e.g. 'Python and Docker', 'only React, 5+ yrs')..."
              className="input-field"
              style={{ paddingLeft: '42px', fontSize: '0.9375rem', padding: '0.75rem 0.875rem 0.75rem 42px' }}
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary"
            style={{ padding: '0 1.5rem', minWidth: '120px' }}
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </form>

        {/* Filter Controls Row: JD Selector, Min Exp, Top-N */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '2fr 1fr 1fr auto',
          gap: '1rem',
          alignItems: 'center',
          paddingTop: '0.5rem',
          borderTop: '1px solid var(--border-color)'
        }}>
          {/* Select JD to score results against */}
          <div>
            <label className="input-label" style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <Briefcase size={13} /> Score Against Job Description (Optional)
            </label>
            <select
              value={selectedJdId}
              onChange={(e) => {
                setSelectedJdId(e.target.value);
                handleSearch(null, e.target.value);
              }}
              className="input-field"
              style={{ fontSize: '0.8125rem', padding: '0.5rem 0.75rem' }}
            >
              <option value="">No JD (Rank by query/skills alone)</option>
              {jds.map(jd => (
                <option key={jd.id} value={jd.id}>
                  {jd.title} (v{jd.jd_version})
                </option>
              ))}
            </select>
          </div>

          {/* Minimum Experience */}
          <div>
            <label className="input-label">Min. Experience (Yrs)</label>
            <input
              type="number"
              min="0"
              step="0.5"
              value={minExp}
              onChange={(e) => setMinExp(e.target.value)}
              placeholder="e.g. 3"
              className="input-field"
              style={{ fontSize: '0.8125rem', padding: '0.5rem 0.75rem' }}
            />
          </div>

          {/* Top-N Results Limit */}
          <div>
            <label className="input-label">Results Limit (Top-N)</label>
            <select
              value={topN}
              onChange={(e) => {
                setTopN(e.target.value);
              }}
              className="input-field"
              style={{ fontSize: '0.8125rem', padding: '0.5rem 0.75rem' }}
            >
              <option value={10}>Top 10</option>
              <option value={20}>Top 20 (Default)</option>
              <option value={50}>Top 50</option>
              <option value={100}>Top 100 (Max)</option>
            </select>
          </div>

          <div style={{ paddingTop: '1.25rem' }}>
            <button
              type="button"
              onClick={handleClearAll}
              className="btn btn-secondary"
              style={{ fontSize: '0.8125rem', padding: '0.5rem 0.875rem' }}
            >
              Reset
            </button>
          </div>
        </div>

        {/* Active Filter Chips & Modifier Feedback */}
        <div style={{ marginTop: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-subtle)', textTransform: 'uppercase' }}>
              Active Filters:
            </span>
            {filterChips.map((chip, i) => (
              <span key={i} className="chip">
                <span>{chip}</span>
                <span onClick={() => removeChip(chip)} className="chip-remove">
                  <X size={13} />
                </span>
              </span>
            ))}
            {filterChips.length === 0 && (
              <span style={{ fontSize: '0.75rem', color: 'var(--text-subtle)', fontStyle: 'italic' }}>
                None (all candidates considered)
              </span>
            )}
          </div>

          {modifierNotice && (
            <span className="badge badge-primary" style={{ fontSize: '0.75rem' }}>
              <Sparkles size={13} /> {modifierNotice}
            </span>
          )}
        </div>
      </div>

      {/* Results Telemetry Banner */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <div style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text-main)' }}>
          {searchResults ? (
            <span>
              Found <strong style={{ color: 'var(--primary)' }}>{searchResults.total_matches.toLocaleString()}</strong> matches
              {searchResults.total_matches > searchResults.top_n && (
                <span> (displaying top {searchResults.top_n})</span>
              )}
              {searchResults.scored_against_jd && (
                <span> • Scored against <strong>{searchResults.scored_against_jd.title}</strong> (v{searchResults.scored_against_jd.version})</span>
              )}
            </span>
          ) : (
            'Enter a query or select a JD to view ranked candidates'
          )}
        </div>

        <div style={{ fontSize: '0.75rem', color: 'var(--text-subtle)' }}>
          Strict Top-N pagination enforced
        </div>
      </div>

      {/* Results List */}
      {loading ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <Sparkles size={32} className="animate-spin" color="var(--primary)" style={{ margin: '0 auto 1rem' }} />
          <div style={{ fontSize: '1rem', fontWeight: 700 }}>Calculating Semantic & Skill Matches...</div>
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Evaluating vector similarities and experience requirements
          </p>
        </div>
      ) : searchResults?.results.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {searchResults.results.map((item, index) => {
            const cand = item.candidate;
            const score = item.match_score;
            const isExpanded = expandedRow === cand.id;

            // Score color coding
            const scoreBadgeClass = score >= 80 ? 'badge-success' : score >= 60 ? 'badge-warning' : 'badge-neutral';

            return (
              <div
                key={cand.id}
                className="card card-hover"
                style={{
                  padding: '1.25rem 1.5rem',
                  borderLeft: `4px solid ${score >= 80 ? 'var(--success)' : score >= 60 ? 'var(--warning)' : 'var(--primary)'}`
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
                  {/* Left: Name, Experience, Status */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <div style={{
                      width: '44px',
                      height: '44px',
                      borderRadius: '50%',
                      backgroundColor: 'var(--bg-subtle)',
                      border: '1px solid var(--border-color)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'var(--text-main)',
                      fontWeight: 700,
                      fontSize: '1.125rem'
                    }}>
                      {cand.candidate_name.charAt(0)}
                    </div>

                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                        <Link
                          to={`/candidates/${cand.id}`}
                          style={{ fontSize: '1.0625rem', fontWeight: 700, color: 'var(--text-main)', textDecoration: 'none' }}
                        >
                          {cand.candidate_name}
                        </Link>
                        <span className={`badge ${scoreBadgeClass}`} style={{ fontSize: '0.75rem', fontWeight: 800 }}>
                          {score.toFixed(1)}% Match
                        </span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                        <span>{cand.years_experience} yrs experience</span>
                        <span>•</span>
                        <span>{cand.education || 'Education not specified'}</span>
                        <span>•</span>
                        <span>Added {new Date(cand.uploaded_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  </div>

                  {/* Right: Actions & Status selector */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <select
                      value={cand.status}
                      onChange={(e) => handleStatusChange(cand.id, e.target.value)}
                      className="input-field"
                      style={{
                        padding: '0.35rem 0.65rem',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        width: 'auto',
                        backgroundColor: 'var(--bg-subtle)'
                      }}
                    >
                      <option value="New">Status: New</option>
                      <option value="Shortlisted">Status: Shortlisted</option>
                      <option value="Interviewed">Status: Interviewed</option>
                      <option value="Rejected">Status: Rejected</option>
                    </select>

                    <button
                      type="button"
                      onClick={() => setExpandedRow(isExpanded ? null : cand.id)}
                      className="btn btn-secondary"
                      style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }}
                    >
                      <span>Breakdown</span>
                      {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>

                    <Link
                      to={`/candidates/${cand.id}`}
                      className="btn btn-primary"
                      style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }}
                    >
                      <span>Profile</span>
                      <ArrowRight size={13} />
                    </Link>
                  </div>
                </div>

                {/* Candidate Skills Pills */}
                <div style={{ marginTop: '0.875rem', display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                  {cand.extracted_skills?.map((s, idx) => {
                    const isMatched = item.score_breakdown?.matched_skills?.includes(s) || filterChips.includes(s);
                    return (
                      <span
                        key={idx}
                        className="badge"
                        style={{
                          backgroundColor: isMatched ? 'var(--primary-light)' : 'var(--bg-subtle)',
                          color: isMatched ? 'var(--primary)' : 'var(--text-muted)',
                          border: isMatched ? '1px solid var(--primary-border)' : '1px solid var(--border-color)',
                          fontSize: '0.7rem'
                        }}
                      >
                        {s}
                      </span>
                    );
                  })}
                </div>

                {/* Expanded Score Breakdown & Citations Drawer */}
                {isExpanded && (
                  <div style={{
                    marginTop: '1.25rem',
                    padding: '1.25rem',
                    backgroundColor: 'var(--bg-subtle)',
                    borderRadius: '8px',
                    border: '1px solid var(--border-color)'
                  }} className="animate-fade-in">
                    {/* Score Formula Components */}
                    <div style={{ marginBottom: '1rem' }}>
                      <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-subtle)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                        Hybrid Score Components
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', textAlign: 'center' }}>
                        <div style={{ padding: '0.5rem', backgroundColor: 'var(--bg-card)', borderRadius: '6px' }}>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-subtle)' }}>Semantic Sim (45%)</div>
                          <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--primary)' }}>
                            {item.score_breakdown?.semantic_score ?? 0}%
                          </div>
                        </div>
                        <div style={{ padding: '0.5rem', backgroundColor: 'var(--bg-card)', borderRadius: '6px' }}>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-subtle)' }}>Skill Overlap (35%)</div>
                          <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--primary)' }}>
                            {item.score_breakdown?.skill_score ?? 0}%
                          </div>
                        </div>
                        <div style={{ padding: '0.5rem', backgroundColor: 'var(--bg-card)', borderRadius: '6px' }}>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-subtle)' }}>Baseline Credit (20%)</div>
                          <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--success)' }}>
                            {item.score_breakdown?.baseline_score ?? 20}%
                          </div>
                        </div>
                        <div style={{ padding: '0.5rem', backgroundColor: 'var(--bg-card)', borderRadius: '6px' }}>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-subtle)' }}>Experience Penalty</div>
                          <div style={{ fontSize: '1rem', fontWeight: 700, color: item.score_breakdown?.experience_penalty > 0 ? 'var(--danger)' : 'var(--text-muted)' }}>
                            -{item.score_breakdown?.experience_penalty ?? 0}%
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* AI Match Justification & Citations */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                      {item.llm_summary && (
                        <div>
                          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-subtle)', textTransform: 'uppercase', marginBottom: '0.25rem' }}>
                            Match Justification
                          </div>
                          <p style={{ fontSize: '0.8125rem', color: 'var(--text-main)', lineHeight: 1.5 }}>
                            {item.llm_summary}
                          </p>
                        </div>
                      )}

                      {item.cited_quote && (
                        <div style={{
                          padding: '0.75rem',
                          backgroundColor: 'var(--bg-card)',
                          borderRadius: '6px',
                          borderLeft: '3px solid var(--primary)',
                          display: 'flex',
                          gap: '0.5rem'
                        }}>
                          <Quote size={16} color="var(--primary)" style={{ flexShrink: 0, marginTop: '2px' }} />
                          <div>
                            <div style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--primary)' }}>
                              Cited from JD ({item.cited_section || 'Requirements'}):
                            </div>
                            <div style={{ fontSize: '0.8125rem', fontStyle: 'italic', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
                              "{item.cited_quote}"
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
          No candidates found matching your active filters. Try removing keywords or reducing minimum experience.
        </div>
      )}
    </div>
  );
}
