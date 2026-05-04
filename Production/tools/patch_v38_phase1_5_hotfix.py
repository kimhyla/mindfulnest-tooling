#!/usr/bin/env python3
"""
Phase 1.5 HOTFIX — April 18 2026 (task_id=phase-1.5-hotfix-20260418)

Fixes two bugs caught by Kim in browser validation ~30 min after Phase 1.5 shipped:

  Bug 1: No .save-ind DOM elements exist on page load.
         Phase 1.5 spans are created LAZILY on first widget interaction, so
         before Kim edits anything, `document.querySelectorAll('[class*="save-ind"]')`
         returns 0. Fix: inject a visible pre-created span per row after
         pathappHydrate completes, using class "save-ind pathapp-saveind" so
         both Kim's querySelector and the existing pulse CSS match.

  Bug 2: pathappPatch sends expected_version=0 when BEAT_VERSIONS[beatId] is
         undefined, causing the server to return 409 conflict for any beat
         with _version > 0. Fix: only include expected_version in the
         request body if the client actually has a known version for that
         beat. Server already handles `expected_version is None` correctly
         (patch_state line 2106, _handle_v2_patch line 4709).

Rule 7 Path B compliance: <script>/<style> edits only. Base64 data URIs
extracted, SHA256'd, asserted identical before/after. Backup preserved.
If any image-fingerprint drift, script restores backup and exits non-zero.

Does NOT modify Phase 1 pathappPatch signature or return shape — only the
body construction (conditional expected_version inclusion). Does NOT modify
the 5 wired widget handlers from Phase 1.5 — only augments hydration to
pre-create visible save-ind spans.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
V38 = PROJECT_ROOT / "Production" / "Event_1" / "storyboard_v38_prod.html"
TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
BACKUP = V38.with_suffix(f".html.bak_phase1_5_hotfix_{TS}")

DATA_URI_RE = re.compile(r"data:image/[a-zA-Z0-9.+-]+;base64,([A-Za-z0-9+/=]+)")


def base64_fingerprints(text: str) -> list[str]:
    payloads = DATA_URI_RE.findall(text)
    hashes = [hashlib.sha256(p.encode("ascii")).hexdigest() for p in payloads]
    hashes.sort()
    return hashes


# -----------------------------------------------------------------------------
# FIX 1: Bug 2 — pathappPatch must omit expected_version when unknown.
# -----------------------------------------------------------------------------
# Exact Phase 1 block to replace (lines 1880-1887 of current v38):
#
#     var expectedVersion = BEAT_VERSIONS[beatId];
#     if (expectedVersion === undefined) expectedVersion = 0;
#     var body = {
#       field: field,
#       value: value,
#       mutation_id: mutationId,
#       expected_version: expectedVersion,
#     };
#
# Replacement omits expected_version entirely when BEAT_VERSIONS[beatId] is
# undefined OR when options.skipVersionCheck is true. Server treats missing
# expected_version as "apply unconditionally" (patch_state line 2106).

PATHAPP_VERSION_OLD = (
    '    var expectedVersion = BEAT_VERSIONS[beatId];\n'
    '    if (expectedVersion === undefined) expectedVersion = 0;\n'
    '    var body = {\n'
    '      field: field,\n'
    '      value: value,\n'
    '      mutation_id: mutationId,\n'
    '      expected_version: expectedVersion,\n'
    '    };'
)

PATHAPP_VERSION_NEW = (
    '    // HOTFIX 20260418: only send expected_version if caller or hydrate\n'
    '    // populated BEAT_VERSIONS[beatId]. Missing => server applies\n'
    '    // unconditionally (no optimistic check).\n'
    '    var body = {\n'
    '      field: field,\n'
    '      value: value,\n'
    '      mutation_id: mutationId,\n'
    '    };\n'
    '    var expectedVersion = BEAT_VERSIONS[beatId];\n'
    '    if (options && options.expected_version !== undefined) {\n'
    '      body.expected_version = options.expected_version;\n'
    '    } else if (expectedVersion !== undefined && expectedVersion !== null) {\n'
    '      body.expected_version = expectedVersion;\n'
    '    }\n'
    '    // else: omit field entirely -> server skips version check.'
)


# -----------------------------------------------------------------------------
# FIX 2: Bug 1 — pre-create visible save-ind spans after hydrate.
# -----------------------------------------------------------------------------
# Injection point: immediately after `pathappHydrate();` calls on DOM-ready.
# We wrap the ready block so after hydrate + render, we walk every L[] entry
# and append a visible <span class="save-ind pathapp-saveind" data-beat-id=..>
# to the row element. Class "save-ind" (hyphenated) matches Kim's
# querySelectorAll('[class*="save-ind"]') query. Class "pathapp-saveind"
# ensures existing pulse/colour CSS applies on transitions.

HYDRATE_READY_OLD = (
    '  // Run hydration on DOM ready\n'
    '  if (document.readyState === "loading") {\n'
    '    document.addEventListener("DOMContentLoaded", pathappHydrate);\n'
    '  } else {\n'
    '    pathappHydrate();\n'
    '  }\n'
    '})();\n'
    '</script>'
)

HYDRATE_READY_NEW = (
    '  // HOTFIX 20260418: after hydrate, pre-create visible save-ind spans.\n'
    '  // Ensures `document.querySelectorAll("[class*=\\"save-ind\\"]").length > 0`\n'
    '  // on page load BEFORE any widget interaction.\n'
    '  async function pathappHydrateAndSeedIndicators() {\n'
    '    try { await pathappHydrate(); } catch (e) { console.warn("[hotfix] hydrate:", e); }\n'
    '    try { pathappSeedSaveIndicators(); } catch (e) { console.warn("[hotfix] seed:", e); }\n'
    '  }\n'
    '  function pathappSeedSaveIndicators() {\n'
    '    if (!window.L || !Array.isArray(window.L)) return;\n'
    '    var seeded = 0;\n'
    '    for (var i = 0; i < window.L.length; i++) {\n'
    '      var rowEl = document.getElementById("r" + i);\n'
    '      if (!rowEl) continue;\n'
    '      var beatId = "beat_" + String(i + 1).padStart(2, "0");\n'
    '      // Skip if a hotfix-seeded span already exists for this row.\n'
    '      if (rowEl.querySelector(\'.save-ind[data-beat-id="\' + beatId + \'"]\')) continue;\n'
    '      var span = document.createElement("span");\n'
    '      span.className = "save-ind pathapp-saveind";\n'
    '      span.setAttribute("data-beat-id", beatId);\n'
    '      span.setAttribute("data-field", "row");\n'
    '      span.textContent = "\\u25CB";  /* open circle = idle */\n'
    '      span.style.marginLeft = "8px";\n'
    '      span.style.display = "inline-block";\n'
    '      span.style.minWidth = "16px";\n'
    '      span.style.fontSize = "11px";\n'
    '      span.style.opacity = "0.55";\n'
    '      span.title = "save indicator (idle)";\n'
    '      rowEl.appendChild(span);\n'
    '      seeded += 1;\n'
    '    }\n'
    '    console.log("[hotfix] seeded", seeded, "save-ind spans");\n'
    '  }\n'
    '  // Expose so _pathappWire handlers can find the row-level span too.\n'
    '  window.pathappSeedSaveIndicators = pathappSeedSaveIndicators;\n'
    '\n'
    '  // Run hydration on DOM ready (+ seed save-ind spans after)\n'
    '  if (document.readyState === "loading") {\n'
    '    document.addEventListener("DOMContentLoaded", pathappHydrateAndSeedIndicators);\n'
    '  } else {\n'
    '    pathappHydrateAndSeedIndicators();\n'
    '  }\n'
    '})();\n'
    '</script>'
)


# -----------------------------------------------------------------------------
# FIX 3: Also have _ensureSaveInd tag spans with class "save-ind" (hyphenated)
# so widget-created spans match Kim's querySelector too. Preserves "pathapp-saveind"
# so existing pulse CSS continues to work.
# -----------------------------------------------------------------------------

ENSURESAVE_OLD = (
    '    span = document.createElement("span");\n'
    '    span.className = "pathapp-saveind";\n'
    '    span.setAttribute("data-pid", pid);\n'
    '    span.style.marginLeft = "6px";\n'
    '    parent.appendChild(span);\n'
    '    return span;\n'
    '  }'
)

ENSURESAVE_NEW = (
    '    span = document.createElement("span");\n'
    '    // HOTFIX 20260418: "save-ind" class added so `[class*="save-ind"]` matches.\n'
    '    span.className = "save-ind pathapp-saveind";\n'
    '    span.setAttribute("data-pid", pid);\n'
    '    span.setAttribute("data-beat-id", "beat_" + String(rowIdx + 1).padStart(2, "0"));\n'
    '    span.setAttribute("data-field", kind);\n'
    '    span.style.marginLeft = "6px";\n'
    '    parent.appendChild(span);\n'
    '    return span;\n'
    '  }'
)


# -----------------------------------------------------------------------------
# Orchestration
# -----------------------------------------------------------------------------

REPLACEMENTS = [
    ("pathapp_version_body", PATHAPP_VERSION_OLD, PATHAPP_VERSION_NEW),
    ("hydrate_ready_seed",  HYDRATE_READY_OLD,  HYDRATE_READY_NEW),
    ("ensuresave_class",    ENSURESAVE_OLD,     ENSURESAVE_NEW),
]


def main() -> int:
    if not V38.exists():
        print(f"FATAL: v38 not found at {V38}", file=sys.stderr)
        return 2

    original = V38.read_text(encoding="utf-8")

    before_hashes = base64_fingerprints(original)
    print(f"[hotfix] base64 image count BEFORE: {len(before_hashes)}")

    shutil.copyfile(V38, BACKUP)
    print(f"[hotfix] backup written: {BACKUP.name}")

    patched = original
    for name, old, new in REPLACEMENTS:
        count = patched.count(old)
        if count != 1:
            print(
                f"FATAL: replacement '{name}' matched {count} times (expected 1). "
                "Aborting. Backup preserved; v38 untouched.",
                file=sys.stderr,
            )
            return 3
        patched = patched.replace(old, new, 1)
        print(f"[hotfix] applied: {name}")

    after_hashes = base64_fingerprints(patched)
    print(f"[hotfix] base64 image count AFTER:  {len(after_hashes)}")

    if before_hashes != after_hashes:
        print(
            "FATAL: base64 image fingerprints differ before vs after. "
            "Restoring backup and aborting.",
            file=sys.stderr,
        )
        shutil.copyfile(BACKUP, V38)
        before_set = set(before_hashes)
        after_set = set(after_hashes)
        missing = before_set - after_set
        extra = after_set - before_set
        print(f"  missing hashes: {len(missing)}", file=sys.stderr)
        print(f"  extra hashes:   {len(extra)}", file=sys.stderr)
        return 5

    V38.write_text(patched, encoding="utf-8")

    combined = hashlib.sha256(("\n".join(before_hashes)).encode("ascii")).hexdigest()
    print(f"[hotfix] combined base64-fingerprint SHA256: {combined}")
    print(f"[hotfix] wrote patched v38 ({len(patched)} chars)")
    print(f"[hotfix] backup: {BACKUP}")
    print("[hotfix] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
