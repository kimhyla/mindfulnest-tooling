#!/usr/bin/env python3
"""
Path B patch: storyboard v56 -> v57 — Fix-V.

INVARIANTS:
  - Patches v56 only (must contain _fixPInited..._fixU_installed)
  - </html> last-position is structural close
  - Idempotency via _fixV_installed sentinel
  - SHA256 base64 byte-identical pre/post
  - Atomic .tmp + readback + os.replace
  - Server-side counterpart (production_server.py edits) deployed first
    via separate edit + Rule 29 server restart
  - Phase 6.5 4-variant live probe confirms /api/cr/library/delete works

Fix-V (LD-pending LIB_MTIME_SORT_AND_DELETE_V1):
  Adds 🗑 delete buttons per source-tier .mn-lib-item via _mnLibRender wrap.
  Click → confirm() → POST absolute-localhost /api/cr/library/delete.

Phase 0 advocate+counter (Sonnet) findings addressed at root cause:
  CRIT(invalidated): file_path is ABSOLUTE in prod_assets (not relative)
  HIGH: glob.escape() + space-vs-underscore handling (server-side, done)
  HIGH: Rule 19 try/except OSError + FileNotFoundError → 404 (server-side, done)
  MED: typeof _mnLibRender === 'function' guard (this patch)
  MED: explicit z-index/pointer-events on delete button (this patch)

Phase 0 preflight: 186
"""
import hashlib, os, re, sys
from pathlib import Path

_EVENT_DIR = Path(__file__).parent.parent / "Event_1"
SRC  = _EVENT_DIR / "storyboard_v56_prod.html"
DEST = _EVENT_DIR / "storyboard_v57_prod.html"
TMP  = _EVENT_DIR / "storyboard_v57_prod.html.tmp"

if not SRC.exists():
    print(f"ERROR: source {SRC} not found", file=sys.stderr); sys.exit(2)
html = SRC.read_text(encoding="utf-8")
print(f"Read {SRC.name}: {len(html):,} chars")

end_count = html.count("</html>")
if end_count < 1:
    print("ERROR: </html> not found", file=sys.stderr); sys.exit(2)
last_pos = html.rfind("</html>")
trailing = html[last_pos + len("</html>"):].strip()
if trailing:
    print(f"ERROR: content after last </html>", file=sys.stderr); sys.exit(2)

if "_fixV_installed" in html:
    print("ERROR: _fixV_installed already present", file=sys.stderr); sys.exit(2)

for sentinel, name in (("_fixPInited","P"), ("_fixQ_installed","Q"),
                       ("_fixR_installed","R"), ("_fixS_installed","S"),
                       ("_fixT_installed","T"), ("_fixU_installed","U")):
    if sentinel not in html:
        print(f"ERROR: source missing {sentinel} (Fix-{name}) — not v56", file=sys.stderr); sys.exit(2)
print("  Sentinel gate: P/Q/R/S/T/U all present")


def b64_sig(text):
    blobs = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', text)
    h = hashlib.sha256()
    for b in blobs: h.update(b.encode())
    return h.hexdigest(), len(blobs)


hash_before, count_before = b64_sig(html)
print(f"Base64 blobs before: {count_before}, sha256: {hash_before[:16]}...")


