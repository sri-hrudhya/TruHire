import { CalendarRange, X } from 'lucide-react';
import './requirements.css';

// From / To pair of date inputs; empty means unbounded.
export default function DateRangeFilter({ from, to, onChange }) {
  return (
    <div className="date-filter" role="group" aria-label="Filter by date">
      <CalendarRange size={16} aria-hidden="true" />
      <label>From <input type="date" value={from} max={to || undefined} onChange={(e) => onChange({ from: e.target.value, to })} /></label>
      <label>To <input type="date" value={to} min={from || undefined} onChange={(e) => onChange({ from, to: e.target.value })} /></label>
      {(from || to) && (
        <button type="button" className="icon-btn" onClick={() => onChange({ from: '', to: '' })} aria-label="Clear date filter" title="Clear date filter"><X size={14} /></button>
      )}
    </div>
  );
}
