import assert from 'node:assert/strict';
import { jdsInCategory, jdAfterCategoryChange, searchDecision, topNOptions } from '../src/lib/categories.js';

const jds = [
  { id: 'a', demand_id: 'java' }, { id: 'b', demand_id: 'java' }, { id: 'c', demand_id: 'pega' }, { id: 'd', demand_id: 'others' },
];

// Category/JD selector filtering
assert.deepEqual(jdsInCategory(jds, 'java').map((j) => j.id), ['a', 'b']);
assert.deepEqual(jdsInCategory(jds, 'camunda'), []);
assert.equal(jdsInCategory(jds, '').length, 4);

// Switching category clears an incompatible JD, keeps a compatible one
assert.equal(jdAfterCategoryChange(jds, 'pega', 'a'), '');
assert.equal(jdAfterCategoryChange(jds, 'java', 'a'), 'a');
assert.equal(jdAfterCategoryChange(jds, 'java', ''), '');
assert.equal(jdAfterCategoryChange(jds, 'java', 'missing'), '');

// JD-specific search sends the JD id only (the category just narrowed the choice)
assert.deepEqual(searchDecision({ categoryId: 'java', jdId: 'a', query: '', hasOtherFilters: false }),
  { action: 'run', mode: 'jd', positionId: 'a', demandId: null });
assert.deepEqual(searchDecision({ categoryId: '', jdId: 'a', query: 'x' }), { action: 'run', mode: 'jd', positionId: 'a', demandId: null });
// Category + keyword, no JD: scoped to the category, no position
assert.deepEqual(searchDecision({ categoryId: 'java', jdId: '', query: ' spring ', hasOtherFilters: false }),
  { action: 'run', mode: 'category-keyword', positionId: null, demandId: 'java' });
assert.equal(searchDecision({ categoryId: 'java', jdId: '', query: '', hasSkills: true }).mode, 'category-keyword');
// Category alone (even with location/role filters): nothing runs
assert.equal(searchDecision({ categoryId: 'java', jdId: '', query: '  ', hasOtherFilters: true }).action, 'need-jd-or-query');
// Keyword-only, no category
assert.deepEqual(searchDecision({ categoryId: '', jdId: '', query: 'python', hasOtherFilters: false }),
  { action: 'run', mode: 'keyword', positionId: null, demandId: null });
// Nothing at all
assert.equal(searchDecision({ categoryId: '', jdId: '', query: '', hasOtherFilters: false }).action, 'idle');
assert.equal(searchDecision({ categoryId: '', jdId: '', query: '', hasOtherFilters: true }).mode, 'keyword');

// Result-size choices come from the server limits and never exceed the maximum
assert.deepEqual(topNOptions({ default_top_n: 20, max_top_n: 100 }, [10, 50]), [10, 20, 50, 100]);
assert.deepEqual(topNOptions({ default_top_n: 20, max_top_n: 30 }, [10, 50]), [10, 20, 30]);

console.log('categories tests passed');

// --- Zero-result regression ---------------------------------------------------------------------
import { prefillFromJdFilters, emptyResultMessage, resultsViewState } from '../src/lib/categories.js';

// Picking a JD must not auto-apply hard role/location filters (they would exclude every candidate); they are suggestions.
assert.deepEqual(
  prefillFromJdFilters({ location: 'Pune, India', role: 'Generative AI Solutions Architect', sources: { role: 'jd_text' } }),
  { locations: [], role: '', suggestedLocations: ['Pune, India'], suggestedRole: 'Generative AI Solutions Architect' });
assert.deepEqual(prefillFromJdFilters({ locations: ['Pune', 'Mumbai'], location: 'Pune' }).suggestedLocations, ['Pune', 'Mumbai']);
assert.deepEqual(prefillFromJdFilters(null), { locations: [], role: '', suggestedLocations: [], suggestedRole: '' });

// Backend response with candidates is displayed; an empty one shows the backend's reason.
const payload = { total_matches: 1, top_n: 20, results: [{ candidate: { id: 'c1', candidate_name: 'Asha' }, match_score: 71.2 }], empty_reason: null };
assert.equal(resultsViewState(payload), 'results');
assert.equal(resultsViewState(payload, true), 'loading');
assert.equal(resultsViewState(null), 'idle');
const empty = { total_matches: 0, results: [], empty_reason: { code: 'no_candidates', message: 'No candidates have been ingested yet.' } };
assert.equal(resultsViewState(empty), 'empty');
assert.equal(emptyResultMessage(empty), 'No candidates have been ingested yet.');
assert.match(emptyResultMessage({ results: [] }), /No candidates found/);
