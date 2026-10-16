import React, { useEffect, useState } from 'react';
import { AlertCircle, ArrowLeft, Eye, History, Loader2, Mail, RefreshCw, Sparkles, X } from 'lucide-react';
import { emailApi, jdApi } from '../lib/api';
import EmailComposer, { EmailStatusBadge, RecipientSelector, formatDateTime } from '../components/EmailComposer';

const errorText = (err, fallback) => err?.response?.data?.detail || err?.message || fallback;

function SendEmailsSection({ onSent }) {
  const [jds, setJds] = useState([]);
  const [jdId, setJdId] = useState('');
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [composing, setComposing] = useState(false);

  useEffect(() => {
    jdApi.list().then((r) => setJds(r.data)).catch((err) => setError(errorText(err, 'Failed to load requirements.')));
  }, []);

  const loadCandidates = async (id) => {
    setLoading(true);
    setError(null);
    try {
      const res = await jdApi.getMatches(id, 50);
      setCandidates((res.data?.matches || []).map((m) => ({
        ...m.candidate,
        match_score: m.match_score,
        requirement_status: m.requirement_status,
        last_email: m.last_email,
      })));
    } catch (err) {
      setCandidates([]);
      setError(errorText(err, 'Failed to load matching candidates.'));
    } finally {
      setLoading(false);
    }
  };

  const chooseJd = (id) => {
    setJdId(id);
    setSelectedIds([]);
    setComposing(false);
    setCandidates([]);
    if (id) loadCandidates(id);
  };

  const position = jds.find((j) => j.id === jdId);

  return (
    <div className="card" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
      <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <Mail size={18} color="var(--primary)" /> Send Emails
      </h2>
      <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', margin: '0.25rem 0 1rem' }}>
        Choose a requirement, select candidates marked Shortlisted for it, and review AI-personalized drafts before sending.
      </p>

      <label className="input-label" htmlFor="email-jd">Requirement</label>
      <select id="email-jd" className="input-field" value={jdId} onChange={(e) => chooseJd(e.target.value)} disabled={composing} style={{ maxWidth: '520px' }}>
        <option value="">Select a requirement…</option>
        {jds.map((j) => <option key={j.id} value={j.id}>{j.display_id} · {j.title}</option>)}
      </select>

      {error && (
        <div style={{ marginTop: '1rem', color: 'var(--danger-text)', fontSize: '0.8125rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <AlertCircle size={14} /> {error}
          {jdId && <button type="button" className="btn btn-secondary" style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem' }} onClick={() => loadCandidates(jdId)}>Retry</button>}
        </div>
      )}

      {jdId && (
        <div style={{ marginTop: '1.25rem' }}>
          {loading ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              <Loader2 size={16} className="animate-spin" /> Loading matching candidates…
            </div>
          ) : composing ? (
            <>
              <button type="button" className="btn btn-secondary" style={{ fontSize: '0.75rem', marginBottom: '1rem' }} onClick={() => { setComposing(false); loadCandidates(jdId); }}>
                <ArrowLeft size={13} /> Back to recipients
              </button>
              <EmailComposer
                position={position}
                recipients={candidates.filter((c) => selectedIds.includes(c.id))}
                onSent={onSent}
              />
            </>
          ) : candidates.length === 0 && !error ? (
            <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>No candidates meet the match threshold for this requirement.</div>
          ) : (
            <>
              <RecipientSelector candidates={candidates} selectedIds={selectedIds} onChange={setSelectedIds} />
              {!candidates.some((c) => c.requirement_status === 'Shortlisted') && (
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: '0.75rem' }}>
                  No candidates are Shortlisted for this requirement yet. Update statuses on the Requirements page.
                </p>
              )}
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
                <button type="button" className="btn btn-primary" disabled={!selectedIds.length} onClick={() => setComposing(true)}>
                  <Sparkles size={15} /> Generate {selectedIds.length} personalized email{selectedIds.length === 1 ? '' : 's'}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function EmailContentModal({ record, onClose }) {
  if (!record) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(3px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100, padding: '1rem' }}>
      <div className="card" style={{ maxWidth: '680px', width: '100%', maxHeight: '90vh', overflowY: 'auto', padding: '1.5rem', boxShadow: 'var(--shadow-lg)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 800 }}>{record.subject}</h3>
          <button type="button" onClick={onClose} aria-label="Close" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={18} /></button>
        </div>
        <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', display: 'grid', gap: '0.25rem', marginBottom: '1rem' }}>
          <div>To: <strong>{record.candidate_name}</strong> ({record.candidate_display_id || '—'}) &lt;{record.recipient_email}&gt;</div>
          <div>Requirement: {record.position_display_id} · {record.position_title}</div>
          <div>Date: {formatDateTime(record.created_at)} · Attempts: {record.attempts}</div>
          <div>Status: <EmailStatusBadge status={record.status} /> {record.delivery_mode === 'simulated' && '(no SMTP configured; not delivered)'}</div>
          {record.error && <div style={{ color: 'var(--danger-text)' }}>Error: {record.error}</div>}
        </div>
        <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: '0.875rem', lineHeight: 1.6, margin: 0, padding: '1rem', backgroundColor: 'var(--bg-subtle)', borderRadius: '8px' }}>
          {record.body}
        </pre>
      </div>
    </div>
  );
}

function EmailHistorySection({ refreshToken }) {
  const [roles, setRoles] = useState([]);
  const [loadingRoles, setLoadingRoles] = useState(true);
  const [error, setError] = useState(null);
  const [role, setRole] = useState(null);
  const [records, setRecords] = useState([]);
  const [loadingRecords, setLoadingRecords] = useState(false);
  const [viewing, setViewing] = useState(null);
  const [retrying, setRetrying] = useState(null);

  const loadRoles = async () => {
    setLoadingRoles(true);
    setError(null);
    try {
      const res = await emailApi.history();
      setRoles(res.data.roles);
    } catch (err) {
      setError(errorText(err, 'Failed to load email history.'));
    } finally {
      setLoadingRoles(false);
    }
  };

  const loadRecords = async (positionId) => {
    setLoadingRecords(true);
    setError(null);
    try {
      const res = await emailApi.historyForRole(positionId);
      setRecords(res.data.records);
    } catch (err) {
      setError(errorText(err, 'Failed to load emails for this role.'));
    } finally {
      setLoadingRecords(false);
    }
  };

  useEffect(() => {
    loadRoles();
    if (role) loadRecords(role.position_id);
  }, [refreshToken]);

  const openRole = (r) => {
    setRole(r);
    loadRecords(r.position_id);
  };

  const retry = async (rec) => {
    setRetrying(rec.id);
    setError(null);
    try {
      await emailApi.retry(rec.id);
    } catch (err) {
      setError(errorText(err, 'Retry failed.'));
    } finally {
      setRetrying(null);
      loadRecords(rec.position_id);
      loadRoles();
    }
  };

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <History size={18} color="var(--primary)" /> Email History
          {role && <span style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.9rem' }}>· {role.position_display_id} {role.position_title}</span>}
        </h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {role && (
            <button type="button" className="btn btn-secondary" style={{ fontSize: '0.75rem' }} onClick={() => setRole(null)}>
              <ArrowLeft size={13} /> All roles
            </button>
          )}
          <button type="button" className="btn btn-secondary" style={{ fontSize: '0.75rem' }} onClick={() => { loadRoles(); if (role) loadRecords(role.position_id); }}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: '1rem', color: 'var(--danger-text)', fontSize: '0.8125rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <AlertCircle size={14} /> {error}
        </div>
      )}

      {!role ? (
        loadingRoles ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', fontSize: '0.875rem' }}><Loader2 size={16} className="animate-spin" /> Loading…</div>
        ) : roles.length === 0 ? (
          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>No emails have been sent yet.</div>
        ) : (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr><th>Role</th><th>Requirement ID</th><th>Total emails</th><th>Outcome</th><th>Latest activity</th></tr>
              </thead>
              <tbody>
                {roles.map((r) => (
                  <tr key={r.position_id} onClick={() => openRole(r)} style={{ cursor: 'pointer' }}>
                    <td style={{ fontWeight: 700 }}>
                      {r.position_title}
                      {r.requirement_deleted && <span className="badge badge-neutral" style={{ fontSize: '0.65rem', marginLeft: '0.4rem' }}>Removed</span>}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>{r.position_display_id || '—'}</td>
                    <td>{r.total_emails}</td>
                    <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {[r.sent && `${r.sent} sent`, r.simulated && `${r.simulated} simulated`, r.failed && `${r.failed} failed`].filter(Boolean).join(' · ') || '—'}
                    </td>
                    <td>{formatDateTime(r.latest_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : loadingRecords ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', fontSize: '0.875rem' }}><Loader2 size={16} className="animate-spin" /> Loading…</div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr><th>Candidate</th><th>Recipient</th><th>Subject</th><th>Date / time</th><th>Status</th><th></th></tr>
            </thead>
            <tbody>
              {records.map((rec) => (
                <tr key={rec.id}>
                  <td>
                    <div style={{ fontWeight: 700 }}>{rec.candidate_name}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--text-muted)' }}>{rec.candidate_display_id || '—'}</div>
                  </td>
                  <td style={{ fontSize: '0.8125rem' }}>{rec.recipient_email}</td>
                  <td style={{ fontSize: '0.8125rem', maxWidth: '280px' }}>{rec.subject}</td>
                  <td style={{ fontSize: '0.8125rem', whiteSpace: 'nowrap' }}>{formatDateTime(rec.created_at)}</td>
                  <td><EmailStatusBadge status={rec.status} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button type="button" className="btn btn-secondary" style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem' }} onClick={() => setViewing(rec)}>
                      <Eye size={13} /> View
                    </button>
                    {rec.status === 'failed' && (
                      <button type="button" className="btn btn-primary" style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem', marginLeft: '0.4rem' }}
                        disabled={retrying === rec.id} onClick={() => retry(rec)}>
                        {retrying === rec.id ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Retry
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <EmailContentModal record={viewing} onClose={() => setViewing(null)} />
    </div>
  );
}

export default function EmailPage() {
  const [historyVersion, setHistoryVersion] = useState(0);

  return (
    <div>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 className="page-header-title" style={{ margin: 0 }}>Email</h1>
        <p className="page-header-subtitle" style={{ marginTop: '0.35rem' }}>
          Send personalized emails to shortlisted candidates and review every email sent from here or from Requirements.
        </p>
      </div>
      <SendEmailsSection onSent={() => setHistoryVersion((v) => v + 1)} />
      <EmailHistorySection refreshToken={historyVersion} />
    </div>
  );
}
