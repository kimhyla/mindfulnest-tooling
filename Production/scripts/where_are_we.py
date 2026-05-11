#!/usr/bin/env python3
"""
where_are_we.py — live Directus build-status synthesizer.

When Kim asks "where are we in the build" / "status" / "where do we stand" /
"current state", any Claude session (Terminal OR Desktop) runs this script via
Bash and renders the markdown output. Sub-minute-fresh by construction —
queries Directus live every invocation; no rendered file, no cron, no drift.

Replaces the manually-edited MINDFULNEST_PROFESSIONAL_SETUP_ROADMAP_v1.md
canonical-doc model. Authority: LD MASTER_ROADMAP_LIVE_QUERY_PATTERN_V1
(supersedes LD-561 MASTER_ROADMAP_LIVING_DOC_V1).

Surfaces queried (read-only):
  - prod_locked_decisions (recent + active SHORTCUTs)
  - prod_blockers (open, grouped by severity)
  - prod_activity_log (recent _COMPLETE events + latest state summary)
  - prod_reference_docs (in-flight specs)
  - prod_modules (pipeline-stage distribution)

Output: human-readable markdown to stdout. NON-BLOCKING — errors per query are
logged to stderr but do not halt the script.

Usage:
    python3 Production/scripts/where_are_we.py
    python3 Production/scripts/where_are_we.py --json
    python3 Production/scripts/where_are_we.py --recent-days 14
    python3 Production/scripts/where_are_we.py --no-modules
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
from lib.directus_admin_client import DirectusAdminClient, DirectusAdminError  # noqa: E402

# Severity ordering (LDs use UPPERCASE post-2026-05-04 enum migration; blockers use lowercase)
LD_SEVERITY_RANK = {"HARD": 5, "CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "SOFT": 1, "LOW": 1, None: 0, "": 0}
BLOCKER_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, None: 0, "": 0}


def _iso_to_short(s: str | None) -> str:
    if not s:
        return "-"
    try:
        # Directus returns "2026-05-10T16:21:14.976Z"
        return s.replace("T", " ").split(".")[0].rstrip("Z") + "Z"
    except Exception:
        return s[:19] if s else "-"


def _ago(s: str | None, now: datetime) -> str:
    if not s:
        return "-"
    try:
        ts = datetime.fromisoformat(s.replace("Z", "+00:00"))
        delta = now - ts
        if delta.total_seconds() < 60:
            return f"{int(delta.total_seconds())}s ago"
        if delta.total_seconds() < 3600:
            return f"{int(delta.total_seconds() / 60)}m ago"
        if delta.total_seconds() < 86400:
            return f"{int(delta.total_seconds() / 3600)}h ago"
        return f"{int(delta.total_seconds() / 86400)}d ago"
    except Exception:
        return s[:10]


def query_recent_lds(client: DirectusAdminClient, days: int) -> list[dict]:
    """Recently locked or amended LDs (default last 7 days), active only."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    rows = client.get_items(
        "prod_locked_decisions",
        filters={"date_locked": {"_gte": cutoff}, "status": {"_eq": "active"}},
    ) or []
    # Chronological sort: most-recently-locked first, then highest id (handles same-day ordering).
    # Severity is shown in the table column but doesn't drive ordering for "what just happened."
    rows.sort(key=lambda r: (r.get("date_locked") or "", r.get("id", 0)), reverse=True)
    return rows


def query_open_blockers(client: DirectusAdminClient) -> dict[str, list[dict]]:
    """Open blockers grouped by severity bucket."""
    rows = client.get_items("prod_blockers", filters={"is_resolved": {"_eq": False}}) or []
    grouped: dict[str, list[dict]] = {"critical": [], "high": [], "medium": [], "low": []}
    for r in rows:
        sev = (r.get("severity") or "").lower()
        if sev in grouped:
            grouped[sev].append(r)
        else:
            grouped.setdefault("other", []).append(r)
    for sev in grouped:
        grouped[sev].sort(key=lambda r: r.get("id", 0), reverse=True)
    return grouped


def query_active_shortcut_lds(client: DirectusAdminClient) -> list[dict]:
    """Active SHORTCUT_* LDs — closure-cap clock is running on each."""
    rows = client.get_items(
        "prod_locked_decisions",
        filters={"decision_key": {"_starts_with": "SHORTCUT_"}, "status": {"_eq": "active"}},
    ) or []
    rows.sort(key=lambda r: r.get("date_locked") or "", reverse=True)
    return rows


