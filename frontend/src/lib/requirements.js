// Pure helpers for the Requirements section (folder cards, demand cards, demand form, history log).

export const MAX_EXPERIENCE_YEARS = 60;
export const MAX_LOCATIONS = 10;
export const MAX_POSITIONS = 10000;
// The client dropdown's last choice: the recruiter types the name.
export const OTHER_CLIENT = '__other__';
// Fixed list of people a demand can be owned by (shown in the editor's Demand Owner dropdown).
export const DEMAND_OWNERS = Object.freeze([
  'Akshitha Margani',
  'Anurag Bohini',
  'Chandra Teja Allamsetty',
  'Manvitha Kamuni',
  'Rama Devi Badhri',
  'Swathi Priya Nadindla',
]);
export const MAX_CANCELLATION_REASON = 1000;

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

const blank = (v) => v === null || v === undefined || v === '';

// "3-5 yrs", "3+ yrs", "up to 5 yrs", "4 yrs" (min equals max) or "—".
export function formatExperience(min, max) {
  const lo = blank(min) ? null : Number(min);
  const hi = blank(max) ? null : Number(max);
  const okLo = lo !== null && Number.isFinite(lo);
  const okHi = hi !== null && Number.isFinite(hi);
  const unit = (n) => (n === 1 ? 'yr' : 'yrs');
  if (okLo && okHi) return lo === hi ? `${lo} ${unit(lo)}` : `${lo}-${hi} yrs`;
  if (okLo) return `${lo}+ ${unit(lo)}`;
  if (okHi) return `up to ${hi} ${unit(hi)}`;
  return '—';
}

// A demand's places as a list; demands saved before several places were allowed carry one `location` text.
export const jdLocations = (jd) => (Array.isArray(jd?.locations) && jd.locations.length ? jd.locations : jd?.location ? [jd.location] : []);
export const formatLocations = (jd) => jdLocations(jd).join(', ') || '—';
export const formatPositions = (n) => (n === null || n === undefined || n === '' ? '—' : String(n));

// The role is only worth showing when it says something the title does not.
const squash = (v) => (v || '').toLowerCase().replace(/\s+/g, ' ').trim();
export const showRole = (jd) => !!squash(jd?.role) && squash(jd.role) !== squash(jd.title);

// Statuses that carry extra data: a Cancelled demand its reason, a Mapped / Fulfilled one its resumes.
export const CANCELLED = 'Cancelled';
export const RESUME_LINKED = ['Mapped', 'Fulfilled'];

// Form values -> API payload. Blank means "not stated" (null), so clearing a field is expressible.
// The reason / resume ids are only sent with the status that needs them.
export function detailsPayload({ demandId, locations, clientName, demandOwner, currentStatus, experience, experienceMax, noOfPositions, startDate, endDate, status, cancellationReason, candidateIds }) {
  const text = (v) => (v || '').trim() || null;
  return {
    ...(status === CANCELLED ? { cancellation_reason: text(cancellationReason) } : {}),
    ...(RESUME_LINKED.includes(status) ? { candidate_ids: candidateIds || [] } : {}),
    ...(demandId ? { demand_id: demandId } : {}),
    locations: (locations || []).map((p) => (p || '').trim()).filter(Boolean),
    no_of_positions: blank(noOfPositions) ? null : Number(noOfPositions),
    client_name: text(clientName),
    demand_owner: text(demandOwner),
    current_status: text(currentStatus),
    experience_years: blank(experience) ? null : Number(experience),
    experience_max_years: blank(experienceMax) ? null : Number(experienceMax),
    start_date: startDate || null,
    end_date: endDate || null,
    status,
  };
}

// Error message for unacceptable form values, or null.
export function validateDetails({ experience, experienceMax, noOfPositions, locations, startDate, endDate }) {
  if ((locations || []).length > MAX_LOCATIONS) return `Add at most ${MAX_LOCATIONS} locations.`;
  if (!blank(noOfPositions)) {
    const n = Number(noOfPositions);
    if (!Number.isInteger(n) || n < 0 || n > MAX_POSITIONS) return `No. of positions must be a whole number from 0 to ${MAX_POSITIONS}.`;
  }
  for (const [label, value] of [['Min experience', experience], ['Max experience', experienceMax]]) {
    if (blank(value)) continue;
    const n = Number(value);
    if (!Number.isFinite(n) || n < 0 || n > MAX_EXPERIENCE_YEARS) return `${label} must be a number from 0 to ${MAX_EXPERIENCE_YEARS} years.`;
  }
  if (!blank(experience) && !blank(experienceMax) && Number(experienceMax) < Number(experience)) return 'Max experience cannot be less than min experience.';
  if (startDate && endDate && endDate < startDate) return 'End date cannot be before the start date.';
  return null;
}

// Only the fields that differ from what the form was opened with, so saving an old JD does not record edits nobody made.
export function changedDetails(initial, current) {
  const next = detailsPayload(current);
  const was = detailsPayload(initial);
  const same = (a, b) => a === b || JSON.stringify(a) === JSON.stringify(b);
  return Object.fromEntries(Object.entries(next).filter(([k, v]) => !same(v, was[k])));
}

