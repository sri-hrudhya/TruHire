import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { 
  User, 
  Mail, 
  Phone, 
  GraduationCap, 
  Briefcase, 
  Calendar, 
  FileText, 
  Sparkles, 
  ArrowLeft,
  Quote,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';
import { candidatesApi } from '../lib/api';
import AIChatWindow from '../components/AIChatWindow';

export default function CandidateDetailPage() {
  const { id } = useParams();
  const [candidate, setCandidate] = useState(null);
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);

  useEffect(() => {
    const loadCandidateData = async () => {
      try {
        const [candRes, matchesRes] = await Promise.all([
          candidatesApi.get(id),
          candidatesApi.getMatches(id)
        ]);
        setCandidate(candRes.data);
        setMatches(matchesRes.data.matches || []);
      } catch (err) {
        console.error('Error loading candidate detail:', err);
      } finally {
        setLoading(false);
      }
    };
    loadCandidateData();
  }, [id]);

  const handleStatusUpdate = async (newStatus) => {
    try {
      await candidatesApi.updateStatus(id, newStatus);
      setCandidate(prev => ({ ...prev, status: newStatus }));
      setStatusMessage(`Recruitment status updated to ${newStatus}`);
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (err) {
      console.error('Failed to update status:', err);
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
        <Link to="/search" className="btn btn-primary" style={{ marginTop: '1rem' }}>
          Return to Search
        </Link>
      </div>
    );
  }

  return (
    <div className="page-body">
      {/* Back button */}
      <Link
        to="/search"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.5rem',
          fontSize: '0.8125rem',
          fontWeight: 600,
          color: 'var(--text-muted)',
          textDecoration: 'none',
          marginBottom: '1.5rem'
        }}
      >
        <ArrowLeft size={16} /> Back to Search
      </Link>

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
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <h1 style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-main)' }}>
                  {candidate.candidate_name}
                </h1>
                <span className="badge badge-primary">
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
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Briefcase size={14} /> {candidate.years_experience} Years Experience
                </span>
              </div>
            </div>
          </div>

          {/* Actions: Status Dropdown + AI Chat */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <select
              value={candidate.status}
              onChange={(e) => handleStatusUpdate(e.target.value)}
              className="input-field"
              style={{
                width: 'auto',
                padding: '0.625rem 1rem',
                fontSize: '0.875rem',
                fontWeight: 600,
                backgroundColor: 'var(--bg-subtle)'
              }}
            >
              <option value="New">Status: New</option>
              <option value="Shortlisted">Status: Shortlisted</option>
              <option value="Interviewed">Status: Interviewed</option>
              <option value="Rejected">Status: Rejected</option>
            </select>

            <button
              onClick={() => setIsChatOpen(true)}
              className="btn btn-primary"
            >
              <Sparkles size={16} /> AI Interview Copilot
            </button>
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

      {/* Cross-JD Match Matrix */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
          <div>
            <h3 style={{ fontSize: '1.125rem', fontWeight: 800, color: 'var(--text-main)' }}>
              Cross-JD Match Matrix
            </h3>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              Evaluations of this candidate against job descriptions across the platform.
            </p>
          </div>
          <span className="badge badge-neutral">
            {matches.length} Evaluated Position(s)
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
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <span style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)' }}>
                        {m.position_title}
                      </span>
                      <span className="badge badge-neutral" style={{ fontSize: '0.7rem' }}>
                        Evaluated on v{m.jd_version} {m.is_version_current ? '(Current)' : '(Historical)'}
                      </span>
                    </div>

                    <span className={`badge ${badgeClass}`} style={{ fontSize: '0.8125rem', fontWeight: 800 }}>
                      {m.match_score.toFixed(1)}% Match
                    </span>
                  </div>

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
            This candidate has not yet been scored against any active Job Descriptions in Search.
          </div>
        )}
      </div>

      {/* Copilot Drawer */}
      <AIChatWindow
        isOpen={isChatOpen}
        onClose={() => setIsChatOpen(false)}
        candidateId={candidate.id}
        title={`AI Copilot: ${candidate.candidate_name}`}
      />
    </div>
  );
}
