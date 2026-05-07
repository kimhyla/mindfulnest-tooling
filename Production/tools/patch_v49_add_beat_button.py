#!/usr/bin/env python3
"""
Path B patch: Add Beat button + two-click delete guard for Beat Generator UI.

Fix-O:
  1. Wraps _bgRenderBeats to inject "+ Add Beat" divs between (and after) every
     beat card in #bg-beats.
  2. Replaces single-click confirm() delete guard with a two-click inline guard:
     first click → button turns "DELETE? ×" (red); second click within 3s → deletes;
     clicking elsewhere cancels.
  3. Adds POST /api/bg/add-beat call on click: inserts blank beat after after_beat_id,
     then calls _bgLoadState() to refresh.

Input:  storyboard_v49_prod.html
Output: storyboard_v50_prod.html

Safety: SHA256 of all base64 blobs verified identical before/after.
"""
import hashlib, re, sys
from pathlib import Path

_EVENT_DIR = Path(__file__).parent.parent / "Event_1"
SRC  = _EVENT_DIR / "storyboard_v49_prod.html"
DEST = _EVENT_DIR / "storyboard_v50_prod.html"

if not SRC.exists():
    print(f"ERROR: {SRC} not found"); sys.exit(1)

html = SRC.read_text(encoding="utf-8")
print(f"Read {SRC.name}: {len(html):,} chars")


def b64_hash(text):
    blobs = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', text)
    h = hashlib.sha256()
    for b in blobs:
        h.update(b.encode())
    return h.hexdigest(), len(blobs)


hash_before, count_before = b64_hash(html)
print(f"Base64 blobs before: {count_before}, hash: {hash_before[:16]}…")

