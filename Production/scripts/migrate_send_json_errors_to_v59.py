#!/usr/bin/env python3
"""V59 Phase 7 mass error-shape migrator.

Migrates legacy `(h|self)._send_json(<4xx|5xx>, {"error": "<msg>"[, "<k>": <v>]*})`
to canonical V59 form:
    (h|self)._send_error_v59(
        <status>,
        error_code="<SCREAMING_SNAKE>",
        error_message="<msg>",
        retry_safe=<bool>,
        hint=<None|str>,
        extra=<None|dict>,
    )

Strategy:
- Use Python ast.parse to find call sites (robust against multiline/whitespace).
- For each match, determine:
    * status (literal int)
    * error_message (the "error" key's value AST — preserved as-is, supports f-strings/concat)
    * extra (any OTHER keys in the dict — bundled into extra={...})
    * error_code (lookup in PHRASE_MAP if message is a literal str; else generic mapped from
      first 6 words of the literal, or GENERIC_ERROR with the message-AST preserved for non-literals)
    * retry_safe (4xx -> False, 5xx -> True per V59 convention)
- Rewrite source text via offset edits, preserving comments + surrounding code.

Run:
    python3 Production/scripts/migrate_send_json_errors_to_v59.py --dry-run
    python3 Production/scripts/migrate_send_json_errors_to_v59.py --apply
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_SERVER = ROOT / "Production" / "tools" / "production_server.py"
SERVER_HANDLERS_DIR = ROOT / "Production" / "tools" / "server_handlers"

# Hand-curated phrase→error_code map for the common patterns surfaced by the
# pre-migration grep. Anything not matched here falls through to the heuristic
# auto-generator (snake-case the message). Map is consulted by EXACT message
# string match (case-sensitive); add new entries as they appear.
PHRASE_MAP: dict[str, str] = {
    "not implemented in v1 MVP": "NOT_IMPLEMENTED_V1_MVP",
    "not found": "NOT_FOUND",
    "file not found": "FILE_NOT_FOUND",
    "missing beat_id in body": "MISSING_BEAT_ID",
    "missing beat_id": "MISSING_BEAT_ID",
    "beat required": "MISSING_BEAT",
    "beat_id required": "MISSING_BEAT_ID",
    "beat_id required and must be non-empty string": "MISSING_BEAT_ID",
    "beat_id and key required": "MISSING_BEAT_ID_OR_KEY",
    "beat_id and option_key required": "MISSING_BEAT_ID_OR_OPTION_KEY",
    "beat_ids required": "MISSING_BEAT_IDS",
    "beats array required": "MISSING_BEATS_ARRAY",
    "beat_id must match [A-Za-z0-9_-]+": "INVALID_BEAT_ID",
    "missing 'beat'/'beat_id' or 'image_key'": "MISSING_BEAT_OR_IMAGE_KEY",
    "missing 'beat'": "MISSING_BEAT",
    "cross-origin not allowed": "CROSS_ORIGIN_FORBIDDEN",
    "path outside project root": "PATH_OUTSIDE_PROJECT_ROOT",
    "path validation failed": "PATH_VALIDATION_FAILED",
    "input_path outside project root": "INPUT_PATH_OUTSIDE_PROJECT_ROOT",
    "input_path required": "MISSING_INPUT_PATH",
    "filename escapes event_dir": "FILENAME_ESCAPES_EVENT_DIR",
    "filename validation failed": "FILENAME_VALIDATION_FAILED",
    "filename must be .png, .webp, .jpg, or .jpeg": "INVALID_FILENAME_EXTENSION",
    "filename and image_b64 required": "MISSING_FILENAME_OR_IMAGE_B64",
    "name and data are required": "MISSING_NAME_OR_DATA",
    "image corruption detected, write aborted": "IMAGE_CORRUPTION_DETECTED",
    "crop_png_b64 required": "MISSING_CROP_PNG_B64",
    "forbidden": "FORBIDDEN",
    "Bake already in progress": "BAKE_ALREADY_IN_PROGRESS",
    "Job name is required": "MISSING_JOB_NAME",
    "audio extraction timed out": "AUDIO_EXTRACTION_TIMED_OUT",
    "audio extraction failed": "AUDIO_EXTRACTION_FAILED",
    "audio_delay must be 0-10 seconds": "INVALID_AUDIO_DELAY",
    "could not determine source duration": "SOURCE_DURATION_UNAVAILABLE",
    "cue id is required": "MISSING_CUE_ID",
    "cue id required in path": "MISSING_CUE_ID",
    "source_path is required": "MISSING_SOURCE_PATH",
    "mp4_path is required": "MISSING_MP4_PATH",
    "body must be JSON object": "INVALID_REQUEST_BODY",
    "WaveSpeed client not configured": "WAVESPEED_NOT_CONFIGURED",
    "WaveSpeed client not configured (missing API key)": "WAVESPEED_NOT_CONFIGURED",
    "'speaker' must be a string": "INVALID_SPEAKER",
    "'speaker' must be a non-empty string": "INVALID_SPEAKER",
    "'text' must be a string": "INVALID_TEXT",
    "ffmpeg timed out (>60s)": "FFMPEG_TIMED_OUT",
    "ffmpeg blend timed out (>300s)": "FFMPEG_BLEND_TIMED_OUT",
    "ffmpeg loudnorm timed out (>600s)": "FFMPEG_LOUDNORM_TIMED_OUT",
    "ffmpeg SFX mix timed out": "FFMPEG_SFX_MIX_TIMED_OUT",
    "event_changed_mid_job": "EVENT_CHANGED_MID_JOB",
}


def auto_error_code(msg: str) -> str:
    """Heuristic: derive SCREAMING_SNAKE error_code from message text.

    Drops punctuation, keeps first ~5 word-chars groups, uppercases. Aimed at
    making the code distinguishable in client logs without inventing semantics.
    """
    words = re.findall(r"[A-Za-z][A-Za-z0-9]*", msg)
    if not words:
        return "GENERIC_ERROR"
    code = "_".join(words[:5]).upper()
    if not code:
        return "GENERIC_ERROR"
    return code


def status_to_retry_safe(status: int) -> bool:
    """V59 convention: 5xx retryable (server transient), 4xx not (client must fix request).

    Specific overrides: 504 (timeout) yes, 503 yes, 502 yes, 500 yes.
    409 (conflict — scope mismatch class) is retry_safe=False.
    """
    if 500 <= status < 600:
        return True
    return False


class SiteFinder(ast.NodeVisitor):
    """Walks AST and collects all `<X>._send_json(<status_int>, {"error": ...})` Call nodes."""

    def __init__(self) -> None:
        self.sites: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "_send_json"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, int)
            and 400 <= node.args[0].value < 600
            and isinstance(node.args[1], ast.Dict)
        ):
            # Confirm the dict has an "error" key
            keys = node.args[1].keys
            has_error_key = any(
                isinstance(k, ast.Constant) and k.value == "error" for k in keys
            )
            if has_error_key:
                self.sites.append(node)
        self.generic_visit(node)


def site_message_literal(d: ast.Dict) -> str | None:
    """Return the string literal for the 'error' key if it's a Constant str; else None."""
    for k, v in zip(d.keys, d.values):
        if isinstance(k, ast.Constant) and k.value == "error":
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                return v.value
            return None
    return None


