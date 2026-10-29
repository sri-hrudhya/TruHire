import { AlertCircle, Check, Loader2, X } from 'lucide-react';
import './ui.css';

const ICONS = { success: Check, error: AlertCircle, info: Loader2, warning: AlertCircle };

// Inline status line: success, error, warning, or an in-progress note.
export default function Notice({ type = 'info', onDismiss = null, children }) {
  const Icon = ICONS[type] || AlertCircle;
  return (
    <div className={`notice notice-${type}`} role={type === 'error' ? 'alert' : 'status'}>
      <Icon size={16} className={type === 'info' ? 'animate-spin' : undefined} aria-hidden="true" />
      <span className="notice-text">{children}</span>
      {onDismiss && (
        <button type="button" className="icon-btn" onClick={onDismiss} aria-label="Dismiss">
          <X size={14} />
        </button>
      )}
    </div>
  );
}
