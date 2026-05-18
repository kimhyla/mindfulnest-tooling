#!/usr/bin/env python3
"""One-shot extractor for Phase 4 Pass 2. Run from Production/tools/."""
from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).parent
PS = ROOT / "production_server.py"
SOURCE = PS.read_text(encoding="utf-8")
LINES = SOURCE.splitlines(keepends=True)

BEATS_LEGACY = [
    "_handle_beat_accepted_bg",
    "_handle_beat_finalize",
    "_serve_beat_audio",
    "_handle_beat_update_text",
    "_handle_beat_update_speaker",
    "_handle_beat_done_toggle",
    "_handle_beat_graft",
    "_handle_beat_regenerate_audio",
    "_handle_beat_delay",
    "_handle_beat_trim",
]

BACKGROUND = [
    "_serve_magic_picker",
    "_handle_magic_resolve_bg",
    "_handle_magic_status",
    "_handle_magic_submit_path",
    "_handle_magic_still",
    "_handle_magic_video",
    "_handle_bg_crop_preview",
    "_handle_bg_segments",
    "_handle_bg_session_state",
    "_handle_bg_poll_flux",
    "_handle_bg_set_active_context",
    "_handle_bg_extract_beats",
    "_handle_bg_inject_beats",
    "_handle_bg_update_beat",
    "_handle_bg_reorder_beats",
    "_handle_bg_delete_beat",
    "_handle_bg_accept_beats",
    "_handle_bg_submit_flux",
    "_handle_bg_submit_gpt_batch",
    "_handle_bg_poll_gpt_status",
    "_handle_bg_accept_option",
    "_handle_bg_accept_lib_image",
    "_handle_bg_groups",
    "_handle_bg_add_beat",
    "_handle_bg_create_group",
    "_handle_bg_delete_group",
    "_handle_bg_update_group",
    "_handle_bg_assemble_group",
    "_handle_bg_poll_assemble_status",
    "_handle_bg_run_local_animation",
    "_handle_bg_update_beat_anim_method",
    "_handle_bg_accept_local_animation",
    "_handle_bg_stills",
    "_handle_animate",
    "_handle_status",
    "_handle_redo",
    "_handle_watercolor_animate",
]

CROPPER = [
    "_handle_cr_library",
    "_handle_cr_full_image",
    "_handle_cr_library_delete",
    "_handle_cr_save_crop",
    "_handle_cr_upload",
    "_serve_cropper",
    "_serve_asset",
]

MODULES = {
    "beats_legacy": (BEATS_LEGACY, "beats_legacy.py", "Legacy beat handlers"),
    "background": (BACKGROUND, "background.py", "Background / magic / animate handlers"),
    "cropper": (CROPPER, "cropper.py", "Cropper + asset serve handlers"),
}


def _find_class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise RuntimeError(f"class {name} not found")


def _method_map(cls: ast.ClassDef) -> dict[str, ast.FunctionDef]:
    out: dict[str, ast.FunctionDef] = {}
    for node in cls.body:
        if isinstance(node, ast.FunctionDef):
            out[node.name] = node
    return out


def _decorator_lines(fn: ast.FunctionDef) -> list[str]:
    if not fn.decorator_list:
        return []
    start = min(d.lineno for d in fn.decorator_list)
    end = fn.lineno - 1
    return [LINES[i - 1] for i in range(start, end + 1)]


def _method_source_lines(fn: ast.FunctionDef) -> list[str]:
    start = fn.lineno - 1
    end = fn.end_lineno
    return LINES[start:end]


def _to_free_function(method_lines: list[str], old_name: str, new_name: str) -> str:
    text = "".join(method_lines)
    # Drop leading blank lines inside class
    text = text.lstrip("\n")
    # Rename def line: _handle_foo(self -> handle_foo(h
    m = re.match(
        r"^(\s*)def " + re.escape(old_name) + r"\(self(.*)\)\s*(->.*)?:",
        text,
        re.MULTILINE,
    )
    if not m:
        raise ValueError(f"cannot parse def for {old_name}")
    indent, rest_args, ret = m.group(1), m.group(2), m.group(3) or ""
    # Module-level functions use no extra indent (body was class-indented)
    class_indent = indent
    body = text[m.end() :]
    # Dedent method body by EXACTLY one class-indent level (4 spaces).
    # textwrap.dedent would strip the min common whitespace, which for a
    # method body inside a class is 8 spaces — that flattens the body to
    # column 0 (invalid). We want 8→4, preserving inner indentation.
    body_lines = body.splitlines(keepends=True)
    new_body_lines = []
    for line in body_lines:
        if line.strip() == "":
            new_body_lines.append(line)  # preserve blank lines as-is
        elif line.startswith("    "):
            new_body_lines.append(line[4:])  # strip exactly 4 spaces
        else:
            new_body_lines.append(line)
    dedented = "".join(new_body_lines)
    sig = f"def {new_name}(h{rest_args}){ret}:\n"
    # Replace self with h in body only
    dedented = re.sub(r"\bself\b", "h", dedented)
    # server_handlers/*.py lives one level down from Production/tools/
    dedented = dedented.replace(
        "Path(__file__).parent",
        "Path(__file__).resolve().parent.parent",
    )
    return sig + dedented


def _free_name(method_name: str) -> str:
    if method_name.startswith("_"):
        return method_name[1:]  # _handle_foo -> handle_foo
    return method_name