def render_node(src: str, node: ast.AST) -> str:
    """Slice source by node offsets and return the exact text."""
    return ast.get_source_segment(src, node) or ""


def build_replacement(src: str, call: ast.Call) -> tuple[int, int, str]:
    """Return (start_offset, end_offset, replacement_text) for the Call node."""
    assert isinstance(call.func, ast.Attribute)
    receiver = call.func.value  # h or self (could be Name or Attribute)
    receiver_text = render_node(src, receiver)
    status_node = call.args[0]
    status = status_node.value  # type: ignore[union-attr]
    err_dict = call.args[1]
    assert isinstance(err_dict, ast.Dict)

    # Extract error_message AST text + collect extras (any non-"error" keys).
    # Each extra slot is either ("key_repr", "value_repr") for a normal kv pair,
    # or (None, "value_repr") for a `**unpack` entry. None signals to emit
    # `**<value>` rather than `<key>: <value>`.
    err_msg_text: str | None = None
    extra_keys: list[tuple[str | None, str]] = []
    for k, v in zip(err_dict.keys, err_dict.values):
        if isinstance(k, ast.Constant) and k.value == "error":
            err_msg_text = render_node(src, v)
            continue
        val_text = render_node(src, v)
        if k is None:
            extra_keys.append((None, val_text))
        else:
            key_text = render_node(src, k)
            extra_keys.append((key_text, val_text))

    if err_msg_text is None:
        # Should not happen because SiteFinder filtered, but be defensive
        return (call.col_offset, call.end_col_offset, render_node(src, call))

    # Determine error_code
    literal_msg = site_message_literal(err_dict)
    if literal_msg is not None:
        error_code = PHRASE_MAP.get(literal_msg) or auto_error_code(literal_msg)
    else:
        # Non-literal (f-string, concat, str(exc), etc.) — use generic
        error_code = "GENERIC_ERROR"

    retry_safe = status_to_retry_safe(int(status))

    # Compute leading indent so the rewritten call is readable inline
    # We use the column offset of the original call as the base.
    base_col = call.col_offset
    arg_indent = " " * (base_col + 4)
    close_indent = " " * base_col

    parts: list[str] = []
    parts.append(f"{receiver_text}._send_error_v59(")
    parts.append(f"\n{arg_indent}{status},")
    parts.append(f"\n{arg_indent}error_code=\"{error_code}\",")
    parts.append(f"\n{arg_indent}error_message={err_msg_text},")
    parts.append(f"\n{arg_indent}retry_safe={retry_safe},")
    if extra_keys:
        parts_extra: list[str] = []
        for k, v in extra_keys:
            if k is None:
                parts_extra.append(f"**{v}")
            else:
                parts_extra.append(f"{k}: {v}")
        extra_inner = ", ".join(parts_extra)
        parts.append(f"\n{arg_indent}extra={{{extra_inner}}},")
    parts.append(f"\n{close_indent})")

    replacement = "".join(parts)

    # Compute byte offsets in `src` for the entire Call node
    start = node_offset(src, call.lineno, call.col_offset)
    end = node_offset(src, call.end_lineno, call.end_col_offset)
    return (start, end, replacement)


