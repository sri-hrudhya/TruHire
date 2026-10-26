"""Location and role filters: normalization, matching and index-payload helpers.

One module owns the rules so the three places that need them - Qdrant and OpenSearch
(candidate pre-filter), and the PostgreSQL check that runs before scoring - cannot drift.

Principles:
- A filter only ever *narrows*. A candidate with no stored location / job titles never matches an
  active filter for that field (missing data is not a match, and nothing is guessed).
- Locations are equal only when their normalized place names are equal (spelling variants such as
  Bangalore/Bengaluru are unified; different cities are never merged).
- Roles are compared on canonical token sets, so "Backend Developer" == "Backend Engineer" while
  "Backend Engineer" != "Software Engineer" and != "Backend Engineering Manager".
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MAX_FILTER_CHARS = 100
MAX_TITLES = 10
MAX_TITLE_CHARS = 80
MAX_TITLE_WORDS = 8


class InvalidFilter(ValueError):
    """A location/role filter value that cannot be normalized into anything searchable."""


def _ascii_lower(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in folded if not unicodedata.combining(ch)).lower()


def clean_filter_text(value: Optional[str]) -> Optional[str]:
    """Trim, drop control characters and collapse whitespace. Empty input -> None (no filter)."""
    if value is None:
        return None
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


# --- Locations -------------------------------------------------------------------------

# Spelling / legacy-name variants of the *same* place. Everything not listed is compared as-is, so
# unknown places degrade to exact (normalized) match rather than to a guess.
LOCATION_ALIASES = {
    "bangalore": "bengaluru", "bengaluru urban": "bengaluru", "bombay": "mumbai", "madras": "chennai",
    "calcutta": "kolkata", "gurgaon": "gurugram", "new delhi": "delhi", "poona": "pune",
    "trivandrum": "thiruvananthapuram", "cochin": "kochi", "mysore": "mysuru", "vizag": "visakhapatnam",
    "nyc": "new york", "new york city": "new york", "sf": "san francisco", "la": "los angeles",
    "washington dc": "washington", "washington d.c": "washington",
    "usa": "united states", "us": "united states", "u.s": "united states", "u.s.a": "united states",
    "united states of america": "united states", "america": "united states",
    "uk": "united kingdom", "u.k": "united kingdom", "great britain": "united kingdom",
    "uae": "united arab emirates", "bharat": "india",
}
_LOCATION_NOISE_WORDS = re.compile(r"\b(?:remote|hybrid|onsite|on-site|relocation|open to relocate|willing to relocate)\b", re.I)
_LOCATION_AREA_SUFFIX = re.compile(r"\b(?:metropolitan area|metro area|metro|area|region|city|district)$")
_LOCATION_AREA_PREFIX = re.compile(r"^(?:greater)\s+")


def location_keys(raw: Optional[str]) -> List[str]:
    """'Bangalore, Karnataka, India' -> ['bengaluru', 'karnataka', 'india'] (most specific first)."""
    text = clean_filter_text(raw)
    if not text:
        return []
    text = re.sub(r"\([^)]*\)", " ", _ascii_lower(text))
    text = _LOCATION_NOISE_WORDS.sub(" ", text)
    keys: List[str] = []
    for part in re.split(r"[,;|\n]", text):
        part = re.sub(r"[^a-z0-9.\s'-]", " ", part)
        part = re.sub(r"\s+", " ", part).strip(" .-'")
        part = _LOCATION_AREA_PREFIX.sub("", part)
        part = _LOCATION_AREA_SUFFIX.sub("", part).strip()
        part = LOCATION_ALIASES.get(part, part)
        if len(part) >= 2 and part not in keys:
            keys.append(part)
    return keys


def location_key(raw: Optional[str]) -> Optional[str]:
    """The single most specific place named, used as the filter value."""
    keys = location_keys(raw)
    return keys[0] if keys else None


# --- Roles -----------------------------------------------------------------------------

_ROLE_PHRASES = [
    (re.compile(r"\bback[\s-]*end\b"), "backend"),
    (re.compile(r"\bfront[\s-]*end\b"), "frontend"),
    (re.compile(r"\bfull[\s-]*stack\b"), "fullstack"),
    (re.compile(r"\b(?:sde|swe)\b"), "software engineer"),
    (re.compile(r"\bdev[\s-]*ops\b"), "devops"),
    (re.compile(r"\bml\b"), "machine learning"),
    (re.compile(r"\bqa\b"), "quality assurance"),
]
# Words that name the same job; seniority/level words are dropped because experience level is a
# separate filter (min. experience) and "Senior Backend Engineer" is still a Backend Engineer.
_ROLE_TOKEN_ALIASES = {"developer": "engineer", "developers": "engineer", "dev": "engineer", "programmer": "engineer",
                       "engineers": "engineer"}
_ROLE_DROPPED = {"senior", "sr", "junior", "jr", "principal", "i", "ii", "iii", "iv", "and", "of", "the", "a", "an", "at", "for", "in"}


def role_tokens(raw: Optional[str]) -> Tuple[str, ...]:
    """Canonical, sorted token set of one job title. Empty tuple when nothing usable remains."""
    text = clean_filter_text(raw)
    if not text:
        return ()
    text = _ascii_lower(text)
    text = re.sub(r"[()\[\],|/&_]", " ", text)
    for pattern, replacement in _ROLE_PHRASES:
        text = pattern.sub(replacement, text)
    tokens = set()
    for tok in re.findall(r"[a-z0-9+#.]+", text.replace("-", " ")):
        tok = tok.strip(".")
        tok = _ROLE_TOKEN_ALIASES.get(tok, tok)
        if tok and re.search(r"[a-z0-9]", tok) and tok not in _ROLE_DROPPED:
            tokens.update(tok.split())
    return tuple(sorted(tokens))


# --- Filter object ---------------------------------------------------------------------

@dataclass(frozen=True)
class SearchFilters:
    location: Optional[str] = None            # recruiter-visible text
    role: Optional[str] = None
    location_key: Optional[str] = None        # normalized, drives matching and the cache key
    role_tokens: Tuple[str, ...] = ()

    @property
    def active(self) -> bool:
        return bool(self.location_key or self.role_tokens)

    def cache_part(self) -> Dict[str, Any]:
        return {"location": self.location_key, "role": " ".join(self.role_tokens) or None}


NO_FILTERS = SearchFilters()


def build_filters(location: Optional[str], role: Optional[str]) -> SearchFilters:
    """Validate and normalize recruiter input. Blank -> no filter; unusable text -> InvalidFilter."""
    loc_text, role_text = clean_filter_text(location), clean_filter_text(role)
    if loc_text and len(loc_text) > MAX_FILTER_CHARS or role_text and len(role_text) > MAX_FILTER_CHARS:
        raise InvalidFilter(f"Location and role filters are limited to {MAX_FILTER_CHARS} characters.")
    loc_key = location_key(loc_text) if loc_text else None
    if loc_text and not loc_key:
        raise InvalidFilter("Location filter has no recognizable place name.")
    tokens = role_tokens(role_text) if role_text else ()
    if role_text and not tokens:
        raise InvalidFilter("Role filter has no recognizable job title.")
    return SearchFilters(location=loc_text, role=role_text, location_key=loc_key, role_tokens=tokens)


# --- Candidate side --------------------------------------------------------------------

def clean_titles(values: Any) -> List[str]:
    """Bound a list of job titles: strings only, short, no sentences, de-duplicated, most recent first."""
    titles: List[str] = []
    seen = set()
    for value in values if isinstance(values, (list, tuple)) else []:
        title = re.sub(r"\s+", " ", str(value or "")).strip(" -|,;:")
        if not title or len(title) > MAX_TITLE_CHARS or len(title.split()) > MAX_TITLE_WORDS:
            continue
        if not role_tokens(title):
            continue
        if title.lower() not in seen:
            seen.add(title.lower())
            titles.append(title)
        if len(titles) >= MAX_TITLES:
            break
    return titles


def _delimited(values: Iterable[str]) -> Optional[str]:
    values = [v for v in values if v]
    return ("|" + "|".join(values) + "|") if values else None


def candidate_filter_fields(location: Optional[str], titles: Any) -> Dict[str, Any]:
    """Column values derived from raw extracted metadata. `location_norm` / `title_norms` are
    '|'-delimited so SQL can pre-narrow with LIKE; exact matching always re-checks the raw values."""
    loc = clean_filter_text(location)
    cleaned = clean_titles(titles)
    return {
        "location": loc,
        "location_norm": _delimited(location_keys(loc)),
        "job_titles": cleaned,
        "title_norms": _delimited(" ".join(role_tokens(t)) for t in cleaned),
    }


def set_candidate_filter_metadata(candidate: Any, location: Optional[str], titles: Any) -> None:
    for column, value in candidate_filter_fields(location, titles).items():
        setattr(candidate, column, value)


def index_payload_fields(location: Optional[str], titles: Any) -> Dict[str, Any]:
    """Fields stored in the Qdrant payload and OpenSearch document for filter push-down."""
    cleaned = clean_titles(titles)
    tokens = sorted({tok for t in cleaned for tok in role_tokens(t)})
    return {"location": clean_filter_text(location) or "", "location_keys": location_keys(location),
            "job_titles": cleaned, "role_tokens": tokens}


def candidate_matches(location: Optional[str], titles: Sequence[str], filters: SearchFilters) -> bool:
    """Authoritative eligibility check. Missing metadata never satisfies an active filter."""
    if filters.location_key and filters.location_key not in location_keys(location):
        return False
    if filters.role_tokens:
        wanted = set(filters.role_tokens)
        if not any(wanted <= set(role_tokens(t)) for t in (titles or [])):
            return False
    return True


def apply_sql_prefilter(query, candidate_model, filters: SearchFilters):
    """Cheap, recall-safe narrowing for the relational fallback (a superset of candidate_matches)."""
    if filters.location_key:
        query = query.filter(candidate_model.location_norm.like(f"%|{_like_escape(filters.location_key)}|%", escape="\\"))
    for tok in filters.role_tokens:
        query = query.filter(candidate_model.title_norms.like(f"%{_like_escape(tok)}%", escape="\\"))
    return query


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --- Index query fragments -------------------------------------------------------------

def qdrant_filter(filters: SearchFilters) -> Optional[Dict[str, Any]]:
    must: List[Dict[str, Any]] = []
    if filters.location_key:
        must.append({"key": "location_keys", "match": {"value": filters.location_key}})
    must.extend({"key": "role_tokens", "match": {"value": tok}} for tok in filters.role_tokens)
    return {"must": must} if must else None


def opensearch_filters(filters: SearchFilters) -> List[Dict[str, Any]]:
    clauses: List[Dict[str, Any]] = []
    if filters.location_key:
        clauses.append({"term": {"location_keys": filters.location_key}})
    clauses.extend({"term": {"role_tokens": tok}} for tok in filters.role_tokens)
    return clauses


# --- JD side ---------------------------------------------------------------------------

_JD_LOCATION_LABEL = re.compile(r"^(?:job\s+|work\s+|office\s+|primary\s+)?(?:location|city)s?\s*[:\-]\s*(.+)$", re.I)
_JD_ROLE_LABEL = re.compile(r"^(?:job\s+title|position(?:\s+title)?|role|designation|opening|title)\s*[:\-]\s*(.+)$", re.I)
_JD_MODE_LABEL = re.compile(r"^(?:work\s+(?:mode|type|model|arrangement)|workplace(?:\s+type)?|employment\s+mode)\s*[:\-]\s*(.+)$", re.I)
_JD_MODE_PHRASES = [
    ("remote", re.compile(r"\b(?:fully|100%|completely)\s+remote\b|\bremote[\s-]first\b|\bwork\s+from\s+home\b", re.I)),
    ("hybrid", re.compile(r"\bhybrid\s+(?:work|model|setup|role|position)\b|\b\d\s+days?\s+(?:a|per)\s+week\s+(?:in|at)\s+(?:the\s+)?office\b", re.I)),
    ("onsite", re.compile(r"\b(?:on[\s-]?site|work\s+from\s+office)\s+(?:role|position|only|required)\b|\bwork\s+from\s+office\b", re.I)),
]


def _work_mode_in(text: str) -> str:
    lowered = text.lower()
    for mode, pattern in (("hybrid", re.compile(r"\bhybrid\b")), ("remote", re.compile(r"\bremote\b")), ("onsite", re.compile(r"\bon[\s-]?site\b|\bin[\s-]office\b|\bwork from office\b"))):
        if pattern.search(lowered):
            return mode
    return ""


def heuristic_jd_filters(jd_text: str) -> Dict[str, str]:
    """Label-driven fallback ('Location: Pune', 'Job Title: ...'); reports only what the JD states."""
    out = {"location": "", "role": "", "work_mode": ""}
    lines = [ln.strip(" \t*#-•") for ln in (jd_text or "").splitlines() if ln.strip()]
    for line in lines[:80]:
        if not out["location"] and (m := _JD_LOCATION_LABEL.match(line)):
            value = re.sub(r"\s*[|•].*$", "", m.group(1)).strip(" ,.;")
            if 2 <= len(value) <= MAX_FILTER_CHARS:
                out["location"] = value
                out["work_mode"] = out["work_mode"] or _work_mode_in(m.group(1))
        elif not out["role"] and (m := _JD_ROLE_LABEL.match(line)):
            candidate = clean_titles([m.group(1)])
            out["role"] = candidate[0] if candidate else ""
        elif not out["work_mode"] and (m := _JD_MODE_LABEL.match(line)):
            out["work_mode"] = _work_mode_in(m.group(1))
    if not out["work_mode"]:
        for mode, pattern in _JD_MODE_PHRASES:
            if pattern.search(jd_text or ""):
                out["work_mode"] = mode
                break
    return out


# Document words that name the file, not the job ("Senior Data Scientist Job Description"): never part of a role.
_TITLE_NOISE = re.compile(r"\b(?:job\s+descriptions?|jds?|job\s+requirements?|requirements?|requisitions?|vacanc(?:y|ies)|openings?|positions?)\b", re.I)


def strip_title_noise(title: Optional[str]) -> str:
    return re.sub(r"\s+", " ", _TITLE_NOISE.sub(" ", title or "")).strip(" -|,;:")


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9+#.]+", _ascii_lower(text))


def _location_stated_in(location: str, jd_text: str) -> bool:
    """Anti-hallucination: the place named must literally appear in the JD."""
    haystack = " " + " ".join(_words(jd_text)) + " "
    parts = [" ".join(_words(p)) for p in re.split(r"[,;|]", location)]
    return any(p and f" {p} " in haystack for p in parts)


def _role_stated_in(role: str, jd_text: str, title: str) -> bool:
    haystack = set(_words(jd_text)) | set(_words(title))
    words = _words(role)
    return bool(words) and all(w in haystack for w in words)


def extract_jd_filters(title: str, jd_text: str) -> Dict[str, Any]:
    """Target location, role and work mode for a JD. LLM extraction first (only accepted when the
    value literally appears in the JD/title), label heuristics second, then the recruiter-entered
    requirement title for the role. Nothing is inferred beyond what the text states."""
    llm: Dict[str, str] = {}
    try:
        from backend.services.llm.ai_service import llm_extract_jd_filters
        llm = llm_extract_jd_filters(title, jd_text) or {}
    except Exception:
        llm = {}
    heur = heuristic_jd_filters(jd_text)

    location, loc_source = "", None
    for value, source in ((llm.get("location", ""), "jd_text"), (heur["location"], "jd_text")):
        if value and location_key(value) and _location_stated_in(value, jd_text):
            location, loc_source = value, source
            break
    role, role_source = "", None
    for value, source in ((llm.get("role", ""), "jd_text"), (heur["role"], "jd_text")):
        if value and role_tokens(value) and _role_stated_in(value, jd_text, title):
            role, role_source = value, source
            break
    if not role:
        cleaned = clean_titles([strip_title_noise(title)])
        if cleaned:
            role, role_source = cleaned[0], "title"
    work_mode = llm.get("work_mode") or heur["work_mode"] or ""
    return {"location": location or None, "role": role or None, "work_mode": work_mode or None,
            "sources": {"location": loc_source, "role": role_source}}
