import hashlib
import json
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import User
from backend.auth import get_current_user
from backend.services.search import parse_search_query, execute_candidate_search
from backend.services.cache import get_cache, set_cache

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRequest(BaseModel):
    query: Optional[str] = ""
    filter_skills: Optional[List[str]] = []
    min_experience: Optional[float] = None
    position_id: Optional[str] = None
    top_n: Optional[int] = 20


class ParseQueryRequest(BaseModel):
    query: str
    existing_skills: Optional[List[str]] = []


@router.post("/parse-query")
def parse_query_endpoint(
    req: ParseQueryRequest,
    user: User = Depends(get_current_user)
):
    """
    Parses a natural language query for skill chips, experience, and modifier intent
    (and/also/too vs only/just/instead).
    """
    updated_skills, min_exp, clean_query, modifier_mode = parse_search_query(
        req.query, req.existing_skills
    )
    return {
        "updated_skills": updated_skills,
        "min_experience": min_exp,
        "clean_query": clean_query,
        "modifier_mode": modifier_mode
    }


@router.post("")
def search_candidates_endpoint(
    req: SearchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Search candidates across the entire shared pool.
    - Natural language query with skill filter first, then semantic vector ranking.
    - Modifier detection (and/also/too adds to filters, only/just/instead replaces).
    - If position_id is selected, scores candidates against that JD and stores CandidateMatch.
    - Strictly paginated to top_n (default 20, max 100).
    """
    # 1. Parse modifiers and extract skills from query
    resolved_skills = list(req.filter_skills or [])
    min_exp = req.min_experience
    modifier_mode = "neutral"

    if req.query and req.query.strip():
        parsed_skills, parsed_exp, _, mode = parse_search_query(req.query, resolved_skills)
        resolved_skills = parsed_skills
        modifier_mode = mode
        if parsed_exp is not None and (min_exp is None or min_exp == 0):
            min_exp = parsed_exp

    # 2. Check query cache (if no position_id scoring is requested, cache lookup is active)
    cache_key = None
    if not req.position_id:
        cache_params = f"{req.query}_{sorted(resolved_skills)}_{min_exp}_{req.top_n}"
        cache_key = f"search_{hashlib.md5(cache_params.encode('utf-8')).hexdigest()}"
        cached_result = get_cache(cache_key)
        if cached_result:
            return cached_result

    # 3. Execute search
    search_output = execute_candidate_search(
        db=db,
        query_text=req.query or "",
        filter_skills=resolved_skills,
        min_experience=min_exp,
        position_id=req.position_id,
        top_n=req.top_n or settings.SEARCH_TOP_N
    )

    search_output["active_filter_chips"] = resolved_skills
    search_output["min_experience"] = min_exp
    search_output["modifier_mode"] = modifier_mode

    # Cache if not position scoring
    if cache_key:
        set_cache(cache_key, search_output, settings.CACHE_TTL_QUERY)

    return search_output
