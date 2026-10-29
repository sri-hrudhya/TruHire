# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Recruiters (in-house and staffing-agency) working at a desktop for hours, triaging many resumes against open requirements, plus admins who assign work, and occasional hiring managers who review shortlists. All three groups were confirmed by the owner.

## Product Purpose
TruHire ingests resumes, stores job descriptions (requirements) grouped into five fixed categories (Java, GenAI, Camunda, Pega, Others), and ranks candidates against a requirement or a keyword query using hybrid vector + keyword retrieval with AI-written match summaries. Success: a recruiter finds the right candidates quickly, records a decision, hands work to a colleague and leaves feedback.

## Positioning
Search that explains itself: every result carries a score breakdown and a cited reason, and empty results say why. Reviews are shared: candidates are assigned to a recruiter per requirement and carry a comment thread.

## Operating Context
Workflow: ingest resumes, write or upload a JD, review ranked matches, set a per-requirement status (Pending Review, Shortlisted, Not Shortlisted), email candidates, search by JD, by category plus keyword, or by keyword alone. Roles: admin and recruiter.

## Capabilities and Constraints
React 18 + Vite app in `frontend/`, FastAPI backend, light and dark themes already exist. Categories are fixed system data, not user-editable. Statuses and limits come from the backend (`/api/meta`).

## Brand Commitments
Only the name TruHire is fixed. No existing logo, palette or voice must be preserved (owner confirmed).

## Evidence on Hand
No testimonials, customer names or benchmarks exist; none may be invented. Real data comes from the user's own ingested resumes.

## Product Principles
- Operate, don't decorate: scanning and deciding fast beats expression.
- Say why: scores, empty states and errors always explain themselves.
- One source of truth: enums, limits and categories come from the backend, never retyped in the UI.
- Shared by default: assignment and feedback are visible to the whole team.

## Accessibility & Inclusion
Keyboard operable (category row, lists), visible focus, WCAG AA contrast in both themes, reduced motion respected.
