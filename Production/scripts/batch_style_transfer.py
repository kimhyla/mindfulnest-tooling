#!/usr/bin/env python3
"""
batch_style_transfer.py
-----------------------
Convert existing character pose images to a new art style using gpt-image-1
image edits (multi-image input: source + style reference).

Usage:
  python3 batch_style_transfer.py                  # Tessa test only (3 images)
  python3 batch_style_transfer.py --all             # All characters (up to 3 each)
  python3 batch_style_transfer.py --char LUNA       # Single character

Outputs to:
  Production/NEW STYLE CHARACTERS/{CHARACTER}/{emotion}_{timestamp}.png

Kim's exact prompt (verbatim):
  "I am uploading a style reference image. Using this style, please reproduce
   this existing image exactly, same position, same shapes, same arrangement,
   same items, same layout in all respects except that it's in the style of
   the ref image"
"""
from __future__ import annotations

import argparse
import base64
import http.client as _http
import importlib.util
import json
import os
import ssl as _ssl
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DROPBOX_PROD = Path(
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
)
STYLE_REF_PATHS = [
    DROPBOX_PROD / "NEW STYLE CHARACTERS" / "STYLE REF 1.png",  # owl explorer
    DROPBOX_PROD / "NEW STYLE CHARACTERS" / "STYLE REF 2.png",  # flamingo with balloon
]
OUTPUT_BASE = DROPBOX_PROD / "NEW STYLE CHARACTERS"

# ---------------------------------------------------------------------------
# Kim's style-transfer prompt (verbatim from 2026-05-21 instruction)
# ---------------------------------------------------------------------------
STYLE_PROMPT = (
    "I am uploading style reference images. Using this style, please reproduce "
    "the first image exactly, same position, same shapes, same arrangement, "
    "same items, same layout — show the COMPLETE character from head to toe, "
    "nothing cropped — in all respects except that it's in the style of "
    "the reference images"
)

# ---------------------------------------------------------------------------
# Character → emotion → source path map
# Only include combinations where a good source image exists.
# Skipped emotions get a warning, not an error.
# ---------------------------------------------------------------------------
# Paths are relative to DROPBOX_PROD
CHARACTER_MAP: dict[str, dict[str, str]] = {
    "TESSA": {
        "neutral_happy": "Tessa/poses/tessa_neutral.png",
        "shocked_thrilled": "Tessa/poses/tessa_shocked.png",
        "upset_sad": "Tessa/poses/tessa_scared.png",
    },
    "LUNA": {
        "neutral_happy": "Luna/poses/luna_peaceful.png",
        "shocked_thrilled": "Luna/poses/luna_shocked.png",
        "upset_sad": "Luna/poses/luna stressed by mindfulnest.png",
    },
    "BENSON": {
        "neutral_happy": "Benson/poses/benson_pose_neutral.png",
        "shocked_thrilled": "Benson/poses/benson_pose_shocked_openmouth_nb_c1.png",
        "upset_sad": "Benson/poses/benson_pose_sad.png",
    },
    "EMBER": {
        "neutral_happy": "Ember/poses/ember_pose_happy.png",
        "shocked_thrilled": "Ember/poses/ember_pose_shocked_halfsmile_nb_c1.png",
        "upset_sad": "Ember/poses/ember_pose_sad.png",
    },
    "BORK": {
        "neutral_happy": "Bork/poses/bork_pose_neutral.png",
        "shocked_thrilled": "Bork/poses/bork_pose_shocked_openmouth_nb_c1.png",
        "upset_sad": "Bork/poses/bork_pose_sad.png",
    },
    "BRAMBLE": {
        "neutral_happy": "Bramble/poses/bramble_pose_neutral.png",
        "shocked_thrilled": "Bramble/poses/bramble_pose_shocked_openmouth.png",
        "upset_sad": "Bramble/poses/bramble_pose_sad.png",
    },
    "GRIZZLE": {
        "neutral_happy": "Grizzle/poses/grizzle_HERO.png",
        "shocked_thrilled": "Grizzle/poses/grizzle_pose_shocked_openmouth_nb_c1.png",
        # No distinct sad pose found — skip
    },
    "OLIVER": {
        "neutral_happy": "Oliver/poses/oliver_pose_happy_v3.png",
        # No shocked pose found — skip
        "upset_sad": "Oliver/poses/oliver_pose_sad.png",
    },
}


# ---------------------------------------------------------------------------
# API key loading (same pattern as kling_startend_pipeline.py)
# ---------------------------------------------------------------------------
def _load_openai_key() -> str:
    env_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if env_key:
        return env_key

    # Try lib.paths → API_KEYS_MASTER_PATH (Dropbox canonical)
    try:
        _spec = importlib.util.spec_from_file_location(
            "production_server",
            str(DROPBOX_PROD / "tools" / "production_server.py"),
        )
        mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(mod)

        try:
            from lib.paths import API_KEYS_MASTER_PATH  # type: ignore
            keys = mod.parse_api_keys(API_KEYS_MASTER_PATH)
        except ImportError:
            keys = mod.parse_api_keys(DROPBOX_PROD / "API_KEYS_MASTER.md")

        key = (keys.get("openai") or "").strip()
        if key:
            return key
    except Exception as exc:
        print(f"  [warn] Could not load via production_server: {exc}")

    # Direct parse fallback
    try:
        ak_path = DROPBOX_PROD / "API_KEYS_MASTER.md"
        text = ak_path.read_text()
        for line in text.splitlines():
            if "openai" in line.lower() and "sk-" in line:
                parts = line.split()
                for p in parts:
                    if p.startswith("sk-"):
                        return p.strip("`\"',")
    except Exception as exc:
        print(f"  [warn] Direct parse failed: {exc}")

    sys.exit("FATAL: No OpenAI API key found. Set OPENAI_API_KEY env var or check API_KEYS_MASTER.md")


