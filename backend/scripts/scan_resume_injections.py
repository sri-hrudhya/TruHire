"""
Re-screen every stored resume for hidden or embedded AI instructions.

    python -m backend.scripts.scan_resume_injections            # dry run: report only
    python -m backend.scripts.scan_resume_injections --delete   # remove flagged candidates

Uses the same screen as ingestion (backend/services/ingestion/injection_screen.py), on the
original stored file when it still exists (needed to see hidden text) plus the stored
resume text. Deletion goes through the normal candidate removal path (vectors, OpenSearch
document, file, review statuses) and every deletion is written to the AI audit trail.
"""
import argparse
import sys

from backend.database import SessionLocal
from backend.models import Candidate
from backend.services.common import ai_audit
from backend.services.ingestion.injection_screen import screen_resume
from backend.services.ingestion.storage import resolve_stored_file


def scan(db):
    flagged = []
    for cand in db.query(Candidate).order_by(Candidate.uploaded_at.asc()).all():
        path = resolve_stored_file(cand.resume_file_url)
        file_bytes = path.read_bytes() if path else b""
        result = screen_resume(cand.original_filename or (path.name if path else ""), file_bytes, cand.resume_text or "")
        if result.blocked:
            flagged.append((cand, result))
    return flagged


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--delete", action="store_true", help="delete flagged candidates (default: report only)")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        total = db.query(Candidate).count()
        flagged = scan(db)
        print(f"Scanned {total} candidate(s); {len(flagged)} flagged.")
        for cand, result in flagged:
            excerpt = (result.hidden_text or "")[:160]
            print(f"- {cand.display_id or cand.id} | {cand.candidate_name} | {cand.original_filename} | {result.summary()}")
            if excerpt:
                print(f"    hidden text: {excerpt!r}")

        if not args.delete or not flagged:
            if flagged:
                print("Dry run: nothing deleted. Re-run with --delete to remove these candidates.")
            return 0

        from backend.routers.candidates import _remove_candidate, invalidate_candidate_cache
        for cand, result in flagged:
            ai_audit.record(provider="injection_screen", feature="resume_screen", status="blocked",
                            prompt=cand.resume_text, output=result.hidden_text,
                            details={"action": "deleted_existing_candidate", "candidate_id": cand.id,
                                     "display_id": cand.display_id, "reasons": result.reasons})
            _remove_candidate(cand, db)
        db.commit()
        invalidate_candidate_cache()
        ai_audit.flush()
        print(f"Deleted {len(flagged)} candidate(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
