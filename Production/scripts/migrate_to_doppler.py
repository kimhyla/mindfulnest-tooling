#!/usr/bin/env python3
"""
WA-C14 Doppler migration — batch redaction of hardcoded API keys.

Per LD-208 RENT_DOPPLER_SECRETS. Preflight row 51, task_id wa-c14-doppler-migration-20260418.

Behavior:
  * For .py files: replace hardcoded key literals with credential_store.get_secret("ENV_NAME")
    calls. Prepend boilerplate that adds Production/ to sys.path so `from lib.credential_store
    import get_secret` works from any depth.
  * For .html/.json/.txt/.md/.sh files: replace hardcoded key literals with a
    `<REDACTED_PER_LD208_USE_DOPPLER>` placeholder. Adds a top-of-file comment where feasible.
  * Skips Production/API_KEYS_MASTER.md (canonical source, archived separately)
  * Skips Production/lib/credential_store.py (the migration helper itself)
  * Skips Production/scripts/migrate_to_doppler.py (this script)
  * Verifies each Python file remains syntactically valid (ast.parse) after edit.
  * Dry-run mode prints planned changes without writing.

Usage:
    python3 Production/scripts/migrate_to_doppler.py --dry-run
    python3 Production/scripts/migrate_to_doppler.py --execute
"""
from __future__ import annotations
import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PRODUCTION_DIR = PROJECT_ROOT / "Production"

# Label -> env var name. Include the FULL key literal for matching.
SECRETS: list[tuple[str, str, str]] = [
    # (env_var_name, key_literal, human_label)
    ("ELEVENLABS_API_KEY",      "<REDACTED:elevenlabs_full:2026-04-22>", "ElevenLabs"),
    ("RUNWAY_API_KEY",          "<REDACTED:runway_full:2026-04-22>", "Runway"),
    ("WAVESPEED_API_KEY",       "<REDACTED:wavespeed_full:2026-04-22>", "WaveSpeed"),
    ("BFL_API_KEY",             "<REDACTED:bfl_full:2026-04-22>", "BFL Flux Kontext"),
    ("FAL_KEY",                 "<REDACTED:fal_full:2026-04-22>", "fal.ai"),
    ("REPLICATE_API_TOKEN",     "<REDACTED:replicate_full:2026-04-22>", "Replicate"),
    ("SEGMIND_API_KEY",         "<REDACTED:segmind_full:2026-04-22>", "Segmind"),
    ("EVOLINK_API_KEY",         "<REDACTED:evolink_full:2026-04-22>", "EvoLink"),
    ("GEMINI_API_KEY",          "<REDACTED:gemini_full:2026-04-22>", "Gemini"),
    ("OPENAI_API_KEY",          "<REDACTED:openai_full:2026-04-22>_RtlxG-T3BlbkFJ1HcksxNHzxpVaB7nbqE1KorgTmcgNuesy9jxQgF_1aoKbin9G_JYNF7u3SOYLQ2-Z_XZrVCjsA", "OpenAI"),
]

# Files to NEVER touch (handled separately or are tooling)
SKIP_PATHS: set[Path] = {
    PRODUCTION_DIR / "API_KEYS_MASTER.md",
    PRODUCTION_DIR / "lib" / "credential_store.py",
    PRODUCTION_DIR / "scripts" / "migrate_to_doppler.py",
}

PY_BOILERPLATE = '''# --- WA-C14 Doppler migration (per LD-208) ---
# credential_store reads from Doppler env vars first, falls back to API_KEYS_MASTER.md.
import os as _os, sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve()
while _p.parent != _p and _p.name != "Production":
    _p = _p.parent
if _p.name == "Production":
    _sys.path.insert(0, str(_p))
from lib.credential_store import get_secret  # noqa: E402
# --- end WA-C14 boilerplate ---
'''

REDACTION_PLACEHOLDER = "<REDACTED_PER_LD208_USE_DOPPLER>"


@dataclass
class FileChange:
    path: Path
    file_kind: str  # "python" | "html" | "json" | "markdown" | "shell" | "text"
    replacements: list[tuple[str, str, str]]  # (env_var, before_snippet, after_snippet)
    boilerplate_added: bool
    syntax_ok: bool
    error: str | None = None


