"""Requirement Tracker values read from what a resume states. Anything the resume does not state stays blank."""
import re
from typing import Dict, Iterable, Optional

_LABEL_END = r"[ \t]*[:\-–][ \t]*([^\n]{1,80})"


def _labelled(text: str, labels: str) -> Optional[str]:
    match = re.search(rf"(?im)^[ \t•\-*]*(?:{labels}){_LABEL_END}", text)
    return match.group(1).strip(" .;,") if match else None


FRAMEWORKS = ("Spring Boot", "Spring", "Hibernate", "Struts", "Django", "Flask", "FastAPI", "Angular", "React", "Vue", "Node.js",
              "Express", ".NET Core", "ASP.NET", "Entity Framework", "Camunda", "Activiti", "jBPM", "Pega Constellation", "Selenium",
              "TestNG", "JUnit", "Kafka", "Micronaut", "Quarkus", "Bootstrap", "jQuery")
DOMAINS = ("Banking", "BFSI", "Insurance", "Healthcare", "Telecom", "Retail", "E-commerce", "Finance", "Logistics",
           "Manufacturing", "Pharma", "Automotive", "Energy", "Education", "Government", "Travel", "Media")


def _present(names: Iterable[str], text: str, skills: Iterable[str]) -> Optional[str]:
    haystack = text + "\n" + "\n".join(skills)
    found = [n for n in names if re.search(rf"(?<![\w.]){re.escape(n)}(?![\w])", haystack, re.I)]
    return ", ".join(dict.fromkeys(found)) or None


def resume_fields(text: Optional[str], skills: Optional[Iterable[str]]) -> Dict[str, str]:
    """Tracker columns a resume can state: CTCs, notice and joining dates, preferred location, offer, reason, domains, frameworks."""
    text = text or ""
    skills = list(skills or [])
    notice = _labelled(text, r"notice\s+period|serving\s+notice")
    found = {
        "current_ctc": _labelled(text, r"current\s+(?:ctc|salary|compensation)|c\.?ctc"),
        "expected_ctc": _labelled(text, r"expected\s+(?:ctc|salary|compensation)|e\.?ctc"),
        "lwd": _labelled(text, r"lwd|last\s+working\s+(?:day|date)"),
        "expected_joining": _labelled(text, r"expected\s+(?:date\s+of\s+)?joining(?:\s+date)?|available\s+from|joining\s+date"),
        "preferred_location": _labelled(text, r"preferred\s+(?:work\s+)?location|location\s+preference"),
        "offer_in_hand": _labelled(text, r"offers?\s+in\s+hand|current\s+offers?"),
        "reason_for_change": _labelled(text, r"reason\s+for\s+(?:job\s+)?change|reason\s+for\s+leaving"),
        "relevant_experience": _labelled(text, r"relevant\s+experience"),
        "domains": _present(DOMAINS, text, []),
        "frameworks": _present(FRAMEWORKS, text, skills),
    }
    if notice:
        found["serving_notice"] = "Yes" if re.search(r"serving|currently\s+serving", text, re.I) and not re.search(r"not\s+serving", text, re.I) else "No"
    return {key: value for key, value in found.items() if value}
