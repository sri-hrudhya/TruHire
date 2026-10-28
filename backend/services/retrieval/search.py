import hashlib
import json
import logging
import re
import time
from typing import Dict, Any, List, Optional, Tuple, Union
from sqlalchemy.orm import Session
from backend.config import settings
from backend.models import Candidate, Demand, Position, CandidateMatch
from backend.services.classification import matches_category
from backend.services.llm import decision
from backend.services.llm.ai_service import generate_embedding, generate_match_summary, heuristic_match_summary
from backend.services.common.ai_audit import ai_feature
from backend.services.common.cache import get_cache, set_cache, clear_cache, get_index_epoch
from backend.services.llm.guardrails import check_search_result
from backend.services.ingestion.pii import redact_pii
from backend.services.retrieval.qdrant import search_vectors
from backend.services.retrieval.opensearch import search_lexical, get_opensearch_client
from backend.services.retrieval.scoring import calculate_hybrid_score, extract_skills_from_jd, candidate_has_skills
from backend.services.retrieval import reranker
from backend.services.retrieval.filters import SearchFilters, NO_FILTERS, build_filters, candidate_matches, apply_sql_prefilter
from backend.services.ingestion.chunking import chunk_text
from backend.services.ingestion.parsing import COMMON_SKILLS, YEARS_EXP_PATTERN

logger = logging.getLogger(__name__)

MODIFIERS_APPEND = ["and", "also", "too", "plus", "with"]
MODIFIERS_REPLACE = ["only", "just", "instead", "solely"]

# Common query language that happens to be capitalized (sentence-initial or emphasis) -
# excluded so the free-form skill-chip fallback below doesn't mistake it for a skill.
QUERY_STOPWORDS = {
    "looking", "need", "want", "show", "find", "search", "with", "and", "also",
    "only", "just", "instead", "solely", "for", "experience", "years", "yrs",
    "senior", "junior", "developer", "engineer", "candidate", "candidates", "role",
}
FREE_FORM_SKILL_PATTERN = re.compile(r'"([^"]{2,40})"|\b([A-Z][A-Za-z0-9+.#]{2,})\b')


def _free_form_skill_chips(query_text: str, existing_skills: List[str]) -> List[str]:
    """
    Zero-latency, no-LLM fallback for skill mentions outside COMMON_SKILLS' fixed
    dictionary (e.g. "Camunda", "BPMN", "SAP") - quoted phrases, ALL-CAPS acronyms, and
    Title-Case words not already matched and not ordinary query language. Deliberately
    regex-only: this runs on the live interactive search request path.
    """
    already = {s.lower() for s in existing_skills}
    words = query_text.split()
    first_word = words[0].strip(",.") if words else ""
    found: List[str] = []
    for quoted, bare in FREE_FORM_SKILL_PATTERN.findall(query_text):
        token = (quoted or bare).strip()
        if not token or token.lower() in already or token.lower() in QUERY_STOPWORDS:
            continue
        if not quoted and token == first_word:
            continue
        already.add(token.lower())
        found.append(token)
    return found


def parse_search_query(query_text: str, existing_skills: Optional[List[str]] = None) -> Tuple[List[str], Optional[float], str, str]:
    existing = list(existing_skills or [])
    text_lower = query_text.lower().strip()
    modifier_mode = "neutral"
    for word in MODIFIERS_REPLACE:
        if re.search(r"\b" + re.escape(word) + r"\b", text_lower):
            modifier_mode = "replace"; break
    if modifier_mode == "neutral":
        for word in MODIFIERS_APPEND:
            if re.search(r"\b" + re.escape(word) + r"\b", text_lower):
                modifier_mode = "append"; break
    found_skills = [skill for skill in COMMON_SKILLS if re.search(r"\b" + re.escape(skill.lower()) + r"\b", text_lower)]
    found_skills += _free_form_skill_chips(query_text, existing_skills=found_skills)
    min_exp = None
    matches = YEARS_EXP_PATTERN.findall(query_text)
    if matches:
        try: min_exp = float(matches[0])
        except ValueError: pass
    if modifier_mode == "replace":
        updated = found_skills or existing
    else:
        updated = list(dict.fromkeys(existing + found_skills))
    # Remove explicit filter terms from the lexical query so BM25 sees the user's intent.
    clean = re.sub(r"\b(?:only|just|instead|solely|and|also|too|plus|with)\b", " ", query_text, flags=re.I)
    return updated, min_exp, re.sub(r"\s+", " ", clean).strip(), modifier_mode


