import json
import re
from typing import Dict, List, Optional, Tuple
from backend.config import settings
from backend.services.pii import redact_pii
from backend.services.vllm import chat_completion, generate_embedding as vllm_embedding


def generate_embedding(text: str) -> List[float]:
    """Generate a real embedding from the DGX/vLLM OpenAI-compatible endpoint."""
    safe_text = redact_pii(text)
    vector = vllm_embedding(safe_text[:8000])
    if settings.EMBEDDING_DIM and len(vector) != settings.EMBEDDING_DIM:
        # Do not silently pad/truncate: Qdrant dimension must match the real model.
        print(f"Embedding dimension is {len(vector)}; configured EMBEDDING_DIM={settings.EMBEDDING_DIM}. Using actual dimension.")
    return vector


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
        ], temperature=0.1, max_tokens=700)
        return result.strip()
    except Exception as exc:
        print(f"vLLM JD summary failed: {exc}")
        lines = [x.strip() for x in safe_jd.splitlines() if x.strip()]
        return f"Role: {title}\n\nOverview: {' '.join(lines[:3])[:500]}"


def generate_match_summary(candidate_skills: List[str], candidate_exp: float, candidate_edu: str, jd_title: str, jd_text: str, match_score: float) -> Tuple[str, str, str]:
    safe_jd = redact_pii(jd_text)
    prompt = f"""Candidate skills: {', '.join(candidate_skills) or 'None'}\nExperience: {candidate_exp}\nEducation: {candidate_edu}\nMatch score: {match_score:.1f}%\n\nJob Description ({jd_title}):\n{safe_jd[:5000]}\n\nReturn JSON only with keys summary, cited_quote, cited_section. Keep summary to two sentences and cited_quote short and verbatim from the JD."""
    try:
        result = chat_completion([
            {"role": "system", "content": "You are a precise recruitment scoring engine. Return valid JSON only."},
            {"role": "user", "content": prompt}
        ], temperature=0.1, max_tokens=500)
        data = _json_from_response(result)
        if data:
            return str(data.get("summary", "")), str(data.get("cited_quote", "")), str(data.get("cited_section", "Requirements"))
    except Exception as exc:
        print(f"vLLM match summary failed: {exc}")
    skills_text = ", ".join(candidate_skills[:5]) if candidate_skills else "relevant technical skills"
    sentences = re.split(r"[.!?]\s+", safe_jd)
    return (
        f"Candidate has {candidate_exp} years of experience and relevant skills including {skills_text}.",
        sentences[0][:180] if sentences else jd_title,
        "Requirements"
    )


def answer_chat_query(messages: List[Dict[str, str]], context: str) -> str:
    safe_context = redact_pii(context)
    system = "You are TruHire's recruitment RAG assistant. Answer only from the supplied context and conversation. If the context does not contain the answer, say so clearly."
    payload = [{"role": "system", "content": system}, {"role": "system", "content": f"Retrieved context:\n{safe_context[:12000]}"}]
    payload.extend(messages[-12:])
    return chat_completion(payload, temperature=0.15, max_tokens=900).strip()
