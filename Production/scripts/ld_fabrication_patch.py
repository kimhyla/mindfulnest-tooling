#!/usr/bin/env python3
"""Apply mechanical PATCH operations from /tmp/ld_audit_bucketed_v2.json.

Per LD-813 SYSTEMIC_RETROACTIVE_FABRICATION_AUDIT_SPEC_20260520_V1 Phase 5.

For each finding:
  - CANONICAL_LOCATION: PATCH the LD's related_files (or ref_doc's file_path)
    to point at the actual location where the file lives.
  - IN_ARCHIVE_ONLY: PATCH ref_doc's file_path to the archive path.
  - ELEVENLABS_CLIENT_REFS: PATCH LD's related_files to remove
    'Production/lib/elevenlabs_client.py' and add real locations.

Read-back-after-write per LD-364 + Rule 35. Idempotent — safe to re-run.

Usage:
  python3 Production/scripts/ld_fabrication_patch.py --dry-run
  python3 Production/scripts/ld_fabrication_patch.py        # apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

TOOLING_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLING_ROOT / "Production"))

from lib.directus_admin_client import DirectusAdminClient  # type: ignore


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/tmp/ld_audit_bucketed_v2.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="Max patches to apply (0=all)")
    args = ap.parse_args(argv)

    data = json.loads(Path(args.input).read_text())
    client = DirectusAdminClient()

    # Helpers
    DROPBOX_ROOT = "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"

    def to_rel(p: str) -> str:
        """Convert absolute path to project-relative."""
        if p.startswith(DROPBOX_ROOT + "/"):
            return p[len(DROPBOX_ROOT) + 1:]
        if p.startswith(str(TOOLING_ROOT) + "/"):
            return p[len(str(TOOLING_ROOT)) + 1:]
        return p

    # Group findings by (collection, item_id) so we batch all related_files
    # changes for the same row.
    ld_updates: dict[int, dict[str, Any]] = {}
    ref_updates: dict[int, dict[str, Any]] = {}

    def process_bucket(items: list[dict], strategy: str) -> None:
        for f in items:
            if f.get("ld_id"):
                ld_id = f["ld_id"]
                if ld_id not in ld_updates:
                    ld_updates[ld_id] = {"replacements": {}, "removals": [], "claims_handled": [], "_strategy": strategy}
                u = ld_updates[ld_id]
                if strategy == "CANONICAL_LOCATION":
                    paths = f.get("canonical_paths") or []
                    if paths:
                        u["replacements"][f["claim"]] = to_rel(paths[0])
                        u["claims_handled"].append(f["claim"])
                elif strategy == "IN_ARCHIVE_ONLY":
                    paths = f.get("archive_paths") or []
                    if paths:
                        u["replacements"][f["claim"]] = to_rel(paths[0])
                        u["claims_handled"].append(f["claim"])
                elif strategy == "ELEVENLABS_CLIENT_REFS":
                    u["removals"].append(f["claim"])
                    u["claims_handled"].append(f["claim"])
            elif f.get("ref_doc_id"):
                rd_id = f["ref_doc_id"]
                if rd_id not in ref_updates:
                    ref_updates[rd_id] = {"new_path": None, "_strategy": strategy}
                u = ref_updates[rd_id]
                if strategy == "CANONICAL_LOCATION":
                    paths = f.get("canonical_paths") or []
                    if paths:
                        u["new_path"] = to_rel(paths[0])
                elif strategy == "IN_ARCHIVE_ONLY":
                    paths = f.get("archive_paths") or []
                    if paths:
                        u["new_path"] = to_rel(paths[0])

    process_bucket(data.get("CANONICAL_LOCATION", []), "CANONICAL_LOCATION")
    process_bucket(data.get("IN_ARCHIVE_ONLY", []), "IN_ARCHIVE_ONLY")
    # Use sub-bucket if present
    sub = data.get("TRULY_MISSING_SUB", {})
    process_bucket(sub.get("ELEVENLABS_CLIENT_REFS", []), "ELEVENLABS_CLIENT_REFS")

    print(f"LD updates planned: {len(ld_updates)}")
    print(f"Ref-doc updates planned: {len(ref_updates)}")
    print()

    # Apply LD updates
    applied = 0
    for ld_id, u in sorted(ld_updates.items()):
        # Read current state
        try:
            current = client.get_items(
                "prod_locked_decisions",
                filters={"id": {"_eq": ld_id}},
                limit=1,
            )
        except Exception as exc:
            print(f"  LD-{ld_id}: GET failed: {exc}")
            continue
        if not current:
            print(f"  LD-{ld_id}: row not found, skipping")
            continue
        row = current[0]
        related = list(row.get("related_files") or [])
        new_related = []
        for r in related:
            if r in u["removals"]:
                continue  # drop the elevenlabs_client.py path
            if r in u["replacements"]:
                new_related.append(u["replacements"][r])
            else:
                new_related.append(r)
        # For ELEVENLABS strategy: also ADD canonical-pointer entries if not already there
        if u["_strategy"] == "ELEVENLABS_CLIENT_REFS":
            extras = ["Production/tools/production_server.py", "directus://collections/prod_voice_profiles"]
            for e in extras:
                if e not in new_related:
                    new_related.append(e)
        if new_related == related:
            continue  # no-op
        applied += 1
        if args.dry_run:
            print(f"  [DRY] LD-{ld_id} ({row.get('decision_key', '?')[:40]}): {len(u['claims_handled'])} claim(s)")
            for c in u["claims_handled"]:
                if c in u["replacements"]:
                    print(f"        {c} → {u['replacements'][c]}")
                else:
                    print(f"        {c} → (removed)")
            continue
        try:
            client.patch_item("prod_locked_decisions", ld_id, {"related_files": new_related})
            print(f"  LD-{ld_id}: PATCHed {len(u['claims_handled'])} claim(s)")
        except Exception as exc:
            print(f"  LD-{ld_id}: PATCH failed: {exc}")
        if args.limit and applied >= args.limit:
            print(f"  hit --limit={args.limit}, stopping")
            break

    # Apply ref-doc updates
    for rd_id, u in sorted(ref_updates.items()):
        if not u.get("new_path"):
            continue
        try:
            current = client.get_items(
                "prod_reference_docs",
                filters={"id": {"_eq": rd_id}},
                limit=1,
            )
        except Exception as exc:
            print(f"  RefDoc-{rd_id}: GET failed: {exc}")
            continue
        if not current:
            continue
        row = current[0]
        if row.get("file_path") == u["new_path"]:
            continue
        applied += 1
        if args.dry_run:
            print(f"  [DRY] RefDoc-{rd_id} ({row.get('doc_title', '?')[:40]}): {row.get('file_path')} → {u['new_path']}")
            continue
        try:
            client.patch_item("prod_reference_docs", rd_id, {"file_path": u["new_path"]})
            print(f"  RefDoc-{rd_id}: file_path PATCHed → {u['new_path']}")
        except Exception as exc:
            print(f"  RefDoc-{rd_id}: PATCH failed: {exc}")
        if args.limit and applied >= args.limit:
            break

    print(f"\nTotal applied (or planned): {applied}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
