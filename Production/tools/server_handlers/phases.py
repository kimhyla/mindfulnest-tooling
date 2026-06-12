"""Phase A/B handlers — V59 Phase 4 Pass 2.

Handlers extracted from production_server.py.
Each function takes the live `ProductionHandler` instance as `h`.
"""
from __future__ import annotations

import argparse
import base64
import collections as _pathapp_collections
import concurrent.futures as _cf
import functools
import hashlib
import io
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid as _stdlib_uuid
import uuid as _pathapp_uuid
import http.client
import ssl
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# V59 Phase 4 path-depth correction: extracted modules are one level
# deeper than production_server.py. _PSERVER_TOOLS_DIR is for CODE-tree
# lookups (sibling Python modules + sys.path inserts). It is NOT used for
# data paths — those come from the runtime event_dir via _data_root(h).
_PSERVER_TOOLS_DIR = Path(__file__).resolve().parent.parent  # Production/tools/


def _data_root(h) -> Path:
    """Runtime ``Production/`` root, anchored on the running server's event_dir.

    LD-505 Phase C (2026-05-19): replaces the old module-level
    `_PSERVER_PRODUCTION_DIR = Path(__file__).resolve().parent.parent.parent`
    which pointed at the (empty) tooling-side Production/ when CODE was in
    tooling and DATA was in Dropbox. See lib/paths.runtime_production_root.
    Audit C1-2/C1-3/C1-4 (live-confirmed empty libraries).
    """
    return Path(h.app.event_dir).parent


# Project-internal modules imported the same way production_server.py does.
# Handler bodies may reference any of these by bare name.
from lib.atomic_json_write import atomic_json_write
from lib.v3_partition import _iter_v3_beats
from lib.paths import DROPBOX_ROOT
import scope_router
from ffmpeg_utils import strip_audio as _strip_clip_audio
from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC
from server_handlers._path_security import (
    MEDIA_EXTENSIONS,
    require_basename_under_dir,
    require_media_under_project,
)

# Late-resolvable private helpers from the host module.
from tools.production_server import (  # noqa: E402
    _bg_module,
    _ffprobe_duration,
    _resolve_module_for_event,
    _silcomp_audio,
    _trim_video_to_audio,
    _v2_validate_watercolor_cues_json,
    parse_api_keys,
)

# ---------------------------------------------------------------------------
# White-out fade — standardized Phase B ending transition
# ---------------------------------------------------------------------------
# Locked: every Phase B lipsync output gets a white fade-out at the tail.
# Duration is constant (PHASE_B_WHITEOUT_DURATION_SEC). Applied in-place
# on the downloaded mp4 before state is written; fully transparent to callers.
PHASE_B_WHITEOUT_DURATION_SEC: float = 1.5  # seconds of fade-to-white at end
# Kling LipSync on ~43s stems: p99 ~15 min; auto-clear stuck "running" after 20 min.
PHASE_A_LIPSYNC_STALE_SEC: int = 1200

# Cleared on reject/regen so lipsync/mix/stitch no longer reference stale outputs.
_PHASE_LIPSYNC_DERIVED_KEYS = (
    "lipsync_file",
    "lipsync_mtime",
    "lipsync_status",
    "lipsync_method",
    "lipsync_qa_dir",
    "lipsync_av_gap_s",
    "lipsync_reliability_note",
    "lipsync_task_id",
    "lipsync_started_at",
    "mixed_audio_file",
    "mixed_audio_mtime",
    "stitched_file",
    "stitched_mtime",
)
_PHASE_VOICE_STEM_CUT_KEYS = (
    "voice_stem_cut_start_s",
    "voice_stem_cut_end_s",
)
# Legacy keep-region keys (pre-2026-06-12 invert); cleared on write.
_PHASE_VOICE_STEM_TRIM_KEYS_LEGACY = (
    "voice_stem_trim_start_s",
    "voice_stem_trim_back_s",
)


def _phase_voice_stem_cut_window(state: dict, phase: str) -> tuple[float, float]:
    """Return (cut_start_s, cut_end_s) — absolute times of the region TO REMOVE."""
    start = float(state.get(f"phase_{phase}_voice_stem_cut_start_s") or 0.0)
    end = float(state.get(f"phase_{phase}_voice_stem_cut_end_s") or 0.0)
    return max(0.0, start), max(0.0, end)


def _phase_voice_stem_trim_window(state: dict, phase: str) -> tuple[float, float]:
    """Deprecated alias — use _phase_voice_stem_cut_window."""
    return _phase_voice_stem_cut_window(state, phase)


def _materialize_cut_out_audio(
    source: Path,
    dst: Path,
    cut_start_s: float,
    cut_end_s: float,
) -> Path:
    """Remove [cut_start_s, cut_end_s) from *source*; write kept audio to *dst*."""
    if cut_end_s <= cut_start_s + 0.001:
        raise ValueError(
            f"cut region empty or inverted: start={cut_start_s:.3f}s end={cut_end_s:.3f}s",
        )
    dur = _ffprobe_duration(source)
    if cut_end_s - cut_start_s >= dur - 0.001:
        raise ValueError(
            f"cut region covers entire file ({cut_end_s - cut_start_s:.2f}s of {dur:.2f}s)",
        )

    kept = (cut_start_s - 0.0) + max(0.0, dur - cut_end_s)
    if kept < 0.25:
        raise ValueError(
            f"kept audio too small ({kept:.2f}s after removing "
            f"[{cut_start_s:.2f}s, {cut_end_s:.2f}s] from {dur:.2f}s)",
        )

    # Single-segment keeps (head or tail removal).
    if cut_start_s <= 0.001:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{cut_end_s:.3f}",
                "-i", str(source),
                "-c:a", "libmp3lame", "-q:a", "2",
                str(dst),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        return dst

    if cut_end_s >= dur - 0.001:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-t", f"{cut_start_s:.3f}",
                "-i", str(source),
                "-c:a", "libmp3lame", "-q:a", "2",
                str(dst),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        return dst

    # Middle removal — concat [0, cut_start) + [cut_end, dur).
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source),
            "-filter_complex",
            (
                f"[0:a]atrim=0:{cut_start_s:.3f},asetpts=PTS-STARTPTS[a1];"
                f"[0:a]atrim={cut_end_s:.3f}:{dur:.3f},asetpts=PTS-STARTPTS[a2];"
                f"[a1][a2]concat=n=2:v=0:a=1[out]"
            ),
            "-map", "[out]",
            "-c:a", "libmp3lame", "-q:a", "2",
            str(dst),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return dst


def _materialize_trimmed_audio(
    source: Path,
    dst: Path,
    trim_start_s: float,
    trim_back_s: float,
) -> Path:
    """Legacy keep-region trim — maps to cut-out of complement bands."""
    if trim_start_s <= 0.001 and trim_back_s <= 0.001:
        return source
    dur = _ffprobe_duration(source)
    cut_start = trim_start_s
    cut_end = dur - trim_back_s if trim_back_s > 0.001 else dur
    return _materialize_cut_out_audio(source, dst, cut_start, cut_end)


def _phase_clear_stem_cut_keys(state: dict, phase: str) -> None:
    for suffix in _PHASE_VOICE_STEM_CUT_KEYS + _PHASE_VOICE_STEM_TRIM_KEYS_LEGACY:
        state.pop(f"phase_{phase}_{suffix}", None)


def _phase_clear_lipsync_derived(state: dict, phase: str, *, requires_regen: bool) -> None:
    for suffix in _PHASE_LIPSYNC_DERIVED_KEYS:
        state.pop(f"phase_{phase}_{suffix}", None)
        nested = state.get(f"phase_{phase}")
        if isinstance(nested, dict):
            nested.pop(f"phase_{phase}_{suffix}", None)
    state[f"phase_{phase}_lipsync_requires_regen"] = requires_regen
    nested = state.setdefault(f"phase_{phase}", {})
    if isinstance(nested, dict):
        nested[f"phase_{phase}_lipsync_requires_regen"] = requires_regen


def _apply_phase_audio_trim(
    h,
    audio_path: Path,
    phase: str,
    state: dict,
    ts: str,
) -> tuple[Path, float]:
    """Resolve lipsync/mix audio path, applying persisted stem cut when active."""
    cut_start, cut_end = _phase_voice_stem_cut_window(state, phase)
    if cut_end <= cut_start + 0.001:
        return audio_path, _ffprobe_duration(audio_path)
    tmp_trim = h.app.event_dir / f"_tmp_stem_trim_phase_{phase}_{ts}.mp3"
    trimmed = _materialize_cut_out_audio(audio_path, tmp_trim, cut_start, cut_end)
    return trimmed, _ffprobe_duration(trimmed)


def _apply_whiteout_fade(video_path: Path, fade_dur: float = PHASE_B_WHITEOUT_DURATION_SEC) -> None:
    """Add a fade-to-white at the tail of *video_path*. Modifies file in-place.

    Uses ffprobe to get duration, then ffmpeg vf/af fade filters. Writes to a
    temp file then renames over the original (atomic on POSIX).
    """
    # Probe duration
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True, text=True, check=True,
    )
    duration = float(probe.stdout.strip())
    fade_start = max(0.0, duration - fade_dur)

    tmp = video_path.with_suffix(".whiteout_tmp.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", f"fade=out:st={fade_start:.3f}:d={fade_dur:.3f}:color=white",
            "-af", f"afade=out:st={fade_start:.3f}:d={fade_dur:.3f}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k",
            str(tmp),
        ],
        check=True, capture_output=True,
    )
    tmp.rename(video_path)
    print(
        f"[phase_b_whiteout] ✓ {fade_dur}s white fade applied "
        f"(fade_start={fade_start:.2f}s, total={duration:.2f}s)",
        flush=True,
    )

def handle_phase_watercolor_list(h)-> None:

    """GET /api/phase/watercolor_list — inventory of watercolor library.

    Reads Production/assets/watercolor_library/ for PNG/MOV files.
    Returns {items: [{key, filename, kind, thumb_url, mtime}]}.

    kind: 'static' for .png, 'animation' for .mov (animated via the
    Animate-this bridge — LD WATERCOLOR_ANIMATE_THIS_V1).

    Per LD PHASE_A_PRODUCER_V1 + PHASE_B_PRODUCER_V1 (replaces hardcoded
    JS array in v58).
    """
    wc_dir = _data_root(h) / "assets" / "watercolor_library"
    items: list[dict] = []
    if wc_dir.is_dir():
        # Build a set of static PNG/WebP stems for animation→base lookup below.
        static_stems = {
            p.stem for p in wc_dir.iterdir()
            if p.is_file() and p.suffix.lower().lstrip(".") in ("png", "webp")
        }
        for f in sorted(wc_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not f.is_file():
                continue
            ext = f.suffix.lower().lstrip(".")
            if ext not in ("png", "webp", "mov", "mp4"):
                continue
            # Test isolation: never surface smoke-test artifacts in the live library.
            # Files starting with _smoketest_ are test-only and may not have been
            # cleaned up by teardown. Filter here so UI never shows them.
            if f.name.startswith("_smoketest_"):
                continue
            # Skip 0-byte files — render likely failed mid-write; browser cannot decode them.
            if f.stat().st_size == 0:
                continue
            key = f.stem
            kind = "animation" if ext in ("mov", "mp4") else "static"
            # For animations, thumb_url points to the base static PNG so the tile
            # shows the actual watercolor art rather than a black first-frame.
            # Pattern: "hands_rubbing_animated_20260526-011128" → base "hands_rubbing"
            # (strip _animated_YYYYMMDD-HHMMSS suffix).
            thumb_key = key
            if kind == "animation":
                import re as _re
                base = _re.sub(r"_animated_\d{8}-\d{6}$", "", key)
                if base in static_stems:
                    thumb_key = base
            items.append({
                "key": key,
                "filename": f.name,
                "ext": ext,
                "kind": kind,
                "thumb_url": f"http://localhost:5111/api/phase/watercolor_file?key={thumb_key}",
                # animation_url: the actual MP4/MOV for overlay compositing (always black-bg,
                # rendered with mix-blend-mode:screen in the cue overlay).
                "animation_url": (
                    f"http://localhost:5111/api/phase_b/watercolor/{key}"
                    if kind == "animation" else None
                ),
                "mtime": int(f.stat().st_mtime),
                "size_bytes": f.stat().st_size,
            })
    return h._send_json(200, {
        "ok": True,
        "items": items,
        "count": len(items),
        "library_dir": str(wc_dir),
    })


def handle_phase_watercolor_file(h)-> None:

    """GET /api/phase/watercolor_file?key=<stem> — serve a single watercolor file.

    Helper for the watercolor_list thumb_url. Reads from the same
    directory; key is the basename without extension.
    """
    try:
        qs = urllib.parse.urlparse(h.path).query
        params = urllib.parse.parse_qs(qs)
        key_list = params.get("key")
        if not key_list:
            return h._send_error_v59(
                       400,
                       error_code="KEY_QUERY_PARAM_REQUIRED",
                       error_message="key query param required",
                       retry_safe=False,
                   )
        key = key_list[0]
        wc_dir = _data_root(h) / "assets" / "watercolor_library"
        # Direct stem lookup only. watercolor_list strips _animated_* from the
        # thumb_key so thumbnail requests always arrive with the BASE static key
        # (e.g. "hands_rubbing") — the {key}.* glob correctly returns the PNG.
        # Stitcher requests arrive with the FULL animated key
        # (e.g. "hands_rubbing_animated_20260527-223413") after the RC1 cue
        # update fires — {key}.* returns the MP4. No guessing needed.
        # (Reverted 2026-05-28: prior animated-glob-first approach broke
        # thumbnail display because base-key requests began returning MP4,
        # which <img> cannot render.)
        # Find the file by stem.
        matches = list(wc_dir.glob(f"{key}.*"))
        if not matches:
            return h._send_error_v59(
                       404,
                       error_code="GENERIC_ERROR",
                       error_message=f"no watercolor with key={key!r}",
                       retry_safe=False,
                   )
        f = matches[0]
        data = f.read_bytes()
        ext = f.suffix.lower().lstrip(".")
        ct = {
            "png": "image/png", "webp": "image/webp",
            "mov": "video/quicktime", "mp4": "video/mp4",
        }.get(ext, "application/octet-stream")
        h._send_bytes(200, data, ct,
                      extra_headers={"Cache-Control": "public, max-age=600"})
    except (OSError, KeyError) as exc:
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=True,
               )


