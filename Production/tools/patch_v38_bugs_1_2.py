#!/usr/bin/env python3
"""
Bugfix bundle — Path B (JS-only) patcher for BROWSER_TEST_RESULTS_20260418.md bugs #1 and #2.

Bug 1 (MEDIUM): pathappPatch uses a lexical closure reference to pathappSetSaveInd.
  The Phase 1.5 toast wrapper monkey-patches window.pathappSetSaveInd, but the 6 internal
  call sites inside pathappPatch captured the original function at IIFE init time and
  never see the monkey-patched version. Green success toast never fires.
  Fix: rewrite the 6 call sites to use window.pathappSetSaveInd(...) for late binding.

Bug 2 (MEDIUM-HIGH): options.skip_tts_regen accepted by pathappPatch but never forwarded
  to the POST body. Server honors it at production_server.py:4952 but the flag never
  reaches the server. [pause] tag clicks on lipsynced beats trigger unintended TTS regen.
  Fix: after body construction, if options.skip_tts_regen is truthy, copy it to body.

Discipline (Rule 7 Path B — behavior-only):
  1. Read HTML as text.
  2. Extract all base64 data URIs + SHA256 hash each one, pre-patch.
  3. Apply 6 call-site replacements for Bug 1 (precise anchored strings).
  4. Apply 1 body-construction edit for Bug 2.
  5. Extract base64 data URIs + SHA256 hash each one, post-patch.
  6. ASSERT every image's SHA256 is byte-identical. FAIL LOUDLY if not.
  7. Write timestamped backup BEFORE overwriting.
  8. Re-read from disk and verify static checks.

This patcher does NOT rebuild. It does NOT touch images. It does NOT regenerate HTML.
It surgically rewrites a handful of identifiers + adds 1 line of JS.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Absolute paths.
PROJECT_ROOT = Path(
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
)
HTML_PATH = PROJECT_ROOT / "Production" / "Event_1" / "storyboard_v38_prod.html"

# ------------------------------------------------------------------
# Bug 1 — 6 call-site replacements inside pathappPatch.
# Each old_string is anchored with enough surrounding context to be unique
# in the whole file (we'll assert count==1 before replacing).
# ------------------------------------------------------------------
BUG1_REPLACEMENTS = [
    # line 1896 — initial "saving" indicator
    (
        '    var indSpan = options.saveind || null;\n'
        '    pathappSetSaveInd(indSpan, "saving", "saving...");\n',
        '    var indSpan = options.saveind || null;\n'
        '    window.pathappSetSaveInd(indSpan, "saving", "saving...");\n',
    ),
    # line 1905 — 503 rollback mode
    (
        '        // Rollback mode — fall back to legacy\n'
        '        pathappSetSaveInd(indSpan, "error", "legacy mode");\n',
        '        // Rollback mode — fall back to legacy\n'
        '        window.pathappSetSaveInd(indSpan, "error", "legacy mode");\n',
    ),
    # line 1913 — 409 conflict
    (
        '      if (resp.status === 409) {\n'
        '        pathappSetSaveInd(indSpan, "error", "conflict - reload");\n',
        '      if (resp.status === 409) {\n'
        '        window.pathappSetSaveInd(indSpan, "error", "conflict - reload");\n',
    ),
    # line 1918 — !resp.ok error
    (
        '      if (!resp.ok) {\n'
        '        pathappSetSaveInd(indSpan, "error", "error " + resp.status);\n',
        '      if (!resp.ok) {\n'
        '        window.pathappSetSaveInd(indSpan, "error", "error " + resp.status);\n',
    ),
    # line 1924 — success "saved"
    (
        '      }\n'
        '      pathappSetSaveInd(indSpan, "saved", "saved");\n'
        '      setTimeout(function() {\n',
        '      }\n'
        '      window.pathappSetSaveInd(indSpan, "saved", "saved");\n'
        '      setTimeout(function() {\n',
    ),
    # line 1933 — catch network error
    (
        '    } catch (e) {\n'
        '      pathappSetSaveInd(indSpan, "error", "network error");\n',
        '    } catch (e) {\n'
        '      window.pathappSetSaveInd(indSpan, "error", "network error");\n',
    ),
]

# ------------------------------------------------------------------
# Bug 2 — skip_tts_regen forward.
# Anchor on the body construction closing brace + the following expectedVersion
# block so the insertion point is unambiguous.
# ------------------------------------------------------------------
BUG2_OLD = (
    '    var body = {\n'
    '      field: field,\n'
    '      value: value,\n'
    '      mutation_id: mutationId,\n'
    '    };\n'
    '    var expectedVersion = BEAT_VERSIONS[beatId];\n'
)
BUG2_NEW = (
    '    var body = {\n'
    '      field: field,\n'
    '      value: value,\n'
    '      mutation_id: mutationId,\n'
    '    };\n'
    '    if (options && options.skip_tts_regen) body.skip_tts_regen = true;\n'
    '    var expectedVersion = BEAT_VERSIONS[beatId];\n'
)


# ------------------------------------------------------------------
# Helpers.
# ------------------------------------------------------------------

def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


BASE64_URI_PATTERN = re.compile(r'data:image/[^;,\s"]+;base64,([A-Za-z0-9+/=]+)')


def _base64_per_image_shas(html: str) -> dict:
    """Return {index: sha256} for every base64 image data URI in the file.

    Byte-identical verification is per-image, not per-bulk-concat — any single
    image payload changing must trigger an abort.
    """
    shas = {}
    for i, m in enumerate(BASE64_URI_PATTERN.finditer(html)):
        payload = m.group(1)
        shas[i] = hashlib.sha256(payload.encode("ascii")).hexdigest()
    return shas


def _assert_unique(text: str, needle: str, label: str) -> None:
    count = text.count(needle)
    if count != 1:
        raise SystemExit(
            f"ABORT: expected exactly 1 occurrence of {label}, found {count}.\n"
            f"First 200 chars of needle: {needle[:200]!r}"
        )


def _count_pathappPatch_scope_calls(html: str) -> dict:
    """Scope the pathappSetSaveInd call counts to inside the pathappPatch function body only.

    Uses the function header 'async function pathappPatch' and scans until the
    matching close of the function (the line '  }' immediately before
    '  // Expose for manual console use').
    """
    header = 'async function pathappPatch(beatId, field, value, options)'
    idx = html.find(header)
    if idx < 0:
        raise SystemExit("ABORT: cannot find pathappPatch function header.")
    # End of function: the line 'window.pathappPatch = pathappPatch;' is the
    # first line after the closing brace in the IIFE.
    end_marker = 'window.pathappPatch = pathappPatch;'
    end_idx = html.find(end_marker, idx)
    if end_idx < 0:
        raise SystemExit("ABORT: cannot find end of pathappPatch (window.pathappPatch assignment).")
    fn_body = html[idx:end_idx]
    return {
        "window.pathappSetSaveInd(": fn_body.count("window.pathappSetSaveInd("),
        "bare pathappSetSaveInd(": fn_body.count("pathappSetSaveInd(") - fn_body.count("window.pathappSetSaveInd("),
        "body.skip_tts_regen": fn_body.count("body.skip_tts_regen"),
        "fn_body_len": len(fn_body),
    }


# ------------------------------------------------------------------
# Main patch flow.
# ------------------------------------------------------------------

def main() -> int:
    print(f"[bugs_1_2] Reading: {HTML_PATH}")
    original = HTML_PATH.read_text(encoding="utf-8")
    original_size = len(original)

    # Pre-check: refuse to double-patch Bug 2.
    if 'body.skip_tts_regen = true' in original:
        raise SystemExit(
            "ABORT: body.skip_tts_regen = true already present — "
            "refusing to double-patch (Bug 2 already fixed)."
        )

    # Pre-check: anchor uniqueness for all 7 replacements.
    for i, (old, _new) in enumerate(BUG1_REPLACEMENTS, 1):
        _assert_unique(original, old, f"Bug1 anchor #{i}")
    _assert_unique(original, BUG2_OLD, "Bug2 body-construction anchor")

    # Pre-patch scope count.
    scope_before = _count_pathappPatch_scope_calls(original)
    print(f"[bugs_1_2] pathappPatch scope (BEFORE): {scope_before}")
    if scope_before["bare pathappSetSaveInd("] != 6:
        raise SystemExit(
            f"ABORT: expected exactly 6 bare pathappSetSaveInd( in pathappPatch scope, "
            f"found {scope_before['bare pathappSetSaveInd(']}. File may already be patched "
            f"or has drifted from the expected layout."
        )
    if scope_before["window.pathappSetSaveInd("] != 0:
        raise SystemExit(
            f"ABORT: expected 0 window.pathappSetSaveInd( in pathappPatch scope before patch, "
            f"found {scope_before['window.pathappSetSaveInd(']}. File may be partially patched."
        )
    if scope_before["body.skip_tts_regen"] != 0:
        raise SystemExit(
            f"ABORT: expected 0 body.skip_tts_regen in pathappPatch scope before patch, "
            f"found {scope_before['body.skip_tts_regen']}."
        )

    # Per-image SHA before.
    shas_before = _base64_per_image_shas(original)
    print(f"[bugs_1_2] base64 images before: n={len(shas_before)}")

    # Apply Bug 1 patches (6 replacements).
    patched = original
    applied_bug1 = 0
    for i, (old, new) in enumerate(BUG1_REPLACEMENTS, 1):
        before_count = patched.count(old)
        if before_count != 1:
            raise SystemExit(
                f"ABORT mid-patch: Bug1 anchor #{i} no longer unique (count={before_count}). "
                f"Aborting without writing. Disk file unchanged."
            )
        patched = patched.replace(old, new, 1)
        applied_bug1 += 1

    # Apply Bug 2 patch.
    before_count = patched.count(BUG2_OLD)
    if before_count != 1:
        raise SystemExit(
            f"ABORT mid-patch: Bug2 anchor no longer unique (count={before_count})."
        )
    patched = patched.replace(BUG2_OLD, BUG2_NEW, 1)

    # Post-patch per-image SHA verify.
    shas_after = _base64_per_image_shas(patched)
    if len(shas_before) != len(shas_after):
        raise SystemExit(
            f"ABORT: base64 image count changed from {len(shas_before)} to {len(shas_after)}. "
            f"Disk file unchanged."
        )
    mismatches = [i for i in shas_before if shas_before[i] != shas_after.get(i)]
    if mismatches:
        raise SystemExit(
            f"ABORT: base64 image SHA mismatch at indices {mismatches[:5]}... "
            f"Disk file unchanged."
        )
    print(f"[bugs_1_2] base64 per-image SHA verify: {len(shas_after)} images, ALL byte-identical")

    # Post-patch scope count check (in-memory).
    scope_after = _count_pathappPatch_scope_calls(patched)
    print(f"[bugs_1_2] pathappPatch scope (AFTER):  {scope_after}")
    if scope_after["window.pathappSetSaveInd("] != 6:
        raise SystemExit(
            f"ABORT: after patch, expected 6 window.pathappSetSaveInd( in scope, "
            f"found {scope_after['window.pathappSetSaveInd(']}."
        )
    if scope_after["bare pathappSetSaveInd("] != 0:
        raise SystemExit(
            f"ABORT: after patch, expected 0 bare pathappSetSaveInd( in scope, "
            f"found {scope_after['bare pathappSetSaveInd(']}."
        )
    if scope_after["body.skip_tts_regen"] != 1:
        raise SystemExit(
            f"ABORT: after patch, expected 1 body.skip_tts_regen, "
            f"found {scope_after['body.skip_tts_regen']}."
        )

    # Backup BEFORE overwriting.
    ts = _utc_ts()
    backup_path = HTML_PATH.with_name(f"{HTML_PATH.name}.bak_bugs_1_2_{ts}")
    print(f"[bugs_1_2] Writing backup: {backup_path}")
    shutil.copy2(HTML_PATH, backup_path)

    # Write patched file.
    HTML_PATH.write_text(patched, encoding="utf-8")
    new_size = len(patched)
    print(
        f"[bugs_1_2] Wrote {HTML_PATH}  "
        f"({original_size:,} -> {new_size:,} bytes, +{new_size - original_size:,})"
    )

    # Re-read and re-verify from disk.
    redisk = HTML_PATH.read_text(encoding="utf-8")
    shas_redisk = _base64_per_image_shas(redisk)
    mismatches = [i for i in shas_before if shas_before[i] != shas_redisk.get(i)]
    if mismatches:
        shutil.copy2(backup_path, HTML_PATH)
        raise SystemExit(
            f"ABORT: on-disk base64 SHA mismatch at {mismatches[:5]}... restored from backup."
        )
    scope_disk = _count_pathappPatch_scope_calls(redisk)
    if scope_disk != scope_after:
        shutil.copy2(backup_path, HTML_PATH)
        raise SystemExit(
            f"ABORT: on-disk scope counts drift from in-memory. "
            f"memory={scope_after}, disk={scope_disk}. Restored from backup."
        )
    print(f"[bugs_1_2] on-disk re-verify: PASS (scope + per-image SHA identical)")

    # Summary.
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "file": str(HTML_PATH),
        "backup": str(backup_path),
        "original_size_bytes": original_size,
        "patched_size_bytes": new_size,
        "bytes_delta": new_size - original_size,
        "bug1_call_sites_modified": applied_bug1,
        "bug2_body_skip_tts_regen_added": True,
        "base64_images_count": len(shas_before),
        "base64_identical": True,
        "pathappPatch_scope_before": scope_before,
        "pathappPatch_scope_after": scope_after,
    }
    print("\n[bugs_1_2] SUMMARY:")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