export const HISTORY_ACTION_LABELS = Object.freeze({
  created: 'Created', updated: 'Updated', status_changed: 'Status changed', deleted: 'Deleted',
});

const FIELD_LABELS = {
  title: 'Title', jd_text: 'Specification', role: 'Role', experience_years: 'Min experience (yrs)', experience_max_years: 'Max experience (yrs)', no_of_positions: 'No. of positions', work_mode: 'Work mode', start_date: 'Start date',
  end_date: 'End date', location: 'Location', client_name: 'Client', demand_owner: 'Demand owner', current_status: 'Current status', status: 'Demand status', demand: 'Practice', reason: 'Reason',
  cancellation_reason: 'Cancellation reason', mapped_resumes: 'Resumes',
};
const show = (v) => (v === null || v === undefined || v === '' ? 'empty' : String(v));
const historyValue = (key, value) => {
  if (key === 'demand' && typeof value === 'string') return value.replace(/^TRU-DM-[0-9]+[^A-Za-z0-9]+/i, '');
  return show(value);
};

// One row per changed field: { field, from, to } as display text. 'from' is null for creations, 'to' for deletions.
export function historyChanges(entry) {
  return Object.entries(entry?.changes || {}).map(([key, v]) => {
    if (!v || typeof v !== 'object' || !('old' in v || 'new' in v)) return { field: FIELD_LABELS[key] || key, from: null, to: show(v) };
    return {
      field: FIELD_LABELS[key] || key,
      from: entry.action === 'created' ? null : historyValue(key, v.old),
      to: entry.action === 'deleted' ? null : historyValue(key, v.new),
    };
  });
}

// Folder order: open demands first, then mapped and fulfilled (still live work), then cancelled.
// Newest first within a status; the sort is stable, so ties keep API order.
const STATUS_RANK = { Open: 0, Mapped: 1, Map: 1, Fulfilled: 2, Cancelled: 4 };
export const statusRank = (status) => STATUS_RANK[status || 'Open'] ?? 2;
export function sortByStatus(items) {
  const time = (j) => Date.parse(j.created_at) || 0;
  return [...items].sort((a, b) => statusRank(a.status) - statusRank(b.status) || time(b) - time(a));
}

// Partial, case-insensitive match on the demand ID or title. IDs also match without punctuation ("jd 12", "jd12").
const squashId = (v) => String(v || '').toLowerCase().replace(/[^a-z0-9]/g, '');
export function filterDemands(items, query) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return items;
  const qId = squashId(q);
  return items.filter((j) => (j.title || '').toLowerCase().includes(q)
    || (j.display_id || '').toLowerCase().includes(q)
    || (qId && squashId(j.display_id).includes(qId)));
}

// The URL value for demands that name no client.
export const UNASSIGNED_CLIENT = '__unassigned__';
export const clientKey = (jd) => (jd?.client_name || '').trim();
export const inClient = (jd, name) => (name === UNASSIGNED_CLIENT ? !clientKey(jd) : clientKey(jd).toLocaleLowerCase() === (name || '').toLocaleLowerCase());

// Client folders from a list of demands: { name ('' = none), items, cancelled, practices: Map(practiceId -> demands),
// positions }, alphabetical with the unassigned folder last.
// Client names that differ only by case share one folder. `positions` is the headcount opened: the sum of
// no_of_positions over live (not cancelled) demands, blank counting as 0.
export function groupByClient(jds) {
  const groups = new Map();
  for (const jd of jds) {
    const key = clientKey(jd).toLocaleLowerCase();
    if (!groups.has(key)) groups.set(key, { name: clientKey(jd), items: [], cancelled: 0, positions: 0, practices: new Map() });
    const group = groups.get(key);
    group.items.push(jd);
    if (jd.status === CANCELLED) group.cancelled += 1;
    else {
      const n = Number(jd.no_of_positions) || 0;
      group.positions += n;
      group.practices.set(jd.demand_id, (group.practices.get(jd.demand_id) || 0) + 1);
    }
  }
  return [...groups.values()].sort((a, b) => (!a.name) - (!b.name) || a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
}

// Table sections for the list view: [{ key, label, items }] by practice name or client name; items keep their order.
export function groupRows(jds, by, practiceName) {
  const label = (jd) => (by === 'client' ? clientKey(jd) || 'No client assigned' : practiceName(jd.demand_id) || 'No practice assigned');
  const groups = new Map();
  for (const jd of jds) {
    const name = label(jd);
    const key = name.toLocaleLowerCase();
    if (!groups.has(key)) groups.set(key, { key, label: name, items: [] });
    groups.get(key).items.push(jd);
  }
  const last = (g) => /^no (client|practice) assigned$/i.test(g.label);
  return [...groups.values()].sort((a, b) => last(a) - last(b) || a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }));
}
