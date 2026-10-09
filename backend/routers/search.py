from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from backend.database import get_db
from backend.models import User, SearchState
from backend.auth import get_current_user
from backend.services.retrieval.search import RequirementRequired, parse_search_query, execute_candidate_search

router = APIRouter(prefix="/api/search", tags=["search"])
class SearchRequest(BaseModel):
    query: Optional[str] = ""
    filter_skills: Optional[List[str]] = Field(default_factory=list)
    min_experience: Optional[float] = None
    # Candidates are only matched against a selected requirement; there is no requirement-less search.
    position_id: str = Field(..., min_length=1)
    top_n: Optional[int] = 20

@router.get("/state")
def get_search_state(db=Depends(get_db), user: User = Depends(get_current_user)):
    state = db.query(SearchState).filter(SearchState.user_id == user.id).first()
    # Saved searches from before requirement-only search have no position and are not restored.
    if not state or not state.position_id:
        return {"state": None}
    return {"state": {
        "query": state.query, "filter_skills": state.filter_skills or [],
        "min_experience": state.min_experience, "position_id": state.position_id,
        "top_n": state.top_n, "results": state.results or [],
        "total_matches": state.total_matches, "retrieval": state.retrieval or {},
        "updated_at": state.updated_at.isoformat() if state.updated_at else None
    }}

@router.delete("/state")
def clear_search_state(db=Depends(get_db), user: User = Depends(get_current_user)):
    state = db.query(SearchState).filter(SearchState.user_id == user.id).first()
    if state:
        db.delete(state); db.commit()
    return {"cleared": True}

@router.post("")
def search_candidates_endpoint(req: SearchRequest, db=Depends(get_db), user: User = Depends(get_current_user)):
    skills, parsed_exp, clean_query, mode = parse_search_query(req.query or "", req.filter_skills)
    min_exp = req.min_experience if req.min_experience is not None else parsed_exp
    try:
        result = execute_candidate_search(db, clean_query, skills, min_exp, req.position_id, req.top_n or 20)
    except RequirementRequired:
        raise HTTPException(status_code=404, detail="Requirement not found.")
    result.update({"active_filter_chips": skills, "min_experience": min_exp, "modifier_mode": mode, "query": clean_query})

    state = db.query(SearchState).filter(SearchState.user_id == user.id).first()
    if not state:
        state = SearchState(user_id=user.id)
        db.add(state)
    state.query = clean_query
    state.filter_skills = skills
    state.min_experience = min_exp
    state.position_id = req.position_id
    state.top_n = req.top_n or 20
    state.results = result.get("results", [])
    state.total_matches = int(result.get("total_matches", 0))
    state.retrieval = result.get("retrieval", {})
    db.commit()
    return result
