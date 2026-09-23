import re
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import Candidate, Position, CandidateMatch
from backend.services.ai_service import generate_embedding, generate_match_summary
from backend.services.opensearch import search_vectors
from backend.services.scoring import calculate_hybrid_score, extract_skills_from_jd, compute_skill_overlap
from backend.services.parsing import COMMON_SKILLS, YEARS_EXP_PATTERN


MODIFIERS_APPEND = ["and", "also", "too", "plus", "with"]
MODIFIERS_REPLACE = ["only", "just", "instead", "solely"]


def parse_search_query(
    query_text: str,
    existing_skills: Optional[List[str]] = None
) -> Tuple[List[str], Optional[float], str, str]:
    """
    Parses a search query string.
    Identifies modifier intent:
    - If contains 'and', 'also', 'too': mode is 'append'
    - If contains 'only', 'just', 'instead': mode is 'replace'
    - Default: 'append' if existing chips, otherwise 'replace'
    
    Returns:
    (updated_skill_chips, min_years_exp, clean_query_text, modifier_mode)
    """
    existing = list(existing_skills or [])
    text_lower = query_text.lower().strip()

    modifier_mode = "neutral"
    # Check for replace words
    for word in MODIFIERS_REPLACE:
        if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
            modifier_mode = "replace"
            break

    # Check for append words
    if modifier_mode == "neutral":
        for word in MODIFIERS_APPEND:
            if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
                modifier_mode = "append"
                break

    # Extract skills
    found_skills = []
    for skill in COMMON_SKILLS:
        if re.search(r'\b' + re.escape(skill.lower()) + r'\b', text_lower):
            found_skills.append(skill)

    # Extract experience requirements
    min_exp = None
    exp_matches = YEARS_EXP_PATTERN.findall(query_text)
    if exp_matches:
        try:
            min_exp = float(exp_matches[0])
        except ValueError:
            pass

    # Resolve skill chips based on modifier mode
    if modifier_mode == "replace":
        updated_skills = found_skills if found_skills else existing
    elif modifier_mode == "append":
        combined = set(existing)
        combined.update(found_skills)
        updated_skills = list(combined)
    else:
        # Default behavior: union of existing and new skills
        combined = set(existing)
        combined.update(found_skills)
        updated_skills = list(combined)

    return updated_skills, min_exp, query_text, modifier_mode


