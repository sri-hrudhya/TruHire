// Pure helpers for the fixed Demand categories (Java, GenAI, Camunda, Pega, Others) used by Search and Requirements.

// A category id from the URL or storage is only trusted while it still exists; otherwise fall back to "All" (null).
export const resolveActiveCategory = (demands, requestedId) =>
  (requestedId && (demands || []).some((d) => d.id === requestedId) ? requestedId : null);

// Roving selection for the category tab row. `ids` is the visible order (null = All); returns the id to select.
export function nextCategoryId(ids, current, key) {
  const at = Math.max(0, ids.indexOf(current));
  if (key === 'ArrowRight' || key === 'ArrowDown') return ids[(at + 1) % ids.length];
  if (key === 'ArrowLeft' || key === 'ArrowUp') return ids[(at - 1 + ids.length) % ids.length];
  if (key === 'Home') return ids[0];
  if (key === 'End') return ids[ids.length - 1];
  return current;
}

// JDs shown in the JD selector: only those assigned to the chosen category (all when none is chosen).
export const jdsInCategory = (jds, categoryId) => (categoryId ? jds.filter((j) => j.demand_id === categoryId) : jds);

// The JD selection that survives a category change: '' when the selected JD is not in the new category.
export const jdAfterCategoryChange = (jds, categoryId, selectedJdId) => {
  if (!selectedJdId) return '';
  const jd = jds.find((j) => j.id === selectedJdId);
  return jd && (!categoryId || jd.demand_id === categoryId) ? selectedJdId : '';
};

// What Search should do, and what to send. Exactly one of three modes runs:
//   jd               a requirement is chosen: rank against it (the category only narrowed the choice)
//   category-keyword a category plus keywords/skill chips, no requirement: search scoped to that category
//   keyword          no category, no requirement: plain keyword / filter search
// A category alone (no requirement, keywords or skills) is never a search: the user is told what to add.
export function searchDecision({ categoryId, jdId, query, hasSkills = false, hasOtherFilters = false }) {
  const hasQuery = !!(query || '').trim();
  const none = { positionId: null, demandId: null };
  if (jdId) return { action: 'run', mode: 'jd', ...none, positionId: jdId };
  if (categoryId) {
    if (!hasQuery && !hasSkills) return { action: 'need-jd-or-query', mode: null, ...none };
    return { action: 'run', mode: 'category-keyword', ...none, demandId: categoryId };
  }
  if (!hasQuery && !hasSkills && !hasOtherFilters) return { action: 'idle', mode: null, ...none };
  return { action: 'run', mode: 'keyword', ...none };
}

// Location / role read from a JD are suggestions, never applied automatically: as hard filters they
// exclude every candidate whose stated titles/location don't repeat them (a JD for "Generative AI
// Solutions Architect" matches nobody holding that exact title), so picking a JD would return zero.
// The recruiter opts in by applying a suggestion.
export function prefillFromJdFilters(info) {
  const data = info || {};
  return { location: '', role: '', suggestedLocation: data.location || '', suggestedRole: data.role || '' };
}

// Message for a search that returned nobody: the backend's specific reason when it gave one.
export function emptyResultMessage(results) {
  return results?.empty_reason?.message || 'No candidates found matching your active filters. Try removing keywords or reducing minimum experience.';
}

// What the results area shows for a backend search response.
export function resultsViewState(results, loading = false) {
  if (loading) return 'loading';
  if (!results) return 'idle';
  return Array.isArray(results.results) && results.results.length > 0 ? 'results' : 'empty';
}

// Result-size choices: presets plus the server's default and maximum, never above the maximum.
export function topNOptions({ default_top_n: def, max_top_n: max }, presets) {
  return [...new Set([...presets, def, max])].filter((n) => n <= max).sort((a, b) => a - b);
}
