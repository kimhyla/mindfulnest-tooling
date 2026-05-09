"""
DS-24 pre-commit hook — false-positive flap detection.

Normative design: Production/docs/DS_23_24_25_MECHANICAL_GATE_TECH_SPEC_v3.md
§7.2 (preserved from v1+v2), §11.7 (halt mechanism PIN), §11.7-v3-C (3-tier escalation).

Behavior:
  - Reads prod_blockers feed once per process invocation (per-commit cache TTL).
  - For each staged file path:
      * If active DS_24_FP_LOOP_SUSPECTED_<F> blocker exists → emit
        DS_24_HALTED_BY_BLOCKER notice on stderr; SKIP DS-24 sweep for that
        file. Commit is NOT blocked at the hook level. (§11.7-v3-C Tier 1.)
      * Otherwise emit a per-file `DS_24_HALTED_BY_BLOCKER`-counterpart event
        (`DS_24_FP_EVENT`) to prod_activity_log so the weekly preflight audit
        has data for Tier 2 escalation aggregation (>3 halts/file/7d).
  - Tier 2 (>3 halts/file/7d) and Tier 3 (PR-merge gate) escalation is the
    weekly preflight audit's responsibility (§11.7-v3-C); this hook only
    surfaces per-commit observation rows the preflight aggregates.

Exit codes:
  0 — always (per §11.7 Tier 1: developer flow protected; commit is never
      blocked by DS-24 at the hook layer).

NO urllib/requests direct calls — uses DirectusAdminClient (DS-30).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

# Production root resolution
_PRODUCTION_ROOT = Path(__file__).resolve().parents[2]
if str(_PRODUCTION_ROOT) not in sys.path:
    sys.path.insert(0, str(_PRODUCTION_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_staged_files(repo_root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def fetch_active_halt_blockers(client: Optional[Any]) -> dict[str, dict]:
    """Return {file_path: row_dict} for active DS_24_FP_LOOP_SUSPECTED_<F> rows.

    Empty dict on offline / failure (graceful degradation per §11.7 Tier 1).
    """
    if client is None:
        return {}
    try:
        rows = client.get_items(
            "prod_blockers",
            filters={
                "blocker_type": {"_starts_with": "DS_24_FP_LOOP_SUSPECTED_"},
                "is_resolved": {"_eq": False},
            },
            fields=["id", "blocker_type"],
        )
    except Exception as exc:  # pragma: no cover — offline path
        sys.stderr.write(
            f"DS_24_HOOK_NOTICE: prod_blockers fetch failed ({type(exc).__name__}); "
            "halt list treated as empty.\n"
        )
        return {}

    out: dict[str, dict] = {}
    prefix = "DS_24_FP_LOOP_SUSPECTED_"
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        bt = row.get("blocker_type")
        if isinstance(bt, str) and bt.startswith(prefix):
            file_path = bt[len(prefix):]
            out[file_path] = row
    return out


def post_halt_event(
    client: Optional[Any],
    *,
    file_path: str,
    blocker_id: Any,
    commit_sha: Optional[str],
) -> bool:
    """POST DS_24_HALTED_BY_BLOCKER row to prod_activity_log.

    Per LD-597: only `action`, `details`, `performed_by`, `module_id` are
    permitted on prod_activity_log writes. Returns True on success, False on
    failure (e.g. offline). Failures are non-fatal (Tier 1: hook never blocks).

    Rule 35 (read-back-after-write): we POST then GET the created row to
    ensure visibility before exiting.
    """
    if client is None:
        return False

    payload = {
        "action": "DS_24_HALTED_BY_BLOCKER",
        "details": {
            "file_path": file_path,
            "blocker_id": blocker_id,
            "commit_sha": commit_sha,
        },
        "performed_by": "ds24_pre_commit_hook",
        "module_id": None,
    }
    try:
        created = client.post_item("prod_activity_log", payload, retry_post=True)
    except Exception as exc:  # pragma: no cover — offline path
        sys.stderr.write(
            f"DS_24_HOOK_NOTICE: activity-log POST failed ({type(exc).__name__}).\n"
        )
        return False

    if not isinstance(created, dict):
        return False
    item_id = created.get("id")
    if item_id is None:
        return False

    # Rule 35 read-back
    try:
        client.get_item("prod_activity_log", item_id)
    except Exception:  # pragma: no cover
        return False
    return True


def post_event_observation(
    client: Optional[Any],
    *,
    file_path: str,
    commit_sha: Optional[str],
) -> bool:
    """POST DS_24_FP_EVENT observation row.

    Used for Tier 2 aggregation: weekly_preflight_audit reads events in 7-day
    rolling window and writes the DS_24_FP_LOOP_SUSPECTED_<F> blocker when
    threshold breached. Hook itself does NOT write blockers (§11.7 step 2).
    """
    if client is None:
        return False
    payload = {
        "action": "DS_24_FP_EVENT",
        "details": {"file_path": file_path, "commit_sha": commit_sha},
        "performed_by": "ds24_pre_commit_hook",
        "module_id": None,
    }
    try:
        created = client.post_item("prod_activity_log", payload, retry_post=True)
    except Exception:  # pragma: no cover
        return False
    if not isinstance(created, dict):
        return False
    item_id = created.get("id")
    if item_id is None:
        return False
    try:
        client.get_item("prod_activity_log", item_id)
    except Exception:  # pragma: no cover
        return False
    return True


# ---------------------------------------------------------------------------
# Core gate — pure function for tests; CLI is thin wrapper.
# ---------------------------------------------------------------------------


class HookOutcome:
    """Structured outcome for tests + CLI exit-mapping."""

    __slots__ = (
        "exit_code",
        "halted_files",
        "observed_files",
        "stderr_lines",
        "halt_event_writes",
        "observation_writes",
    )

    def __init__(
        self,
        exit_code: int,
        halted_files: list[str],
        observed_files: list[str],
        stderr_lines: list[str],
        halt_event_writes: int,
        observation_writes: int,
    ) -> None:
        self.exit_code = exit_code
        self.halted_files = halted_files
        self.observed_files = observed_files
        self.stderr_lines = stderr_lines
        self.halt_event_writes = halt_event_writes
        self.observation_writes = observation_writes


def run_hook(
    *,
    staged_files: list[str],
    halt_blockers: dict[str, dict],
    commit_sha: Optional[str],
    halt_writer,
    observation_writer,
) -> HookOutcome:
    """Execute the per-commit DS-24 hook contract.

    Args:
        staged_files: paths from `git diff --cached --name-only`.
        halt_blockers: {file_path: blocker_row} from fetch_active_halt_blockers.
        commit_sha: HEAD SHA (or None when not yet committed).
        halt_writer: callable(file_path, blocker_id, commit_sha) -> bool.
        observation_writer: callable(file_path, commit_sha) -> bool.

    Returns: HookOutcome (exit_code is always 0 — Tier 1 protects flow).
    """
    halted: list[str] = []
    observed: list[str] = []
    stderr_lines: list[str] = []
    halt_writes = 0
    obs_writes = 0

    for staged in staged_files:
        if staged in halt_blockers:
            row = halt_blockers[staged]
            blocker_id = row.get("id")
            halted.append(staged)
            stderr_lines.append(
                f"DS_24_HALTED_BY_BLOCKER: {staged} skipped from DS-24 sweep "
                f"per active prod_blockers row (id={blocker_id})"
            )
            ok = halt_writer(staged, blocker_id, commit_sha)
            if ok:
                halt_writes += 1
        else:
            observed.append(staged)
            ok = observation_writer(staged, commit_sha)
            if ok:
                obs_writes += 1

    return HookOutcome(
        exit_code=0,
        halted_files=halted,
        observed_files=observed,
        stderr_lines=stderr_lines,
        halt_event_writes=halt_writes,
        observation_writes=obs_writes,
    )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def _resolve_repo_root() -> Path:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd()


def _resolve_head_sha(repo_root: Path) -> Optional[str]:
    """Best-effort HEAD SHA — `git rev-parse HEAD`. None when unavailable."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            check=False,
        )
        if proc.returncode == 0:
            sha = proc.stdout.strip()
            return sha or None
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def _build_client():
    try:
        from lib.directus_admin_client import DirectusAdminClient

        return DirectusAdminClient()
    except Exception as exc:
        sys.stderr.write(
            f"DS_24_HOOK_NOTICE: DirectusAdminClient unavailable ({type(exc).__name__}); "
            "halt list treated as empty.\n"
        )
        return None


def main(argv: list[str]) -> int:
    # MN_SKIP_DS24_GATE provides escape hatch (mirrors MN_SKIP_DS23_GATE).
    if os.environ.get("MN_SKIP_DS24_GATE") == "1":
        sys.stderr.write(
            "DS_24_HOOK_NOTICE: MN_SKIP_DS24_GATE=1 — hook bypassed.\n"
        )
        return 0

    repo_root = _resolve_repo_root()
    staged = _get_staged_files(repo_root)
    if not staged:
        return 0

    client = _build_client()
    halt_blockers = fetch_active_halt_blockers(client)
    commit_sha = _resolve_head_sha(repo_root)

    def halt_writer(fp, bid, sha):
        return post_halt_event(client, file_path=fp, blocker_id=bid, commit_sha=sha)

    def observation_writer(fp, sha):
        return post_event_observation(client, file_path=fp, commit_sha=sha)

    outcome = run_hook(
        staged_files=staged,
        halt_blockers=halt_blockers,
        commit_sha=commit_sha,
        halt_writer=halt_writer,
        observation_writer=observation_writer,
    )

    for line in outcome.stderr_lines:
        sys.stderr.write(line + "\n")

    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
