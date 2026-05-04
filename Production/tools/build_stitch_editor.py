#!/usr/bin/env python3
"""
build_stitch_editor.py — Rule 7 Path A builder for stitch_editor.html

Usage:
  python3 build_stitch_editor.py [--output PATH] [--port N] [--smoke-test]

Options:
  --output PATH   Where to write the HTML (default: stitch_editor.html next to this script)
  --port N        Server port to inject as SERVER_BASE constant (default: 5111)
  --smoke-test    Verify server up + state file exists + library dirs exist; exit 0/1
"""
import argparse
import os
import socket
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_PRODUCTION = SCRIPT_DIR.parent  # Production/
PROJECT_ROOT = PROJECT_PRODUCTION.parent  # Claude Mindfulnest Project Files/

DEFAULT_OUTPUT = SCRIPT_DIR / "stitch_editor.html"
DEFAULT_TEMPLATE = SCRIPT_DIR / "stitch_editor_template.html"
DEFAULT_PORT = 5111


def smoke_test(port: int) -> bool:
    ok = True

    # 1. Server reachable on port
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=2)
        s.close()
        print(f"[smoke] OK  server reachable on port {port}")
    except OSError:
        print(f"[smoke] FAIL  server NOT reachable on port {port}")
        ok = False

    # 2. State file exists
    state_file = SCRIPT_DIR / "stitch_editor_state.json"
    if state_file.exists():
        print(f"[smoke] OK  {state_file.name} exists")
    else:
        print(f"[smoke] FAIL  {state_file} not found")
        ok = False

    # 3. Sound library dirs exist
    for cat in ("ambient", "sfx", "transitions"):
        lib_dir = PROJECT_PRODUCTION / "assets" / "sound_library" / cat
        if lib_dir.is_dir():
            count = len(list(lib_dir.glob("*.mp3")) + list(lib_dir.glob("*.wav")) + list(lib_dir.glob("*.m4a")))
            print(f"[smoke] OK  sound_library/{cat}/ exists ({count} files)")
        else:
            print(f"[smoke] WARN  sound_library/{cat}/ not found (will be created on first save)")

    return ok


def build(template_path: Path, output_path: Path, port: int) -> None:
    if not template_path.exists():
        print(f"ERROR: template not found: {template_path}", file=sys.stderr)
        sys.exit(1)

    template = template_path.read_text(encoding="utf-8")

    # Inject server base URL constant (only transformation this builder makes)
    result = template.replace("{{SERVER_BASE}}", f"http://localhost:{port}")

    output_path.write_text(result, encoding="utf-8")
    print(f"Built {output_path.name} ({len(result):,} chars, port={port})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()

    if args.smoke_test:
        ok = smoke_test(args.port)
        sys.exit(0 if ok else 1)

    build(DEFAULT_TEMPLATE, args.output, args.port)


if __name__ == "__main__":
    main()
