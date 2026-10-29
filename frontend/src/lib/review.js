// Pure helpers for the shared review workflow (assignments and comment threads).

export const isAdmin = (user) => user?.role === 'admin';

// Mirrors the backend rule: the author or an admin may change a comment. The server stays authoritative.
export const canEditComment = (user, comment) => !!user && (isAdmin(user) || comment?.author?.id === user.id);

// Admins assign anyone; a recruiter may only take an unassigned candidate for themselves.
export function assignmentControl(user, assignment) {
  if (isAdmin(user)) return 'select';
  if (!assignment?.assignee) return 'take';
  return 'text';
}

// "3 min ago" style label; backend timestamps are naive UTC, so a missing zone is treated as UTC.
export function formatRelativeTime(nowMs, iso) {
  if (!iso) return '';
  const t = Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(t)) return '';
  const seconds = Math.max(0, Math.round((nowMs - t) / 1000));
  if (seconds < 60) return 'just now';
  let value;
  let label;
  if (seconds < 3600) { value = Math.floor(seconds / 60); label = 'min'; }
  else if (seconds < 86400) { value = Math.floor(seconds / 3600); label = 'hr'; }
  else { value = Math.floor(seconds / 86400); label = 'day'; }
  return `${value} ${label}${label === 'day' && value !== 1 ? 's' : ''} ago`;
}

export const assignmentsByCandidate = (list) =>
  Object.fromEntries((list || []).map((a) => [a.candidate_id, a]));
