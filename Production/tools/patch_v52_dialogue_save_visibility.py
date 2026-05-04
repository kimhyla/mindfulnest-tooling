#!/usr/bin/env python3
"""
Path B patch: storyboard v51 → v52 — dialogue + image save-failure visibility.

Fix-Q:
  Wraps window.fetch on three save endpoints:
    - POST /api/beat/update_text          (legacy dialogue blur)
    - POST /api/v2/beat/<id>/patch        (v2 routed dialogue + image)
    - POST /api/assign-image              (legacy image-assign)

  On failure (HTTP non-2xx, JSON {error:"..."}, or fetch reject) → fixed-position
  full-width red banner at top of viewport (z-index 99999, click-to-dismiss).

  On every <textarea data-i="..."> input event → mirror current value to
  localStorage key _fixQ_pending_beat_NN with {text, ts}, debounced 500ms.
  Cleared on confirmed save success ONLY when saveKind=='dialogue' (image saves
  do NOT touch dialogue dirty state — protects against cross-field clobber).

  On beforeunload → browser native confirm if any textarea is dirty.

  On window load → sweep localStorage for orphan _fixQ_pending_* keys; entries
  >24h old are auto-purged; remaining orphans surface a recovery banner +
  expose window._fixQ_recover() console function.

Idempotent via window._fixQ_installed flag.

Counter-agent (Phase 0 zero-error-qa) findings addressed at root cause:
  CRIT — JSON.parse(opts.body) wrapped in try/catch (FormData/Blob safety)
  HIGH — saveKind discrimination prevents image-save clearing dialogue dirty
  HIGH — 24h TTL on localStorage entries prevents unbounded namespace growth
  MED  — 500ms debounce on input → localStorage write (no thrash on fast typing)
  MED  — uses window.addEventListener("load") instead of blind setTimeout(500)

Approach: Path B JS-only injection (per CLAUDE.md Rule 7), single IIFE block
inserted before </html>. Same pattern as v51 Fix-P (LD-446).

Input:  Production/Event_1/storyboard_v51_prod.html
Output: Production/Event_1/storyboard_v52_prod.html

Safety gates (HARD STOP on failure):
  - </html> exists exactly once in source
  - _fixQ_installed not already present in source (idempotency)
  - SHA256 of all base64 blobs byte-identical before/after
  - Atomic write: .tmp file first, only renamed to final on all-checks-pass

Phase 0 Directus row: prod_preflight_reviews id=181
LD: DIALOGUE_IMAGE_SAVE_VISIBILITY_V1 (to register on Kim approval after live test)
"""
import hashlib
import os
import re
import sys
from pathlib import Path

_EVENT_DIR = Path(__file__).parent.parent / "Event_1"
SRC  = _EVENT_DIR / "storyboard_v51_prod.html"
DEST = _EVENT_DIR / "storyboard_v52_prod.html"
TMP  = _EVENT_DIR / "storyboard_v52_prod.html.tmp"

if not SRC.exists():
    print(f"ERROR: source {SRC} not found", file=sys.stderr)
    sys.exit(2)

html = SRC.read_text(encoding="utf-8")
print(f"Read {SRC.name}: {len(html):,} chars")

# Gate 1 — </html> exactly once
end_count = html.count("</html>")
if end_count != 1:
    print(f"ERROR: </html> appears {end_count} times in source (expected 1)", file=sys.stderr)
    sys.exit(2)

# Gate 2 — idempotency
if "_fixQ_installed" in html:
    print("ERROR: source already contains _fixQ_installed — already patched", file=sys.stderr)
    sys.exit(2)


def b64_signature(text: str):
    """Returns (sha256_hex, count) over all base64 blobs >100 chars."""
    blobs = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', text)
    h = hashlib.sha256()
    for b in blobs:
        h.update(b.encode())
    return h.hexdigest(), len(blobs)


hash_before, count_before = b64_signature(html)
print(f"Base64 blobs before: {count_before}, sha256: {hash_before[:16]}...")