def _rrf(results: List[Tuple[str, List[Dict[str, Any]]]], top_n: int) -> Dict[str, Dict[str, float]]:
    fused: Dict[str, Dict[str, float]] = {}
    weights = {"vector": settings.HYBRID_VECTOR_WEIGHT, "lexical": settings.HYBRID_LEXICAL_WEIGHT}
    for source, rows in results:
        for rank, row in enumerate(rows, start=1):
            cid = str(row["candidate_id"])
            fused.setdefault(cid, {"rrf": 0.0, "vector_score": 0.0, "lexical_score": 0.0})
            fused[cid]["rrf"] += weights.get(source, 1.0) / (settings.HYBRID_RRF_K + rank)
            fused[cid][f"{source}_score"] = float(row.get("score", 0.0))
            if row.get("chunk_index") is not None:
                fused[cid]["chunk_index"] = int(row["chunk_index"])
    return dict(sorted(fused.items(), key=lambda kv: kv[1]["rrf"], reverse=True)[:top_n])

def _normalize_lexical_scores(fused: Dict[str, Dict[str, float]]) -> None:
    scores = [v["lexical_score"] for v in fused.values() if v.get("lexical_score", 0) > 0]
    max_score = max(scores) if scores else 0.0
    for row in fused.values():
        raw = row.get("lexical_score", 0.0)
        row["lexical_norm"] = (raw / max_score) if max_score > 0 else 0.0

def _semantic_score(fused_row: Dict[str, float]) -> float:
    # Qdrant returns the actual cosine similarity. Do not derive a fake
    # similarity from RRF rank; RRF is retrieval fusion, not semantic similarity.
    # BGE cosine for related text clusters in ~0.4-0.85, so rescale that band to 0-1;
    # otherwise unrelated resumes already score ~50% "semantic".
    score = float(fused_row.get("vector_score", 0.0))
    floor, ceil = settings.SEMANTIC_COSINE_FLOOR, settings.SEMANTIC_COSINE_CEIL
    return max(0.0, min(1.0, (score - floor) / max(ceil - floor, 1e-6)))


def _candidate_payload(c: Candidate) -> Dict[str, Any]:
    return {
        "id": c.id, "display_id": c.display_id, "candidate_name": c.candidate_name, "email": c.email, "phone": c.phone,
        "extracted_skills": c.extracted_skills or [], "years_experience": c.years_experience,
        "education": c.education, "status": c.status, "original_filename": c.original_filename,
        "uploaded_at": c.uploaded_at.isoformat() if c.uploaded_at else None,
        "resume_file_url": c.resume_file_url,
        "location": c.location, "job_titles": c.job_titles or [],
    }


