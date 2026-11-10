"""Paths built from client-supplied file names that cannot leave their directory."""

from __future__ import annotations

from pathlib import Path


class UnsafePathError(ValueError):
    pass


def safe_child_path(base: Path | str, filename: str) -> Path:
    """Resolved path of ``filename`` directly inside ``base``.

    Raises UnsafePathError for anything that is not a plain file name: directory parts,
    ``..``, absolute paths, backslashes, NUL bytes, or a name whose resolved location
    (symlinks followed) is not directly inside ``base``.
    """
    name = str(filename or "")
    if (
        not name
        or "\x00" in name
        or "\\" in name
        or name in {".", ".."}
        or Path(name).is_absolute()
        or Path(name).name != name
    ):
        raise UnsafePathError("Invalid file name.")
    root = Path(base).resolve()
    target = (root / name).resolve()
    if target.parent != root:
        raise UnsafePathError("Invalid file name.")
    return target


def upload_basename(filename: str, fallback: str = "upload") -> str:
    """Last component of a browser-supplied upload name (``C:\\fakepath\\a.docx`` -> ``a.docx``)."""
    name = Path(str(filename or "").replace("\\", "/").replace("\x00", "")).name
    return fallback if name in {"", ".", ".."} else name
