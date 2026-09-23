from collections import Counter
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import Candidate, Position, CandidateMatch, IngestionBatch, User
from backend.auth import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
def get_analytics_overview(
    position_id: Optional[str] = Query(None, description="Optional JD ID to filter match score distribution"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Returns high-level aggregated talent pool analytics.
    Strictly aggregates data without returning individual candidate lists.
    """
    # 1. Total Counts
    total_candidates = db.query(Candidate).count()
    total_positions = db.query(Position).count()
    total_batches = db.query(IngestionBatch).count()

    # 2. Candidates per Skill (Top ANALYTICS_TOP_SKILLS)
    all_cands = db.query(Candidate.extracted_skills, Candidate.years_experience, Candidate.status, Candidate.uploaded_at).all()
    skill_counter = Counter()
    for row in all_cands:
        skills = row[0] or []
        for s in skills:
            if s:
                skill_counter[s] += 1

    top_skills = [
        {"skill": skill, "count": count}
        for skill, count in skill_counter.most_common(settings.ANALYTICS_TOP_SKILLS)
    ]

    # 3. Experience Distribution (0-2y, 3-5y, 5+y)
    exp_buckets = {
        "0-2 years": 0,
        "3-5 years": 0,
        "5+ years": 0
    }
    for row in all_cands:
        exp = row[1] or 0.0
        if exp < 2.5:
            exp_buckets["0-2 years"] += 1
        elif exp <= 5.0:
            exp_buckets["3-5 years"] += 1
        else:
            exp_buckets["5+ years"] += 1

    # 4. Match-Score Distribution (80%+, 60-80%, <60%)
    match_query = db.query(CandidateMatch.match_score)
    if position_id:
        match_query = match_query.filter(CandidateMatch.position_id == position_id)

    matches = match_query.all()
    score_buckets = {
        "80%+": 0,
        "60-80%": 0,
        "<60%": 0
    }
    total_score = 0.0
    for m in matches:
        sc = m[0]
        total_score += sc
        if sc >= 80.0:
            score_buckets["80%+"] += 1
        elif sc >= 60.0:
            score_buckets["60-80%"] += 1
        else:
            score_buckets["<60%"] += 1

    avg_score = round(total_score / len(matches), 1) if matches else 0.0

    # 5. Ingestion Stats Over Time (by date)
    date_counter = Counter()
    for row in all_cands:
        up_at = row[3]
        if up_at:
            d_str = up_at.strftime("%Y-%m-%d")
            date_counter[d_str] += 1

    # Sort ingestion by date
    sorted_dates = sorted(date_counter.keys())
    ingestion_timeline = [
        {"date": d, "resumes_added": date_counter[d]}
        for d in sorted_dates[-14:]  # Last 14 active days
    ]

    # Batch failure stats
    batches = db.query(IngestionBatch).all()
    total_failed_files = sum(b.failed_count or 0 for b in batches)
    total_duplicate_files = sum(b.duplicate_count or 0 for b in batches)

    # 6. Status Funnel (New -> Shortlisted -> Interviewed -> Rejected)
    status_funnel = {
        "New": 0,
        "Shortlisted": 0,
        "Interviewed": 0,
        "Rejected": 0
    }
    for row in all_cands:
        st = row[2] or "New"
        if st in status_funnel:
            status_funnel[st] += 1
        else:
            status_funnel["New"] += 1

    return {
        "summary": {
            "total_candidates": total_candidates,
            "total_job_descriptions": total_positions,
            "total_batches": total_batches,
            "total_failed_files": total_failed_files,
            "total_duplicate_files": total_duplicate_files,
            "average_match_score": avg_score,
            "evaluated_matches_count": len(matches)
        },
        "top_skills": top_skills,
        "experience_distribution": exp_buckets,
        "match_score_distribution": score_buckets,
        "status_funnel": status_funnel,
        "ingestion_timeline": ingestion_timeline,
        "filtered_by_position_id": position_id
    }
