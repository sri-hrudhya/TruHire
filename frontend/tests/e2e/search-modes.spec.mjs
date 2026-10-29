// Browser check of the Requirements category row and the three search modes.
// The API is mocked at the network layer, so this verifies what the UI sends and renders; the backend
// behaviour behind those requests is covered by tests/test_search_category.py.
//
//   VITE_BACKEND_PORT=9 npm run dev        (any port: every /api call is intercepted)
//   E2E_BASE_URL=http://localhost:5173 node tests/e2e/search-modes.spec.mjs
import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
import { chromium } from 'playwright-core';

const BASE = process.env.E2E_BASE_URL || 'http://localhost:5173';
const SHOTS = new URL('./screenshots/', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
mkdirSync(SHOTS, { recursive: true });

const NAMES = ['Java', 'GenAI', 'Camunda', 'Pega', 'Others'];
const demands = NAMES.map((name, i) => ({ id: `d-${name.toLowerCase()}`, name, jd_count: i === 2 ? 2 : 1 }));
const jd = (id, n, demandName) => ({
  id, display_id: `DM-000${n}`, title: `${demandName} Engineer`, jd_text: `${demandName} role text`, jd_summary: null, jd_version: 1,
  demand_id: `d-${demandName.toLowerCase()}`, created_at: '2026-01-01T00:00:00', file_url: null, original_filename: null,
});
const jds = [jd('j-java', 1, 'Java'), jd('j-camunda', 2, 'Camunda'), jd('j-pega', 3, 'Pega')];
const candidate = (id, name, skills) => ({
  candidate: { id, display_id: `TRU-CN-${id}`, candidate_name: name, email: `${id}@example.com`, extracted_skills: skills,
    years_experience: 6, education: 'BSc', status: 'New', uploaded_at: '2026-01-02T00:00:00', location: 'Pune', job_titles: ['Engineer'] },
  match_score: 82.4, score_breakdown: { matched_skills: skills.slice(0, 1), missing_skills: [], semantic_score: 70, skill_score: 80, baseline_score: 20, experience_penalty: 0 },
  llm_summary: `${name} fits.`, cited_quote: null, requirement_status: 'Pending Review', last_email: null,
});
const meta = {
  roles: ['admin', 'recruiter'], requirement_statuses: ['Pending Review', 'Shortlisted', 'Not Shortlisted'], default_requirement_status: 'Pending Review',
  candidate_statuses: ['New', 'Shortlisted', 'Interviewed', 'Rejected'], email_statuses: ['pending', 'sent', 'simulated', 'failed'],
  page_sizes: { history: 25, audit: 25 }, search: { default_top_n: 20, max_top_n: 100 }, comment_max_chars: 2000, accepted_jd_file_types: ['.pdf', '.txt'],
};

const searches = [];
const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

async function mockApi(page) {
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname.replace(/^\/api/, '');
    if (path === '/auth/me') return json(route, { id: 'u1', name: 'Asha', email: 'a@x.com', role: 'recruiter' });
    if (path === '/meta') return json(route, meta);
    if (path === '/demands') return json(route, demands);
    if (path === '/job-descriptions') return json(route, jds);
    if (/^\/job-descriptions\/[^/]+\/matches/.test(path)) return json(route, { matches: [candidate('c1', 'Meera Rao', ['Java', 'Spring'])], min_match_score: 50, retrieval: { lexical: true } });
    if (/\/assignments$/.test(path)) return json(route, []);
    if (/\/search-filters$/.test(path)) return json(route, { location: null, role: null, sources: {} });
    if (path === '/search/state') return json(route, { state: null });
    if (path === '/retention/status') return json(route, { data_retention_days: 30, cleanup_interval_hours: 6 });
    if (/\/comments$/.test(path)) return json(route, []);
    if (path === '/search' && req.method() === 'POST') {
      const body = req.postDataJSON();
      searches.push(body);
      const results = body.demand_id === 'd-camunda' ? [candidate('c2', 'Ravi Menon', ['Camunda', 'BPMN'])] : [candidate('c1', 'Meera Rao', ['Java', 'Spring'])];
      return json(route, { total_matches: results.length, top_n: 20, results, empty_reason: null, warnings: [], filters: null,
        scored_against_jd: body.position_id ? { id: body.position_id, title: 'Java Engineer', version: 1 } : null, retrieval: {}, active_filter_chips: [], modifier_mode: 'neutral' });
    }
    return json(route, {});
  });
}

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
await context.addInitScript(() => {
  localStorage.setItem('truhire_token', 'test-token');
  localStorage.setItem('truhire_user', JSON.stringify({ id: 'u1', name: 'Asha', email: 'a@x.com', role: 'recruiter' }));
});
const page = await context.newPage();
const consoleErrors = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', (e) => consoleErrors.push(String(e)));
await mockApi(page);