def _search_cache_key(query_text: str, filter_skills: Optional[List[str]], min_experience: Optional[float], position_id: Optional[str], top_n: int, filters: SearchFilters = NO_FILTERS, demand_id: Optional[str] = None) -> str:
    payload = json.dumps({
        "q": query_text.strip(), "skills": sorted(s.strip().lower() for s in (filter_skills or []) if s.strip()),
        "min_exp": min_experience, "position_id": position_id, "demand_id": demand_id, "top_n": top_n,
        # Normalized, so "Bangalore" and "Bengaluru" share an entry while any real change gets its own.
        "filters": filters.cache_part(),
        # Any index write changes the epoch, so cached results never outlive the index state.
        "epoch": get_index_epoch(),
        "rerank": settings.RERANKER_ENABLED and settings.RERANKER_MODEL,
    }, sort_keys=True)
    return "search:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rerank_passage(cand: Candidate, chunk_index: Optional[int]) -> str:
    """The resume chunk that best matched the query (re-derived deterministically from the
    stored text, so no chunk text has to live in the vector DB), prefixed with skills."""
    chunks = chunk_text(redact_pii(cand.resume_text or "", candidate_name=cand.candidate_name))
    body = chunks[chunk_index] if chunk_index is not None and 0 <= chunk_index < len(chunks) else (chunks[0] if chunks else "")
    return f"Skills: {', '.join(cand.extracted_skills or [])}. {body}"[:2500]


class RequirementNotFound(ValueError):
    """A position_id was supplied but does not exist."""


RequirementRequired = RequirementNotFound  # backwards-compatible alias


class CategoryNotFound(ValueError):
    """A demand_id was supplied but no such category exists."""


class _AdHocTarget:
    """Transient scoring target (never persisted). Stands in for a Position when the
    recruiter searches without a JD, or adds free text on top of one, so the typed query
    - not a stale JD - drives retrieval, scoring and the rerank."""
    def __init__(self, base: Optional[Position], query: str):
        qhash = hashlib.sha256(query.encode("utf-8", "ignore")).hexdigest()[:16]
        self.title = base.title if base else "Search query"
        self.jd_text = (f"{base.jd_text}\n\nRecruiter focus: {query}" if base else query)
        self.id = f"adhoc:{(base.id if base else 'none')}:{qhash}"
        self.jd_version = base.jd_version if base else 0


# Upper bound on candidates read by the relational fallback when a location/role filter is active.
RELATIONAL_FILTER_WINDOW = 5000


def _filter_report(db: Session, filters: SearchFilters, excluded_missing: int, excluded_mismatch: int) -> Optional[Dict[str, Any]]:
    """What the location/role filters did, so an empty result is explainable (and missing resume
    metadata is visible rather than silently treated as a non-match)."""
    if not filters.active:
        return None
    report: Dict[str, Any] = {"location": filters.location, "role": filters.role, "location_key": filters.location_key,
                              "location_keys": list(filters.location_keys), "role_tokens": list(filters.role_tokens),
                              "excluded_missing_metadata": excluded_missing, "excluded_mismatch": excluded_mismatch}
    if filters.location_key:
        report["candidates_without_location"] = db.query(Candidate.id).filter(Candidate.location_norm.is_(None)).count()
    if filters.role_tokens:
        report["candidates_without_titles"] = db.query(Candidate.id).filter(Candidate.title_norms.is_(None)).count()
    return report


def _empty_reason(db: Session, filters: SearchFilters, active_skills: List[str], min_experience: Optional[float],
                  pool_size: int, after_filters: int, after_skills: int, vector_rows: list, lexical_rows: list) -> Dict[str, str]:
    """Why a search returned nobody, so the UI can say something actionable instead of a generic
    'No candidates found'. Only called when the result is empty."""
    total = db.query(Candidate.id).count()
    if total == 0:
        return {"code": "no_candidates", "message": "No candidates have been ingested yet. Upload resumes on the Ingestion page, then search again."}
    searchable = db.query(Candidate.id).filter(Candidate.resume_text.isnot(None), Candidate.resume_text != "").count()
    if searchable == 0:
        return {"code": "no_resume_text", "message": f"{total} candidate(s) exist but none has searchable resume text. Re-ingest the resumes (the text could not be extracted)."}
    if filters.active and after_filters == 0:
        # With the filter pushed into the indexes the pool can be empty because of the filter itself.
        parts = [x for x in (filters.role and f"role '{filters.role}'", filters.location and f"location '{filters.location}'") if x]
        return {"code": "filters_excluded_all", "matches_without_filters": searchable,
                "message": f"{searchable} candidate(s) have searchable resumes, but none states {' and '.join(parts)}. Clear or broaden the role / location filter."}
    if pool_size == 0:
        if not vector_rows and not lexical_rows:
            return {"code": "no_retrieval_hits", "message": "The search indexes returned nothing for this query and no stored candidate satisfied the experience filter. Try different keywords or lower the minimum experience."}
        return {"code": "no_retrieval_hits", "message": "No candidate resembles this query. Try broader keywords."}
    if active_skills and after_skills == 0:
        return {"code": "skills_excluded_all", "message": f"{after_filters} candidate(s) matched, but none has all of: {', '.join(active_skills)}. Remove a skill chip."}
    if min_experience is not None:
        return {"code": "experience_excluded_all", "message": f"Candidates matched, but none has {min_experience:g}+ years of experience. Lower the minimum experience."}
    return {"code": "no_match", "message": "No candidates matched. Try different keywords."}