def _shim(method_name: str, module: str, decorator_lines: list[str], fn: ast.FunctionDef) -> str:
    free = _free_name(method_name)
    import_mod = f"server_handlers.{module}"
    # Reconstruct signature from AST
    args = ["self"]
    for a in fn.args.args[1:]:  # skip self
        if a.arg == "self":
            continue
        args.append(a.arg)
    # defaults / kwonly not needed for shims — read from source line
    def_line = LINES[fn.lineno - 1].strip()
    # Use original def line but replace name
    shim_def = def_line.replace(f"def {method_name}", f"def {method_name}", 1)
    body = (
        f"        from {import_mod} import {free}\n"
        f"        return {free}(self"
    )
    # Build call args from signature
    import inspect

    # Build call args from AST (drops type annotations + default values cleanly).
    # AST args.args[0] is always self for methods; we skip it and use the
    # parameter NAMES only (no `: type` annotations, no `= default` values)
    # — those would be invalid syntax at the call site.
    call_args_from_ast = [a.arg for a in fn.args.args[1:]]
    # Also include kwonly args if any (rare for handlers but safe to honor)
    call_args_from_ast.extend(a.arg for a in fn.args.kwonlyargs)
    call_tail = ", ".join(call_args_from_ast)
    if call_tail:
        body += f", {call_tail}"
    body += ")\n"
    dec = "".join(decorator_lines)
    return dec + "    " + shim_def + "\n" + body


def _module_level_priv_names(tree: ast.Module) -> set[str]:
    """Return names of all module-level function defs in production_server.py.
    Used to detect references that need a `from tools.production_server import ...`."""
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out.add(node.name)
    return out


def _collect_helper_refs(method_lines: list[str], priv_names: set[str]) -> set[str]:
    """Scan method body text for references to module-level helper names."""
    body_text = "".join(method_lines)
    found: set[str] = set()
    for name in priv_names:
        if re.search(rf"\b{re.escape(name)}\b", body_text):
            found.add(name)
    return found


# Kitchen-sink imports every extracted handler module gets at top.
# Mirrors production_server.py top imports so extracted bodies that reference
# any of those names resolve. Late imports inside function bodies remain too.
_KITCHEN_SINK_IMPORTS = """from __future__ import annotations

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

# Project-internal modules imported the same way production_server.py does.
# Handler bodies may reference any of these by bare name.
from lib.atomic_json_write import atomic_json_write
from lib.v3_partition import _iter_v3_beats
from lib.paths import DROPBOX_ROOT
import scope_router
from ffmpeg_utils import strip_audio as _strip_clip_audio
from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC
"""


def extract():
    tree = ast.parse(SOURCE)
    cls = _find_class(tree, "ProductionHandler")
    methods = _method_map(cls)
    priv_names = _module_level_priv_names(tree)

    replacements: list[tuple[int, int, str]] = []  # start_line, end_line, new_text (1-based inclusive)

    for mod_key, (names, filename, doc) in MODULES.items():
        # First pass: collect all helpers referenced across this module's methods.
        all_helper_refs: set[str] = set()
        for name in names:
            if name not in methods:
                raise KeyError(f"missing method {name}")
            fn = methods[name]
            src = _method_source_lines(fn)
            all_helper_refs |= _collect_helper_refs(src, priv_names)

        header = [
            f'"""{doc} — V59 Phase 4 Pass 2.\n\n'
            "Handlers extracted from production_server.py.\n"
            "Each function takes the live `ProductionHandler` instance as `h`.\n"
            '"""\n',
            _KITCHEN_SINK_IMPORTS,
        ]
        # Add late import of private module-level helpers from production_server.
        # Safe: handler modules are imported lazily from shims, so production_server
        # is fully loaded by the time these names are looked up.
        if all_helper_refs:
            helper_imports = ", ".join(sorted(all_helper_refs))
            header.append(
                f"\n# Late-resolvable private helpers from the host module.\n"
                f"from tools.production_server import (  # noqa: E402\n"
                + "".join(f"    {n},\n" for n in sorted(all_helper_refs))
                + ")\n\n"
            )
        else:
            header.append("\n")
        parts = header[:]
        for name in names:
            if name not in methods:
                raise KeyError(f"missing method {name}")
            fn = methods[name]
            free = _free_name(name)
            src = _method_source_lines(fn)
            parts.append(_to_free_function(src, name, free))
            parts.append("\n\n")
            dec = _decorator_lines(fn)
            shim = _shim(name, mod_key, dec, fn)
            start = (dec[0] if dec else LINES[fn.lineno - 1])
            start_lineno = min(d.lineno for d in fn.decorator_list) if fn.decorator_list else fn.lineno
            end_lineno = fn.end_lineno
            replacements.append((start_lineno, end_lineno, shim))

        out_path = ROOT / "server_handlers" / filename
        content = "".join(parts)
        out_path.write_text(content, encoding="utf-8")
        print(f"Wrote {out_path} ({content.count(chr(10))} lines)")

    # Apply replacements bottom-up
    new_lines = list(LINES)
    for start, end, shim in sorted(replacements, key=lambda x: -x[0]):
        new_lines[start - 1 : end] = [shim]

    PS.write_text("".join(new_lines), encoding="utf-8")
    print(f"Updated {PS} ({len(new_lines)} lines)")


if __name__ == "__main__":
    extract()
