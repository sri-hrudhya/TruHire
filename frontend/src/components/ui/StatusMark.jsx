import { markFor } from '../../config/statusMarks';
import './ui.css';

// Review status as a small drawn mark; the text label is always available to screen readers.
export default function StatusMark({ status, showLabel = false }) {
  const kind = markFor(status);
  return (
    <span className={`status-mark status-mark-${kind}`} title={status}>
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
        <circle cx="7" cy="7" r="5.25" className="status-mark-ring" />
        {kind === 'filled' && <circle cx="7" cy="7" r="3" className="status-mark-fill" />}
        {kind === 'struck' && <line x1="2" y1="12" x2="12" y2="2" className="status-mark-strike" />}
      </svg>
      {showLabel ? <span>{status}</span> : <span className="sr-only">{status}</span>}
    </span>
  );
}
