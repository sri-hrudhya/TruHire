import hashlib
import os
from pathlib import Path
from typing import Tuple, Optional
from backend.config import settings


def ensure_storage_dir() -> Path:
    storage_path = Path(settings.STORAGE_DIR)
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


def ensure_resume_storage_dir() -> Path:
    storage_path = Path(settings.RESUME_STORAGE_DIR)
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


def ensure_jd_storage_dir() -> Path:
    storage_path = Path(settings.JD_STORAGE_DIR)
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


def compute_file_hash(file_bytes: bytes) -> str:
    """Compute SHA-256 hash of file content for exact duplicate detection."""
    return hashlib.sha256(file_bytes).hexdigest()


def save_upload_file(filename: str, file_bytes: bytes, category: str = "resumes") -> Tuple[str, str]:
    """
    Saves the file to the dedicated storage directory based on category.
    category: "resumes" or "job_descriptions" (or "jd")
    Returns (file_url_or_path, file_hash).
    """
    ensure_storage_dir()
    is_jd = category in ("job_descriptions", "jd", "jds")
    if is_jd:
        target_dir = ensure_jd_storage_dir()
        prefix = "/uploads/job_descriptions"
    else:
        target_dir = ensure_resume_storage_dir()
        prefix = "/uploads/resumes"

    file_hash = compute_file_hash(file_bytes)

    # Sanitize filename
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
    if not safe_filename:
        safe_filename = "document.bin"
    target_filename = f"{file_hash[:12]}_{safe_filename}"
    target_path = target_dir / target_filename

    with open(target_path, "wb") as f:
        f.write(file_bytes)

    return f"{prefix}/{target_filename}", file_hash


def delete_file_by_url_or_path(file_url_or_path: Optional[str]) -> bool:
    """
    Safely delete an uploaded file from disk.
    Accepts web paths like '/uploads/resumes/...' or '/uploads/...' or absolute paths.
    """
    if not file_url_or_path:
        return False
    try:
        clean = file_url_or_path.replace("\\", "/").lstrip("/")
        if clean.startswith("uploads/"):
            rel_sub = clean[len("uploads/"):]
            target_path = Path(settings.STORAGE_DIR) / rel_sub
        else:
            target_path = Path(file_url_or_path)

        if target_path.exists() and target_path.is_file():
            target_path.unlink()
            return True
    except Exception as exc:
        print(f"Failed to delete file {file_url_or_path}: {exc}")
    return False
