import json
import re
from typing import Dict, List, Optional, Tuple
from backend.config import settings
from backend.services.ingestion.pii import redact_pii
from backend.services.llm.vllm import (
    chat_completion,
    generate_embedding as vllm_embedding,
    generate_embeddings_batch as vllm_embeddings_batch,
)
from backend.services.llm.local_embeddings import (
    generate_embedding as local_embedding,
    generate_embeddings_batch as local_embeddings_batch,
)


def _check_dim(vector: List[float]) -> List[float]:
    if settings.EMBEDDING_DIM and len(vector) != settings.EMBEDDING_DIM:
        # Do not silently pad/truncate: Qdrant dimension must match the real model.
        print(f"Embedding dimension is {len(vector)}; configured EMBEDDING_DIM={settings.EMBEDDING_DIM}. Using actual dimension.")
    return vector


def generate_embedding(text: str) -> List[float]:
    """Generate a real embedding. EMBEDDING_PROVIDER selects the backend: "local" runs
    fastembed in-process (no API key, no external server); anything else calls out to
    the configured vLLM-compatible embedding endpoint."""
    safe_text = redact_pii(text)
    if settings.EMBEDDING_PROVIDER == "local":
        vector = local_embedding(safe_text[:8000])
    else:
        vector = vllm_embedding(safe_text[:8000])
    return _check_dim(vector)


def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Batched form of generate_embedding - one call for many texts instead of one
    call per text. Used by bulk ingestion, the actual throughput bottleneck."""
    safe_texts = [redact_pii(t)[:8000] for t in texts]
    if settings.EMBEDDING_PROVIDER == "local":
        vectors = local_embeddings_batch(safe_texts)
    else:
        vectors = vllm_embeddings_batch(safe_texts)
    return [_check_dim(v) for v in vectors]


def _json_from_response(text: str) -> Optional[dict]:
    clean = text.strip()
    if "```json" in clean:
        clean = clean.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in clean:
        clean = clean.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        return json.loads(clean)
    except Exception:
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


def summarize_jd(title: str, jd_text: str) -> str:
    safe_jd = redact_pii(jd_text)
    prompt = f"""Summarize this job description for {title}. Return three sections: Role Purpose, Core Technical Skills & Stack, Experience & Qualifications.\n\n{safe_jd[:12000]}"""
    try:
        result = chat_completion([
            {"role": "system", "content": "You are an expert HR recruitment assistant."},
            {"role": "user", "content": prompt}
        ], temperature=0.1, max_tokens=700, enable_thinking=False)
        return result.strip()
    except Exception as exc:
        print(f"vLLM JD summary failed: {exc}")
        lines = [x.strip() for x in safe_jd.splitlines() if x.strip()]
        return f"Role: {title}\n\nOverview: {' '.join(lines[:3])[:500]}"


def heuristic_match_summary(candidate_skills: List[str], candidate_exp: float, safe_jd: str, jd_title: str) -> Tuple[str, str, str]:
    """Deterministic, no-LLM fallback summary/citation. Used when the LLM call fails
    and when a guardrail check rejects an LLM-generated summary/quote as ungrounded."""
    skills_text = ", ".join(candidate_skills[:5]) if candidate_skills else "relevant technical skills"
    sentences = re.split(r"[.!?]\s+", safe_jd)
    return (
        f"Candidate has {candidate_exp} years of experience and relevant skills including {skills_text}.",
        sentences[0][:180] if sentences else jd_title,
        "Requirements"
    )


def generate_match_summary(candidate_skills: List[str], candidate_exp: float, candidate_edu: str, jd_title: str, jd_text: str, match_score: float) -> Tuple[str, str, str]:
    safe_jd = redact_pii(jd_text)
    prompt = f"""Candidate skills: {', '.join(candidate_skills) or 'None'}\nExperience: {candidate_exp}\nEducation: {candidate_edu}\nMatch score: {match_score:.1f}%\n\nJob Description ({jd_title}):\n{safe_jd[:5000]}\n\nReturn JSON only with keys summary, cited_quote, cited_section. Keep summary to two sentences and cited_quote short and verbatim from the JD."""
    try:
        result = chat_completion([
            {"role": "system", "content": "You are a precise recruitment scoring engine. Return valid JSON only."},
            {"role": "user", "content": prompt}
        ], temperature=0.1, max_tokens=500, enable_thinking=False)
        data = _json_from_response(result)
        if data:
            return str(data.get("summary", "")), str(data.get("cited_quote", "")), str(data.get("cited_section", "Requirements"))
    except Exception as exc:
        print(f"vLLM match summary failed: {exc}")
    return heuristic_match_summary(candidate_skills, candidate_exp, safe_jd, jd_title)


def llm_extract_jd_skills(jd_text: str) -> Optional[List[str]]:
    """
    Free-form skill/requirement extraction from a job description via the LLM - not
    limited to any fixed skill dictionary, so a JD naming a niche or non-web-dev
    technology (e.g. "Camunda", "SAP", "PLC programming") isn't invisible to scoring.
    Returns None (caller falls back to the regex/dictionary scan) on any failure.
    """
    safe_jd = redact_pii(jd_text)
    prompt = f"""List every technical skill, tool, platform, framework, methodology, or
