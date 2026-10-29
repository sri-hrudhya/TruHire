// Turns the backend's score_breakdown (hybrid score: semantic + skill overlap + baseline - penalties)
// into the rows of the "why this score" explanation, using the numbers the scorer already returned.

const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
const signed = (v) => `${v < 0 ? '−' : '+'}${Math.abs(v).toFixed(1)}`;

// Contribution rows in percentage points; they add up to the final score (before clamping to 0-100).
export function explainScore(breakdown) {
  const b = breakdown || {};
  const w = b.weights || {};
  const rows = [
    { key: 'semantic', label: 'Semantic similarity', detail: `${num(b.semantic_score)}% similarity × ${num(w.semantic)} weight`, points: num(b.semantic_score) * num(w.semantic) },
    { key: 'skill', label: 'Skill overlap', detail: `${num(b.skill_score)}% of required skills × ${num(w.skill)} weight`, points: num(b.skill_score) * num(w.skill) },
    { key: 'baseline', label: 'Baseline credit', detail: 'Fixed starting credit', points: num(b.baseline_score) },
  ];
  if (num(b.experience_penalty) > 0) {
    rows.push({ key: 'experience', label: 'Experience penalty', detail: `${num(b.candidate_experience)} yrs against ${num(b.required_experience)} yrs required`, points: -num(b.experience_penalty) });
  }
  if (num(b.education_penalty) > 0) {
    rows.push({ key: 'education', label: 'Education penalty', detail: 'No degree found where the requirement asks for one', points: -num(b.education_penalty) });
  }
  return rows.map((r) => ({ ...r, points: Number(r.points.toFixed(1)), text: signed(r.points) }));
}

// Resume skills next to the JD's matched and still-missing required skills.
export function skillComparison(resumeSkills, breakdown) {
  const matched = breakdown?.matched_skills || [];
  const missing = breakdown?.missing_skills || [];
  return { resumeSkills: resumeSkills || [], matched, missing, hasJdSkills: matched.length + missing.length > 0 };
}
