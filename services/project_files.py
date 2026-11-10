"""Reads of an assignment project's own stored files.

A file record's ``storage_path`` (and an image's) is data from the project JSON, never a
trusted location. It is only ever opened one component at a time under
``<storage root>/<project id>/files`` with ``O_NOFOLLOW``, and the opened object must be a
regular file, so checking and reading always concern the same filesystem object.

Server-written outputs (the delivery package and the Format Engine DOCX) are read the same
way, but only as a single file directly inside ``<storage root>/<project id>/<area>``.
"""

from __future__ import annotations

import errno
import logging
import os
import re
import stat
from pathlib import PurePosixPath
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 64 * 1024 * 1024

FILE_MISSING = "FILE_MISSING"
FILE_UNAVAILABLE = "FILE_UNAVAILABLE"
FILE_TOO_LARGE = "FILE_TOO_LARGE"
FOREIGN_RECORD = "FOREIGN_RECORD"
INVALID_PROJECT = "INVALID_PROJECT"
NOT_A_FILE = "NOT_A_FILE"
OUTSIDE_PROJECT = "OUTSIDE_PROJECT"
UNSAFE_PATH = "UNSAFE_PATH"
UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"

FILES_AREA = "files"
DELIVERY_AREA = "delivery"
FORMATTED_AREA = "formatted"
_OUTPUT_AREAS = (DELIVERY_AREA, FORMATTED_AREA)

_PROJECT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_ENCODED_RE = re.compile(r"%(?:2e|2f|5c|00)", re.IGNORECASE)
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_LEGACY_PREFIX = ("data", "projects")
_MAX_PATH_CHARS = 4096
_MAX_NAME_CHARS = 255

_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_SUPPORTED = (
    os.name == "posix"
    and os.open in os.supports_dir_fd
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY")
)


class ProjectFileDenied(Exception):
    """The record does not name a readable regular file of this project."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _deny(code: str, project_id: Any = None) -> ProjectFileDenied:
    if code != FILE_MISSING:
        logger.warning("project file denied project_id=%r code=%s", str(project_id)[:80], code)
    return ProjectFileDenied(code)


def _storage_root() -> str:
    from services.assignment_project.paths import assignment_storage_root

    return str(assignment_storage_root())


def _root(root: Any) -> str:
    return os.path.realpath(os.fspath(root)) if root is not None else _storage_root()


def _scope(project_id: Any, area: str = FILES_AREA) -> tuple[str, str]:
    if not isinstance(project_id, str) or not _PROJECT_ID_RE.fullmatch(project_id):
        raise _deny(INVALID_PROJECT, project_id)
    return project_id, area


def _unsafe_text(raw: str) -> bool:
    return bool(
        "\\" in raw
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in raw)
        or _DRIVE_RE.match(raw)
        or _ENCODED_RE.search(raw)
    )


def relative_parts(
    project_id: str, storage_path: Any, *, area: str = FILES_AREA, root: Any = None
) -> tuple[str, ...]:
    """Components of ``storage_path`` below the project's ``area`` directory.

    Accepts the absolute paths this server writes and the pre-July-2026 relative form
    ``data/projects/<project id>/<area>/...``; anything else is refused, never re-targeted.
    """
    scope = _scope(project_id, area)
    raw = storage_path
    if not isinstance(raw, str) or not raw or len(raw) > _MAX_PATH_CHARS:
        raise _deny(UNSAFE_PATH, project_id)
    if _unsafe_text(raw):
        raise _deny(UNSAFE_PATH, project_id)
    absolute = raw.startswith("/")
    segments = raw.split("/")[1:] if absolute else raw.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise _deny(UNSAFE_PATH, project_id)
    if absolute:
        prefix = (*PurePosixPath(_root(root)).parts[1:], *scope)
    else:
        prefix = (*_LEGACY_PREFIX, *scope)
    if len(segments) <= len(prefix) or tuple(segments[: len(prefix)]) != prefix:
        raise _deny(OUTSIDE_PROJECT, project_id)
    return tuple(segments[len(prefix) :])


def validate_storage_path(project_id: str, storage_path: Any) -> str:
    """``storage_path`` unchanged when it names a location inside the project's files directory."""
    relative_parts(project_id, storage_path)
    return storage_path


def record_storage_path(project_id: str, record: Any) -> str:
    """``storage_path`` of a file record or image entry, refusing records of another project."""
    if isinstance(record, dict):
        owner, path = record.get("project_id"), record.get("storage_path")
    else:
        owner, path = getattr(record, "project_id", None), getattr(record, "storage_path", None)
    if owner not in (None, "") and str(owner) != str(project_id):
        raise _deny(FOREIGN_RECORD, project_id)
    return str(path or "")


