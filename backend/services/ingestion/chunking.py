"""Overlapping resume chunking. Embedding models read ~512 tokens, so a whole resume
embedded as one vector silently loses everything after the first page."""
import re
from typing import List

CHUNK_CHARS = 1400
CHUNK_OVERLAP = 200
MAX_CHUNKS = 12


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP, max_chunks: int = MAX_CHUNKS) -> List[str]:
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text) and len(chunks) < max_chunks:
        end = min(start + size, len(text))
        if end < len(text):
            # Prefer to cut at a line/sentence/word boundary in the last 30% of the window.
            window_start = start + int(size * 0.7)
            cut = max(text.rfind("\n", window_start, end), text.rfind(". ", window_start, end), text.rfind(" ", window_start, end))
            if cut > start:
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def profile_chunks(header: str, resume_text: str) -> List[str]:
    """Each chunk is prefixed with the candidate header (name/skills/experience) so every
    vector keeps the candidate's identity context."""
    body = chunk_text(resume_text)
    if not body:
        return [header]
    return [f"{header}\n{c}" for c in body]


def candidate_header(candidate) -> str:
    return (
        f"Name: {candidate.candidate_name}\nSkills: {', '.join(candidate.extracted_skills or [])}\n"
        f"Experience: {candidate.years_experience}\nEducation: {candidate.education or ''}"
    )
