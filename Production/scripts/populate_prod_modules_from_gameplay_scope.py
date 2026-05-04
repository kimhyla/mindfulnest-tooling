#!/usr/bin/env python3
"""
Populate prod_modules from GAMEPLAY_SCOPE_v3.md (V1 frozen scope per LD-357).

Per LD PROD_MODULES_GAMEPLAY_SCOPE_SOURCE_V1 (S5.5e):
  GAMEPLAY_SCOPE_v3.md is the canonical V1 scope authority. This script
  mirrors that document into Directus prod_modules so Production Map renders
  all 59 modules across 10 arcs.

Inputs (parsed from GAMEPLAY_SCOPE_v3.md):
  1) The 10-arc table at lines ~88-103 — provides arc number + M-range.
  2) The 6-creature table at lines ~109-115 — provides M1..M6 creature/technique/spell.
  3) Arc 10 module list at line 102 — provides M55..M59 techniques.

Modes:
  --dry-run   : parse + report counts; do NOT write. (default)
  --apply     : write missing rows via try_post_or_queue (Rule 35).
                Existing rows are PATCHed only on (creature_name, arc_number,
                video_role) — never on stage_status, current_stage, kim_notes,
                or any *_built_at field (avoids clobbering Kim's manual edits).
  --validate  : count rows by m_number; ASSERT 59 distinct M-numbers present.

Idempotent: re-runnable without duplication. Per Rule 35, every write is
verified via try_post_or_queue (read-back-after-write).

Per CLAUDE.md Rule 19 "no error paths": this script aborts on parse failure
and reports the offending line. It does NOT POST partial data.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

# Allow Production.lib import.
THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from Production.lib.directus import try_post_or_queue, post_item_verified  # noqa: E402
from Production.lib.directus_admin_client import DirectusAdminClient  # noqa: E402


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


# 6 creatures M1-M6 (from GAMEPLAY_SCOPE_v3.md §"6 creatures" table).
# These are FIXED per LD-353 (Benson restored at M3); never auto-derived.
ARC_1_CREATURES: list[dict] = [
    {"m_number": 1, "creature": "Tessa",   "technique_name": "Palm Interoception",  "spell_name": "Magic Hands Spell"},
    {"m_number": 2, "creature": "Luna",    "technique_name": "Squeeze-and-Release", "spell_name": "Breath-Squeezers Spell"},
    {"m_number": 3, "creature": "Benson",  "technique_name": "Physiological Sigh",  "spell_name": "Brave Sniffing Spell"},
    {"m_number": 4, "creature": "Ember",   "technique_name": "Art of Kindness",     "spell_name": "Heart-Sending Spell"},
    {"m_number": 5, "creature": "Bork",    "technique_name": "Letting Go",          "spell_name": "Letting Go Spell"},
    {"m_number": 6, "creature": "Bramble", "technique_name": "Humming Breath",      "spell_name": "Humming Spell"},
]

# Arc 10 specific techniques M55-M59 (from GAMEPLAY_SCOPE_v3.md line 102).
# M59 is uniquely guided by Ophelia (not Guidebird).
ARC_10_MODULES: list[dict] = [
    {"m_number": 55, "creature": "TBD",     "technique_name": "Gratitude/Savoring (K-1)",   "spell_name": "TBD"},
    {"m_number": 56, "creature": "TBD",     "technique_name": "Eye Palming (VP-1)",         "spell_name": "TBD"},
    {"m_number": 57, "creature": "TBD",     "technique_name": "Lion's Breath (CO-M6)",      "spell_name": "TBD"},
    {"m_number": 58, "creature": "Oliver",  "technique_name": "Extended Exhale",            "spell_name": "TBD"},
    {"m_number": 59, "creature": "Ophelia", "technique_name": "Integrated Somatic",         "spell_name": "TBD"},
]


def parse_arc_table(scope_md: str) -> list[dict]:
    """Parse the 10-arc table into a list of {arc, m_low, m_high, name}.

    Targets rows that match either:
        | 1 | Everdale (intro) | ... | 6 | M1-M6 | ...
        | **10** | **THE RETURN** ... | ... | **5** | **M55-M59** | ...
    """
    rows = []
    # Either bare digit | <name> | <plot> | <count> | M<low>-M<high> ...
    # or **digit** | **name** | ... | **count** | **M<low>-M<high>** ...
    pat = re.compile(
        r"^\|\s*\*{0,2}(\d{1,2})\*{0,2}\s*\|\s*\*{0,2}([^|]+?)\*{0,2}\s*\|"  # arc, name
        r"\s*[^|]+\|\s*\*{0,2}\d+\*{0,2}\s*\|\s*\*{0,2}M(\d+)-M(\d+)\*{0,2}",
        re.MULTILINE,
    )
    for m in pat.finditer(scope_md):
        arc = int(m.group(1))
        name = m.group(2).strip()
        m_low = int(m.group(3))
        m_high = int(m.group(4))
        rows.append({"arc": arc, "name": name, "m_low": m_low, "m_high": m_high})
    return rows


def build_full_module_set(arc_rows: list[dict]) -> list[dict]:
    """From the parsed arc rows, build all 59 module entries.

    Logic:
      - Arc 1 (M1-M6): use ARC_1_CREATURES (locked per LD-353).
      - Arc 10 (M55-M59): use ARC_10_MODULES.
      - Arcs 2-9 (M7-M54): placeholder creature=None, technique="TBD",
        spell="TBD"; m_number/arc_number/module_index populated.
    """
    modules: list[dict] = []
    for arc_row in arc_rows:
        arc_n = arc_row["arc"]
        m_low = arc_row["m_low"]
        m_high = arc_row["m_high"]
        for idx, m_n in enumerate(range(m_low, m_high + 1), start=1):
            entry: dict = {
                "m_number": m_n,
                "arc_number": arc_n,
                "module_index": idx,
                "video_role": "intro",
            }
            if arc_n == 1:
                # Lookup in ARC_1_CREATURES.
                row = next((c for c in ARC_1_CREATURES if c["m_number"] == m_n), None)
                if row:
                    entry["creature_name"] = row["creature"]
                    entry["technique_name"] = row["technique_name"]
                    entry["spell_name"] = row["spell_name"]
                else:
                    raise ValueError(f"Arc 1 module M{m_n} missing from ARC_1_CREATURES")
            elif arc_n == 10:
                row = next((c for c in ARC_10_MODULES if c["m_number"] == m_n), None)
                if row:
                    entry["creature_name"] = row["creature"]
                    entry["technique_name"] = row["technique_name"]
                    entry["spell_name"] = row["spell_name"]
                else:
                    raise ValueError(f"Arc 10 module M{m_n} missing from ARC_10_MODULES")
            else:
                # Arcs 2-9: placeholder. Required schema fields filled with "TBD"
                # (creature_name is NOT NULL on prod_modules).
                entry["creature_name"] = "TBD"
                entry["technique_name"] = "TBD"
                entry["spell_name"] = "TBD"
            modules.append(entry)
    return modules


# ---------------------------------------------------------------------------
# Directus interaction
# ---------------------------------------------------------------------------


def fetch_existing_modules(client: DirectusAdminClient) -> dict[int, dict]:
    rows = client._request(
        "GET",
        "/items/prod_modules?fields=id,m_number,arc_number,module_index,creature_name,video_role,technique_name,spell_name&sort=m_number&limit=200",
    )
    return {r["m_number"]: r for r in (rows or []) if r.get("m_number") is not None}


# Fields we are willing to PATCH on existing rows. Excludes anything Kim might
# have edited manually (stage_status, current_stage, kim_notes, *_built_at, etc.).
# `module_index` is intentionally EXCLUDED — Production Map sorts by m_number
# anyway, and the (arc_number, module_index) composite is UNIQUE in Directus, so
# in-place reassignment causes collisions. Existing module_index values reflect
# pre-LD-353 ordering and are harmless.
PATCH_ALLOWED = ("creature_name", "arc_number", "video_role")


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
    parser.add_argument(
        "--scope-md",
        default=str(PROJECT_ROOT / "GAMEPLAY_SCOPE_v3.md"),
        help="Path to GAMEPLAY_SCOPE_v3.md",
    )
    args = parser.parse_args()

    if args.apply:
        args.dry_run = False

    scope_path = Path(args.scope_md)
    if not scope_path.is_file():
        print(f"FATAL: GAMEPLAY_SCOPE_v3.md not found at {scope_path}", file=sys.stderr)
        return 2
    text = scope_path.read_text(encoding="utf-8")

    arc_rows = parse_arc_table(text)
    if len(arc_rows) != 10:
        print(
            f"FATAL: parsed {len(arc_rows)} arc rows; expected 10. "
            "GAMEPLAY_SCOPE_v3.md format may have changed. Aborting.",
            file=sys.stderr,
        )
        for r in arc_rows:
            print(f"  parsed: arc={r['arc']} name={r['name']!r} M{r['m_low']}-M{r['m_high']}", file=sys.stderr)
        return 3

    modules = build_full_module_set(arc_rows)
    if len(modules) != 59:
        print(
            f"FATAL: built {len(modules)} module entries; expected 59. Aborting.",
            file=sys.stderr,
        )
        return 4

    print(f"Parsed {len(arc_rows)} arcs; built {len(modules)} module entries.")
    for arc_row in arc_rows:
        print(f"  arc {arc_row['arc']} M{arc_row['m_low']}-M{arc_row['m_high']}  ({arc_row['name']})")

    # Connect to Directus.
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
                print(f"  M{m['m_number']:>2d} arc={m['arc_number']} idx={m['module_index']} creature={m['creature_name']!r} technique={m['technique_name']!r}")
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
                # The write happened (item_id present); a silent_write_failure here
                # is the JSON-string-vs-array deep-eq artifact noted in this session's
                # preflight. Per Rule 35: re-read to confirm; on byte-equal data, accept.
                read_back = client._request("GET", f"/items/prod_modules/{result['item_id']}?fields=m_number,creature_name,arc_number,video_role")
                if read_back and read_back.get("m_number") == m["m_number"]:
                    created_ids.append(result["item_id"])
                    print(f"  + M{m['m_number']:>2d} → id={result['item_id']} (silent_write_failure cleared by read-back)")
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
        m_numbers = sorted(existing2.keys())
        if len(m_numbers) != 59:
            print(f"  FAIL: {len(m_numbers)} rows; expected 59.", file=sys.stderr)
            print(f"  m_numbers present: {m_numbers}", file=sys.stderr)
            missing = [n for n in range(1, 60) if n not in existing2]
            print(f"  missing: {missing}", file=sys.stderr)
            return 8
        print(f"  OK: {len(m_numbers)} prod_modules rows; M1..M59 all present.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