professional qualification required or preferred in this job description. Return JSON
only with key "skills" as an array of short strings (2-4 words each). Do not limit
yourself to common software/web skills - include domain-specific tools by name exactly
as they appear in the JD.

Job description:
{safe_jd[:6000]}"""
    try:
        result = chat_completion([
            {"role": "system", "content": "You are a precise requirements-extraction engine. Return valid JSON only."},
            {"role": "user", "content": prompt}
        ], temperature=0.0, max_tokens=500, enable_thinking=False)
        data = _json_from_response(result)
        if not data:
            return None
        skills = [str(s).strip() for s in (data.get("skills") or []) if str(s).strip()]
        return skills or None
    except Exception as exc:
        print(f"LLM JD skill extraction failed: {exc}")
        return None


def llm_parse_resume(raw_text: str, filename: str) -> Optional[Dict]:
    """
    Structured resume field extraction via the LLM. Deliberately not PII-redacted
    first: extracting the candidate's own name is exactly what this call needs, and
    it only ever reaches the self-hosted vLLM endpoint, never a third-party API.
    Returns None (caller falls back to the heuristic parser) on any failure.
    """
    prompt = f"""Extract structured fields from this resume. Return JSON only with keys:
candidate_name (the person's actual full name, never a section header like "Summary" or "Profile"),
extracted_skills (array of every technical skill, tool, framework, platform, or methodology
mentioned anywhere in the resume - do not limit yourself to any fixed list),
years_experience (total years of professional experience as a number),
education (degree and institution, or "Not Specified" if none is stated).

Resume filename: {filename}

Resume text:
{raw_text[:8000]}"""
    try:
        result = chat_completion([
            {"role": "system", "content": "You are a precise resume-parsing engine. Return valid JSON only."},
            {"role": "user", "content": prompt}
        ], temperature=0.0, max_tokens=600, enable_thinking=False)
        data = _json_from_response(result)
        if not data:
            return None
        return {
            "candidate_name": str(data.get("candidate_name") or "").strip(),
            "extracted_skills": [str(s).strip() for s in (data.get("extracted_skills") or []) if str(s).strip()],
            "years_experience": float(data.get("years_experience") or 0.0),
            "education": str(data.get("education") or "Not Specified").strip(),
        }
    except Exception as exc:
        print(f"LLM resume parse failed: {exc}")
        return None


def answer_chat_query(messages: List[Dict[str, str]], context: str) -> str:
    safe_context = redact_pii(context)
    system = "You are TruHire's recruitment RAG assistant. Answer only from the supplied context and conversation. If the context does not contain the answer, say so clearly."
    payload = [{"role": "system", "content": system}, {"role": "system", "content": f"Retrieved context:\n{safe_context[:12000]}"}]
    payload.extend(messages[-12:])
    return chat_completion(payload, temperature=0.15, max_tokens=900, enable_thinking=False).strip()
