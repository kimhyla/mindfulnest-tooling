#!/usr/bin/env python3
"""
Path B patch — LIBFIX-V2 (2026-04-25)

Root causes fixed:
  1. Upload button not persistent at top of library:
     Fix-H's _fixhMoveUploadBtn is wrapped into _mnLibFetch at parse-time
     and fires 50ms after EVERY library open, moving the button out of
     .mn-lib-body. FIXLIB-FINAL's structure works on DOMContentLoaded but
     is continuously disrupted by Fix-H. This patch neutralizes _fixhMoveUploadBtn
     and wraps _mnLibToggle so the correct structure is enforced on every open.

  2. "stills pending" shown when stills exist on disk:
     beat_02.status="stills_pending" persists in the sidecar even after stills
     are generated. C2 render wrapper is updated to show "stills ready" whenever
     a beat has flux_options with local_path values (stills exist on disk).
"""

import hashlib, re, sys
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_libfixv2_backup.html"

SENTINEL = "LIBFIX-V2"


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


PATCH = """\

<style>
/* LIBFIX-V2: high-specificity override for .mn-lib-body flex structure (2026-04-25)
   Uses #mn-lib-sidebar > .mn-lib-body (specificity 0,1,1,1) to beat all prior
   class-only rules (.mn-lib-body = 0,0,1,0) so the column layout always wins. */
#mn-lib-sidebar > .mn-lib-body {
  display: flex !important;
  flex-direction: column !important;
  overflow: hidden !important;
  padding: 0 !important;
}
/* Upload btn: pinned flex item at top of the column (no sticky, no fixed) */
#mn-lib-sidebar > .mn-lib-body > .mn-lib-upload-btn {
  flex-shrink: 0 !important;
  position: static !important;
  margin: 5px 6px 4px 6px !important;
  width: calc(100% - 12px) !important;
  box-sizing: border-box !important;
  border-bottom: 1px solid #2a4a2a !important;
  padding-bottom: 6px !important;
  z-index: auto !important;
  order: -1 !important;
}
/* Scroll inner from FIXLIB-FINAL: takes remaining space, scrolls internally */
#mn-lib-sidebar > .mn-lib-body > #mn-lib-scroll-inner {
  flex: 1 !important;
  overflow-y: auto !important;
  padding: 4px 6px 12px 6px !important;
  min-height: 0 !important;
}
</style>
<script>
// =====================================================================
// LIBFIX-V2: Definitive library upload button fix (2026-04-25)
// Neutralizes Fix-H's _fixhMoveUploadBtn (the source of the battle),
// then enforces correct structure on every _mnLibToggle open.
// =====================================================================

(function () {
  "use strict";

  // ── 1. Neutralize Fix-H's _fixhMoveUploadBtn permanently ────────────
  // Fix-H wrapped _mnLibFetch at parse-time so _fixhMoveUploadBtn fires
  // 50ms after every library fetch, moving the btn to a WRONG sidebar
  // sibling (#mn-lib-upload-header in a flex-row parent = narrow column).
  // Simply replacing the function with a no-op breaks the cycle.
  if (typeof window._fixhMoveUploadBtn === "function") {
    window._fixhMoveUploadBtn = function () { /* disabled by LIBFIX-V2 */ };
  }
  // Guard: redefine via defineProperty so it cannot be overwritten later
  // (belt-and-suspenders — the override above is sufficient for our setup).
  try {
    Object.defineProperty(window, "_fixhMoveUploadBtn", {
      value: function () { /* disabled by LIBFIX-V2 */ },
      writable: false, configurable: false
    });
  } catch (e) { /* already non-configurable or strict-mode blocked — fine */ }

  // ── 2. Authoritative structure function ──────────────────────────────
  // Creates #mn-lib-scroll-inner if absent and ensures btn is the first
  // flex child of .mn-lib-body. Idempotent — safe to call repeatedly.
  function _libfixV2Enforce() {
    var body = document.querySelector(".mn-lib-body");
    if (!body) return;

    // Remove any stale #mn-lib-upload-header that Fix-H may have left
    var staleHeader = document.getElementById("mn-lib-upload-header");
    if (staleHeader && staleHeader.parentNode) {
      // Rescue btn before deleting the header
      var rescueBtn = staleHeader.querySelector(".mn-lib-upload-btn");
      if (rescueBtn) body.insertBefore(rescueBtn, body.firstChild);
      staleHeader.parentNode.removeChild(staleHeader);
    }

    var btn = body.querySelector(".mn-lib-upload-btn");

    // Ensure #mn-lib-scroll-inner exists and contains all .mn-lib-section divs
    var inner = document.getElementById("mn-lib-scroll-inner");
    if (!inner) {
      inner = document.createElement("div");
      inner.id = "mn-lib-scroll-inner";
      var sections = Array.prototype.slice.call(body.querySelectorAll(".mn-lib-section"));
      sections.forEach(function (s) { inner.appendChild(s); });
      // Clear body and rebuild: btn first, then scroll-inner
      while (body.firstChild) body.removeChild(body.firstChild);
      if (btn) body.appendChild(btn);
      body.appendChild(inner);
    } else {
      // inner exists — just ensure btn is the first child of body (not inside inner)
      if (btn && btn.parentNode !== body) {
        body.insertBefore(btn, body.firstChild);
      } else if (btn && body.firstElementChild !== btn) {
        body.insertBefore(btn, body.firstChild);
      }
    }
  }

  // ── 3. Run on DOMContentLoaded ────────────────────────────────────────
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _libfixV2Enforce);
  } else {
    _libfixV2Enforce();
  }

  // ── 4. Wrap _mnLibToggle so structure is enforced on every panel open ─
  // _mnLibToggle is defined at parse-time (not on DOMContentLoaded), so we
  // can wrap it immediately at the end of the document.
  document.addEventListener("DOMContentLoaded", function () {
    var _origToggle = window._mnLibToggle;
    if (typeof _origToggle === "function") {
      window._mnLibToggle = function () {
        _origToggle.apply(this, arguments);
        // After toggle, if panel is now open, re-enforce structure
        var sidebar = document.getElementById("mn-lib-sidebar");
        if (sidebar && sidebar.classList.contains("open")) {
          // Defer by one tick so the panel CSS transition starts first,
          // then enforce after fetch+render has had time to settle.
          setTimeout(_libfixV2Enforce, 150);
        }
      };
    }

    // Also patch _mnLibFetch to re-enforce after every render
    // (covers programmatic fetch calls that bypass _mnLibToggle)
    var _origFetch = window._mnLibFetch;
    if (typeof _origFetch === "function") {
      window._mnLibFetch = _mnLibFetch = function () {
        var result = _origFetch.apply(this, arguments);
        setTimeout(_libfixV2Enforce, 150);
        return result;
      };
    }
  });

  // ── 5. Persistent safety poll (no 10s limit) ─────────────────────────
  // Runs every 800ms while the library panel is OPEN to catch any
  // late-arriving DOM change (img loads, dynamic content, etc.).
  setInterval(function () {
    var sidebar = document.getElementById("mn-lib-sidebar");
    if (!sidebar || !sidebar.classList.contains("open")) return; // only when open
    var body = document.querySelector(".mn-lib-body");
    var btn = body && body.querySelector(".mn-lib-upload-btn");
    // If btn is not the first flex child of body, fix it
    if (btn && body && body.firstElementChild !== btn) {
      _libfixV2Enforce();
    }
    // If #mn-lib-upload-header appeared (Fix-H fired somehow), neutralize it
    if (document.getElementById("mn-lib-upload-header")) {
      _libfixV2Enforce();
    }
  }, 800);

})();

// ── 6. Fix "stills pending" status: C3 wrapper patch ─────────────────
// When _bgRenderBeats runs, update beat status display to "stills ready"
// if the beat has flux_options with local_path values (stills exist on disk).
// The sidecar may still have status="stills_pending" if the page was
// refreshed before polling completed — this corrects the UI label only.
(function () {
  "use strict";
  var _prevRender = _bgRenderBeats;
  _bgRenderBeats = function (beats) {
    _prevRender(beats || BG_BEATS);
    (beats || BG_BEATS || []).forEach(function (beat) {
      // Check if stills exist in flux_options
      var fopts = beat.flux_options || [];
      var hasStills = fopts.some(function (f) { return f && f.local_path; });
      if (!hasStills) return;
      // Status is "stills_pending" or similar but stills exist: update label
      var sp = document.getElementById("bg-status-" + beat.beat_id);
      if (sp) {
        var cur = sp.textContent || "";
        if (cur.indexOf("pending") !== -1 || cur === "draft") {
          sp.textContent = "stills ready";
        }
      }
    });
  };
})();
// === END LIBFIX-V2 ===
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

    BACKUP_PATH.write_bytes(HTML_PATH.read_bytes())
    print(f"  Backup: {BACKUP_PATH.name}")

    anchor = "</body>" if "</body>" in html else "</html>"
    patched = html.replace(anchor, PATCH + anchor, 1)

    b64c2, b64h2 = sha256_b64(patched)
    if b64h != b64h2 or b64c != b64c2:
        print("ABORT: base64 changed."); sys.exit(1)
    print("  ✓ Base64 byte-identical")

    expected = PATCH.count(SENTINEL)
    if patched.count(SENTINEL) != expected:
        print(f"ABORT: sentinel count {patched.count(SENTINEL)} ≠ {expected}.")
        sys.exit(1)
    print(f"  ✓ Sentinel ×{expected}")

    HTML_PATH.write_text(patched, encoding="utf-8")
    print(f"  ✓ Written: {HTML_PATH.name} ({HTML_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
