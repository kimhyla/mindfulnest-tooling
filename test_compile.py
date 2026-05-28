#!/usr/bin/env python3
"""Test compilation of modified Python files"""
import py_compile
import sys
from pathlib import Path

base = Path("/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/tools")
files = [
    "server_handlers/background.py",
    "server_handlers/phases.py",
    "production_server.py",
    "magic_compositor.py",
    "build_storyboard.py",
]

all_ok = True
for f in files:
    try:
        py_compile.compile(str(base / f), doraise=True)
        print(f"✓ {f} OK")
    except py_compile.PyCompileError as e:
        print(f"✗ {f} FAILED:")
        print(f"  {e}")
        all_ok = False

if all_ok:
    print("\n✓ All files compiled successfully")
    sys.exit(0)
else:
    print("\n✗ Some files failed compilation")
    sys.exit(1)
