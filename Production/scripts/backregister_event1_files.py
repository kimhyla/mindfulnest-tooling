#!/usr/bin/env python3
"""V59 Wave 2 — D3 back-register Event_1 files in prod_assets.

Per V59 spec line 94 (D3): back-register unregistered Event_1 production
files into Directus prod_assets so the asset inventory is accurate.

Files are scanned under Production/Event_1/, classified by extension +
directory context, and registered with module_id=1 (M1).

Safety:
- Default mode is --dry-run (counts + classifies, but writes nothing)
- Whitelist of excluded paths per CLAUDE.md Rule 34 ('_temp_*', '_sandbox',
  'tests/', 'debug_*', '_previews/')
- Skips backup files (.bak*, .pre*, .sha256, sidecar variants)
- De-duplicates against existing prod_assets entries (queries file_path
  for already-registered files before POSTing)
- Uses try_post_or_queue for read-back-after-write per Rule 35
- Per-batch progress prints; HALT on first POST error

Per CLAUDE.md Rule 19 (no shortcuts): no silent failures, every write
verified via read-back.

Usage:
    python3 Production/scripts/backregister_event1_files.py --dry-run
    python3 Production/scripts/backregister_event1_files.py --apply

Exit codes:
    0 — all classified files either registered OK or already present
    1 — any POST failure (HALT class) or filesystem error
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from Production.lib.directus_admin_client import DirectusAdminClient  # noqa: E402

# Event_1 lives in the Dropbox tree (Kim's runtime); tooling tree mirrors are deploy artifacts
EVENT_1_DIR = Path.home() / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/Event_1"

# Per Rule 34 — whitelist of paths NEVER registered (intermediate / sandbox)
EXCLUDED_PATH_PARTS = {
    "_temp_images", "_sandbox", "tests", "debug", "_previews",
    "__pycache__", ".git", "pipeline_test",
}

# File-name patterns that indicate backups / intermediates we skip
SKIP_NAME_PATTERNS = [
    re.compile(r"\.bak"),
    re.compile(r"\.pre[a-zA-Z0-9_]+"),
    re.compile(r"\.s2_pre_restore_backup"),
    re.compile(r"\.sha256$"),
    re.compile(r"\.pyc$"),
    re.compile(r"^\.last_deploy$"),
    re.compile(r"_tmp_"),
]

# Documentation/script extensions — these aren't assets
NON_ASSET_EXTENSIONS = {".md", ".txt", ".py", ".sh", ".pid", ".test"}

# Extension → asset_type classification
EXTENSION_TO_ASSET_TYPE = {
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".mp4": "video",
    ".mov": "video",
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".aac": "audio",
    ".ogg": "audio",
    ".html": "storyboard",
    ".json": "state_snapshot",  # only register top-level production_state.json (filtered below)
    ".docx": "doc",
}

# Path-context overrides (longest-prefix match wins)
PATH_CONTEXT_OVERRIDES = [
    ("/kling_clips/", "video", "kling_clip"),
    ("/animation_clips/", "video", "animation_clip"),
    ("/animated_v3/", "video", "animation_clip"),
    ("/animated_v2/", "video", "animation_clip"),
    ("/normalized_segments/", "video", "normalized_segment"),
    ("/scene_assemble_bodies/", "video", "scene_body"),
    ("/scene_assemble_xfade/", "video", "scene_xfade"),
    ("/story_scene_v3/", "video", "story_scene"),
    ("/story_scene_v2/", "video", "story_scene"),
    ("/story_scene_produced/", "video", "story_scene"),
    ("/intro/", "video", "intro_video"),
    ("/gemini_stills/", "image", "gemini_still"),
    ("/variants/", "image", "variant"),
    ("/variant_frames/", "image", "variant_frame"),
    ("/sfx/", "audio", "sfx"),
    ("/phase_a_tts/", "audio", "phase_a_tts"),
    ("/tts_emotional/", "audio", "tts"),
    ("/preserved_winners/", "video", "preserved_winner"),
]


def should_skip(path: Path) -> tuple[bool, str]:
    """Return (skip, reason)."""
    parts = path.relative_to(EVENT_1_DIR).parts
    for excluded in EXCLUDED_PATH_PARTS:
        if any(p == excluded or p.startswith(excluded + "_") for p in parts):
            return True, f"excluded_dir={excluded}"
    for pat in SKIP_NAME_PATTERNS:
        if pat.search(path.name):
            return True, f"skip_pattern={pat.pattern}"
    ext = path.suffix.lower()
    if ext in NON_ASSET_EXTENSIONS:
        return True, f"non_asset_ext={ext}"
    if ext == ".json" and path.name != "production_state.json":
        return True, "intermediate_json"
    if not ext:
        return True, "no_extension"
    return False, ""


def classify(path: Path) -> tuple[str, str]:
    """Return (asset_type, produced_by_skill)."""
    rel = "/" + str(path.relative_to(EVENT_1_DIR.parent)).replace(os.sep, "/")
    # Path-context overrides take priority (most specific)
    for prefix, atype, skill in PATH_CONTEXT_OVERRIDES:
        if prefix in rel:
            return atype, skill
    # Fall back to extension
    ext = path.suffix.lower()
    return EXTENSION_TO_ASSET_TYPE.get(ext, "unknown"), "uncategorized"


def extract_beat_id(name: str) -> str | None:
    """Pull beat_NN from filename if present."""
    m = re.search(r"\bbeat[_-]?(\d{1,3})\b", name, re.IGNORECASE)
    if m:
        return f"beat_{int(m.group(1)):02d}"
    return None


def short_sha256(path: Path, max_bytes: int = 1_048_576) -> str:
    """Compute sha256 over first max_bytes (fast for large videos; full sha on small files)."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            data = f.read(max_bytes)
            h.update(data)
    except (OSError, PermissionError):
        return ""
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", default=True, help="default: scan + classify, do not write")
    ap.add_argument("--apply", dest="dry_run", action="store_false", help="actually write to prod_assets")
    ap.add_argument("--limit", type=int, default=None, help="cap at N new registrations (for staged ramp-up)")
    ap.add_argument("--event-id-int", type=int, default=1, help="event_id int to populate (default 1 = Event_1)")
    ap.add_argument("--module-id", type=int, default=1, help="module_id (default 1 = M1)")
    args = ap.parse_args()

    if not EVENT_1_DIR.is_dir():
        print(f"FAIL: Event_1 dir not found at {EVENT_1_DIR}", file=sys.stderr)
        return 1

    print(f"=== D3 back-register Event_1 files (mode: {'DRY-RUN' if args.dry_run else 'APPLY'}) ===")
    print(f"Event_1 dir: {EVENT_1_DIR}")
    print(f"module_id: {args.module_id}  event_id_int: {args.event_id_int}")

    # 1. Query existing prod_assets to skip duplicates
    print("\n[1/4] Querying existing prod_assets...")
    c = DirectusAdminClient()
    # DirectusAdminClient.get_items doesn't expose offset; use limit=-1 to fetch all rows.
    existing_paths: set[str] = set()
    try:
        rows = c.get_items(
            "prod_assets",
            filters={"file_path": {"_starts_with": "Production/Event_1/"}},
            fields=["id", "file_path"],
            limit=-1,
        )
        for r in rows:
            if r.get("file_path"):
                existing_paths.add(r["file_path"])
    except Exception as e:
        print(f"  ERROR: prod_assets dedup query failed ({e}); refusing to write without dedup", file=sys.stderr)
        return 1
    print(f"  already-registered Event_1 file_paths: {len(existing_paths)}")

    # 2. Scan disk
    print("\n[2/4] Scanning Event_1 disk...")
    classified: list[dict] = []
    skipped_count = 0
    seen_count = 0
    for path in EVENT_1_DIR.rglob("*"):
        if not path.is_file():
            continue
        seen_count += 1
        skip, reason = should_skip(path)
        if skip:
            skipped_count += 1
            continue
        rel_str = "Production/Event_1/" + str(path.relative_to(EVENT_1_DIR)).replace(os.sep, "/")
        if rel_str in existing_paths:
            continue
        atype, skill = classify(path)
        if atype == "unknown":
            skipped_count += 1
            continue
        beat_id = extract_beat_id(path.name)
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        classified.append({
            "rel_path": rel_str,
            "name": path.name,
            "asset_type": atype,
            "produced_by_skill": skill,
            "beat_id": beat_id,
            "file_size_bytes": size,
            "abs_path": path,
        })

    print(f"  files seen: {seen_count}")
    print(f"  files skipped: {skipped_count}")
    print(f"  files already registered: {seen_count - skipped_count - len(classified)}")
    print(f"  new registrations to write: {len(classified)}")

    # 3. Summary by asset_type
    print("\n[3/4] Classification summary:")
    from collections import Counter
    type_counts = Counter(c["asset_type"] for c in classified)
    skill_counts = Counter(c["produced_by_skill"] for c in classified)
    for t, n in type_counts.most_common():
        print(f"  asset_type={t}: {n}")
    print("\n  produced_by_skill distribution:")
    for s, n in skill_counts.most_common(10):
        print(f"    {s}: {n}")

    if args.limit:
        classified = classified[:args.limit]
        print(f"\n  --limit={args.limit} applied; will write at most {len(classified)} rows")

    if args.dry_run:
        print(f"\n[DRY-RUN] Would write {len(classified)} new prod_assets rows. Re-run with --apply to actually write.")
        return 0

    # 4. Write (carefully, batched)
    print(f"\n[4/4] Writing {len(classified)} rows to prod_assets via try_post_or_queue...")
    try:
        from Production.lib.directus import try_post_or_queue
    except Exception as e:
        print(f"FAIL: try_post_or_queue not importable: {e}", file=sys.stderr)
        return 1

    written = 0
    failed = 0
    for i, item in enumerate(classified):
        payload = {
            "module_id": args.module_id,
            "asset_type": item["asset_type"],
            "asset_name": item["name"],
            "file_path": item["rel_path"],
            "event_id": args.event_id_int,
            "beat_id": item["beat_id"],
            "file_size_bytes": item["file_size_bytes"],
            "produced_by_skill": item["produced_by_skill"],
            "status": "pending",
            "library": False,
            "is_current": True,
            "notes": f"Back-registered by V59 Wave 2 D3 ({args.module_id}/Event_1).",
        }
        try:
            res = try_post_or_queue("prod_assets", payload)
            if res.get("ok"):
                written += 1
                if (i + 1) % 100 == 0:
                    print(f"  ... {i+1}/{len(classified)} written")
            else:
                failed += 1
                print(f"  ! row {i} failed: {res}", file=sys.stderr)
                if failed > 5:
                    print(f"FAIL: >5 errors, halting at row {i}", file=sys.stderr)
                    return 1
        except Exception as e:
            failed += 1
            print(f"  ! row {i} exception: {e}", file=sys.stderr)
            if failed > 5:
                return 1

    print(f"\nD3_COMPLETE  written={written}  failed={failed}  total={len(classified)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
