#!/usr/bin/env python3
"""
Display fix — CRFIX-LIBFIX-V9 (2026-04-25)

Root cause: _bgAcceptToStoryboardV3 (LIBFIX-V3) uses L.push() which APPENDS
beat generator beats to whatever is already in L[]. If the storyboard still
contains a previous video's lines (Phase A intro, Phase B, etc.), those remain
and the new beats stack underneath them.

Fix: wrap _bgAcceptToStoryboardV3 to set L.length = 0 before calling the
original, so "Accept All to Storyboard" REPLACES L[] instead of appending.

L.length = 0 is the safe, in-place array truncation (same object reference,
no need to reassign the global).
"""

import hashlib, re, sys, tempfile, shutil
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_crfix_libfixv9_backup.html"

SENTINEL = "CRFIX-LIBFIX-V9"


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


PATCH = """\

<script>
// =====================================================================
// CRFIX-LIBFIX-V9: "Accept All to Storyboard" replaces L[], not appends (2026-04-25)
// _bgAcceptToStoryboardV3 (LIBFIX-V3) used L.push() — old storyboard content
// remained when beat generator beats were added. This wrapper clears L[] first.
// =====================================================================
document.addEventListener("DOMContentLoaded", function () {
  var _origAcceptAll = window._bgAcceptToStoryboardV3;
  if (typeof _origAcceptAll !== "function") {
    console.warn("[V9] _bgAcceptToStoryboardV3 not found — wrapper skipped.");
    return;
  }

  var _wrapped = function () {
    // Clear existing storyboard lines before accepting beat generator content
    if (typeof L !== "undefined" && Array.isArray(L)) {
      L.length = 0;
      console.log("[V9] L[] cleared — storyboard will be replaced, not appended.");
    }
    _origAcceptAll.apply(this, arguments);
  };

  window._bgAcceptToStoryboardV3 = _wrapped;
  window._bgAcceptToStoryboard   = _wrapped;

  console.log("[V9] _bgAcceptToStoryboardV3 wrapped — Accept All now REPLACES storyboard.");
});
// === END CRFIX-LIBFIX-V9 ===
</script>
"""


def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")
    b64c, b64h = sha256_b64(html)
    print(f"  Base64 blocks: {b64c}, sha256: {b64h}")

    if SENTINEL in html:
        print(f"ERROR: already patched ('{SENTINEL}' found).")
        sys.exit(1)

    if "CRFIX-LIBFIX-V8" not in html:
        print("ERROR: CRFIX-LIBFIX-V8 not found — apply earlier patches first.")
        sys.exit(1)

    BACKUP_PATH.write_bytes(HTML_PATH.read_bytes())
    print(f"  Backup: {BACKUP_PATH.name}")

    anchor = "</body>" if "</body>" in html else "</html>"
    patched = html.replace(anchor, PATCH + anchor, 1)

    b64c2, b64h2 = sha256_b64(patched)
    if b64h != b64h2 or b64c != b64c2:
        print("ABORT: base64 fingerprint changed."); sys.exit(1)
    print("  ✓ Base64 byte-identical")

    expected = PATCH.count(SENTINEL)
    if patched.count(SENTINEL) != expected:
        print(f"ABORT: sentinel {patched.count(SENTINEL)} ≠ {expected}")
        sys.exit(1)
    print(f"  ✓ Sentinel ×{expected}")

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".html", dir=HTML_PATH.parent)
    try:
        with open(tmp_fd, 'w', encoding="utf-8") as f:
            f.write(patched)
        shutil.move(tmp_path, str(HTML_PATH))
    except Exception as e:
        import os; os.unlink(tmp_path)
        print(f"ABORT: write failed — {e}"); sys.exit(1)

    print(f"  ✓ Written: {HTML_PATH.name} ({HTML_PATH.stat().st_size // 1024} KB)")
    print()
    print("Fix applied:")
    print("  • _bgAcceptToStoryboardV3 now clears L[] before pushing beats")
    print("  • 'Accept All to Storyboard' REPLACES old content, not appends")
    print("  • L.length = 0 is safe: same array object, no global reassignment needed")
    print()
    print("Cmd+Shift+R to reload, then click 'Accept All to Storyboard'.")


if __name__ == "__main__":
    main()
