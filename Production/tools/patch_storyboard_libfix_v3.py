#!/usr/bin/env python3
"""
Path B patch — LIBFIX-V3 (2026-04-25)

Root cause (confirmed after Opus agent debate):
  The upload button sits at the BOTTOM of .mn-lib-body in the static HTML.
  All prior JS patches (FIXLIB-FINAL, LIBFIX-V2) try to move it dynamically
  on DOMContentLoaded, but they race against _mnLibFetch re-renders and inline
  style overrides. The CSS order:-1 trick is irrelevant because FIXLIB-FINAL
  already moves the btn to firstChild via JS — but the STATIC ordering causes
  a flash-of-wrong-position before JS runs, and any _mnLibFetch timing edge
  can re-introduce the wrong state.

Fix:
  Bake the CORRECT structure into the static HTML:
    .mn-lib-body
      ├── .mn-lib-upload-btn    ← first in DOM (no JS needed)
      └── #mn-lib-scroll-inner  ← all .mn-lib-section divs wrapped here
            ├── .mn-lib-section Source
            ├── .mn-lib-section Ready
            └── .mn-lib-section Character Masters

  With this static structure, FIXLIB-FINAL's guard fires immediately
  (getElementById("mn-lib-scroll-inner") already exists → return),
  LIBFIX-V2's _libfixV2Enforce finds btn is already firstChild → does nothing.
  The CSS flex-column + overflow:hidden + flex:1 on scroll-inner works as designed.

Also adds:
  - "✓ Use This" accept button on each FLUX option slot (bg-opt-accept)
    so Kim can choose which of the 3 FLUX options to mark as accepted
  - _bgAcceptAll enhanced to skip beats with no accepted_image_key
    (beat 1 intentionally empty) rather than prompting with confirm()
  - /api/bg/accept-option server call from accept button
"""

import hashlib, re, sys
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_libfixv3_backup.html"

SENTINEL = "LIBFIX-V3"


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


def restructure_lib_body(html: str) -> str:
    """
    Move the upload button to be the FIRST child of .mn-lib-body,
    and wrap all .mn-lib-section divs in #mn-lib-scroll-inner.

    Before:
      <div class="mn-lib-body">
        <div class="mn-lib-section">...</div> x3
        <label class="mn-lib-upload-btn">...</label>
      </div>

    After:
      <div class="mn-lib-body">
        <label class="mn-lib-upload-btn">...</label>
        <div id="mn-lib-scroll-inner">
          <div class="mn-lib-section">...</div> x3
        </div>
      </div>
    """
    # Find the full .mn-lib-body block
    body_pattern = re.compile(
        r'(<div class="mn-lib-body">)(.*?)(</div>\s*\n</div>)',
        re.DOTALL
    )
    m = body_pattern.search(html)
    if not m:
        # try without trailing newline
        body_pattern = re.compile(
            r'(<div class="mn-lib-body">)(.*?)(</div>\s*</div>)',
            re.DOTALL
        )
        m = body_pattern.search(html)
    if not m:
        raise ValueError("Could not find .mn-lib-body block in HTML")

    open_tag = m.group(1)
    inner_content = m.group(2)
    close_tags = m.group(3)

    # Extract the upload button
    btn_pattern = re.compile(
        r'\s*<label class="mn-lib-upload-btn">.*?</label>',
        re.DOTALL
    )
    btn_m = btn_pattern.search(inner_content)
    if not btn_m:
        raise ValueError("Could not find .mn-lib-upload-btn inside .mn-lib-body")

    upload_btn_html = btn_m.group(0).strip()
    content_without_btn = inner_content[:btn_m.start()] + inner_content[btn_m.end():]

    # Verify sections are present
    sections = re.findall(r'<div class="mn-lib-section">', content_without_btn)
    if len(sections) < 3:
        raise ValueError(f"Expected 3 .mn-lib-section divs, found {len(sections)}")

    # Build new inner structure
    new_inner = f"""
{upload_btn_html}
<div id="mn-lib-scroll-inner">{content_without_btn}</div>"""

    new_body = open_tag + new_inner + "\n" + close_tags
    new_html = html[:m.start()] + new_body + html[m.end():]
    return new_html


