"""Path containment helpers for server_handlers (CodeQL py/path-injection).

Uses separator-anchored realpath checks (same idiom as production_server.py
and CODEQL_PATH_INJECTION_NATIVE_PATTERN_REFACTOR_V1). Callers should assign
the returned path immediately before open/subprocess sinks.
"""
from __future__ import annotations

import os
from pathlib import Path

from lib.paths import DROPBOX_ROOT

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".m4v"})
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | frozenset({".wav", ".mp3", ".m4a", ".aac"})


def project_root_str() -> str:
    return os.path.realpath(str(DROPBOX_ROOT))


def is_realpath_under_root(real_path: str, root: str) -> bool:
    return real_path == root or real_path.startswith(root + os.sep)


def require_realpath_under_project(raw: str) -> str:
    """Return os.path.realpath(raw) iff under DROPBOX_ROOT; else raise ValueError."""
    root = project_root_str()
    try:
        resolved = os.path.realpath(raw)
    except OSError as exc:
        raise ValueError(f"path validation failed: {raw!r}") from exc
    if not is_realpath_under_root(resolved, root):
        raise ValueError(f"path outside project root: {raw!r}")
    return resolved


def require_resolved_under_root(resolved: Path, root: Path | None = None) -> Path:
    """Ensure an already-resolved Path stays under project root."""
    root_p = (root or Path(DROPBOX_ROOT)).resolve()
    try:
        resolved.relative_to(root_p)
    except ValueError as exc:
        raise ValueError(f"path outside project root: {resolved}") from exc
    return resolved


def require_path_under_anchor(raw: str, anchor: Path) -> Path:
    """Resolve raw (relative to anchor if needed) and confine under anchor."""
    p = Path(raw)
    resolved = (p if p.is_absolute() else anchor / p).resolve()
    anchor_r = anchor.resolve()
    try:
        resolved.relative_to(anchor_r)
    except ValueError as exc:
        raise ValueError(f"path outside allowed root: {raw!r}") from exc
    return resolved


def require_media_under_project(
    raw: str,
    *,
    anchor: Path | None = None,
    extensions: frozenset[str] = MEDIA_EXTENSIONS,
) -> str:
    """Project containment + media extension whitelist; returns realpath string."""
    if anchor is not None:
        resolved = str(require_path_under_anchor(raw, anchor))
    else:
        resolved = require_realpath_under_project(raw)
    ext = os.path.splitext(resolved)[1].lower()
    if ext not in extensions:
        raise ValueError(f"unsupported media extension: {ext!r}")
    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"file not found: {raw!r}")
    return resolved


def require_basename_under_dir(filename: str, parent_dir: Path) -> Path:
    """Reject traversal; return resolved file under parent_dir (direct child)."""
    if not filename or "/" in filename or "\\" in filename or ".." in filename or "\x00" in filename:
        raise ValueError(f"invalid filename: {filename!r}")
    parent = parent_dir.resolve()
    target = (parent / Path(filename).name).resolve()
    if target.parent != parent:
        raise ValueError(f"path escapes directory: {filename!r}")
    return target
