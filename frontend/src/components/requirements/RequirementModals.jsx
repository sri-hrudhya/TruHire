import { useState } from 'react';
import { Loader2, Sparkles, Trash2 } from 'lucide-react';
import Modal from '../ui/Modal';
import EmailComposer, { RecipientSelector } from '../EmailComposer';

export function DeleteRequirementModal({ jd, onConfirm, onClose }) {
  const [busy, setBusy] = useState(false);
  const confirm = async () => {
    setBusy(true);
    const ok = await onConfirm(jd);
    setBusy(false);
    if (ok) onClose();
  };
  return (
    <Modal
      title="Remove requirement"
      size="sm"
      busy={busy}
      onClose={onClose}
      footer={(
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className="btn btn-danger" onClick={confirm} disabled={busy}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />} Remove
          </button>
        </>
      )}
    >
      <p>Remove <strong>{jd.display_id}</strong> “{jd.title}”?</p>
    </Modal>
  );
}

export function RetentionModal({ retention, onCleanup, onClose }) {
  const [busy, setBusy] = useState(false);
  const run = async () => { setBusy(true); await onCleanup(); setBusy(false); };
  const rows = [
    ['Retention period', `${retention?.data_retention_days} days`],
    ['Cleanup runs every', `${retention?.cleanup_interval_hours} hours`],
    ['Resumes past retention', retention?.expired_candidates_count || 0],
    ['Requirements past retention', retention?.expired_positions_count || 0],
  ];
  return (
    <Modal
      title="Data retention"
      size="sm"
      busy={busy}
      onClose={onClose}
      footer={(
        <>
          <button type="button" className="btn btn-secondary" onClick={run} disabled={busy}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />} Run cleanup now
          </button>
          <button type="button" className="btn btn-primary" onClick={onClose}>Close</button>
        </>
      )}
    >
      <dl className="kv">
        {rows.map(([k, v]) => (<div key={k}><dt>{k}</dt><dd>{v}</dd></div>))}
      </dl>
    </Modal>
  );
}

export function EmailShortlistModal({ jd, candidates, onSent, onClose }) {
  const [step, setStep] = useState('select');
  const [selected, setSelected] = useState(() => candidates.filter((c) => c.email).map((c) => c.id));
  return (
    <Modal title={`Email shortlisted candidates · ${jd.display_id}`} size="lg" onClose={onClose}>
      {step === 'select' ? (
        <>
          <RecipientSelector candidates={candidates} selectedIds={selected} onChange={setSelected} />
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="button" className="btn btn-primary" disabled={!selected.length} onClick={() => setStep('compose')}>
              <Sparkles size={15} /> Draft {selected.length} email{selected.length === 1 ? '' : 's'}
            </button>
          </div>
        </>
      ) : (
        <EmailComposer position={jd} recipients={candidates.filter((c) => selected.includes(c.id))} onSent={onSent} onCancel={onClose} />
      )}
    </Modal>
  );
}
