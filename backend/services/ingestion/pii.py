import re
from typing import Dict, List, Optional

# Compiled regex patterns for PII detection
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', re.IGNORECASE)
PHONE_REGEX = re.compile(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', re.IGNORECASE)
SSN_REGEX = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
ADDRESS_REGEX = re.compile(
    r'\b\d{1,5}\s+[A-Za-z0-9\.\s]{2,25}\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Circle|Cir|Terrace|Ter|Parkway|Pkwy|Place|Pl|Square|Sq)\b',
    re.IGNORECASE
)
POSTAL_CODE_REGEX = re.compile(r'\b\d{5}(?:-\d{4})?\b')


def detect_pii(text: str) -> Dict[str, List[str]]:
    """
    Detects potential PII occurrences in a text string.
    Returns a dictionary with found items.
    """
    if not text:
        return {}

    return {
        "emails": EMAIL_REGEX.findall(text),
        "phones": PHONE_REGEX.findall(text),
        "ssn": SSN_REGEX.findall(text),
        "addresses": ADDRESS_REGEX.findall(text),
    }


def redact_pii(text: str, candidate_name: Optional[str] = None) -> str:
    """
    Redacts all PII from text before passing to external AI or embeddings.
    Replaces sensitive data with placeholder tokens:
    [EMAIL], [PHONE], [NAME], [ADDRESS], [ID].
    """
    if not text:
        return ""

    redacted = text

    # 1. Redact Emails first (prevents name tokens from mangling email addresses)
    redacted = EMAIL_REGEX.sub("[EMAIL]", redacted)

    # 2. Redact Phone numbers
    redacted = PHONE_REGEX.sub("[PHONE]", redacted)

    # 3. Redact SSN / national IDs
    redacted = SSN_REGEX.sub("[ID]", redacted)

    # 4. Redact street addresses
    redacted = ADDRESS_REGEX.sub("[ADDRESS]", redacted)

    # 5. Redact explicit candidate name if provided and non-trivial
    if candidate_name and len(candidate_name.strip()) > 2:
        name_tokens = candidate_name.strip().split()
        # Redact full name
        pattern = re.compile(re.escape(candidate_name.strip()), re.IGNORECASE)
        redacted = pattern.sub("[NAME]", redacted)
        # Redact individual name parts if longer than 2 chars
        for token in name_tokens:
            if len(token) > 2 and token.lower() not in {"resume", "curriculum", "vitae", "experience", "profile"}:
                t_pattern = re.compile(r'\b' + re.escape(token) + r'\b', re.IGNORECASE)
                redacted = t_pattern.sub("[NAME]", redacted)

    return redacted
