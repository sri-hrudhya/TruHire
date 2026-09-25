import hashlib
import re
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from backend.config import settings
from backend.models import Candidate, Position, CandidateMatch
from backend.services.ai_service import generate_embedding, generate_match_summary
from backend.services.qdrant import search_vectors
from backend.services.opensearch import search_lexical
from backend.services.scoring import calculate_hybrid_score, extract_skills_from_jd, compute_skill_overlap
from backend.services.parsing import COMMON_SKILLS, YEARS_EXP_PATTERN

MODIFIERS_APPEND = ["and", "also", "too", "plus", "with"]
MODIFIERS_REPLACE = ["only", "just", "instead", "solely"]


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
        "id": c.id, "candidate_name": c.candidate_name, "email": c.email, "phone": c.phone,
        "extracted_skills": c.extracted_skills or [], "years_experience": c.years_experience,
        "education": c.education, "status": c.status, "original_filename": c.original_filename,
        "uploaded_at": c.uploaded_at.isoformat() if c.uploaded_at else None,
    }


def execute_candidate_search(db: Session, query_text: str = "", filter_skills: Optional[List[str]] = None, min_experience: Optional[float] = None, position_id: Optional[str] = None, top_n: int = 20) -> Dict[str, Any]:
    limit = max(1, min(top_n, settings.SEARCH_MAX_TOP_N))
    active_skills = [s.strip() for s in (filter_skills or []) if s.strip()]
    target_position = db.query(Position).filter(Position.id == position_id).first() if position_id else None

    if target_position:
        lexical_query = f"{target_position.title} {target_position.jd_text}"
        if query_text.strip():
            lexical_query = f"{lexical_query} {query_text.strip()}"
        vector = generate_embedding(lexical_query)
        jd_skills = extract_skills_from_jd(target_position.jd_text)
    else:
        lexical_query = query_text.strip()
        vector = generate_embedding(lexical_query) if lexical_query else None
        jd_skills = active_skills

    candidate_limit = min(max(limit * settings.SEARCH_CANDIDATE_MULTIPLIER, 50), 500)
    vector_rows = search_vectors(vector, candidate_limit) if vector else []
    lexical_rows = search_lexical(lexical_query, candidate_limit, active_skills, min_experience) if lexical_query else []
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

    results = []
    for cand in candidates:
        fused_row = fused.get(cand.id, {"rrf": 0.0, "vector_score": 0.0, "lexical_score": 0.0})
        semantic = _semantic_score(fused_row)
        lexical_norm = float(fused_row.get("lexical_norm", 0.0))
        retrieval_score = (settings.HYBRID_VECTOR_WEIGHT * semantic) + (settings.HYBRID_LEXICAL_WEIGHT * lexical_norm)
        if target_position:
            final_score, breakdown = calculate_hybrid_score(
                semantic_sim=retrieval_score, candidate_skills=cand.extracted_skills or [], candidate_exp=cand.years_experience,
                candidate_edu=cand.education or "", jd_title=target_position.title, jd_text=target_position.jd_text,
                target_skills=jd_skills
            )
            summary, quote, section = generate_match_summary(cand.extracted_skills or [], cand.years_experience, cand.education or "", target_position.title, target_position.jd_text, final_score)
            match = db.query(CandidateMatch).filter(CandidateMatch.candidate_id == cand.id, CandidateMatch.position_id == target_position.id).first()
            if not match:
                match = CandidateMatch(candidate_id=cand.id, position_id=target_position.id)
                db.add(match)
            match.match_score = final_score; match.score_breakdown = breakdown; match.llm_summary = summary; match.cited_quote = quote; match.cited_section = section; match.jd_version = target_position.jd_version
            score = final_score
        else:
            overlap, matched, missing = compute_skill_overlap(cand.extracted_skills or [], active_skills)
            # RRF is used for retrieval; semantic cosine is shown separately. When only lexical retrieval exists, score remains meaningful.
            score = round(((0.70 * retrieval_score) + (0.30 * overlap)) * 100, 1)
            summary = f"Hybrid retrieval matched {len(matched)} requested skill(s)."
            quote = ""
            section = "Search"
            breakdown = {"final_score": score, "semantic_score": round(semantic * 100, 1), "retrieval_score": round(retrieval_score * 100, 1), "hybrid_rrf": round(fused_row.get("rrf", 0.0), 6), "lexical_score": round(fused_row.get("lexical_score", 0.0), 3), "lexical_normalized": round(lexical_norm * 100, 1), "matched_skills": matched, "missing_skills": missing}

        results.append({"candidate": _candidate_payload(cand), "match_score": score, "score_breakdown": breakdown, "llm_summary": summary, "cited_quote": quote, "cited_section": section})

    db.commit() if target_position else None
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return {"total_matches": len(results), "top_n": limit, "results": results[:limit],
            "scored_against_jd": ({"id": target_position.id, "title": target_position.title, "version": target_position.jd_version} if target_position else None),
            "retrieval": {"vector": bool(vector_rows), "lexical": bool(lexical_rows), "hybrid": bool(vector_rows and lexical_rows)}}
