import re
from typing import Dict, Any, List, Optional, Tuple
from backend.config import settings


def extract_skills_from_jd(jd_text: str) -> List[str]:
    """Extract known skill keywords mentioned in JD text."""
    from backend.services.parsing import COMMON_SKILLS
    found = []
    text_lower = jd_text.lower()
    for skill in COMMON_SKILLS:
        pattern = r'\b' + re.escape(skill.lower()) + r'\b'
        if re.search(pattern, text_lower):
            found.append(skill)
    return found


def extract_required_experience(jd_text: str) -> float:
    """Extract stated required experience from JD text."""
    from backend.services.parsing import YEARS_EXP_PATTERN
    matches = YEARS_EXP_PATTERN.findall(jd_text)
    if matches:
        nums = []
        for m in matches:
            try:
                nums.append(float(m))
            except ValueError:
                pass
        if nums:
            return max(nums)
    return 3.0  # default reasonable expectation if unstated


def compute_skill_overlap(candidate_skills: List[str], target_skills: List[str]) -> Tuple[float, List[str], List[str]]:
    """
    Computes Jaccard / coverage skill overlap score in [0.0, 1.0].
    Returns (overlap_ratio, matched_skills, missing_skills).
    """
    if not target_skills:
        return 1.0 if candidate_skills else 0.5, candidate_skills, []

    cand_set = {s.lower() for s in candidate_skills}
    target_set = {s.lower() for s in target_skills}

    matched = cand_set.intersection(target_set)
    missing = target_set.difference(cand_set)

    # Coverage ratio of required skills
    coverage = len(matched) / len(target_set) if target_set else 0.0

    # Retrieve original casing for presentation
    matched_names = [s for s in target_skills if s.lower() in matched]
    missing_names = [s for s in target_skills if s.lower() in missing]

    return round(coverage, 2), matched_names, missing_names


def calculate_hybrid_score(
    semantic_sim: float,
    candidate_skills: List[str],
    candidate_exp: float,
    candidate_edu: str,
    jd_title: str,
    jd_text: str,
    target_skills: Optional[List[str]] = None,
    required_exp: Optional[float] = None
) -> Tuple[float, Dict[str, Any]]:
    """
    Calculates hybrid score:
    Score = (SEMANTIC_WEIGHT * semantic) + (SKILL_WEIGHT * skill_overlap) + BASELINE_SCORE
            - EXPERIENCE_PENALTY - EDUCATION_PENALTY
    Normalized to 0 - 100 range.
    """
    # 1. Target skills
    if target_skills is None:
        target_skills = extract_skills_from_jd(jd_text)
    if required_exp is None:
        required_exp = extract_required_experience(jd_text)

    # 2. Skill overlap
    skill_coverage, matched_skills, missing_skills = compute_skill_overlap(candidate_skills, target_skills)

    # 3. Experience penalty
    exp_penalty = 0.0
    if required_exp > 0 and candidate_exp < required_exp:
        deficit = (required_exp - candidate_exp) / required_exp
        exp_penalty = min(settings.EXPERIENCE_PENALTY, deficit * settings.EXPERIENCE_PENALTY)

    # 4. Education penalty
    edu_penalty = 0.0
    has_degree = any(k.lower() in (candidate_edu or "").lower() for k in ["bachelor", "master", "phd", "b.s", "degree", "university", "college", "b.tech"])
    if not has_degree and ("degree" in jd_text.lower() or "bachelor" in jd_text.lower()):
        edu_penalty = settings.EDUCATION_PENALTY

    # 5. Hybrid formula
    # Clamping semantic similarity to [0, 1]
    sem_score = max(0.0, min(1.0, semantic_sim))
    raw_score = (
        (settings.SEMANTIC_WEIGHT * sem_score) +
        (settings.SKILL_WEIGHT * skill_coverage) +
        settings.BASELINE_SCORE -
        exp_penalty -
        edu_penalty
    )

    final_score = round(max(0.0, min(1.0, raw_score)) * 100.0, 1)

    breakdown = {
        "final_score": final_score,
        "semantic_score": round(sem_score * 100, 1),
        "skill_score": round(skill_coverage * 100, 1),
        "baseline_score": round(settings.BASELINE_SCORE * 100, 1),
        "experience_penalty": round(exp_penalty * 100, 1),
        "education_penalty": round(edu_penalty * 100, 1),
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "candidate_experience": candidate_exp,
        "required_experience": required_exp,
        "weights": {
            "semantic": settings.SEMANTIC_WEIGHT,
            "skill": settings.SKILL_WEIGHT,
            "baseline": settings.BASELINE_SCORE
        }
    }

    return final_score, breakdown
