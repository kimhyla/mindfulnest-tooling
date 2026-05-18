#!/usr/bin/env python3
"""Replay handler routes and diff against baseline — V59 Phase 4-prep.

Re-probes every OpenAPI route with the same stub payloads as
capture_handler_replay_baseline.py and compares fingerprints.

Exit 0 when diffs == 0; exit 1 otherwise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import capture_handler_replay_baseline as baseline_mod  # noqa: E402

ROOT = baseline_mod.ROOT
BASELINE_PATH = baseline_mod.BASELINE_PATH


def _is_skipped(fp: dict[str, Any]) -> bool:
    return fp.get("status") == "skipped"


def _http_status(fp: dict[str, Any]) -> int | None:
    status = fp.get("status")
    return status if isinstance(status, int) else None


def _consistent_5xx(baseline: dict[str, Any], replay: dict[str, Any]) -> bool:
    b_status = _http_status(baseline)
    r_status = _http_status(replay)
    if b_status is None or r_status is None:
        return False
    if b_status < 500 or r_status < 500:
        return False
    return (
        baseline.get("body_sha256") == replay.get("body_sha256")
        and baseline.get("content_type") == replay.get("content_type")
    )


def _body_len_diff_significant(baseline_len: int, replay_len: int) -> bool:
    if baseline_len == replay_len:
        return False
    denom = max(baseline_len, 1)
    return abs(replay_len - baseline_len) / denom > 0.05


def compare_fingerprints(
    baseline: dict[str, Any],
    replay: dict[str, Any],
    *,
    method: str,
    path: str,
) -> list[dict[str, Any]]:
    """Return diff records for one route (empty if match)."""
    if _is_skipped(baseline) or _is_skipped(replay):
        return []

    if _consistent_5xx(baseline, replay):
        return []

    diffs: list[dict[str, Any]] = []

    b_status = baseline.get("status")
    r_status = replay.get("status")
    if b_status != r_status:
        diffs.append(
            {
                "method": method,
                "path": path,
                "field": "status",
                "baseline": b_status,
                "replay": r_status,
            }
        )

    b_sha = baseline.get("body_sha256")
    r_sha = replay.get("body_sha256")
    b_len = baseline.get("body_len", 0)
    r_len = replay.get("body_len", 0)

    if b_sha != r_sha:
        entry: dict[str, Any] = {
            "method": method,
            "path": path,
            "field": "body_sha256",
            "baseline": b_sha,
            "replay": r_sha,
        }
        if b_len is not None or r_len is not None:
            entry["baseline_len"] = b_len
            entry["replay_len"] = r_len
        diffs.append(entry)

    b_ct = baseline.get("content_type")
    r_ct = replay.get("content_type")
    if b_ct != r_ct:
        diffs.append(
            {
                "method": method,
                "path": path,
                "field": "content_type",
                "baseline": b_ct,
                "replay": r_ct,
            }
        )

    if (
        b_sha != r_sha
        and isinstance(b_len, int)
        and isinstance(r_len, int)
        and _body_len_diff_significant(b_len, r_len)
    ):
        diffs.append(
            {
                "method": method,
                "path": path,
                "field": "body_len",
                "baseline": b_len,
                "replay": r_len,
            }
        )

    return diffs


def run_diff(
    baseline_data: dict[str, dict[str, Any]] | None = None,
    *,
    baseline_path: Path | None = None,
) -> dict[str, Any]:
    path = baseline_path or BASELINE_PATH
    if baseline_data is None:
        if not path.is_file():
            raise FileNotFoundError(f"baseline not found: {path}")
        baseline_data = json.loads(path.read_text(encoding="utf-8"))

    routes = baseline_mod.load_openapi_routes()
    replay_data = baseline_mod.collect_fingerprints(routes)

    all_keys = sorted(set(baseline_data) | set(replay_data))
    diffs_detail: list[dict[str, Any]] = []
    matched = 0
    skipped = 0

    for key in all_keys:
        method, path = baseline_mod.parse_key(key)
        b_fp = baseline_data.get(key, {"status": "error", "reason": "missing in baseline"})
        r_fp = replay_data.get(key, {"status": "error", "reason": "missing in replay"})

        if _is_skipped(b_fp) or _is_skipped(r_fp):
            skipped += 1
            continue

        route_diffs = compare_fingerprints(b_fp, r_fp, method=method, path=path)
        if route_diffs:
            diffs_detail.extend(route_diffs)
        else:
            matched += 1

    total = len(all_keys)
    result = {
        "ok": len(diffs_detail) == 0,
        "total": total,
        "matched": matched,
        "diffs": len({(d["method"], d["path"]) for d in diffs_detail}),
        "skipped": skipped,
        "diffs_detail": diffs_detail,
    }
    return result


def main() -> int:
    try:
        result = run_diff()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["diffs"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