def query_recent_complete_events(client: DirectusAdminClient, hours: int = 48) -> list[dict]:
    """Recent action=*_complete events from prod_activity_log."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    # Directus filter on action _ends_with would be ideal but isn't always reliable on text;
    # use _contains as a wider net + Python filter for precision.
    rows = client.get_items(
        "prod_activity_log",
        filters={"created_at": {"_gte": cutoff}, "action": {"_contains": "complete"}},
    ) or []
    rows = [r for r in rows if (r.get("action") or "").lower().endswith("complete")]
    rows.sort(key=lambda r: r.get("id", 0), reverse=True)
    return rows[:15]


def query_latest_state_summary(client: DirectusAdminClient) -> dict | None:
    """Latest CROSS_SESSION_STATE_SUMMARY_* row (Rule 37 / LD-666)."""
    rows = client.get_items(
        "prod_activity_log",
        filters={"action": {"_starts_with": "CROSS_SESSION_STATE_SUMMARY_"}},
    ) or []
    if not rows:
        return None
    rows.sort(key=lambda r: r.get("id", 0), reverse=True)
    return rows[0]


def query_in_flight_specs(client: DirectusAdminClient, days: int = 14) -> list[dict]:
    """Recently registered or updated prod_reference_docs that are still current."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = client.get_items(
        "prod_reference_docs",
        filters={"is_current": {"_eq": True}, "created_at": {"_gte": cutoff}},
    ) or []
    rows.sort(key=lambda r: r.get("id", 0), reverse=True)
    return rows


def query_module_pipeline_distribution(client: DirectusAdminClient) -> dict[str, list[dict]]:
    """Modules grouped by current pipeline stage."""
    rows = client.get_items("prod_modules", filters=None) or []
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        stage = r.get("pipeline_stage") or r.get("current_stage") or "unknown"
        grouped.setdefault(stage, []).append(r)
    for stage in grouped:
        grouped[stage].sort(key=lambda r: r.get("m_number") or 99)
    return grouped


