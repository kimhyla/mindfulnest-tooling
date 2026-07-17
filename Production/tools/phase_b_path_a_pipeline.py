"""Phase B "Path A" layered lipsync pipeline — Cedric (Jul 2026).

Produces a full-length Phase B video with real full-body idle motion and
Kling lipsync, WITHOUT scene-wide warp, by separating the static room plate
from the character cutout.

Pipeline (validated on Event 5 Phase B, Jul 17 2026):

1. IDLE TRACK  — pre-generated 10s blue-screen gesture idle units (Kling
   start/end I2V, same still as both bookends) are head/tail-trimmed to cut
   the near-still bookend ramps, then chained with 0.5s crossfades. This is
   what eliminates the "frozen seam": raw units decay to stillness at each
   bookend, so trimming the still ramps before the xfade keeps visible
   motion through every join.
2. CHUNKING    — the voice stem is split at silence midpoints (~45-50s per
   chunk) so each lipsync job stays inside Kling's duration limit and cuts
   land in pauses, never mid-word.
3. LIPSYNC     — each chunk video+audio goes to the WaveSpeed Kling lipsync
   endpoint (transport="url"). Output is ALWAYS 832x464 regardless of input
   resolution, so the character crop is upscaled to fill the submitted
   frame (1920x1080) and the 832x464 result is DOWNSCALED back to its final
   on-plate size — preserving detail instead of losing it.
4. QC          — automated pupil scan (white-eyes hallucination) and
   body-motion still-span scan (frozen seams) gate every chunk and the
   final composite.
5. COMPOSITE   — lipsync chunks are padded to exact audio duration,
   concatenated, sharpened (cas) and color-matched (eq), overlaid back onto
   the blue cutout frame, chroma-keyed, despilled, and composited over the
   static room plate with the full stem audio.

Build LOCAL-FIRST: heavy encodes go to local /tmp, get verified (full
decode + both QC scans), and only then are copied into Dropbox. Writing
straight into Dropbox CloudStorage corrupted a 2-minute encode mid-write.

Known-good geometry is for the 1280x720 Cedric wizard-desk plate
(cedric_room_plate_1280x720_v1.png) with the matching blue cutout.
"""
from __future__ import annotations

import json
import re
import shutil
import socket
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
PATH_A_PREP = DROPBOX_PRODUCTION / "NEW STYLE CHARACTERS/CEDRIC/path_a_prep"
LIPSYNC_BASES = DROPBOX_PRODUCTION / "assets/lipsync_bases"

CEDRIC_CUTOUT_BLUE_PNG = PATH_A_PREP / "cedric_cutout_blue_1280x720_v1.png"
CEDRIC_ROOM_PLATE_PNG = PATH_A_PREP / "cedric_room_plate_1280x720_v1.png"

# --- character geometry on the 1280x720 plate -------------------------------
# Tight crop box around Cedric. The blue idle is cropped here, upscaled to
# 1920x1080 for lipsync submission, and the 832x464 lipsync output is scaled
# back to CROP_W x CROP_H and overlaid at (CROP_X, CROP_Y).
CROP_W, CROP_H = 832, 468
CROP_X, CROP_Y = 292, 150

# --- idle units --------------------------------------------------------------
# 10s Kling bookend units (same still as start+end frame → no scale drift).
# head_trim/tail_trim cut the near-still ramps into/out of the bookend pose,
# measured from per-frame motion curves (fps=12 gray-diff over the character
# region). Re-measure if units are regenerated: trim to where motion exceeds
# ~25% of the unit's median.
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


IDLE_UNIT_A = IdleUnit(
    "A", LIPSYNC_BASES / "cedric_path_a_gesture_idle_10s_loop_v1_blue_1920x1080.mp4", 0.6, 1.2
)
IDLE_UNIT_B = IdleUnit(
    "B", LIPSYNC_BASES / "cedric_path_a_gesture_idle_B_10s_loop_v1_blue_1920x1080.mp4", 1.3, 0.5
)
# C2 (sealed lips, level head) is eyes-safe but too calm — its low overall
# motion reads as a freeze next to A/B, so it is EXCLUDED from the default
# rotation. Kept on disk for future remixing.
IDLE_UNIT_C2 = IdleUnit(
    "C2", LIPSYNC_BASES / "cedric_path_a_gesture_idle_C2_10s_loop_v1_blue_1920x1080.mp4", 0.5, 0.7
)

