"""Secure avatar upload helpers (extension + content sniffing + path isolation)."""

from __future__ import annotations

import secrets
from pathlib import Path

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

ALLOWED_AVATAR_EXT = frozenset({"png", "jpg", "jpeg", "webp"})
AVATAR_MAX_BYTES = 2 * 1024 * 1024  # 2 MB

# Magic-byte signatures (prefix match).
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "webp": (b"RIFF",),  # also check WEBP at offset 8
}


class AvatarUploadError(ValueError):
    """Invalid avatar upload."""


def avatar_storage_dir(repo_root: Path) -> Path:
    """Static directory isolated from executable code."""
    path = repo_root / "static" / "uploads" / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    # Prevent directory listing surprises; keep a gitkeep.
    keep = path / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")
    return path


def _ext_of(filename: str) -> str:
    name = secure_filename(filename or "")
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower()


def validate_and_store_avatar(
    upload: FileStorage,
    *,
    user_id: int,
    repo_root: Path,
) -> str:
    """Validate and save avatar. Returns relative path under ``static/``."""
    if upload is None or not upload.filename:
        raise AvatarUploadError("No file uploaded.")

    ext = _ext_of(upload.filename)
    if ext not in ALLOWED_AVATAR_EXT:
        raise AvatarUploadError("Only PNG, JPG, and WebP images are allowed.")

    raw = upload.read(AVATAR_MAX_BYTES + 1)
    if not raw:
        raise AvatarUploadError("Empty file.")
    if len(raw) > AVATAR_MAX_BYTES:
        raise AvatarUploadError("Avatar must be 2 MB or smaller.")

    if not _looks_like_image(raw, ext):
        raise AvatarUploadError("File content does not match an allowed image type.")

    dest_dir = avatar_storage_dir(repo_root)
    token = secrets.token_hex(16)
    safe_name = secure_filename(f"u{int(user_id)}_{token}.{ext}")
    dest = dest_dir / safe_name
    dest.write_bytes(raw)
    # Relative URL path served by Flask static.
    return f"uploads/avatars/{safe_name}"


def _looks_like_image(data: bytes, ext: str) -> bool:
    sigs = _SIGNATURES.get(ext) or ()
    if not any(data.startswith(sig) for sig in sigs):
        return False
    if ext == "webp":
        return len(data) >= 12 and data[8:12] == b"WEBP"
    return True
