import assert from 'node:assert/strict';
import { isHeading, parseJd } from '../src/lib/jdFormat.js';

const run = (name, fn) => { try { fn(); console.log(`PASS ${name}`); } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };

run('headings, paragraphs, bullets and numbered lists are separated', () => {
  const blocks = parseJd('JOB DESCRIPTION\nWe need a Java developer\nwith Spring.\n\nResponsibilities:\n- Build APIs\n• Review code\n\nSteps\n1. Apply\n2) Interview');
  assert.deepEqual(blocks, [
    { type: 'h', text: 'JOB DESCRIPTION' },
    { type: 'p', text: 'We need a Java developer with Spring.' },
    { type: 'h', text: 'Responsibilities' },
    { type: 'ul', items: ['Build APIs', 'Review code'] },
    { type: 'p', text: 'Steps' },
    { type: 'ol', items: ['Apply', 'Interview'] },
  ]);
});

run('wrapped list items are joined and CRLF is handled', () => {
  assert.deepEqual(parseJd('- First item\r\n  continues here\r\n- Second'), [{ type: 'ul', items: ['First item continues here', 'Second'] }]);
});

run('nothing is invented or dropped; empty input gives no blocks', () => {
  assert.deepEqual(parseJd(''), []);
  assert.deepEqual(parseJd(null), []);
  assert.deepEqual(parseJd('Plain sentence.'), [{ type: 'p', text: 'Plain sentence.' }]);
});

run('sentences and long lines are not headings', () => {
  assert.equal(isHeading('We are hiring.'), false);
  assert.equal(isHeading('AN ALL CAPS SENTENCE THAT ENDS WITH A PERIOD.'), false);
  assert.equal(isHeading('Skills:'), true);
  assert.equal(isHeading('QUALIFICATIONS'), true);
});