DEFAULT_ROTATION = (IDLE_UNIT_A, IDLE_UNIT_B)

# --- lipsync / chunking ------------------------------------------------------
LIPSYNC_OUTPUT_SIZE = "832x464"  # fixed by the Kling lipsync model
MAX_CHUNK_SECONDS = 50.0
SILENCE_DETECT_ARGS = "silencedetect=noise=-35dB:d=0.45"

# --- post / composite --------------------------------------------------------
LIPSYNC_POST_FILTERS = "cas=0.45,eq=contrast=1.03:saturation=1.03"
CHROMAKEY_BLUE = "chromakey=0x0000FF:0.28:0.06,despill=type=blue"

# Body region for the still scan, per canvas:
# 1920x1080 idle track -> "800:700:560:190"; the same box mapped onto the
# 1280x720 composite (character at 832x468 @ 292,150, scale 832/1920).
IDLE_BODY_CROP = "800:700:560:190"
COMPOSITE_BODY_CROP = "346:302:534:232"

# LD-379-class ISP DNS poisoning: these hosts NXDOMAIN on the local resolver.
DNS_PIN_HOSTS = ("filebin.net", "catbox.moe", "uguu.se", "api.wavespeed.ai")


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kw)


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


# =============================================================================
# 1. Idle track
# =============================================================================

def build_idle_track(
    dest: Path,
    duration: float,
    rotation: tuple[IdleUnit, ...] = DEFAULT_ROTATION,
    fade: float = XFADE_SECONDS,
) -> list[IdleUnit]:
    """Chain trimmed idle units with crossfades into a >=duration track.

    Returns the unit sequence used. Output is 1920x1080/24fps, no audio.
    """
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


# =============================================================================
# 2. Chunking
# =============================================================================

def detect_chunk_boundaries(stem: Path, max_chunk: float = MAX_CHUNK_SECONDS) -> list[float]:
    """Cut points at silence midpoints so no chunk exceeds max_chunk seconds."""
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
    """Slice audio stem and idle track at the same boundaries."""
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


# =============================================================================
# 3. Lipsync submission (parallel, DNS-pinned)
# =============================================================================

def install_dns_pins(hosts: tuple[str, ...] = DNS_PIN_HOSTS) -> dict[str, str]:
    """Resolve hosts via 1.1.1.1 and monkeypatch getaddrinfo (LD-379 class)."""
    pins: dict[str, str] = {}
    for h in hosts:
        try:
            out = subprocess.run(
                ["dig", "+short", "@1.1.1.1", h],
                capture_output=True, text=True, timeout=10,
            ).stdout
            ips = [ln for ln in out.strip().splitlines() if ln and ln[0].isdigit()]
            if ips:
                pins[h] = ips[0]
        except Exception:
            pass
    orig = socket.getaddrinfo

    def patched(host, *a, **k):
        if host in pins:
            return orig(pins[host], *a, **k)
        return orig(host, *a, **k)

    socket.getaddrinfo = patched
    return pins


def submit_lipsync_chunks(work: Path, n_chunks: int, api_key: str) -> dict[int, str]:
    """Submit chunk_i_video.mp4 + chunk_i_audio.mp3 in parallel; download results."""
    sys.path.insert(0, str(TOOLS_DIR))
    from lipsync_sender import LipSyncClient  # noqa: PLC0415

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


# =============================================================================
# 4. QC scans
# =============================================================================

def qc_pupil_scan(path: Path, fps: int = 6) -> list[tuple[float, float]]:
    """White-eyes hallucination detector on 832x464 lipsync output.

    Counts dark pixels in the eye band; a span where the count collapses
    below 40% of the clip median means the pupils went white.
    Returns suspect (start_s, end_s) spans — must be empty to pass.
    """
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
    """Frozen-seam detector: still spans in the character body region.

    Default crop targets Cedric's chest/shoulders on the 1920x1080 idle track
    (mouth excluded so lipsync doesn't mask body stillness). For the final
    1280x720 composite use COMPOSITE_BODY_CROP (same box mapped through the
    832x468 @ 292,150 on-plate placement).
    Returns (start_s, duration_s) spans of motion below threshold — must be
    empty to pass.
    """
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


