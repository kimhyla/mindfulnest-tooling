#!/usr/bin/env python3
"""Heal Benson Kling Element frontal + Event_5 locked beat refs (ELEMENT_CHAR_REF_AUTHORITY_V1).

Promotes canonical brown Benson pose to Element frontal_image on Dropbox runtime registry,
re-registers Wavespeed Element, and aligns Event_5 Benson beat sidecar refs.

Usage:
  MN_PROD_ROOT="$HOME/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production" \\
    python3 Production/scripts/heal_benson_element_frontal_authority.py

  MN_BEATGEN_DB_PATH=~/.mindfulnest/state/beatgen_event5.db \\
    python3 Production/scripts/heal_benson_element_frontal_authority.py --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD_SCRIPTS = HERE
PROD_ROOT = HERE.parent
TOOLS = PROD_ROOT / "tools"
if str(PROD_ROOT) not in sys.path:
    sys.path.insert(0, str(PROD_ROOT))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from lib.credential_store import get_secret  # noqa: E402
from tools import beat_generator as bg  # noqa: E402
from tools import kling_character_registry as reg  # noqa: E402

CANONICAL_REL = "Benson/poses/benson_pose_neutral.png"
BENSON_BEAT_IDS = (
    "bg_arc1_event5_pre_beat_01",
    "bg_arc1_event5_pre_beat_03",
    "bg_arc1_event5_pre_beat_12",
)
GRAY_STEMS = frozenset(
    {
        "chatgpt_image_jul_3_2026_11_28_44_pm.png",
        "chatgpt image jul 3, 2026, 11_28_44 pm.png",
    }
)


def _sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _default_prod_root() -> Path:
    env = os.environ.get("MN_PROD_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    dropbox = Path.home() / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
    return dropbox.resolve()


def _default_db_path() -> Path:
    raw = os.environ.get("MN_BEATGEN_DB_PATH", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / ".mindfulnest" / "state" / "beatgen_event5.db"


def _is_gray_ref(path: str) -> bool:
    name = Path(path).name.lower().replace(",", "").replace(" ", "_")
    return any(stem.replace(" ", "_") in name for stem in GRAY_STEMS)


def heal_benson(*, dry_run: bool = False) -> dict:
    prod = _default_prod_root()
    canonical = (prod / CANONICAL_REL).resolve()
    if not canonical.is_file():
        raise SystemExit(f"FATAL: canonical Benson pose missing: {canonical}")

    reg.set_prod_root(prod)
    entry = reg.get_character_entry("Benson") or {}
    before_frontal = str(entry.get("frontal_image") or "")
    before_element = str(entry.get("element_id") or "")

    report: dict = {
        "prod_root": str(prod),
        "canonical_rel": CANONICAL_REL,
        "canonical_sha16": _sha16(canonical),
        "before_frontal": before_frontal,
        "before_element_id": before_element,
        "dry_run": dry_run,
    }

    if dry_run:
        report["action"] = "dry_run"
        return report

    ws_key = get_secret("WAVESPEED_API_KEY")
    out = reg.add_element_pose("Benson", canonical, ws_key, promote_frontal=True)
    report["registry_action"] = out

    entry_after = reg.get_character_entry("Benson") or {}
    report["after_frontal"] = str(entry_after.get("frontal_image") or "")
    report["after_element_id"] = str(entry_after.get("element_id") or "")

    frontal_after = reg.resolve_frontal_abs_path("Benson")
    if not frontal_after or _sha16(Path(frontal_after)) != report["canonical_sha16"]:
        raise SystemExit(
            f"FATAL: frontal promote failed — frontal={frontal_after!r} "
            f"sha={_sha16(Path(frontal_after)) if frontal_after else 'NA'}"
        )

    db_path = _default_db_path()
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    beat_updates: list[dict] = []
    new_element_id = str(entry_after.get("element_id") or "")
    now = datetime.now(timezone.utc).isoformat()
    for beat_id in BENSON_BEAT_IDS:
        row = conn.execute(
            "SELECT beat_json FROM beats WHERE beat_id=?", (beat_id,),
        ).fetchone()
        if not row:
            continue
        beat = json.loads(row[0])
        if (beat.get("speaker") or "").strip() != "Benson":
            continue
        ref = beat.get("reference_image") if isinstance(beat.get("reference_image"), dict) else {}
        old_path = str(ref.get("abs_path") or "")
        if old_path and not _is_gray_ref(old_path):
            beat_updates.append({"beat_id": beat_id, "skipped": "already_canonical", "old": old_path})
            continue
        beat["reference_image"] = bg._ref_dict_from_path(str(canonical))  # noqa: SLF001
        beat["reference_image_locked"] = True
        o3q = beat.get("o3_element_quality") if isinstance(beat.get("o3_element_quality"), dict) else {}
        o3q["element_id"] = new_element_id
        beat["o3_element_quality"] = o3q
        beat["element_char_ref_ok"] = True
        conn.execute(
            """
            UPDATE beats SET beat_json=?, revision=revision+1, updated_at=?
            WHERE beat_id=?
            """,
            (json.dumps(beat, ensure_ascii=False, separators=(",", ":"), sort_keys=True), now, beat_id),
        )
        beat_updates.append(
            {
                "beat_id": beat_id,
                "old_ref": Path(old_path).name if old_path else None,
                "new_ref": canonical.name,
                "element_id": new_element_id,
            }
        )
    conn.commit()
    conn.close()
    report["beat_updates"] = beat_updates
    report["db_path"] = str(db_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = heal_benson(dry_run=args.dry_run)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