FIX_V = r"""
<script>
// =====================================================================
// Fix-V: Library delete UI — per-source-tier .mn-lib-item 🗑 button
// (2026-05-02)
//
// INVARIANTS:
//   - Server-side counterpart deployed: POST /api/cr/library/delete
//     (returns {ok, error?, asset_ids?, deleted?}). Phase 6.5 4-variant
//     probe confirmed dispatch + safety + glob.escape + mtime sort.
//   - typeof _mnLibRender === 'function' guard: required because Fix-V
//     IIFE may execute before _mnLibRender is defined depending on
//     <script> ordering (counter-agent finding).
//   - Wraps _mnLibRender at parse time. After base render runs (which
//     does grid.innerHTML = '' wiping any prior delete buttons), Fix-V
//     injects fresh 🗑 buttons. No stacking on re-render.
//   - Source tier ONLY — not crops (deliveries) or character_master (refs).
//
// LD: LIB_MTIME_SORT_AND_DELETE_V1 (preflight 186)
// =====================================================================
(function FixV() {
  "use strict";
  if (window._fixV_installed) return;
  window._fixV_installed = true;
  console.log("[Fix-V] Library delete UI active");

  function _fixV_buildDeleteBtn(libKey) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "mn-lib-delete-btn";
    b.textContent = "🗑";
    b.title = "Delete '" + libKey + "' from library";
    b.setAttribute("data-key", libKey);
    // Explicit positioning per Phase 0 counter MED: avoid stacking-context
    // / overflow:hidden interactions in future patches.
    b.style.cssText = "position:absolute !important;"
      + "top:2px !important;"
      + "right:2px !important;"
      + "z-index:10 !important;"
      + "pointer-events:auto !important;"
      + "background:rgba(0,0,0,0.6) !important;"
      + "color:#ff6 !important;"
      + "border:none !important;"
      + "border-radius:3px !important;"
      + "padding:1px 5px !important;"
      + "font-size:11px !important;"
      + "cursor:pointer !important;"
      + "line-height:1 !important;";
    b.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (b.disabled) return;
      if (!window.confirm("Delete '" + libKey + "' from library?\n\n"
          + "This permanently removes the file from disk.")) return;
      b.disabled = true;
      b.textContent = "…";
      fetch("http://localhost:5111/api/cr/library/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: libKey })
      })
      .then(function (r) { return r.json().then(function (d) { return [r.status, d]; }); })
      .then(function (pair) {
        var status = pair[0], d = pair[1];
        if (d && d.ok) {
          console.log("[Fix-V] deleted:", libKey, "→", d.deleted);
          if (typeof _mnLibFetch === "function") _mnLibFetch();
        } else if (status === 409 && d && d.asset_ids) {
          alert("Cannot delete '" + libKey + "':\n\n"
            + d.error + "\n\n"
            + "Referenced by prod_asset id(s): " + d.asset_ids.join(", ") + "\n\n"
            + "Delete or supersede those asset records first.");
          b.disabled = false; b.textContent = "🗑";
        } else {
          alert("Delete failed: " + (d && d.error || ("HTTP " + status)));
          b.disabled = false; b.textContent = "🗑";
        }
      })
      .catch(function (err) {
        alert("Network error: " + (err && err.message || err));
        b.disabled = false; b.textContent = "🗑";
      });
    });
    return b;
  }

  function _fixV_injectDeleteButtons() {
    var sourceItems = document.querySelectorAll(
      "#mn-lib-grid-source .mn-lib-item[data-key]");
    for (var i = 0; i < sourceItems.length; i++) {
      var item = sourceItems[i];
      // Idempotent: skip if button already injected for this render
      if (item.querySelector(".mn-lib-delete-btn")) continue;
      var k = item.getAttribute("data-key");
      if (!k) continue;
      // Ensure parent has position:relative so absolute-positioned button
      // anchors correctly (defensive — most .mn-lib-item already have it
      // via base CSS, but explicit is safer)
      if (getComputedStyle(item).position === "static") {
        item.style.position = "relative";
      }
      item.appendChild(_fixV_buildDeleteBtn(k));
    }
  }

  // Wrap _mnLibRender to inject delete buttons after each render
  function _fixV_wrap() {
    if (typeof _mnLibRender !== "function") {
      console.warn("[Fix-V] _mnLibRender not defined yet — deferring");
      return false;
    }
    if (window._fixV_wrapInstalled) return true;
    window._fixV_wrapInstalled = true;
    var orig = window._mnLibRender;
    window._mnLibRender = function () {
      orig.apply(this, arguments);
      _fixV_injectDeleteButtons();
    };
    // Also run once now in case render already happened before wrap installed
    _fixV_injectDeleteButtons();
    return true;
  }

  if (!_fixV_wrap()) {
    // Defer to DCL if _mnLibRender not yet defined
    document.addEventListener("DOMContentLoaded", function () {
      if (!_fixV_wrap()) {
        console.warn("[Fix-V] _mnLibRender still not defined at DCL — giving up");
      }
    });
  }
})();
// === END Fix-V ===
</script>
"""

MARKER = "</html>"
pos = html.rfind(MARKER)
patched = html[:pos] + FIX_V + html[pos:]
print(f"Injected Fix-V ({len(FIX_V):,} chars)")

hash_after, count_after = b64_sig(patched)
if hash_before != hash_after or count_before != count_after:
    print(f"INTEGRITY FAIL", file=sys.stderr); sys.exit(3)
print(f"Base64 verified: {count_after} blobs unchanged")

TMP.write_text(patched, encoding="utf-8")
verify = TMP.read_text(encoding="utf-8")
hv, cv = b64_sig(verify)
if hv != hash_after or cv != count_after:
    print("VERIFY FAIL", file=sys.stderr); TMP.unlink(missing_ok=True); sys.exit(4)
for s in ("_fixPInited", "_fixQ_installed", "_fixR_installed",
          "_fixS_installed", "_fixT_installed", "_fixU_installed", "_fixV_installed"):
    if s not in verify:
        print(f"VERIFY FAIL — missing {s}", file=sys.stderr); TMP.unlink(missing_ok=True); sys.exit(4)
print("Tmp readback verified, all 7 sentinels (P/Q/R/S/T/U/V) present")

os.replace(TMP, DEST)
print(f"\nPatch complete.")
print(f"  Source:  {SRC.name} ({len(html):,} chars)")
print(f"  Output:  {DEST.name} ({len(patched):,} chars)")
print(f"  Delta:   +{len(patched) - len(html):,} chars")
