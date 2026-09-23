from backend.services.parsing import heuristic_parse_resume, extract_text_from_file


def test_heuristic_parse_resume_fields():
    resume_text = """Johnathan Doe
j.doe@enterprise.com | +1 (415) 555-2671 | San Francisco, CA

PROFESSIONAL SUMMARY
Senior Cloud Engineer with 6 years of experience designing scalable microservices.

TECHNICAL SKILLS
Languages & Frameworks: Python, FastAPI, TypeScript, React, Go
Cloud & DevOps: Docker, Kubernetes, AWS, Terraform, CI/CD
Databases: PostgreSQL, Redis

EDUCATION
Bachelor of Science in Computer Science, University of California, Berkeley (2018)
"""

    parsed = heuristic_parse_resume(resume_text, "Johnathan_Doe_Resume.pdf")
    assert parsed["candidate_name"] == "Johnathan Doe"
    assert parsed["email"] == "j.doe@enterprise.com"
    assert "415" in parsed["phone"]
    assert "Python" in parsed["extracted_skills"]
    assert "Docker" in parsed["extracted_skills"]
    assert "Kubernetes" in parsed["extracted_skills"]
    assert "PostgreSQL" in parsed["extracted_skills"]
    assert parsed["years_experience"] >= 6.0
    assert "Bachelor" in parsed["education"]


def test_extract_text_from_txt_file():
    content = b"Sample text resume for Jane Smith\nSkills: Python, SQL"
    text = extract_text_from_file("jane_resume.txt", content)
    assert "Jane Smith" in text
    assert "Python" in text
