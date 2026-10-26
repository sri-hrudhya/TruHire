import assert from 'node:assert/strict';
import { resolveActiveCategory, nextCategoryId } from '../src/lib/categories.js';
import { canEditComment, assignmentControl, formatRelativeTime, assignmentsByCandidate } from '../src/lib/review.js';

const run = (name, fn) => { try { fn(); console.log(`PASS ${name}`); } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };
const demands = [{ id: 'java' }, { id: 'pega' }];

run('resolveActiveCategory returns null for an unknown or empty id', () => {
  assert.equal(resolveActiveCategory(demands, 'gone'), null);
  assert.equal(resolveActiveCategory(demands, ''), null);
  assert.equal(resolveActiveCategory(demands, null), null);
  assert.equal(resolveActiveCategory([], 'java'), null);
});

run('resolveActiveCategory keeps a known id', () => {
  assert.equal(resolveActiveCategory(demands, 'pega'), 'pega');
});

run('category row keyboard: arrows move and wrap, Home/End jump', () => {
  const ids = [null, 'java', 'pega'];
  assert.equal(nextCategoryId(ids, null, 'ArrowRight'), 'java');
  assert.equal(nextCategoryId(ids, 'pega', 'ArrowRight'), null);
  assert.equal(nextCategoryId(ids, null, 'ArrowLeft'), 'pega');
  assert.equal(nextCategoryId(ids, 'java', 'Home'), null);
  assert.equal(nextCategoryId(ids, 'java', 'End'), 'pega');
  assert.equal(nextCategoryId(ids, 'java', 'x'), 'java');
});

run('canEditComment: author or admin only', () => {
  const comment = { author: { id: 'u1' } };
  assert.equal(canEditComment({ id: 'u1', role: 'recruiter' }, comment), true);
  assert.equal(canEditComment({ id: 'u2', role: 'recruiter' }, comment), false);
  assert.equal(canEditComment({ id: 'u2', role: 'admin' }, comment), true);
  assert.equal(canEditComment(null, comment), false);
});

run('assignmentControl: admins select, recruiters take only when unassigned', () => {
  assert.equal(assignmentControl({ role: 'admin' }, null), 'select');
  assert.equal(assignmentControl({ role: 'recruiter' }, null), 'take');
  assert.equal(assignmentControl({ role: 'recruiter' }, { assignee: { id: 'x' } }), 'text');
});

run('formatRelativeTime treats naive timestamps as UTC', () => {
  const now = Date.parse('2026-01-01T12:00:00Z');
  assert.equal(formatRelativeTime(now, '2026-01-01T11:59:50'), 'just now');
  assert.equal(formatRelativeTime(now, '2026-01-01T11:55:00'), '5 min ago');
  assert.equal(formatRelativeTime(now, '2026-01-01T09:00:00Z'), '3 hr ago');
  assert.equal(formatRelativeTime(now, '2025-12-30T12:00:00Z'), '2 days ago');
  assert.equal(formatRelativeTime(now, 'not a date'), '');
});

run('assignmentsByCandidate indexes by candidate id', () => {
  assert.deepEqual(Object.keys(assignmentsByCandidate([{ candidate_id: 'a' }, { candidate_id: 'b' }])), ['a', 'b']);
  assert.deepEqual(assignmentsByCandidate(null), {});
});
