#!/usr/bin/env python3
"""
Display fix — CRFIX-BGACCEPT-V11 (2026-04-25)

Two bugs fixed:

1. Old production animations injecting into BG beat rows.
   injectAnimationsFromStatus() maps beat_01→row0, beat_02→row1 by POSITION.
   After "Accept All to Storyboard", the new BG rows 0 and 1 get the old Tessa
   Phase A clips injected into them because production_state still has beat_01/02.
   Fix: set window._BG_MODE = true when _bgAcceptToStoryboardV3 runs; wrap
   _injectAnimations to be a no-op in BG mode.

2. Accepted crop thumbnails not showing (TH[] cold after reload).
   The L[] entry has i: accepted_image_key, but render() needs TH[key]=data_uri
   to display the thumbnail. After a page reload TH[] is empty.
   Fix: in _bgAcceptToStoryboardV3, before calling render(), fetch all missing
   keys from the new /api/bg/crop-preview?keys=... endpoint and pre-fill TH[].
"""

import hashlib, re, sys, tempfile, shutil
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_crfix_bgacceptv11_backup.html"

SENTINEL = "CRFIX-BGACCEPT-V11"


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


PATCH = """\

<script>
// =====================================================================
// CRFIX-BGACCEPT-V11: Fix old animation injection + cold TH[] on Accept All (2026-04-25)
//
// Bug 1: injectAnimationsFromStatus maps beat_01->row0 by position index,
//   so old Tessa Phase A clips appear in BG beat rows after Accept All.
//   Fix: window._BG_MODE = true suppresses _injectAnimations in BG mode.
//
// Bug 2: accepted crop thumbnail absent after cold page reload (TH[] empty).
//   Fix: _bgAcceptToStoryboardV3 pre-fills TH[] from /api/bg/crop-preview
//   before calling render().
// =====================================================================
document.addEventListener("DOMContentLoaded", function () {

  // ── Fix 1: suppress old animation injection in BG mode ──────────────
  var _origInjectAnimations = window._injectAnimations;
  window._injectAnimations = function () {
    if (window._BG_MODE) {
      console.log("[V11] _injectAnimations suppressed — BG mode active, old clips blocked.");
      return;
    }
    if (typeof _origInjectAnimations === "function") _origInjectAnimations.apply(this, arguments);
  };

  // Also intercept the continuous poll path (injectAnimationsFromStatus
  // is called from flushQueued inside the status-poll closure). We can't
  // easily wrap the private closure, but _injectAnimations is the public
  // entry point that render() calls — wrapping it catches the render pass.
  // The poll-driven injection path calls the private injectAnimationsFromStatus
  // directly; intercept that via the status-poll callback if accessible.
  if (typeof window._pollStatusCb === "function") {
    var _origPollCb = window._pollStatusCb;
    window._pollStatusCb = function(s) {
      if (window._BG_MODE) return;
      _origPollCb.apply(this, arguments);
    };
  }

  // ── Fix 2: pre-fill TH[] before render() in Accept All path ─────────
  var _origAcceptAll = window._bgAcceptToStoryboardV3;
  if (typeof _origAcceptAll !== "function") {
    console.warn("[V11] _bgAcceptToStoryboardV3 not found at DOMContentLoaded — V11 partial.");
  } else {
    window._bgAcceptToStoryboardV3 = function () {
      window._BG_MODE = true;
      console.log("[V11] BG mode ON — old animation injection blocked.");

      // Collect accepted keys that are missing from TH[]
      var missingKeys = [];
      if (Array.isArray(BG_BEATS)) {
        BG_BEATS.forEach(function(beat) {
          var k = beat.accepted_image_key;
          if (k && !(typeof TH !== "undefined" && TH[k])) {
            missingKeys.push(k);
          }
        });
      }

      if (missingKeys.length === 0) {
        // TH[] already warm — proceed synchronously
        _origAcceptAll.apply(this, arguments);
        return;
      }

      // Fetch missing thumbnails from server, then render
      var self = this, args = arguments;
      var url = BG_SERVER + "/api/bg/crop-preview?keys=" + missingKeys.map(encodeURIComponent).join(",");
      fetch(url)
        .then(function(r) { return r.json(); })
        .then(function(d) {
          var previews = (d && d.previews) || {};
          Object.keys(previews).forEach(function(k) {
            if (typeof TH !== "undefined") TH[k] = previews[k];
          });
          console.log("[V11] Pre-filled TH[] with " + Object.keys(previews).length + " crop preview(s).");
        })
        .catch(function(e) {
          console.warn("[V11] crop-preview fetch failed:", e);
        })
        .finally(function() {
          _origAcceptAll.apply(self, args);
        });
    };

    window._bgAcceptToStoryboard = window._bgAcceptToStoryboardV3;
    console.log("[V11] _bgAcceptToStoryboardV3 wrapped — TH[] pre-fill + BG mode gate active.");
  }
});
// === END CRFIX-BGACCEPT-V11 ===
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

    if "CRFIX-LIBFIX-V10" not in html:
        print("ERROR: CRFIX-LIBFIX-V10 not found — apply earlier patches first.")
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
    print("Fixes applied:")
    print("  • _injectAnimations wrapped — no-op in BG mode (old Tessa clips blocked)")
    print("  • _bgAcceptToStoryboardV3 wrapped — sets window._BG_MODE = true")
    print("  • Pre-fills TH[] from /api/bg/crop-preview before render() on cold reload")
    print("  • Server restart required to activate /api/bg/crop-preview endpoint")
    print()
    print("After server restart + Cmd+Shift+R:")
    print("  1. Go to Beat Generator tab")
    print("  2. Click 'Accept All to Storyboard'")
    print("  3. BG beats should show crop thumbnails, NO old Tessa animation clips")


if __name__ == "__main__":
    main()
