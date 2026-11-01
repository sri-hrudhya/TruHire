import { STORAGE_KEYS } from '../config/env.js';

// Splits buffered Server-Sent-Events text into complete {event, data} messages plus the unfinished tail.
export function parseSse(buffer) {
  const blocks = buffer.split('\n\n');
  const rest = blocks.pop();
  const events = [];
  for (const block of blocks) {
    let event = 'message';
    let data = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data += line.slice(5).trim();
    }
    if (data) events.push({ event, data: JSON.parse(data) });
  }
  return { events, rest };
}

// POST /assistant/message/stream. Calls onToken(text) for every piece as it arrives and resolves with the
// final payload (same shape as /assistant/message). Axios cannot read a response while it is still
// arriving, so this uses fetch.
export async function streamAssistantMessage(body, onToken, signal) {
  const token = localStorage.getItem(STORAGE_KEYS.token);
  const response = await fetch('/api/assistant/message/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const detail = await response.json().then((j) => j?.detail).catch(() => null);
    const error = new Error(typeof detail === 'string' ? detail : 'I could not complete that request.');
    error.response = { status: response.status, data: { detail } };
    throw error;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let done = null;
  for (;;) {
    const { value, done: finished } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !finished });
    const parsed = parseSse(finished ? `${buffer}\n\n` : buffer);
    buffer = parsed.rest;
    for (const { event, data } of parsed.events) {
      if (event === 'token') onToken(data.text);
      else if (event === 'done') done = data;
    }
    if (finished) break;
  }
  if (!done) throw new Error('The answer was interrupted.');
  return done;
}
