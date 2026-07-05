#!/usr/bin/env python3
"""Post-bake Phase B preview: optional pause-interior seam + freeze hold insert.

ON-DEMAND OPERATOR TOOL ONLY — not wired to Send to Stitcher, phase export, or CI.
Run manually (or ask the agent to run) when a baked ``phase_b`` preview needs extra
meditation hold time at a specific timestamp.

``--update-stitch-job`` is opt-in: it points an *existing* stitch slot at the new
file after you explicitly pass the flag. Nothing runs automatically on export.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
_CRED = TOOLS / "credentials_lib"
if str(_CRED) not in sys.path:
    sys.path.insert(0, str(_CRED))

from credentials_lib.ffmpeg_stitch import (  # noqa: E402
    STITCH_EXPORT_AV_MAX_DRIFT_S,
    av_duration_drift_s,
    ffprobe_duration,
)

PHASE_B_PREVIEW_HOLD_INSERT_V1 = "PHASE_B_PREVIEW_HOLD_INSERT_V1"
DEFAULT_FADE_S = 0.30
DEFAULT_MAX_DRIFT_S = STITCH_EXPORT_AV_MAX_DRIFT_S
# Hold freeze must not be sampled during a seam fade-to-black tail/head.
HOLD_FRAME_MIN_LUMA = 12.0
HOLD_SEAM_INSERT_MIN_GAP_S = DEFAULT_FADE_S + 0.05

ENC = [
    "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-r", "24", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "1", "-movflags", "+faststart",
]


@dataclass(frozen=True)
class SeamSpec:
    out_s: float
    in_s: float
    label: str = ""


@dataclass(frozen=True)
class HoldResult:
    output: Path
    duration_s: float
    duration_ms: int
    av_drift_s: float
    manifest_path: Path


def _run_ffmpeg(cmd: list[str], *, label: str) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-4000:]
        raise RuntimeError(f"{label} failed:\n{tail}")


def mean_frame_luma(frame_png: Path) -> float:
    """Mean grayscale luma 0–255 for hold-frame brightness gate."""
    raw = subprocess.check_output([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", str(frame_png),
        "-vf", "format=gray,scale=1:1,format=rgb24",
        "-frames:v", "1", "-f", "rawvideo", "pipe:1",
    ])
    if len(raw) < 3:
        raise RuntimeError(f"could not sample luma from {frame_png.name}")
    return (raw[0] + raw[1] + raw[2]) / 3.0


def validate_seams_vs_hold_insert(seams: list[SeamSpec], *, insert_at_s: float) -> None:
    """Seam out-point and hold insert are independent — never co-locate them."""
    for seam in seams:
        gap = insert_at_s - seam.out_s
        if abs(gap) < HOLD_SEAM_INSERT_MIN_GAP_S:
            raise ValueError(
                f"seam out {seam.out_s}s is only {gap:.3f}s from hold insert {insert_at_s}s; "
                "the fade-to-black tail would darken the freeze hold. "
                "Keep the watercolor/pause-interior seam earlier (e.g. 149.85) and "
                "insert the hold later (e.g. 150.4) on the already-spliced preview.",
            )
        if seam.out_s > insert_at_s:
            raise ValueError(
                f"seam out {seam.out_s}s is after hold insert {insert_at_s}s — "
                "apply pause-interior seams before the hold point only",
            )


def probe_stream_durations(path: Path) -> tuple[float, float]:
    def one(st: str) -> float:
        raw = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", st,
            "-show_entries", "stream=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ], text=True).strip()
        return float(raw) if raw else 0.0

    return one("v:0"), one("a:0")


def production_rel_path(path: Path, *, production_root: Path) -> str:
    resolved = path.resolve()
    prod = production_root.resolve()
    try:
        rel = resolved.relative_to(prod)
        return f"Production/{rel.as_posix()}"
    except ValueError:
        return resolved.as_posix()


def drift_within_gate(drift_s: float, *, max_drift_s: float = DEFAULT_MAX_DRIFT_S) -> bool:
    return drift_s <= max_drift_s


def render_pause_interior_segment(
    src: Path,
    dest: Path,
    *,
    start_s: float,
    end_s: float,
    fade_out: bool,
    fade_in: bool,
    fade_s: float = DEFAULT_FADE_S,
) -> None:
    dur = max(0.04, end_s - start_s)
    fade_in_vf = f"fade=t=in:st=0:d={fade_s}:color=black," if fade_in and dur > fade_s else ""
    fade_out_vf = (
        f"fade=t=out:st={dur - fade_s:.6f}:d={fade_s}:color=black," if fade_out and dur > fade_s else ""
    )
    vf = f"{fade_in_vf}{fade_out_vf}format=yuv420p"
    af_in = f"afade=t=in:st=0:d={fade_s}," if fade_in and dur > fade_s else ""
    af_out = f"afade=t=out:st={dur - fade_s:.6f}:d={fade_s}," if fade_out and dur > fade_s else ""
    af = f"{af_in}{af_out}aresample=48000,aformat=channel_layouts=mono"
    _run_ffmpeg([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start_s:.6f}", "-i", str(src), "-t", f"{dur:.6f}",
        "-vf", vf, "-af", af,
        *ENC,
        str(dest),
    ], label=f"segment {dest.name}")


def splice_pause_interior(
    src: Path,
    dest: Path,
    seam: SeamSpec,
    *,
    work_dir: Path,
    fade_s: float = DEFAULT_FADE_S,
) -> None:
    src_dur = ffprobe_duration(src)
    if seam.out_s <= 0 or seam.in_s <= seam.out_s or seam.in_s >= src_dur:
        raise ValueError(f"invalid seam out={seam.out_s} in={seam.in_s} src_dur={src_dur:.3f}")
    work_dir.mkdir(parents=True, exist_ok=True)
    seg_a = work_dir / f"seam_a_{seam.out_s:.3f}.mp4"
    seg_b = work_dir / f"seam_b_{seam.in_s:.3f}.mp4"
    render_pause_interior_segment(
        src, seg_a, start_s=0.0, end_s=seam.out_s, fade_out=True, fade_in=False, fade_s=fade_s,
    )
    render_pause_interior_segment(
        src, seg_b, start_s=seam.in_s, end_s=src_dur, fade_out=False, fade_in=True, fade_s=fade_s,
    )
    lst = work_dir / f"concat_{dest.stem}.txt"
    lst.write_text(f"file '{seg_a}'\nfile '{seg_b}'\n", encoding="utf-8")
    _run_ffmpeg([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(lst),
        "-c", "copy", "-movflags", "+faststart", str(dest),
    ], label=f"splice {dest.name}")


def capture_hold_frame(src: Path, insert_at_s: float, frame: Path) -> float:
    """Extract one freeze frame; return mean luma for brightness gate."""
    _run_ffmpeg([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{insert_at_s:.6f}", "-i", str(src), "-frames:v", "1", str(frame),
    ], label="hold frame capture")
    luma = mean_frame_luma(frame)
    if luma < HOLD_FRAME_MIN_LUMA:
        raise RuntimeError(
            f"hold frame at {insert_at_s}s is too dark (mean_luma={luma:.1f} < {HOLD_FRAME_MIN_LUMA}); "
            "likely sampled during a seam fade-to-black — use an earlier seam out-point "
            "or a source that already has the watercolor card removed",
        )
    return luma


def insert_freeze_hold(
    src: Path,
    dest: Path,
    *,
    insert_at_s: float,
    hold_s: float,
    work_dir: Path,
    hold_frame_src: Path | None = None,
    hold_frame_at_s: float | None = None,
) -> None:
    if hold_s <= 0:
        raise ValueError("hold_s must be > 0")
    if insert_at_s < 0:
        raise ValueError("insert_at_s must be >= 0")
    work_dir.mkdir(parents=True, exist_ok=True)
    seg_a = work_dir / "hold_seg_a.mp4"
    seg_b = work_dir / "hold_seg_b.mp4"
    hold = work_dir / "hold_clip.mp4"
    frame = work_dir / "hold_frame.png"

    _run_ffmpeg([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src), "-t", f"{insert_at_s:.6f}",
        *ENC, str(seg_a),
    ], label="hold head")
    _run_ffmpeg([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{insert_at_s:.6f}", "-i", str(src),
        *ENC, str(seg_b),
    ], label="hold tail")
    frame_src = hold_frame_src or src
    frame_at = hold_frame_at_s if hold_frame_at_s is not None else insert_at_s
    capture_hold_frame(frame_src, frame_at, frame)
    audio_start = max(0.0, insert_at_s - 0.1)
    _run_ffmpeg([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", "24", "-i", str(frame),
        "-ss", f"{audio_start:.6f}", "-t", "0.1", "-i", str(src),
        "-filter_complex", (
            f"[1:a]aloop=loop=-1:size=4800,atrim=duration={hold_s:.6f},asetpts=PTS-STARTPTS[a];"
            f"[0:v]trim=duration={hold_s:.6f},setpts=PTS-STARTPTS[v]"
        ),
        "-map", "[v]", "-map", "[a]", "-t", f"{hold_s:.6f}",
        *ENC, str(hold),
    ], label="hold middle")

    for label, part in (("head", seg_a), ("hold", hold), ("tail", seg_b)):
        vd, ad = probe_stream_durations(part)
        if abs(vd - ad) > DEFAULT_MAX_DRIFT_S:
            raise RuntimeError(
                f"{label} segment A/V drift {abs(vd - ad):.3f}s > {DEFAULT_MAX_DRIFT_S}s",
            )

    lst = work_dir / "hold_concat.txt"
    lst.write_text(f"file '{seg_a}'\nfile '{hold}'\nfile '{seg_b}'\n", encoding="utf-8")
    _run_ffmpeg([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(lst),
        "-c", "copy", "-movflags", "+faststart", str(dest),
    ], label="hold concat")


def build_manifest(
    *,
    source: Path,
    output: Path,
    insert_at_s: float,
    hold_s: float,
    duration_before_s: float,
    duration_after_s: float,
    seams: list[SeamSpec],
    av_drift_s: float,
    sha256: str | None = None,
) -> dict:
    digest = sha256
    if digest is None and output.is_file():
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {
        "schema_version": PHASE_B_PREVIEW_HOLD_INSERT_V1,
        "tool": Path(__file__).name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source.name,
        "output": output.name,
        "insert_at_s": insert_at_s,
        "hold_s": hold_s,
        "fade_ms": int(DEFAULT_FADE_S * 1000),
        "seams": [
            {
                "label": s.label or f"seam_{i + 1}",
                "module_join_out_s": s.out_s,
                "module_join_in_s": s.in_s,
            }
            for i, s in enumerate(seams)
        ],
        "duration_before_s": duration_before_s,
        "duration_after_s": duration_after_s,
        "added_hold_s": hold_s,
        "av_drift_s": av_drift_s,
        "sha256": digest or "",
    }


def run_pipeline(
    src: Path,
    dest: Path,
    *,
    insert_at_s: float,
    hold_s: float,
    seams: list[SeamSpec],
    work_dir: Path,
    max_drift_s: float = DEFAULT_MAX_DRIFT_S,
) -> HoldResult:
    dest.parent.mkdir(parents=True, exist_ok=True)
    validate_seams_vs_hold_insert(seams, insert_at_s=insert_at_s)
    current = src.resolve()
    duration_before_s = ffprobe_duration(src)
    applied_seams: list[SeamSpec] = []

    for idx, seam in enumerate(seams):
        step = work_dir / f"after_seam_{idx + 1}.mp4"
        splice_pause_interior(current, step, seam, work_dir=work_dir / f"seam_{idx + 1}")
        current = step
        applied_seams.append(seam)
        duration_before_s = ffprobe_duration(current)

    insert_freeze_hold(
        current, dest,
        insert_at_s=insert_at_s,
        hold_s=hold_s,
        work_dir=work_dir / "hold",
        hold_frame_src=current,
        hold_frame_at_s=insert_at_s,
    )

    duration_after_s = ffprobe_duration(dest)
    av_drift_s = av_duration_drift_s(dest)
    if av_drift_s > max_drift_s:
        raise RuntimeError(
            f"output A/V drift {av_drift_s:.3f}s exceeds gate {max_drift_s}s — not writing stitch slot",
        )

    manifest_path = dest.with_name(dest.stem + "_manifest.json")
    manifest_path.write_text(
        json.dumps(
            build_manifest(
                source=src,
                output=dest,
                insert_at_s=insert_at_s,
                hold_s=hold_s,
                duration_before_s=duration_before_s,
                duration_after_s=duration_after_s,
                seams=applied_seams,
                av_drift_s=av_drift_s,
            ),
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    return HoldResult(
        output=dest,
        duration_s=duration_after_s,
        duration_ms=int(round(duration_after_s * 1000)),
        av_drift_s=av_drift_s,
        manifest_path=manifest_path,
    )


def update_stitch_slot_optional(
    *,
    job_name: str,
    slot_key: str,
    video_rel: str,
    video_dur_ms: int,
    port: int,
    host: str = "localhost",
) -> dict:
    """Opt-in only: point an existing stitch slot at ``video_rel`` (never auto-runs)."""
    payload = {
        "name": job_name,
        "merge_slots": True,
        "edit_kind": "video_lineage",
        "slots": {
            slot_key: {
                "video_path": video_rel,
                "dry_export_path": video_rel,
                "video_dur_ms": video_dur_ms,
                "overlay_baked": True,
                "source": "phase_b_export",
            },
        },
    }
    url = f"http://{host}:{port}/api/stitch_editor/job"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"stitch slot update HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"stitch server unreachable at {host}:{port} — file written; load slot manually",
        ) from exc
    if not body.get("ok"):
        raise RuntimeError(f"stitch slot update failed: {body}")
    return body


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Insert freeze hold into a baked Phase B preview MP4 (on-demand operator tool). "
            "Not connected to Send to Stitcher or export pipelines."
        ),
    )
    p.add_argument("--src", type=Path, required=True, help="Input phase_b preview MP4")
    p.add_argument("--out", type=Path, required=True, help="Output MP4 path")
    p.add_argument("--insert-at", type=float, required=True, help="Hold starts at this timeline second")
    p.add_argument("--hold-s", type=float, default=3.0, help="Freeze hold duration (default 3)")
    p.add_argument(
        "--seam", action="append", default=[],
        help="Pause-interior seam as OUT:IN seconds (repeatable, applied before hold)",
    )
    p.add_argument(
        "--seam-out", type=float, default=None,
        help="Optional single seam OUT (use --seam OUT:IN for multiple)",
    )
    p.add_argument("--seam-in", type=float, default=None, help="Pair with --seam-out")
    p.add_argument(
        "--work-dir", type=Path, default=None,
        help="Temp dir (default: alongside --out)",
    )
    p.add_argument(
        "--update-stitch-job", default="",
        help="OPT-IN: after success, point this stitch job slot at --out",
    )
    p.add_argument("--stitch-slot", default="phase_b", help="Slot key for --update-stitch-job")
    p.add_argument("--stitch-port", type=int, default=5111, help="Storyboard server port")
    p.add_argument("--dry-run", action="store_true", help="Print plan and exit")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    src = args.src.expanduser().resolve()
    if not src.is_file():
        print(f"error: --src not found: {src}", file=sys.stderr)
        return 2

    seams: list[SeamSpec] = []
    for raw in args.seam:
        if ":" not in raw:
            print(f"error: --seam must be OUT:IN, got {raw!r}", file=sys.stderr)
            return 2
        out_raw, in_raw = raw.split(":", 1)
        seams.append(SeamSpec(out_s=float(out_raw), in_s=float(in_raw)))
    if (args.seam_out is None) ^ (args.seam_in is None):
        print("error: --seam-out and --seam-in must be passed together", file=sys.stderr)
        return 2
    if args.seam_out is not None:
        seams.append(SeamSpec(out_s=float(args.seam_out), in_s=float(args.seam_in)))

    out = args.out.expanduser().resolve()
    work_dir = (args.work_dir or out.parent / f".hold_insert_{out.stem}").expanduser().resolve()

    if args.dry_run:
        print(json.dumps({
            "code": PHASE_B_PREVIEW_HOLD_INSERT_V1,
            "src": str(src),
            "out": str(out),
            "insert_at_s": args.insert_at,
            "hold_s": args.hold_s,
            "seams": [s.__dict__ for s in seams],
            "update_stitch_job": args.update_stitch_job or None,
        }, indent=2))
        return 0

    try:
        result = run_pipeline(
            src, out,
            insert_at_s=float(args.insert_at),
            hold_s=float(args.hold_s),
            seams=seams,
            work_dir=work_dir,
        )
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"ok {result.output}")
    print(f"duration_s {result.duration_s:.3f} dur_ms {result.duration_ms} av_drift_s {result.av_drift_s:.3f}")
    print(f"manifest {result.manifest_path}")

    if args.update_stitch_job:
        prod_root = TOOLS.parent
        if str(prod_root) not in sys.path:
            sys.path.insert(0, str(prod_root))
        from lib.paths import DROPBOX_ROOT  # noqa: WPS433

        production_root = DROPBOX_ROOT / "Production"
        video_rel = production_rel_path(result.output, production_root=production_root)
        try:
            body = update_stitch_slot_optional(
                job_name=args.update_stitch_job,
                slot_key=args.stitch_slot,
                video_rel=video_rel,
                video_dur_ms=result.duration_ms,
                port=int(args.stitch_port),
            )
            print(f"stitch job updated: {args.update_stitch_job} slot={args.stitch_slot} path={video_rel}")
            if body.get("artifact_build"):
                print(f"artifact_build status={body['artifact_build'].get('status')}")
        except RuntimeError as exc:
            print(f"warning: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
