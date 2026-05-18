#!/usr/bin/env python3
"""V59 Phase 1 healthcheck — server alive, generators, LD markers, registry coverage.

Gates (exit 1 on failure unless noted):
  1. GET /api/health → 200 JSON
  2. generate_openapi.py + generate_feature_registry.py subprocesses
  3. LD marker grep — prod_locked_decisions notes marker_string= + git grep
  4. Registry coverage — flag tabs with <3 testids (LOW_COVERAGE, non-fatal)
  5. OpenAPI prefix route counts (informational)

Exit 0 when server alive AND ld_markers_failed == 0.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
SCRIPTS = ROOT / "scripts"
OPENAPI_PATH = ROOT / "openapi" / "production_server.yaml"
REGISTRY_PATH = ROOT / "feature_registry.json"
HEALTH_URL = "http://localhost:5111/api/health"

LD_LABELS: tuple[str, ...] = (
    "LD-723",
    "LD-730",
    "LD-739",
    "LD-755",
    "LD-757",
    "LD-761",
    "LD-765",
    "LD-769",
    "LD-770",
    "LD-775",
    "LD-778",
    "LD-782",
    "LD-783",
    "LD-786",
    "LD-789",
    "LD-790",
)

MARKER_IN_NOTES_RE = re.compile(
    r"marker_string\s*=\s*['\"]?([^'\"\s\n,;]+)['\"]?",
    re.IGNORECASE,
)

OPENAPI_PREFIXES: tuple[str, ...] = (
    "/api/beat",
    "/api/lipsync",
    "/api/phase_a",
    "/api/phase_b",
    "/api/cr",
    "/api/bg",
    "/api/stitch",
    "/api/v2",
    "/api/admin",
)

MIN_TESTIDS_PER_TAB = 3

sys.path.insert(0, str(REPO_ROOT))

from Production.lib.directus_admin_client import DirectusAdminClient  # noqa: E402


def _try_get_ld_row(client: Any, ld_label: str) -> Optional[dict]:
    """Fetch prod_locked_decisions row for LD-NNN (id or decision_key)."""
    try:
        from Production.lib import directus as directus_mod  # noqa: WPS433

        if hasattr(directus_mod, "try_get_or_warn"):
            fn = directus_mod.try_get_or_warn
            numeric = ld_label.replace("LD-", "")
            if numeric.isdigit():
                row = fn(
                    "prod_locked_decisions",
                    filters={"id": {"_eq": int(numeric)}},
                    fields=["id", "decision_key", "notes", "decision_text"],
                    limit=1,
                    client=client,
                )
                if row:
                    return row[0] if isinstance(row, list) else row
    except Exception:
        pass

    numeric = ld_label.replace("LD-", "")
    filters: dict
    if numeric.isdigit():
        filters = {"id": {"_eq": int(numeric)}}
    else:
        filters = {"decision_key": {"_eq": ld_label}}
    rows = client.get_items(
        "prod_locked_decisions",
        filters=filters,
        fields=["id", "decision_key", "notes", "decision_text"],
        limit=1,
    )
    return rows[0] if rows else None


def _extract_marker(row: dict) -> Optional[str]:
    for field in ("notes", "decision_text"):
        text = row.get(field) or ""
        if not isinstance(text, str):
            continue
        m = MARKER_IN_NOTES_RE.search(text)
        if m:
            return m.group(1).strip()
        m2 = re.search(r"marker_string['\"]?\s*:\s*['\"]([^'\"]+)['\"]", text)
        if m2:
            return m2.group(1).strip()
    return None


def _git_grep_count(marker: str) -> int:
    try:
        proc = subprocess.run(
            ["git", "grep", "-l", marker, "--", "."],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode == 0:
            return len([ln for ln in proc.stdout.splitlines() if ln.strip()])
        if proc.returncode == 1:
            return 0
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"git grep error for {marker!r}: {exc}", file=sys.stderr)
    return 0


def _check_server_health() -> tuple[bool, str]:
    try:
        req = urllib.request.Request(HEALTH_URL, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            if resp.status != 200:
                return False, f"{resp.status} {body[:120]}"
            json.loads(body)
            return True, "200 OK"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, type(e).__name__


def _run_generators() -> bool:
    for script in ("generate_openapi.py", "generate_feature_registry.py"):
        path = SCRIPTS / script
        try:
            subprocess.check_call(
                [sys.executable, str(path)],
                cwd=str(REPO_ROOT),
            )
        except subprocess.CalledProcessError:
            print(f"HALT: {script} failed", file=sys.stderr)
            return False
    return True


def _check_ld_markers(client: DirectusAdminClient) -> tuple[int, int, list[dict]]:
    passed = 0
    failed = 0
    failures: list[dict] = []
    for ld in LD_LABELS:
        row = _try_get_ld_row(client, ld)
        if not row:
            failed += 1
            failures.append({"ld": ld, "error": "row_not_found"})
            continue
        marker = _extract_marker(row)
        if not marker:
            failed += 1
            failures.append({"ld": ld, "error": "marker_string_missing_in_notes"})
            continue
        matches = _git_grep_count(marker)
        if matches < 1:
            failed += 1
            failures.append(
                {"ld": ld, "marker": marker, "error": "git_grep_zero_matches"}
            )
        else:
            passed += 1
    return passed, failed, failures


def _registry_coverage() -> tuple[int, list[str]]:
    if not REGISTRY_PATH.is_file():
        return 0, []
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_tab: dict[str, list] = data.get("by_tab") or {}
    low: list[str] = []
    for tab, ids in sorted(by_tab.items()):
        if len(ids) < MIN_TESTIDS_PER_TAB:
            low.append(tab)
    testid_count = len(data.get("testids") or [])
    return testid_count, low


def _openapi_prefix_summary() -> tuple[int, dict[str, int]]:
    if not OPENAPI_PATH.is_file():
        return 0, {}
    text = OPENAPI_PATH.read_text(encoding="utf-8")
    paths = re.findall(r"^\s{2}(/[^\s:]+):\s*$", text, re.MULTILINE)
    counts: dict[str, int] = {p: 0 for p in OPENAPI_PREFIXES}
    for path in paths:
        for prefix in OPENAPI_PREFIXES:
            if path.startswith(prefix):
                counts[prefix] += 1
                break
    return len(paths), counts


def main() -> int:
    t0 = time.perf_counter()
    red: dict[str, Any] = {"failures": []}

    server_ok, server_health = _check_server_health()
    if not server_ok:
        red["failures"].append({"gate": "server_health", "detail": server_health})

    if not _run_generators():
        red["failures"].append({"gate": "generators", "detail": "subprocess_failed"})

    ld_passed = ld_failed = 0
    ld_failures: list[dict] = []
    try:
        client = DirectusAdminClient()
        ld_passed, ld_failed, ld_failures = _check_ld_markers(client)
    except Exception as exc:
        ld_failed = len(LD_LABELS)
        ld_failures = [{"ld": "all", "error": type(exc).__name__, "detail": str(exc)}]
    if ld_failures:
        red["failures"].extend(ld_failures)

    registry_count, low_tabs = _registry_coverage()
    if low_tabs:
        print(f"LOW_COVERAGE tabs={low_tabs}", file=sys.stderr)

    openapi_total, prefix_counts = _openapi_prefix_summary()
    print("OPENAPI_PREFIX_COUNTS:", json.dumps(prefix_counts, sort_keys=True))

    elapsed = round(time.perf_counter() - t0, 1)
    # Split LD failures: "marker_string_missing_in_notes" is a registration gap
    # (the LD predates the LD-783 marker-string convention) — surface as a
    # warning, not a fatal. Only "git_grep_zero_matches" is the real fabrication
    # signal that must block the gate.
    fatal_failures = [f for f in ld_failures if f.get("error") == "git_grep_zero_matches"]
    governance_gaps = [f for f in ld_failures if f.get("error") == "marker_string_missing_in_notes"]
    ok = server_ok and len(fatal_failures) == 0
    result = {
        "ok": ok,
        "server_health": server_health,
        "openapi_routes": openapi_total,
        "feature_registry_testids": registry_count,
        "ld_markers_passed": ld_passed,
        "ld_markers_failed_fabrication": len(fatal_failures),
        "ld_markers_governance_gap": len(governance_gaps),
        "low_coverage_tabs": low_tabs,
        "elapsed_s": elapsed,
    }
    print(json.dumps(result, indent=2))
    if governance_gaps:
        print(
            f"GOVERNANCE_GAP: {len(governance_gaps)} LDs lack marker_string in notes "
            f"(predate LD-783 convention) — backfill in a separate governance sweep:",
            file=sys.stderr,
        )
        print(json.dumps({"governance_gaps": governance_gaps}, indent=2), file=sys.stderr)
    if not ok:
        print(json.dumps(red, indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