def node_offset(src: str, lineno: int, col_offset: int) -> int:
    """Convert (1-indexed line, 0-indexed UTF-8 BYTE col) to absolute codepoint offset.

    Python AST `col_offset` / `end_col_offset` are UTF-8 byte offsets within the
    line, NOT codepoint offsets. Lines that contain multi-byte chars (e.g. ≥, ≤,
    em-dash) need byte→codepoint translation when slicing the source string.
    """
    line_starts_cp = [0]
    for i, ch in enumerate(src):
        if ch == "\n":
            line_starts_cp.append(i + 1)
    line_start_cp = line_starts_cp[lineno - 1]
    # Find the line text (up to the next \n)
    nl = src.find("\n", line_start_cp)
    line_text = src[line_start_cp:nl] if nl != -1 else src[line_start_cp:]
    # Translate byte col_offset within the line to codepoint offset within the line
    line_bytes = line_text.encode("utf-8")
    if col_offset > len(line_bytes):
        # End-col-offset may equal line length (pointing at the \n)
        return line_start_cp + len(line_text)
    byte_slice = line_bytes[:col_offset]
    cp_in_line = len(byte_slice.decode("utf-8"))
    return line_start_cp + cp_in_line


def migrate_file(path: Path, dry_run: bool = True) -> tuple[int, int]:
    """Returns (sites_found, sites_migrated)."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    finder = SiteFinder()
    finder.visit(tree)
    sites = finder.sites
    if not sites:
        return (0, 0)

    # Sort descending by end offset so we rewrite from bottom up (offsets stay valid)
    edits: list[tuple[int, int, str]] = []
    for call in sites:
        start, end, repl = build_replacement(src, call)
        edits.append((start, end, repl))
    edits.sort(key=lambda e: e[0], reverse=True)

    new_src = src
    for start, end, repl in edits:
        new_src = new_src[:start] + repl + new_src[end:]

    # Verify the new source parses
    try:
        ast.parse(new_src, filename=str(path))
    except SyntaxError as e:
        print(f"  SYNTAX ERROR after migration of {path.name}: {e}", file=sys.stderr)
        return (len(sites), 0)

    if not dry_run:
        path.write_text(new_src, encoding="utf-8")

    return (len(sites), len(edits))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    ap.add_argument("--file", type=str, help="Migrate a single file (relative or absolute)")
    args = ap.parse_args()

    dry_run = not args.apply
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[{mode}] V59 Phase 7 mass error-shape migration")

    if args.file:
        targets = [Path(args.file).resolve()]
    else:
        targets = [PRODUCTION_SERVER]
        targets.extend(sorted(SERVER_HANDLERS_DIR.glob("*.py")))

    total_found = 0
    total_migrated = 0
    for target in targets:
        if not target.is_file():
            continue
        found, migrated = migrate_file(target, dry_run=dry_run)
        if found:
            try:
                rel = target.relative_to(ROOT)
            except ValueError:
                rel = target
            print(f"  {rel}: {migrated}/{found} migrated")
            total_found += found
            total_migrated += migrated

    print(f"\nTotal: {total_migrated}/{total_found} sites migrated")
    return 0 if total_migrated == total_found else 1


if __name__ == "__main__":
    raise SystemExit(main())
