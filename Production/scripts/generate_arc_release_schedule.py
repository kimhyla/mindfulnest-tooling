#!/usr/bin/env python3
"""
Stream F Item 7 — Arc Release Schedule Generator

Produces a CDN deadline table for Arcs 2-10 based on fastest-family
progression math. The schedule is never hand-authored — this script is
the single source of truth (LD ARC_RELEASE_CADENCE_MONITOR_V1).

Governing decisions:
  LD-282  CATALOG_DELIVERY_ARC_AT_A_TIME_V1   — arc-at-a-time; Arc 1 bundled at install
  LD-352  V1_CADENCE_DEFERRED_PENDING_VELOCITY_V1 — cadence deferred; default 3×/wk
  LD-339  RETENTION_LAYER_V1                  — 2×/wk aspirational (comparison column)
  LD-358  V1_ARC10_RESTORED_WITH_ARC8_20260421 — Arc 10 = 5 modules (M55-M59)
  Rule 19 No error paths — generator must be re-runnable; schedule must not rot

Math:
  cdn_deadline_weeks(arc_N) = ceil(sum_of_modules(arcs_1_to_N-1) / cadence) + buffer_weeks
  production_start_deadline = cdn_deadline_weeks - production_lead_weeks

  At cadence=3 (default, worst-case fastest family):
    Arc 2: ceil(6/3) + 2 = 4 weeks
    Arc 3: ceil(12/3) + 2 = 6 weeks
    ...
    Arc 10: ceil(54/3) + 2 = 20 weeks

Usage:
  python3 generate_arc_release_schedule.py --dry-run
  python3 generate_arc_release_schedule.py --launch-date 2026-09-01
  python3 generate_arc_release_schedule.py --launch-date 2026-09-01 --write-md ../ARC_RELEASE_SCHEDULE.md
  python3 generate_arc_release_schedule.py --launch-date 2026-09-01 --write-directus
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

# ─── Arc module counts (LOCKED — LD-332, LD-358) ─────────────────────────────

# Arc 1-9 = 6 modules each; Arc 10 = 5 modules (M55-M59, LD-358)
MODULES_PER_ARC: dict[int, int] = {
    1: 6, 2: 6, 3: 6, 4: 6, 5: 6,
    6: 6, 7: 6, 8: 6, 9: 6, 10: 5,
}

# Arcs that need CDN deadlines (Arc 1 bundled at install per LD-282)
SCHEDULE_ARCS = list(range(2, 11))

# ─── Defaults (all overridable via CLI) ──────────────────────────────────────

DEFAULT_CADENCE_FAST = 3.0   # modules/week — fastest-family planning anchor
DEFAULT_CADENCE_ASPIR = 2.0  # modules/week — aspirational (LD-339 Parent Weekly Plan)
DEFAULT_BUFFER_WEEKS = 2     # CDN safety buffer weeks
DEFAULT_PRODUCTION_LEAD = 4  # weeks from arc-start to CDN-live (pre-M1-M6-empirics estimate)


# ─── Core math ───────────────────────────────────────────────────────────────

def modules_before_arc(arc_n: int) -> int:
    """Total modules in arcs 1 through arc_n-1 (completed before needing arc_n)."""
    return sum(MODULES_PER_ARC[a] for a in range(1, arc_n))


def cdn_deadline_weeks(arc_n: int, cadence: float, buffer: int) -> float:
    """Weeks post-launch by which arc_n must be CDN-live."""
    modules = modules_before_arc(arc_n)
    return math.ceil(modules / cadence) + buffer


def production_start_weeks(arc_n: int, cadence: float, buffer: int, lead: int) -> float:
    """Weeks post-launch by which arc_n production must have started."""
    return cdn_deadline_weeks(arc_n, cadence, buffer) - lead


def cdn_deadline_date(arc_n: int, launch: date, cadence: float, buffer: int) -> date:
    return launch + timedelta(weeks=cdn_deadline_weeks(arc_n, cadence, buffer))


def production_start_date(arc_n: int, launch: date, cadence: float, buffer: int, lead: int) -> date:
    weeks = production_start_weeks(arc_n, cadence, buffer, lead)
    if weeks < 0:
        return launch  # production should already be in-flight at launch
    return launch + timedelta(weeks=weeks)


# ─── Schedule row ─────────────────────────────────────────────────────────────

def build_row(
    arc_n: int,
    launch: Optional[date],
    cadence_fast: float,
    cadence_aspir: float,
    buffer: int,
    lead: int,
) -> dict:
    row: dict = {
        "arc_number": arc_n,
        "modules": MODULES_PER_ARC[arc_n],
        "modules_before": modules_before_arc(arc_n),
        "cdn_weeks_fast": cdn_deadline_weeks(arc_n, cadence_fast, buffer),
        "prod_start_weeks_fast": production_start_weeks(arc_n, cadence_fast, buffer, lead),
        "cdn_weeks_aspir": cdn_deadline_weeks(arc_n, cadence_aspir, buffer),
        "prod_start_weeks_aspir": production_start_weeks(arc_n, cadence_aspir, buffer, lead),
    }
    if launch:
        row["cdn_date_fast"] = cdn_deadline_date(arc_n, launch, cadence_fast, buffer)
        row["prod_start_date_fast"] = production_start_date(arc_n, launch, cadence_fast, buffer, lead)
        row["cdn_date_aspir"] = cdn_deadline_date(arc_n, launch, cadence_aspir, buffer)
        row["prod_start_date_aspir"] = production_start_date(arc_n, launch, cadence_aspir, buffer, lead)
    return row


def build_schedule(
    launch: Optional[date],
    cadence_fast: float = DEFAULT_CADENCE_FAST,
    cadence_aspir: float = DEFAULT_CADENCE_ASPIR,
    buffer: int = DEFAULT_BUFFER_WEEKS,
    lead: int = DEFAULT_PRODUCTION_LEAD,
) -> list[dict]:
    return [build_row(n, launch, cadence_fast, cadence_aspir, buffer, lead) for n in SCHEDULE_ARCS]


# ─── Markdown rendering ───────────────────────────────────────────────────────

def _fmt_weeks(w: float) -> str:
    if w <= 0:
        return "AT LAUNCH"
    return f"T+{w:.0f}wk"


def _fmt_date(d: Optional[date]) -> str:
    if d is None:
        return "—"
    return d.strftime("%Y-%m-%d")


def render_markdown(
    rows: list[dict],
    launch: Optional[date],
    cadence_fast: float,
    cadence_aspir: float,
    buffer: int,
    lead: int,
    generated_at: str,
) -> str:
    launch_str = launch.isoformat() if launch else "[PENDING — re-run with --launch-date when launch date locks]"

    header = f"""# Arc Release Schedule
