import { useState } from 'react';
import Modal from '../ui/Modal';
import { timeAgo } from '../../lib/ingestion';
import './ingestion.css';

// Shown before an upload when some files were already ingested. Each duplicate is Skipped (default) or Updated
// (re-ingested over the existing resume); onConfirm receives { filename: 'update' | 'skip' }.
export default function DuplicateDialog({ duplicates, onConfirm, onClose }) {
  const [actions, setActions] = useState(() => Object.fromEntries(duplicates.map((d) => [d.filename, 'skip'])));
  const setAll = (value) => setActions(Object.fromEntries(duplicates.map((d) => [d.filename, value])));

  return (
    <Modal
      title="Resumes already ingested"
      onClose={onClose}
      footer={(
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel upload</button>
          <button type="button" className="btn btn-primary" onClick={() => onConfirm(actions)}>Continue upload</button>
        </>
      )}
    >
      <p>{duplicates.length === 1 ? 'This file was' : `These ${duplicates.length} files were`} ingested before. Choose to skip each one or update the existing resume with it.</p>
      <p className="dup-all">
        Apply to all:
        <button type="button" className="btn btn-secondary btn-compact" onClick={() => setAll('skip')}>Skip all</button>
        <button type="button" className="btn btn-secondary btn-compact" onClick={() => setAll('update')}>Update all</button>
      </p>
      <ul className="dup-list">
        {duplicates.map((d) => (
          <li key={d.filename} className="dup-row">
            <div className="dup-info">
              <strong className="dup-file">{d.filename}</strong>
              <span className="slug">
                {d.display_id} {d.candidate_name} · Ingested {timeAgo(d.uploaded_at) || 'earlier'}{d.uploaded_by ? ` by ${d.uploaded_by}` : ''}
              </span>
            </div>
            <div className="dup-choice" role="radiogroup" aria-label={`What to do with ${d.filename}`}>
              {['skip', 'update'].map((value) => (
                <label key={value}>
                  <input type="radio" name={`dup-${d.filename}`} checked={actions[d.filename] === value} onChange={() => setActions((prev) => ({ ...prev, [d.filename]: value }))} />
                  {value === 'skip' ? 'Skip' : 'Update'}
                </label>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
