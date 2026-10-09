import hashlib
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from backend.config import settings
from backend.models import Candidate, Position, CandidateMatch
from backend.services.llm import decision
from backend.services.llm.ai_service import generate_embedding, generate_match_summary, heuristic_match_summary
from backend.services.common.ai_audit import ai_feature
from backend.services.common.cache import get_cache, set_cache, clear_cache
from backend.services.llm.guardrails import check_search_result
from backend.services.ingestion.pii import redact_pii
from backend.services.retrieval.qdrant import search_vectors
from backend.services.retrieval.opensearch import search_lexical
from backend.services.retrieval.scoring import calculate_hybrid_score, extract_skills_from_jd
from backend.services.ingestion.parsing import COMMON_SKILLS, YEARS_EXP_PATTERN

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
    score = float(fused_row.get("vector_score", 0.0))
    return max(0.0, min(1.0, score))


def _candidate_payload(c: Candidate) -> Dict[str, Any]:
    return {
        "id": c.id, "display_id": c.display_id, "candidate_name": c.candidate_name, "email": c.email, "phone": c.phone,
        "extracted_skills": c.extracted_skills or [], "years_experience": c.years_experience,
        "education": c.education, "status": c.status, "original_filename": c.original_filename,
        "uploaded_at": c.uploaded_at.isoformat() if c.uploaded_at else None,
        "resume_file_url": c.resume_file_url,
    }


def _search_cache_key(query_text: str, filter_skills: Optional[List[str]], min_experience: Optional[float], position_id: Optional[str], top_n: int) -> str:
    payload = json.dumps({
        "q": query_text.strip(), "skills": sorted(s.strip().lower() for s in (filter_skills or []) if s.strip()),
        "min_exp": min_experience, "position_id": position_id, "top_n": top_n,
    }, sort_keys=True)
    return "search:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RequirementRequired(ValueError):
    """Candidates are only ever matched against a selected requirement."""


def execute_candidate_search(db: Session, query_text: str = "", filter_skills: Optional[List[str]] = None, min_experience: Optional[float] = None, position_id: Optional[str] = None, top_n: int = 20) -> Dict[str, Any]:
    """Rank candidates against one requirement (JD). The query text and skill chips only
    narrow / re-rank within that requirement; there is no requirement-less scoring."""
    target_position = db.query(Position).filter(Position.id == position_id).first() if position_id else None
    if not target_position:
        raise RequirementRequired("Select a requirement to search candidates.")

    limit = max(1, min(top_n, settings.SEARCH_MAX_TOP_N))
    cache_key = _search_cache_key(query_text, filter_skills, min_experience, position_id, limit)
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    active_skills = [s.strip() for s in (filter_skills or []) if s.strip()]
    lexical_query = f"{target_position.title} {target_position.jd_text}"
    if query_text.strip():
        lexical_query = f"{lexical_query} {query_text.strip()}"
    vector = generate_embedding(lexical_query)
    jd_skills = extract_skills_from_jd(target_position.jd_text)

    candidate_limit = min(max(limit * settings.SEARCH_CANDIDATE_MULTIPLIER, 50), 500)
    vector_rows = search_vectors(vector, candidate_limit) if vector else []
    lexical_rows = search_lexical(lexical_query, candidate_limit, active_skills, min_experience)
    fused = _rrf([("vector", vector_rows), ("lexical", lexical_rows)], candidate_limit)
    _normalize_lexical_scores(fused)

    # If indexes are empty, use the relational pool rather than returning fake semantic scores.
    candidate_ids = list(fused.keys())
    if not candidate_ids:
        q = db.query(Candidate)
        if min_experience is not None: q = q.filter(Candidate.years_experience >= min_experience)
        candidates = q.order_by(Candidate.uploaded_at.desc()).limit(candidate_limit).all()
    else:
        candidates = db.query(Candidate).filter(Candidate.id.in_(candidate_ids)).all()
        by_id = {c.id: c for c in candidates}
        candidates = [by_id[cid] for cid in candidate_ids if cid in by_id]

    # Hard skill filters are AND-like for explicit chips: every chip should be present.
    if active_skills:
        required = {s.lower() for s in active_skills}
        candidates = [c for c in candidates if required.issubset({s.lower() for s in (c.extracted_skills or [])})]
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
            target_skills=jd_skills
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
    existing_matches = {
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
        if decision.should_reuse_summary(match, target_position):
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
    # Match rows were rewritten, so cached per-candidate match matrices are stale.
    clear_cache("candidate:matches:")
    response = {"total_matches": len(scored), "top_n": limit, "results": results,
            "scored_against_jd": {"id": target_position.id, "title": target_position.title, "version": target_position.jd_version},
            "retrieval": {"vector": bool(vector_rows), "lexical": bool(lexical_rows), "hybrid": bool(vector_rows and lexical_rows), "laya_calls": laya_calls, "llm_calls": llm_calls}}
    set_cache(cache_key, response, settings.CACHE_TTL_QUERY)
    return response
    