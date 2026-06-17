#!/usr/bin/env python3
"""LD-O3-DUAL-ROOT-PARITY-V1 — fail if tooling and Dropbox critical files diverge."""
from __future__ import annotations
import hashlib, os, sys
from pathlib import Path

CODE_PARITY_PATHS = (
    "Production/tools/beat_generator.py",
    "Production/tools/beat_extract_policy.py",
    "Production/tools/claude_extract_beats.py",
    "Production/tools/kling_o3_prompt.py",
    "Production/tools/ken_burns_render.py",
    "Production/tools/kling_character_registry.py",
    "Production/tools/magic_compositor.py",
    "Production/tools/magic_render_contract.py",
    "Production/tools/server_handlers/background.py",
    "Production/tools/server_handlers/cropper.py",
    "Production/tools/production_server.py",
    "Production/tools/kling_o3_element_beat_pipeline.py",
    "Production/tools/arlo_o3_voice_pipeline.py",
    "Production/tools/server_handlers/background.py",
    "Production/tools/server_handlers/kling_o3.py",
    "Production/tools/kling_o3_job_store.py",
    "Production/tools/teleport_intro_kit.py",
    "Production/tools/teleport_intro_canonical.py",
    "Production/tools/credentials_lib/ffmpeg_stitch.py",
    "Production/tools/server_handlers/stitch_editor.py",
    "Production/tools/o3_job_status_contract.py",
    "Production/tools/o3_generation_intent.py",
    "Production/scripts/verify_tooling_dropbox_parity.py",
    "Production/scripts/verify_o3_intro_contract.sh",
    "Production/scripts/verify_visible_magic_contract.sh",
    "Production/scripts/post_tooling_change_smoke.sh",
    "Production/scripts/verify_lorelai_element_name_durability.sh",
)
REGISTRY_COMPARE_PATHS = (
    "Production/character_subjects.json",
    "Production/canonical_image_registry.json",
    "Production/lib/event_library.py",
)

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main() -> int:
    tooling = Path(os.environ.get("MN_TOOLING_ROOT", "/Users/kimberlysmith/Projects/mindfulnest-tooling"))
    dropbox = Path(os.environ.get("MN_DROPBOX_ROOT", "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"))
    code_mismatches, registry_mismatches, missing, verified = [], [], [], 0
    def _compare(rel, strict):
        nonlocal verified
        src, dst = tooling / rel, dropbox / rel
        if not src.is_file(): missing.append(f"missing tooling: {rel}"); return
        if not dst.is_file(): missing.append(f"missing dropbox: {rel}"); return
        s, d = _sha256(src), _sha256(dst)
        if s != d:
            block = f"{rel}\n  tooling: {s}\n  dropbox: {d}"
            (code_mismatches if strict else registry_mismatches).append(block)
        else:
            verified += 1; print(f"OK  {rel}  {s[:12]}…")
    for rel in CODE_PARITY_PATHS: _compare(rel, True)
    for rel in REGISTRY_COMPARE_PATHS: _compare(rel, False)
    if missing:
        print("\nMISSING:", file=sys.stderr)
        for line in missing: print(f"  {line}", file=sys.stderr)
    if registry_mismatches:
        print("\nREGISTRY DRIFT (warn — Dropbox is runtime source of truth):", file=sys.stderr)
        for block in registry_mismatches: print(f"  {block}", file=sys.stderr)
        if os.environ.get("MN_REGISTRY_PARITY_STRICT") == "1": code_mismatches.extend(registry_mismatches)
    if code_mismatches:
        print("\nSHA256 MISMATCH (tooling ≠ Dropbox):", file=sys.stderr)
        for block in code_mismatches: print(f"  {block}", file=sys.stderr)
        return 1
    if missing: return 1
    print(f"\nparity ok — {verified} critical file(s) match")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