def handle_phase_watercolor_delete(h, body: dict) -> None:
    """POST /api/phase/watercolor_delete — delete a watercolor file from the library.

    Body: {"key": "<stem>"}   e.g. "hands_rubbing" or "hands_rubbing_animated_20260527-223413"

    Deletes every file in watercolor_library/ whose stem matches key (normally one
    file, but handles rare sidecar cases). Returns 404 when key not found.
    """
    key = (body or {}).get("key")
    if not key:
        return h._send_error_v59(
            400,
            error_code="MISSING_KEY",
            error_message="'key' is required",
            retry_safe=False,
        )
    wc_dir = _data_root(h) / "assets" / "watercolor_library"
    matches = list(wc_dir.glob(f"{key}.*"))
    if not matches:
        return h._send_error_v59(
            404,
            error_code="NOT_FOUND",
            error_message=f"no watercolor with key={key!r}",
            retry_safe=False,
        )
    for f in matches:
        f.unlink()
    return h._send_json(200, {"status": "deleted", "key": key, "count": len(matches)})


def handle_phase_base_clips_list(h)-> None:

    """GET /api/phase/base_clips_list — inventory of lipsync base clips.

    Reads Production/assets/lipsync_bases/. Returns {items: [{id,
    filename, character, duration_s?}]}. Backups (.bak*) excluded.

    Per LDs PHASE_A_PRODUCER_V1 + PHASE_B_PRODUCER_V1.
    """
    bases_dir = _data_root(h) / "assets" / "lipsync_bases"
    items: list[dict] = []
    if bases_dir.is_dir():
        for f in sorted(bases_dir.iterdir(), key=lambda p: p.name):
            if not f.is_file():
                continue
            if ".bak" in f.name:
                continue
            ext = f.suffix.lower().lstrip(".")
            if ext not in ("mp4", "mov"):
                continue
            # Character is heuristic: "arlo", "chipper", or "cedric" in filename.
            lname = f.name.lower()
            character = (
                "arlo" if "arlo" in lname
                else "chipper" if "chipper" in lname
                else "cedric" if "cedric" in lname
                else None
            )
            # Duration: best-effort via ffprobe if available, else skip.
            duration_s: float | None = None
            try:
                duration_s = _ffprobe_duration(f)
            except Exception:
                duration_s = None
            items.append({
                "id": f.stem,
                "filename": f.name,
                "ext": ext,
                "character": character,
                "duration_s": round(duration_s, 3) if duration_s else None,
            })
    return h._send_json(200, {"ok": True, "items": items, "count": len(items)})


def handle_phase_b_ambient_preset_list(h)-> None:

    """GET /api/phase_b/ambient_preset_list — list ambient bed presets.

    Returns {ok, items: [{preset_id, file_size_bytes}], count}. Empty
    list (count=0) is a valid result — the producer UI surfaces a
    "no presets available" hint when the list is empty.

    Per LD AMBIENT_PRESET_SELECTOR_INPRODUCER_V1 (S5.5f spec §3.7).

    F-AMBIENT-001 (prod_blockers id=118) fix: directory was previously
    `Production/audio_library/ambient/` which does NOT exist on disk.
    The canonical sound-library convention used by `_handle_stitch_library`
    (line 15531: `production / "assets" / "sound_library"`) is the single
    source of truth. Endpoint now scans `Production/assets/sound_library/ambient/`.
    Note: endpoint name `phase_b_ambient_preset_list` is a misnomer (this is
    a global ambient catalog, not phase-b-specific) but renaming is out of
    scope for this fix per the parent dispatch.
    """
    ambient_dir = _data_root(h) / "assets" / "sound_library" / "ambient"
    items: list[dict] = []
    if ambient_dir.is_dir():
        for f in sorted(ambient_dir.iterdir(), key=lambda p: p.name):
            if not f.is_file():
                continue
            if f.suffix.lower() != ".mp3":
                continue
            items.append({
                "preset_id": f.stem,
                "file_size_bytes": f.stat().st_size,
            })
    return h._send_json(200, {"ok": True, "items": items, "count": len(items)})


# ---------------------------------------------------------------------------
# Anthropic helper — shared by suggest_script + brief generation
# ---------------------------------------------------------------------------