def render_markdown(snapshot: dict, args) -> str:
    now = snapshot["now"]
    out = []
    out.append(f"# MindfulNest Build Status — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    out.append("")
    out.append(f"_Live query from Directus. Generated in {snapshot['elapsed_ms']}ms._")
    out.append("")

    # Recent LDs
    lds = snapshot["recent_lds"]
    out.append(f"## Recent Locked Decisions ({args.recent_days}d)")
    out.append("")
    if lds:
        out.append("| LD | Severity | Locked | Key |")
        out.append("|---:|---|---|---|")
        for r in lds[:20]:
            out.append(
                f"| {r.get('id')} | {r.get('severity') or '-'} | "
                f"{r.get('date_locked') or '-'} | {r.get('decision_key', '')} |"
            )
        if len(lds) > 20:
            out.append(f"\n_+{len(lds) - 20} more (use `--recent-days {args.recent_days // 2}` to narrow)._")
    else:
        out.append("_(none)_")
    out.append("")

    # Open blockers grouped by severity
    blockers = snapshot["open_blockers"]
    total_open = sum(len(v) for v in blockers.values())
    out.append(f"## Open Blockers ({total_open} total)")
    out.append("")
    for sev_key, label in (("critical", "CRITICAL"), ("high", "HIGH"), ("medium", "MEDIUM"), ("low", "LOW")):
        bucket = blockers.get(sev_key, [])
        if not bucket:
            continue
        out.append(f"### {label} ({len(bucket)})")
        out.append("")
        for b in bucket[:15]:
            title = (b.get("title") or "")[:120]
            out.append(f"- **#{b.get('id')}** — {title}")
        if len(bucket) > 15:
            out.append(f"  _(+{len(bucket) - 15} more)_")
        out.append("")
    if blockers.get("other"):
        out.append(f"### OTHER severity ({len(blockers['other'])})")
        out.append("")
        for b in blockers["other"][:10]:
            out.append(f"- **#{b.get('id')}** [{b.get('severity')}] — {(b.get('title') or '')[:120]}")
        out.append("")

    # Active SHORTCUTs
    shortcuts = snapshot["active_shortcuts"]
    out.append(f"## Active SHORTCUT LDs ({len(shortcuts)})")
    out.append("")
    if shortcuts:
        for s in shortcuts:
            # date_locked is a YYYY-MM-DD string (not full ISO), so compute days-ago directly
            days_ago = "?"
            try:
                d = datetime.fromisoformat(s["date_locked"]).replace(tzinfo=timezone.utc)
                delta_days = (now - d).days
                days_ago = f"{delta_days}d ago" if delta_days > 0 else "today"
            except Exception:
                pass
            out.append(
                f"- **LD-{s.get('id')}** {s.get('decision_key', '')} — locked {s.get('date_locked') or '-'} ({days_ago})"
            )
    else:
        out.append("_(none — no active deferrals with closure caps)_")
    out.append("")

    # Recent _COMPLETE events
    completes = snapshot["recent_completes"]
    out.append("## Recent _COMPLETE Events (48h)")
    out.append("")
    if completes:
        for c in completes[:10]:
            out.append(
                f"- **id={c.get('id')}** `{c.get('action', '')}` — "
                f"{_iso_to_short(c.get('created_at'))} ({_ago(c.get('created_at'), now)})"
            )
    else:
        out.append("_(none in last 48h)_")
    out.append("")

    # Latest state-summary row
    summary = snapshot["latest_summary"]
    out.append("## Latest Cross-Session Snapshot (Rule 37)")
    out.append("")
    if summary:
        details = summary.get("details") or {}
        purpose = (details.get("purpose") or "")[:200] if isinstance(details, dict) else "-"
        out.append(f"- **id={summary.get('id')}** `{summary.get('action', '')}`")
        out.append(f"  - Created: {_iso_to_short(summary.get('created_at'))} ({_ago(summary.get('created_at'), now)})")
        out.append(f"  - Purpose: {purpose}")
        if isinstance(details, dict):
            nfa = (details.get("next_session_first_action") or "")[:300]
            if nfa:
                out.append(f"  - Next-session first action: {nfa}")
    else:
        out.append("_(no CROSS_SESSION_STATE_SUMMARY rows yet)_")
    out.append("")

    # In-flight specs
    specs = snapshot["in_flight_specs"]
    out.append(f"## In-Flight Reference Docs (last 14d, is_current=true)")
    out.append("")
    if specs:
        for s in specs[:15]:
            cat = s.get("doc_category") or "-"
            out.append(
                f"- **id={s.get('id')}** ({cat}) — {s.get('doc_title', '')} "
                f"[{_iso_to_short(s.get('created_at'))}]"
            )
    else:
        out.append("_(none in last 14d)_")
    out.append("")

    # Module pipeline distribution
    if not args.no_modules:
        modules = snapshot["module_distribution"]
        total_mods = sum(len(v) for v in modules.values())
        out.append(f"## Module Pipeline Distribution ({total_mods} modules)")
        out.append("")
        if modules:
            out.append("| Stage | Count | Modules |")
            out.append("|---|---:|---|")
            for stage in sorted(modules.keys()):
                bucket = modules[stage]
                names = ", ".join(
                    f"M{m.get('m_number')}/{m.get('creature_name', '?')}" for m in bucket[:6]
                )
                if len(bucket) > 6:
                    names += f", +{len(bucket) - 6}"
                out.append(f"| {stage} | {len(bucket)} | {names} |")
        else:
            out.append("_(no modules registered)_")
        out.append("")

    out.append("---")
    out.append("")
    out.append(
        f"_Source of truth: Directus production. Authority: LD `MASTER_ROADMAP_LIVE_QUERY_PATTERN_V1`._"
    )
    return "\n".join(out)


def build_snapshot(client: DirectusAdminClient, args) -> dict:
    t0 = time.monotonic()
    snapshot = {
        "now": datetime.now(timezone.utc),
        "recent_lds": [],
        "open_blockers": {},
        "active_shortcuts": [],
        "recent_completes": [],
        "latest_summary": None,
        "in_flight_specs": [],
        "module_distribution": {},
    }
    # Each query is independently fault-tolerant — one failure doesn't abort the rest
    queries = [
        ("recent_lds", lambda: query_recent_lds(client, args.recent_days)),
        ("open_blockers", lambda: query_open_blockers(client)),
        ("active_shortcuts", lambda: query_active_shortcut_lds(client)),
        ("recent_completes", lambda: query_recent_complete_events(client, hours=48)),
        ("latest_summary", lambda: query_latest_state_summary(client)),
        ("in_flight_specs", lambda: query_in_flight_specs(client, days=14)),
    ]
    if not args.no_modules:
        queries.append(("module_distribution", lambda: query_module_pipeline_distribution(client)))

    for name, fn in queries:
        try:
            snapshot[name] = fn()
        except (DirectusAdminError, RuntimeError) as e:
            print(f"[where_are_we] WARN: query '{name}' failed: {e}", file=sys.stderr)
            # Leave default empty value in snapshot

    snapshot["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
    return snapshot


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Live Directus query: current MindfulNest build status.",
    )
    ap.add_argument(
        "--json", action="store_true",
        help="Emit JSON instead of markdown (programmatic consumers)",
    )
    ap.add_argument(
        "--recent-days", type=int, default=7,
        help="Recency window for LD lookback (default 7)",
    )
    ap.add_argument(
        "--no-modules", action="store_true",
        help="Skip the module pipeline distribution section",
    )
    args = ap.parse_args()

    try:
        client = DirectusAdminClient()
    except (DirectusAdminError, RuntimeError) as e:
        print(f"[where_are_we] ERROR: Directus unreachable: {e}", file=sys.stderr)
        return 2

    snapshot = build_snapshot(client, args)

    if args.json:
        # Convert datetimes to ISO for JSON serialization
        snapshot["now"] = snapshot["now"].isoformat()
        print(json.dumps(snapshot, indent=2, default=str))
    else:
        print(render_markdown(snapshot, args))

    return 0


if __name__ == "__main__":
    sys.exit(main())
