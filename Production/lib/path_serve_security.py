"""Path resolution for /files and staging serves (CodeQL py/path-injection).

Central gate: realpath + separator-anchored containment before open/read.
"""
from __future__ import annotations

import os
from pathlib import Path

from lib.paths import DROPBOX_ROOT


def _repo_root_str() -> str:
    # production_server uses _MN_REPO_ROOT; mirror via paths module parent.
    from pathlib import Path as _P

    return os.path.realpath(str(_P(__file__).resolve().parents[2]))


def is_realpath_under_any_root(real_path: str, roots: list[str]) -> bool:
    for root in roots:
        if not root:
            continue
        if real_path == root or real_path.startswith(root + os.sep):
            return True
    return False


def safe_realpath_under_serve_roots(cand: str) -> str | None:
    """Return os.path.realpath(cand) iff file exists under an allowed serve root."""
    if not isinstance(cand, str) or not cand:
        return None
    try:
        drop_root = os.path.realpath(str(DROPBOX_ROOT))
        repo_root = os.path.realpath(_repo_root_str())
        roots = [drop_root, repo_root]
        try:
            # Local APFS hot media (playback cache + trim scratch) off Dropbox.
            import sys
            from pathlib import Path as _P

            tools = _P(__file__).resolve().parents[1] / "tools"
            if str(tools) not in sys.path:
                sys.path.insert(0, str(tools))
            from media_hot_root import media_hot_serve_roots  # noqa: PLC0415

            roots.extend(media_hot_serve_roots())
        except Exception:
            pass
        real_path = os.path.realpath(cand)
        if not os.path.isfile(real_path):
            return None
        if not is_realpath_under_any_root(real_path, roots):
            return None
        return os.path.realpath(real_path)
    except OSError:
        return None


def reject_path_traversal_segments(rel: str) -> None:
    """Reject .. and absolute segments in client-relative paths."""
    if not rel or not isinstance(rel, str):
        raise ValueError("empty path")
    p = Path(rel)
    if p.is_absolute():
        return
    for part in p.parts:
        if part in ("..", "") or part.startswith("\x00"):
            raise ValueError(f"path traversal rejected: {rel!r}")


def require_basename_under_dir(filename: str, parent_dir: Path) -> Path:
    """Reject traversal; return resolved file under parent_dir (direct child)."""
    if not filename or "/" in filename or "\\" in filename or ".." in filename or "\x00" in filename:
        raise ValueError(f"invalid filename: {filename!r}")
    parent = parent_dir.resolve()
    target = (parent / Path(filename).name).resolve()
    if target.parent != parent:
        raise ValueError(f"path escapes directory: {filename!r}")
    return target
