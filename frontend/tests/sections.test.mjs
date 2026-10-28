import assert from 'node:assert/strict';
import { changedDetails, clientSummary, filterDemands, sortByStatus, detailsPayload, showRole, formatDate, formatExperience, historyChanges, validateDetails } from '../src/lib/requirements.js';
import { MAX_NOTICE_DAYS, freshness, formatNotice, noticePayload } from '../src/lib/ingestion.js';
import { explainScore, skillComparison } from '../src/lib/scoreExplanation.js';
import { FALLBACK_META } from '../src/lib/meta.js';

const run = (name, fn) => { try { fn(); console.log(`PASS ${name}`); } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };
const DAY = 86_400_000;

run('JD statuses are exactly Open, Cancelled, Fulfilled, Mapped (no Closed)', () => {
  assert.deepEqual(FALLBACK_META.jd_statuses, ['Open', 'Cancelled', 'Fulfilled', 'Mapped']);
  assert.deepEqual(FALLBACK_META.resume_linked_jd_statuses, ['Mapped', 'Fulfilled']);
  assert.deepEqual(FALLBACK_META.client_names, ['Cretera', 'Infosys', 'Coforge', 'Aaseya', 'NTT Data', 'Utsuk']);
  assert.equal(FALLBACK_META.default_jd_status, 'Open');
});

run('details validation: experience range and date order', () => {
  assert.equal(validateDetails({ experience: '5', startDate: '2026-01-01', endDate: '2026-01-01' }), null);
  assert.equal(validateDetails({ experience: '', startDate: '', endDate: '' }), null);
  assert.match(validateDetails({ experience: '-1' }), /Min experience/);
  assert.match(validateDetails({ experience: '61' }), /Min experience/);
  assert.match(validateDetails({ experience: 'abc' }), /Min experience/);
  assert.match(validateDetails({ startDate: '2026-02-01', endDate: '2026-01-01' }), /End date/);
});

run('detailsPayload turns blanks into null and trims text', () => {
  assert.deepEqual(detailsPayload({ role: 'ignored', location: '  Pune ', experience: '', startDate: '', endDate: '', status: 'Open' }),
    { location: 'Pune', client_name: null, experience_years: null, experience_max_years: null, start_date: null, end_date: null, status: 'Open' });
  assert.equal(detailsPayload({ experience: '0', status: 'Open' }).experience_years, 0);
  assert.equal(detailsPayload({ experience: '3', experienceMax: '5', status: 'Open' }).experience_max_years, 5);
});

run('min / max experience: validation and display', () => {
  assert.equal(validateDetails({ experience: '3', experienceMax: '5' }), null);
  assert.equal(validateDetails({ experience: '', experienceMax: '5' }), null);
  assert.match(validateDetails({ experience: '5', experienceMax: '3' }), /Max experience cannot be less/);
  assert.match(validateDetails({ experienceMax: '61' }), /Max experience/);
  assert.equal(formatExperience(3, 5), '3-5 yrs');
  assert.equal(formatExperience(3, null), '3+ yrs');
  assert.equal(formatExperience(null, 5), 'up to 5 yrs');
  assert.equal(formatExperience(4, 4), '4 yrs');
  assert.equal(formatExperience(null, null), '—');
});

run('changedDetails sends only edited fields', () => {
  const initial = { location: 'Pune', experience: '3', startDate: '', endDate: '', status: 'Open' };
  assert.deepEqual(changedDetails(initial, initial), {});
  assert.deepEqual(changedDetails(initial, { ...initial, location: '', status: 'Open' }), { location: null });
});

run('a status that needs extra data sends it, and only with that status', () => {
  const initial = { status: 'Open' };
  assert.deepEqual(changedDetails(initial, { ...initial, status: 'Cancelled', cancellationReason: '  Budget cut ' }), { status: 'Cancelled', cancellation_reason: 'Budget cut' });
  assert.deepEqual(changedDetails(initial, { ...initial, status: 'Mapped', candidateIds: ['a', 'b'] }), { status: 'Mapped', candidate_ids: ['a', 'b'] });
  assert.equal('candidate_ids' in detailsPayload({ status: 'Open', candidateIds: ['a'] }), false);
  assert.equal('cancellation_reason' in detailsPayload({ status: 'Mapped', cancellationReason: 'x' }), false);
  // Untouched Mapped demand: nothing to send.
  const mapped = { status: 'Mapped', candidateIds: ['a', 'b'] };
  assert.deepEqual(changedDetails(mapped, { ...mapped, candidateIds: ['a', 'b'] }), {});
  assert.deepEqual(changedDetails(mapped, { ...mapped, candidateIds: ['a'] }), { candidate_ids: ['a'] });
});

run('date-only values keep their calendar day; missing values show a dash', () => {
  assert.match(formatDate('2026-11-01'), /1/);
  assert.equal(formatDate(null), '—');
  assert.equal(formatExperience(1), '1+ yr');
  assert.equal(formatExperience(5), '5+ yrs');
  assert.equal(formatExperience(null), '—');
});

run('role is shown only when it differs from the title', () => {
  assert.equal(showRole({ title: 'Java Developer', role: 'java  developer' }), false);
  assert.equal(showRole({ title: 'Java Developer', role: 'Backend Engineer' }), true);
  assert.equal(showRole({ title: 'Java Developer', role: null }), false);
  assert.equal(showRole({ title: 'Java Developer', role: '  ' }), false);
});

