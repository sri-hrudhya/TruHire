import { useState } from 'react';
import { X } from 'lucide-react';
import './ui.css';

// Several short values in one field: type and press Enter or comma to add, Backspace on an empty box removes the last.
// Text still in the box when it loses focus is added too, so nothing typed is lost on submit.
export default function TagInput({ id, values, onChange, placeholder, maxItems = 10, maxLength = 100, ariaLabel, itemLabel = 'value' }) {
  const [draft, setDraft] = useState('');

  const add = (raw) => {
    const parts = raw.split(',').map((p) => p.replace(/\s+/g, ' ').trim()).filter(Boolean);
    if (!parts.length) { setDraft(''); return; }
    const next = [...values];
    for (const part of parts) {
      if (next.length < maxItems && !next.some((v) => v.toLowerCase() === part.toLowerCase())) next.push(part.slice(0, maxLength));
    }
    onChange(next);
    setDraft('');
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      if (draft.trim() || e.key === ',') e.preventDefault();
      if (draft.trim()) add(draft);
    } else if (e.key === 'Backspace' && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  };

  return (
    <div className="tag-input input-field" onClick={(e) => e.currentTarget.querySelector('input')?.focus()}>
      {values.map((v) => (
        <span key={v} className="chip">
          {v}
          <button type="button" className="chip-remove" onClick={() => onChange(values.filter((x) => x !== v))} aria-label={`Remove ${itemLabel} ${v}`}><X size={12} /></button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        maxLength={maxLength}
        disabled={values.length >= maxItems}
        onChange={(e) => (e.target.value.includes(',') ? add(e.target.value) : setDraft(e.target.value))}
        onKeyDown={onKeyDown}
        onBlur={() => draft.trim() && add(draft)}
        placeholder={values.length ? '' : placeholder}
        aria-label={ariaLabel}
      />
    </div>
  );
}
