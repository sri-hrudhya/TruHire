import io
import re
from typing import Dict, Any, List, Optional
import pypdf

# Common tech & general skills dictionary for fast heuristic extraction
COMMON_SKILLS = [
    "Python", "JavaScript", "TypeScript", "React", "Vue", "Angular", "Node.js",
    "FastAPI", "Django", "Flask", "SQL", "PostgreSQL", "MySQL", "MongoDB",
    "Redis", "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Git", "CI/CD",
    "GraphQL", "REST API", "Linux", "Terraform", "Java", "C++", "C#", "Go",
    "Rust", "PHP", "Ruby", "Spring Boot", "Microservices", "Machine Learning",
    "Deep Learning", "NLP", "PyTorch", "TensorFlow", "OpenSearch", "Elasticsearch",
    "Pandas", "NumPy", "Scikit-Learn", "Agile", "Scrum", "DevOps", "Cybersecurity",
    "System Design", "Kafka", "RabbitMQ", "HTML", "CSS", "Tailwind CSS", "Next.js"
]

EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
PHONE_PATTERN = re.compile(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')
YEARS_EXP_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+experience)?', re.IGNORECASE)
EDUCATION_KEYWORDS = ["Bachelor", "Master", "PhD", "B.S.", "M.S.", "B.Tech", "M.Tech", "B.E.", "Degree", "University", "College"]


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract raw text from PDF bytes using pypdf."""
    text = ""
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
    return text.strip()


def extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    """Extract text based on file extension."""
    ext = filename.lower().split(".")[-1]
    if ext == "pdf":
        return extract_text_from_pdf(file_bytes)
    else:
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return file_bytes.decode("latin-1", errors="ignore")


def heuristic_parse_resume(raw_text: str, filename: str) -> Dict[str, Any]:
    """
    Fast regex and keyword extraction of resume fields.
    """
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    
    # 1. Candidate Name
    candidate_name = ""
    if lines:
        # First non-empty line often contains the candidate's name
        first_line = lines[0]
        # Clean obvious header words
        if not any(k in first_line.lower() for k in ["resume", "curriculum", "vitae", "profile", "page"]):
            if len(first_line.split()) <= 4 and len(first_line) < 50:
                candidate_name = first_line

    if not candidate_name:
        # Fallback to filename without extension
        clean_name = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
        candidate_name = clean_name.title()

    # 2. Email
    emails = EMAIL_PATTERN.findall(raw_text)
    email = emails[0] if emails else None

    # 3. Phone
    phones = PHONE_PATTERN.findall(raw_text)
    phone = phones[0] if phones else None

    # 4. Skills extraction
    found_skills = []
    text_lower = raw_text.lower()
    for skill in COMMON_SKILLS:
        pattern = r'\b' + re.escape(skill.lower()) + r'\b'
        if re.search(pattern, text_lower):
            found_skills.append(skill)

    # 5. Years of experience
    years_exp = 0.0
    matches = YEARS_EXP_PATTERN.findall(raw_text)
    if matches:
        # Take the maximum reasonable stated experience
        exp_nums = []
        for m in matches:
            try:
                val = float(m)
                if 0.5 <= val <= 40.0:
                    exp_nums.append(val)
            except ValueError:
                pass
        if exp_nums:
            years_exp = max(exp_nums)
    else:
        # Estimate based on date ranges (e.g., 2018 - 2023)
        year_matches = re.findall(r'\b(19\d{2}|20\d{2})\s*[-–—to]+\s*(19\d{2}|20\d{2}|present|current)\b', raw_text, re.IGNORECASE)
        if year_matches:
            current_year = 2026
            total_duration = 0.0
            for start, end in year_matches:
                try:
                    s_yr = int(start)
                    e_yr = current_year if end.lower() in ['present', 'current'] else int(end)
                    if 1980 <= s_yr <= e_yr <= current_year:
                        total_duration += (e_yr - s_yr)
                except Exception:
                    pass
            if total_duration > 0:
                years_exp = min(total_duration, 40.0)

    # 6. Education
    education = "Not Specified"
    edu_lines = []
    for line in lines:
        if any(keyword.lower() in line.lower() for keyword in EDUCATION_KEYWORDS):
            edu_lines.append(line)
            if len(edu_lines) >= 2:
                break
    if edu_lines:
        education = " | ".join(edu_lines[:2])

    return {
        "candidate_name": candidate_name,
        "email": email,
        "phone": phone,
        "extracted_skills": found_skills,
        "years_experience": round(years_exp, 1),
        "education": education,
        "raw_text": raw_text
    }