run('history rows show previous and new values, and only one side for create/delete', () => {
  const upd = historyChanges({ action: 'updated', changes: { location: { old: 'Pune', new: 'Mumbai' }, role: { old: null, new: 'Lead' } } });
  assert.deepEqual(upd, [{ field: 'Location', from: 'Pune', to: 'Mumbai' }, { field: 'Role', from: 'empty', to: 'Lead' }]);
  assert.equal(historyChanges({ action: 'created', changes: { status: { old: null, new: 'Open' } } })[0].from, null);
  assert.equal(historyChanges({ action: 'deleted', changes: { status: { old: 'Open', new: null } } })[0].to, null);
  assert.deepEqual(historyChanges({ action: 'updated' }), []);
});

run('freshness: recent within 7 days, old after, null without a date', () => {
  const now = Date.parse('2026-10-23T12:00:00Z');
  assert.equal(freshness('2026-10-22T12:00:00', now), 'recent');           // naive timestamps are read as UTC
  assert.equal(freshness(new Date(now - 7 * DAY).toISOString(), now), 'recent');
  assert.equal(freshness(new Date(now - 8 * DAY).toISOString(), now), 'old');
  assert.equal(freshness(null, now), null);
  assert.equal(freshness('garbage', now), null);
});

run('notice period payload validation', () => {
  assert.deepEqual(noticePayload('', 'Days'), { value: null, unit: null });
  assert.deepEqual(noticePayload('2', 'Weeks'), { value: 2, unit: 'Weeks' });
  assert.ok(noticePayload('-1', 'Days').error);
  assert.ok(noticePayload('abc', 'Days').error);
  assert.ok(noticePayload('2', 'Years').error);
  assert.ok(noticePayload('100', 'Months').error);
  assert.equal(noticePayload(String(MAX_NOTICE_DAYS), 'Days').error, undefined);
  assert.equal(formatNotice(1, 'Weeks'), '1 Week');
  assert.equal(formatNotice(null, null), 'Not set');
});

run('score explanation adds up to the final score from the scorer breakdown', () => {
  const breakdown = {
    final_score: 62.5, semantic_score: 70, skill_score: 50, baseline_score: 10, experience_penalty: 5, education_penalty: 0,
    weights: { semantic: 0.5, skill: 0.4, baseline: 0.1 }, candidate_experience: 2, required_experience: 5,
    matched_skills: ['Java'], missing_skills: ['Camunda'],
  };
  const rows = explainScore(breakdown);
  assert.deepEqual(rows.map((r) => r.key), ['semantic', 'skill', 'baseline', 'experience']);
  assert.equal(rows.reduce((sum, r) => sum + r.points, 0), 60);
  assert.equal(rows.find((r) => r.key === 'experience').text, '−5.0');
  assert.ok(explainScore(null).length >= 3);
});

run('skill comparison exposes matched and missing JD skills', () => {
  const c = skillComparison(['Java', 'SQL'], { matched_skills: ['Java'], missing_skills: ['Camunda'] });
  assert.deepEqual([c.matched, c.missing, c.hasJdSkills], [['Java'], ['Camunda'], true]);
  assert.equal(skillComparison(['Java'], {}).hasJdSkills, false);
});

run('client name is optional, trimmed, and clearable', () => {
  assert.equal(detailsPayload({ clientName: '  Acme  ', status: 'Open' }).client_name, 'Acme');
  assert.equal(detailsPayload({ clientName: '   ', status: 'Open' }).client_name, null);
  const initial = { clientName: 'Acme', status: 'Open' };
  assert.deepEqual(changedDetails(initial, { ...initial, clientName: '' }), { client_name: null });
});

run('demands sort Open -> Mapped -> Fulfilled -> Cancelled, newest first within a status', () => {
  const d = (id, status, created_at) => ({ id, status, created_at });
  const sorted = sortByStatus([
    d('x', 'Cancelled', '2026-03-01'), d('a', 'Fulfilled', '2026-03-02'), d('b', 'Open', '2026-01-01'),
    d('c', 'Open', '2026-02-01'), d('e', undefined, '2026-01-15'), d('f', 'Mapped', '2026-01-01'),
  ]);
  assert.deepEqual(sorted.map((j) => j.id), ['c', 'e', 'b', 'f', 'a', 'x']);
});

run('folder search matches partial ID or title, ignoring case and punctuation', () => {
  const jds = [{ display_id: 'TRU-JD-0012', title: 'Senior Java Developer' }, { display_id: 'TRU-JD-0013', title: 'Pega Lead' }];
  assert.equal(filterDemands(jds, '').length, 2);
  assert.deepEqual(filterDemands(jds, 'java').map((j) => j.display_id), ['TRU-JD-0012']);
  assert.deepEqual(filterDemands(jds, '0013').map((j) => j.display_id), ['TRU-JD-0013']);
  assert.deepEqual(filterDemands(jds, 'jd 0012').map((j) => j.display_id), ['TRU-JD-0012']);
  assert.equal(filterDemands(jds, 'zzz').length, 0);
});

run('client summary handles none, one, several and partly missing', () => {
  assert.equal(clientSummary([], 3), 'No client');
  assert.equal(clientSummary(['Acme']), 'Acme');
  assert.equal(clientSummary(['Acme', 'Globex', 'Initech', 'Umbrella']), 'Acme, Globex +2 more');
  assert.equal(clientSummary(['Acme'], 2), 'Acme (+2 unassigned)');
});
