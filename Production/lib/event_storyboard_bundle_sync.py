"""EVENT_SWITCH_STORYBOARD_BUNDLE_SYNC_V1 — copy canonical dist bundle into Event_N.

Ensures dropdown / provision never lands on an event folder missing
``storyboard_v59_prod.html`` or serving a stale pre-deploy copy.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from lib.paths import TOOLING_ROOT

CODE = "EVENT_SWITCH_STORYBOARD_BUNDLE_SYNC_V1"
TARGET_NAME = "storyboard_v59_prod.html"


@dataclass(frozen=True)
class BundleSyncResult:
    ok: bool
    event_dir: Path
    target: Path
    copied: bool
    source: str | None = None
    skipped_reason: str | None = None
    error: str | None = None

    def to_json(self) -> dict:
        return {
            "ok": self.ok,
            "code": CODE,
            "event_dir": str(self.event_dir),
            "target": str(self.target),
            "copied": self.copied,
            "source": self.source,
            "skipped_reason": self.skipped_reason,
            "error": self.error,
        }


def _canonical_bundle_path() -> Path:
    return TOOLING_ROOT / "Production" / "tools" / "storyboard-v2" / "dist" / "index.html"


def sync_event_storyboard_bundle(
    event_dir: Path,
    *,
    fallback_source: Path | None = None,
    force: bool = False,
) -> BundleSyncResult:
    """Copy canonical storyboard bundle into ``event_dir`` when missing or stale."""
    event_dir = Path(event_dir)
    target = event_dir / TARGET_NAME
    canonical = _canonical_bundle_path()

    source: Path | None = None
    if canonical.is_file():
        source = canonical
    elif fallback_source and fallback_source.is_file():
        source = fallback_source

    if source is None:
        if target.is_file():
            return BundleSyncResult(
                ok=True,
                event_dir=event_dir,
                target=target,
                copied=False,
                skipped_reason="target_exists_no_canonical",
            )
        return BundleSyncResult(
            ok=False,
            event_dir=event_dir,
            target=target,
            copied=False,
            error="no canonical bundle and no fallback source",
        )

    try:
        if not force and target.is_file():
            if target.stat().st_mtime >= source.stat().st_mtime and target.stat().st_size == source.stat().st_size:
                return BundleSyncResult(
                    ok=True,
                    event_dir=event_dir,
                    target=target,
                    copied=False,
                    source=str(source),
                    skipped_reason="target_fresh",
                )
        event_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return BundleSyncResult(
            ok=True,
            event_dir=event_dir,
            target=target,
            copied=True,
            source=str(source),
        )
    except OSError as exc:
        return BundleSyncResult(
            ok=False,
            event_dir=event_dir,
            target=target,
            copied=False,
            source=str(source),
            error=str(exc),
        )
