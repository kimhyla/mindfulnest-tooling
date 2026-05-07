#!/usr/bin/env python3
"""
Display fix — CRFIX-BGACCEPT-V12 (2026-04-25)

V11 introduced async-before-render: it fetched thumbnails BEFORE calling
_origAcceptAll, so render() and _bgSwitchTab() lived inside .finally().
This caused a race condition where "Accept All" appeared to do nothing
(the sync wrapper returned immediately without modifying L[]).

Fix: SYNC FIRST, ASYNC THUMBNAILS AFTER.
  1. Set _BG_MODE synchronously (suppresses old animation injection).
  2. Call _origAcceptAll() synchronously (L.length=0 → push beats → render → switch tab).
  3. THEN async-fetch missing TH[] entries from /api/bg/crop-preview.
  4. When fetch completes, call render() again so thumbnails appear.

This means Accept All is instant (same timing as pre-V11), thumbnails appear
~100ms later after the server responds.
"""

import hashlib, re, sys, tempfile, shutil
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_crfix_bgacceptv12_backup.html"

SENTINEL = "CRFIX-BGACCEPT-V12"


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


PATCH = """\

<script>
// =====================================================================
// CRFIX-BGACCEPT-V12: Sync-first Accept All + lazy thumbnail fetch (2026-04-25)
//
// V11 was async-before-render which silently broke Accept All (render()
// never fired because it lived inside .finally() which ran too late).
// V12 fixes: call _origAcceptAll() synchronously, THEN fetch thumbnails.
// =====================================================================
document.addEventListener("DOMContentLoaded", function () {

  // ── Suppress old animation injection in BG mode (same as V11 Fix 1) ──
  var _origInjectAnims = window._injectAnimations;
  window._injectAnimations = function () {
    if (window._BG_MODE) {
      console.log("[V12] _injectAnimations suppressed — BG mode active.");
      return;
    }
    if (typeof _origInjectAnims === "function") _origInjectAnims.apply(this, arguments);
  };

  // ── Fix Accept All: sync-first, async thumbnails after ───────────────
  var _origAcceptAll = window._bgAcceptToStoryboardV3;
  if (typeof _origAcceptAll !== "function") {
    console.warn("[V12] _bgAcceptToStoryboardV3 not found — skipping wrapper.");
    return;
  }

  window._bgAcceptToStoryboardV3 = function () {
    // 1. Set BG mode BEFORE render() so _injectAnimations is suppressed
    window._BG_MODE = true;
    console.log("[V12] BG mode ON.");

    // 2. Call original SYNCHRONOUSLY — L.length=0, push beats, render, switch tab
    _origAcceptAll.apply(this, arguments);

    // 3. THEN async-fetch missing thumbnails and re-render
    var missingKeys = [];
    if (Array.isArray(BG_BEATS)) {
      BG_BEATS.forEach(function(beat) {
        var k = beat.accepted_image_key;
        if (k && !(typeof TH !== "undefined" && TH[k])) {
          missingKeys.push(k);
        }
      });
    }

    if (missingKeys.length > 0) {
      var url = BG_SERVER + "/api/bg/crop-preview?keys=" +
                missingKeys.map(encodeURIComponent).join(",");
      fetch(url)
        .then(function(r) { return r.json(); })
        .then(function(d) {
          var previews = (d && d.previews) || {};
          var filled = 0;
          Object.keys(previews).forEach(function(k) {
            if (typeof TH !== "undefined") { TH[k] = previews[k]; filled++; }
          });
          if (filled > 0 && typeof render === "function") {
            console.log("[V12] TH[] filled with " + filled + " preview(s) — re-rendering.");
            render();
          }
        })
        .catch(function(e) {
          console.warn("[V12] crop-preview fetch failed (server restart needed?):", e);
        });
    }
  };

  window._bgAcceptToStoryboard = window._bgAcceptToStoryboardV3;
  console.log("[V12] _bgAcceptToStoryboardV3 wrapped — sync-first Accept All active.");
});
// === END CRFIX-BGACCEPT-V12 ===
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

    if "CRFIX-BGACCEPT-V11" not in html:
        print("ERROR: CRFIX-BGACCEPT-V11 not found — apply earlier patches first.")
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
    print("  • Accept All now: set _BG_MODE → sync _origAcceptAll → async thumbnail fetch")
    print("  • render() called SYNCHRONOUSLY (no more race condition)")
    print("  • Thumbnails appear ~100ms later after /api/bg/crop-preview responds")
    print("  • Old Tessa animation clips blocked by _BG_MODE gate on _injectAnimations")
    print()
    print("Now: restart server, then Cmd+Shift+R, then go to BG tab, click Accept All.")


if __name__ == "__main__":
    main()
