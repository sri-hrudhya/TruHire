// Pure helpers for the Ingestion section: resume freshness and the notice-period field.

export const RECENT_RESUME_DAYS = 7;
export const MAX_NOTICE_DAYS = 365 * 2;
export const UNIT_DAYS = Object.freeze({ Days: 1, Weeks: 7, Months: 30 });
export const NOTICE_UNITS = Object.freeze(Object.keys(UNIT_DAYS));

// Stored timestamps are naive UTC; mark them so the browser converts correctly.
const asUtc = (value) => new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`);

// 'recent' = uploaded within RECENT_RESUME_DAYS, 'old' = earlier, null = no usable date.
export function freshness(uploadedAt, now = Date.now(), recentDays = RECENT_RESUME_DAYS) {
  if (!uploadedAt) return null;
  const t = asUtc(uploadedAt).getTime();
  if (Number.isNaN(t)) return null;
  return now - t <= recentDays * 86_400_000 ? 'recent' : 'old';
}

export const FRESHNESS_LABEL = Object.freeze({ recent: 'Recently uploaded', old: 'Old' });

// "12 Oct 2026, 6:01 PM IST": upload times are always Indian Standard Time, whatever the browser's timezone.
export function formatIst(uploadedAt) {
  if (!uploadedAt) return '—';
  const d = asUtc(uploadedAt);
  if (Number.isNaN(d.getTime())) return '—';
  const text = d.toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'Asia/Kolkata' });
  return `${text.replace(/\b(am|pm)\b/, (m) => m.toUpperCase())} IST`;
}

// "3 days ago": how long ago a resume was ingested ('' when the date is missing or unreadable).
const AGO_UNITS = [['year', 365 * 86_400_000], ['month', 30 * 86_400_000], ['day', 86_400_000], ['hour', 3_600_000], ['minute', 60_000]];
export function timeAgo(uploadedAt, now = Date.now()) {
  if (!uploadedAt) return '';
  const t = asUtc(uploadedAt).getTime();
  if (Number.isNaN(t)) return '';
  const elapsed = now - t;
  for (const [unit, ms] of AGO_UNITS) {
    const n = Math.floor(elapsed / ms);
    if (n >= 1) return `${n} ${unit}${n === 1 ? '' : 's'} ago`;
  }
  return 'just now';
}

export function formatNotice(value, unit) {
  if (value === null || value === undefined || !unit) return 'Not set';
  return `${value} ${Number(value) === 1 ? unit.replace(/s$/, '') : unit}`;
}

// { error } for an invalid pair, else { value, unit } to send (both null clears the notice period).
export function noticePayload(rawValue, unit) {
  if (rawValue === '' || rawValue === null || rawValue === undefined) return { value: null, unit: null };
  const n = Number(rawValue);
  if (!Number.isFinite(n) || n < 0) return { error: 'Enter a number that is 0 or more.' };
  if (!NOTICE_UNITS.includes(unit)) return { error: 'Choose Days, Weeks or Months.' };
  if (n * UNIT_DAYS[unit] > MAX_NOTICE_DAYS) return { error: 'Notice period cannot exceed 2 years.' };
  return { value: n, unit };
}