> **GENERATED** by `generate_arc_release_schedule.py` — do not edit manually
> Parameters: cadence_fast={cadence_fast}/wk, cadence_aspir={cadence_aspir}/wk, buffer={buffer}wk, production_lead={lead}wk
> Launch date: {launch_str}
> Generated: {generated_at}
>
> Arc 1 is bundled at install (LD-282) — schedule covers Arcs 2-10 only.
> **3×/wk column** = fastest-family worst-case planning anchor (LD-352: uncapped therapist prescription).
> **2×/wk column** = aspirational default (LD-339 Parent Weekly Plan, 26wk program).
> CDN-live signal = Firestore `arc_manifests/{{arcId}}` existence (LD-406).
> Re-run generator after any change to launch date or cadence assumption.

"""

    if launch:
        table = (
            "| Arc | Mods | 3×/wk CDN Deadline | 3×/wk Prod Start | "
            "2×/wk CDN Deadline | 2×/wk Prod Start |\n"
            "|-----|------|--------------------|------------------|"
            "--------------------|------------------|\n"
        )
        for r in rows:
            cdn_f = f"{_fmt_weeks(r['cdn_weeks_fast'])} ({_fmt_date(r.get('cdn_date_fast'))})"
            ps_f  = f"{_fmt_weeks(r['prod_start_weeks_fast'])} ({_fmt_date(r.get('prod_start_date_fast'))})"
            cdn_a = f"{_fmt_weeks(r['cdn_weeks_aspir'])} ({_fmt_date(r.get('cdn_date_aspir'))})"
            ps_a  = f"{_fmt_weeks(r['prod_start_weeks_aspir'])} ({_fmt_date(r.get('prod_start_date_aspir'))})"
            table += f"| Arc {r['arc_number']} | {r['modules']} | {cdn_f} | {ps_f} | {cdn_a} | {ps_a} |\n"
    else:
        table = (
            "| Arc | Mods | 3×/wk CDN Deadline | 3×/wk Prod Start | "
            "2×/wk CDN Deadline | 2×/wk Prod Start |\n"
            "|-----|------|--------------------|------------------|"
            "--------------------|------------------|\n"
        )
        for r in rows:
            table += (
                f"| Arc {r['arc_number']} | {r['modules']} "
                f"| {_fmt_weeks(r['cdn_weeks_fast'])} | {_fmt_weeks(r['prod_start_weeks_fast'])} "
                f"| {_fmt_weeks(r['cdn_weeks_aspir'])} | {_fmt_weeks(r['prod_start_weeks_aspir'])} |\n"
            )
        table += "\n> Launch date not yet locked — dates shown as relative offsets from T (launch day).\n"

    notes = """