def execute_candidate_search(
    db: Session,
    query_text: str = "",
    filter_skills: Optional[List[str]] = None,
    min_experience: Optional[float] = None,
    position_id: Optional[str] = None,
    top_n: int = 20
) -> Dict[str, Any]:
    """
    Executes search over the shared candidate pool.
    - Resolves filter chips and experience filters.
    - Uses vector semantic search.
    - If position_id is selected, scores candidates against that JD and persists CandidateMatch.
    - Always strictly paginated to top_n (max SEARCH_MAX_TOP_N).
    - Returns total match count and top-N ranked items.
    """
    # 1. Enforce strict pagination limits
    limit = max(1, min(top_n, settings.SEARCH_MAX_TOP_N))

    # 2. Base candidate pool query
    base_query = db.query(Candidate)

    if min_experience is not None and min_experience > 0:
        base_query = base_query.filter(Candidate.years_experience >= min_experience)

    all_candidates = base_query.all()
    total_candidates_count = len(all_candidates)

    if not all_candidates:
        return {
            "total_matches": 0,
            "top_n": limit,
            "results": [],
            "scored_against_jd": None
        }

    # 3. Filter by skills if present
    active_skills = [s.strip() for s in (filter_skills or []) if s.strip()]
    filtered_candidates = []
    for cand in all_candidates:
        cand_skills = [s.lower() for s in (cand.extracted_skills or [])]
        if active_skills:
            # Must match at least one active filter skill
            if any(req.lower() in cand_skills for req in active_skills):
                filtered_candidates.append(cand)
        else:
            filtered_candidates.append(cand)

    total_matches = len(filtered_candidates)

    # 4. If Position / JD is selected, compute candidate-vs-JD match scores
    target_position = None
    if position_id:
        target_position = db.query(Position).filter(Position.id == position_id).first()

    results = []

    # Generate query or JD vector for semantic ranking
    if target_position:
        ref_text = f"{target_position.title} {target_position.jd_text}"
        ref_vector = generate_embedding(ref_text)
        jd_skills = extract_skills_from_jd(target_position.jd_text)

        # Get vector rankings
        vec_results = search_vectors(ref_vector, top_k=len(filtered_candidates) or 1)
        sim_map = {item["candidate_id"]: item["score"] for item in vec_results}

        for cand in filtered_candidates:
            sim = sim_map.get(cand.id, 0.5)
            final_score, breakdown = calculate_hybrid_score(
                semantic_sim=sim,
                candidate_skills=cand.extracted_skills or [],
                candidate_exp=cand.years_experience,
                candidate_edu=cand.education or "",
                jd_title=target_position.title,
                jd_text=target_position.jd_text,
                target_skills=jd_skills
            )

            # Check if CandidateMatch exists or needs update
            existing_match = db.query(CandidateMatch).filter(
                CandidateMatch.candidate_id == cand.id,
                CandidateMatch.position_id == target_position.id
            ).first()

            summary, quote, section = generate_match_summary(
                candidate_skills=cand.extracted_skills or [],
                candidate_exp=cand.years_experience,
                candidate_edu=cand.education or "",
                jd_title=target_position.title,
                jd_text=target_position.jd_text,
                match_score=final_score
            )

            if existing_match:
                existing_match.match_score = final_score
                existing_match.score_breakdown = breakdown
                existing_match.llm_summary = summary
                existing_match.cited_quote = quote
                existing_match.cited_section = section
                existing_match.jd_version = target_position.jd_version
            else:
                new_match = CandidateMatch(
                    candidate_id=cand.id,
                    position_id=target_position.id,
                    match_score=final_score,
                    score_breakdown=breakdown,
                    llm_summary=summary,
                    cited_quote=quote,
                    cited_section=section,
                    jd_version=target_position.jd_version
                )
                db.add(new_match)

            results.append({
                "candidate": {
                    "id": cand.id,
                    "candidate_name": cand.candidate_name,
                    "email": cand.email,
                    "phone": cand.phone,
                    "extracted_skills": cand.extracted_skills or [],
                    "years_experience": cand.years_experience,
                    "education": cand.education,
                    "status": cand.status,
                    "original_filename": cand.original_filename,
                    "uploaded_at": cand.uploaded_at.isoformat() if cand.uploaded_at else None,
                },
                "match_score": final_score,
                "score_breakdown": breakdown,
                "llm_summary": summary,
                "cited_quote": quote,
                "cited_section": section
            })

        db.commit()
        # Sort descending by match_score
        results.sort(key=lambda x: x["match_score"], reverse=True)

    else:
        # No JD selected: rank by skill overlap with active_skills & query semantic similarity
        if query_text:
            query_vector = generate_embedding(query_text)
            vec_results = search_vectors(query_vector, top_k=len(filtered_candidates) or 1)
            sim_map = {item["candidate_id"]: item["score"] for item in vec_results}
        else:
            sim_map = {}

        for cand in filtered_candidates:
            # Skill overlap with active filter chips
            overlap_ratio, matched, missing = compute_skill_overlap(cand.extracted_skills or [], active_skills)
            sem_sim = sim_map.get(cand.id, 0.5)

            # Combined ranking score
            rank_score = round(((0.6 * overlap_ratio) + (0.4 * sem_sim)) * 100.0, 1)

            results.append({
                "candidate": {
                    "id": cand.id,
                    "candidate_name": cand.candidate_name,
                    "email": cand.email,
                    "phone": cand.phone,
                    "extracted_skills": cand.extracted_skills or [],
                    "years_experience": cand.years_experience,
                    "education": cand.education,
                    "status": cand.status,
                    "original_filename": cand.original_filename,
                    "uploaded_at": cand.uploaded_at.isoformat() if cand.uploaded_at else None,
                },
                "match_score": rank_score,
                "score_breakdown": {
                    "final_score": rank_score,
                    "skill_score": round(overlap_ratio * 100, 1),
                    "semantic_score": round(sem_sim * 100, 1),
                    "matched_skills": matched,
                    "missing_skills": missing
                },
                "llm_summary": f"Matches {len(matched)} requested skill(s).",
                "cited_quote": None,
                "cited_section": None
            })

        results.sort(key=lambda x: x["match_score"], reverse=True)

    # Strictly slice top-N
    paginated_results = results[:limit]

    return {
        "total_matches": total_matches,
        "top_n": limit,
        "results": paginated_results,
        "scored_against_jd": {
            "id": target_position.id,
            "title": target_position.title,
            "version": target_position.jd_version
        } if target_position else None
    }
