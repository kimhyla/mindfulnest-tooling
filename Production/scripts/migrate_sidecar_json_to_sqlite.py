#!/usr/bin/env python3
"""Import Dropbox beat_generator_state.json into local SQLite authority."""
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
    ap = argparse.ArgumentParser(description="Migrate Beat Gen JSON sidecar → SQLite")
    ap.add_argument(
        "--source",
        type=Path,
        default=dropbox_root() / "Production" / "beat_generator_state.json",
    )
    ap.add_argument("--db", type=Path, default=default_db_path())
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not args.dry_run and not args.apply:
        print("FATAL: pass --dry-run or --apply", file=sys.stderr)
        return 1
    src = args.source.resolve()
    if not src.is_file():
        print(f"FATAL: missing source {src}", file=sys.stderr)
        return 1
    data = json.loads(src.read_text(encoding="utf-8"))
    beats = sum(
        len(seg.get("beats") or [])
        for arc in (data.get("arcs") or {}).values()
        for seg in (arc.get("segments") or {}).values()
    )
    print(f"source={src} bytes={src.stat().st_size} beats={beats}")
    if args.dry_run:
        print("dry-run ok")
        return 0
    BeatgenStore.reset_singleton_for_tests()
    store = BeatgenStore(args.db)
    count = store.import_from_dict(data, replace=True)
    roundtrip = store.assemble_sidecar_dict()
    if not beats_equal_by_id(data, roundtrip):
        print("FATAL: parity failed after import", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "db": str(store.db_path),
                "beats_imported": count,
                "integrity": store.integrity_check(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