## Activation instructions (when launch date locks)

```bash
# 1. Re-run generator with the locked launch date
python3 Production/scripts/generate_arc_release_schedule.py \\
    --launch-date YYYY-MM-DD --write-md Production/ARC_RELEASE_SCHEDULE.md

# 2. Apply Directus migration (one-time)
python3 Production/migrations/create_prod_arc_release_schedule.py --apply

# 3. Write schedule rows to Directus
python3 Production/scripts/generate_arc_release_schedule.py \\
    --launch-date YYYY-MM-DD --write-directus

# 4. Uncomment the arc_cadence_monitor launchd plist entry in
#    ~/Library/LaunchAgents/com.mindfulnest.arc-cadence-monitor.plist
#    and run: launchctl load ~/Library/LaunchAgents/com.mindfulnest.arc-cadence-monitor.plist
```

## Slip-handling policy

When an arc misses its production-start deadline:
- `arc_cadence_monitor.py` creates a CRITICAL `app_blockers` row
- **No auto-cascade** — downstream deadlines do not shift automatically
- Kim re-runs this generator with an updated `--launch-date` (or adjusted `--buffer-weeks`) to see revised deadlines
- Re-running overwrites this file and upserts Directus rows (idempotent)

## Stream F Item 8 (post-launch)

`prod_family_velocity_observations` collection and real family-velocity telemetry
are deferred to Stream F Item 8, activating T+4 weeks post-launch.
See `app_blockers` feature_id=stream_f_item_8_velocity_telemetry.
"""
    return header + table + notes


# ─── Directus write ───────────────────────────────────────────────────────────

def write_to_directus(
    rows: list[dict],
    cadence_fast: float,
    cadence_aspir: float,
    buffer: int,
    lead: int,
    generated_at: str,
    dry_run: bool = False,
) -> None:
    try:
        from directus_admin_client import DirectusAdminClient
    except ImportError:
        sys.exit("ERROR: Cannot import DirectusAdminClient. Run from project root or add Production/lib to PYTHONPATH.")

    client = DirectusAdminClient()

    # Verify collection exists
    try:
        client._request("GET", "/collections/prod_arc_release_schedule")
    except Exception as e:
        sys.exit(
            "ERROR: prod_arc_release_schedule collection not found in Directus.\n"
            "Apply the migration first:\n"
            "  python3 Production/migrations/create_prod_arc_release_schedule.py --apply\n"
            f"(Original error: {e})"
        )

    params_json = json.dumps({
        "cadence_fast": cadence_fast, "cadence_aspir": cadence_aspir,
        "buffer_weeks": buffer, "production_lead_weeks": lead,
        "generated_at": generated_at,
    })

    for r in rows:
        payload = {
            "arc_number": r["arc_number"],
            "weeks_post_launch_target": r["cdn_weeks_fast"],
            "weeks_post_launch_hard_ceiling": r["cdn_weeks_aspir"] + 1,  # +1 extra buffer
            "production_start_deadline_weeks": r["prod_start_weeks_fast"],
            "production_lead_weeks_assumed": float(lead),
            "cadence_assumed": cadence_fast,
            "cdn_ready_status": "not_started",
            "generated_at": generated_at,
            "generator_params": params_json,
        }

        if dry_run:
            print(f"  [dry-run] Would upsert prod_arc_release_schedule arc={r['arc_number']}: {payload}")
            continue

        # Upsert by arc_number: check for existing row, PATCH or POST
        try:
            existing = client.get_items(
                "prod_arc_release_schedule",
                filters={"arc_number": {"_eq": r["arc_number"]}},
                fields=["id"],
                limit=1,
            )
            if existing:
                row_id = existing[0]["id"]
                client._request("PATCH", f"/items/prod_arc_release_schedule/{row_id}", data=payload)
                print(f"  PATCH arc={r['arc_number']} id={row_id} ✓")
            else:
                result = client.post_item("prod_arc_release_schedule", payload)
                print(f"  POST arc={r['arc_number']} id={result.get('id')} ✓")
        except Exception as e:
            print(f"  WARNING: Directus write failed for arc={r['arc_number']} — {e}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate MindfulNest arc CDN release schedule (Stream F Item 7)"
    )
    parser.add_argument(
        "--launch-date", default=None,
        help="Launch date YYYY-MM-DD. If omitted, outputs relative-offset table only.",
    )
    parser.add_argument(
        "--cadence", type=float, default=DEFAULT_CADENCE_FAST,
        help=f"Fastest-family planning anchor: modules/week (default {DEFAULT_CADENCE_FAST}). "
             "LD-352: therapist-prescribed, no upper cap. Use 3.0 for conservative planning.",
    )
    parser.add_argument(
        "--aspir-cadence", type=float, default=DEFAULT_CADENCE_ASPIR,
        help=f"Aspirational cadence modules/week for comparison column (default {DEFAULT_CADENCE_ASPIR}, LD-339).",
    )
    parser.add_argument(
        "--buffer-weeks", type=int, default=DEFAULT_BUFFER_WEEKS,
        help=f"Safety buffer weeks added to each CDN deadline (default {DEFAULT_BUFFER_WEEKS}).",
    )
    parser.add_argument(
        "--production-lead-weeks", type=int, default=DEFAULT_PRODUCTION_LEAD,
        help=f"Weeks needed from arc-production-start to CDN-live (default {DEFAULT_PRODUCTION_LEAD}). "
             "Update after M1-M6 empirical data (LD-352).",
    )
    parser.add_argument(
        "--write-md", default=None, metavar="PATH",
        help="Write markdown schedule to this file path (default: print to stdout).",
    )
    parser.add_argument(
        "--write-directus", action="store_true",
        help="Upsert schedule rows to prod_arc_release_schedule Directus collection. "
             "Migration must be applied first.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate + compute schedule without writing files or Directus rows.",
    )

    args = parser.parse_args()

    # Parse launch date
    launch: Optional[date] = None
    if args.launch_date:
        try:
            launch = date.fromisoformat(args.launch_date)
        except ValueError:
            sys.exit(f"ERROR: --launch-date must be YYYY-MM-DD, got: {args.launch_date!r}")

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build schedule
    rows = build_schedule(
        launch=launch,
        cadence_fast=args.cadence,
        cadence_aspir=args.aspir_cadence,
        buffer=args.buffer_weeks,
        lead=args.production_lead_weeks,
    )

    # Render markdown
    md = render_markdown(
        rows=rows,
        launch=launch,
        cadence_fast=args.cadence,
        cadence_aspir=args.aspir_cadence,
        buffer=args.buffer_weeks,
        lead=args.production_lead_weeks,
        generated_at=generated_at,
    )

    # Output markdown
    if args.dry_run:
        print("=== DRY RUN — no files or Directus writes ===\n")
        print(md)
        if args.write_directus:
            print("\n=== DRY RUN — Directus upserts ===")
            write_to_directus(rows, args.cadence, args.aspir_cadence, args.buffer_weeks,
                              args.production_lead_weeks, generated_at, dry_run=True)
        return

    if args.write_md:
        out_path = Path(args.write_md)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"Written: {out_path}")
    else:
        print(md)

    # Directus write
    if args.write_directus:
        print("\nWriting to Directus prod_arc_release_schedule ...")
        write_to_directus(rows, args.cadence, args.aspir_cadence, args.buffer_weeks,
                          args.production_lead_weeks, generated_at, dry_run=False)

    print(f"\nSchedule generated at {generated_at}")
    if not launch:
        print("Re-run with --launch-date YYYY-MM-DD when launch date locks.")


if __name__ == "__main__":
    main()
