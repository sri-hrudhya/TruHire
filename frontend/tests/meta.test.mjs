import assert from 'node:assert/strict';
import { STORAGE_KEYS, TIMEOUTS_MS, POLL_MS } from '../src/config/env.js';
import { FALLBACK_META, normalizeMeta } from '../src/lib/meta.js';

const run = (name, fn) => { try { fn(); console.log(`PASS ${name}`); } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };

run('storage keys are unique and namespaced', () => {
  const values = Object.values(STORAGE_KEYS);
  assert.equal(new Set(values).size, values.length);
  assert.ok(values.every((v) => v.startsWith('truhire_')));
});

run('timeouts and polls are positive integers', () => {
  for (const v of [...Object.values(TIMEOUTS_MS), ...Object.values(POLL_MS)]) assert.ok(Number.isInteger(v) && v > 0);
});

run('normalizeMeta fills defaults when a field is missing', () => {
  const meta = normalizeMeta({ requirement_statuses: ['A'], search: { max_top_n: 7 } });
  assert.deepEqual(meta.requirement_statuses, ['A']);
  assert.equal(meta.search.max_top_n, 7);
  assert.equal(meta.search.default_top_n, FALLBACK_META.search.default_top_n);
  assert.equal(meta.comment_max_chars, FALLBACK_META.comment_max_chars);
});

run('normalizeMeta survives null and garbage', () => {
  assert.deepEqual(normalizeMeta(null), normalizeMeta(undefined));
  assert.equal(normalizeMeta('nope').page_sizes.history, FALLBACK_META.page_sizes.history);
});