FIX_Q = r"""
<script>
// =====================================================================
// Fix-Q: Dialogue + image save-failure visibility (2026-05-01)
//
// Wraps window.fetch on dialogue + image save endpoints to make silent
// save failures impossible to miss. Mirrors textarea edits to localStorage
// with 24h TTL. beforeunload guard + crash-recovery sweep on load.
//
// LD: DIALOGUE_IMAGE_SAVE_VISIBILITY_V1 (preflight 181)
// =====================================================================
(function FixQ() {
  "use strict";
  if (window._fixQ_installed) return;
  window._fixQ_installed = true;
  console.log("[Fix-Q] Dialogue+image save-failure visibility active");

  var ORPHAN_TTL_MS = 24 * 60 * 60 * 1000;  // 24h
  var DEBOUNCE_MS = 500;
  var BANNER_ID = "_fixQ_banner";

  // ── Banner ──────────────────────────────────────────────────
  function showBanner(msg) {
    var b = document.getElementById(BANNER_ID);
    if (!b) {
      b = document.createElement("div");
      b.id = BANNER_ID;
      b.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:99999;"
        + "padding:14px 20px;font:600 14px system-ui,Arial,sans-serif;"
        + "background:#c0392b;color:#fff;text-align:center;cursor:pointer;"
        + "box-shadow:0 2px 8px rgba(0,0,0,0.4)";
      b.title = "Click to dismiss";
      b.onclick = function () { b.style.display = "none"; };
      if (document.body) {
        document.body.appendChild(b);
      } else {
        document.addEventListener("DOMContentLoaded", function () {
          if (document.body) document.body.appendChild(b);
        });
      }
    }
    b.style.display = "block";
    b.textContent = msg;
  }

  // ── Dirty tracking + localStorage shadow ────────────────────
  var _dirty = new Set();
  var _debounce = {};

  function _bidFromTextarea(t) {
    var i = parseInt(t.getAttribute("data-i"), 10);
    if (isNaN(i)) return null;
    return "beat_" + (i < 9 ? "0" : "") + (i + 1);
  }

  document.addEventListener("input", function (e) {
    var t = e.target;
    if (!t || t.tagName !== "TEXTAREA" || !t.hasAttribute("data-i")) return;
    var bid = _bidFromTextarea(t);
    if (!bid) return;
    _dirty.add(t);
    if (_debounce[bid]) clearTimeout(_debounce[bid]);
    _debounce[bid] = setTimeout(function () {
      try {
        localStorage.setItem("_fixQ_pending_" + bid,
          JSON.stringify({ text: t.value, ts: Date.now() }));
      } catch (e) { /* private mode / quota — ignore */ }
      delete _debounce[bid];
    }, DEBOUNCE_MS);
  }, true);

  function _clearDialogueDirty(bid) {
    var toDelete = [];
    _dirty.forEach(function (t) {
      if (_bidFromTextarea(t) === bid) toDelete.push(t);
    });
    toDelete.forEach(function (t) { _dirty.delete(t); });
    if (_debounce[bid]) {
      clearTimeout(_debounce[bid]);
      delete _debounce[bid];
    }
    try { localStorage.removeItem("_fixQ_pending_" + bid); } catch (e) {}
  }

  // ── Fetch wrapper ───────────────────────────────────────────
  // Identifies dialogue/image save endpoints and wraps with
  // visible-failure UX. Pass-through on any non-save endpoint.
  var _orig = window.fetch;
  window.fetch = function (url, opts) {
    if (typeof url !== "string") return _orig.apply(this, arguments);

    var saveKind = null;  // 'dialogue' | 'image' | null
    var bid = null;

    if (url.indexOf("/api/beat/update_text") >= 0) {
      saveKind = "dialogue";
      try { bid = JSON.parse((opts && opts.body) || "{}").beat || null; }
      catch (e) { /* unparseable body — don't track */ saveKind = null; }
    } else if (url.indexOf("/api/assign-image") >= 0) {
      saveKind = "image";
      try { bid = JSON.parse((opts && opts.body) || "{}").beat || null; }
      catch (e) { saveKind = null; }
    } else {
      var m = url.match(/\/api\/v2\/beat\/([^/]+)\/patch/);
      if (m) {
        bid = m[1];
        try {
          var body = JSON.parse((opts && opts.body) || "{}");
          if (body.field === "dialogue") saveKind = "dialogue";
          else if (body.field === "image_override") saveKind = "image";
          // other fields (selected_option / trim_*) — not tracked
        } catch (e) {
          // FormData / Blob / unparseable — pass through unwrapped
          saveKind = null;
        }
      }
    }

    if (!saveKind || !bid) return _orig.apply(this, arguments);
    var label = saveKind === "dialogue" ? "Dialogue" : "Image";

    return _orig.apply(this, arguments).then(function (r) {
      if (!r.ok) {
        showBanner("⚠ " + label + " save FAILED for " + bid
          + " (HTTP " + r.status + "). Edit NOT on disk. "
          + "Is production_server.py running on :5111?");
        return r;
      }
      r.clone().json().then(function (d) {
        if (d && d.error) {
          showBanner("⚠ " + label + " save REJECTED for " + bid + ": "
            + d.error + ". Edit NOT on disk.");
          return;
        }
        // Confirmed success — clear dialogue dirty ONLY on dialogue saves.
        // Image saves leave dialogue state untouched (counter-agent HIGH #1).
        if (saveKind === "dialogue") _clearDialogueDirty(bid);
      }).catch(function () { /* non-JSON body — leave dirty mark intact */ });
      return r;
    }).catch(function (err) {
      showBanner("⚠ " + label + " save FAILED for " + bid + " ("
        + ((err && err.message) || "network error") + "). "
        + "Edit NOT on disk. Is production_server.py running on :5111?");
      throw err;
    });
  };

  // ── Beforeunload guard ─────────────────────────────────────
  window.addEventListener("beforeunload", function (e) {
    if (_dirty.size > 0) {
      var msg = "You have " + _dirty.size + " unsaved dialogue edit(s). "
        + "Click into each line and Tab out to save before closing.";
      e.preventDefault();
      e.returnValue = msg;
      return msg;
    }
  });

  // ── Crash-recovery sweep on window load ────────────────────
  window.addEventListener("load", function () {
    var orphans = [];
    var stale = [];
    var now = Date.now();
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (!k || k.indexOf("_fixQ_pending_") !== 0) continue;
        try {
          var v = JSON.parse(localStorage.getItem(k));
          if (v && typeof v.ts === "number" && (now - v.ts) > ORPHAN_TTL_MS) {
            stale.push(k);
          } else if (v && typeof v.text === "string") {
            orphans.push({
              beat: k.replace("_fixQ_pending_", ""),
              text: v.text,
              ts: v.ts
            });
          } else {
            stale.push(k);
          }
        } catch (e) {
          stale.push(k);
        }
      }
      stale.forEach(function (k) {
        try { localStorage.removeItem(k); } catch (e) {}
      });
    } catch (e) { /* localStorage unavailable — no recovery possible */ }

    if (orphans.length > 0) {
      showBanner("⚠ Found " + orphans.length
        + " UNSAVED dialogue edit(s) from a previous session: "
        + orphans.map(function (o) { return o.beat; }).join(", ")
        + ". Run window._fixQ_recover() in console to view.");
      window._fixQ_recover = function () {
        console.group("[Fix-Q] Orphan dialogue edits");
        orphans.forEach(function (o) {
          console.log(o.beat, "(saved " + new Date(o.ts).toISOString() + "):");
          console.log("  " + o.text);
        });
        console.groupEnd();
        return orphans;
      };
    }
  });
})();
// === END Fix-Q ===
</script>
"""

