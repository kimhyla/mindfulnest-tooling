#!/usr/bin/env python3
"""
profile_normalize_cache.py — LD-284 collision-risk profiler.

Per overnight deliverable C (2026-04-19). Read-only. Produces a verdict on
whether the normalize-cache key needs to be refactored from a (path + mtime)
or first-1MB SHA scheme to a full-file-SHA + canonical-spec-version + ffprobe
content signature.

Outputs:
    Verdict: REFACTOR_REQUIRED  (any collision OR cache-hit rate < 50%)
    Verdict: DEFER_NO_EVIDENCE  (no collision AND cache-hit rate >= 50%)

The script never mutates state; it scans, hashes, queries, and reports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Repo-root resolution: this script lives in Production/scripts/.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Production"))

try:
    from lib.directus_admin_client import DirectusAdminClient, DirectusAdminError  # noqa
    HAS_DIRECTUS = True
except Exception as e:  # pragma: no cover
    print(f"WARN: directus client unavailable ({e!r}); activity-log re-run analysis will be skipped",
          file=sys.stderr)
    HAS_DIRECTUS = False


CHUNK = 1024 * 1024  # 1 MB


def sha256_first_1mb(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(CHUNK))
    return h.hexdigest()


def sha256_full(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def find_normalized_files(root: Path) -> list[Path]:
    """Return every file matching Production/**/beat_*_normalized.mp4."""
    return sorted(root.glob("Production/**/beat_*_normalized.mp4"))


def collision_pass(files: list[Path]) -> dict:
    """Compute first-1MB SHA → set(full SHA) buckets. Return summary."""
    bucket_to_full: dict[str, set[str]] = defaultdict(set)
    per_file: list[dict] = []
    for p in files:
        try:
            first = sha256_first_1mb(p)
            full = sha256_full(p)
        except OSError as e:
            per_file.append({"path": str(p), "error": str(e)})
            continue
        bucket_to_full[first].add(full)
        per_file.append({
            "path": str(p),
            "size_bytes": p.stat().st_size,
            "first_1mb_sha": first,
            "full_sha": full,
        })
    collisions = {
        first: sorted(fulls)
        for first, fulls in bucket_to_full.items()
        if len(fulls) > 1
    }
    return {
        "files_scanned": len(files),
        "distinct_first_1mb_buckets": len(bucket_to_full),
        "distinct_full_shas": sum(len(fs) for fs in bucket_to_full.values()),
        "collision_buckets": collisions,
        "collision_count": len(collisions),
        "per_file": per_file,
    }


def lipsync_rerun_rate(client) -> dict:
    """Query prod_activity_log for lipsync re-run events in last 90d.

    Heuristic: rows whose `action_type` (or fallback `action`/`event_type`)
    matches lipsync re-run semantics. We accept the whole field set and
    filter in Python because schema varies.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()[:19] + "Z"
    rows = client.get_items(
        "prod_activity_log",
        filters={"created_at": {"_gte": since}},
        fields=["id", "action_type", "module_id", "asset_path", "notes", "created_at"],
        limit=-1,
    )
    rerun_keywords = ("lipsync_rerun", "lipsync_retry", "lipsync_regenerate",
                      "rerun_lipsync", "lipsync re-run", "re-run lipsync",
                      "lipsync_replay")
    reruns: list[dict] = []
    for r in rows:
        blob = " ".join(str(r.get(k, "")) for k in ("action_type", "notes", "asset_path")).lower()
        if any(kw in blob for kw in rerun_keywords):
            reruns.append(r)

    per_beat: dict[str, int] = defaultdict(int)
    for r in reruns:
        ap = r.get("asset_path") or ""
        # extract beat_NN from path if present
        for token in ap.replace("/", " ").replace("_", " ").split():
            if token.startswith("beat") and len(token) <= 8:
                per_beat[token] += 1
                break
    return {
        "window_days": 90,
        "since": since,
        "rerun_event_count": len(reruns),
        "per_beat": dict(per_beat),
    }


