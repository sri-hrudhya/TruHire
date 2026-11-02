import assert from 'node:assert/strict';
import { errorText } from '../src/lib/errors.js';

const run = (name, fn) => { try { fn(); console.log(`PASS ${name}`); } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };
const http = (detail) => ({ response: { data: { detail } }, message: 'Request failed with status code 422' });

run('a string detail from the API is shown as is', () => assert.equal(errorText(http('Candidate has no email address.'), 'x'), 'Candidate has no email address.'));
run('validation errors are joined from their messages', () => assert.equal(errorText(http([{ msg: 'Field required' }, { msg: 'Too short' }]), 'x'), 'Field required Too short'));
run('an empty or unknown detail uses the fallback, not the axios status text', () => {
  assert.equal(errorText(http(''), 'Could not save.'), 'Could not save.');
  assert.equal(errorText(http([{}]), 'Could not save.'), 'Could not save.');
  assert.equal(errorText(http({ other: 1 }), 'Could not save.'), 'Could not save.');
});
run('no response (offline, timeout) shows the transport message', () => assert.equal(errorText({ message: 'timeout of 30000ms exceeded' }, 'x'), 'timeout of 30000ms exceeded'));
run('nothing at all uses the fallback', () => assert.equal(errorText(undefined, 'Failed.'), 'Failed.'));
