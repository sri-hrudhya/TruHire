// Pure helpers for the Requirements section (demand cards, JD cards, JD form, history log).

export const MAX_EXPERIENCE_YEARS = 60;

// A date-only value ("2026-11-01") shows as the same calendar day in every timezone.
export function formatDate(value) {
  if (!value) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

// Timestamps from the API are UTC; the offset is added when the server omitted it.
export function formatDateTime(value) {
  if (!value) return '—';
  const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function formatExperience(years) {
  if (years === null || years === undefined || years === '') return '—';
  const n = Number(years);
  return Number.isFinite(n) ? `${n} ${n === 1 ? 'yr' : 'yrs'}` : '—';
}

// The role is only worth showing when it says something the title does not.
const squash = (v) => (v || '').toLowerCase().replace(/\s+/g, ' ').trim();
export const showRole = (jd) => !!squash(jd?.role) && squash(jd.role) !== squash(jd.title);

// Form values -> API payload. Blank means "not stated" (null), so clearing a field is expressible.
export function detailsPayload({ location, experience, startDate, endDate, status }) {
  const text = (v) => (v || '').trim() || null;
  return {
    location: text(location),
    experience_years: experience === '' || experience === null || experience === undefined ? null : Number(experience),
    start_date: startDate || null,
    end_date: endDate || null,
    status,
  };
}

// Error message for unacceptable form values, or null.
export function validateDetails({ experience, startDate, endDate }) {
  if (experience !== '' && experience !== null && experience !== undefined) {
    const n = Number(experience);
    if (!Number.isFinite(n) || n < 0 || n > MAX_EXPERIENCE_YEARS) return `Experience must be a number from 0 to ${MAX_EXPERIENCE_YEARS} years.`;
  }
  if (startDate && endDate && endDate < startDate) return 'End date cannot be before the start date.';
  return null;
}

// Only the fields that differ from what the form was opened with, so saving an old JD does not record edits nobody made.
export function changedDetails(initial, current) {
  const next = detailsPayload(current);
  const was = detailsPayload(initial);
  return Object.fromEntries(Object.entries(next).filter(([k, v]) => v !== was[k]));
}

export const HISTORY_ACTION_LABELS = Object.freeze({
  created: 'Created', updated: 'Updated', status_changed: 'Status changed', deleted: 'Deleted',
});

const FIELD_LABELS = {
  title: 'Title', jd_text: 'Specification', role: 'Role', experience_years: 'Experience (yrs)', start_date: 'Start date',
  end_date: 'End date', location: 'Location', status: 'JD status', demand: 'Demand', reason: 'Reason',
};
const show = (v) => (v === null || v === undefined || v === '' ? 'empty' : String(v));

// One row per changed field: { field, from, to } as display text. 'from' is null for creations, 'to' for deletions.
export function historyChanges(entry) {
  return Object.entries(entry?.changes || {}).map(([key, v]) => {
    if (!v || typeof v !== 'object' || !('old' in v || 'new' in v)) return { field: FIELD_LABELS[key] || key, from: null, to: show(v) };
    return {
      field: FIELD_LABELS[key] || key,
      from: entry.action === 'created' ? null : show(v.old),
      to: entry.action === 'deleted' ? null : show(v.new),
    };
  });
}
