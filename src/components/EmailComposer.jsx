import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, Mail, RefreshCw, Send, Sparkles } from 'lucide-react';
import { emailApi } from '../lib/api';

export const REQUIREMENT_STATUSES = ['Pending Review', 'Shortlisted', 'Not Shortlisted'];

const REQUIREMENT_STATUS_BADGE = {
  'Pending Review': 'badge-neutral',
  Shortlisted: 'badge-success',
  'Not Shortlisted': 'badge-danger',
};

function RequirementStatusBadge({ status }) {
  return (
    <span className={`badge ${REQUIREMENT_STATUS_BADGE[status] || 'badge-neutral'}`} style={{ fontSize: '0.7rem' }}>
      {status || 'Pending Review'}
    </span>
  );
}

const EMAIL_STATUS = {
  sent: { cls: 'badge-success', label: 'Sent' },
  simulated: { cls: 'badge-warning', label: 'Simulated (not delivered)' },
  failed: { cls: 'badge-danger', label: 'Failed' },
  pending: { cls: 'badge-neutral', label: 'Pending' },
};

export function EmailStatusBadge({ status }) {
  const s = EMAIL_STATUS[status] || { cls: 'badge-neutral', label: status };
  return <span className={`badge ${s.cls}`} style={{ fontSize: '0.7rem' }}>{s.label}</span>;
}

export const formatDateTime = (iso) => {
  if (!iso) return '—';
  // Backend timestamps are naive UTC.
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return d.toLocaleString();
};

const apiErrorMessage = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join('; ');
  return err?.message || fallback;
};

const newKey = () => (window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);

/**
 * Candidate table with selection. Only candidates Shortlisted for the requirement and
 * having an email address can be selected.
 */
