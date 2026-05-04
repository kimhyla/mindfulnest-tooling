"""Post-test decision record writer for LD-204.

Usage:
  python3 11_decision_record.py \
    --feel-score 7 --workflow-speed true --drag-drop-robust true \
    --webhook-refresh true --kanban-paint true \
    --verdict commit_option_c \
    --notes "..."
"""
from __future__ import annotations
import sys, argparse, json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import hosted, TASK_ID, PREFLIGHT_ID, ORIGINAL_PREFLIGHT_ID, LD_ID  # type: ignore


VERDICTS = {
    "commit_option_c",
    "fall_back_option_a",
    "escalate_option_d_retool",
    "iterate_prototype",
}


def _bool(s: str) -> bool:
    return str(s).lower() in ("true", "1", "yes", "y", "t")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workflow-speed", required=True)
    p.add_argument("--drag-drop-robust", required=True)
    p.add_argument("--webhook-refresh", required=True)
    p.add_argument("--kanban-paint", required=True)
    p.add_argument("--feel-score", type=int, required=True)
    p.add_argument("--verdict", required=True, choices=sorted(VERDICTS))
    p.add_argument("--kim-hours", type=float, default=2.0)
    p.add_argument("--claude-hours", type=float, default=1.0)
    p.add_argument("--spend-usd", type=float, default=0.45)
    p.add_argument("--notes", default="")
    args = p.parse_args()

    scorecard = {
        "workflow_speed_under_5min": _bool(args.workflow_speed),
        "drag_drop_robust": _bool(args.drag_drop_robust),
        "webhook_refresh_under_10s": _bool(args.webhook_refresh),
        "kanban_paint_under_3s": _bool(args.kanban_paint),
        "feel_score_7_or_higher_after_2hrs": args.feel_score,
    }

    c = hosted()

    # Find Luna module_id
    modules = c.get("prod_modules", filters={"m_number": 2}, limit=1)
    module_id = modules[0]["id"] if modules else 0

    details = {
        "task_id": TASK_ID,
        "activity_type": "prototype_completion",
        "linked_preflight_id": PREFLIGHT_ID,
        "linked_original_preflight_id": ORIGINAL_PREFLIGHT_ID,
        "linked_decision_id": LD_ID,
        "exit_criteria_scorecard": scorecard,
        "kim_verdict": args.verdict,
        "actual_claude_hours": args.claude_hours,
        "actual_kim_hours": args.kim_hours,
        "actual_spend_usd": args.spend_usd,
        "notes": args.notes,
    }

    log = c.log_activity(
        module_id=module_id,
        action=f"option_c_prototype_{args.verdict}",
        details=details,
        performed_by="kim+claude-opus-4-7",
        kim_verdict=("approved" if args.verdict == "commit_option_c" else "rejected"),
        kim_feedback=args.notes or None,
    )
    print(f"Wrote decision record: prod_activity_log id={log['id']}")

    # Update LD-204 status depending on verdict
    if args.verdict == "commit_option_c":
        c.update("prod_locked_decisions", LD_ID, {"status": "validated"})
        print(f"LD-{LD_ID} status -> validated")
    elif args.verdict in ("fall_back_option_a", "escalate_option_d_retool"):
        c.update("prod_locked_decisions", LD_ID, {"status": "superseded"})
        print(f"LD-{LD_ID} status -> superseded (next action: {args.verdict})")
    else:  # iterate_prototype
        c.update("prod_locked_decisions", LD_ID, {"status": "iterating"})
        print(f"LD-{LD_ID} status -> iterating")


if __name__ == "__main__":
    main()
