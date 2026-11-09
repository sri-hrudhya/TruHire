"""Client scoped search over saved, active job descriptions."""
from sqlalchemy import func

from backend.models import Position
from backend.services.retrieval.search import execute_candidate_search


def list_client_names(db):
    rows = (db.query(func.min(Position.client_name))
            .filter(Position.client_name.isnot(None), func.trim(Position.client_name) != "")
            .filter(func.coalesce(Position.status, "Open") != "Cancelled")
            .group_by(func.lower(func.trim(Position.client_name)))
            .order_by(func.lower(func.trim(Position.client_name))).all())
    return [row[0] for row in rows if row[0]]


def search_client_requirements(db, client_name, query_text, filter_skills=None,
                                min_experience=None, top_n=20, location=None,
                                role=None, demand_id=None, position_id=None):
    """Search each active JD matching client_name and keep distinct JD result groups."""
    normalized = " ".join((client_name or "").split()).casefold()
    positions = (db.query(Position)
                 .filter(Position.client_name.isnot(None), func.lower(func.trim(Position.client_name)) == normalized)
                 .filter(func.coalesce(Position.status, "Open") != "Cancelled"))
    if demand_id:
        positions = positions.filter(Position.demand_id == demand_id)
    if position_id:
        positions = positions.filter(Position.id == position_id)
    positions = positions.order_by(Position.created_at.desc(), Position.id).all()
    if not positions:
        return {"total_matches": 0, "empty_reason": "No active saved requirements were found for this client.",
                "warnings": [], "top_n": top_n, "results": [], "client_groups": [], "filters": {},
                "scored_against_jd": False, "retrieval": {}}

    groups = []
    warnings = []
    for position in positions:
        result = execute_candidate_search(db, query_text, filter_skills, min_experience,
                                          position.id, top_n, location, role, position.demand_id)
        groups.append({"position": {"id": position.id, "display_id": position.display_id,
                                     "title": position.title, "client_name": position.client_name,
                                     "demand_id": position.demand_id},
                       "total_matches": result.get("total_matches", 0),
                       "results": result.get("results", []),
                       "retrieval": result.get("retrieval", {}),
                       "empty_reason": result.get("empty_reason")})
        warnings.extend(result.get("warnings", []))
    flattened = [item for group in groups for item in group["results"]]
    return {"total_matches": sum(group["total_matches"] for group in groups),
            "empty_reason": None if flattened else "No candidates matched the client's active requirements.",
            "warnings": list(dict.fromkeys(warnings)), "top_n": top_n, "results": flattened,
            "client_groups": groups, "filters": {}, "scored_against_jd": True,
            "retrieval": {"mode": "client_requirements", "requirements": len(groups)}}