FIX_O = r"""
<script>
// ══════════════════════════════════════════════════════════════════════════
// Fix-O: Add Beat button + two-click delete guard (2026-04-29)
// ══════════════════════════════════════════════════════════════════════════
(function () {
  "use strict";
  if (window._addBeatInited) return;
  window._addBeatInited = true;

  // ── 1. Two-click delete guard ───────────────────────────────────────────
  // Replace every .bg-del-btn onclick with a two-click inline guard.
  // First click:  button text → "DELETE? ×", adds class bg-del-confirm.
  //               A 3-second timeout auto-cancels if no second click.
  // Second click: proceeds with the server call + BG_BEATS splice.
  // Any other click on the page: cancels confirming state.
  var _delConfirmTimer = null;
  var _delConfirmBtn   = null;

  function _resetDelConfirm() {
    if (_delConfirmTimer) { clearTimeout(_delConfirmTimer); _delConfirmTimer = null; }
    if (_delConfirmBtn) {
      _delConfirmBtn.textContent = "×";
      _delConfirmBtn.classList.remove("bg-del-confirm");
      _delConfirmBtn = null;
    }
  }

  document.addEventListener("click", function (e) {
    // If click is NOT on the confirming button, cancel confirming state.
    if (_delConfirmBtn && e.target !== _delConfirmBtn) {
      _resetDelConfirm();
    }
  }, true);  // capture so it fires before the button onclick

  function _patchDelButtons() {
    var btns = document.querySelectorAll(".bg-del-btn");
    btns.forEach(function (btn) {
      if (btn.dataset.delPatched) return;  // already patched
      btn.dataset.delPatched = "1";

      // Remove the old onclick by cloning (drops all old listeners cleanly)
      var fresh = btn.cloneNode(true);
      fresh.dataset.delPatched = "1";
      btn.parentNode.replaceChild(fresh, btn);

      var beatCard = fresh.closest(".bg-beat-card");
      var beatId   = beatCard ? beatCard.id.replace(/^bg-card-/, "") : "";

      fresh.addEventListener("click", function (e) {
        e.stopPropagation();

        if (_delConfirmBtn === fresh) {
          // ── Second click: confirmed — do the delete ──────────────────
          _resetDelConfirm();
          fetch("http://localhost:5111/api/bg/delete-beat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ beat_id: beatId })
          }).then(function (r) { return r.json(); })
            .then(function (d) {
              if (d.ok) {
                window.BG_BEATS = (window.BG_BEATS || []).filter(
                  function (b) { return b.beat_id !== beatId; }
                );
                if (typeof window._bgRenderBeats === "function") {
                  window._bgRenderBeats(window.BG_BEATS);
                }
              }
            });
        } else {
          // ── First click: arm the guard ───────────────────────────────
          _resetDelConfirm();
          _delConfirmBtn = fresh;
          fresh.textContent = "DELETE? ×";
          fresh.classList.add("bg-del-confirm");
          _delConfirmTimer = setTimeout(function () {
            _resetDelConfirm();
          }, 3000);
        }
      });
    });
  }

  // ── 2. "+ Add Beat" buttons between cards ──────────────────────────────
  function _injectAddBeatButtons() {
    var container = document.getElementById("bg-beats");
    if (!container) return;

    // Remove any previously injected add-beat rows so we don't duplicate
    container.querySelectorAll(".bg-add-beat-row").forEach(function (el) {
      el.parentNode.removeChild(el);
    });

    var cards = Array.from(container.querySelectorAll(".bg-beat-card"));
    cards.forEach(function (card) {
      var afterBeatId = card.id ? card.id.replace(/^bg-card-/, "") : "";

      var row = document.createElement("div");
      row.className = "bg-add-beat-row";
      row.title = "Insert a new beat after this one";

      var addBtn = document.createElement("button");
      addBtn.className = "bg-add-beat-btn b";
      addBtn.textContent = "+ Add Beat";
      addBtn.addEventListener("click", function () {
        addBtn.disabled = true;
        addBtn.textContent = "Adding…";
        fetch("http://localhost:5111/api/bg/add-beat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            after_beat_id: afterBeatId,
            segment: window.BG_SEG || "event_2_pre"
          })
        }).then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.ok) {
              if (typeof window._bgLoadState === "function") {
                window._bgLoadState();
              }
            } else {
              alert("Add beat failed: " + (d.error || "unknown"));
              addBtn.disabled = false;
              addBtn.textContent = "+ Add Beat";
            }
          })
          .catch(function (e) {
            alert("Add beat error: " + e);
            addBtn.disabled = false;
            addBtn.textContent = "+ Add Beat";
          });
      });

      row.appendChild(addBtn);
      card.insertAdjacentElement("afterend", row);
    });

    // Also patch delete buttons now that cards are fresh
    _patchDelButtons();
  }

  // ── 3. Style injection ──────────────────────────────────────────────────
  var style = document.createElement("style");
  style.textContent = [
    ".bg-add-beat-row{display:flex;justify-content:center;padding:4px 0;opacity:0.5;transition:opacity 0.15s;}",
    ".bg-add-beat-row:hover{opacity:1;}",
    ".bg-add-beat-btn{font-size:11px;padding:3px 12px;background:#1a3a2a;color:#7dffb0;border:1px dashed #7dffb0;border-radius:4px;cursor:pointer;}",
    ".bg-add-beat-btn:hover{background:#2a5a3a;}",
    ".bg-del-confirm{background:#8b0000!important;color:#ffcccc!important;animation:bg-del-pulse 0.3s ease;}",
    "@keyframes bg-del-pulse{0%{transform:scale(1);}50%{transform:scale(1.15);}100%{transform:scale(1);}}"
  ].join("");
  document.head.appendChild(style);

  // ── 4. Hook into _bgRenderBeats ─────────────────────────────────────────
  function _wrapRenderBeats() {
    if (!window._bgRenderBeats) return false;
    if (window._bgRenderBeats._addBeatWrapped) return true;

    var _orig = window._bgRenderBeats;
    window._bgRenderBeats = function (beats) {
      _orig(beats);
      _injectAddBeatButtons();
    };
    window._bgRenderBeats._addBeatWrapped = true;
    return true;
  }

  // Try immediately; retry if _bgRenderBeats isn't defined yet
  if (!_wrapRenderBeats()) {
    var _retryTimer = setInterval(function () {
      if (_wrapRenderBeats()) clearInterval(_retryTimer);
    }, 200);
    setTimeout(function () { clearInterval(_retryTimer); }, 5000);
  }

  // Also run once on load in case beats are already rendered
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _injectAddBeatButtons);
  } else {
    setTimeout(_injectAddBeatButtons, 600);
  }
})();
</script>
"""

MARKER = "</html>"
pos = html.rfind(MARKER)
if pos == -1:
    print("ERROR: </html> not found"); sys.exit(1)

patched = html[:pos] + FIX_O + html[pos:]
print(f"Injected Fix-O ({len(FIX_O):,} chars) before </html>")

hash_after, count_after = b64_hash(patched)
if hash_before != hash_after or count_before != count_after:
    print("INTEGRITY FAIL — base64 blobs changed!"); sys.exit(1)
print(f"Base64 integrity verified: {count_after} blobs ✓")

DEST.write_text(patched, encoding="utf-8")
print(f"Wrote {DEST.name}")
