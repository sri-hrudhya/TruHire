import hashlib
import os
from pathlib import Path
from typing import Tuple
from backend.config import settings


def ensure_storage_dir() -> Path:
    storage_path = Path(settings.STORAGE_DIR)
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


def compute_file_hash(file_bytes: bytes) -> str:
    """Compute SHA-256 hash of file content for exact duplicate detection."""
    return hashlib.sha256(file_bytes).hexdigest()


def save_upload_file(filename: str, file_bytes: bytes) -> Tuple[str, str]:
    """
    Saves the file to the storage directory.
    Returns (file_url_or_path, file_hash).
    """
    storage_dir = ensure_storage_dir()
    file_hash = compute_file_hash(file_bytes)
    
    # Sanitize filename
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
    target_filename = f"{file_hash[:12]}_{safe_filename}"
    target_path = storage_dir / target_filename

    with open(target_path, "wb") as f:
        f.write(file_bytes)

    # Return relative URL or path
    return f"/uploads/{target_filename}", file_hash