def execute_candidate_search(db: Session, query_text: str = "", filter_skills: Optional[List[str]] = None, min_experience: Optional[float] = None, position_id: Optional[str] = None, top_n: int = 20, location: Union[str, List[str], None] = None, role: Optional[str] = None, demand_id: Optional[str] = None) -> Dict[str, Any]:
    """Rank candidates against one requirement (JD). The query text and skill chips only
    narrow / re-rank within that requirement; there is no requirement-less scoring.

    `demand_id` scopes a requirement-less search to candidates whose skills / titles / resume qualify for that
    category (see classification.matches_category); with a requirement it only has to agree with the requirement's own category.

    `location` / `role` are hard eligibility filters: they are applied inside Qdrant and OpenSearch,
    and again against PostgreSQL before any scoring, so rank fusion and rerankers only ever see
    eligible candidates. Raises filters.InvalidFilter (a ValueError) for unusable values."""
    filters = build_filters(location, role)
    base_position = None
    if position_id:
        base_position = db.query(Position).filter(Position.id == position_id).first()
        if not base_position:
            raise RequirementNotFound("Requirement not found.")
    category = None
    if demand_id:
        category = db.query(Demand).filter(Demand.id == demand_id).first()
        if not category:
            raise CategoryNotFound("Category not found.")
        if base_position and base_position.demand_id != demand_id:
            raise ValueError(f"The selected requirement does not belong to the {category.name} category.")
    query_text = (query_text or "").strip()
    active_skills = [s.strip() for s in (filter_skills or []) if s.strip()]
    if category and not base_position and not query_text and not active_skills:
        raise ValueError(f"Enter keywords or pick a requirement to search within {category.name}.")
    if not base_position and not query_text and not active_skills and not filters.active:
        raise ValueError("Enter a search query, add a skill filter, add a location or role filter, or select a requirement.")

    scope_category = category.name if (category and not base_position) else None
    started = time.perf_counter()
    limit = max(1, min(top_n, settings.SEARCH_MAX_TOP_N))
    cache_key = _search_cache_key(query_text, filter_skills, min_experience, position_id, limit, filters, demand_id)
    cached = get_cache(cache_key)
    if cached is not None:
        logger.info("search cache_hit query=%r position=%s top_n=%s", query_text[:80], position_id or "-", limit)
        return cached

    # Query-first: whatever the recruiter typed always drives retrieval and scoring. A JD,
    # when selected, is context (title + skills), not a replacement for the query.
    persist_matches = bool(base_position) and not query_text
    ad_hoc_text = query_text or " ".join(active_skills) or " ".join(filter(None, [filters.role, filters.location]))
    target_position = base_position if persist_matches else _AdHocTarget(base_position, ad_hoc_text)
    if query_text:
        retrieval_text = f"{base_position.title} {query_text}" if base_position else query_text
    elif base_position:
        retrieval_text = f"{base_position.title} {base_position.jd_text}"
    else:
        retrieval_text = " ".join(active_skills) or ad_hoc_text
    lexical_query = retrieval_text
    vector = generate_embedding(retrieval_text)
    if base_position:
        jd_skills = extract_skills_from_jd(base_position.jd_text)
        jd_skills = list(dict.fromkeys(jd_skills + active_skills))
    else:
        jd_skills = active_skills

    candidate_limit = min(max(limit * settings.SEARCH_CANDIDATE_MULTIPLIER, 50), 500)
    vector_rows = search_vectors(vector, candidate_limit, filters) if vector else []
    # Skill chips are enforced below with text-aware matching; a hard OpenSearch keyword filter on the
    # parsed skills list would drop candidates whose resume has the skill but whose parse missed it.
    lexical_rows = search_lexical(lexical_query, candidate_limit, None, min_experience, filters)
    fused = _rrf([("vector", vector_rows), ("lexical", lexical_rows)], candidate_limit)
    _normalize_lexical_scores(fused)

    # If indexes are empty, use the relational pool rather than returning fake semantic scores.
    candidate_ids = list(fused.keys())
    indexed_candidates: List[Candidate] = []
    if candidate_ids:
        found = {c.id: c for c in db.query(Candidate).filter(Candidate.id.in_(candidate_ids)).all()}
        indexed_candidates = [found[cid] for cid in candidate_ids if cid in found]
        if not indexed_candidates:
            logger.warning("search: all %s index hits point at candidates that no longer exist (stale index entries); using the relational pool", len(candidate_ids))
    if not indexed_candidates:
        q = apply_sql_prefilter(db.query(Candidate), Candidate, filters)
        if min_experience is not None: q = q.filter(Candidate.years_experience >= min_experience)
        # With a location/role filter the exact check below can drop SQL-prefilter hits, so read a
        # wider window first instead of truncating before the filter.
        candidates = q.order_by(Candidate.uploaded_at.desc()).limit(RELATIONAL_FILTER_WINDOW if (filters.active or scope_category) else candidate_limit).all()
    else:
        candidates = indexed_candidates

    # Location / role: the authoritative check, before any scoring. The index pre-filters only narrow
    # recall; this enforces the exact rules against the stored metadata (and covers legacy index
    # entries and the relational fallback). Missing metadata is excluded, never assumed to match.
    excluded_missing = excluded_mismatch = 0
    pool_size = len(candidates)
    if filters.active:
        eligible = []
        for c in candidates:
            if candidate_matches(c.location, c.job_titles, filters):
                eligible.append(c)
            elif (filters.location_key and not c.location) or (filters.role_tokens and not c.job_titles):
                excluded_missing += 1
            else:
                excluded_mismatch += 1
        candidates = eligible[:candidate_limit]

    after_filters = len(candidates)
    if scope_category:
        candidates = [c for c in candidates if matches_category(scope_category, c.job_titles, c.extracted_skills, c.resume_text)][:candidate_limit]
    after_category = len(candidates)
    # Hard skill filters are AND-like for explicit chips: every chip should be present.
    if active_skills:
        candidates = [c for c in candidates if candidate_has_skills(c.extracted_skills or [], active_skills, c.resume_text)]
    after_skills = len(candidates)
    if min_experience is not None:
        candidates = [c for c in candidates if c.years_experience >= min_experience]

    # Pass 1a (cheap, whole pool): deterministic scoring only. No Laya/LLM calls happen
    # here, however large `candidates` is.
    deterministic: List[Tuple[Candidate, float, Dict[str, Any]]] = []
    for cand in candidates:
        fused_row = fused.get(cand.id, {"rrf": 0.0, "vector_score": 0.0, "lexical_score": 0.0})
        semantic = _semantic_score(fused_row)
        lexical_norm = float(fused_row.get("lexical_norm", 0.0))
        retrieval_score = (settings.HYBRID_VECTOR_WEIGHT * semantic) + (settings.HYBRID_LEXICAL_WEIGHT * lexical_norm)
        final_score, breakdown = calculate_hybrid_score(
            semantic_sim=retrieval_score, candidate_skills=cand.extracted_skills or [], candidate_exp=cand.years_experience,
            candidate_edu=cand.education or "", jd_title=target_position.title, jd_text=target_position.jd_text,
            target_skills=jd_skills,
            required_exp=None if base_position else (min_experience or 0.0),
            skill_coverage_fallback=None if jd_skills else lexical_norm,
            candidate_text=cand.resume_text,
        )
        deterministic.append((cand, final_score, breakdown))

    # Pass 1b: one batched Laya call reranks a bounded shortlist near the top of the
    # deterministic ranking - not the whole pool (which can be up to 500 candidates).
    # Even batched, Laya measured ~0.4s/candidate on this CPU-only hardware (the model
    # card's ~30-70ms figures assume a GPU); reranking the full pool could add tens of
    # seconds to a single search for no benefit, since a candidate far outside the
    # shortlist has no realistic path into top_n anyway.
    laya_calls = 0
    deterministic.sort(key=lambda row: row[1], reverse=True)

    # Pass 1a': BGE cross-encoder over the best chunk of the top of the deterministic
    # ranking. Skipped (ordering unchanged) when disabled or the model is unavailable.
    rerank_pool = min(len(deterministic), max(limit, settings.RERANKER_POOL_CAP))
    rerank_query = retrieval_text[:2000]
    relevances = None
    if settings.RERANKER_ENABLED:
        passages = [_rerank_passage(cand, fused.get(cand.id, {}).get("chunk_index")) for cand, _, _ in deterministic[:rerank_pool]]
        relevances = reranker.rerank_passages(rerank_query, passages)
    reranked_by_bge = relevances is not None
    if relevances is not None:
        for i, relevance in enumerate(relevances):
            cand, score, breakdown = deterministic[i]
            breakdown["rerank"] = {"model": settings.RERANKER_MODEL, "relevance": round(relevance * 100, 1), "pre_rerank_score": score}
            deterministic[i] = (cand, reranker.blend(score, relevance), breakdown)
        deterministic.sort(key=lambda row: row[1], reverse=True)
    shortlist_size = min(len(deterministic), max(limit * 2, settings.LAYA_RERANK_POOL_CAP))
    shortlist, rest = deterministic[:shortlist_size], deterministic[shortlist_size:]

    blended = decision.rerank_scores_batch([(score, cand, target_position) for cand, score, _ in shortlist])
    reranked = [
        (cand, blended_score, breakdown, laya_signal)
        for (cand, _, breakdown), (blended_score, laya_signal) in zip(shortlist, blended)
    ]
    unranked = [(cand, score, breakdown, None) for cand, score, breakdown in rest]

    # Bulk-fetch existing CandidateMatch rows once, instead of one query per
    # candidate in the loop below (an N+1 query pattern - up to `candidate_limit`,
    # i.e. up to 500, individual SELECTs per search otherwise).
    all_pool_candidates = [cand for cand, *_ in reranked + unranked]
    existing_matches = {} if not persist_matches else {
        m.candidate_id: m
        for m in db.query(CandidateMatch).filter(
            CandidateMatch.candidate_id.in_([c.id for c in all_pool_candidates]),
            CandidateMatch.position_id == target_position.id,
        ).all()
    }

    scored: List[Tuple[Candidate, float, Dict[str, Any], CandidateMatch]] = []
    for cand, final_score, breakdown, laya_signal in reranked + unranked:
        if laya_signal:
            laya_calls += 1
            breakdown["laya_rerank"] = laya_signal
        match = None
        if persist_matches:
            match = existing_matches.get(cand.id)
            if not match:
                match = CandidateMatch(candidate_id=cand.id, position_id=target_position.id)
                db.add(match)
            # pyrefly: ignore [parse-error]
            match.match_score = final_score; match.score_breakdown = breakdown; match.jd_version = target_position.jd_version
        scored.append((cand, final_score, breakdown, match))

    scored.sort(key=lambda row: row[1], reverse=True)
    top_slice = scored[:limit]

    # Pass 2 (expensive, top_n only): LLM narrative generation + guardrails. This is
    # the step that used to run once per candidate in the whole pool.
    results = []
    llm_calls = 0
    for cand, score, breakdown, match in top_slice:
        if not persist_matches:
            # Ad-hoc query: fast deterministic summary, nothing persisted against a JD.
            summary, quote, section = heuristic_match_summary(cand.extracted_skills or [], cand.years_experience, redact_pii(target_position.jd_text), target_position.title)
        elif decision.should_reuse_summary(match, target_position):
            summary, quote, section = match.llm_summary, match.cited_quote, match.cited_section
        else:
            summary, quote, section = generate_match_summary(cand.extracted_skills or [], cand.years_experience, cand.education or "", target_position.title, target_position.jd_text, score)
            llm_calls += 1
            with ai_feature("search_summary"):
                guard = check_search_result(quote, target_position.jd_text, summary)
            if not guard.passed:
                safe_jd = redact_pii(target_position.jd_text)
                summary, quote, section = heuristic_match_summary(cand.extracted_skills or [], cand.years_experience, safe_jd, target_position.title)
            # pyrefly: ignore [parse-error]
            match.llm_summary = summary; match.cited_quote = quote; match.cited_section = section

        results.append({"candidate": _candidate_payload(cand), "match_score": score, "score_breakdown": breakdown, "llm_summary": summary, "cited_quote": quote, "cited_section": section})

    db.commit()
    if persist_matches:
        # Match rows were rewritten, so cached per-candidate match matrices are stale.
        clear_cache("candidate:matches:")
    empty_reason = None if scored else _empty_reason(db, filters, active_skills, min_experience, pool_size, after_filters, after_skills, vector_rows, lexical_rows)
    if not scored and scope_category and after_filters > 0 and after_category == 0:
        empty_reason = {"code": "category_excluded_all",
                        "message": f"{after_filters} candidate(s) matched the query, but none looks like a {scope_category} profile. Try a broader keyword or pick All categories."}
    warnings = []
    if not lexical_rows and get_opensearch_client() is None:
        warnings.append("Keyword index (OpenSearch) is unavailable; results are ranked by vector similarity" + ("" if vector_rows else " or the stored candidate list") + " only.")
    if not vector_rows and not fused:
        warnings.append("Vector index (Qdrant) returned nothing; results come from the stored candidate list.")
    response = {"total_matches": len(scored), "empty_reason": empty_reason, "warnings": warnings, "top_n": limit, "results": results,
            "filters": _filter_report(db, filters, excluded_missing, excluded_mismatch),
            "scored_against_jd": ({"id": base_position.id, "title": base_position.title, "version": base_position.jd_version} if base_position else None),
            "retrieval": {"vector": bool(vector_rows), "lexical": bool(lexical_rows), "hybrid": bool(vector_rows and lexical_rows), "reranker": reranked_by_bge, "laya_calls": laya_calls, "llm_calls": llm_calls}}
    set_cache(cache_key, response, settings.CACHE_TTL_QUERY)
    logger.info(
        "search query=%r position=%s skills=%s min_exp=%s filters=%s matches=%s returned=%s vector=%s lexical=%s reranker=%s laya_calls=%s llm_calls=%s duration_ms=%s",
        query_text[:80], position_id or "-", active_skills, min_experience, filters.cache_part(), len(scored), len(results),
        bool(vector_rows), bool(lexical_rows), reranked_by_bge, laya_calls, llm_calls, round((time.perf_counter() - started) * 1000),
    )
    if not vector_rows:
        logger.warning("search used no vector results (Qdrant empty/unreachable or collection missing) - ranking is lexical/relational only")
    if not lexical_rows:
        logger.warning("search used no lexical results (OpenSearch empty/unreachable) - ranking is vector only")
    return response
    