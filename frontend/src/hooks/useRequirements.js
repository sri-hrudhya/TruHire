import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { demandApi, jdApi, retentionApi, reviewApi, usersApi } from '../lib/api';
import { resolveActiveCategory } from '../lib/categories';
import { sortByStatus } from '../lib/requirements';
import { assignmentsByCandidate, isAdmin } from '../lib/review';
import { TIMEOUTS_MS } from '../config/env';
import { useAuth } from '../context/AuthContext';

// FastAPI sends a string for its own errors and a list of { msg } objects for request validation errors.
const errorText = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((d) => d?.msg).filter(Boolean).join(' ') || fallback;
  return (typeof detail === 'string' && detail) || fallback;
};

// All data and actions of the Requirements page: the list, the selected requirement, its ranked matches,
// and the review workflow (status, assignment). The page itself only composes components.
export default function useRequirements() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [jds, setJds] = useState([]);
  const [demands, setDemands] = useState([]);
  const [selectedJd, setSelectedJd] = useState(null);
  const [creating, setCreating] = useState(false);
  const [template, setTemplate] = useState(null);  // the demand a new one is being copied from
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState(null);

  const [matches, setMatches] = useState([]);
  const [loadingMatches, setLoadingMatches] = useState(false);
  const [minMatchScore, setMinMatchScore] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [statusError, setStatusError] = useState(null);

  const [assignments, setAssignments] = useState({});
  const [users, setUsers] = useState([]);
  const [retention, setRetention] = useState(null);

  const demandId = resolveActiveCategory(demands, searchParams.get('demand'));

  const loadDemands = useCallback(async () => {
    try { setDemands((await demandApi.list()).data); } catch (err) { console.error('Failed to load categories:', err); }
  }, []);

  const loadAssignments = useCallback(async (jdId) => {
    try { setAssignments(assignmentsByCandidate((await reviewApi.listAssignments(jdId)).data)); } catch { setAssignments({}); }
  }, []);

  const loadMatches = useCallback(async (jdId) => {
    setLoadingMatches(true);
    try {
      const res = await jdApi.getMatches(jdId, undefined);
      setMatches(res.data?.matches || []);
      if (typeof res.data?.min_match_score === 'number') setMinMatchScore(res.data.min_match_score);
      setCoverage({ unindexed: res.data?.unindexed_candidates || 0, lexicalDown: res.data?.retrieval ? !res.data.retrieval.lexical : false });
    } catch (err) {
      console.error('Failed to load matches for requirement:', err);
      setMatches([]);
      setCoverage(null);
    } finally {
      setLoadingMatches(false);
    }
    loadAssignments(jdId);
  }, [loadAssignments]);

  const selectJd = useCallback((jd) => {
    setSelectedJd(jd);
    setCreating(false);
    setStatusError(null);
    setNotice(null);
    loadMatches(jd.id);
    const next = new URLSearchParams(searchParams);
    next.set('id', jd.id);
    next.delete('view');
    if (jd.demand_id) next.set('demand', jd.demand_id);
    setSearchParams(next, { replace: true });
  }, [loadMatches, searchParams, setSearchParams]);

  // Back from a JD (or the editor) to its demand's cards.
  const closeJd = () => {
    setSelectedJd(null);
    setCreating(false);
    setMatches([]);
    setNotice(null);
    const next = new URLSearchParams(searchParams);
    next.delete('id');
    setSearchParams(next, { replace: true });
  };

  const showHistory = (on) => {
    const next = new URLSearchParams(searchParams);
    if (on) { next.set('view', 'history'); next.delete('id'); } else next.delete('view');
    if (on) { setSelectedJd(null); setCreating(false); }
    setSearchParams(next, { replace: true });
  };

  // With a demand passed in, the form opens as a copy of it; nothing is saved until the user saves.
  const startCreate = (source = null) => {
    setCreating(true);
    setTemplate(source);
    setSelectedJd(null);
    setMatches([]);
    setNotice(source ? { type: 'info', message: `Copying ${source.display_id || 'the demand'} “${source.title}”. Change what differs, then save to create a new demand.` } : null);
    const next = new URLSearchParams(searchParams);
    next.delete('id');
    next.delete('view');
    setSearchParams(next, { replace: true });
  };

  // Opening a demand lists its JDs; leaving it (null) goes back to the five demand cards.
  const setDemand = (id) => {
    const next = new URLSearchParams(searchParams);
    if (id) next.set('demand', id); else next.delete('demand');
    next.delete('id');
    next.delete('view');
    setSelectedJd(null);
    setCreating(false);
    setMatches([]);
    setSearchParams(next, { replace: true });
  };

  const loadJDs = useCallback(async () => {
    try {
      const res = await jdApi.list();
      setJds(res.data);
      return res.data;
    } catch (err) {
      console.error('Failed to load requirements:', err);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  // First load: restore the requirement named in the URL, else the first one.
  useEffect(() => {
    (async () => {
      const list = await loadJDs();
      loadDemands();
      retentionApi.getStatus().then((r) => setRetention(r.data)).catch(() => {});
      const wanted = list.find((jd) => jd.id === searchParams.get('id'));
      if (wanted) selectJd(wanted);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!isAdmin(user)) return;
    usersApi.list().then((r) => setUsers(r.data)).catch(() => setUsers([]));
  }, [user]);

  // Open first, then Closed, then Cancelled; recomputed whenever a status changes.
  const visibleJds = useMemo(() => sortByStatus(demandId ? jds.filter((j) => j.demand_id === demandId) : jds), [jds, demandId]);
  const historyOpen = searchParams.get('view') === 'history';

  const changeStatus = async (candidateId, status) => {
    const previous = matches;
    setStatusError(null);
    setMatches((ms) => ms.map((m) => (m.candidate.id === candidateId ? { ...m, requirement_status: status } : m)));
    try {
      await jdApi.setCandidateStatus(selectedJd.id, candidateId, status);
    } catch (err) {
      setMatches(previous);
      setStatusError(errorText(err, 'Could not update the candidate status.'));
    }
  };

  const assign = async (candidateId, assigneeId) => {
    setStatusError(null);
    try {
      if (assigneeId) {
        const res = await reviewApi.assign(selectedJd.id, candidateId, assigneeId);
        setAssignments((a) => ({ ...a, [candidateId]: res.data }));
      } else {
        await reviewApi.unassign(selectedJd.id, candidateId);
        setAssignments((a) => { const { [candidateId]: _removed, ...rest } = a; return rest; });
      }
    } catch (err) {
      setStatusError(errorText(err, 'Could not change the assignment.'));
    }
  };

  const saveJd = async ({ title, text, fileUrl, originalFilename, details }) => {
    const payload = { title: title.trim(), jd_text: text.trim(), file_url: fileUrl, original_filename: originalFilename, ...details };
    const filedUnder = (jd) => {
      const name = demands.find((d) => d.id === jd.demand_id)?.name;
      return `${name ? ` Filed under ${name}.` : ''}${jd.classification_note ? ` ${jd.classification_note}` : ''}`;
    };
    try {
      if (creating) {
        const created = (await jdApi.create(payload)).data;
        await loadJDs();
        loadDemands();
        selectJd(created);
        setNotice({ type: 'success', message: `Demand created.${filedUnder(created)}` });
      } else {
        const res = await jdApi.update(selectedJd.id, payload);
        loadDemands();
        const bumped = res.data.jd_version > selectedJd.jd_version;
        setSelectedJd(res.data);
        await loadJDs();
        if (res.data.demand_id && res.data.demand_id !== demandId) {  // an edit can re-file the demand under another folder
          const next = new URLSearchParams(searchParams);
          next.set('demand', res.data.demand_id);
          setSearchParams(next, { replace: true });
        }
        loadMatches(res.data.id);
        setNotice({ type: 'success', message: `${bumped ? `Saved as version ${res.data.jd_version}.` : 'Demand updated.'}${filedUnder(res.data)}` });
      }
      return true;
    } catch (err) {
      setNotice({ type: 'error', message: errorText(err, 'Failed to save the demand.') });
      return false;
    }
  };

  // extras carry what the status needs (cancellation reason / resume ids). Returns null on success, else the error text,
  // so the popup that collected the extras can stay open and show it.
  const changeJdStatus = async (status, extras = {}) => {
    setNotice(null);
    try {
      const res = await jdApi.setStatus(selectedJd.id, status, extras);
      setSelectedJd(res.data);
      await loadJDs();
      setNotice({ type: 'success', message: `Demand status is now ${res.data.status}.` });
      return null;
    } catch (err) {
      const message = errorText(err, 'Could not change the demand status.');
      setNotice({ type: 'error', message });
      return message;
    }
  };

  // The end date is tentative: set, change or clear it (null) without touching anything else.
  const changeEndDate = async (endDate) => {
    if (endDate && selectedJd.start_date && endDate < selectedJd.start_date) {
      setNotice({ type: 'error', message: 'End date cannot be before the start date.' });
      return false;
    }
    try {
      const res = await jdApi.update(selectedJd.id, { end_date: endDate });
      setSelectedJd(res.data);
      await loadJDs();
      setNotice({ type: 'success', message: endDate ? 'End date updated.' : 'End date cleared.' });
      return true;
    } catch (err) {
      setNotice({ type: 'error', message: errorText(err, 'Could not change the end date.') });
      return false;
    }
  };

  const summarize = async () => {
    try {
      const res = await jdApi.summarize(selectedJd.id);
      setSelectedJd((prev) => ({ ...prev, jd_summary: res.data.jd_summary }));
      setNotice({ type: 'success', message: 'Summary generated.' });
      await loadJDs();
    } catch {
      setNotice({ type: 'error', message: 'Failed to summarize the demand.' });
    }
  };

  const removeJd = async (jd) => {
    try {
      await jdApi.delete(jd.id);
      const rest = jds.filter((item) => item.id !== jd.id);
      setJds(rest);
      loadDemands();
      setNotice({ type: 'success', message: `Removed ${jd.display_id || ''} "${jd.title}". Candidates and resumes were not deleted.` });
      if (selectedJd?.id === jd.id) closeJd();
      return true;
    } catch (err) {
      setNotice({ type: 'error', message: errorText(err, 'Failed to remove the demand.') });
      return false;
    }
  };

  const runRetentionCleanup = async () => {
    try {
      const res = await retentionApi.cleanup();
      setRetention((await retentionApi.getStatus()).data);
      await loadJDs();
      setNotice({ type: 'success', message: `Retention cleanup removed ${res.data.total_candidates_deleted} resume(s) and ${res.data.total_jds_deleted} requirement(s).` });
    } catch (err) {
      setNotice({ type: 'error', message: `Retention cleanup failed: ${errorText(err, 'unknown error')}` });
    }
  };

  const openJdFile = async (jdId) => {
    // Opened synchronously inside the click so popup blockers allow it, then pointed at the blob.
    const tab = window.open('', '_blank');
    try {
      const res = await jdApi.getFile(jdId);
      const url = URL.createObjectURL(res.data);
      if (tab) tab.location.href = url;
      setTimeout(() => URL.revokeObjectURL(url), TIMEOUTS_MS.objectUrlRevoke);
    } catch {
      if (tab) tab.close();
      setStatusError('Could not open the demand file.');
    }
  };

  return {
    user, jds, visibleJds, demands, demandId, setDemand, selectedJd, creating, template, loading, notice, setNotice,
    matches, loadingMatches, minMatchScore, coverage, statusError, assignments, users, retention,
    historyOpen, showHistory, closeJd, changeJdStatus, changeEndDate,
    selectJd, startCreate, loadMatches, changeStatus, assign, saveJd, summarize, removeJd, runRetentionCleanup, openJdFile,
    setSelectedJd, setCreating,
  };
}
