import { useCallback, useEffect, useState } from 'react';
import { candidatesApi, demandApi, exportApi, jdApi, searchApi } from '../lib/api';
import { jdAfterCategoryChange, prefillFromJdFilters, resolveActiveCategory, searchDecision } from '../lib/categories';
import { STORAGE_KEYS } from '../config/env';
import { COPY } from '../config/copy';
import { useMeta } from '../context/MetaContext';

const readStored = (key) => { try { return localStorage.getItem(key); } catch { return null; } };
const writeStored = (key, value) => {
  try { if (value) localStorage.setItem(key, value); else localStorage.removeItem(key); } catch { /* storage unavailable: the category is simply not remembered */ }
};

// All state and actions of the Search page. Three modes: a requirement, a category plus keywords, keywords only.
export default function useSearch() {
  const { search: searchLimits } = useMeta();
  const [query, setQuery] = useState('');
  const [chips, setChips] = useState([]);
  const [minExp, setMinExp] = useState('');
  const [jdId, setJdId] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [locations, setLocations] = useState([]);
  const [role, setRole] = useState('');
  const [jdFilterInfo, setJdFilterInfo] = useState(null);
  const [positions, setPositions] = useState('');    // narrows the requirement choices to demands with this many positions
  const [topN, setTopN] = useState(null);
  const [jds, setJds] = useState([]);
  const [demands, setDemands] = useState([]);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState(null);
  const [exporting, setExporting] = useState(null);
  const effectiveTopN = topN ?? searchLimits.default_top_n;

  const rememberCategory = (id) => { setCategoryId(id); writeStored(STORAGE_KEYS.searchCategory, id); };

  // The page always opens on an empty form; only the lists and the remembered category are loaded.
  useEffect(() => {
    (async () => {
      try {
        const [jdRes, demandRes] = await Promise.all([jdApi.list(), demandApi.list().catch(() => ({ data: [] }))]);
        const cats = demandRes.data || [];
        setJds(jdRes.data);
        setDemands(cats);
        const stored = resolveActiveCategory(cats, readStored(STORAGE_KEYS.searchCategory));
        setCategoryId(stored || '');
        if (!stored) writeStored(STORAGE_KEYS.searchCategory, '');
      } catch (err) {
        console.error('Failed to load the search lists:', err);
      }
    })();
  }, []);

  // `over` lets a handler search with values it has just set, before React re-renders.
  const run = useCallback(async (over = {}) => {
    const skills = over.chips ?? chips;
    const jd = over.jdId ?? jdId;
    const category = over.categoryId ?? categoryId;
    const locs = over.locations ?? locations;
    const rol = (over.role ?? role).trim();
    const decision = searchDecision({ categoryId: category, jdId: jd, query, hasSkills: skills.length > 0, hasOtherFilters: locs.length > 0 || !!rol });
    setNotice(null);
    if (decision.action !== 'run') {
      setResults(null);
      setNotice(COPY.nothingToSearch);
      return;
    }
    setLoading(true);
    try {
      const res = await searchApi.search({
        query: query.trim(),
        filter_skills: skills,
        min_experience: minExp ? parseFloat(minExp) : null,
        position_id: decision.positionId,
        demand_id: decision.demandId,
        locations: locs,
        role: rol || null,
        top_n: parseInt(effectiveTopN, 10),
      });
      setResults(res.data);
      if (res.data.active_filter_chips) setChips(res.data.active_filter_chips);
      if (res.data.modifier_mode && res.data.modifier_mode !== 'neutral') {
        setNotice(res.data.modifier_mode === 'replace' ? 'Applied "replace": the active filters were updated.' : 'Applied "append": added to the active filters.');
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setResults(null);
      setNotice(typeof detail === 'string' ? detail
        : err?.code === 'ECONNABORTED' ? 'The search is taking longer than expected. Scoring is still slow on this machine; try again, or search with fewer results.'
        : 'Search failed. Try again.');
    } finally {
      setLoading(false);
    }
  }, [chips, jdId, categoryId, locations, role, query, minExp, effectiveTopN]);

  const selectJd = async (id) => {
    setJdId(id);
    setJdFilterInfo(null);
    setNotice(null);
    if (!id) {
      setLocations([]);
      setRole('');
      return;
    }
    let derived = null;
    try { derived = (await jdApi.getSearchFilters(id)).data || null; setJdFilterInfo(derived); } catch (err) { console.error('Could not read location/role from the requirement:', err); }
    // Location / role read from a JD are only suggestions: applied as hard filters they would exclude most candidates.
    const prefill = prefillFromJdFilters(derived);
    setLocations(prefill.locations);
    setRole(prefill.role);
  };

  const selectCategory = (id) => {
    const nextId = id || '';
    if (jdAfterCategoryChange(jds, nextId, jdId) !== jdId) {
      setJdId('');
      setJdFilterInfo(null);
      setLocations([]);
      setRole('');
      setResults(null);
    }
    rememberCategory(nextId);
    setNotice(null);
  };

  // Edits to the form never search; only the Search button does.
  const removeChip = (chip) => setChips(chips.filter((c) => c !== chip));
  const clearRoleLocation = () => { setRole(''); setLocations([]); };

  const reset = () => {
    rememberCategory('');
    setQuery(''); setPositions(''); setLocations([]); setRole(''); setJdFilterInfo(null); setChips([]); setMinExp(''); setJdId('');
    setResults(null); setNotice(null);
  };

  const setCandidateStatus = async (candidateId, status) => {
    try {
      await candidatesApi.updateStatus(candidateId, status);
      setResults((prev) => prev && ({
        ...prev,
        results: prev.results.map((it) => (it.candidate.id === candidateId ? { ...it, candidate: { ...it.candidate, status } } : it)),
      }));
    } catch (err) {
      setNotice(err?.response?.data?.detail || 'Could not update the candidate status.');
    }
  };

  const exportCandidates = async (format) => {
    setExporting(format);
    try { await exportApi.downloadCandidates(format, jdId || null); } catch { setNotice('Export failed. Check that you are signed in and try again.'); } finally { setExporting(null); }
  };

  return {
    query, setQuery, positions, setPositions, chips, minExp, setMinExp, jdId, categoryId, locations, setLocations, role, setRole, jdFilterInfo,
    topN: effectiveTopN, setTopN, jds, demands, results, loading, notice, exporting,
    run, selectJd, selectCategory, removeChip, clearRoleLocation, reset, setCandidateStatus, exportCandidates,
  };
}
