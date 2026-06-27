#!/usr/bin/env python3
"""Verify SQLite sidecar matches Dropbox JSON beat-by-beat."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve()
_ROOT = _SCRIPT.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.beatgen_store import BeatgenStore, beats_equal_by_id, default_db_path  # noqa: E402
from lib.paths import dropbox_root  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--json",
        type=Path,
        default=dropbox_root() / "Production" / "beat_generator_state.json",
    )
    ap.add_argument("--db", type=Path, default=default_db_path())
    args = ap.parse_args()
    if not args.json.is_file():
        print(f"FATAL: missing json {args.json}", file=sys.stderr)
        return 1
    if not args.db.is_file():
        print(f"FATAL: missing db {args.db}", file=sys.stderr)
        return 1
    data = json.loads(args.json.read_text(encoding="utf-8"))
    store = BeatgenStore(args.db)
    roundtrip = store.assemble_sidecar_dict()
    if beats_equal_by_id(data, roundtrip):
        print(
            json.dumps(
                {
                    "ok": True,
                    "beats": store.beat_count(),
                    "integrity": store.integrity_check(),
                }
            )
        )
        return 0
    print("FATAL: beat parity mismatch", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
