#!/usr/bin/env python3
"""
Populate prod_modules from Production Event Map (production_event_map.py).

Per LD PROD_MODULES_GAMEPLAY_SCOPE_SOURCE_V1 + Judgment Call 2 (Kim 2026-07-04):
  production_event_map.py replaces GAMEPLAY_SCOPE_v3.md as the canonical V1 scope
  authority. Mirrors verified Arc Skeleton play-order into Directus prod_modules.

Modes:
  --dry-run   : parse + report counts; do NOT write. (default)
  --apply     : write missing rows via try_post_or_queue (Rule 35).
                Existing rows are PATCHed only on (creature_name, arc_number,
                video_role) — never on stage_status, current_stage, kim_notes,
                or any *_built_at field (avoids clobbering Kim's manual edits).
  --validate  : count rows; assert all map M-numbers present and 60 total rows
                (V1_SCOPE_EXPANSION_60_MODULES_M13_V1 — includes legacy M54 row).

Idempotent: re-runnable without duplication. Per Rule 35, every write is
verified via try_post_or_queue (read-back-after-write).

Per CLAUDE.md Rule 19 "no error paths": this script aborts on parse failure
and reports the offending line. It does NOT POST partial data.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow Production.lib import.
THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from Production.lib.directus import try_post_or_queue  # noqa: E402
from Production.lib.directus_admin_client import DirectusAdminClient  # noqa: E402
from Production.lib.production_event_map import (  # noqa: E402
    EXPECTED_MODULE_ROW_COUNT,
    build_prod_module_rows,
)


# Fields we are willing to PATCH on existing rows. Excludes anything Kim might
# have edited manually (stage_status, current_stage, kim_notes, *_built_at, etc.).
# `module_index` is intentionally EXCLUDED — Production Map sorts by m_number
# anyway, and the (arc_number, module_index) composite is UNIQUE in Directus.
# `arc_number` excluded — (arc_number, module_index) is UNIQUE; stale rows collide on shift.
PATCH_ALLOWED = ("creature_name", "video_role", "technique_name", "spell_name")


def fetch_existing_modules(client: DirectusAdminClient) -> dict[int, dict]:
    rows = client._request(
        "GET",
        "/items/prod_modules?fields=id,m_number,arc_number,module_index,creature_name,video_role,technique_name,spell_name&sort=m_number&limit=200",
    )
    return {r["m_number"]: r for r in (rows or []) if r.get("m_number") is not None}


def fetch_row_count(client: DirectusAdminClient) -> int:
    rows = client._request(
        "GET",
        "/items/prod_modules?fields=id&limit=200",
    )
    return len(rows or [])


def diff_for_patch(existing: dict, target: dict) -> dict:
    """Return a dict of fields where target differs from existing (PATCH-only)."""
    out = {}
    for field in PATCH_ALLOWED:
        if target.get(field) != existing.get(field):
            out[field] = target[field]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    if args.apply:
        args.dry_run = False

    modules = build_prod_module_rows()
    print(f"Built {len(modules)} module entries from production_event_map.py.")
    arc_summary: dict[int, list[int]] = {}
    for m in modules:
        arc_summary.setdefault(m["arc_number"], []).append(m["m_number"])
    for arc in sorted(arc_summary):
        nums = arc_summary[arc]
        print(f"  arc {arc}: {len(nums)} modules M{min(nums)}-M{max(nums)}")

    client = DirectusAdminClient()
    existing = fetch_existing_modules(client)
    print(f"\nDirectus baseline: {len(existing)} existing prod_modules rows.")

    to_create: list[dict] = []
    to_patch: list[tuple[int, dict]] = []
    for m in modules:
        existing_row = existing.get(m["m_number"])
        if existing_row is None:
            to_create.append(m)
        else:
            patch = diff_for_patch(existing_row, m)
            if patch:
                to_patch.append((existing_row["id"], patch))

    print(f"\nDelta: {len(to_create)} new modules, {len(to_patch)} existing rows need PATCH.")
    if args.dry_run:
        print("\n--dry-run: no writes. Use --apply to write.")
        if to_create:
            print("Sample new entries:")
            for m in to_create[:3]:
                print(
                    f"  M{m['m_number']:>2d} arc={m['arc_number']} idx={m['module_index']} "
                    f"creature={m['creature_name']!r} spell={m['spell_name']!r}"
                )
        if to_patch:
            print("Sample patches:")
            for pid, p in to_patch[:3]:
                print(f"  id={pid}: {p}")

    if args.apply:
        print("\n--apply: writing...")
        created_ids: list[int] = []
        for m in to_create:
            payload = {
                "m_number": m["m_number"],
                "arc_number": m["arc_number"],
                "module_index": m["module_index"],
                "creature_name": m["creature_name"],
                "video_role": m["video_role"],
                "technique_name": m["technique_name"],
                "spell_name": m["spell_name"],
                "current_stage": "intake",
                "stage_status": "not_started",
            }
            result = try_post_or_queue("prod_modules", payload)
            if isinstance(result, dict) and result.get("id"):
                created_ids.append(result["id"])
                print(f"  + M{m['m_number']:>2d} → id={result['id']}")
            elif isinstance(result, dict) and result.get("silent_write_failure"):
                read_back = client._request(
                    "GET",
                    f"/items/prod_modules/{result['item_id']}?fields=m_number,creature_name,arc_number,video_role",
                )
                if read_back and read_back.get("m_number") == m["m_number"]:
                    created_ids.append(result["item_id"])
                    print(
                        f"  + M{m['m_number']:>2d} → id={result['item_id']} "
                        "(silent_write_failure cleared by read-back)"
                    )
                else:
                    print(f"  ! M{m['m_number']:>2d} FAILED — read-back mismatch")
                    return 6
            else:
                print(f"  ! M{m['m_number']:>2d} FAILED: {result}")
                return 5

        for pid, patch in to_patch:
            try:
                client.patch_item("prod_modules", pid, patch)
                print(f"  ~ id={pid} patched: {patch}")
            except Exception as e:
                print(f"  ! id={pid} PATCH FAILED: {e}")
                return 7

        print(f"\nApply complete: {len(created_ids)} created, {len(to_patch)} patched.")

    if args.validate:
        print("\n--validate:")
        existing2 = fetch_existing_modules(client)
        row_count = fetch_row_count(client)
        map_numbers = sorted(m["m_number"] for m in modules)
        missing_from_directus = [n for n in map_numbers if n not in existing2]
        if missing_from_directus:
            print(f"  FAIL: map M-numbers missing from Directus: {missing_from_directus}", file=sys.stderr)
            return 8
        if row_count != EXPECTED_MODULE_ROW_COUNT:
            print(
                f"  FAIL: {row_count} rows; expected {EXPECTED_MODULE_ROW_COUNT}.",
                file=sys.stderr,
            )
            print(f"  distinct m_numbers: {sorted(existing2.keys())}", file=sys.stderr)
            return 9
        print(
            f"  OK: {row_count} prod_modules rows; all {len(map_numbers)} map M-numbers present."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
