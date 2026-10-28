from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from backend.database import get_db
from backend.models import User, SearchState
from backend.auth import get_current_user
from backend.services.retrieval.search import CategoryNotFound, RequirementRequired, parse_search_query, execute_candidate_search
from backend.services.retrieval.filters import MAX_FILTER_CHARS, MAX_LOCATION_FILTERS, clean_filter_text

router = APIRouter(prefix="/api/search", tags=["search"])
class SearchRequest(BaseModel):
    query: Optional[str] = ""
    filter_skills: Optional[List[str]] = Field(default_factory=list)
    min_experience: Optional[float] = None
    # Optional: a typed query / skill chips search on their own; a JD only adds context.
    position_id: Optional[str] = None
    # Optional: restricts a requirement-less search to one category (Demand); needs a query, skills or a JD.
    demand_id: Optional[str] = None
    top_n: Optional[int] = 20
    # Hard eligibility filters; blank means "no filter". Normalization/validation lives in retrieval.filters.
    location: Optional[str] = Field(default=None, max_length=MAX_FILTER_CHARS * 2)
    # Several places at once: a candidate in any of them qualifies. Merged with `location` when both are sent.
    locations: Optional[List[str]] = Field(default=None, max_length=MAX_LOCATION_FILTERS)
    role: Optional[str] = Field(default=None, max_length=MAX_FILTER_CHARS * 2)

    @field_validator("location", "role", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError("must be a string")
        return clean_filter_text(value)

    @field_validator("locations", mode="before")
    @classmethod
    def _clean_locations(cls, value):
        if value is None:
            return None
        if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) for v in value):
            raise ValueError("must be a list of strings")
        return [t for t in (clean_filter_text(v) for v in value) if t]

    def places(self) -> List[str]:
        return [p for p in [self.location, *(self.locations or [])] if p]

@router.get("/state")
def get_search_state(db=Depends(get_db), user: User = Depends(get_current_user)):
    state = db.query(SearchState).filter(SearchState.user_id == user.id).first()
    # Saved searches from before requirement-only search have no position and are not restored.
    if not state or not (state.position_id or state.query):
        return {"state": None}
    return {"state": {
        "query": state.query, "filter_skills": state.filter_skills or [],
        "min_experience": state.min_experience, "position_id": state.position_id,
        # Hard location/role filters are never restored: a forgotten one silently zeroes every later search.
        "location": None, "role": None,
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
    places = req.places()
    try:
        result = execute_candidate_search(db, clean_query, skills, min_exp, req.position_id, req.top_n or 20, places or None, req.role, req.demand_id)
    except CategoryNotFound:
        raise HTTPException(status_code=404, detail="Category not found.")
    except RequirementRequired:
        raise HTTPException(status_code=404, detail="Requirement not found.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result.update({"active_filter_chips": skills, "min_experience": min_exp, "location": ", ".join(places) or None, "locations": places, "role": req.role, "modifier_mode": mode, "query": clean_query})

    state = db.query(SearchState).filter(SearchState.user_id == user.id).first()
    if not state:
        state = SearchState(user_id=user.id)
        db.add(state)
    state.query = clean_query
    state.filter_skills = skills
    state.min_experience = min_exp
    state.location = ", ".join(places) or None
    state.role = req.role
    state.position_id = req.position_id or None
    state.top_n = req.top_n or 20
    state.results = result.get("results", [])
    state.total_matches = int(result.get("total_matches", 0))
    state.retrieval = result.get("retrieval", {})
    db.commit()
    return result
