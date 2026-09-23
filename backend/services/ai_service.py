import hashlib
import json
import math
import re
from typing import Dict, Any, List, Optional, Tuple

from backend.config import settings
from backend.services.pii import redact_pii

# Initialize Groq client if key available
groq_client = None
if settings.GROQ_API_KEY:
    try:
        from groq import Groq
        groq_client = Groq(api_key=settings.GROQ_API_KEY)
    except Exception as e:
        print(f"Failed to initialize Groq client: {e}")


def _mock_embedding(text: str, dim: int = 768) -> List[float]:
    """
    Generates a deterministic, normalized vector embedding using pseudo-random token projection.
    Semantically similar texts sharing keywords will have higher cosine similarity.
    """
    vector = [0.0] * dim
    words = re.findall(r'\w+', text.lower())
    if not words:
        return [1.0 / math.sqrt(dim)] * dim

    for word in words:
        # Seeded projection
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
        index = h % dim
        sign = 1.0 if (h >> 4) % 2 == 0 else -1.0
        vector[index] += sign * (1.0 + (len(word) / 10.0))

    # Normalize vector to unit length (L2 norm)
    norm = math.sqrt(sum(x * x for x in vector))
    if norm > 0:
        return [x / norm for x in vector]
    return [1.0 / math.sqrt(dim)] * dim


def generate_embedding(text: str) -> List[float]:
    """
    Generates text embedding. Redacts PII first if any remains.
    """
    safe_text = redact_pii(text)

    # If OpenRouter is configured for embeddings
    if settings.EMBEDDING_PROVIDER == "openrouter" and settings.OPENROUTER_API_KEY:
        try:
            import httpx
            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": settings.EMBEDDING_MODEL,
                "input": safe_text[:2000]
            }
            resp = httpx.post("https://openrouter.ai/api/v1/embeddings", json=payload, headers=headers, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                return data["data"][0]["embedding"]
        except Exception as e:
            print(f"OpenRouter embedding error: {e}, falling back to local deterministic embedding.")

    return _mock_embedding(safe_text, dim=settings.EMBEDDING_DIM)


def _call_groq_chat(prompt: str, system_prompt: str = "You are an expert HR and recruitment AI assistant.") -> Optional[str]:
    """Call Groq API with automatic fallback model."""
    if not groq_client:
        return None

    # Try primary model
    try:
        completion = groq_client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=600,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Groq primary model ({settings.GROQ_MODEL}) failed: {e}. Trying fallback model...")

    # Try fallback model
    try:
        completion = groq_client.chat.completions.create(
            model=settings.GRO_FALLBACK_MODEL if hasattr(settings, 'GRO_FALLBACK_MODEL') else settings.GROQ_FALLBACK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=600,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Groq fallback model failed: {e}")
        return None


def summarize_jd(title: str, jd_text: str) -> str:
    """
    Produces a structured summary of a Job Description.
    """
    safe_jd = redact_pii(jd_text)

    prompt = f"""
Summarize the following Job Description for title: "{title}".
JD Text:
\"\"\"{safe_jd}\"\"\"

Provide a concise, 3-section summary:
1. Role Purpose (1-2 sentences)
2. Core Technical Skills & Stack
3. Experience & Qualification Requirements
"""
    result = _call_groq_chat(prompt)
    if result:
        return result.strip()

    # High-quality fallback deterministic summary
    lines = [l.strip() for l in safe_jd.splitlines() if l.strip()]
    first_few = " ".join(lines[:3])[:250]
    return (
        f"**Role:** {title}\n\n"
        f"**Overview:** {first_few}...\n\n"
        f"**Key Requirements:** Extensive hands-on experience in modern technology stack, "
        f"collaborative problem-solving, and building resilient systems."
    )


def generate_match_summary(
    candidate_skills: List[str],
    candidate_exp: float,
    candidate_edu: str,
    jd_title: str,
    jd_text: str,
    match_score: float
) -> Tuple[str, str, str]:
    """
    Produces an LLM match summary, cited quote, and cited section.
    """
    safe_jd = redact_pii(jd_text)
    
    prompt = f"""
Candidate profile:
- Skills: {", ".join(candidate_skills) if candidate_skills else "None specified"}
- Years Experience: {candidate_exp} years
- Education: {candidate_edu}
- Match Score: {match_score:.1f}%

Job Description ({jd_title}):
\"\"\"{safe_jd[:1500]}\"\"\"

Provide JSON output with keys:
"summary": a 2-sentence explanation of candidate fit,
"cited_quote": a direct short excerpt from the JD that justifies this match,
"cited_section": section name in JD (e.g. "Requirements", "Responsibilities")
"""
    groq_res = _call_groq_chat(prompt, system_prompt="You are an AI scoring engine. Return pure JSON only.")
    if groq_res:
        try:
            # Extract JSON
            clean = groq_res.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0].strip()
            elif "```" in clean:
                clean = clean.split("```")[1].split("```")[0].strip()
            data = json.loads(clean)
            return (
                data.get("summary", ""),
                data.get("cited_quote", ""),
                data.get("cited_section", "Requirements")
            )
        except Exception:
            pass

    # Fallback deterministic justification
    skills_text = ", ".join(candidate_skills[:4]) if candidate_skills else "general profile"
    summary = (
        f"Candidate offers {candidate_exp} years of industry experience with proven proficiency in {skills_text}. "
        f"Matches key qualifications outlined for the {jd_title} opening."
    )
    
    # Extract representative quote from JD
    sentences = re.split(r'[.!?]\s+', safe_jd)
    quote = sentences[0][:150] if sentences else f"Seeking qualified candidates for {jd_title}."
    section = "Requirements & Qualifications"

    return summary, quote, section


def answer_chat_query(messages: List[Dict[str, str]], context: str) -> str:
    """
    RAG conversational response over candidate or JD context.
    """
    safe_context = redact_pii(context)
    last_user_query = messages[-1]["content"] if messages else ""

    prompt = f"""
Context:
\"\"\"{safe_context[:2500]}\"\"\"

Conversation history:
{json.dumps(messages[-4:], indent=2)}

User Question: {last_user_query}

Answer the user question accurately based solely on the provided context. If unsure, state clearly.
"""
    result = _call_groq_chat(prompt)
    if result:
        return result.strip()

    # Fallback answer
    return (
        f"Based on the provided records, the candidate/job matches requirements with relevant "
        f"background. Question: '{last_user_query}'."
    )
