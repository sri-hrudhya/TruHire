import assert from 'node:assert/strict';
import { changedDetails, detailsPayload, showRole, formatDate, formatExperience, historyChanges, validateDetails } from '../src/lib/requirements.js';
import { MAX_NOTICE_DAYS, freshness, formatNotice, noticePayload } from '../src/lib/ingestion.js';
import { explainScore, skillComparison } from '../src/lib/scoreExplanation.js';
import { FALLBACK_META } from '../src/lib/meta.js';

const run = (name, fn) => { try { fn(); console.log(`PASS ${name}`); } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };
const DAY = 86_400_000;

run('JD statuses are exactly Open, Closed, Cancelled, Fulfilled, Map', () => {
  assert.deepEqual(FALLBACK_META.jd_statuses, ['Open', 'Closed', 'Cancelled', 'Fulfilled', 'Map']);
  assert.equal(FALLBACK_META.default_jd_status, 'Open');
});

run('details validation: experience range and date order', () => {
  assert.equal(validateDetails({ experience: '5', startDate: '2026-01-01', endDate: '2026-01-01' }), null);
  assert.equal(validateDetails({ experience: '', startDate: '', endDate: '' }), null);
  assert.match(validateDetails({ experience: '-1' }), /Experience/);
  assert.match(validateDetails({ experience: '61' }), /Experience/);
  assert.match(validateDetails({ experience: 'abc' }), /Experience/);
  assert.match(validateDetails({ startDate: '2026-02-01', endDate: '2026-01-01' }), /End date/);
});

run('detailsPayload turns blanks into null and trims text', () => {
  assert.deepEqual(detailsPayload({ role: 'ignored', location: '  Pune ', experience: '', startDate: '', endDate: '', status: 'Open' }),
    { location: 'Pune', experience_years: null, start_date: null, end_date: null, status: 'Open' });
  assert.equal(detailsPayload({ experience: '0', status: 'Open' }).experience_years, 0);
});

run('changedDetails sends only edited fields', () => {
  const initial = { location: 'Pune', experience: '3', startDate: '', endDate: '', status: 'Open' };
  assert.deepEqual(changedDetails(initial, initial), {});
  assert.deepEqual(changedDetails(initial, { ...initial, location: '', status: 'Closed' }), { location: null, status: 'Closed' });
});

run('date-only values keep their calendar day; missing values show a dash', () => {
  assert.match(formatDate('2026-11-01'), /1/);
  assert.equal(formatDate(null), '—');
  assert.equal(formatExperience(1), '1 yr');
  assert.equal(formatExperience(5), '5 yrs');
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
