import assert from 'node:assert/strict';
import { parseSse } from '../src/lib/assistantStream.js';

const run = (name, fn) => { try { fn(); console.log(`PASS ${name}`); } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };

run('complete SSE events are parsed in order and the unfinished tail is kept', () => {
  const { events, rest } = parseSse('event: token\ndata: {"text":"Hel"}\n\nevent: token\ndata: {"text":"lo"}\n\nevent: done\ndata: {"rep');
  assert.deepEqual(events, [{ event: 'token', data: { text: 'Hel' } }, { event: 'token', data: { text: 'lo' } }]);
  assert.equal(rest, 'event: done\ndata: {"rep');
});

run('a tail completed by the next chunk parses on the next call', () => {
  const first = parseSse('event: done\ndata: {"reply":"ok",');
  const second = parseSse(`${first.rest}"action":"reply"}\n\n`);
  assert.deepEqual(second.events, [{ event: 'done', data: { reply: 'ok', action: 'reply' } }]);
});

run('text with newlines and unicode survives the JSON payload', () => {
  const { events } = parseSse(`event: token\ndata: ${JSON.stringify({ text: 'a\nb “c”' })}\n\n`);
  assert.equal(events[0].data.text, 'a\nb “c”');
});