MARKER = "</html>"
pos = html.rfind(MARKER)
if pos == -1:
    print("ERROR: </html> not found", file=sys.stderr)
    sys.exit(2)

patched = html[:pos] + FIX_Q + html[pos:]
print(f"Injected Fix-Q ({len(FIX_Q):,} chars) before </html>")

# Gate 3 — base64 byte-identical
hash_after, count_after = b64_signature(patched)
if hash_before != hash_after or count_before != count_after:
    print(
        f"INTEGRITY FAIL — base64 blob count {count_before} → {count_after}, "
        f"hash {hash_before[:16]}... → {hash_after[:16]}...",
        file=sys.stderr,
    )
    sys.exit(3)
print(f"Base64 integrity verified: {count_after} blobs, sha256 {hash_after[:16]}... unchanged")

# Atomic write — .tmp first, only rename on all-checks-pass
TMP.write_text(patched, encoding="utf-8")
print(f"Wrote tmp {TMP.name}: {len(patched):,} chars")

# Final verification — read back tmp, re-compute hash
verify_text = TMP.read_text(encoding="utf-8")
hash_verify, count_verify = b64_signature(verify_text)
if hash_verify != hash_after or count_verify != count_after:
    print(f"VERIFY FAIL — tmp file disagrees with computed patch", file=sys.stderr)
    TMP.unlink(missing_ok=True)
    sys.exit(4)
if "_fixQ_installed" not in verify_text:
    print("VERIFY FAIL — tmp file missing _fixQ_installed sentinel", file=sys.stderr)
    TMP.unlink(missing_ok=True)
    sys.exit(4)
print(f"Tmp readback verified: {count_verify} blobs, sha256 {hash_verify[:16]}... + _fixQ_installed present")

# All gates passed — atomic rename
os.replace(TMP, DEST)
print(f"\nPatch complete.")
print(f"  Source:      {SRC.name}  ({len(html):,} chars)")
print(f"  Output:      {DEST.name}  ({len(patched):,} chars)")
print(f"  Delta:       +{len(patched) - len(html):,} chars (Fix-Q IIFE)")
print(f"  Base64 sha:  {hash_after[:16]}... ({count_after} blobs, unchanged)")
print(f"  Idempotent:  _fixQ_installed sentinel present")