def _call_anthropic_urllib(api_key: str, req_body: dict, timeout: int = 60) -> tuple:
    """Make a single Anthropic Messages API call.
    Returns (resp_data_dict, elapsed_ms_int).
    Raises urllib.error.HTTPError or urllib.error.URLError on failure.
    """
    import urllib.request as _ur
    url = "https://api.anthropic.com/v1/messages"
    req_data = json.dumps(req_body).encode("utf-8")
    req = _ur.Request(
        url, data=req_data,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    t0 = time.time()
    with _ur.urlopen(req, timeout=timeout) as resp:
        resp_data = json.loads(resp.read().decode("utf-8"))
    return resp_data, int((time.time() - t0) * 1000)


def _build_therapeutic_brief(
    api_key: str,
    module_meta: dict,
    therapeutic_note: str,
    technique_inventory: str,
) -> dict | None:
    """Generate a structured therapeutic brief via a separate Haiku call.

    Returns dict with {goal, must_hits, what_to_evoke, watch_outs} or None on
    any failure. Never raises — brief is non-critical; script generation is the
    primary payload.

    Brief content spec (per Kim 2026-05-25):
      goal        — what the child will EXPERIENCE and to what clinical end
      must_hits   — ordered steps the exercise structurally requires
      what_to_evoke — internal state/feeling/insight/body-sensation
      watch_outs  — contraindications for children, clinical caveats
    """
    creature = module_meta.get('creature_name', '')
    technique = module_meta.get('technique_name', '') or '(see Therapeutic Note)'

    system_prompt = (
        "You generate tightly structured clinical guidance briefs for CRI-framework "
        "script writers (MindfulNest therapeutic app, ages 7–11). "
        "Return ONLY a valid JSON object — no preamble, no explanation, no markdown fences."
    )
    user_prompt = (
        f"Creature: {creature}\nTechnique: {technique}\n\n"
        f"Therapeutic Note:\n---\n{therapeutic_note or '(not available)'}\n---\n\n"
        "Return this exact JSON object and nothing else:\n"
        "{\n"
        '  "goal": "<one sentence: what the child will EXPERIENCE, and to what clinical end>",\n'
        '  "must_hits": ["<ordered step 1 the technique structurally requires>", "<step 2>", "..."],\n'
        '  "what_to_evoke": ["<internal state / feeling / insight / body-sensation bullet>", "..."],\n'
        '  "watch_outs": ["<contraindication for children OR clinical caveat OR thing to avoid>", "..."]\n'
        "}\n\n"
        "Rules:\n"
        "  - goal: exactly ONE sentence, clinically precise\n"
        "  - must_hits: 2–4 bullets, ORDERED (step 1 then step 2 etc.), structural requirements of the technique\n"
        "  - what_to_evoke: 2–4 bullets — the internal state/insight/realization/body-feeling the child reaches\n"
        "    (child-accessible language — what the child actually notices, not clinical terminology)\n"
        "  - watch_outs: 2–4 bullets — contraindications for children, clinical caveats, things to avoid;\n"
        "    clinical precision OK here (Kim is the therapist)\n"
        "  - ONLY the JSON object. No extra text, no markdown fences."
    )
    req_body = {
        "model": "claude-haiku-4-5",
        "max_tokens": 512,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    try:
        resp_data, _ = _call_anthropic_urllib(api_key, req_body, timeout=30)
        content = resp_data.get("content") or []
        raw = ""
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                raw += block.get("text", "")
        raw = raw.strip()
        # Strip markdown fences if model ignores instructions
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        brief = json.loads(raw)
        # Validate expected keys are present
        required = ("goal", "must_hits", "what_to_evoke", "watch_outs")
        for k in required:
            if k not in brief:
                print(f"[suggest_script] brief missing key {k!r} — dropping brief")
                return None
        return brief
    except Exception as exc:
        print(f"[suggest_script] therapeutic brief generation failed (non-fatal): {exc}")
        return None


def handle_phase_suggest_script(h, body: dict)-> None:

    """POST /api/phase/suggest_script {phase, event_id?, scope_event_id?}

    Drafts a Phase A or Phase B script via Claude API, grounded in the
    authored Therapeutic Note + Unified Technique Inventory for the
    current module.

    Resolves the current event_id (e.g., 'M1E1') to module metadata via
    prod_modules (arc_number, m_number, creature_name, technique_name),
    then loads:
      - The '### Therapeutic Note —' section from
        Arc Skeletons/ARC_NN_SKELETON_FINAL.md matching the (M<m_number>)
        marker in the event title.
      - The Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_<latest>.md (canonical
        technique catalog with mechanism + age suitability + clinical refs).

    Phase A: also reads phase_b_script (so the demo references the
    meditation that just played) and tailors output to the Chipper voice
    + 30-60s playful demo format.
    Phase B: produces 90-120s Cedric meditation with cue markers and
    9-step arc, grounded in the Therapeutic Note's clinical framing.

    Per LDs PHASE_A_PRODUCER_V1 + PHASE_B_PRODUCER_V1 +
    PB_2_THERAPEUTIC_SOURCES_LOAD_V1 (locked 2026-05-13 to close the
    silent-failure: prior implementation ignored both the Therapeutic
    Note and the Technique Inventory, producing generic meditation text
    for every module regardless of the authored technique).
    """
    # READ-ONLY probe (LLM script suggestion — does not mutate state).
    # Per spec_v2 §5.2 + SCOPE_REQUIRED_DEFAULTS_V1 read-only probes keep
    # allow_missing=True.
    if not h._assert_event_scope(h._scope_body(body), allow_missing=True):
        return
    phase = ((body or {}).get("phase") or "").strip().lower()
    if phase not in ("a", "b"):
        return h._send_error_v59(
                   400,
                   error_code="PHASE_MUST_BE_A_OR",
                   error_message="phase must be 'a' or 'b'",
                   retry_safe=False,
               )

    # Resolve the Anthropic API key.
    try:
        sys.path.insert(0, str(_PSERVER_REPO_ROOT / "lib"))
        from credential_store import get_secret_optional  # type: ignore
        api_key = get_secret_optional("ANTHROPIC_API_KEY")
    except Exception:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return h._send_json(503, {
            "ok": False,
            "code": "ANTHROPIC_API_KEY_MISSING",
            "message": (
                "Anthropic API key not configured. Add ANTHROPIC_API_KEY to "
                "Doppler (project=mindfulnest, config=dev) or set the env var "
                "and restart the server. Endpoint code is ready."
            ),
            "phase": phase,
        })

    # Read state + resolve the event_id to module metadata.
    try:
        state = h.app.state.read_state()
    except Exception:
        state = {}

    scope = h._scope_body(body)
    # Prefer state.event_id (canonical 'M<n>E<m>' form, e.g. 'M1E1') over
    # scope.event_id (directory form, e.g. 'Event_1') so the prod_modules
    # resolver finds the row. state stores the M-form because it's the
    # event identity from the production pipeline; scope normalizes to
    # directory-id for scope-guard routing.
    event_id_str = (
        state.get('event_id')
        or (body or {}).get('event_id')
        or scope.get('event_id')
        or (body or {}).get('scope_event_id')
        or ''
    )
    module_meta = _resolve_module_for_event(event_id_str) or {
        'arc_number': 1, 'm_number': 1, 'event_number': 1,
        'creature_name': 'Unknown', 'technique_name': '',
    }

    # Load the authored therapeutic sources for this module.
    bg = _bg_module()
    therapeutic_note = bg.extract_therapeutic_note(
        module_meta['arc_number'], module_meta['m_number'],
    )
    technique_inventory = bg.load_technique_inventory()

    # Sources_loaded telemetry — surfaced in the JSON response so callers
    # can detect the silent-failure regression class (handler runs but
    # therapeutic sources fail to load).
    sources_loaded = {
        'therapeutic_note_chars': len(therapeutic_note),
        'technique_inventory_chars': len(technique_inventory),
        'arc_number': module_meta['arc_number'],
        'm_number': module_meta['m_number'],
        'creature_name': module_meta['creature_name'],
        'technique_name': module_meta['technique_name'],
    }
    if not therapeutic_note:
        print(
            f'[suggest_script] WARNING: no Therapeutic Note found for '
            f'arc={module_meta["arc_number"]} m_number={module_meta["m_number"]} '
            f'event_id={event_id_str!r}. Claude prompt will lack authored context.'
        )
    if not technique_inventory:
        print(
            '[suggest_script] WARNING: technique inventory unavailable at '
            'Canon/UNIFIED_TECHNIQUE_INVENTORY_v1_*.md. Claude prompt will '
            'lack canonical technique catalog.'
        )

    # Module identity block — shared header for both phases.
    module_identity = (
        f"Module identity (resolved from event_id={event_id_str!r}):\n"
        f"  - Arc: {module_meta['arc_number']}\n"
        f"  - M-number: M{module_meta['m_number']}\n"
        f"  - Creature: {module_meta['creature_name']}\n"
        f"  - Technique: {module_meta['technique_name'] or '(see Therapeutic Note below)'}\n"
    )

    therapeutic_section = (
        "Authored Therapeutic Note for THIS module (from Arc Skeleton — "
        "this is the canonical source of truth for the technique, "
        "rationale, and clinical framing; the script MUST teach the "
        "technique it describes, not a generic meditation):\n"
        f"---\n{therapeutic_note}\n---\n"
        if therapeutic_note
        else "Authored Therapeutic Note: (NOT FOUND — Claude must explicitly state this gap in the response if asked to write a clinically-grounded script)\n"
    )

    technique_section = (
        "Canonical Technique Inventory (the catalog of all MindfulNest "
        "techniques with mechanism, age suitability, and clinical "
        "references — use the matching entry as the authoritative "
        "definition of the technique):\n"
        f"---\n{technique_inventory}\n---\n"
        if technique_inventory
        else ""
    )

    if phase == "a":
        # S5.5d (v3): phase_b is TOP-LEVEL state.
        _phase_b_partition = state.get("phase_b") or {}
        phase_b_script = _phase_b_partition.get("phase_b_script") or "(no phase_b_script in state — write Phase B first or paste a draft to seed context)"
        user_prompt = (
            "You are drafting a Phase A 'demo' script for an interactive "
            "children's therapeutic app (MindfulNest, ages 7-11). Phase A "
            "is the Chipper-led playful demonstration that follows Phase "
            "B's calm meditation. The child has just completed Phase B; "
            "Chipper now demonstrates the technique so the child can try "
            "it themselves.\n\n"
            f"{module_identity}\n"
            f"{therapeutic_section}\n"
            f"{technique_section}\n"
            "Phase B script just completed (the meditation the child "
            f"just heard):\n---\n{phase_b_script}\n---\n\n"
            "Constraints:\n"
            "  - 30-60 seconds spoken (Chipper voice — bright, playful, "
            "    encouraging).\n"
            "  - Direct address ('let's try this together').\n"
            "  - Reference the technique by its in-world spell name "
            "    (e.g., 'Magic Hands Spell') from the Therapeutic Note.\n"
            "  - Demonstrate ONE concrete action the child can do at "
            "    home (e.g., 'put your hands together and feel the warm "
            "    tingly feeling').\n"
            "  - Don't restate the meditation — demonstrate it.\n"
            "  - No clinical jargon. No stage directions. Plain spoken "
            "    text.\n\n"
            "Write the Phase A demo script now."
        )
        system_prompt = (
            "You are a CRI (Competence-Rooted Identity) script writer "
            "for MindfulNest, drafting Phase A playful demonstrations "
            "for ages 7-11 in the Chipper guide-bird voice. Ground every "
            "script in the authored Therapeutic Note + Technique "
            "Inventory provided in the user message."
        )
    else:  # phase == "b"
        user_prompt = (
            "You are drafting a Phase B meditation script for MindfulNest "
            "(ages 7-11), narrated by Cedric the wizard.\n\n"
            f"{module_identity}\n"
            f"{therapeutic_section}\n"
            f"{technique_section}\n"
            "## TEMPLATE SELECTION\n\n"
            "Choose the correct template based on the technique type:\n\n"
            "1. **Sequential-step** — technique has 2-3 mechanically distinct "
            "physical steps in order; the CONTRAST between steps (the release, "
            "the long exhale) is the clinical payload. Examples: Physiological "
            "Sigh, Squeeze & Release.\n"
            "   Structure: WELCOME→CONNECTION→SETUP (name step count)→"
            "PART 1→PART 2→[PART 3]→FULL ROUND (narrator paces only, minimal "
            "words)→LANDING→EXIT. Word budget ~110-145.\n\n"
            "2. **Cycle-based** — pure rhythmic counting (4-7-8, box breathing).\n"
            "   Structure: WELCOME→CONNECTION→SETUP→CYCLE 1→TRANSITION→"
            "CYCLE 2→LANDING→EXIT. Word budget ~120-140.\n\n"
            "3. **Standard 7-section** — child feels a single sustained physical "
            "action (warmth, belly moving, muscle relaxation).\n"
            "   Structure: WELCOME→CONNECTION→SETUP→INSTRUCTION→DEEPENING→"
            "LANDING→EXIT. Word budget ~120-160.\n\n"
            "4. **Preview-enhanced** — technique is mental/cognitive (invisible). "
            "Add PREVIEW (full walk-through before starting), CHECK-IN, and "
            "an ACTION MARKER at the key therapeutic moment.\n"
            "   Structure: WELCOME→CONNECTION→PREVIEW→SETUP→INSTRUCTION→"
            "CHECK-IN→GUIDED PRACTICE→LANDING→EXIT. Word budget ~150-180.\n\n"
            "## STRUCTURAL CONSTANTS (every template)\n\n"
            "- WELCOME: Opens with 'Ahh...' (warm exhale, not a word). "
            "Ends with 'Good.' as its own beat. {childName} appears ONCE, "
            "in WELCOME only.\n"
            "- CONNECTION: Uses exact Phase A vocabulary. Never re-teaches "
            "what Phase A showed.\n"
            "- LANDING: Names the felt experience. Use 'that's your magic' "
            "or equivalent ownership framing. Conditional: 'notice if you "
            "feel it' — NOT 'you will feel calm.'\n"
            "- EXIT: 'Stay right there. Keep [breathing / feeling that]...' "
            "— trails off. Do NOT conclude. Rescue sustain picks up here.\n"
            "- 'you' never 'we'. Conditional sensation language throughout. "
            "No clinical jargon. No therapy-speak.\n\n"
            "## PACING FORMAT\n\n"
            "Write plain sentences only — no 'Cedric:' prefixes.\n"
            "Two-tier pause system:\n"
            "  - Short pauses (< 2s): use ellipsis (… or …..) inline "
            "within the sentence.\n"
            "  - Long pauses (2s+): use [silence:Ns] tag (e.g. "
            "[silence:4s], [silence:6s], [silence:9s]). The server "
            "processes these into real ffmpeg silence — they produce "
            "EXACT timed gaps in the audio. Use them generously for "
            "the child to actually feel the sensation.\n"
            "  - [long pause] is also valid for a medium pause (~2s).\n"
            "  - [warm] at the very start signals a warm tonal cue.\n"
            "End the script with the wizard releasing the child "
            "('off you go, little one') — do NOT write "
            "'[fade to Rescue sustain]'.\n\n"
            "## FEW-SHOT EXAMPLE (Kim's final approved M1 script — May 2026)\n\n"
            "This is the canonical format. Match this sparseness and "
            "silence placement exactly. 'little one' not '{childName}'.\n\n"
            "[warm] Ah, yes. ….. Welcome little one …... I am your Magical "
            "Arts teacher. I've come to teach you …. the Magic Hands Spell.\n"
            "You'll make a real ball of energy … right between your "
            "hands.[long pause]\n"
            "Step One. [long pause] Rub your hands together. …. Getting "
            "warmer … warmer.[silence:4s]\n"
            "Good.\n"
            "Now imagine a soccer-sized ball of magic in your "
            "hands. [silence:6s]\n"
            "Can you feel it? [long pause] [long pause] Big breath "
            "in.[long pause]\n"
            "As you breathe out, move your hands closer "
            "together. [silence:8s]\n"
            "Good. Pull your hands farther apart. [silence:6s]\n"
            "Now move your hands in and out, however you like. Play with "
            "the energy you feel between your hands.[silence:9s]\n"
            "Keep breathing. [silence:4s]\n"
            "What do you feel between your hands? … Pulling? … Tingling? "
            "… Warmth? … [silence:6s]\n"
            "Can you move the energy around?[silence:4s]\n"
            "That's the magic you have inside of you.\n"
            "Let that magic grow stronger... [silence:4s]. Now, off you "
            "go, little one. Come back again later for your next lesson.\n\n"
            "IMPORTANT: Use [silence:Ns] for pauses where the child needs "
            "to actually feel something — do NOT replace long silences with "
            "ellipsis. No 'Cedric:' prefixes. No {{BELL_CUE}} or "
            "{{PAUSE:Xs}} markers.\n\n"
            "## TASK\n\n"
            "Select the correct template from the four above based on the "
            "technique in the Therapeutic Note. Apply all structural "
            "constants and cue markers. Match the sparseness and pacing "
            "of the few-shot example. Write the Phase B script now."
        )
        system_prompt = (
            "You are a CRI script writer drafting Phase B meditation "
            "scripts for MindfulNest (ages 7-11), narrated by Cedric "
            "the wizard. Ground every script in the authored Therapeutic "
            "Note + Technique Inventory in the user message. Never invent "
            "or substitute techniques. Follow the template structure, "
            "structural constants, and cue markers exactly as provided."
        )

    # Call Anthropic in PARALLEL: (1) script generation, (2) therapeutic brief.
    # Both use Haiku. Brief failure is non-fatal — returns null in the response.
    # Using _cf (concurrent.futures) already imported at module top.
    script_req = {
        "model": "claude-haiku-4-5",
        "max_tokens": 2048,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    with _cf.ThreadPoolExecutor(max_workers=2) as pool:
        script_future = pool.submit(_call_anthropic_urllib, api_key, script_req, 60)
        brief_future = pool.submit(
            _build_therapeutic_brief,
            api_key, module_meta, therapeutic_note, technique_inventory,
        )
        # Script result — errors are fatal, returned as HTTP error response
        try:
            resp_data, elapsed_ms = script_future.result()
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            return h._send_error_v59(
                502, error_code="GENERIC_ERROR",
                error_message=f"Anthropic API HTTP {exc.code}",
                retry_safe=True,
                extra={"ok": False, "detail": err_body[:500]},
            )
        except urllib.error.URLError as exc:
            return h._send_error_v59(
                502, error_code="GENERIC_ERROR",
                error_message=f"Anthropic API URL error: {exc}",
                retry_safe=True,
                extra={"ok": False},
            )
        # Brief result — non-fatal
        try:
            therapeutic_brief = brief_future.result()
        except Exception as exc:
            print(f"[suggest_script] brief future error (non-fatal): {exc}")
            therapeutic_brief = None

    # Extract text from script response.
    content = resp_data.get("content") or []
    script_text = ""
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            script_text += block.get("text", "")
    usage = resp_data.get("usage") or {}
    return h._send_json(200, {
        "ok": True,
        "phase": phase,
        "script": script_text,
        "therapeutic_brief": therapeutic_brief,
        "model_used": resp_data.get("model", "claude-haiku-4-5"),
        "generation_time_ms": elapsed_ms,
        "tokens_in": usage.get("input_tokens"),
        "tokens_out": usage.get("output_tokens"),
        "sources_loaded": sources_loaded,
    })


def _parse_silence_segments(script: str):
    """Split script on [silence:Ns] tags.

    Returns list of ('text', str) | ('silence', float) tuples.
    Strips whitespace from text segments; preserves order.
    """
    import re as _re
    _PAT = _re.compile(r'\[silence:\s*(\d+(?:\.\d+)?)\s*s?\]', _re.IGNORECASE)
    parts = []
    last = 0
    for m in _PAT.finditer(script):
        chunk = script[last:m.start()].strip()
        if chunk:
            parts.append(('text', chunk))
        parts.append(('silence', float(m.group(1))))
        last = m.end()
    tail = script[last:].strip()
    if tail:
        parts.append(('text', tail))
    return parts


def _build_silence_mp3(duration_s: float, out_path) -> None:
    """Write a silent MP3 of exact duration using ffmpeg anullsrc."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(duration_s),
            "-acodec", "libmp3lame",
            "-b:a", "128k",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def handle_phase_reject_lipsync(h, body: dict) -> None:
    """POST /api/phase_{a|b}/reject_lipsync

    Clears lipsync + derived mix/stitch state so the waveform returns to the
    voice stem. Keeps the lipsync MP4 on disk (archived filename optional later).
    Body: {"phase": "a"|"b"}
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    phase = (body.get("phase") or "").strip().lower()
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
            400,
            error_code="GENERIC_ERROR",
            error_message=err,
            retry_safe=False,
            extra={"hint": "phase is 'a' or 'b'."},
        )

    state = h.app.state.read_state()
    lipsync_name = state.get(f"phase_{phase}_lipsync_file")
    if not lipsync_name:
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=f"phase_{phase}_lipsync_file not set — nothing to reject",
            retry_safe=False,
            extra={"hint": "Generate a lipsync first, or edit the stem trim directly if no video exists."},
        )

    if state.get(f"phase_{phase}_lipsync_status") == "running":
        return h._send_error_v59(
            409,
            error_code="PHASE_LIPSYNC_RUNNING",
            error_message=f"Phase {phase.upper()} lipsync still running",
            retry_safe=False,
            extra={"hint": "Wait for the in-flight job to finish or time out before rejecting."},
        )

    archived_name: str | None = None
    try:
        src = require_basename_under_dir(lipsync_name, h.app.event_dir)
        if src.is_file():
            archive_dir = h.app.event_dir / "_rejected_lipsync"
            archive_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            archived = archive_dir / f"phase_{phase}_lipsync_rejected_{ts}_{src.name}"
            shutil.move(str(src), str(archived))
            archived_name = archived.name
    except (ValueError, OSError) as exc:
        print(f"[phase_reject_lipsync] archive move skipped: {exc}", flush=True)

    def _apply(st, _p=phase):
        _phase_clear_lipsync_derived(st, _p, requires_regen=True)
        st[f"phase_{_p}_lipsync_status"] = "rejected"
        st["_module_version"] = int(st.get("_module_version", 0) or 0) + 1
        return st["_module_version"]

    try:
        new_version = h.app.state.mutate_state(_apply)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
            500,
            error_code="GENERIC_ERROR",
            error_message=f"mutate_state failed: {type(exc).__name__}: {exc}",
            retry_safe=True,
        )

    return h._send_json(200, {
        "ok": True,
        "phase": phase,
        "archived_file": archived_name,
        "previous_lipsync_file": lipsync_name,
        "module_version": new_version,
        "message": (
            "Lipsync cleared from state — waveform now shows voice stem. "
            "Set stem trim (front/back seconds), then Send for Lipsync."
        ),
    })