# ---------------------------------------------------------------------------
# gpt-image-1 style transfer — TWO images (source + style ref)
# ---------------------------------------------------------------------------
def generate_styled(
    source_bytes: bytes,
    style_ref_list: list[bytes],
    api_key: str,
    source_label: str = "source",
    timeout_s: int = 240,
) -> bytes:
    """
    POST to /v1/images/edits with N+1 image[] fields:
      [0] source image (the pose to restyle)
      [1..N] style reference images

    Returns PNG bytes of the styled result.
    """
    boundary = f"----MNStyleBoundary-{uuid.uuid4().hex}"

    def _text_field(name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")

    def _file_field(field_name: str, filename: str, content_type: str, data: bytes) -> bytes:
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
        return header + data + b"\r\n"

    # Use 1024x1024 for character portraits (safe square; avoids "auto" duplication bug)
    size_param = "1024x1024"

    style_ref_total = sum(len(b) for b in style_ref_list)
    body_parts = [
        _text_field("model", "gpt-image-1"),
        _text_field("prompt", STYLE_PROMPT),
        _text_field("quality", "high"),
        _text_field("input_fidelity", "high"),
        _text_field("size", size_param),
        _text_field("n", "1"),
        # image[] field 0: source (pose to restyle)
        _file_field("image[]", f"{source_label}.png", "image/png", source_bytes),
    ]
    # image[] fields 1..N: style references
    for i, ref_bytes in enumerate(style_ref_list):
        body_parts.append(_file_field("image[]", f"style_ref_{i+1}.png", "image/png", ref_bytes))
    body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(body_parts)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }

    print(f"  → POST /v1/images/edits  source={len(source_bytes):,}B  "
          f"style_refs={len(style_ref_list)} ({style_ref_total:,}B total)  size={size_param}")

    ctx = _ssl.create_default_context()
    try:
        conn = _http.HTTPSConnection("api.openai.com", timeout=timeout_s, context=ctx)
        conn.request("POST", "/v1/images/edits", body=body, headers=headers)
        resp = conn.getresponse()
        status = resp.status
        raw = resp.read()
        conn.close()
    except Exception as exc:
        sys.exit(f"  Connection failed: {type(exc).__name__}: {exc}")

    if status >= 400:
        sys.exit(f"  HTTP {status}: {raw[:800].decode('utf-8', 'replace')}")

    try:
        result = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        sys.exit(f"  Non-JSON response: {exc}  body={raw[:400]!r}")

    data = result.get("data") or []
    if not data:
        sys.exit(f"  No data in response: {result}")

    b64 = data[0].get("b64_json")
    if not b64:
        sys.exit(f"  No b64_json in response data: {data[0]}")

    try:
        png_bytes = base64.b64decode(b64)
    except Exception as exc:
        sys.exit(f"  b64 decode failed: {exc}")

    print(f"  ← {len(png_bytes):,}B PNG received")
    return png_bytes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_character(char_name: str, api_key: str, style_ref_list: list[bytes]) -> list[Path]:
    """Process one character — returns list of saved output paths."""
    emotions = CHARACTER_MAP.get(char_name.upper())
    if not emotions:
        print(f"[SKIP] {char_name} — not in CHARACTER_MAP")
        return []

    out_dir = OUTPUT_BASE / char_name.upper()
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved: list[Path] = []

    for emotion, rel_path in emotions.items():
        src_path = DROPBOX_PROD / rel_path
        if not src_path.exists():
            print(f"  [SKIP] {char_name}/{emotion} — source not found: {src_path}")
            continue

        print(f"\n[{char_name}] {emotion}")
        print(f"  source: {src_path.name}")

        source_bytes = src_path.read_bytes()

        try:
            png_bytes = generate_styled(
                source_bytes=source_bytes,
                style_ref_list=style_ref_list,
                api_key=api_key,
                source_label=f"{char_name.lower()}_{emotion}",
            )
        except SystemExit as e:
            print(f"  [ERROR] {e}")
            continue

        out_path = out_dir / f"{emotion}_{ts}.png"
        out_path.write_bytes(png_bytes)
        print(f"  ✓ saved → {out_path}")
        saved.append(out_path)

    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch style-transfer character images via gpt-image-1")
    parser.add_argument("--all", action="store_true", help="Process all characters (default: Tessa only)")
    parser.add_argument("--char", type=str, default=None, help="Single character name (e.g. LUNA)")
    args = parser.parse_args()

    # Load style reference images
    style_ref_list: list[bytes] = []
    for srp in STYLE_REF_PATHS:
        if not srp.exists():
            print(f"  [warn] Style ref not found: {srp} — skipping")
            continue
        b = srp.read_bytes()
        style_ref_list.append(b)
        print(f"Style reference: {srp.name}  ({len(b):,}B)")
    if not style_ref_list:
        sys.exit("FATAL: No style reference images found")

    # Load API key
    api_key = _load_openai_key()
    print(f"OpenAI key: {api_key[:8]}...{api_key[-4:]}  ({len(api_key)} chars)")
    print()

    # Determine which characters to run
    if args.char:
        chars = [args.char.upper()]
    elif args.all:
        chars = list(CHARACTER_MAP.keys())
    else:
        chars = ["TESSA"]  # Default: Tessa test

    all_saved: list[Path] = []
    for char in chars:
        saved = run_character(char, api_key, style_ref_list)
        all_saved.extend(saved)

    print(f"\n{'='*60}")
    print(f"DONE — {len(all_saved)} image(s) saved:")
    for p in all_saved:
        print(f"  {p}")


if __name__ == "__main__":
    main()