# =============================================================================
# 5. Composite
# =============================================================================

def pad_concat_lipsync(work: Path, n_chunks: int, dest: Path) -> None:
    """Pad each lipsync chunk to exact audio duration (clone last frame),
    scale to the on-plate crop size, and concat."""
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
    # concat -c copy has produced NAL corruption before — verify decode.
    run(["ffmpeg", "-v", "error", "-i", str(dest), "-f", "null", "-"])


def composite_on_plate(lipsync_track: Path, stem: Path, dest: Path) -> None:
    """Sharpen + color-match lipsync, rebuild the blue frame, key, composite."""
    fc = (
        f"[1:v]{LIPSYNC_POST_FILTERS}[ls];"
        f"[0:v][ls]overlay={CROP_X}:{CROP_Y}:shortest=1[full];"
        f"[full]{CHROMAKEY_BLUE}[keyed];"
        f"[2:v][keyed]overlay=0:0:shortest=1,format=yuv420p[out]"
    )
    run(["ffmpeg", "-y", "-loglevel", "fatal",
         "-loop", "1", "-i", str(CEDRIC_CUTOUT_BLUE_PNG),
         "-i", str(lipsync_track),
         "-loop", "1", "-i", str(CEDRIC_ROOM_PLATE_PNG),
         "-i", str(stem),
         "-filter_complex", fc,
         "-map", "[out]", "-map", "3:a",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-c:a", "aac", "-b:a", "160k", "-shortest", str(dest)])
    run(["ffmpeg", "-v", "error", "-i", str(dest), "-f", "null", "-"])


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("stem", type=Path, help="Phase B voice stem (mp3)")
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

    work = args.work or Path(tempfile.mkdtemp(prefix="phase_b_path_a_"))
    work.mkdir(parents=True, exist_ok=True)
    print(f"[path_a] work dir: {work}")

    total = ffprobe_duration(args.stem)
    idle = work / "idle_track.mp4"
    seq = build_idle_track(idle, total)
    print(f"[path_a] idle track: {len(seq)} units {'/'.join(u.name for u in seq)}")
    stills = qc_still_scan(idle)
    if stills:
        print(f"[path_a] FAIL idle still spans: {stills}", file=sys.stderr)
        return 1

    cuts = detect_chunk_boundaries(args.stem)
    n = cut_chunks(args.stem, idle, cuts, work)
    print(f"[path_a] {n} chunks, cuts at {cuts}")

    pins = install_dns_pins()
    print(f"[path_a] dns pins: {pins}")
    results = submit_lipsync_chunks(work, n, api_key)
    print(f"[path_a] lipsync results: {results}")
    if any(v != "ok" for v in results.values()):
        return 1

    for i in range(n):
        spans = qc_pupil_scan(work / f"chunk_{i}_lipsync.mp4")
        if spans:
            print(f"[path_a] FAIL chunk {i} pupil spans: {spans}", file=sys.stderr)
            return 1
    print("[path_a] pupil scan clean on all chunks")

    lipsync_track = work / "lipsync_full.mp4"
    pad_concat_lipsync(work, n, lipsync_track)

    local_out = work / "composite_local.mp4"
    composite_on_plate(lipsync_track, args.stem, local_out)
    comp_stills = qc_still_scan(local_out, crop=COMPOSITE_BODY_CROP)
    if comp_stills:
        print(f"[path_a] FAIL composite still spans: {comp_stills}", file=sys.stderr)
        return 1
    print("[path_a] composite QC: no still spans")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local_out, args.out)
    print(f"[path_a] delivered: {args.out} ({ffprobe_duration(args.out):.2f}s)")
    (work / "manifest.json").write_text(json.dumps({
        "stem": str(args.stem), "out": str(args.out),
        "cuts": cuts, "units": [u.name for u in seq],
        "lipsync": results,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