def handle_phase_apply_stem_cut(h, body: dict) -> None:
    """POST /api/phase_{a|b}/apply_stem_cut

    Bakes persisted stem trim into a new voice_stem mp3 (ffmpeg), replaces
    phase_{phase}_voice_stem_file, clears trim keys, and invalidates lipsync.
    Body: {"phase": "a"|"b"}
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    phase = (body.get("phase") or "").strip().lower()
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
            400,
            error_code="GENERIC_ERROR",
            error_message=err,
            retry_safe=False,
            extra={"hint": "phase is 'a' or 'b'."},
        )

    state = h.app.state.read_state()
    stem_name = state.get(f"phase_{phase}_voice_stem_file")
    if not stem_name:
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=f"phase_{phase}_voice_stem_file not set",
            retry_safe=False,
            extra={"hint": "Generate a voice stem first."},
        )

    cut_start, cut_end = _phase_voice_stem_cut_window(state, phase)
    if cut_end <= cut_start + 0.001:
        return h._send_error_v59(
            400,
            error_code="GENERIC_ERROR",
            error_message="No stem cut region set — drag amber handles first",
            retry_safe=False,
            extra={"hint": "Amber box = audio to REMOVE. Drag handles, then Apply Cut."},
        )

    try:
        src = require_basename_under_dir(stem_name, h.app.event_dir)
    except ValueError as exc:
        return h._send_error_v59(
            400,
            error_code="GENERIC_ERROR",
            error_message=str(exc),
            retry_safe=False,
        )

    if not src.is_file():
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=f"voice stem missing on disk: {stem_name}",
            retry_safe=False,
        )

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_name = f"phase_{phase}_voice_stem_{ts}.mp3"
    out_path = h.app.event_dir / out_name
    try:
        _materialize_cut_out_audio(src, out_path, cut_start, cut_end)
        duration = _ffprobe_duration(out_path)
    except (subprocess.CalledProcessError, ValueError, OSError) as exc:
        traceback.print_exc()
        return h._send_error_v59(
            500,
            error_code="GENERIC_ERROR",
            error_message=f"stem cut failed: {exc}",
            retry_safe=True,
            extra={"hint": "Check ffmpeg/ffprobe and trim window size."},
        )

    mtime = int(os.path.getmtime(str(out_path)))

    def _apply(st, _p=phase, _n=out_name, _m=mtime):
        st[f"phase_{_p}_voice_stem_file"] = _n
        st[f"phase_{_p}_voice_stem_mtime"] = _m
        _phase_clear_stem_cut_keys(st, _p)
        _phase_clear_lipsync_derived(st, _p, requires_regen=True)
        st["_module_version"] = int(st.get("_module_version", 0) or 0) + 1
        return st["_module_version"]

    try:
        new_version = h.app.state.mutate_state(_apply)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
            500,
            error_code="GENERIC_ERROR",
            error_message=f"mutate_state failed: {type(exc).__name__}: {exc}",
            retry_safe=True,
        )

    return h._send_json(200, {
        "ok": True,
        "phase": phase,
        "file": out_name,
        "mtime": mtime,
        "duration_s": round(duration, 3),
        "cut_start_s": cut_start,
        "cut_end_s": cut_end,
        "previous_stem_file": stem_name,
        "module_version": new_version,
        "message": "Stem cut applied — removed amber region; waveform reloads kept audio.",
    })


def handle_phase_b_regen_audio(h, body: dict)-> None:

    """POST /api/phase_b/regen_audio

    Body: {"phase": "a"|"b", "script": "text"}

    Supports [silence:Ns] tags in script for exact server-side silence injection.
    Splits script at markers, calls ElevenLabs per segment, ffmpeg-concats with
    real silence between segments.  Single-segment scripts use the fast single-call path.

    Writes phase_{phase}_voice_stem_<TS>.mp3 to event_dir root.
    Patches state phase_X_voice_stem_file + phase_X_voice_stem_mtime via mutate_state.
    Returns 200 with file path + duration on success.
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_phase_b_regen_audio',
    }
    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
    # If the event was swapped via /api/event/load between scope-guard
    # and work start, abort BEFORE any expensive work begins.
    if not h._check_event_pin(_pin, '_handle_phase_b_regen_audio_pre_work'):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": '_handle_phase_b_regen_audio', "hint": "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."},
               )

    phase = (body.get("phase") or "").strip().lower()
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
                   extra={"hint": "phase is 'a' (Chipper) or 'b' (Cedric)."},
               )
    script = body.get("script") or ""
    if not isinstance(script, str) or not script.strip():
        return h._send_error_v59(
                   400,
                   error_code="SCRIPT_IS_REQUIRED_AND_MUST",
                   error_message="script is required and must be non-empty string",
                   retry_safe=False,
                   extra={"hint": "Paste the Phase {} script in the panel textarea.".format(phase.upper())},
               )
    if len(script) > 50_000:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"script too long ({len(script)} chars, max 50000)",
                   retry_safe=False,
                   extra={"hint": "Split into shorter segments or edit down."},
               )

    # Load ElevenLabs key via parse_api_keys pattern (matches server-wide usage).
    root = h._phase_project_root()
    keys = parse_api_keys(root / "Production" / "API_KEYS_MASTER.md")
    elevenlabs_key = keys.get("elevenlabs")
    if not elevenlabs_key:
        return h._send_error_v59(
                   500,
                   error_code="ELEVENLABS_API_KEY_NOT_CONFIGURED",
                   error_message="ElevenLabs API key not configured",
                   retry_safe=True,
                   extra={"hint": "Set ELEVENLABS_API_KEY env var or populate API_KEYS_MASTER.md."},
               )

    voice_id, model_id, voice_settings, speaker = h._phase_resolve_voice_settings(phase)
    # Universal hardening: robust_https_request with 3 retries + 90s timeout.
    from kling_startend_pipeline import robust_https_request  # noqa: PLC0415

    def _tts_call(text_segment: str):
        """Single ElevenLabs TTS call; returns (status_code, bytes)."""
        body_bytes = json.dumps({
            "text": text_segment,
            "model_id": model_id,
            "voice_settings": voice_settings,
        }).encode("utf-8")
        return robust_https_request(
            host="api.elevenlabs.io",
            path=f"/v1/text-to-speech/{voice_id}",
            method="POST",
            headers={"xi-api-key": elevenlabs_key,
                     "Content-Type": "application/json",
                     "Accept": "audio/mpeg"},
            body=body_bytes,
            timeout=90,
            max_retries=3,
        )

    segments = _parse_silence_segments(script)
    # Fast path: no [silence:Ns] tags → single TTS call (original behaviour).
    use_multi = any(kind == 'silence' for kind, _ in segments)

    t0 = time.time()
    if not use_multi:
        try:
            status_code, audio_bytes = _tts_call(script)
        except Exception as exc:  # noqa: BLE001
            return h._send_error_v59(
                       502,
                       error_code="GENERIC_ERROR",
                       error_message=f"ElevenLabs network failure (after retries): "
                         f"{type(exc).__name__}: {exc}",
                       retry_safe=True,
                       extra={"speaker": speaker, "voice_id": voice_id,
                              "hint": "Check network / ElevenLabs status. Retry after a minute."},
                   )
        if status_code >= 400:
            detail = audio_bytes[:400].decode("utf-8", errors="replace")
            return h._send_error_v59(
                       502,
                       error_code="GENERIC_ERROR",
                       error_message=f"ElevenLabs HTTP {status_code}: {detail}",
                       retry_safe=True,
                       extra={"speaker": speaker,
                              "hint": "Often: API key expired or voice_id renamed. Check API_KEYS_MASTER.md."},
                   )
    else:
        # Multi-segment path: call ElevenLabs per text segment, inject real silence.
        import tempfile as _tempfile
        tmp_dir = Path(_tempfile.mkdtemp(prefix="mn_regen_audio_"))
        concat_parts = []  # list of pathlib.Path in order
        try:
            seg_idx = 0
            for kind, value in segments:
                if kind == 'text':
                    seg_path = tmp_dir / f"seg_{seg_idx:03d}_speech.mp3"
                    try:
                        sc, seg_bytes = _tts_call(value)
                    except Exception as exc:  # noqa: BLE001
                        return h._send_error_v59(
                                   502,
                                   error_code="GENERIC_ERROR",
                                   error_message=f"ElevenLabs segment {seg_idx} network failure: "
                                     f"{type(exc).__name__}: {exc}",
                                   retry_safe=True,
                                   extra={"segment_index": seg_idx, "speaker": speaker},
                               )
                    if sc >= 400:
                        detail = seg_bytes[:400].decode("utf-8", errors="replace")
                        return h._send_error_v59(
                                   502,
                                   error_code="GENERIC_ERROR",
                                   error_message=f"ElevenLabs segment {seg_idx} HTTP {sc}: {detail}",
                                   retry_safe=True,
                                   extra={"segment_index": seg_idx, "speaker": speaker},
                               )
                    seg_path.write_bytes(seg_bytes)
                    concat_parts.append(seg_path)
                    seg_idx += 1
                else:  # silence
                    sil_path = tmp_dir / f"seg_{seg_idx:03d}_silence_{value}s.mp3"
                    try:
                        _build_silence_mp3(value, sil_path)
                    except subprocess.CalledProcessError as exc:
                        return h._send_error_v59(
                                   500,
                                   error_code="GENERIC_ERROR",
                                   error_message=f"ffmpeg silence generation failed for {value}s: {exc}",
                                   retry_safe=True,
                               )
                    concat_parts.append(sil_path)
                    seg_idx += 1

            # ffmpeg concat all parts into final bytes.
            list_file = tmp_dir / "concat_list.txt"
            list_file.write_text(
                "\n".join(f"file '{p}'" for p in concat_parts),
                encoding="utf-8",
            )
            concat_out = tmp_dir / "concat_out.mp3"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", str(list_file),
                    "-acodec", "libmp3lame", "-b:a", "128k",
                    str(concat_out),
                ],
                check=True,
                capture_output=True,
            )
            audio_bytes = concat_out.read_bytes()
        finally:
            # Clean up temp dir regardless of success/failure.
            import shutil as _shutil
            _shutil.rmtree(tmp_dir, ignore_errors=True)

    elapsed_call = time.time() - t0

    # Atomic write to event_dir root.
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_name = f"phase_{phase}_voice_stem_{ts}.mp3"
    out_path = h.app.event_dir / out_name
    tmp = out_path.with_suffix(f".mp3.tmp.{os.getpid()}")
    # LD-460 — terminal pin check before voice-stem file write.
    if not h._check_event_pin(_pin, "phase_b_regen_audio_write_bytes"):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_MID_JOB",
                   error_message="event_changed_mid_job",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1"},
               )
    try:
        tmp.write_bytes(audio_bytes)
        os.replace(tmp, out_path)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"atomic write failed: {exc}",
                   retry_safe=True,
                   extra={"hint": "Check event_dir permissions / disk space."},
               )
    # NOTE: No atempo post-processing on the regen_audio (audition) path.
    # ElevenLabs speed=0.50 (from Directus voice profile) already gives meditative
    # pacing for auditioning word delivery. Compounding atempo=0.75 on top produces
    # 37.5% normal speed — unnatural and artifacts on deep voices.
    # The Python production render (render_phase_b_v9_meditation.py) applies
    # atempo=0.75 on the final render where sentence-level silences are added
    # separately and the compounding is intentional.
    try:
        duration = _ffprobe_duration(out_path)
    except (subprocess.CalledProcessError, ValueError, OSError):
        duration = 0.0
    mtime = int(os.path.getmtime(str(out_path)))

    # Patch state via mutate_state.
    def _apply(state, _p=phase, _n=out_name, _m=mtime):
        state[f"phase_{_p}_voice_stem_file"] = _n
        state[f"phase_{_p}_voice_stem_mtime"] = _m
        # Fresh stem invalidates lipsync/mix/stitch derived from the old audio.
        _phase_clear_lipsync_derived(state, _p, requires_regen=True)
        _phase_clear_stem_cut_keys(state, _p)
        state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
        return state["_module_version"]
    try:
        new_version = h.app.state.mutate_state(_apply)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"mutate_state failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"hint": "State.json could not be persisted. File was written to disk."},
               )

    return h._send_json(200, {
        "status": "ok",
        "phase": phase,
        "file": out_name,
        "mtime": mtime,
        "duration_s": round(duration, 3),
        "size_bytes": len(audio_bytes),
        "voice_id": voice_id,
        "speaker": speaker,
        "elapsed_s": round(elapsed_call, 2),
        "module_version": new_version,
    })


