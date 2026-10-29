import { useEffect, useState } from 'react';
import { Check, Loader2, Search, X } from 'lucide-react';
import Modal from '../ui/Modal';
import { candidatesApi } from '../../lib/api';
import { MAX_CANCELLATION_REASON } from '../../lib/requirements';

function Footer({ busy, canConfirm, onClose, label, onConfirm }) {
  return (
    <>
      <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
      <button type="button" className="btn btn-primary" onClick={onConfirm} disabled={busy || !canConfirm}>
        {busy ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />} {label}
      </button>
    </>
  );
}

// Choosing Cancelled asks for the reason first; nothing is saved until it is given.
// onConfirm resolves to null on success or an error message to show inside the popup.
export function CancelReasonModal({ initial = '', onConfirm, onClose }) {
  const [reason, setReason] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const confirm = async () => {
    setBusy(true);
    const problem = await onConfirm(reason.trim());
    setBusy(false);
    if (problem) setError(problem); else onClose();
  };
  return (
    <Modal title="Cancel demand" size="sm" busy={busy} onClose={onClose}
      footer={<Footer busy={busy} canConfirm={!!reason.trim()} onClose={onClose} label="Confirm cancellation" onConfirm={confirm} />}>
      <label className="input-label" htmlFor="cancel-reason">Reason for cancelling</label>
      <textarea id="cancel-reason" className="input-field" rows={4} maxLength={MAX_CANCELLATION_REASON} autoFocus required
        value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why is this demand being cancelled?" />
      {error && <p className="req-error" role="alert">{error}</p>}
    </Modal>
  );
}

// Choosing Mapped or Fulfilled asks which resume(s) the demand is filled with: search by resume ID or name,
// tick one or more, then confirm. `initial` is the current selection as [{ id, display_id, candidate_name }].
export function MapResumesModal({ status, initial = [], onConfirm, onClose }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [selected, setSelected] = useState(() => new Map(initial.map((r) => [r.id, r])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    setSearching(true);
    const timer = setTimeout(async () => {
      try {
        const data = (await candidatesApi.list({ q: query.trim() || undefined, limit: 20 }, true)).data;
        if (live) { setResults(data.candidates || []); setSearchError(null); }
      } catch {
        if (live) setSearchError('Could not search resumes. Try again.');
      } finally {
        if (live) setSearching(false);
      }
    }, query ? 250 : 0);
    return () => { live = false; clearTimeout(timer); };
  }, [query]);

  const toggle = (c) => setSelected((prev) => {
    const next = new Map(prev);
    if (next.has(c.id)) next.delete(c.id); else next.set(c.id, { id: c.id, display_id: c.display_id, candidate_name: c.candidate_name });
    return next;
  });

  const confirm = async () => {
    setBusy(true);
    const problem = await onConfirm([...selected.keys()], [...selected.values()]);
    setBusy(false);
    if (problem) setError(problem); else onClose();
  };

  return (
    <Modal title={`Mark demand as ${status}`} size="md" busy={busy} onClose={onClose}
      footer={<Footer busy={busy} canConfirm={selected.size > 0} onClose={onClose} label={`Confirm (${selected.size})`} onConfirm={confirm} />}>
      <div className="folder-search">
        <Search size={16} aria-hidden="true" />
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} autoFocus
          placeholder="Search resumes by ID or candidate name" aria-label="Search resumes by ID or candidate name" />
      </div>
      {selected.size > 0 && (
        <ul className="chip-list" aria-label="Selected resumes">
          {[...selected.values()].map((r) => (
            <li key={r.id} className="chip">
              <span>{r.display_id || '—'} · {r.candidate_name || 'Unnamed'}</span>
              <button type="button" className="icon-btn" onClick={() => toggle(r)} aria-label={`Remove ${r.candidate_name || r.display_id}`}><X size={12} /></button>
            </li>
          ))}
        </ul>
      )}
      {searchError && <p className="req-error" role="alert">{searchError}</p>}
      <ul className="resume-pick" aria-label="Matching resumes" aria-busy={searching}>
        {results.map((c) => (
          <li key={c.id}>
            <label className="resume-pick-row">
              <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c)} />
              <span className="slug">{c.display_id || '—'}</span>
              <span>{c.candidate_name || 'Unnamed candidate'}</span>
            </label>
          </li>
        ))}
        {!searching && !searchError && results.length === 0 && <li className="req-empty">{query.trim() ? `No resumes match “${query.trim()}”.` : 'No resumes uploaded yet.'}</li>}
      </ul>
      {error && <p className="req-error" role="alert">{error}</p>}
    </Modal>
  );
}
