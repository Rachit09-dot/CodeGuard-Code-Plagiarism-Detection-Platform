from __future__ import annotations

import os
import uuid
from pathlib import Path

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", Path(__file__).resolve().parents[2] / "storage"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def save_uploaded_file(file_name: str, content: bytes, directory: str = "uploads") -> tuple[str, str]:
    target_dir = UPLOAD_DIR / directory
    target_dir.mkdir(parents=True, exist_ok=True)

    original_name = (file_name or "upload.py").strip()
    if not original_name:
        raise ValueError("No Python file name was provided.")
    if original_name in {".", ".."} or "/" in original_name or "\\" in original_name:
        raise ValueError(f"Unsupported file type for '{original_name}'. Only Python (.py) files are allowed.")

    safe_name = Path(original_name).name
    if safe_name != original_name or safe_name in {".", ".."} or not safe_name:
        raise ValueError(f"Unsupported file type for '{original_name}'. Only Python (.py) files are allowed.")

    safe_storage_name = f"{uuid.uuid4().hex}_{Path(safe_name).name}"
    file_path = target_dir / safe_storage_name
    with open(file_path, "wb") as handle:
        handle.write(content)
    return str(file_path), safe_name
