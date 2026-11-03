import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const run = (name, fn) => { try { fn(); console.log(`PASS ${name}`); } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };
const assistant = readFileSync(new URL('../src/components/TruHireAssistant.jsx', import.meta.url), 'utf8');
const card = readFileSync(new URL('../src/components/assistant/DemandSessionCard.jsx', import.meta.url), 'utf8');
const css = readFileSync(new URL('../src/components/truhire-assistant.css', import.meta.url), 'utf8');

run('assistant opens with the plain welcome message and no sample prompts', () => {
  assert.match(assistant, /Hello! I’m your TruHire Assistant\. I can help you create demands, find candidates and manage recruitment workflows\. What would you like to do\?/);
  for (const gone of ['SUGGESTIONS', 'difference between a practice and a demand', 'How many demands are there per practice', 'Show demands by client', 'Find top candidates for a requirement', 'suggestion']) {
    assert.ok(!assistant.includes(gone), `${gone} should be gone from the assistant`);
  }
  assert.ok(!/suggestion/i.test(css));
});

run('demand fields come from the server, not a list in the component', () => {
  for (const hardcoded of ["'Demand Practice'", "'Java', 'GenAI'", 'JD_QUESTION_DEFS', 'CLIENT_NAMES']) {
    assert.ok(!assistant.includes(hardcoded) && !card.includes(hardcoded), `${hardcoded} should not be hardcoded`);
  }
  assert.match(card, /session\.fields/);
  assert.match(card, /field\.options/);
});

run('progress is read from the session, and creation is confirmed by the server', () => {
  assert.match(card, /session\.progress\.step/);
  assert.match(card, /onAct\('confirm'\)/);
  assert.ok(!/created successfully/i.test(assistant) && !/created successfully/i.test(card));
});