def handle_phase_b_mix_audio(h, body: dict)-> None:

    """POST /api/phase_b/mix_audio

    Body: {"phase": "a"|"b", "ambient_preset_id": "meditation_fireplace_v1"}

    Reads phase_{phase}_voice_stem_file from state (must exist).
    Loads ambient from Production/assets/ambient_library/<ambient_preset_id>.mp3.
    Mixes voice (0dB) + ambient (-18dB) via ffmpeg amix filter.
    Writes phase_{phase}_mixed_<TS>.mp3 and patches state.
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_phase_b_mix_audio',
    }
    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — pre-work pin check (S2).
    # If the event was swapped via /api/event/load between scope-guard
    # and work start, abort BEFORE any expensive work begins.
    if not h._check_event_pin(_pin, '_handle_phase_b_mix_audio_pre_work'):
        return h._send_error_v59(
                   423,
                   error_code="EVENT_CHANGED_PRE_WORK",
                   error_message="event_changed_pre_work",
                   retry_safe=False,
                   extra={"code": "ASYNC_JOB_GENERATION_PIN_V1", "handler": '_handle_phase_b_mix_audio', "hint": "Event changed between scope-guard and work start. "
                "No work was done; no orphan output. Client should "
                "re-hydrate scope and retry."},
               )

    phase = (body.get("phase") or "").strip().lower()
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
                   extra={"hint": "phase is 'a' or 'b'."},
               )
    ambient_preset_id = body.get("ambient_preset_id")
    if not ambient_preset_id or not isinstance(ambient_preset_id, str):
        # Fallback: UI may omit preset if state was set via dropdown patch only.
        state_for_preset = h.app.state.read_state()
        ambient_preset_id = state_for_preset.get(f"phase_{phase}_ambient_preset_id")
    if not ambient_preset_id or not isinstance(ambient_preset_id, str):
        return h._send_error_v59(
                   400,
                   error_code="AMBIENT_PRESET_ID_IS_REQUIRED",
                   error_message="ambient_preset_id is required (string)",
                   retry_safe=False,
                   extra={"hint": "Pick from the ambient preset dropdown."},
               )
    if "/" in ambient_preset_id or "\\" in ambient_preset_id or ".." in ambient_preset_id:
        return h._send_error_v59(
                   400,
                   error_code="INVALID_AMBIENT_PRESET_ID",
                   error_message="invalid ambient_preset_id",
                   retry_safe=False,
               )
    # Resolve voice stem from state.
    state = h.app.state.read_state()
    voice_stem_name = state.get(f"phase_{phase}_voice_stem_file")
    if not voice_stem_name:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"phase_{phase}_voice_stem_file not set in state",
                   retry_safe=False,
                   extra={"hint": "Run Regen Audio first to produce a voice stem."},
               )
    try:
        voice_stem_path = require_basename_under_dir(voice_stem_name, h.app.event_dir)
    except ValueError as exc:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
               )
    if not voice_stem_path.is_file():
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"voice stem file not found: {voice_stem_name}",
                   retry_safe=False,
                   extra={"hint": "File may have been deleted. Re-run Regen Audio."},
               )
    # Resolve ambient preset.
    ambient_dir = h._phase_assets_dir("ambient_library")
    try:
        ambient_path = require_basename_under_dir(
            f"{ambient_preset_id}.mp3", ambient_dir,
        )
    except ValueError as exc:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=str(exc),
                   retry_safe=False,
               )
    if not ambient_path.is_file():
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"ambient preset not found: {ambient_preset_id}.mp3",
                   retry_safe=False,
                   extra={"hint": f"Check {ambient_dir} for available presets.", "looked_in": str(ambient_dir)},
               )
    # Voice-source selection:
    # If a lipsync video exists, extract its audio track and use THAT as
    # the voice source — it is bit-exact what ByteDance animated against,
    # so the mixed output preserves perfect beak-sync timing. Running a
    # fresh silcomp here produces subtly different silence boundaries than
    # what was in the lipsync submission, which causes drift.
    # Fallback: use raw voice stem (used when lipsync hasn't run yet).
    # (Fix 2026-04-21 evening.)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    voice_extract_path = h.app.event_dir / f"_tmp_voice_extract_{phase}_{ts}.mp3"
    voice_for_mix_path = voice_stem_path  # default fallback
    cut_start, cut_end = _phase_voice_stem_cut_window(state, phase)
    lipsync_name_for_source = state.get(f"phase_{phase}_lipsync_file")
    lipsync_source_path: Path | None = None
    if lipsync_name_for_source:
        if "/" in lipsync_name_for_source or "\\" in lipsync_name_for_source or ".." in lipsync_name_for_source:
            lipsync_name_for_source = ""
        else:
            try:
                candidate = require_basename_under_dir(
                    lipsync_name_for_source, h.app.event_dir,
                )
            except ValueError:
                candidate = None
        if candidate is not None and candidate.is_file():
            lipsync_source_path = candidate
            try:
                ffmpeg_lipsync_in = require_media_under_project(
                    str(candidate), anchor=h.app.event_dir, extensions=MEDIA_EXTENSIONS,
                )
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", ffmpeg_lipsync_in,
                    "-vn", "-c:a", "libmp3lame", "-b:a", "192k",
                    "-ac", "1", "-ar", "44100",
                    "-f", "mp3",
                    str(voice_extract_path),
                ], check=True, capture_output=True, timeout=60)
                voice_for_mix_path = voice_extract_path
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                    OSError) as exc:
                # Non-fatal: fall back to voice stem + warn in logs.
                print(f"[mix_audio] extract-from-lipsync failed (falling back to voice_stem): {exc}")
                lipsync_source_path = None

    if lipsync_source_path is None and cut_end > cut_start + 0.001:
        try:
            tmp_trim = h.app.event_dir / f"_tmp_stem_trim_mix_{phase}_{ts}.mp3"
            voice_for_mix_path = _materialize_cut_out_audio(
                voice_stem_path, tmp_trim, cut_start, cut_end,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                OSError, ValueError) as exc:
            return h._send_error_v59(
                400,
                error_code="STEM_TRIM_FAILED",
                error_message=f"stem cut failed: {exc}",
                retry_safe=False,
                extra={
                    "cut_start_s": cut_start,
                    "cut_end_s": cut_end,
                    "hint": "Reduce front/back trim values so at least 0.25s of audio remains.",
                },
            )

    out_name = f"phase_{phase}_mixed_{ts}.mp3"
    out_path = h.app.event_dir / out_name
    tmp = out_path.with_suffix(f".mp3.tmp.{os.getpid()}")
    try:
        # Voice loud, ambient bed quiet and clipped to voice duration.
        # normalize=0 keeps the explicit volume multipliers intact — default
        # amix normalize=1 divides each input by N, silently halving voice
        # to 0.5 and bed to 0.075 (2026-04-21 fix).
        filter_complex = (
            "[0:a]volume=1.0[voice];"
            "[1:a]volume=0.15[bed];"
            "[voice][bed]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[mix]"
        )
        ffmpeg_voice_in = require_media_under_project(
            str(voice_for_mix_path), anchor=h.app.event_dir, extensions=MEDIA_EXTENSIONS,
        )
        ffmpeg_ambient_in = require_media_under_project(
            str(ambient_path), anchor=ambient_dir, extensions=MEDIA_EXTENSIONS,
        )
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", ffmpeg_voice_in,
            "-i", ffmpeg_ambient_in,
            "-filter_complex", filter_complex,
            "-map", "[mix]",
            "-c:a", "libmp3lame", "-b:a", "128k",
            "-ac", "1", "-ar", "44100",
            # Force mp3 format: tmp filename ends in .tmp.<PID> which ffmpeg
            # can't auto-detect as mp3 from the extension (2026-04-21 fix).
            "-f", "mp3",
            str(tmp),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        os.replace(tmp, out_path)
    except subprocess.CalledProcessError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        stderr = (exc.stderr or b"")[:400].decode("utf-8", errors="replace")
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"ffmpeg amix failed (returncode={exc.returncode})",
                   retry_safe=True,
                   extra={"stderr": stderr, "hint": "Check ambient preset format (expect mp3, 44.1kHz)."},
               )
    except (subprocess.TimeoutExpired, OSError) as exc:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"ffmpeg mix error: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"hint": "Try a shorter voice stem or different ambient preset."},
               )
    finally:
        # Cleanup tmp voice-extract file regardless of outcome.
        try:
            voice_extract_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    try:
        duration = _ffprobe_duration(out_path)
    except (subprocess.CalledProcessError, ValueError, OSError):
        duration = 0.0
    mtime = int(os.path.getmtime(str(out_path)))

    def _apply(state, _p=phase, _n=out_name, _m=mtime, _pid=ambient_preset_id):
        state[f"phase_{_p}_mixed_audio_file"] = _n
        state[f"phase_{_p}_mixed_audio_mtime"] = _m
        state[f"phase_{_p}_ambient_preset_id"] = _pid
        state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
        return state["_module_version"]
    try:
        new_version = h.app.state.mutate_state(_apply)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"mutate_state failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"hint": "State.json could not be persisted. File was written to disk."},
               )

    # Auto-remux: if a lipsync video exists for this phase, replace its
    # audio track with the newly mixed (voice + ambient bed) audio so the
    # "Preview Phase A/B Stitched" button reads the right thing. Added
    # 2026-04-21 after Kim hit the case where Phase A lipsync was baked
    # with voice-only audio (no bed) because the panel workflow is
    # lipsync-first, mix-later. ffmpeg -c:v copy keeps the video stream
    # bit-exact; only the audio track is replaced.
    remux_info = None
    state_after = h.app.state.read_state()
    lipsync_name = state_after.get(f"phase_{phase}_lipsync_file")
    if lipsync_name:
        if "/" not in lipsync_name and "\\" not in lipsync_name and ".." not in lipsync_name:
            try:
                lipsync_path = require_basename_under_dir(lipsync_name, h.app.event_dir)
            except ValueError:
                lipsync_path = None
        else:
            lipsync_path = None
        if lipsync_path is not None and lipsync_path.is_file():
            new_lipsync_name = f"phase_{phase}_lipsync_withbed_{ts}.mp4"
            new_lipsync_path = h.app.event_dir / new_lipsync_name
            try:
                ffmpeg_lipsync_in = require_media_under_project(
                    str(lipsync_path), anchor=h.app.event_dir, extensions=MEDIA_EXTENSIONS,
                )
                ffmpeg_mixed_in = require_media_under_project(
                    str(out_path), anchor=h.app.event_dir, extensions=MEDIA_EXTENSIONS,
                )
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", ffmpeg_lipsync_in,
                    "-i", ffmpeg_mixed_in,
                    "-c:v", "copy",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-shortest",
                    str(new_lipsync_path),
                ], check=True, capture_output=True, timeout=60)
                new_lipsync_mtime = int(os.path.getmtime(str(new_lipsync_path)))
                def _apply_lipsync(state, _p=phase, _n=new_lipsync_name, _m=new_lipsync_mtime):
                    state[f"phase_{_p}_lipsync_file"] = _n
                    state[f"phase_{_p}_lipsync_mtime"] = _m
                    state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
                    return state["_module_version"]
                new_version = h.app.state.mutate_state(_apply_lipsync)
                remux_info = {"lipsync_file": new_lipsync_name, "lipsync_mtime": new_lipsync_mtime}
            except subprocess.CalledProcessError as exc:
                # Non-fatal: the mix succeeded. Just log and move on.
                stderr = (exc.stderr or b"")[:200].decode("utf-8", errors="replace")
                print(f"[mix_audio] lipsync re-mux failed (non-fatal): rc={exc.returncode} stderr={stderr}")
            except (subprocess.TimeoutExpired, OSError) as exc:
                print(f"[mix_audio] lipsync re-mux failed (non-fatal): {type(exc).__name__}: {exc}")

    # Auto-assemble Phase A canonical: flyin + lipsync_withbed + flyout,
    # all normalized to LD-284 (H.264 High / yuv420p / 1280x720 / 24fps /
    # AAC 128k / +faststart) and concatenated via concat demuxer with
    # -c copy. Triggers only for phase=='a'. Phase B modules ship the
    # lipsync file directly (no fly-in/out wrapper). Added 2026-04-21.
    canonical_info = None
    if phase == "a" and remux_info is not None:
        try:
            canonical_info = h._auto_assemble_phase_a_stitched(ts)
        except Exception as exc:  # noqa: BLE001
            # Non-fatal: mix + remux succeeded; canonical is a nice-to-have.
            traceback.print_exc()
            canonical_info = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}

    return h._send_json(200, {
        "status": "ok",
        "phase": phase,
        "file": out_name,
        "mtime": mtime,
        "remux": remux_info,
        "canonical": canonical_info,
        "duration_s": round(duration, 3),
        "ambient_preset_id": ambient_preset_id,
        "module_version": new_version,
    })


def handle_phase_a_lipsync(h, body: dict) -> None:
    """POST /api/phase_a/lipsync — idle Kling lipsync for Chipper (birds).

    Kim 2026-06-08: storyboard idle pattern on body plate still + slow zoom.
    Phase B human lipsync stays on Kling Sync (handle_phase_b_lipsync).
    Locked policy: Production/docs/PHASE_A_CHIPPER_PIPELINE_LOCKED_v1.md
    """
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": "_handle_phase_a_lipsync",
    }

    if h.app.client is None:
        return h._send_error_v59(
            500,
            error_code="WAVESPEED_NOT_CONFIGURED",
            error_message="WaveSpeed client not configured (missing API key)",
            retry_safe=True,
            extra={"hint": "Populate API_KEYS_MASTER.md wavespeed entry."},
        )

    state = h.app.state.read_state()

    def _phase_a_lipsync_running_stale(st: dict) -> bool:
        if st.get("phase_a_lipsync_status") != "running":
            return False
        started = st.get("phase_a_lipsync_started_at")
        if not isinstance(started, (int, float)):
            return True  # legacy running with no timestamp — treat as stale
        return (time.time() - float(started)) > PHASE_A_LIPSYNC_STALE_SEC

    if state.get("phase_a_lipsync_status") == "running":
        if _phase_a_lipsync_running_stale(state):
            def _clear_stale_running(st):
                st["phase_a_lipsync_status"] = (
                    f"error: stale_timeout: running > {PHASE_A_LIPSYNC_STALE_SEC}s"
                )
                st.pop("phase_a_lipsync_started_at", None)
                nested = st.setdefault("phase_a", {})
                if isinstance(nested, dict):
                    nested["phase_a_lipsync_status"] = st["phase_a_lipsync_status"]
                    nested.pop("phase_a_lipsync_started_at", None)
                return st.get("_module_version", 0)
            h.app.state.mutate_state(_clear_stale_running)
            state = h.app.state.read_state()
        else:
            return h._send_error_v59(
                409,
                error_code="PHASE_A_LIPSYNC_RUNNING",
                error_message="Phase A lipsync already running",
                retry_safe=False,
                extra={"hint": f"Wait up to {PHASE_A_LIPSYNC_STALE_SEC // 60} min or refresh after stale auto-clear."},
            )

    base_clip_id = (
        (body or {}).get("base_clip_id")
        or state.get("phase_a_chipper_sitting_clip_id")
        or state.get("phase_a_empty_desk_bg_id")
    )

    audio_name = (
        state.get("phase_a_voice_stem_file")
        or (state.get("phase_a") or {}).get("phase_a_voice_stem_file")
        or state.get("phase_a_mixed_audio_file")
    )
    if not audio_name:
        return h._send_error_v59(
            400,
            error_code="GENERIC_ERROR",
            error_message="phase_a_voice_stem_file unset",
            retry_safe=False,
            extra={"hint": "Run Regen Audio first."},
        )
    audio_path = h.app.event_dir / audio_name
    if not audio_path.is_file():
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message=f"audio file not found: {audio_name}",
            retry_safe=False,
        )

    ts_pre = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        audio_for_lipsync, _ = _apply_phase_audio_trim(
            h, audio_path, "a", state, ts_pre,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            OSError, ValueError) as exc:
        return h._send_error_v59(
            400,
            error_code="STEM_TRIM_FAILED",
            error_message=f"stem trim failed: {exc}",
            retry_safe=False,
            extra={"hint": "Adjust stem trim front/back seconds on the waveform row."},
        )

    base_video_path: Path | None = None
    if base_clip_id:
        from phase_a_chipper_kling_lipsync import resolve_lipsync_base

        bases_dir = h._phase_assets_dir("lipsync_bases")
        try:
            base_video_path = resolve_lipsync_base(bases_dir, base_clip_id)
        except FileNotFoundError:
            base_video_path = None

    still_path: Path | None = None
    if base_video_path is None:
        from phase_a_chipper_idle_lipsync import resolve_body_plate

        try:
            still_path = resolve_body_plate(h.app.event_dir, state)
        except FileNotFoundError as exc:
            return h._send_error_v59(
                404,
                error_code="GENERIC_ERROR",
                error_message=str(exc),
                retry_safe=False,
                extra={"hint": "Add phase_a_chipper_body_plate_v1.png to the event folder."},
            )

    # Base-clip path: ByteDance LatentSync (preserves wing pixels). Idle-from-still: 2× Kling jobs.
    lipsync_jobs = 1 if base_video_path else 2
    lipsync_method = "base_clip_bytedance_tight_v1" if base_video_path else "idle_kling_lipsync"
    spend = h.app.state.read_spend()
    if spend["budget_remaining"] < COST_PER_LIPSYNC * lipsync_jobs:
        return h._send_error_v59(
            402,
            error_code="BUDGET_EXCEEDED_FOR_LIP_SYNC",
            error_message="budget exceeded for lip sync",
            retry_safe=False,
            extra={
                "budget_remaining": spend["budget_remaining"],
                "cost": COST_PER_LIPSYNC * lipsync_jobs,
            },
        )

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_name = f"phase_a_lipsync_{ts}.mp4"
    out_path = h.app.event_dir / out_name

    def _apply_running(st):
        st["phase_a_lipsync_status"] = "running"
        st["phase_a_lipsync_started_at"] = time.time()
        st.pop("phase_a_lipsync_task_id", None)
        nested = st.setdefault("phase_a", {})
        if isinstance(nested, dict):
            nested["phase_a_lipsync_status"] = "running"
            nested["phase_a_lipsync_started_at"] = st["phase_a_lipsync_started_at"]
        st["_module_version"] = int(st.get("_module_version", 0) or 0) + 1
        return st["_module_version"]

    h.app.state.mutate_state(_apply_running)

    _app = h.app
    _pin_captured = dict(_pin)
    _stitch = h._auto_assemble_phase_a_stitched
    _still_path = still_path
    _base_clip_id = base_clip_id
    _base_video_path = base_video_path
    _lipsync_jobs = lipsync_jobs
    _lipsync_method = lipsync_method

    def _bg(
        _out_path=out_path,
        _out_name=out_name,
        _audio_path=audio_for_lipsync,
        _still=_still_path,
        _base_clip_id=_base_clip_id,
        _base_video=_base_video_path,
        _jobs=_lipsync_jobs,
        _method=_lipsync_method,
    ):
        try:
            if _base_video is not None:
                from phase_a_middle_permanent import run_phase_a_base_clip_bytedance_lipsync

                tmp_dir = _app.event_dir / "_tmp_phase_a_permanent"
                run_phase_a_base_clip_bytedance_lipsync(
                    _base_video, _audio_path, _out_path, tmp_dir=tmp_dir,
                )
            else:
                from phase_a_chipper_idle_lipsync import run_phase_a_chipper_idle_lipsync

                tmp_dir = _app.event_dir / "_tmp_phase_a_idle_lipsync"
                run_phase_a_chipper_idle_lipsync(
                    _still, _audio_path, _out_path, tmp_dir=tmp_dir, apply_zoom=False,
                )
            if not _out_path.is_file():
                raise RuntimeError(f"lipsync finished but output missing: {_out_path}")

            from phase_a_av_post import av_duration_gap
            from phase_a_middle_permanent import extract_qa_frames

            video_s, audio_s, av_gap_s = av_duration_gap(_out_path)
            if av_gap_s > 0.10:
                raise RuntimeError(
                    f"Phase A media gate failed: A/V gap {av_gap_s:.3f}s "
                    f"(video={video_s:.3f}s audio={audio_s:.3f}s)"
                )
            qa_dir = _app.event_dir / f"phase_a_lipsync_qa_{Path(_out_name).stem}"
            extract_qa_frames(_out_path, qa_dir)

            _cur_gen = getattr(_app, "event_generation", None)
            _pin_gen = _pin_captured.get("pinned_generation")
            _cur_dir = getattr(_app, "event_dir", None)
            _pin_dir = _pin_captured.get("pinned_event_dir")
            if (_pin_gen is not None and _cur_gen != _pin_gen) or \
               (_pin_dir is not None and _cur_dir != _pin_dir):
                print(
                    f"[phase_a_lipsync] pin mismatch — output at {_out_path} "
                    f"but state NOT mutated",
                    flush=True,
                )

                def _apply_pin_mismatch(st):
                    st["phase_a_lipsync_status"] = "error: pin_mismatch: event scope changed mid-job"
                    st.pop("phase_a_lipsync_started_at", None)
                    nested = st.setdefault("phase_a", {})
                    if isinstance(nested, dict):
                        nested["phase_a_lipsync_status"] = st["phase_a_lipsync_status"]
                        nested.pop("phase_a_lipsync_started_at", None)
                    return st.get("_module_version", 0)

                try:
                    _app.state.mutate_state(_apply_pin_mismatch)
                except Exception:  # noqa: BLE001
                    pass
                return

            _app.state.add_spend("lipsync", COST_PER_LIPSYNC * _jobs)
            mtime = int(os.path.getmtime(str(_out_path)))

            def _apply_done(st,
                           _n=_out_name, _m=mtime, _bid=_base_clip_id, _meth=_method,
                           _qa=str(qa_dir), _gap=av_gap_s):
                for key, val in (
                    ("phase_a_lipsync_file", _n),
                    ("phase_a_lipsync_mtime", _m),
                    ("phase_a_lipsync_status", "needs_manual_visual_review"),
                    ("phase_a_lipsync_method", _meth),
                    ("phase_a_lipsync_qa_dir", _qa),
                    ("phase_a_lipsync_av_gap_s", round(_gap, 3)),
                ):
                    st[key] = val
                    nested = st.setdefault("phase_a", {})
                    if isinstance(nested, dict):
                        nested[key] = val
                st["phase_a_lipsync_requires_regen"] = False
                st.pop("phase_a_lipsync_reliability_note", None)
                nested = st.setdefault("phase_a", {})
                if isinstance(nested, dict):
                    nested["phase_a_lipsync_requires_regen"] = False
                    nested.pop("phase_a_lipsync_reliability_note", None)
                if _bid:
                    st["phase_a_chipper_sitting_clip_id"] = _bid
                    nested = st.setdefault("phase_a", {})
                    if isinstance(nested, dict):
                        nested["phase_a_chipper_sitting_clip_id"] = _bid
                st.pop("phase_a_lipsync_task_id", None)
                st.pop("phase_a_lipsync_started_at", None)
                nested = st.setdefault("phase_a", {})
                if isinstance(nested, dict):
                    nested.pop("phase_a_lipsync_started_at", None)
                st["_module_version"] = int(st.get("_module_version", 0) or 0) + 1
                return st["_module_version"]

            _app.state.mutate_state(_apply_done)
            print(
                f"[phase_a_lipsync] media gate passed; visual review required → {_out_name} "
                f"({_out_path.stat().st_size} bytes, av_gap={av_gap_s:.3f}s, qa={qa_dir})",
                flush=True,
            )
            print("[phase_a_lipsync] auto-stitch skipped until visual gates pass", flush=True)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()

            def _apply_err(st, _e=exc):
                st["phase_a_lipsync_status"] = (
                    f"error: {type(_e).__name__}: {str(_e)[:100]}"
                )
                st.pop("phase_a_lipsync_task_id", None)
                st.pop("phase_a_lipsync_started_at", None)
                nested = st.setdefault("phase_a", {})
                if isinstance(nested, dict):
                    nested["phase_a_lipsync_status"] = st["phase_a_lipsync_status"]
                    nested.pop("phase_a_lipsync_started_at", None)
                return st.get("_module_version", 0)

            try:
                _app.state.mutate_state(_apply_err)
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=_bg, daemon=True).start()
    return h._send_json(202, {
        "ok": True,
        "status": "running",
        "phase": "a",
        "vendor": lipsync_method,
        "still": still_path.name if still_path else None,
        "base_clip_id": base_clip_id,
        "base_clip_file": base_video_path.name if base_video_path else None,
        "message": (
            "ByteDance Phase A lipsync is processing. "
            "Phase A will stop for visual review after media gates pass."
        ),
    })


def handle_phase_b_lipsync(h, body: dict)-> None:

    """POST /api/phase_b/lipsync

    Body: {"phase": "a"|"b", "base_clip_id": "placeholder_cedric_base_v1"}

    Module-level lipsync (no beat). Loads base clip from
    Production/assets/lipsync_bases/<base_clip_id> (auto .mp4 / .mov),
    mixed audio from state phase_{phase}_mixed_audio_file (fallback to
    voice_stem). Applies silcomp, loops or trims base clip to audio
    duration, submits to Kling Sync via LipSyncClient.submit_and_wait
    (synchronous). Route: wavespeed.ai/kwaivgi/kling-lipsync.

    Writes phase_{phase}_lipsync_<TS>.mp4 and patches state.
    """
    # LD-456 SCOPE_VALIDATION_V1 + LD-461 SCOPE_BODY_HELPER_V1
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    # LD-460 ASYNC_JOB_GENERATION_PIN_V1 — capture pin at entry; terminal writes assert via _check_event_pin.
    _pin = {
        "pinned_generation": h.app.event_generation,
        "pinned_event_dir": h.app.event_dir,
        "pinned_video_role": (body or {}).get("scope_video_role", "intro"),
        "_handler": '_handle_phase_b_lipsync',
    }

    if h.app.client is None:
        return h._send_error_v59(
                   500,
                   error_code="WAVESPEED_NOT_CONFIGURED",
                   error_message="WaveSpeed client not configured (missing API key)",
                   retry_safe=True,
                   extra={"hint": "Populate API_KEYS_MASTER.md wavespeed entry."},
               )
    phase = (body.get("phase") or "").strip().lower()
    if phase == "a":
        return handle_phase_a_lipsync(h, body)
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
                   extra={"hint": "phase is 'a' or 'b'."},
               )
    base_clip_id = body.get("base_clip_id")
    if not base_clip_id or not isinstance(base_clip_id, str):
        return h._send_error_v59(
                   400,
                   error_code="BASE_CLIP_ID_IS_REQUIRED",
                   error_message="base_clip_id is required (string)",
                   retry_safe=False,
                   extra={"hint": "Pick from the base-clip dropdown."},
               )
    # Resolve audio source: prefer mixed_audio_file, fallback to voice_stem.
    state = h.app.state.read_state()
    existing_status = state.get(f"phase_{phase}_lipsync_status")
    existing_tid = state.get(f"phase_{phase}_lipsync_task_id")
    if existing_status == "polling" and existing_tid:
        return h._send_json(202, {
            "ok": True,
            "status": "already_polling",
            "task_id": existing_tid,
            "phase": phase,
            "message": "Lipsync already in progress — auto-updating when done.",
        })
    audio_name = (state.get(f"phase_{phase}_mixed_audio_file")
                  or state.get(f"phase_{phase}_voice_stem_file"))
    if not audio_name:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=f"phase_{phase}_mixed_audio_file and phase_{phase}_voice_stem_file both unset",
                   retry_safe=False,
                   extra={"hint": "Run Regen Audio (and optionally Mix Audio) first."},
               )
    audio_path = h.app.event_dir / audio_name
    if not audio_path.is_file():
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"audio file not found: {audio_name}",
                   retry_safe=False,
                   extra={"hint": "File may have been deleted. Re-run Regen Audio."},
               )
    # Resolve base clip — auto-detect .mp4 or .mov. Accept raw key if it
    # already includes an extension.
    bases_dir = h._phase_assets_dir("lipsync_bases")
    base_path: Path | None = None
    raw = bases_dir / base_clip_id
    if raw.is_file():
        base_path = raw
    else:
        for ext in ("mp4", "mov"):
            candidate = bases_dir / f"{base_clip_id}.{ext}"
            if candidate.is_file():
                base_path = candidate
                break
    if base_path is None:
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=f"base clip not found: {base_clip_id}",
                   retry_safe=False,
                   extra={"hint": f"Expected {bases_dir}/{base_clip_id}.mp4 or .mov", "looked_in": str(bases_dir)},
               )

    # Budget check.
    spend = h.app.state.read_spend()
    if spend["budget_remaining"] < COST_PER_LIPSYNC:
        return h._send_error_v59(
                   402,
                   error_code="BUDGET_EXCEEDED_FOR_LIP_SYNC",
                   error_message="budget exceeded for lip sync",
                   retry_safe=False,
                   extra={"budget_remaining": spend["budget_remaining"], "cost": COST_PER_LIPSYNC, "hint": "Raise budget via /api/budget/override or ship fewer."},
               )

    # Kling Sync handles the full audio including meditation silences — do NOT
    # apply silcomp (§8.4 silence compression was designed for ByteDance's 10s
    # cap; SWITCH_TO_KLING_LIPSYNC_20260524 eliminated that vendor).
    _VIDEO_TAILROOM_S = 2.0  # Kim: "1.5–2s tail so cut-off after speaking isn't sudden"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        audio_for_lipsync, audio_duration = _apply_phase_audio_trim(
            h, audio_path, phase, state, ts,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            OSError, ValueError) as exc:
        return h._send_error_v59(
            400,
            error_code="STEM_TRIM_FAILED",
            error_message=f"stem trim failed: {exc}",
            retry_safe=False,
            extra={"hint": "Adjust stem trim front/back seconds before Send for Lipsync."},
        )
    tmp_audio_path = h.app.event_dir / f"_tmp_silcomp_phase_{phase}_{ts}.mp3"
    tmp_video_path = h.app.state.clips_dir / f"_tmp_trim_phase_{phase}_{ts}.mp4"
    try:
        raw_dur = _ffprobe_duration(base_path)
        target_video_s = audio_duration + _VIDEO_TAILROOM_S
        # WaveSpeed enforces a 30MB cap on the base64-encoded 'video' field.
        # base64 adds ~33% overhead, so raw files > ~22MB will exceed the cap.
        # Re-encode oversized clips at 2 Mbps H.264 (sufficient quality for
        # lipsync input — Kling generates fresh output anyway).
        _WAVESPEED_RAW_MB_CEILING = 22.0
        raw_size_mb = base_path.stat().st_size / 1024 / 1024

        if raw_dur < target_video_s:
            # Base clip is shorter than audio — Kling loops internally.
            # DO NOT pre-loop: looping a 28MB clip to 76s → 165MB, instant reject.
            if raw_size_mb > _WAVESPEED_RAW_MB_CEILING:
                # File too large for data URI submission — re-encode at 2 Mbps.
                print(
                    f"[phase_b_lipsync] base clip {raw_size_mb:.1f}MB > "
                    f"{_WAVESPEED_RAW_MB_CEILING}MB ceiling — re-encoding at 2Mbps for API",
                    flush=True,
                )
                subprocess.run(
                    [
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(base_path),
                        "-c:v", "libx264", "-preset", "fast",
                        "-b:v", "2000k", "-maxrate", "2000k", "-bufsize", "4000k",
                        "-an",
                        "-movflags", "+faststart",
                        str(tmp_video_path),
                    ],
                    check=True, capture_output=True, timeout=120,
                )
                reenc_mb = tmp_video_path.stat().st_size / 1024 / 1024
                print(f"[phase_b_lipsync] re-encoded: {reenc_mb:.1f}MB → base64 ~{reenc_mb*1.34:.1f}MB", flush=True)
                video_for_lipsync = tmp_video_path
            else:
                print(
                    f"[phase_b_lipsync] base clip {raw_dur:.2f}s < audio {audio_duration:.2f}s, "
                    f"{raw_size_mb:.1f}MB — sending raw; Kling loops internally",
                    flush=True,
                )
                video_for_lipsync = base_path
        else:
            # Base clip is longer than audio — trim to avoid sending excess data.
            video_for_lipsync, _, _, _ = _trim_video_to_audio(
                base_path, tmp_video_path, audio_duration,
                trim_start=0.0, trim_end=None,
            )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            OSError, ValueError) as exc:
        traceback.print_exc()
        return h._send_error_v59(
                   500,
                   error_code="LIPSYNC_PRE_CONDITIONING_FAILED",
                   error_message="lipsync pre-conditioning failed",
                   retry_safe=True,
                   extra={"stage": "silcomp_or_trim", "detail": str(exc)[:400], "hint": "Check ffmpeg + that base clip is decodable."},
               )

    # Submit to Kling Sync (POST only — returns task_id in a few seconds).
    # Poll + download run in a background thread so the HTTP response returns
    # immediately (HTTP 202). Phase B meditations are 90-150s; Kling takes
    # 2-10 minutes to process — a synchronous submit_and_wait would always
    # time out in the browser ("Failed to fetch" / HTTP 0).
    import threading as _threading

    out_name = f"phase_{phase}_lipsync_{ts}.mp4"
    out_path = h.app.event_dir / out_name
    lipsync_client = LipSyncClient(h.app.client.api_key)
    try:
        task_id = lipsync_client.submit(video_for_lipsync, audio_for_lipsync)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        for tmp in (tmp_audio_path, tmp_video_path):
            try:
                tmp.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
        return h._send_error_v59(
                   502,
                   error_code="GENERIC_ERROR",
                   error_message=f"Kling LipSync submit failed: {type(exc).__name__}: {exc}",
                   retry_safe=True,
                   extra={"hint": f"{str(exc)[:200]} — check server stderr. "
                "Likely: WaveSpeed API key, DNS, or oversized payload."},
               )

    # Mark state as polling so UI can reflect in-progress status.
    def _apply_polling(state, _p=phase, _tid=task_id, _bid=base_clip_id):
        state[f"phase_{_p}_lipsync_status"] = "polling"
        state[f"phase_{_p}_lipsync_task_id"] = _tid
        if _p == "b" and _bid:
            state["phase_b_cedric_base_clip_id"] = _bid
        state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
        return state["_module_version"]
    try:
        h.app.state.mutate_state(_apply_polling)
    except Exception:  # noqa: BLE001
        pass  # non-fatal — polling state is cosmetic

    # Background thread: poll Kling → download → write final state.
    # Captures everything it needs from the enclosing scope; does NOT use h
    # after the HTTP response is sent (h.wfile may be closed).
    _app = h.app
    _pin_captured = dict(_pin)

    def _bg_poll_and_write(
        _task_id=task_id,
        _out_path=out_path,
        _out_name=out_name,
        _phase=phase,
        _base_clip_id=base_clip_id,
        _audio_dur=audio_duration,
        _tmp_audio=tmp_audio_path,
        _tmp_video=tmp_video_path,
    ):
        try:
            result = lipsync_client.poll_until_done(_task_id)
            status = (result.get("status") or "").lower()
            if status == "completed" and result.get("outputs"):
                url = result["outputs"][0]
                lipsync_client.download(url, _out_path)
                if not _out_path.is_file():
                    raise RuntimeError(
                        f"Kling reported completed but output not on disk: {_out_path}"
                    )
                # Standardized white-out transition at end of Phase B lipsync.
                # Applied to EVERY lipsync output before state is written.
                try:
                    _apply_whiteout_fade(_out_path)
                except Exception as _fade_exc:  # noqa: BLE001
                    print(
                        f"[phase_b_whiteout] WARNING: fade failed ({_fade_exc!r}) "
                        f"— keeping raw download, proceeding without fade",
                        flush=True,
                    )
                _app.state.add_spend("lipsync", COST_PER_LIPSYNC)
                mtime = int(os.path.getmtime(str(_out_path)))

                # LD-460 pin check before terminal state write — inline
                # (can't call h._check_event_pin from bg thread; h is the
                # HTTP handler whose socket may be closed).
                _cur_gen = getattr(_app, "event_generation", None)
                _pin_gen = _pin_captured.get("pinned_generation")
                _cur_dir = getattr(_app, "event_dir", None)
                _pin_dir = _pin_captured.get("pinned_event_dir")
                if (_pin_gen is not None and _cur_gen != _pin_gen) or \
                   (_pin_dir is not None and _cur_dir != _pin_dir):
                    print(
                        f"[phase_b_lipsync] pin mismatch after poll — "
                        f"output on disk at {_out_path} but state NOT mutated "
                        f"(event changed mid-job)",
                        flush=True,
                    )
                    return

                def _apply(state,
                           _p=_phase, _n=_out_name, _m=mtime,
                           _bid=_base_clip_id):
                    state[f"phase_{_p}_lipsync_file"] = _n
                    state[f"phase_{_p}_lipsync_mtime"] = _m
                    state[f"phase_{_p}_lipsync_status"] = "done"
                    state[f"phase_{_p}_lipsync_requires_regen"] = False
                    state.pop(f"phase_{_p}_lipsync_task_id", None)
                    state[f"phase_{_p}_cedric_base_clip_id" if _p == "b"
                          else f"phase_{_p}_empty_desk_bg_id"] = _bid
                    state["_module_version"] = (
                        int(state.get("_module_version", 0) or 0) + 1
                    )
                    return state["_module_version"]
                _app.state.mutate_state(_apply)
                print(
                    f"[phase_b_lipsync] ✓ complete → {_out_name} "
                    f"({_out_path.stat().st_size} bytes)",
                    flush=True,
                )
            else:
                err = result.get("raw", {}).get("error", "unknown")
                def _apply_err(state, _p=_phase, _e=err):
                    state[f"phase_{_p}_lipsync_status"] = f"error: {str(_e)[:120]}"
                    state.pop(f"phase_{_p}_lipsync_task_id", None)
                    return state
                _app.state.mutate_state(_apply_err)
                print(
                    f"[phase_b_lipsync] ✗ Kling returned status={status!r} "
                    f"error={err}",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            def _apply_exc(state, _p=_phase, _exc=exc):
                state[f"phase_{_p}_lipsync_status"] = (
                    f"error: {type(_exc).__name__}: {str(_exc)[:100]}"
                )
                state.pop(f"phase_{_p}_lipsync_task_id", None)
                return state
            try:
                _app.state.mutate_state(_apply_exc)
            except Exception:  # noqa: BLE001
                pass
        finally:
            for tmp in (_tmp_audio, _tmp_video):
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass

    t = _threading.Thread(target=_bg_poll_and_write, daemon=True)
    t.start()
    print(
        f"[phase_b_lipsync] submitted task_id={task_id} — "
        f"polling in background thread {t.name}",
        flush=True,
    )

    return h._send_json(202, {
        "ok": True,
        "status": "submitted",
        "task_id": task_id,
        "phase": phase,
        "audio_duration_s": round(audio_duration, 3),
        "base_clip_id": base_clip_id,
        "message": (
            "Kling Sync is processing (~8-20 min). "
            "The storyboard will auto-update when done."
        ),
    })


def _write_phase_b_lipsync_complete(
    app,
    *,
    phase: str,
    out_path: Path,
    out_name: str,
    base_clip_id: str | None,
) -> None:
    """Terminal success write shared by bg thread + persistent poller."""
    try:
        _apply_whiteout_fade(out_path)
    except Exception as fade_exc:  # noqa: BLE001
        print(
            f"[phase_{phase}_lipsync] WARNING: fade failed ({fade_exc!r}) "
            f"— keeping raw download",
            flush=True,
        )
    app.state.add_spend("lipsync", COST_PER_LIPSYNC)
    mtime = int(os.path.getmtime(str(out_path)))

    def _apply(state, _p=phase, _n=out_name, _m=mtime, _bid=base_clip_id):
        state[f"phase_{_p}_lipsync_file"] = _n
        state[f"phase_{_p}_lipsync_mtime"] = _m
        state[f"phase_{_p}_lipsync_status"] = "done"
        state[f"phase_{_p}_lipsync_requires_regen"] = False
        state.pop(f"phase_{_p}_lipsync_task_id", None)
        if _bid:
            key = f"phase_{_p}_cedric_base_clip_id" if _p == "b" else f"phase_{_p}_empty_desk_bg_id"
            state[key] = _bid
        state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
        return state["_module_version"]

    app.state.mutate_state(_apply)


def sweep_phase_module_lipsync_polls(state, client) -> None:
    """Poll in-flight phase B module lipsync jobs — survives server restarts.

    Beat-level lipsync uses LipsyncPollingThread in production_server.py;
    phase B module lipsync previously used a one-shot daemon thread that died
    on deploy/restart while state stayed ``polling``.
    """
    snap = state.read_state()
    phase = "b"
    status = snap.get(f"phase_{phase}_lipsync_status")
    task_id = snap.get(f"phase_{phase}_lipsync_task_id")
    if status != "polling" or not task_id:
        return
    try:
        result = client.poll(task_id)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[phase_{phase}_lipsync-poller] {task_id[:12]}… transport error "
            f"({type(exc).__name__}: {exc!r}); will retry",
            flush=True,
        )
        return
    poll_status = (result.get("status") or "").lower()
    outputs = result.get("outputs") or []
    print(
        f"[phase_{phase}_lipsync-poller] {task_id[:12]}… status={poll_status!r} "
        f"outputs={len(outputs)}",
        flush=True,
    )
    if poll_status == "completed" and outputs:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_name = f"phase_{phase}_lipsync_{ts}.mp4"
        out_path = state.event_dir / out_name
        base_clip_id = snap.get(f"phase_{phase}_cedric_base_clip_id")
        try:
            LipSyncClient(client.api_key).download(outputs[0], out_path)
        except Exception as exc:  # noqa: BLE001
            print(
                f"[phase_{phase}_lipsync-poller] download failed ({exc}); will retry",
                flush=True,
            )
            return
        if not out_path.is_file():
            print(
                f"[phase_{phase}_lipsync-poller] completed but file missing: {out_path}",
                flush=True,
            )
            return
        # Reconstruct minimal app shim for shared writer (add_spend + mutate_state).
        class _AppShim:
            pass

        shim = _AppShim()
        shim.state = state
        _write_phase_b_lipsync_complete(
            shim,
            phase=phase,
            out_path=out_path,
            out_name=out_name,
            base_clip_id=base_clip_id,
        )
        print(
            f"[phase_{phase}_lipsync-poller] ✓ recovered → {out_name} "
            f"({out_path.stat().st_size} bytes)",
            flush=True,
        )
    elif poll_status in ("failed", "error"):
        err = result.get("raw", {}).get("error", "unknown")

        def _apply_err(st, _p=phase, _e=err):
            st[f"phase_{_p}_lipsync_status"] = f"error: {str(_e)[:120]}"
            st.pop(f"phase_{_p}_lipsync_task_id", None)
            return st

        state.mutate_state(_apply_err)


def _phase_load_overlay_helpers():
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "credentials_lib"))
        from ffmpeg_stitch import (  # type: ignore
            render_watercolor_overlay,
            resolve_watercolor_asset,
            WATERCOLOR_OVERLAY_RECIPE_HASH,
            PREVIEW_OVERLAY_ENCODER_ARGS,
            lru_cleanup,
        )
    except ImportError as exc:
        raise RuntimeError(f"lib/ffmpeg_stitch import failed: {exc}") from exc
    return (
        render_watercolor_overlay,
        resolve_watercolor_asset,
        WATERCOLOR_OVERLAY_RECIPE_HASH,
        PREVIEW_OVERLAY_ENCODER_ARGS,
        lru_cleanup,
    )


def _phase_ensure_overlay_mp4(h, phase: str) -> tuple[Path, str]:
    """Return cached or freshly rendered phase preview MP4 with overlays baked in."""
    (
        render_watercolor_overlay,
        resolve_watercolor_asset,
        WATERCOLOR_OVERLAY_RECIPE_HASH,
        PREVIEW_OVERLAY_ENCODER_ARGS,
        lru_cleanup,
    ) = _phase_load_overlay_helpers()

    err = h._phase_check(phase)
    if err:
        raise ValueError(err)

    state = h.app.state.read_state()
    lipsync_name = state.get(f"phase_{phase}_lipsync_file")
    if not lipsync_name:
        raise ValueError(f"phase_{phase}_lipsync_file not set in state")
    if "/" in lipsync_name or "\\" in lipsync_name or ".." in lipsync_name:
        raise ValueError("invalid phase lipsync filename in state")

    lipsync_path = require_basename_under_dir(lipsync_name, h.app.event_dir)
    if not lipsync_path.is_file():
        raise FileNotFoundError(f"lipsync file not found on disk: {lipsync_name}")
    lipsync_path = lipsync_path.resolve()

    cues_json = state.get(f"phase_{phase}_watercolor_cues_json") or "[]"
    try:
        cues = json.loads(cues_json)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"phase_{phase}_watercolor_cues_json invalid: {exc}") from exc
    if not isinstance(cues, list):
        raise ValueError(f"phase_{phase}_watercolor_cues_json is not a list")

    library_dir = h._phase_assets_dir("watercolor_library")
    missing_assets = []
    for i, cue in enumerate(cues):
        try:
            resolve_watercolor_asset(
                library_dir, cue.get("key") or "", cue.get("cue_type") or "png",
            )
        except FileNotFoundError as exc:
            missing_assets.append({"cue_index": i, "error": str(exc)})
    if missing_assets:
        raise FileNotFoundError(f"watercolor assets missing: {missing_assets}")

    frame_x = h._PHASE_FRAME_X[phase]
    frame_y = h._PHASE_FRAME_Y
    frame_max_w = h._PHASE_FRAME_MAX_W[phase]
    frame_max_h = h._PHASE_FRAME_MAX_H[phase]

    lipsync_mtime = os.path.getmtime(str(lipsync_path))
    normalized_cues_json = _v2_validate_watercolor_cues_json(cues_json)
    hash_parts = [
        "recipe:v3",
        f"wc_overlay:{WATERCOLOR_OVERLAY_RECIPE_HASH}",
        f"phase:{phase}",
        f"frame_x:{frame_x}",
        f"frame_y:{frame_y}",
        f"frame_max_w:{frame_max_w}",
        f"frame_max_h:{frame_max_h}",
        f"lipsync:{lipsync_name}:{lipsync_mtime:.6f}",
        f"voice_stem_mtime:{state.get(f'phase_{phase}_voice_stem_mtime', 0)}",
        f"ambient:{state.get(f'phase_{phase}_ambient_preset_id', '')}",
        f"mixed_mtime:{state.get(f'phase_{phase}_mixed_audio_mtime', 0)}",
        f"base_clip:{state.get('phase_b_cedric_base_clip_id' if phase == 'b' else 'phase_a_empty_desk_bg_id', '')}",
        f"cues:{hashlib.sha256(normalized_cues_json.encode('utf-8')).hexdigest()[:16]}",
    ]
    cache_hash = hashlib.sha256(";".join(hash_parts).encode("utf-8")).hexdigest()

    preview_dir = h.app.event_dir / "preview" / f"phase_{phase}"
    preview_dir.mkdir(parents=True, exist_ok=True)
    final_path = preview_dir / f"phase_{phase}_preview_{cache_hash}.mp4"
    lock_path = preview_dir / ".lock"

    import fcntl  # noqa: PLC0415
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            raise RuntimeError("another phase preview is generating") from exc

        if final_path.is_file():
            lru_cleanup(preview_dir)
            return final_path, cache_hash

        render_watercolor_overlay(
            base_video_path=lipsync_path,
            cues=cues,
            frame_x=frame_x,
            frame_y=frame_y,
            output_path=final_path,
            library_dir=library_dir,
            chromakey_for_video=True,
            frame_max_w=frame_max_w,
            frame_max_h=frame_max_h,
            encoder_args=PREVIEW_OVERLAY_ENCODER_ARGS,
        )
        lru_cleanup(preview_dir)
        return final_path, cache_hash
    finally:
        try:
            fcntl.lockf(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(lock_fd)
        except OSError:
            pass


def handle_phase_export_stitcher(h, body: dict) -> None:
    """POST /api/phase/export_stitcher — bake overlays (Phase B) and upsert stitch slot."""
    from server_handlers.stitch_editor import stitch_upsert_event_slot

    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    phase = (body.get("phase") or "").strip().lower()
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
            400,
            error_code="GENERIC_ERROR",
            error_message=err,
            retry_safe=False,
            extra={"hint": "phase is 'a' or 'b'."},
        )

    event_id = h.app.event_dir.name
    slot_key = f"phase_{phase}"
    state = h.app.state.read_state()
    overlay_baked = False

    if phase == "b":
        try:
            final_path, _cache_hash = _phase_ensure_overlay_mp4(h, phase)
        except ValueError as exc:
            return h._send_error_v59(
                400, error_code="GENERIC_ERROR", error_message=str(exc), retry_safe=False,
            )
        except FileNotFoundError as exc:
            return h._send_error_v59(
                404, error_code="GENERIC_ERROR", error_message=str(exc), retry_safe=False,
            )
        except RuntimeError as exc:
            return h._send_error_v59(
                409, error_code="ANOTHER_PHASE_PREVIEW_IS_GENERATING",
                error_message=str(exc), retry_safe=False,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"")[:600].decode("utf-8", errors="replace")
            return h._send_error_v59(
                500, error_code="GENERIC_ERROR",
                error_message=f"ffmpeg overlay failed (returncode={exc.returncode})",
                retry_safe=True, extra={"stderr": stderr},
            )
        root = h._stitch_project_root()
        video_rel = str(final_path.resolve().relative_to(root))
        overlay_baked = True
    else:
        stitched_name = state.get("phase_a_stitched_file")
        if not stitched_name:
            return h._send_error_v59(
                400,
                error_code="GENERIC_ERROR",
                error_message="phase_a_stitched_file not set in state",
                retry_safe=False,
                extra={"hint": "Run Mix Audio (auto-stitch) first."},
            )
        if "/" in stitched_name or "\\" in stitched_name or ".." in stitched_name:
            return h._send_error_v59(
                400,
                error_code="INVALID_PHASE_STITCHED_FILENAME",
                error_message="invalid phase_a_stitched filename in state",
                retry_safe=False,
            )
        video_rel = f"Production/{event_id}/{stitched_name}"

    try:
        h._stitch_resolve_path(video_rel)
    except ValueError:
        return h._send_error_v59(
            403,
            error_code="VIDEO_PATH_OUTSIDE_PROJECT_ROOT",
            error_message="export video path outside project root",
            retry_safe=False,
        )

    job_name = stitch_upsert_event_slot(
        h,
        event_id,
        slot_key,
        {
            "video_path": video_rel,
            "overlay_baked": overlay_baked,
            "source": f"phase_{phase}_export",
        },
    )
    return h._send_json(200, {
        "ok": True,
        "job_name": job_name,
        "slot_key": slot_key,
        "video_path": video_rel,
        "overlay_baked": overlay_baked,
    })


def handle_phase_b_preview(h, body: dict)-> None:

    """POST /api/phase_b/preview — stream cached or freshly rendered overlay MP4."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    phase = (body.get("phase") or "").strip().lower()
    err = h._phase_check(phase)
    if err:
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=err,
                   retry_safe=False,
                   extra={"hint": "phase is 'a' or 'b'."},
               )

    try:
        final_path, cache_hash = _phase_ensure_overlay_mp4(h, phase)
    except RuntimeError as exc:
        if "import failed" in str(exc):
            return h._send_error_v59(
                       500,
                       error_code="GENERIC_ERROR",
                       error_message=str(exc),
                       retry_safe=True,
                       extra={"hint": "Verify Production/tools/lib/ffmpeg_stitch.py has render_watercolor_overlay."},
                   )
        return h._send_error_v59(
                   409,
                   error_code="ANOTHER_PHASE_PREVIEW_IS_GENERATING",
                   error_message="another phase preview is generating",
                   retry_safe=False,
                   extra={"hint": "Wait for the in-flight preview to finish."},
               )
    except ValueError as exc:
        msg = str(exc)
        extra: dict = {}
        if "lipsync_file not set" in msg:
            extra["hint"] = "Send for Lipsync first, then retry Preview."
        return h._send_error_v59(
                   400,
                   error_code="GENERIC_ERROR",
                   error_message=msg,
                   retry_safe=False,
                   extra=extra or None,
               )
    except FileNotFoundError as exc:
        msg = str(exc)
        if "watercolor assets missing" in msg:
            return h._send_error_v59(
                       400,
                       error_code="WATERCOLOR_ASSETS_MISSING_FOR_CUE",
                       error_message="watercolor assets missing for cue(s)",
                       retry_safe=False,
                       extra={"hint": msg},
                   )
        return h._send_error_v59(
                   404,
                   error_code="GENERIC_ERROR",
                   error_message=msg,
                   retry_safe=False,
               )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"")[:600].decode("utf-8", errors="replace")
        return h._send_error_v59(
                   500,
                   error_code="GENERIC_ERROR",
                   error_message=f"ffmpeg overlay failed (returncode={exc.returncode})",
                   retry_safe=True,
                   extra={"stderr": stderr, "hint": "Check stderr; common cause is missing cue asset or corrupt lipsync."},
               )

    try:
        _, _, _, _, lru_cleanup = _phase_load_overlay_helpers()
        evicted = lru_cleanup(final_path.parent)
    except Exception:
        evicted = []
    return h._stream_preview_mp4(final_path, cache_hash, evicted=evicted)


