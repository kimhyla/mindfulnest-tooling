#!/usr/bin/env python3
"""Smoke-test Directus row writer.

Reads details JSON from a file, composes the prod_activity_log payload,
and calls try_post_or_queue (read-back-after-write per LD-364 / Rule 35).

Exit 0 on persisted-row OR offline-queue (smoke ran cleanly, write deferred).
Exit 1 on silent_write_failure OR unexpected gate sentinel.

Caller: Production/scripts/event_smoke_test.sh (LD-782).
"""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True)
    parser.add_argument("--details-file", required=True)
    parser.add_argument("--performed-by", default="event_smoke_test")
    args = parser.parse_args()

    # Locate Production/lib relative to this script.
    # script_dir = .../Production/scripts/
    # project_root = .../
    # lib_dir = .../Production/lib/
    script_dir = Path(__file__).resolve().parent
    # Resolve lib/directus.py robustly: this file lives at
    # <repo>/Production/scripts/_smoke_directus_writer.py, so the canonical
    # location is `script_dir.parent / "lib"` (one level up to Production/, then
    # over to lib/). The previous `parent.parent / "Production" / "lib"` form
    # was fragile (correct only when invoked from the exact repo root) and
    # silently mis-resolved under symlinks / unusual CWDs. The current form is
    # CWD-independent because it's anchored on this script's __file__.
    lib_dir = script_dir.parent / "lib"
    if not (lib_dir / "directus.py").is_file():
        print(
            f"FATAL: directus.py not found at {lib_dir} "
            f"(script_dir={script_dir}, expected layout: "
            f"<repo>/Production/scripts/_smoke_directus_writer.py)",
            file=sys.stderr,
        )
        return 1
    sys.path.insert(0, str(lib_dir))

    try:
        from directus import try_post_or_queue  # type: ignore
    except ImportError as e:
        print(f"FATAL: cannot import try_post_or_queue: {e}", file=sys.stderr)
        return 1

    details_path = Path(args.details_file)
    if not details_path.is_file():
        print(f"FATAL: details file not found: {details_path}", file=sys.stderr)
        return 1

    try:
        details = json.loads(details_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FATAL: details file malformed JSON: {e}", file=sys.stderr)
        return 1

    payload = {
        "action": args.action,
        "details": details,
        "performed_by": args.performed_by,
    }

    result = try_post_or_queue("prod_activity_log", payload)

    if isinstance(result, dict) and result.get("id") and not result.get("queued"):
        print(f"[directus] ok row_id={result['id']} action={args.action}")
        return 0
    if isinstance(result, dict) and result.get("queued"):
        print(
            f"[directus] OFFLINE queued to {result.get('path')}: "
            f"{result.get('error', '')}",
            file=sys.stderr,
        )
        # Offline queue is not a smoke-gate failure — the script still ran.
        return 0
    if isinstance(result, dict) and result.get("silent_write_failure"):
        print(
            f"[directus] SILENT WRITE FAILURE — mismatches: "
            f"{result.get('mismatches')}",
            file=sys.stderr,
        )
        return 1
    if isinstance(result, dict) and (
        result.get("browser_smoke_missing")
        or result.get("browser_smoke_gate_unverifiable")
        or result.get("override_without_audit")
    ):
        # Our action does NOT end in _COMPLETE so this shouldn't fire, but
        # defensively surface the gate signal.
        print(
            f"[directus] phase-F gate fired unexpectedly: {result}",
            file=sys.stderr,
        )
        return 1
    print(f"[directus] unknown result shape: {result}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