def _open_dir(project_id: str, parts: tuple[str, ...], root: Any = None) -> int:
    """Descriptor of ``root/parts...``, refusing any symlinked component."""
    if not _SUPPORTED:
        raise _deny(UNSUPPORTED_PLATFORM, project_id)
    try:
        dir_fd = os.open(_root(root), os.O_RDONLY | os.O_DIRECTORY | _CLOEXEC)
    except OSError:
        raise _deny(FILE_MISSING, project_id) from None
    try:
        for part in parts:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | _CLOEXEC, dir_fd=dir_fd)
            os.close(dir_fd)
            dir_fd = next_fd
    except OSError as exc:
        os.close(dir_fd)
        raise _deny(FILE_MISSING if exc.errno == errno.ENOENT else FILE_UNAVAILABLE, project_id) from None
    return dir_fd


def _open_parts(project_id: str, parts: tuple[str, ...], root: Any = None) -> int:
    dir_fd = _open_dir(project_id, parts[:-1], root)
    try:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | _CLOEXEC, dir_fd=dir_fd)
    except OSError as exc:
        raise _deny(FILE_MISSING if exc.errno == errno.ENOENT else FILE_UNAVAILABLE, project_id) from None
    finally:
        os.close(dir_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise _deny(NOT_A_FILE, project_id)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _read_fd(fd: int, project_id: str, max_bytes: int) -> bytes:
    with os.fdopen(fd, "rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise _deny(FILE_TOO_LARGE, project_id)
    return data


def _open_regular(project_id: str, storage_path: Any) -> int:
    return _open_parts(project_id, (*_scope(project_id), *relative_parts(project_id, storage_path)))


def read_project_file(project_id: str, storage_path: Any, *, max_bytes: int = DEFAULT_MAX_BYTES) -> bytes:
    """Bytes of the project's own regular file, or ProjectFileDenied."""
    return _read_fd(_open_regular(project_id, storage_path), project_id, max_bytes)


def read_project_record(project_id: str, record: Any, *, max_bytes: int = DEFAULT_MAX_BYTES) -> bytes:
    return read_project_file(project_id, record_storage_path(project_id, record), max_bytes=max_bytes)


def project_file_exists(project_id: str, storage_path: Any) -> bool:
    try:
        os.close(_open_regular(project_id, storage_path))
    except ProjectFileDenied:
        return False
    return True


def project_record_exists(project_id: str, record: Any) -> bool:
    try:
        return project_file_exists(project_id, record_storage_path(project_id, record))
    except ProjectFileDenied:
        return False


def storage_suffix(storage_path: Any) -> str:
    return PurePosixPath(str(storage_path or "")).suffix.lower()


def _output_scope(project_id: Any, area: str) -> tuple[str, str]:
    if area not in _OUTPUT_AREAS:
        raise _deny(UNSAFE_PATH, project_id)
    return _scope(project_id, area)


def _output_name(project_id: str, name: Any) -> str:
    if (
        not isinstance(name, str)
        or not name
        or len(name) > _MAX_NAME_CHARS
        or "/" in name
        or name in (".", "..")
        or _unsafe_text(name)
    ):
        raise _deny(UNSAFE_PATH, project_id)
    return name


def read_project_output(
    project_id: str, area: str, storage_path: Any, *, root: Any = None, max_bytes: int = DEFAULT_MAX_BYTES
) -> bytes:
    """Bytes of a regular file directly inside ``<root>/<project id>/<area>``; nothing else is read.

    ``root`` is the server's configured storage root (default: ``assignment_storage_root()``).
    """
    scope = _output_scope(project_id, area)
    rest = relative_parts(project_id, storage_path, area=area, root=root)
    if len(rest) != 1:
        raise _deny(OUTSIDE_PROJECT, project_id)
    return _read_fd(_open_parts(project_id, (*scope, rest[0]), root), project_id, max_bytes)


def read_project_output_name(
    project_id: str, area: str, name: Any, *, root: Any = None, max_bytes: int = DEFAULT_MAX_BYTES
) -> bytes:
    """Bytes of the regular file called ``name`` directly inside ``<root>/<project id>/<area>``."""
    scope = _output_scope(project_id, area)
    return _read_fd(_open_parts(project_id, (*scope, _output_name(project_id, name)), root), project_id, max_bytes)


def project_output_names(project_id: str, area: str, *, root: Any = None) -> list[str]:
    """Sorted names of the regular, non-symlink files directly inside ``<root>/<project id>/<area>``."""
    scope = _output_scope(project_id, area)
    if os.scandir not in os.supports_fd:
        return []
    try:
        dir_fd = _open_dir(project_id, scope, root)
    except ProjectFileDenied:
        return []
    try:
        with os.scandir(dir_fd) as entries:
            return sorted(entry.name for entry in entries if entry.is_file(follow_symlinks=False))
    finally:
        os.close(dir_fd)
