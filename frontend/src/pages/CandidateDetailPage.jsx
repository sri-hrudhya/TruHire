import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  Mail,
  Phone,
  GraduationCap,
  Briefcase,
  FileText,
  Sparkles,
} from 'lucide-react';
import { candidatesApi } from '../lib/api';
import ResumePreviewModal from '../components/ResumePreviewModal';
import PageBreadcrumbs from '../components/PageBreadcrumbs';
import { useBackNavigation } from '../lib/navigation';
import CommentThread from '../components/review/CommentThread';
import './candidate-detail.css';

export default function CandidateDetailPage() {
  const { id } = useParams();
  // Back returns to wherever the profile was opened from (Search, Requirements, Ingestion History).
  const { goBack, backLabel } = useBackNavigation('/search', 'Search');
  const [candidate, setCandidate] = useState(null);
  const [matches, setMatches] = useState([]);
  const [history, setHistory] = useState([]);
  const [requirementHistory, setRequirementHistory] = useState([]);
  const [historyCursor, setHistoryCursor] = useState(null);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [historyLoadingMore, setHistoryLoadingMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [isResumeOpen, setIsResumeOpen] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);

  useEffect(() => {
    const loadCandidateData = async () => {
      setLoading(true);
      try {
        const [candRes, matchesRes, historyRes] = await Promise.all([
          candidatesApi.get(id),
          candidatesApi.getMatches(id),
          candidatesApi.getHistory(id).catch(() => ({ data: { items: [] } }))
        ]);
        setCandidate(candRes.data);
        setMatches(matchesRes.data.matches || []);
        setHistory(historyRes.data.items || []);
        setRequirementHistory(historyRes.data.requirements || []);
        setHistoryCursor(historyRes.data.next_cursor || null);
        setHistoryHasMore(!!historyRes.data.has_more);
      } catch (err) {
        console.error('Error loading candidate detail:', err);
      } finally {
        setLoading(false);
      }
    };
    loadCandidateData();
  }, [id]);

  const refreshHistory = async () => {
    const historyRes = await candidatesApi.getHistory(id);
    setHistory(historyRes.data.items || []);
    setRequirementHistory(historyRes.data.requirements || []);
    setHistoryCursor(historyRes.data.next_cursor || null);
    setHistoryHasMore(!!historyRes.data.has_more);
  };

  const handleAvailabilityUpdate = async (newStatus) => {
    try {
      const response = await candidatesApi.updateAvailability(id, newStatus);
      setCandidate((previous) => ({ ...previous, ...response.data }));
      await refreshHistory();
      setStatusMessage(`Availability updated to ${newStatus}`);
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err) {
      console.error('Failed to update availability:', err);
      setStatusMessage('Could not update availability. Please try again.');
    }
  };

  const handleRequirementStatusUpdate = async (positionId, newStatus) => {
    try {
      await candidatesApi.updateRequirementStatus(positionId, id, newStatus);
      setMatches((previous) => previous.map((match) => match.position_id === positionId
        ? { ...match, requirement_status: newStatus } : match));
      await refreshHistory();
      setStatusMessage(`Requirement status updated to ${newStatus}`);
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err) {
      console.error('Failed to update requirement status:', err);
      setStatusMessage('Could not update requirement status. Please try again.');
    }
  };

  const loadMoreHistory = async () => {
    if (!historyCursor || historyLoadingMore) return;
    setHistoryLoadingMore(true);
    try {
      const response = await candidatesApi.getHistory(id, { cursor: historyCursor, limit: 50 });
      setHistory((previous) => [...previous, ...(response.data.items || [])]);
      setHistoryCursor(response.data.next_cursor || null);
      setHistoryHasMore(!!response.data.has_more);
    } catch {
      setStatusMessage('Could not load more candidate history. Try again.');
    } finally {
      setHistoryLoadingMore(false);
    }
  };

  if (loading) {
    return (
      <div className="page-body" style={{ textAlign: 'center', padding: '4rem' }}>
        <Sparkles size={32} className="animate-spin" color="var(--primary)" style={{ margin: '0 auto 1rem' }} />
        <div style={{ fontSize: '1rem', fontWeight: 600 }}>Loading Candidate Dossier...</div>
      </div>
    );
  }

  if (!candidate) {
    return (
      <div className="page-body" style={{ textAlign: 'center', padding: '4rem' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>Candidate not found</h2>
        <button type="button" onClick={goBack} className="btn btn-primary" style={{ marginTop: '1rem' }}>
          Return to {backLabel}
        </button>
      </div>
    );
  }

  return (
    <div className="page-body">
      {/* Back button */}
      <PageBreadcrumbs
        onBack={goBack}
        backLabel={backLabel}
        items={[
          { label: backLabel, onClick: goBack },
          { label: candidate.candidate_name || candidate.display_id || 'Candidate' },
        ]}
      />

      {statusMessage && (
        <div className="badge-success" style={{ padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1.5rem' }}>
          {statusMessage}
        </div>
      )}

      {/* Profile Overview Card */}
      <div className="card" style={{ marginBottom: '2rem', padding: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
            <div style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              backgroundColor: 'var(--primary-light)',
              border: '2px solid var(--primary-border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--primary)',
              fontSize: '1.75rem',
              fontWeight: 800
            }}>
              {candidate.candidate_name.charAt(0)}
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                <span
                  className="badge badge-primary"
                  style={{
                    fontSize: '0.8125rem',
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 800,
                    padding: '0.25rem 0.65rem'
                  }}
                >
                  {candidate.display_id || 'TRU-CN-????'}
                </span>
                <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-main)', margin: 0 }}>
                  {candidate.candidate_name}
                </h1>
                <span className="badge badge-neutral">
                  Shared Talent Pool
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', flexWrap: 'wrap', marginTop: '0.5rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                {candidate.email && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Mail size={14} /> {candidate.email}
                  </span>
                )}
                {candidate.phone && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Phone size={14} /> {candidate.phone}
                  </span>
                )}
                {candidate.current_company && <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Briefcase size={14} /> {candidate.current_company}
                </span>}
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Briefcase size={14} /> {candidate.years_experience} Years Experience
                </span>
              </div>
            </div>
          </div>

          {/* Availability is global; hiring stage is set per requirement below. */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <button
              onClick={() => setIsResumeOpen(true)}
              className="btn btn-secondary"
              title="Preview candidate resume document"
            >
              <FileText size={16} color="var(--primary)" /> View Resume
            </button>

            <select
              value={candidate.availability_status || 'Active'}
              onChange={(e) => handleAvailabilityUpdate(e.target.value)}
              aria-label="Candidate availability"
              className="input-field"
              style={{
                width: 'auto',
                padding: '0.625rem 1rem',
                fontSize: '0.875rem',
                fontWeight: 600,
                backgroundColor: 'var(--bg-subtle)'
              }}
            >
              <option value="Active">Active</option>
              <option value="Not Active">Not Active</option>
            </select>
          </div>
        </div>

        {/* Qualifications row */}
        <div style={{
          marginTop: '1.5rem',
          paddingTop: '1.5rem',
          borderTop: '1px solid var(--border-color)',
          display: 'grid',
          gridTemplateColumns: '1fr 2fr',
          gap: '2rem'
        }}>
          <div>
            <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-subtle)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
              Education & Credentials
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', fontSize: '0.875rem', color: 'var(--text-main)' }}>
              <GraduationCap size={18} color="var(--primary)" style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>{candidate.education || 'Self-taught / Not formally specified'}</div>
            </div>
          </div>

          <div>
            <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-subtle)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
              Extracted Technical Competencies ({candidate.extracted_skills?.length || 0})
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
              {candidate.extracted_skills?.map((s, idx) => (
                <span key={idx} className="badge badge-neutral" style={{ fontSize: '0.75rem' }}>
                  {s}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Requirements Match Matrix */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
          <div>
            <h3 style={{ fontSize: '1.125rem', fontWeight: 800, color: 'var(--text-main)' }}>
              Requirements Match Matrix
            </h3>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              Evaluations of this candidate against job requirements across the platform.
            </p>
          </div>
          <span className="badge badge-neutral">
            {matches.length} Evaluated Requirement(s)
          </span>
        </div>

        {matches.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {matches.map((m) => {
              const badgeClass = m.match_score >= 80 ? 'badge-success' : m.match_score >= 60 ? 'badge-warning' : 'badge-neutral';
              return (
                <div
                  key={m.match_id}
                  style={{
                    padding: '1.25rem',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border-color)',
                    backgroundColor: 'var(--bg-surface)'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                      {m.position_display_id && (
                        <span className="badge badge-primary" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', fontWeight: 700 }}>
                          {m.position_display_id}
                        </span>
                      )}
                      <span style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)' }}>
                        {m.position_title}
                      </span>
                      {m.client_name && <span className="badge badge-neutral">{m.client_name}</span>}
                      <span className="badge badge-neutral" style={{ fontSize: '0.7rem' }}>
                        {m.is_version_current ? 'Current requirement' : 'Earlier requirement version'}
                      </span>
                    </div>

                    <span className={`badge ${badgeClass}`} style={{ fontSize: '0.8125rem', fontWeight: 800 }}>
                      {m.match_score.toFixed(1)}% Match
                    </span>
                  </div>

                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.8125rem', fontWeight: 600 }}>
                    Hiring stage for this requirement
                    <select className="input-field" value={m.requirement_status || 'New'}
                      onChange={(event) => handleRequirementStatusUpdate(m.position_id, event.target.value)}
                      aria-label={`Hiring stage for ${m.position_display_id || m.position_title}`} style={{ width: 'auto' }}>
                      {['New', 'Shortlisted', 'Interviewed', 'Rejected'].map((stage) => <option key={stage} value={stage}>{stage}</option>)}
                    </select>
                  </label>

                  {/* Summary & Citation */}
                  {m.llm_summary && (
                    <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: '0.75rem' }}>
                      {m.llm_summary}
                    </p>
                  )}

                  {m.cited_quote && (
                    <div style={{
                      padding: '0.625rem 0.875rem',
                      backgroundColor: 'var(--bg-subtle)',
                      borderRadius: '6px',
                      borderLeft: '3px solid var(--primary)',
                      fontSize: '0.75rem',
                      color: 'var(--text-muted)',
                      fontStyle: 'italic'
                    }}>
                      "{m.cited_quote}"
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-subtle)', fontSize: '0.875rem' }}>
            This candidate has not yet been scored against any active Requirements in Search.
          </div>
        )}
      </div>

      <section className="card" style={{ marginTop: '2rem', padding: '1.5rem' }}>
        <div className="section-head"><h2>Team feedback</h2></div>
        <div style={{ paddingTop: 'var(--space-4)' }}>
          <CommentThread candidateId={candidate.id} />
        </div>
      </section>

      <section className="card" style={{ marginTop: '2rem', padding: '1.5rem' }}>
        <div className="section-head"><h2>Candidate History</h2></div>
        <p className="dek">Availability: <strong>{candidate.availability_status || 'Active'}</strong>
          {candidate.availability_updated_at && <> · Last modified {new Date(candidate.availability_updated_at).toLocaleString()}{candidate.availability_updated_by ? ` by ${history.find((event) => event.event_type === 'availability_status_changed')?.actor || 'a recruiter'}` : ''}</>}
        </p>
        <h3>Requirements and client status</h3>
        {requirementHistory.length ? <ul className="candidate-requirement-history">
          {requirementHistory.map((item) => <li key={item.id}>
            <strong>{item.client_name || 'No client'} — {item.status}</strong>
            <span>{[item.display_id, item.title].filter(Boolean).join(' · ')}{item.demand_owner ? ` · Demand owner: ${item.demand_owner}` : ''}</span>
            {item.last_modified && <small>Last modified {new Date(item.last_modified).toLocaleString()}{item.modified_by ? ` | Modified by ${item.modified_by}` : ''}</small>}
          </li>)}
        </ul> : <p className="dek">No requirement status has been recorded yet.</p>}
        <h3>Activity notes</h3>
        {history.length ? <ol className="candidate-history" aria-label="Candidate history with TruHire">
          {history.map((event) => <li key={event.id}>
            <strong>{event.summary}</strong>
            {(event.position_title || event.client_name) && <span>{[event.position_title, event.client_name].filter(Boolean).join(' · ')}</span>}
            <small>Last modified {new Date(event.timestamp).toLocaleString()}{event.actor ? ` | Modified by ${event.actor}` : ''}</small>
          </li>)}
        </ol> : <p className="dek">No recorded activity yet. New status and review activity will appear here.</p>}
        {historyHasMore && <button type="button" className="btn btn-secondary btn-compact" onClick={loadMoreHistory} disabled={historyLoadingMore}>
          {historyLoadingMore ? 'Loading…' : 'Load more history'}
        </button>}
      </section>

      {/* Resume Preview Modal */}
      <ResumePreviewModal
        isOpen={isResumeOpen}
        onClose={() => setIsResumeOpen(false)}
        candidate={candidate}
      />
    </div>
  );
}
