import assert from 'node:assert/strict';
import { formatIst, timeAgo } from '../src/lib/ingestion.js';

const now = Date.parse('2026-11-04T12:00:00Z');
const ago = (ms) => new Date(now - ms).toISOString();
const S = 1000, M = 60 * S, H = 60 * M, D = 24 * H;

assert.equal(timeAgo(ago(59 * S), now), 'just now');
assert.equal(timeAgo(ago(1 * M), now), '1 minute ago');
assert.equal(timeAgo(ago(59 * M), now), '59 minutes ago');
assert.equal(timeAgo(ago(1 * H), now), '1 hour ago');
assert.equal(timeAgo(ago(23 * H), now), '23 hours ago');
assert.equal(timeAgo(ago(1 * D), now), '1 day ago');
assert.equal(timeAgo(ago(29 * D), now), '29 days ago');
assert.equal(timeAgo(ago(30 * D), now), '1 month ago');
assert.equal(timeAgo(ago(75 * D), now), '2 months ago');
assert.equal(timeAgo(ago(400 * D), now), '1 year ago');
assert.equal(timeAgo(new Date(now + 5 * M).toISOString(), now), 'just now'); // clock skew: future date
// Naive-UTC stamps (no Z) are read as UTC, like the rest of the ingestion helpers.
assert.equal(timeAgo('2026-11-04T10:00:00', now), '2 hours ago');
assert.equal(timeAgo(null, now), '');
assert.equal(timeAgo('garbage', now), '');

// Upload times are always shown in Indian Standard Time (UTC+5:30), whatever the browser's timezone.
assert.equal(formatIst('2026-10-12T12:31:23Z'), '12 Oct 2026, 6:01 PM IST');
assert.equal(formatIst('2026-10-12T12:31:23'), '12 Oct 2026, 6:01 PM IST'); // naive-UTC stamp from the API
assert.equal(formatIst('2026-11-02T18:45:00Z'), '3 Nov 2026, 12:15 AM IST'); // crosses midnight into the next IST day
assert.equal(formatIst(null), '—');
assert.equal(formatIst('garbage'), '—');

console.log('ingestion tests passed');
