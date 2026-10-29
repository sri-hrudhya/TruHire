---
version: 1
slug: "frontend-src-pages-jobdescriptionspage-jsx"
primary_target: "frontend/src/pages/JobDescriptionsPage.jsx"
related_targets: ["frontend/src/pages/SearchPage.jsx"]
---

# Surface brief: TruHire app shell, Requirements, Search

Mode: Operate. Users: recruiters, admins, hiring managers working at a desktop for hours.

## Direction contract
THESIS: The app is a newsroom assignment desk: requirements are stories on a desk, candidates are wire items, recruiters take assignments. It refuses the icon-in-box SaaS card grid and the blue-slate dashboard.
OWN-WORLD: Cool newsprint-grey ground (#EEF0EE light) with ink (#15191C); one wire-teal action colour (#0B6E5C light, lifted in dark); state marks instead of coloured pills: hollow = pending, filled = shortlisted, struck = not shortlisted. Source Serif 4 for names and page titles, Public Sans for UI, JetBrains Mono only for ids/data. Hairline rules, 4-6px radii, no card shadows; elevation by border only.
STORY: A recruiter sees which desk (category) they are in, scans ranked items fast, reads why each ranked, sets a mark, assigns or comments, and moves on.
FIRST VIEWPORT: Left rail nav (collapsible). Top of Requirements: page title + one horizontal row of desks (All, Java, GenAI, Camunda, Pega, Others) with counts, underline for active. Below: two panes, requirement list (slug, title, age) and the selected requirement with its ranked matches as dense rows (slug, serif name, one-line dek, score, mark, assignee initials). Primary action (New requirement) top right.
FORM: Newsroom assignment desk, position 5 of my grounded list; seed:c23c2360ed5864cc.
SIGNATURE MOVE: the status mark vocabulary plus slug-and-dek rows; fixed columns never reflow (kept from the split-flap challenger).
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
