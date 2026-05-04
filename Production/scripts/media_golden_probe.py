#!/usr/bin/env python3
"""
Media golden probe for FFmpeg/lipsync outputs (Phase 6.8 gate).

Compares a candidate media file against a known-good golden file and asserts:
  1. Duration tolerance ≤ ±50 ms vs golden
  2. Frame rate exactly 24 fps (avg_frame_rate AND r_frame_rate)
  3. A/V sync drift < 100 ms (start-time + end-time drift)
  4. Loudness within ±1.0 dBFS of target
  5. No B-frames (has_b_frames = 0)
  6. Zero decode errors (ffmpeg -v error pass)

Usage — specify golden by path:
  python3 Production/scripts/media_golden_probe.py \\
    --candidate out.mp4 \\
    --golden golden.mp4 \\
    --target-dbfs -16.0

Usage — specify golden by Directus prod_assets id (preferred):
  python3 Production/scripts/media_golden_probe.py \\
    --candidate out.mp4 \\
    --asset-id 42 \\
    --target-dbfs -16.0

  Queries prod_assets where id=<asset-id> AND kim_verdict='approved',
  uses the registered file_path as the golden. HARD STOP if Directus
  unreachable, no approved row found, file_path empty, or file not on disk.

Exit 0 on full PASS, exit 1 on any failure.

Requires: ffmpeg + ffprobe on PATH.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ProbeResult:
    checks: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)


def run_cmd(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
    )


def ffprobe_json(path: str) -> Dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,r_frame_rate,avg_frame_rate,"
        "start_time,duration,has_b_frames",
        "-of", "json",
        path,
    ]
    cp = run_cmd(cmd)
    if cp.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path!r}: {cp.stderr.strip()}")
    try:
        return json.loads(cp.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid ffprobe JSON for {path!r}") from exc


def parse_rate(rate_str: str) -> float:
    if not rate_str or rate_str == "0/0":
        return 0.0
    return float(Fraction(rate_str))


def get_stream(meta: Dict[str, Any], stream_type: str) -> Optional[Dict[str, Any]]:
    for s in meta.get("streams", []):
        if s.get("codec_type") == stream_type:
            return s
    return None


def to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def extract_mean_volume_dbfs(path: str) -> float:
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", path,
        "-af", "volumedetect",
        "-f", "null",
        "-",
    ]
    cp = run_cmd(cmd)
    # volumedetect outputs to stderr even with -v error in some builds
    output = f"{cp.stdout}\n{cp.stderr}"
    m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", output)
    if not m:
        raise RuntimeError(
            f"Could not parse mean_volume from ffmpeg volumedetect for {path!r}"
        )
    return float(m.group(1))


def count_decode_errors(path: str) -> int:
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"]
    cp = run_cmd(cmd)
    err = cp.stderr.strip()
    if not err:
        return 0
    return len([ln for ln in err.splitlines() if ln.strip()])


def probe_file(path: str, result: ProbeResult, target_dbfs: float, golden_duration: Optional[float]) -> None:
    meta = ffprobe_json(path)
    duration = to_float(meta.get("format", {}).get("duration"))

    # 1. Duration vs golden
    if golden_duration is not None:
        delta = abs(duration - golden_duration)
        if delta <= 0.050:
            result.checks.append(f"duration PASS  delta={delta:.6f}s (≤0.050s)")
        else:
            result.failures.append(
                f"duration FAIL  delta={delta:.6f}s exceeds ±50ms ceiling"
            )

    video = get_stream(meta, "video")
    audio = get_stream(meta, "audio")

    if video is None:
        result.failures.append("stream FAIL  no video stream found in candidate")
    if audio is None:
        result.failures.append("stream FAIL  no audio stream found in candidate")

    if video is not None:
        # 2. Frame rate — both avg and r must be exactly 24.000000
        fps_avg = parse_rate(str(video.get("avg_frame_rate", "0/0")))
        fps_r = parse_rate(str(video.get("r_frame_rate", "0/0")))
        if (
            math.isclose(fps_avg, 24.0, rel_tol=0.0, abs_tol=1e-6)
            and math.isclose(fps_r, 24.0, rel_tol=0.0, abs_tol=1e-6)
        ):
            result.checks.append(
                f"fps PASS  avg_frame_rate={fps_avg:.6f}, r_frame_rate={fps_r:.6f}"
            )
        else:
            result.failures.append(
                f"fps FAIL  avg={fps_avg:.6f}, r={fps_r:.6f} — both must equal exactly 24.000000"
            )

        # 5. B-frames
        has_b = int(video.get("has_b_frames", 0))
        if has_b == 0:
            result.checks.append("bframes PASS  has_b_frames=0")
        else:
            result.failures.append(f"bframes FAIL  has_b_frames={has_b} (must be 0)")

    if video is not None and audio is not None:
        # 3. A/V sync drift (start-time delta + end-time delta, take max)
        v_start = to_float(video.get("start_time", 0.0))
        a_start = to_float(audio.get("start_time", 0.0))
        start_drift = abs(v_start - a_start)

        v_dur = to_float(video.get("duration", duration))
        a_dur = to_float(audio.get("duration", duration))
        end_drift = abs((v_start + v_dur) - (a_start + a_dur))

        av_drift = max(start_drift, end_drift)
        if av_drift < 0.100:
            result.checks.append(f"av_sync PASS  drift={av_drift:.6f}s (<100ms)")
        else:
            result.failures.append(
                f"av_sync FAIL  drift={av_drift:.6f}s (≥100ms ceiling)"
            )

    # 4. Loudness
    mean_dbfs = extract_mean_volume_dbfs(path)
    loudness_delta = abs(mean_dbfs - target_dbfs)
    if loudness_delta <= 1.0:
        result.checks.append(
            f"loudness PASS  mean={mean_dbfs:.2f}dBFS, "
            f"target={target_dbfs:.2f}dBFS, delta={loudness_delta:.2f}dB"
        )
    else:
        result.failures.append(
            f"loudness FAIL  mean={mean_dbfs:.2f}dBFS, "
            f"target={target_dbfs:.2f}dBFS, delta={loudness_delta:.2f}dB (>±1.0dB)"
        )

    # 6. Decode errors
    dec_errs = count_decode_errors(path)
    if dec_errs == 0:
        result.checks.append("decode PASS  zero decode errors")
    else:
        result.failures.append(f"decode FAIL  {dec_errs} decode error line(s) detected")


def fetch_golden_from_directus(asset_id: int) -> str:
    """Query prod_assets for the approved golden file path by id."""
    lib_path = Path(__file__).resolve().parent.parent / "lib"
    sys.path.insert(0, str(lib_path))
    try:
        from directus_admin_client import DirectusAdminClient, DirectusAdminError
    except ImportError as exc:
        raise RuntimeError(
            f"Cannot import directus_admin_client from {lib_path} — "
            f"ensure Production/lib/ is present: {exc}"
        ) from exc

    client = DirectusAdminClient()
    url = (
        f"/items/prod_assets"
        f"?filter[id][_eq]={asset_id}"
        f"&filter[kim_verdict][_eq]=approved"
        f"&limit=1"
        f"&fields=id,asset_name,file_path,kim_verdict"
    )
    try:
        raw = client._request("GET", url)
        data = raw if isinstance(raw, list) else []
    except DirectusAdminError as exc:
        raise RuntimeError(
            f"Directus unreachable while fetching prod_assets id={asset_id}: {exc}\n"
            f"Fix connection or pass --golden <path> directly."
        ) from exc

    if not data:
        raise RuntimeError(
            f"No approved asset found in prod_assets with id={asset_id}.\n"
            f"Check: (1) id is correct, (2) kim_verdict='approved' is set in Directus."
        )

    row = data[0]
    file_path = (row.get("file_path") or "").strip()
    if not file_path:
        raise RuntimeError(
            f"prod_assets row id={asset_id} has no file_path set.\n"
            f"Register the file path in Directus before using --asset-id."
        )

    if not Path(file_path).exists():
        raise RuntimeError(
            f"Golden file from Directus does not exist on disk: {file_path!r}\n"
            f"Check that the file is synced from Dropbox (open folder in Finder to trigger sync)."
        )

    asset_name = row.get("asset_name", f"id={asset_id}")
    print(f"Golden resolved from Directus: {asset_name!r} → {file_path}")
    return file_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Media golden probe — Phase 6.8 gate"
    )
    parser.add_argument("--candidate", required=True, help="Path to candidate MP4")

    golden_group = parser.add_mutually_exclusive_group(required=True)
    golden_group.add_argument(
        "--golden",
        help="Path to golden/approved MP4 (direct path)",
    )
    golden_group.add_argument(
        "--asset-id",
        type=int,
        metavar="PROD_ASSETS_ID",
        help=(
            "Directus prod_assets id of the approved golden file. "
            "Queries prod_assets where id=N AND kim_verdict='approved' "
            "and uses the registered file_path. HARD STOP if not found."
        ),
    )

    parser.add_argument(
        "--target-dbfs",
        required=True,
        type=float,
        help="Target mean loudness in dBFS (e.g. -16.0)",
    )
    args = parser.parse_args()

    # Resolve golden path — either direct or via Directus
    if args.asset_id is not None:
        try:
            golden_path = fetch_golden_from_directus(args.asset_id)
        except RuntimeError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        golden_path = args.golden

    result = ProbeResult()

    # Probe golden to get reference duration
    golden_meta = ffprobe_json(golden_path)
    golden_duration = to_float(golden_meta.get("format", {}).get("duration"))

    # Probe candidate
    probe_file(args.candidate, result, args.target_dbfs, golden_duration)  # type: ignore[arg-type]

    # Report
    for line in result.checks:
        print(line)

    if result.failures:
        for line in result.failures:
            print(line, file=sys.stderr)
        print(
            f"\nFAIL: media golden probe — {len(result.failures)} assertion(s) failed.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"\nPASS: media golden probe clean — "
        f"{len(result.checks)} assertion(s) passed "
        f"(duration/fps/AV-sync/loudness/B-frames/decode)."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
