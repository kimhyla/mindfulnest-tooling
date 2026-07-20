"""Phase A "Path A" layered lipsync pipeline — Arlo (Jul 2026).

Mirrors ``phase_b_path_a_pipeline.py`` (Cedric) for Phase A:

1. IDLE TRACK  — pre-generated 10s green-screen gesture idle (tight crop,
   1920x1080) head/tail-trimmed and self-looped with 0.5s crossfades.
2. CHUNKING    — voice stem split at silence midpoints (≤50s).
3. LIPSYNC     — WaveSpeed Kling lipsync per chunk (transport="url").
   Output is always 832x464; crop fills the submit frame, then downscales
   back to on-plate size.
4. QC          — pupil scan + body still-span scan.
5. COMPOSITE   — overlay onto green cutout, chromakey green, plate + stem.

Build LOCAL-FIRST (/tmp), verify, then copy to event dir.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent

DROPBOX_PRODUCTION = Path(
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/"
    "Claude Mindfulnest Project Files/Production"
)
PATH_A_PREP = DROPBOX_PRODUCTION / "NEW STYLE CHARACTERS/ARLO/path_a_prep"
LIPSYNC_BASES = DROPBOX_PRODUCTION / "assets/lipsync_bases"

# Green cutout — Arlo keeps green (blue scarf collides with Cedric-style blue key).
ARLO_CUTOUT_GREEN_PNG = PATH_A_PREP / "arlo_cutout_green_1280x720_v1.png"
ARLO_ROOM_PLATE_PNG = PATH_A_PREP / "arlo_room_plate_1280x720_v1.png"

# Character geometry on the 1280x720 plate — MUST cover all of Arlo.
# Path A overlays lipsync onto the green cutout in this box, then keys.
# Shrinking this to "upper body only" leaves legs as the still cutout
# (looks cut in half). Tighter Kling submit needs a separate face-paste
# step; do not shrink CROP_* for that.
CROP_W, CROP_H = 832, 468
CROP_X, CROP_Y = 325, 157

# Idle unit: provisional working default (O3 v12). Not a locked Kim pick —
# swap IDLE_UNIT_A.path to any full-body crop under lipsync_bases when chosen.
# fullframe → crop 1248x702@488,236 on 1920x1080, then scale to 1920x1080.
UNIT_DURATION = 10.041667
XFADE_SECONDS = 0.5


@dataclass(frozen=True)
class IdleUnit:
    name: str
    path: Path
    head_trim: float
    tail_trim: float

    @property
    def trimmed_duration(self) -> float:
        return UNIT_DURATION - self.head_trim - self.tail_trim


# Provisional unit — replace path when Kim selects the production idle.
IDLE_UNIT_A = IdleUnit(
    "A",
    LIPSYNC_BASES
    / "arlo_path_a_gesture_idle_o3_v12_10s_crop_green_1920x1080.mp4",
    0.3,
    0.5,
)

DEFAULT_ROTATION = (IDLE_UNIT_A,)

LIPSYNC_OUTPUT_SIZE = "832x464"
MAX_CHUNK_SECONDS = 50.0
SILENCE_DETECT_ARGS = "silencedetect=noise=-35dB:d=0.45"

LIPSYNC_POST_FILTERS = "cas=0.45,eq=contrast=1.03:saturation=1.03"
# Cedric blue params don't apply — Arlo scarf is blue. Green key + strong despill.
CHROMAKEY_GREEN = "chromakey=0x00FF00:0.28:0.06,despill=type=green:mix=1:expand=1"

# Body region for still scan (mouth excluded). Cropped idle fills frame with
# Arlo; composite crop maps chest/shoulders on the 1280x720 plate placement.
IDLE_BODY_CROP = "700:600:610:280"
COMPOSITE_BODY_CROP = "220:280:630:300"

PHASE_A_PATH_A_ROUTE_V1 = "PHASE_A_PATH_A_ROUTE_V1"


class PhaseAPathAQCError(RuntimeError):
    """A QC gate (pupil scan / still-span scan) refused the build."""


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kw)


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def build_idle_track(
    dest: Path,
    duration: float,
    rotation: tuple[IdleUnit, ...] = DEFAULT_ROTATION,
    fade: float = XFADE_SECONDS,
) -> list[IdleUnit]:
    """Chain trimmed idle units with crossfades into a >=duration track."""
    seq: list[IdleUnit] = []
    total = 0.0
    i = 0
    while total < duration + fade:
        u = rotation[i % len(rotation)]
        total = u.trimmed_duration if not seq else total + u.trimmed_duration - fade
        seq.append(u)
        i += 1

    inputs: list[str] = []
    for u in seq:
        inputs += ["-i", str(u.path)]
    parts = []
    for k, u in enumerate(seq):
        parts.append(
            f"[{k}:v]trim=start={u.head_trim}:end={UNIT_DURATION - u.tail_trim},"
            f"setpts=PTS-STARTPTS,fps=24,scale=1920:1080:flags=lanczos,"
            f"setsar=1:1,settb=AVTB[v{k}]"
        )
    prev = "v0"
    offset = 0.0
    for k in range(1, len(seq)):
        offset += seq[k - 1].trimmed_duration - fade
        parts.append(
            f"[{prev}][v{k}]xfade=transition=fade:duration={fade}:offset={offset:.4f}[x{k}]"
        )
        prev = f"x{k}"
    parts.append(f"[{prev}]trim=duration={duration},setpts=PTS-STARTPTS[vout]")

    run(
        ["ffmpeg", "-y", "-v", "error", *inputs,
         "-filter_complex", ";".join(parts), "-map", "[vout]", "-an",
         "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
         "-preset", "medium", "-g", "48",
         "-b:v", "4500k", "-maxrate", "5500k", "-bufsize", "9000k",
         str(dest)]
    )
    return seq


def detect_chunk_boundaries(stem: Path, max_chunk: float = MAX_CHUNK_SECONDS) -> list[float]:
    proc = subprocess.run(
        ["ffmpeg", "-i", str(stem), "-af", SILENCE_DETECT_ARGS, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    silences: list[tuple[float, float]] = []
    start = None
    for line in proc.stderr.splitlines():
        m = re.search(r"silence_start: ([\d.]+)", line)
        if m:
            start = float(m.group(1))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            silences.append((start, float(m.group(1))))
            start = None

    total = ffprobe_duration(stem)
    cuts: list[float] = []
    pos = 0.0
    while total - pos > max_chunk:
        candidates = [s for s in silences if pos < (s[0] + s[1]) / 2 <= pos + max_chunk]
        if not candidates:
            raise RuntimeError(f"no silence found in ({pos}, {pos + max_chunk}] — lower max_chunk?")
        s = candidates[-1]
        cut = round((s[0] + s[1]) / 2, 2)
        cuts.append(cut)
        pos = cut
    return cuts


def cut_chunks(stem: Path, idle_track: Path, cuts: list[float], work: Path) -> int:
    total = ffprobe_duration(stem)
    bounds = [0.0, *cuts, total]
    n = len(bounds) - 1
    for i in range(n):
        a, b = bounds[i], bounds[i + 1]
        run(["ffmpeg", "-y", "-v", "error", "-i", str(stem),
             "-ss", f"{a}", *(["-to", f"{b}"] if i < n - 1 else []),
             "-c:a", "libmp3lame", "-q:a", "2", str(work / f"chunk_{i}_audio.mp3")])
        run(["ffmpeg", "-y", "-v", "error", "-i", str(idle_track),
             "-ss", f"{a}", *(["-to", f"{b}"] if i < n - 1 else []),
             "-c:v", "libx264", "-preset", "medium", "-crf", "15",
             "-pix_fmt", "yuv420p", "-an", str(work / f"chunk_{i}_video.mp4")])
    return n


def submit_lipsync_chunks(work: Path, n_chunks: int, api_key: str) -> dict[int, str]:
    sys.path.insert(0, str(TOOLS_DIR))
    from lipsync_sender import LipSyncClient, install_public_dns_fallback  # noqa: PLC0415

    install_public_dns_fallback()
    results: dict[int, str] = {}

    def worker(i: int) -> None:
        client = LipSyncClient(api_key)
        try:
            job = client.submit(
                work / f"chunk_{i}_video.mp4", work / f"chunk_{i}_audio.mp3",
                transport="url",
            )
            res = client.poll_until_done(job)
            outs = res.get("outputs") or []
            if res.get("status") == "completed" and outs:
                client.download(outs[0], work / f"chunk_{i}_lipsync.mp4")
                results[i] = "ok"
            else:
                results[i] = f"failed:{res.get('status')}"
        except Exception as exc:  # noqa: BLE001
            results[i] = f"exception:{exc}"

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_chunks)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def qc_pupil_scan(path: Path, fps: int = 6) -> list[tuple[float, float]]:
    """White-eyes detector on 832x464 lipsync output (eye-band crop)."""
    import numpy as np  # noqa: PLC0415

    w, h = 300, 130
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-vf", f"fps={fps},crop={w}:{h}:266:60,format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True,
    ).stdout
    n = len(raw) // (w * h)
    fr = np.frombuffer(raw[: n * w * h], dtype=np.uint8).reshape(n, h, w)
    dark = (fr < 70).sum(axis=(1, 2)).astype(float)
    bad = dark < 0.4 * np.median(dark)
    spans = []
    j = 0
    while j < n:
        if bad[j]:
            k = j
            while k < n and bad[k]:
                k += 1
            if k - j >= 2:
                spans.append((round(j / fps, 2), round(k / fps, 2)))
            j = k
        else:
            j += 1
    return spans


def qc_still_scan(
    path: Path,
    crop: str = IDLE_BODY_CROP,
    min_still_seconds: float = 0.5,
    fps: int = 12,
    threshold: float = 0.31,
) -> list[tuple[float, float]]:
    import numpy as np  # noqa: PLC0415

    cw, ch = (int(x) for x in crop.split(":")[:2])
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-vf", f"fps={fps},crop={crop},format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True,
    ).stdout
    n = len(raw) // (cw * ch)
    fr = np.frombuffer(raw[: n * cw * ch], dtype=np.uint8).reshape(n, ch, cw).astype(np.int16)
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    still = d < threshold
    spans = []
    start = None
    for i, s in enumerate(still):
        if s and start is None:
            start = i
        if not s and start is not None:
            if (i - start) / fps >= min_still_seconds:
                spans.append((round(start / fps, 2), round((i - start) / fps, 2)))
            start = None
    if start is not None and (n - 1 - start) / fps >= min_still_seconds:
        spans.append((round(start / fps, 2), round((n - 1 - start) / fps, 2)))
    return spans


def pad_concat_lipsync(work: Path, n_chunks: int, dest: Path) -> None:
    concat_lines = []
    for i in range(n_chunks):
        ad = ffprobe_duration(work / f"chunk_{i}_audio.mp3")
        exact = work / f"chunk_{i}_exact.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-i", str(work / f"chunk_{i}_lipsync.mp4"),
             "-vf",
             f"fps=24,scale={CROP_W}:{CROP_H}:flags=lanczos,"
             f"tpad=stop_mode=clone:stop_duration=2,trim=duration={ad},setpts=PTS-STARTPTS",
             "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "15",
             "-pix_fmt", "yuv420p", str(exact)])
        concat_lines.append(f"file '{exact.name}'")
    lst = work / "concat_lipsync.txt"
    lst.write_text("\n".join(concat_lines) + "\n")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-c", "copy", str(dest)])
    run(["ffmpeg", "-v", "error", "-i", str(dest), "-f", "null", "-"])


def composite_on_plate(lipsync_track: Path, stem: Path, dest: Path) -> None:
    """Sharpen + color-match lipsync, rebuild green frame, key, composite."""
    fc = (
        f"[1:v]{LIPSYNC_POST_FILTERS}[ls];"
        f"[0:v][ls]overlay={CROP_X}:{CROP_Y}:shortest=1[full];"
        f"[full]{CHROMAKEY_GREEN}[keyed];"
        f"[2:v][keyed]overlay=0:0:shortest=1,format=yuv420p[out]"
    )
    run(["ffmpeg", "-y", "-loglevel", "fatal",
         "-loop", "1", "-i", str(ARLO_CUTOUT_GREEN_PNG),
         "-i", str(lipsync_track),
         "-loop", "1", "-i", str(ARLO_ROOM_PLATE_PNG),
         "-i", str(stem),
         "-filter_complex", fc,
         "-map", "[out]", "-map", "3:a",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-c:a", "aac", "-b:a", "160k", "-shortest", str(dest)])
    run(["ffmpeg", "-v", "error", "-i", str(dest), "-f", "null", "-"])


def count_phase_a_path_a_chunks(stem: Path, max_chunk: float = MAX_CHUNK_SECONDS) -> int:
    return len(detect_chunk_boundaries(stem, max_chunk)) + 1


def validate_path_a_assets() -> None:
    missing = [
        str(p) for p in (
            ARLO_CUTOUT_GREEN_PNG,
            ARLO_ROOM_PLATE_PNG,
            *(u.path for u in DEFAULT_ROTATION),
        ) if not p.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Phase A Path A assets missing: " + ", ".join(missing)
        )


def run_phase_a_path_a_lipsync(
    audio_path: Path,
    out_path: Path,
    *,
    api_key: str,
    work_dir: Path | None = None,
) -> dict:
    """Full Path A build for Phase A. LOCAL-FIRST; QC gates; copy to out_path."""
    audio_path = Path(audio_path)
    out_path = Path(out_path)
    validate_path_a_assets()

    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="phase_a_path_a_"))
    work.mkdir(parents=True, exist_ok=True)
    print(f"[phase_a_path_a] work dir: {work}", flush=True)

    total = ffprobe_duration(audio_path)
    idle = work / "idle_track.mp4"
    seq = build_idle_track(idle, total)
    print(
        f"[phase_a_path_a] idle track: {len(seq)} units "
        f"{'/'.join(u.name for u in seq)}",
        flush=True,
    )
    stills = qc_still_scan(idle)
    if stills:
        raise PhaseAPathAQCError(f"idle still spans >=0.5s: {stills}")

    cuts = detect_chunk_boundaries(audio_path)
    n = cut_chunks(audio_path, idle, cuts, work)
    print(f"[phase_a_path_a] {n} chunks, cuts at {cuts}", flush=True)

    results = submit_lipsync_chunks(work, n, api_key)
    print(f"[phase_a_path_a] lipsync results: {results}", flush=True)
    failed = {i: v for i, v in results.items() if v != "ok"}
    if failed or len(results) != n:
        raise RuntimeError(f"lipsync chunk failures: {failed or 'missing results'}")

    for i in range(n):
        spans = qc_pupil_scan(work / f"chunk_{i}_lipsync.mp4")
        if spans:
            raise PhaseAPathAQCError(f"chunk {i} pupil (white-eye) spans: {spans}")
    print("[phase_a_path_a] pupil scan clean on all chunks", flush=True)

    lipsync_track = work / "lipsync_full.mp4"
    pad_concat_lipsync(work, n, lipsync_track)

    local_out = work / "composite_local.mp4"
    composite_on_plate(lipsync_track, audio_path, local_out)
    comp_stills = qc_still_scan(local_out, crop=COMPOSITE_BODY_CROP)
    if comp_stills:
        raise PhaseAPathAQCError(f"composite still spans >=0.5s: {comp_stills}")
    print("[phase_a_path_a] composite QC: no still spans", flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local_out, out_path)
    print(
        f"[phase_a_path_a] delivered: {out_path} ({ffprobe_duration(out_path):.2f}s)",
        flush=True,
    )
    manifest = {
        "route": PHASE_A_PATH_A_ROUTE_V1,
        "stem": str(audio_path),
        "out": str(out_path),
        "chunk_count": n,
        "cuts": cuts,
        "units": [u.name for u in seq],
        "lipsync": {str(k): v for k, v in results.items()},
    }
    (work / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("stem", type=Path, help="Phase A voice stem (mp3)")
    p.add_argument("out", type=Path, help="final composite destination (mp4)")
    p.add_argument("--work", type=Path, default=None,
                   help="work dir (default: local mkdtemp — keep off Dropbox)")
    args = p.parse_args()

    from kling_startend_pipeline import load_api_keys  # noqa: PLC0415

    keys = load_api_keys()
    api_key = keys.get("wavespeed") or keys.get("WAVESPEED_API_KEY") or keys.get("wavespeed_api_key")
    if not api_key:
        print("no wavespeed api key", file=sys.stderr)
        return 1

    try:
        run_phase_a_path_a_lipsync(
            args.stem, args.out, api_key=api_key, work_dir=args.work,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[phase_a_path_a] FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