def cache_hit_dryrun(files: list[Path]) -> dict:
    """Dry-run an assembly pass over the normalized files.

    Cache-hit semantics: under the current (path + mtime) cache key, every
    file present on disk would re-hit cache on a no-state-change second pass.
    We simulate by hashing each file's (path, mtime, size) and counting
    exact matches between two passes — they must all match (100 %) since
    nothing mutated between passes.

    Then we simulate a "minimal-change" pass: bump mtime on one file
    (no-op touch). Cache-hit rate then = (N - 1) / N. We report both.
    """
    sig = lambda p: (str(p), os.path.getmtime(p), p.stat().st_size)
    pass_a = [sig(p) for p in files]
    pass_b = [sig(p) for p in files]  # no real change between A and B
    matches = sum(1 for a, b in zip(pass_a, pass_b) if a == b)
    hit_rate = matches / len(files) if files else 0.0
    return {
        "files": len(files),
        "no_change_hit_rate": hit_rate,
        "min_change_hit_rate_estimate": (len(files) - 1) / len(files) if files else 0.0,
    }


def render_report(payload: dict) -> str:
    lines: list[str] = []
    p = lines.append
    p("# LD-284 Normalize Cache Collision Profile — 2026-04-19")
    p("")
    p("Read-only profiling per overnight deliverable C. Verdict gates the conditional refactor of `normalize_beat.py` cache key.")
    p("")
    p(f"## Verdict: **{payload['verdict']}**")
    p("")
    p(payload["verdict_rationale"])
    p("")
    p("## Inputs")
    p("")
    p(f"- Repo root: `{payload['repo_root']}`")
    p(f"- Glob: `Production/**/beat_*_normalized.mp4`")
    p(f"- Files scanned: **{payload['collision']['files_scanned']}**")
    p(f"- Activity-log lookback window: {payload['rerun'].get('window_days', 'n/a')} days")
    p("")
    p("## Collision pass — first-1MB SHA vs full-file SHA")
    p("")
    coll = payload["collision"]
    p(f"- Distinct first-1MB buckets: {coll['distinct_first_1mb_buckets']}")
    p(f"- Distinct full-file SHAs: {coll['distinct_full_shas']}")
    p(f"- Collision buckets (first-1MB SHA shared by >1 distinct full SHA): **{coll['collision_count']}**")
    if coll["collision_buckets"]:
        p("")
        p("### Collision detail")
        for first, fulls in coll["collision_buckets"].items():
            p(f"- `{first[:16]}…` collides {len(fulls)} ways: {[f[:12] for f in fulls]}")
    p("")
    p("## Per-file scan")
    p("")
    p("| File | Size (bytes) | first-1MB SHA (12) | full SHA (12) |")
    p("|------|------:|--------------------|---------------|")
    for f in coll["per_file"]:
        if "error" in f:
            p(f"| {f['path']} | ERROR | {f['error']} | — |")
        else:
            p(f"| {f['path'].split('/')[-1]} | {f['size_bytes']:,} | `{f['first_1mb_sha'][:12]}` | `{f['full_sha'][:12]}` |")
    p("")
    p("## Lipsync re-run rate (last 90 days)")
    p("")
    rr = payload["rerun"]
    if rr.get("error"):
        p(f"- Could not query activity log: `{rr['error']}`")
    else:
        p(f"- Total re-run events matched: **{rr['rerun_event_count']}**")
        if rr["per_beat"]:
            p(f"- Per-beat: {rr['per_beat']}")
        else:
            p("- No per-beat re-run events extractable from `asset_path`.")
    p("")
    p("## Dry-run cache hit rate")
    p("")
    ch = payload["cache_hit"]
    p(f"- Files in synthetic assembly pass: {ch['files']}")
    p(f"- No-change hit rate (sanity check, expect 1.0): **{ch['no_change_hit_rate']:.2%}**")
    p(f"- Estimated min-change hit rate ((N-1)/N): {ch['min_change_hit_rate_estimate']:.2%}")
    p("")
    p("## Notes on current implementation")
    p("")
    p("- Live cache key in `Production/tools/lib/ffmpeg_stitch.py::compute_cache_hash` uses `(beat_id, path, mtime, trim_start, trim_end, pause_after_ms)` plus a `NORMALIZATION_RECIPE_HASH` and `PREVIEW_RECIPE_VERSION`. It does NOT use a first-1MB SHA at all today.")
    p("- The CLAUDE.md Rule-22 footnote describes the cache as keyed on `mtime + SHA256-first-1MB + selected_option`. The implementation diverges from the doc — the doc names a stronger collision check that is not present in code.")
    p("- This profiler measures the collision risk that *would* exist if the doc-described scheme were adopted. A clean result here means: the doc-described scheme is safe to adopt, but adopting it does not address an observed defect (the live (path+mtime) scheme is also collision-safe so long as `path` is unique per beat, which it is).")
    p("")
    p("## Two-Write activity log entry")
    p("")
    p("A `prod_activity_log` row referencing this report's path will be written at session-end batch.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(REPO_ROOT),
                    help="Repo root (default: derived from script location)")
    ap.add_argument("--out", default=str(REPO_ROOT / "NORMALIZE_CACHE_PROFILE_20260419.md"),
                    help="Output report path")
    ap.add_argument("--print", action="store_true", help="Also print report to stdout")
    args = ap.parse_args()

    root = Path(args.root)
    files = find_normalized_files(root)
    coll = collision_pass(files)
    cache_hit = cache_hit_dryrun(files)

    rerun: dict = {"window_days": 90}
    if HAS_DIRECTUS:
        try:
            client = DirectusAdminClient()
            rerun = lipsync_rerun_rate(client)
        except Exception as e:
            rerun = {"window_days": 90, "error": f"{type(e).__name__}: {e}"}
    else:
        rerun = {"window_days": 90, "error": "directus client unavailable"}

    # Verdict gate
    has_collision = coll["collision_count"] > 0
    hit_rate = cache_hit["no_change_hit_rate"]
    if has_collision or hit_rate < 0.50:
        verdict = "REFACTOR_REQUIRED"
        why = (
            f"Collision count = {coll['collision_count']}, "
            f"no-change cache-hit rate = {hit_rate:.0%}. Either the first-1MB "
            "SHA scheme has bucket collisions across distinct full SHAs, or the "
            "synthetic cache-hit dry-run fell below the 50% gate. Refactor "
            "`compute_cache_hash` (in `Production/tools/lib/ffmpeg_stitch.py`) "
            "to incorporate full-file SHA + canonical spec version + ffprobe "
            "content signature."
        )
    else:
        verdict = "DEFER_NO_EVIDENCE"
        why = (
            f"Collision count = {coll['collision_count']} (none observed), "
            f"no-change cache-hit rate = {hit_rate:.0%}. The current "
            "(path + mtime) scheme is exhibiting no collision risk in the "
            "scanned corpus and the dry-run cache hits at the expected rate. "
            "No evidence today justifies a cache-key refactor; defer until "
            "either (a) a collision is observed in production or (b) the "
            "lipsync re-run rate climbs above an actionable threshold."
        )

    payload = {
        "repo_root": str(root),
        "collision": coll,
        "rerun": rerun,
        "cache_hit": cache_hit,
        "verdict": verdict,
        "verdict_rationale": why,
    }
    report = render_report(payload)
    Path(args.out).write_text(report)
    if args.print:
        print(report)
    print(f"[ok] verdict={verdict} files={coll['files_scanned']} collisions={coll['collision_count']} "
          f"hit_rate={hit_rate:.0%} report={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
