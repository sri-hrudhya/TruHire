import { useEffect, useRef, useState } from 'react';
import { FileText, Info } from 'lucide-react';
import './requirements.css';

// Small icon beside a Cancelled / Mapped / Fulfilled status. Click it to read the saved cancellation reason
// or the resumes the demand is associated with. Renders nothing for any other status.
export default function StatusNote({ jd }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (e.type === 'keydown' ? e.key === 'Escape' : !ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', close); };
  }, [open]);

  const cancelled = jd.status === 'Cancelled';
  const linked = jd.status === 'Mapped' || jd.status === 'Fulfilled' || jd.status === 'Map';
  if (!cancelled && !linked) return null;
  const resumes = jd.mapped_resumes || [];
  const Icon = cancelled ? Info : FileText;
  const label = cancelled ? 'Show cancellation reason' : `Show ${jd.status} resumes`;

  return (
    <span className="status-note" ref={ref}>
      <button type="button" className="icon-btn status-note-btn" onClick={() => setOpen((o) => !o)} aria-label={label} aria-expanded={open} title={label}>
        <Icon size={14} />
      </button>
      {open && (
        <div className="status-note-pop" role="dialog" aria-label={cancelled ? 'Cancellation reason' : 'Associated resumes'}>
          {cancelled ? (
            <>
              <strong>Cancellation reason</strong>
              <p>{jd.cancellation_reason || 'No reason was recorded for this demand.'}</p>
            </>
          ) : (
            <>
              <strong>{jd.status === 'Fulfilled' ? 'Fulfilled with' : 'Mapped to'} {resumes.length === 1 ? 'resume' : 'resumes'}</strong>
              {resumes.length === 0 ? <p>No resumes are recorded for this demand.</p> : (
                <ul>{resumes.map((r) => <li key={r.id}><span className="slug">{r.display_id || '—'}</span> {r.candidate_name || 'Unnamed candidate'}</li>)}</ul>
              )}
            </>
          )}
        </div>
      )}
    </span>
  );
}
