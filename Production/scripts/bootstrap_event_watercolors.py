#!/usr/bin/env python3
"""Bootstrap empty per-event watercolor libraries from the first non-empty Event_* template.

EVENT_WC_SEED_V1 — Phase B drag-drop requires draggable tiles in the bottom grid
and/or Library → watercolors filter. New events (Event_4+) were created with empty
library/watercolors/ until manually seeded.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLING_ROOT = HERE.parent.parent
if str(TOOLING_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLING_ROOT))

from Production.lib.event_library import (  # noqa: E402
    event_watercolors_dir,
    seed_event_watercolors_if_empty,
)
from Production.lib.paths import DROPBOX_ROOT  # noqa: E402


def _event_dirs(prod_root: Path) -> list[Path]:
    out: list[Path] = []
    for d in sorted((prod_root / "Production").glob("Event_*")):
        if d.is_dir() and not d.name.endswith("_Plans"):
            out.append(d)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--event",
        action="append",
        dest="events",
        metavar="Event_N",
        help="Seed one event (repeatable). Default: all Event_* under Production/",
    )
    parser.add_argument(
        "--template",
        metavar="Event_N",
        help="Template event dir name (default: first non-empty Event_*)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    prod_root = DROPBOX_ROOT
    template_dir = (
        prod_root / "Production" / args.template if args.template else None
    )
    targets = (
        [prod_root / "Production" / e for e in args.events]
        if args.events
        else _event_dirs(prod_root)
    )

    total = 0
    for event_dir in targets:
        if not event_dir.is_dir():
            print(f"[skip] missing {event_dir}")
            continue
        wc_dir = event_watercolors_dir(event_dir)
        before = len(list(wc_dir.glob("*"))) if wc_dir.is_dir() else 0
        if before > 0:
            print(f"[ok] {event_dir.name}: already has watercolors ({before} files)")
            continue
        if args.dry_run:
            print(f"[dry-run] would seed {event_dir.name} from template")
            continue
        n = seed_event_watercolors_if_empty(
            event_dir,
            template_event_dir=template_dir,
            prod_root=prod_root,
        )
        if n:
            print(f"[seed] {event_dir.name}: copied {n} watercolor file(s)")
            total += n
        else:
            print(f"[warn] {event_dir.name}: no template watercolors found")
    print(f"[bootstrap_event_watercolors] done — copied {total} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