def classify(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".py":
        return "python"
    if suf in (".html", ".htm"):
        return "html"
    if suf == ".json":
        return "json"
    if suf in (".md", ".markdown"):
        return "markdown"
    if suf in (".sh", ".command"):
        return "shell"
    return "text"


def find_target_files() -> list[Path]:
    """Walk Production/ and return files containing any hardcoded key literal."""
    targets: set[Path] = set()
    for env, literal, _ in SECRETS:
        for path in PRODUCTION_DIR.rglob("*"):
            if not path.is_file():
                continue
            if path in SKIP_PATHS:
                continue
            if any(part.startswith(".") for part in path.parts):
                continue  # hidden dirs (like .git if any)
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if literal in content:
                targets.add(path)
    return sorted(targets)


def migrate_python(path: Path, dry_run: bool) -> FileChange:
    content = path.read_text(encoding="utf-8")
    original = content
    replacements: list[tuple[str, str, str]] = []

    for env_var, literal, label in SECRETS:
        if literal not in content:
            continue
        # Replace occurrences inside string literals with get_secret(ENV_VAR)
        # We handle two common patterns:
        #  1. "LITERAL" as a Python string literal  -> get_secret("ENV")
        #  2. 'LITERAL' as a Python string literal  -> get_secret("ENV")
        before = f'"{literal}"'
        after = f'get_secret("{env_var}")'
        if before in content:
            count = content.count(before)
            content = content.replace(before, after)
            replacements.append((env_var, f'"{literal[:10]}..."', f'get_secret("{env_var}")  # x{count}'))

        before_sq = f"'{literal}'"
        after_sq = f'get_secret("{env_var}")'
        if before_sq in content:
            count = content.count(before_sq)
            content = content.replace(before_sq, after_sq)
            replacements.append((env_var, f"'{literal[:10]}...'", f'get_secret("{env_var}")  # x{count}'))

        # Bare literal as unquoted token (rare in code, common in prose) — only replace if still present
        if literal in content:
            count = content.count(literal)
            content = content.replace(literal, REDACTION_PLACEHOLDER)
            replacements.append((env_var, f'{literal[:10]}... (bare)', f'{REDACTION_PLACEHOLDER}  # x{count}'))

    boilerplate_added = False
    # Inject boilerplate if we made any get_secret replacements and it's not already present
    if any("get_secret" in r[2] for r in replacements) and "from lib.credential_store import get_secret" not in content:
        # Find insertion point: after the module docstring (if any) and any `from __future__` imports
        tree_ok = True
        try:
            tree = ast.parse(original)
        except SyntaxError:
            tree_ok = False
        insertion_line = 0
        if tree_ok:
            body = tree.body
            # Skip docstring
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                insertion_line = body[0].end_lineno or 0
            # Skip from __future__ imports
            for node in body:
                if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                    insertion_line = max(insertion_line, node.end_lineno or 0)
            lines = content.splitlines(keepends=True)
            if 0 <= insertion_line <= len(lines):
                lines.insert(insertion_line, "\n" + PY_BOILERPLATE)
                content = "".join(lines)
                boilerplate_added = True
        else:
            # File already broken — prepend at top
            content = PY_BOILERPLATE + "\n" + content
            boilerplate_added = True

    syntax_ok = True
    error = None
    if replacements:
        try:
            ast.parse(content)
        except SyntaxError as e:
            syntax_ok = False
            error = f"Post-migration SyntaxError: {e}"

    if replacements and not dry_run and syntax_ok:
        path.write_text(content, encoding="utf-8")

    return FileChange(path, "python", replacements, boilerplate_added, syntax_ok, error)


def migrate_nonpy(path: Path, kind: str, dry_run: bool) -> FileChange:
    content = path.read_text(encoding="utf-8")
    replacements: list[tuple[str, str, str]] = []

    for env_var, literal, label in SECRETS:
        if literal in content:
            count = content.count(literal)
            content = content.replace(literal, REDACTION_PLACEHOLDER)
            replacements.append((env_var, f"{literal[:10]}... x{count}", REDACTION_PLACEHOLDER))

    if replacements and not dry_run:
        path.write_text(content, encoding="utf-8")

    return FileChange(path, kind, replacements, boilerplate_added=False, syntax_ok=True)


def migrate_one(path: Path, dry_run: bool) -> FileChange:
    kind = classify(path)
    if kind == "python":
        return migrate_python(path, dry_run)
    return migrate_nonpy(path, kind, dry_run)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    dry_run = args.dry_run

    targets = find_target_files()
    print(f"Found {len(targets)} files with hardcoded keys.")
    print(f"Mode: {'DRY-RUN (no writes)' if dry_run else 'EXECUTE (writing changes)'}")
    print()

    results: list[FileChange] = []
    for path in targets:
        try:
            fc = migrate_one(path, dry_run)
        except Exception as e:
            fc = FileChange(path, classify(path), [], False, False, error=f"Exception: {e!r}")
        results.append(fc)

    by_kind: dict[str, list[FileChange]] = {}
    for fc in results:
        by_kind.setdefault(fc.file_kind, []).append(fc)

    for kind, group in by_kind.items():
        print(f"--- {kind.upper()} ({len(group)} files) ---")
        for fc in group:
            rel = fc.path.relative_to(PROJECT_ROOT)
            total_subs = sum(int(r[2].rsplit("x", 1)[-1]) if "x" in r[2] else 1 for r in fc.replacements)
            status = "OK" if fc.syntax_ok and fc.error is None else f"FAIL: {fc.error}"
            boil = " [+boilerplate]" if fc.boilerplate_added else ""
            print(f"  {rel}  {total_subs} substitutions{boil}  [{status}]")
        print()

    fails = [fc for fc in results if not fc.syntax_ok or fc.error]
    if fails:
        print(f"*** {len(fails)} FILES FAILED — rolling back any writes is on you. Re-run --dry-run to inspect.")
        for fc in fails:
            print(f"    {fc.path.relative_to(PROJECT_ROOT)}: {fc.error}")
        return 2

    total = sum(sum(int(r[2].rsplit('x', 1)[-1]) if 'x' in r[2] else 1 for r in fc.replacements) for fc in results)
    print(f"Total substitutions: {total} across {len(results)} files.")
    if dry_run:
        print("Dry-run complete. Re-run with --execute to apply.")
    else:
        print("Execute complete. Verify with: grep -rln '11f1c7afb99b25f' Production | grep -v ARCHIVED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