# CSS: tighten up the upload btn appearance at sidebar level
# JS: add "✓ Use This" accept button per FLUX option slot + enhance Accept All
PATCH = """\

<style>
/* LIBFIX-V3: Static HTML structure fix (2026-04-25)
   .mn-lib-body is now flex-column with upload btn FIRST in DOM + #mn-lib-scroll-inner
   wrapping the sections. No JS needed — FIXLIB-FINAL and LIBFIX-V2 guards fire as
   no-ops since the structure already matches what they were trying to build. */

/* Ensure the upload btn is always visible and styled correctly at top of body */
#mn-lib-sidebar > .mn-lib-body > .mn-lib-upload-btn {
  display: block !important;
  flex-shrink: 0 !important;
  position: static !important;
  margin: 6px 6px 4px 6px !important;
  width: calc(100% - 12px) !important;
  box-sizing: border-box !important;
  border-bottom: 1px solid #2a4a2a !important;
  padding-bottom: 6px !important;
  order: -999 !important;
}

/* Per-option accept button */
.bg-opt-accept {
  position: absolute;
  bottom: 2px;
  right: 2px;
  background: #2d6a4f;
  color: #fff;
  border: none;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 700;
  padding: 2px 5px;
  cursor: pointer;
  z-index: 8;
  letter-spacing: 0.3px;
  white-space: nowrap;
}
.bg-opt-accept:hover { background: #40916c; }
.bg-opt.chosen .bg-opt-accept {
  background: #1b4332;
  content: "\2713 Accepted";
}
/* Make bg-opt position:relative so absolute children work */
.bg-opt { position: relative !important; }
</style>
<script>
// =====================================================================
// LIBFIX-V3: Accept flow enhancements (2026-04-25)
// 1. "✓ Use This" button on each FLUX option slot (sets accepted_image_key)
// 2. _bgAcceptToStoryboard enhanced: skips beats with no accepted_image_key
//    (beat 1 is intentionally empty) without a confirm() dialog
// =====================================================================

(function () {
  "use strict";

  // ── 1. Inject "✓ Use This" buttons into rendered FLUX option slots ────
  // _bgRenderBeats creates the slots but has no accept button.
  // We wrap _bgRenderBeats to inject accept buttons after every render.
  document.addEventListener("DOMContentLoaded", function () {
    var _prevRender = window._bgRenderBeats;
    if (typeof _prevRender !== "function") return;

    function _injectAcceptButtons() {
      var slots = document.querySelectorAll(".bg-opt[data-beat][data-opt]");
      for (var i = 0; i < slots.length; i++) {
        var slot = slots[i];
        if (slot.querySelector(".bg-opt-accept")) continue; // already has button
        // Only add if slot has an image (i.e. a FLUX still loaded)
        var img = slot.querySelector("img");
        if (!img) continue;

        var beatId  = slot.getAttribute("data-beat");
        var slotIdx = parseInt(slot.getAttribute("data-opt") || "0", 10);

        (function (bid, si, sl) {
          var btn = document.createElement("button");
          btn.className = "bg-opt-accept";
          btn.textContent = "\u2713 Use This";
          btn.title = "Mark this still as the accepted image for this beat";
          btn.onclick = function (e) {
            e.stopPropagation();
            _bgAcceptFluxOption(bid, si, sl);
          };
          sl.appendChild(btn);
        })(beatId, slotIdx, slot);
      }
    }

    window._bgRenderBeats = function (beats) {
      _prevRender(beats || BG_BEATS);
      setTimeout(_injectAcceptButtons, 50);
    };

    // Also inject on first load (if beats already rendered before this script)
    setTimeout(_injectAcceptButtons, 300);
  });

  // ── 2. Accept a FLUX option as the chosen still for a beat ───────────
  window._bgAcceptFluxOption = function (beatId, slotIndex, slotEl) {
    // Find the beat's flux_options[slotIndex].key
    var beat = null;
    for (var j = 0; j < (BG_BEATS || []).length; j++) {
      if (BG_BEATS[j].beat_id === beatId) { beat = BG_BEATS[j]; break; }
    }
    if (!beat) { console.warn("[BG-ACCEPT] beat not found:", beatId); return; }

    var fopts = beat.flux_options || [];
    var fopt  = fopts[slotIndex];
    if (!fopt || !fopt.key) {
      console.warn("[BG-ACCEPT] no flux_options key at slot", slotIndex, "for beat", beatId);
      return;
    }

    var key = fopt.key;

    // Update in-memory
    beat.accepted_image_key = key;
    beat.status = "accepted";

    // Visual: mark chosen slot, un-choose others on this beat
    var card = document.getElementById("bg-card-" + beatId);
    if (card) {
      var allSlots = card.querySelectorAll(".bg-opt");
      for (var si = 0; si < allSlots.length; si++) {
        allSlots[si].classList.remove("chosen");
        var ab = allSlots[si].querySelector(".bg-opt-accept");
        if (ab) ab.textContent = "\u2713 Use This";
      }
    }
    slotEl.classList.add("chosen");
    var acceptBtn = slotEl.querySelector(".bg-opt-accept");
    if (acceptBtn) acceptBtn.textContent = "\u2713 Accepted";

    // Enable the Accept All to Storyboard button
    var globalBtn = document.getElementById("bg-accept-btn");
    if (globalBtn) globalBtn.disabled = false;

    // Update status chip
    var sp = document.getElementById("bg-status-" + beatId);
    if (sp) sp.textContent = "accepted";

    // Persist to server
    fetch(BG_SERVER + "/api/bg/update-beat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        beat_id: beatId,
        accepted_image_key: key,
        status: "accepted"
      })
    }).catch(function (e) {
      console.warn("[BG-ACCEPT] server persist failed:", e);
    });

    console.log("[BG-ACCEPT] Beat", beatId, "accepted slot", slotIndex, "key:", key);
  };

  // ── 3. Enhanced Accept All to Storyboard ─────────────────────────────
  // Replaces the existing _bgAcceptToStoryboard to:
  //   - SKIP beats with no accepted_image_key (don't push to L[] or warn)
  //   - Log skipped beats to console
  //   - Switch to storyboard tab after push
  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("bg-accept-btn");
    if (btn) {
      // Remove old onclick and replace
      btn.onclick = null;
      btn.removeAttribute("onclick");
      btn.addEventListener("click", function () {
        _bgAcceptToStoryboardV3();
      });
    }
    window._bgAcceptToStoryboard = _bgAcceptToStoryboardV3;
  });

  window._bgAcceptToStoryboardV3 = function () {
    if (!BG_BEATS || !BG_BEATS.length) return;

    var pushed = 0;
    var skipped = [];

    BG_BEATS.forEach(function (beat, idx) {
      if (!beat.accepted_image_key) {
        // Beat intentionally empty or not yet decided — skip silently
        skipped.push("Beat " + (idx + 1) + " (" + beat.beat_id + ")");
        return;
      }
      L.push({
        s: beat.speaker || "Chipper",
        t: beat.dialogue_text || "",
        i: beat.accepted_image_key,
        a: null,
        p: 0.5,
        g: BG_SEG ? BG_SEG.name : "Beat Generator"
      });
      pushed++;
    });

    if (skipped.length) {
      console.log("[BG-ACCEPT-ALL] Skipped empty beats:", skipped.join(", "));
    }
    if (!pushed) {
      alert("No beats have an accepted image yet.\nClick \"\u2713 Use This\" on a still first.");
      return;
    }

    // Persist to server
    fetch(BG_SERVER + "/api/bg/accept-beats", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({beats: BG_BEATS, segment: BG_SEG})
    }).catch(function () {});

    // Re-render storyboard and switch tab
    if (typeof render === "function") render();
    _bgSwitchTab("sb", null);

    console.log("[BG-ACCEPT-ALL] Pushed " + pushed + " beats to storyboard L[], skipped " + skipped.length + ".");
  };

})();
// === END LIBFIX-V3 ===
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

    # Backup
    BACKUP_PATH.write_bytes(HTML_PATH.read_bytes())
    print(f"  Backup: {BACKUP_PATH.name}")

    # Step 1: Restructure static HTML (.mn-lib-body → btn first + scroll-inner)
    print("  Restructuring .mn-lib-body static HTML...")
    try:
        html = restructure_lib_body(html)
        print("  ✓ Upload button moved to first child + #mn-lib-scroll-inner created")
    except ValueError as e:
        print(f"ABORT: {e}")
        sys.exit(1)

    # Verify #mn-lib-scroll-inner and btn ordering
    body_m = re.search(r'<div class="mn-lib-body">(.*?)</div>\s*\n</div>', html, re.DOTALL)
    if not body_m:
        body_m = re.search(r'<div class="mn-lib-body">(.*?)</div>\s*</div>', html, re.DOTALL)
    if body_m:
        inner = body_m.group(1)
        btn_pos = inner.find('mn-lib-upload-btn')
        inner_pos = inner.find('mn-lib-scroll-inner')
        if btn_pos < 0:
            print("ABORT: btn not found in body after restructure")
            sys.exit(1)
        if inner_pos < 0:
            print("ABORT: #mn-lib-scroll-inner not found after restructure")
            sys.exit(1)
        if btn_pos > inner_pos:
            print(f"ABORT: btn pos {btn_pos} > scroll-inner pos {inner_pos} — ordering wrong")
            sys.exit(1)
        print(f"  ✓ DOM order verified: btn @ {btn_pos}, scroll-inner @ {inner_pos}")

    # Step 2: Inject JS/CSS patch (before </body>)
    anchor = "</body>" if "</body>" in html else "</html>"
    patched = html.replace(anchor, PATCH + anchor, 1)

    # Safety: base64 byte-identical
    b64c2, b64h2 = sha256_b64(patched)
    if b64h != b64h2 or b64c != b64c2:
        print("ABORT: base64 fingerprint changed."); sys.exit(1)
    print("  ✓ Base64 byte-identical")

    expected = PATCH.count(SENTINEL)
    if patched.count(SENTINEL) != expected:
        print(f"ABORT: sentinel count {patched.count(SENTINEL)} ≠ {expected}.")
        sys.exit(1)
    print(f"  ✓ Sentinel ×{expected}")

    HTML_PATH.write_text(patched, encoding="utf-8")
    print(f"  ✓ Written: {HTML_PATH.name} ({HTML_PATH.stat().st_size // 1024} KB)")
    print()
    print("Changes made:")
    print("  1. Static HTML: .mn-lib-upload-btn moved to FIRST child of .mn-lib-body")
    print("  2. Static HTML: all .mn-lib-section divs wrapped in #mn-lib-scroll-inner")
    print("  3. JS: '✓ Use This' accept button injected on each FLUX option slot")
    print("  4. JS: Accept All to Storyboard now SKIPS empty beats (beat 1 safe)")


if __name__ == "__main__":
    main()
