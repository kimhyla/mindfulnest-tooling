"""Beat Gen sidecar / disk health checks — S3 (H1) + S5 (H2) sibling program."""
from __future__ import annotations

import re
from pathlib import Path

_CONFLICT_RE = re.compile(r"conflicted copy", re.I)


def warn_dropbox_conflict_copies(event_dir: Path | str) -> list[str]:
    """Return paths of Dropbox conflict copies under event dir; log-ready strings."""
    root = Path(event_dir).expanduser().resolve()
    if not root.is_dir():
        return []
    found: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _CONFLICT_RE.search(path.name):
            found.append(str(path))
    return found


def find_orphan_kling_clips(
    event_dir: Path | str,
    *,
    sidecar_paths: set[str] | None = None,
) -> list[str]:
    """MP4s under kling_o3_clips/ not referenced in sidecar_paths (warn-only)."""
    root = Path(event_dir).expanduser().resolve()
    clips = root / "kling_o3_clips"
    if not clips.is_dir():
        return []
    known = {str(Path(p).expanduser().resolve()) for p in (sidecar_paths or set()) if p}
    orphans: list[str] = []
    for mp4 in clips.rglob("*.mp4"):
        resolved = str(mp4.resolve())
        if resolved not in known:
            orphans.append(resolved)
    return orphans
