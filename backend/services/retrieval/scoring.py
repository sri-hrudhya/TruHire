import logging
import hashlib
import re
from functools import lru_cache
from typing import Dict, Any, List, Optional, Tuple
from backend.config import settings

logger = logging.getLogger(__name__)


def extract_skills_from_jd(jd_text: str) -> List[str]:
    """
    Extract required skills/tools mentioned in JD text. Tries free-form LLM extraction
    first (not limited to any fixed dictionary, so niche/domain-specific requirements
    aren't invisible to scoring), cached by JD content hash so the same JD text never
    re-triggers the LLM call. Falls back to the regex/dictionary scan on any failure.
    """
    from backend.services.common.cache import get_cache, set_cache

    cache_key = "jd_skills:" + hashlib.sha256(jd_text.encode("utf-8", "ignore")).hexdigest()
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    llm_skills = None
    try:
        from backend.services.llm.ai_service import llm_extract_jd_skills
        llm_skills = llm_extract_jd_skills(jd_text)
    except Exception as exc:
        logger.warning(f"LLM JD skill extraction unavailable: {exc}")

    if llm_skills:
        set_cache(cache_key, llm_skills, settings.CACHE_TTL_DECISION)
        return llm_skills

    from backend.services.ingestion.parsing import COMMON_SKILLS
    found = []
    text_lower = jd_text.lower()
    for skill in COMMON_SKILLS:
        pattern = r'\b' + re.escape(skill.lower()) + r'\b'
        if re.search(pattern, text_lower):
            found.append(skill)
    set_cache(cache_key, found, settings.CACHE_TTL_DECISION)
    return found


def extract_required_experience(jd_text: str) -> float:
    """Extract stated required experience from JD text."""
    from backend.services.ingestion.parsing import YEARS_EXP_PATTERN
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


# Spelling variants that must count as the same skill. Keys and values are normalized forms.
SKILL_ALIASES = {
    "nodejs": "node.js", "node": "node.js", "js": "javascript", "ts": "typescript", "k8s": "kubernetes",
    "postgres": "postgresql", "golang": "go", "reactjs": "react", "vuejs": "vue", "angularjs": "angular",
    "springboot": "spring boot", "restful": "rest api", "rest": "rest api", "restful api": "rest api",
    "ci cd": "ci/cd", "cicd": "ci/cd", "ml": "machine learning", "gcp": "google cloud", "tf": "terraform",
    "mongo": "mongodb", "elastic search": "elasticsearch", "dotnet": ".net", "csharp": "c#",
    "microservice": "microservices", "micro-services": "microservices", "micro services": "microservices",
    "web-service": "web services", "webservices": "web services",
}
_VERSION = re.compile(r"(?<![a-z0-9])v?\d+(?:\.\d+)*(?:\.x)?(?![a-z0-9+#])", re.I)


def normalize_skill(skill: str) -> str:
    """'Camunda 8.5' -> 'camunda', 'REST APIs' -> 'rest api', 'NodeJS' -> 'node.js'. Versions are dropped
    (a Camunda 8 developer satisfies 'Camunda'), plurals folded, common aliases unified."""
    s = re.sub(r"\s+", " ", (skill or "").strip().lower())
    s = _VERSION.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip(" -_/,.")
    if s.endswith("apis"):
        s = s[:-1]
    return SKILL_ALIASES.get(s, s)


@lru_cache(maxsize=2048)
def _skill_text_pattern(normalized: str) -> "re.Pattern":
    variants = {normalized} | {alias for alias, canon in SKILL_ALIASES.items() if canon == normalized}
    alt = "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True))
    # alphanumeric-boundary (not \\b) so tokens like "c++", "node.js", "ci/cd" match whole.
    # An optional version suffix and plural 's' are tolerated: "Camunda 8", "REST APIs".
    return re.compile(rf"(?<![a-z0-9])(?:{alt})(?:s)?(?![a-z0-9])", re.I)


def compute_skill_overlap(candidate_skills: List[str], target_skills: List[str], resume_text: Optional[str] = None) -> Tuple[float, List[str], List[str]]:
    """
    Coverage of the required skills in [0.0, 1.0]. A required skill counts as matched when it is in
    the candidate's extracted skills (after normalization) OR appears in the resume text itself - so a
    skill the parser missed (or spelled differently) still counts for a candidate who clearly has it.
    Returns (coverage, matched_skills, missing_skills).
    """
    if not target_skills:
        return 1.0 if candidate_skills else 0.5, candidate_skills, []

    cand_norm = {normalize_skill(s) for s in candidate_skills}
    text = resume_text or ""
    matched_names, missing_names, seen = [], [], set()
    for skill in target_skills:
        norm = normalize_skill(skill)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        if norm in cand_norm or (text and _skill_text_pattern(norm).search(text)):
            matched_names.append(skill)
        else:
            missing_names.append(skill)
    total = len(matched_names) + len(missing_names)
    coverage = len(matched_names) / total if total else 0.0
    return round(coverage, 2), matched_names, missing_names


def candidate_has_skills(candidate_skills: List[str], required: List[str], resume_text: Optional[str] = None) -> bool:
    """All-of check used by explicit skill-chip filters (same normalization + text fallback)."""
    cov, _, missing = compute_skill_overlap(candidate_skills, required, resume_text)
    return not missing


def calculate_hybrid_score(
    semantic_sim: float,
    candidate_skills: List[str],
    candidate_exp: float,
    candidate_edu: str,
    jd_title: str,
    jd_text: str,
    target_skills: Optional[List[str]] = None,
    required_exp: Optional[float] = None,
    skill_coverage_fallback: Optional[float] = None,
    candidate_text: Optional[str] = None,
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
    skill_coverage, matched_skills, missing_skills = compute_skill_overlap(candidate_skills, target_skills, candidate_text)
    if not target_skills and skill_coverage_fallback is not None:
        # No skills to measure against (free-text query): use lexical relevance rather than
        # handing every candidate a free 100% skill score.
        skill_coverage = max(0.0, min(1.0, skill_coverage_fallback))

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