def handle_phase_a_regen_flyin_flyout(h, body: dict) -> None:
    """POST /api/phase_a/regen_flyin_flyout — wide room bookends (~13 min)."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    state = h.app.state.read_state()
    if state.get("phase_a_flyin_flyout_status") == "running":
        return h._send_error_v59(
            409,
            error_code="GENERIC_ERROR",
            error_message="fly-in/fly-out regeneration already running",
            retry_safe=False,
        )

    # CODE tree — sibling script under Production/tools/
    tools_dir = _PSERVER_TOOLS_DIR
    script = tools_dir / "phase_a_flyin_flyout_wide_v1.py"
    if not script.is_file():
        return h._send_error_v59(
            500,
            error_code="GENERIC_ERROR",
            error_message=f"missing script: {script.name}",
            retry_safe=False,
        )

    _app = h.app
    _stitch = h._auto_assemble_phase_a_stitched

    def _apply_running(state):
        state["phase_a_flyin_flyout_status"] = "running"
        state.pop("phase_a_flyin_flyout_error", None)
        return state

    h.app.state.mutate_state(_apply_running)

    def _bg():
        import subprocess as _sp
        env = {**os.environ, "MN_EVENT_DIR": str(_app.event_dir)}
        try:
            proc = _sp.run(
                [sys.executable, str(script), "--no-element"],
                cwd=str(tools_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=1800,
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "")[:300]
                def _fail(state, _e=err):
                    state["phase_a_flyin_flyout_status"] = f"error: {_e[:120]}"
                    return state
                _app.state.mutate_state(_fail)
                return
            ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            try:
                canonical = _stitch(ts)
            except Exception as exc:  # noqa: BLE001
                canonical = {"error": str(exc)[:200]}
            def _done(state, _c=canonical):
                state["phase_a_flyin_flyout_status"] = "done"
                return state
            _app.state.mutate_state(_done)
            print(f"[phase_a_regen_flyin_flyout] complete canonical={canonical}", flush=True)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            def _exc(state, _x=exc):
                state["phase_a_flyin_flyout_status"] = (
                    f"error: {type(_x).__name__}: {str(_x)[:100]}"
                )
                return state
            _app.state.mutate_state(_exc)

    threading.Thread(target=_bg, daemon=True).start()
    return h._send_json(202, {
        "ok": True,
        "status": "running",
        "message": "Kling wide fly-in/out started (~13 min). Phase A will auto-stitch when done.",
    })


def handle_phase_a_regen_base_clip(h, body: dict) -> None:
    """POST /api/phase_a/regen_base_clip — Kling idle base (~6 min)."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return

    state = h.app.state.read_state()
    if state.get("phase_a_base_clip_regen_status") == "running":
        return h._send_error_v59(
            409,
            error_code="GENERIC_ERROR",
            error_message="base clip regeneration already running",
            retry_safe=False,
        )

    # CODE tree — sibling script under Production/tools/
    tools_dir = _PSERVER_TOOLS_DIR
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from phase_a_chipper_lipsync_base import (  # noqa: WPS433
        DEFAULT_CLIP_ID,
        PHASE_A_BASE_CLIP_DURATION_S,
    )
    script = tools_dir / "phase_a_chipper_lipsync_base.py"
    clip_id = (body or {}).get("clip_id") or DEFAULT_CLIP_ID
    duration_s = int((body or {}).get("duration_s") or PHASE_A_BASE_CLIP_DURATION_S)
    _app = h.app

    def _apply_running(state):
        state["phase_a_base_clip_regen_status"] = "running"
        return state

    h.app.state.mutate_state(_apply_running)

    def _bg():
        import subprocess as _sp
        env = {**os.environ, "MN_EVENT_DIR": str(_app.event_dir)}
        try:
            proc = _sp.run(
                [
                    sys.executable,
                    str(script),
                    "--clip-id",
                    str(clip_id),
                    "--duration",
                    str(duration_s),
                ],
                cwd=str(tools_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=900,
            )
            def _term(state, _rc=proc.returncode, _out=proc.stdout, _err=proc.stderr):
                if _rc == 0:
                    state["phase_a_base_clip_regen_status"] = "done"
                    state["phase_a_chipper_sitting_clip_id"] = clip_id
                else:
                    state["phase_a_base_clip_regen_status"] = (
                        f"error: {(_err or _out or 'failed')[:120]}"
                    )
                return state
            _app.state.mutate_state(_term)
        except Exception as exc:  # noqa: BLE001
            def _exc(state, _x=exc):
                state["phase_a_base_clip_regen_status"] = (
                    f"error: {type(_x).__name__}: {str(_x)[:100]}"
                )
                return state
            _app.state.mutate_state(_exc)

    threading.Thread(target=_bg, daemon=True).start()
    return h._send_json(202, {
        "ok": True,
        "status": "running",
        "clip_id": clip_id,
        "duration_s": duration_s,
        "message": (
            f"Kling idle base clip started (~6 min, {duration_s}s). "
            "Send for Lipsync when done."
        ),
    })


def handle_phase_a_restitch(h, body: dict) -> None:
    """POST /api/phase_a/restitch — re-assemble from pinned fly-in/out + raw lipsync."""
    if not h._assert_event_scope(h._scope_body(body), allow_missing=False):
        return
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    try:
        result = h._auto_assemble_phase_a_stitched(ts)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return h._send_error_v59(
            500,
            error_code="GENERIC_ERROR",
            error_message=f"restitch failed: {exc}",
            retry_safe=True,
        )
    if not result:
        return h._send_error_v59(
            404,
            error_code="GENERIC_ERROR",
            error_message="missing raw lipsync input for Phase A stitch",
            retry_safe=False,
        )
    return h._send_json(200, {"ok": True, "canonical": result})