const run = async (name, fn) => { try { await fn(); console.log(`PASS ${name}`); } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; } };

await run('requirements: categories are one horizontal row of tabs, not boxes', async () => {
  await page.goto(`${BASE}/requirements`);
  const tabs = page.getByRole('tablist', { name: 'Categories' }).getByRole('tab');
  await tabs.nth(NAMES.length).waitFor(); // All + the five categories, once /api/demands has answered
  assert.equal(await tabs.count(), NAMES.length + 1);
  const tops = await tabs.evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().top)));
  assert.equal(new Set(tops).size, 1, `tabs must share one row, got tops ${tops}`);
  const styles = await tabs.first().evaluate((el) => getComputedStyle(el));
  assert.equal(styles.borderTopWidth, '0px');
  await page.screenshot({ path: `${SHOTS}requirements.png` });
});

await run('requirements: choosing a category filters the list and keeps the URL in sync', async () => {
  await page.getByRole('tab', { name: /Camunda/ }).click();
  assert.match(page.url(), /demand=d-camunda/);
  const items = page.locator('.req-item');
  assert.equal(await items.count(), 1);
  assert.match(await items.first().innerText(), /Camunda Engineer/);
});

await run('requirements: an unknown ?demand= falls back to All', async () => {
  await page.goto(`${BASE}/requirements?demand=does-not-exist`);
  await page.getByRole('tab', { name: /^All/ }).waitFor();
  assert.equal(await page.getByRole('tab', { name: /^All/ }).getAttribute('aria-selected'), 'true');
  assert.equal(await page.locator('.req-item').count(), jds.length);
});

await run('requirements: arrow keys move between categories', async () => {
  await page.getByRole('tab', { name: /^All/ }).focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.getByRole('tab', { name: /Java/ }).getAttribute('aria-selected'), 'true');
});

await page.goto(`${BASE}/search`);
await page.getByRole('tab', { name: /^All/ }).waitFor();
const submit = page.locator('form.search-form button[type=submit]');

await run('search mode 1: JD-specific sends position_id only', async () => {
  searches.length = 0;
  await page.locator('.search-scope select').selectOption('j-java');
  await page.locator('.match-name').first().waitFor();
  const body = searches.at(-1);
  assert.equal(body.position_id, 'j-java');
  assert.equal(body.demand_id, null);
  assert.match(await page.locator('.results-summary').innerText(), /scored against Java Engineer/);
  await page.screenshot({ path: `${SHOTS}search-jd.png` });
});

await run('search mode 2: category + keyword sends demand_id, no position_id', async () => {
  await page.getByRole('button', { name: 'Reset' }).click();
  searches.length = 0;
  await page.getByRole('tab', { name: /Camunda/ }).click();
  await page.getByPlaceholder(/Skills, role/).fill('workflow');
  await submit.click();
  await page.getByRole('link', { name: 'Ravi Menon' }).waitFor();
  const body = searches.at(-1);
  assert.equal(body.demand_id, 'd-camunda');
  assert.equal(body.position_id, null);
  assert.equal(body.query, 'workflow');
  await page.screenshot({ path: `${SHOTS}search-category-keyword.png` });
});

await run('search: a category with nothing to search sends no request and says what to add', async () => {
  await page.getByRole('button', { name: 'Reset' }).click();
  searches.length = 0;
  await page.getByRole('tab', { name: /Java/ }).click();
  await submit.click();
  await page.getByText('Pick a requirement or enter keywords to search.').first().waitFor();
  assert.equal(searches.length, 0);
});

await run('search mode 3: keyword-only sends neither category nor requirement', async () => {
  await page.getByRole('button', { name: 'Reset' }).click();
  searches.length = 0;
  await page.getByPlaceholder(/Skills, role/).fill('python');
  await submit.click();
  await page.getByRole('link', { name: 'Meera Rao' }).waitFor();
  const body = searches.at(-1);
  assert.equal(body.demand_id, null);
  assert.equal(body.position_id, null);
  assert.equal(body.query, 'python');
  await page.screenshot({ path: `${SHOTS}search-keyword.png` });
});

await run('responsive: category row scrolls inside a 360px viewport without page overflow', async () => {
  await page.setViewportSize({ width: 360, height: 780 });
  await page.goto(`${BASE}/requirements`);
  await page.getByRole('tab', { name: /^All/ }).waitFor();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert.ok(overflow <= 1, `page overflows horizontally by ${overflow}px`);
  await page.screenshot({ path: `${SHOTS}requirements-mobile.png` });
});

await run('no console errors', async () => {
  const real = consoleErrors.filter((t) => !/favicon|Failed to load resource/.test(t));
  assert.deepEqual(real, []);
});

await browser.close();
