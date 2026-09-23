import csv
import io
import json
from typing import List, Dict, Any


def export_candidates_to_csv(candidates_data: List[Dict[str, Any]]) -> str:
    """Exports a list of candidate dictionaries to CSV string."""
    output = io.StringIO()
    fields = [
        "id", "candidate_name", "email", "phone", "years_experience",
        "education", "status", "skills", "uploaded_at", "match_score"
    ]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()

    for item in candidates_data:
        row = item.copy()
        if isinstance(row.get("skills"), list):
            row["skills"] = ", ".join(row["skills"])
        writer.writerow(row)

    return output.getvalue()


def export_candidates_to_json(candidates_data: List[Dict[str, Any]]) -> str:
    """Exports candidates list to pretty-printed JSON string."""
    return json.dumps(candidates_data, indent=2, default=str)