export function RecipientSelector({ candidates, selectedIds, onChange }) {
  const selectable = candidates.filter((c) => c.requirement_status === 'Shortlisted' && c.email);
  const allSelected = selectable.length > 0 && selectable.every((c) => selectedIds.includes(c.id));

  const toggle = (id) => onChange(selectedIds.includes(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id]);

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem', fontSize: '0.8125rem' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: selectable.length ? 'pointer' : 'default', fontWeight: 600 }}>
          <input
            type="checkbox"
            checked={allSelected}
            disabled={!selectable.length}
            onChange={() => onChange(allSelected ? [] : selectable.map((c) => c.id))}
          />
          Select all shortlisted ({selectable.length})
        </label>
        <span style={{ fontWeight: 700, color: 'var(--primary)' }}>{selectedIds.length} recipient{selectedIds.length === 1 ? '' : 's'} selected</span>
      </div>
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: '40px' }}></th>
              <th>Candidate ID</th>
              <th>Name</th>
              <th>Email</th>
              <th>Match</th>
              <th>Status</th>
              <th>Last email</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => {
              const canSelect = c.requirement_status === 'Shortlisted' && Boolean(c.email);
              return (
                <tr key={c.id} style={{ opacity: canSelect ? 1 : 0.6 }}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(c.id)}
                      disabled={!canSelect}
                      onChange={() => toggle(c.id)}
                      title={canSelect ? '' : c.email ? 'Only Shortlisted candidates can be emailed' : 'No email address on file'}
                    />
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', fontWeight: 700 }}>{c.display_id || '—'}</td>
                  <td style={{ fontWeight: 600 }}>{c.candidate_name}</td>
                  <td style={{ color: c.email ? 'var(--text-muted)' : 'var(--warning-text)' }}>{c.email || 'No email'}</td>
                  <td>{typeof c.match_score === 'number' ? `${c.match_score.toFixed(1)}%` : '—'}</td>
                  <td><RequirementStatusBadge status={c.requirement_status} /></td>
                  <td>{c.last_email ? <EmailStatusBadge status={c.last_email.status} /> : <span style={{ color: 'var(--text-subtle)' }}>—</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * AI-drafts one email per recipient, lets the recruiter edit/regenerate each, then sends
 * after an explicit confirmation. Drafts are never filled from a template: if generation
 * fails the recruiter sees the error and can retry.
 */
export default function EmailComposer({ position, recipients, onSent, onCancel }) {
  const [config, setConfig] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [confirming, setConfirming] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState(null);
  const [skipped, setSkipped] = useState([]);
  const mounted = useRef(true);

  const patch = (cid, values) => {
    if (!mounted.current) return;
    setDrafts((prev) => ({ ...prev, [cid]: { ...prev[cid], ...values } }));
  };

  const generate = async (cid) => {
    patch(cid, { state: 'generating', error: null });
    try {
      const res = await emailApi.generate(position.id, [cid]);
      const draft = res.data.drafts.find((d) => d.candidate_id === cid);
      if (draft) {
        // A fresh idempotency key per generated draft; edits keep it so a double submit cannot resend.
        patch(cid, { state: 'ready', subject: draft.subject, body: draft.body, key: newKey(), result: null });
      } else {
        const err = res.data.errors.find((e) => e.candidate_id === cid);
        patch(cid, { state: 'error', error: err?.reason || 'The AI did not return a draft.' });
      }
    } catch (err) {
      patch(cid, { state: 'error', error: apiErrorMessage(err, 'Email generation failed.') });
    }
  };

  useEffect(() => {
    mounted.current = true;
    emailApi.getConfig().then((r) => mounted.current && setConfig(r.data)).catch(() => {});
    setDrafts(Object.fromEntries(recipients.map((r) => [r.id, { state: 'generating' }])));
    let cancelled = false;
    (async () => {
      for (const r of recipients) {
        if (cancelled) break;
        await generate(r.id);
      }
    })();
    return () => { cancelled = true; mounted.current = false; };
  }, [position.id, recipients.map((r) => r.id).join(',')]);

  const sendable = recipients.filter((r) => {
    const d = drafts[r.id];
    return d?.state === 'ready' && d.subject?.trim() && d.body?.trim() && !d.result;
  });
  const generatingCount = recipients.filter((r) => drafts[r.id]?.state === 'generating').length;
  const simulated = config?.delivery_mode === 'simulated';

  const send = async (ids, allowResend = false) => {
    setSending(true);
    setSendError(null);
    try {
      const emails = ids.map((cid) => ({ candidate_id: cid, subject: drafts[cid].subject.trim(), body: drafts[cid].body.trim(), idempotency_key: drafts[cid].key }));
      const res = await emailApi.send(position.id, emails, allowResend);
      res.data.results.forEach((r) => patch(r.candidate_id, { result: r }));
      setSkipped((prev) => [
        ...prev.filter((s) => !ids.includes(s.candidate_id)),
        ...res.data.skipped,
      ]);
      setConfirming(false);
      onSent?.(res.data);
    } catch (err) {
      setSendError(apiErrorMessage(err, 'Sending failed.'));
    } finally {
      setSending(false);
    }
  };

  const alreadyEmailed = skipped.filter((s) => s.already_emailed && drafts[s.candidate_id]?.state === 'ready' && !drafts[s.candidate_id]?.result);

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'flex-start', gap: '0.5rem', padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem', fontSize: '0.8125rem',
        backgroundColor: simulated ? 'var(--warning-bg)' : 'var(--bg-subtle)', color: simulated ? 'var(--warning-text)' : 'var(--text-muted)',
      }}>
        <Mail size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
        <span>
          {!config ? 'Checking email delivery configuration…'
            : simulated ? 'No SMTP server is configured: emails will be recorded in history as "Simulated" and will NOT be delivered.'
              : `Emails will be delivered via SMTP${config.from_address ? ` from ${config.from_address}` : ''}.`}
          {' '}Drafts for <strong>{position.display_id} · {position.title}</strong> are written by AI from the requirement and each candidate's profile. Review every draft before sending.
        </span>
      </div>

      {generatingCount > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8125rem', marginBottom: '0.75rem', color: 'var(--text-muted)' }}>
          <Loader2 size={14} className="animate-spin" /> Generating personalized drafts… {recipients.length - generatingCount}/{recipients.length} done
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {recipients.map((r) => {
          const d = drafts[r.id] || {};
          const locked = Boolean(d.result) || sending;
          const skip = skipped.find((s) => s.candidate_id === r.id);
          return (
            <div key={r.id} className="card" style={{ padding: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <span className="badge badge-primary" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem' }}>{r.display_id || '—'}</span>
                  <strong>{r.candidate_name}</strong>
                  <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>&lt;{r.email}&gt;</span>
                  {d.result && <EmailStatusBadge status={d.result.status} />}
                  {d.result?.duplicate && <span className="badge badge-neutral" style={{ fontSize: '0.7rem' }}>Already sent — not resent</span>}
                </div>
                {!d.result && (
                  <button type="button" className="btn btn-secondary" style={{ fontSize: '0.75rem', padding: '0.3rem 0.7rem' }}
                    disabled={d.state === 'generating' || sending} onClick={() => generate(r.id)}>
                    {d.state === 'generating' ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                    {d.state === 'error' ? 'Retry generation' : 'Regenerate'}
                  </button>
                )}
              </div>

              {d.state === 'generating' && !d.subject && (
                <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <Sparkles size={14} color="var(--primary)" /> Drafting from requirement and resume…
                </div>
              )}
              {d.state === 'error' && (
                <div style={{ fontSize: '0.8125rem', color: 'var(--danger-text)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <AlertCircle size={14} /> AI draft could not be generated: {d.error}
                </div>
              )}
              {(d.state === 'ready' || (d.state === 'generating' && d.subject)) && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', opacity: d.state === 'generating' ? 0.5 : 1 }}>
                  <label className="input-label" style={{ margin: 0 }}>Subject</label>
                  <input className="input-field" value={d.subject || ''} disabled={locked || d.state !== 'ready'}
                    onChange={(e) => patch(r.id, { subject: e.target.value })} />
                  <label className="input-label" style={{ margin: 0 }}>Body</label>
                  <textarea className="input-field" rows={9} value={d.body || ''} disabled={locked || d.state !== 'ready'}
                    onChange={(e) => patch(r.id, { body: e.target.value })} style={{ fontFamily: 'inherit', resize: 'vertical' }} />
                </div>
              )}
              {d.result?.status === 'failed' && (
                <div style={{ fontSize: '0.8125rem', color: 'var(--danger-text)', marginTop: '0.5rem' }}>
                  Delivery failed: {d.result.error}. You can retry it from Email History.
                </div>
              )}
              {skip && !d.result && (
                <div style={{ fontSize: '0.8125rem', color: 'var(--warning-text)', marginTop: '0.5rem' }}>Not sent: {skip.reason}</div>
              )}
            </div>
          );
        })}
      </div>

      {sendError && (
        <div style={{ marginTop: '1rem', color: 'var(--danger-text)', fontSize: '0.8125rem', display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
          <AlertCircle size={14} /> {sendError}
        </div>
      )}

      {alreadyEmailed.length > 0 && (
        <div style={{ marginTop: '1rem', padding: '0.75rem 1rem', borderRadius: '8px', backgroundColor: 'var(--warning-bg)', color: 'var(--warning-text)', fontSize: '0.8125rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
          <span>{alreadyEmailed.length} candidate{alreadyEmailed.length === 1 ? ' was' : 's were'} already emailed for this requirement and {alreadyEmailed.length === 1 ? 'was' : 'were'} skipped.</span>
          <button type="button" className="btn btn-secondary" disabled={sending} style={{ fontSize: '0.75rem' }}
            onClick={() => send(alreadyEmailed.map((s) => s.candidate_id), true)}>
            Send again anyway
          </button>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '0.75rem', marginTop: '1.25rem', flexWrap: 'wrap' }}>
        {confirming ? (
          <>
            <span style={{ fontSize: '0.8125rem', fontWeight: 600 }}>
              {simulated ? `Record ${sendable.length} simulated email${sendable.length === 1 ? '' : 's'} (nothing will be delivered)?` : `Send ${sendable.length} email${sendable.length === 1 ? '' : 's'} now?`}
            </span>
            <button type="button" className="btn btn-secondary" disabled={sending} onClick={() => setConfirming(false)}>Back to editing</button>
            <button type="button" className="btn btn-primary" disabled={sending || !sendable.length} onClick={() => send(sendable.map((r) => r.id))}>
              {sending ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
              {sending ? 'Sending…' : 'Confirm send'}
            </button>
          </>
        ) : (
          <>
            {onCancel && <button type="button" className="btn btn-secondary" onClick={onCancel}>Close</button>}
            <button type="button" className="btn btn-primary" disabled={!sendable.length || generatingCount > 0} onClick={() => setConfirming(true)}>
              <Send size={15} /> Review &amp; send {sendable.length} email{sendable.length === 1 ? '' : 's'}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
