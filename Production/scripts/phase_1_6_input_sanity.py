#!/usr/bin/env python3
"""
phase_1_6_input_sanity.py — Input Data Sanity helper for zero-error-qa Phase 1.6.

Validates on-disk file paths BEFORE they are passed to external generation APIs
(gpt-image-1, Flux Kontext, Kling, Seedance, ElevenLabs, ByteDance LipSync) or
media subprocesses (ffmpeg, ffprobe, imagemagick). Prevents API budget burn on
placeholder, corrupt, truncated, or under-sized inputs.

Authoritative spec: .claude/skills/zero-error-qa/SKILL.md PHASE 1.6.

Callable from:
    1. zero-error-qa Phase 1.6 (QA gate, pre-merge)
    2. Runtime wrappers around external API calls (e.g.
       Production/lib/api_call_with_input_validation.py — when built)

Both call sites should share this single implementation per Phase 0 synthesis
CRIT-3 (static-vs-runtime gap resolution).

Division of responsibility:
- This helper validates a SPECIFIC PATH and emits PASS or HARD_STOP only.
- The SKILL.md text governs the broader DEFERRED / PARTIAL / SKIP outcome
  classes — those are Claude-reasoning-layer declarations made when Claude
  reads the diff and finds (mid-pipeline-generated paths / non-disk inputs /
  no-trigger-firing cases). This helper does not see the diff and cannot
  declare DEFERRED/PARTIAL/SKIP on its own.

Exit codes (CLI):
    0 = PASS (all applicable checks succeeded)
    1 = HARD STOP (a/b/c/d failure — fix before passing to external consumer)
    2 = invocation error (bad args, unknown declared kind, etc.)

Programmatic API:
    from phase_1_6_input_sanity import sanity_check
    result = sanity_check(path, kind)
    # result.status in {"PASS", "HARD_STOP"}; result.detail is human-readable

Per Phase 0 synthesis 20260427_165837:
- JSON has NO byte floor (rely on json.load parse).
- JPEG uses PIL.Image.open(p).load() (verify() too lenient on truncated JPEG).
- PNG/WebP use PIL.Image.open(p).verify().
- Audio decode via ffprobe (mutagen NOT installed; ffprobe canonical per LD-284).
- Character-asset paths: existence (a) -> registration -> (b) size -> (c) decode -> (d) dim.
- Character-ref pattern: `Character_Assets/` (case-insensitive directory) OR
  basename matches `*_master.<image-ext>` / `*_reference_master.<image-ext>`.
"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import json
import os
import platform as _platform
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

# Floors per Phase 1.6 spec. Comparator below is `<= FLOOR` HARD STOP, which
# implements the spec inequality `size > FLOOR` for PASS (file at exactly FLOOR
# fails per spec).
IMAGE_FLOOR_BYTES = 10_000
AUDIO_FLOOR_BYTES = 5_000
VIDEO_FLOOR_BYTES = 100_000

# Character-asset reference dim floor (pixels per side)
CHAR_REF_DIM_FLOOR = 256

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg"}
VIDEO_EXTS = {".mp4", ".mov"}
JSON_EXTS = {".json"}

# Character-asset reference patterns. The matcher requires EITHER:
#   - the path contains the case-insensitive directory `Character_Assets/`, OR
#   - the basename matches a glob `*_master.<image-ext>` /
#     `*_reference_master.<image-ext>` for an image extension.
# This avoids false-positive HARD STOPs on non-character `*_master.*` files
# such as `event_3_render_master.mp4`, `audio_master.wav`, `prompt_master.json`
# which are not character references.
CHAR_REF_DIR_MARKER = "/character_assets/"
CHAR_REF_BASENAME_GLOBS_TEMPLATE = ("*_master.{ext}", "*_reference_master.{ext}")


@dataclass
class SanityResult:
    status: str  # "PASS" | "HARD_STOP"
    detail: str


def _project_root() -> str:
    env = os.environ.get("MINDFULNEST_PROJECT_ROOT")
    if env:
        return env
    if _platform.system() == "Windows":
        return r"C:\Users\ECDS Clinical\Dropbox\Claude Mindfulnest Project Files"
    return "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def _is_character_reference(path: str) -> bool:
    norm = path.replace("\\", "/").lower()
    if CHAR_REF_DIR_MARKER in norm:
        return True
    base = os.path.basename(norm)
    base_ext = os.path.splitext(base)[1]
    if base_ext not in IMAGE_EXTS:
        return False
    ext_no_dot = base_ext.lstrip(".")
    for tmpl in CHAR_REF_BASENAME_GLOBS_TEMPLATE:
        if fnmatch.fnmatch(base, tmpl.format(ext=ext_no_dot)):
            return True
    return False


def _ffprobe_streams(path: str) -> tuple[int, list[dict]]:
    cp = subprocess.run(
        ["ffprobe", "-v", "error", "-of", "json", "-show_streams", path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if cp.returncode != 0:
        return cp.returncode, []
    try:
        data = json.loads(cp.stdout or "{}")
    except json.JSONDecodeError:
        return 1, []
    return 0, data.get("streams", []) or []


def _check_image_decode(path: str, ext: str) -> Optional[str]:
    try:
        from PIL import Image
    except ImportError as e:
        return f"PIL not importable: {e}"
    try:
        if ext in {".jpg", ".jpeg"}:
            with Image.open(path) as im:
                im.load()
        else:
            with Image.open(path) as im:
                im.verify()
    except Exception as e:
        return f"PIL decode failed: {type(e).__name__}: {e}"
    return None


def _image_dims(path: str) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as im:
        return im.size


@contextlib.contextmanager
def _temp_sys_path(entry: str):
    inserted = False
    if entry not in sys.path:
        sys.path.insert(0, entry)
        inserted = True
    try:
        yield
    finally:
        if inserted:
            with contextlib.suppress(ValueError):
                sys.path.remove(entry)


def _check_prod_assets_registered(path: str) -> Optional[str]:
    """Returns None on registration found, otherwise an error string."""
    project_root = _project_root()
    with _temp_sys_path(project_root):
        try:
            from Production.lib.directus_admin_client import DirectusAdminClient  # type: ignore
        except ImportError as e:
            return f"Directus admin client unavailable: {e}"

        rel = path
        if path.startswith(project_root):
            rel = os.path.relpath(path, project_root)
        candidates = {path, rel, rel.replace(os.sep, "/")}

        try:
            client = DirectusAdminClient()
            for cand in candidates:
                rows = client.get_items(
                    "prod_assets",
                    filters={"file_path": {"_eq": cand}},
                    limit=1,
                    fields=["id", "file_path"],
                )
                if rows:
                    return None
            return f"path not registered in prod_assets (tried {sorted(candidates)})"
        except Exception as e:
            return f"prod_assets lookup error: {type(e).__name__}: {e}"


def sanity_check(path: str, kind: Optional[str] = None) -> SanityResult:
    """Run all applicable Phase 1.6 checks for `path`.

    `kind` is one of "image", "audio", "video", "json". If None, infer from extension.
    Returns SanityResult with status in {"PASS", "HARD_STOP"}.
    """
    if not isinstance(path, str) or not path:
        return SanityResult("HARD_STOP", "(invocation) empty or non-string path")

    ext = _ext(path)
    if kind is None:
        if ext in IMAGE_EXTS:
            kind = "image"
        elif ext in AUDIO_EXTS:
            kind = "audio"
        elif ext in VIDEO_EXTS:
            kind = "video"
        elif ext in JSON_EXTS:
            kind = "json"
        else:
            return SanityResult(
                "HARD_STOP",
                f"(invocation) unknown extension {ext!r}; pass --kind explicitly",
            )

    if kind not in {"image", "audio", "video", "json"}:
        return SanityResult("HARD_STOP", f"(invocation) unknown kind: {kind!r}")

    # (a) existence — runs FIRST, before any other check (per spec ordering).
    if not os.path.exists(path):
        return SanityResult("HARD_STOP", f"(a) does not exist: {path}")

    # Character-asset reference registration check — runs after (a) existence
    # but before (b) size and (c) decode. Per spec: "BEFORE checks (b)-(c)".
    is_char_ref = (kind == "image" and _is_character_reference(path))
    if is_char_ref:
        reg_err = _check_prod_assets_registered(path)
        if reg_err is not None:
            return SanityResult(
                "HARD_STOP",
                f"(d-pre/find_asset) character-ref path not registered: {reg_err}. "
                f"Per Rule 31/34, register via Production/tools/registered_write.py first.",
            )

    size = os.path.getsize(path)

    # (b) size floor (does not apply to JSON)
    if kind == "image" and size <= IMAGE_FLOOR_BYTES:
        return SanityResult(
            "HARD_STOP",
            f"(b) image size {size}B <= {IMAGE_FLOOR_BYTES}B floor: {path}",
        )
    if kind == "audio" and size <= AUDIO_FLOOR_BYTES:
        return SanityResult(
            "HARD_STOP",
            f"(b) audio size {size}B <= {AUDIO_FLOOR_BYTES}B floor: {path}",
        )
    if kind == "video" and size <= VIDEO_FLOOR_BYTES:
        return SanityResult(
            "HARD_STOP",
            f"(b) video size {size}B <= {VIDEO_FLOOR_BYTES}B floor: {path}",
        )

    # (c) decode
    if kind == "image":
        err = _check_image_decode(path, ext)
        if err is not None:
            return SanityResult("HARD_STOP", f"(c) {err}: {path}")
    elif kind == "audio":
        rc, streams = _ffprobe_streams(path)
        if rc != 0 or not any(s.get("codec_type") == "audio" for s in streams):
            return SanityResult(
                "HARD_STOP",
                f"(c) ffprobe found no audio stream (rc={rc}): {path}",
            )
    elif kind == "video":
        rc, streams = _ffprobe_streams(path)
        if rc != 0 or not any(s.get("codec_type") == "video" for s in streams):
            return SanityResult(
                "HARD_STOP",
                f"(c) ffprobe found no video stream (rc={rc}): {path}",
            )
    elif kind == "json":
        try:
            with open(path, "r", encoding="utf-8") as f:
                json.load(f)
        except Exception as e:
            return SanityResult(
                "HARD_STOP",
                f"(c) json.load failed: {type(e).__name__}: {e}: {path}",
            )

    # (d) character-asset dim floor (image-only, after (a)+registration+(b)+(c) passed)
    if is_char_ref:
        try:
            w, h = _image_dims(path)
        except Exception as e:
            return SanityResult(
                "HARD_STOP",
                f"(d) PIL .size failed: {type(e).__name__}: {e}: {path}",
            )
        if w < CHAR_REF_DIM_FLOOR or h < CHAR_REF_DIM_FLOOR:
            return SanityResult(
                "HARD_STOP",
                f"(d) char-ref dims {w}x{h} below {CHAR_REF_DIM_FLOOR}x{CHAR_REF_DIM_FLOOR} floor: {path}",
            )
        return SanityResult(
            "PASS",
            f"verified {path}: {size}B, image, {w}x{h}, char-ref registered + dim OK",
        )

    if kind == "image":
        try:
            w, h = _image_dims(path)
            return SanityResult(
                "PASS", f"verified {path}: {size}B, image, {w}x{h}"
            )
        except Exception:
            return SanityResult("PASS", f"verified {path}: {size}B, image (size unread)")
    return SanityResult("PASS", f"verified {path}: {size}B, {kind}")


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="zero-error-qa Phase 1.6 input data sanity check"
    )
    parser.add_argument("--path", "-p", required=True, help="File path to validate")
    parser.add_argument(
        "--kind",
        "-k",
        choices=["image", "audio", "video", "json"],
        default=None,
        help="Declared file kind (inferred from extension if omitted)",
    )
    args = parser.parse_args()
    res = sanity_check(args.path, args.kind)
    print(f"{res.status} — {res.detail}")
    if res.status == "PASS":
        return 0
    if res.status == "HARD_STOP":
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
