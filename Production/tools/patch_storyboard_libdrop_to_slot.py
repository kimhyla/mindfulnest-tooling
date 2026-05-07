#!/usr/bin/env python3
"""
Path B patch — LIBDROP-TO-SLOT: Library image drag-to-beat-option-slot (2026-04-25)

Allows Kim to drag any library gallery card directly onto a beat option slot
(opt 0/1/2) to assign that image as the accepted output for the beat, bypassing
FLUX generation entirely.

Architecture (Counter-debate wins on all 8 failure modes):
  - Separate sidecar field `accepted_library_ref` — flux_options[] untouched
  - TH[] populated from MN_LIB_DATA.gallery_b64 at drop time (zero server round-trips)
  - Cold TH[] re-hydrated via existing /api/cr/full?abs_path= on _bgRenderBeats call
  - Capture-phase drop interceptor prevents existing beat-card handler from
    overwriting reference_image instead of the slot image
  - Crop button disabled on library-assigned slots (library images aren't FLUX stills)
  - Existing FLUX accept / Accept-All-to-Storyboard flows work unchanged
"""

import hashlib, re, sys
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_libdrop_backup.html"

SENTINEL = "LIBDROP-TO-SLOT"   # used for idempotency check


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


PATCH = """\

<style>
/* LIBDROP-TO-SLOT: library-assigned beat option slot states (2026-04-25) */
.bg-opt.bg-lib-drop-over {
  outline: 2px dashed #52b788 !important;
  background: rgba(82,183,136,0.10) !important;
}
.bg-opt.bg-lib-chosen {
  outline: 2px solid #2d6a4f !important;
}
.bg-lib-badge {
  position: absolute;
  top: 2px;
  left: 2px;
  background: #2d6a4f;
  color: #fff;
  font-size: 8px;
  font-weight: 700;
  padding: 1px 3px;
  border-radius: 3px;
  pointer-events: none;
  z-index: 10;
  letter-spacing: 0.5px;
}
</style>
<script>
// =====================================================================
// LIBDROP-TO-SLOT: Library Image → Beat Option Slot (2026-04-25)
// Allows dragging a library card directly onto a beat option slot as the
// accepted image, bypassing FLUX generation.
// Route: POST /api/bg/accept-lib-image (added to production_server.py)
// =====================================================================

// ── 1. Capture-phase drop interceptor ────────────────────────────────
// Fires BEFORE the existing bubble-phase document.drop handler, so we
// can handle .bg-opt slot drops before the beat-card handler converts
// them into reference_image assignments.
document.addEventListener('drop', function (e) {
  "use strict";
  var slot = e.target && e.target.closest && e.target.closest('.bg-opt');
  if (!slot) return;                        // not a slot — let bubble phase handle

  var key = e.dataTransfer && e.dataTransfer.getData('mn-lib-key');
  if (!key) return;

  e.preventDefault();
  e.stopPropagation();                      // prevent bubble-phase beat-card handler

  var libItem = null;
  for (var i = 0; i < MN_LIB_DATA.length; i++) {
    if (MN_LIB_DATA[i].key === key) { libItem = MN_LIB_DATA[i]; break; }
  }
  if (!libItem) {
    console.warn('[LIBDROP] key not found in MN_LIB_DATA:', key);
    return;
  }

  var beatId  = slot.getAttribute('data-beat');
  var slotIdx = parseInt(slot.getAttribute('data-opt') || '0', 10);
  _bgHandleLibSlotDrop(slot, beatId, slotIdx, libItem);

}, true /* capture phase */);

// ── 2. Dragover / dragleave visuals for .bg-opt slots (delegated) ─────
document.addEventListener('dragover', function (e) {
  var types = e.dataTransfer && e.dataTransfer.types;
  if (!types) return;
  var hasLib = (types.indexOf ? types.indexOf('mn-lib-key') !== -1 : types.includes('mn-lib-key'));
  if (!hasLib) return;
  var slot = e.target && e.target.closest && e.target.closest('.bg-opt');
  if (slot) { e.preventDefault(); slot.classList.add('bg-lib-drop-over'); }
}, false);

document.addEventListener('dragleave', function (e) {
  var slot = e.target && e.target.closest && e.target.closest('.bg-opt');
  if (slot && !slot.contains(e.relatedTarget)) {
    slot.classList.remove('bg-lib-drop-over');
  }
}, false);

// ── 3. Core handler ───────────────────────────────────────────────────
function _bgHandleLibSlotDrop(slot, beatId, slotIdx, libItem) {
  "use strict";
  slot.classList.remove('bg-lib-drop-over');

  // Clear prior library badges + chosen state from ALL slots on this beat
  var card = document.getElementById('bg-card-' + beatId);
  if (card) {
    var allSlots = card.querySelectorAll('.bg-opt');
    for (var si = 0; si < allSlots.length; si++) {
      var s = allSlots[si];
      var b = s.querySelector('.bg-lib-badge');
      if (b) b.parentNode.removeChild(b);
      s.classList.remove('bg-lib-chosen', 'chosen');
      // Re-enable Crop on slots that were previously library-assigned
      var cb = s.querySelector('.bg-opt-crop');
      if (cb) cb.disabled = false;
      // Remove lib marker from img
      var im = s.querySelector('img');
      if (im && im.getAttribute('data-lib-key')) {
        im.removeAttribute('data-lib-key');
      }
    }
  }

  // ── Populate TH[] from gallery_b64 — zero server round-trips ────────
  // MN_LIB_DATA always has gallery_b64 (populated by _mnLibFetch on load).
  var b64 = libItem.gallery_b64 || libItem.thumb_b64 || '';
  if (b64) {
    TH[libItem.key] = b64;
  }

  // ── Show image in slot ───────────────────────────────────────────────
  var img = slot.querySelector('img');
  if (!img) {
    img = document.createElement('img');
    slot.insertBefore(img, slot.firstChild);
  }
  if (b64) { img.src = b64; }
  img.setAttribute('data-lib-key', libItem.key);
  img.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:4px;';

  // ── LIB badge ────────────────────────────────────────────────────────
  var badge = document.createElement('span');
  badge.className = 'bg-lib-badge';
  badge.textContent = 'LIB';
  slot.appendChild(badge);
  slot.classList.add('bg-lib-chosen', 'chosen');

  // ── Disable Crop for this slot ───────────────────────────────────────
  // Library images are not FLUX stills — the BG cropper operates on .png
  // files in BG_STILLS_DIR only.  Kim can crop separately via Cropper tab.
  var cropBtn = slot.querySelector('.bg-opt-crop');
  if (cropBtn) cropBtn.disabled = true;

  // ── POST to server: persist accepted_library_ref + accepted_image_key ─
  fetch(BG_SERVER + '/api/bg/accept-lib-image', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      beat_id:    beatId,
      key:        libItem.key,
      filename:   libItem.filename || libItem.key,
      abs_path:   libItem.abs_path || '',
      slot_index: slotIdx
    })
  })
  .then(function (r) { return r.json(); })
  .then(function (d) {
    if (!d.ok) {
      console.error('[LIBDROP] accept-lib-image failed:', d);
      return;
    }
    // ── Update in-memory beat record ─────────────────────────────────
    var beat = null;
    for (var j = 0; j < (BG_BEATS || []).length; j++) {
      if (BG_BEATS[j].beat_id === beatId) { beat = BG_BEATS[j]; break; }
    }
    if (beat) {
      beat.accepted_image_key   = libItem.key;
      beat.accepted_library_ref = {
        key:        libItem.key,
        filename:   libItem.filename || libItem.key,
        abs_path:   libItem.abs_path || '',
        slot_index: slotIdx
      };
      beat.status = 'lib_chosen';
    }

    // ── Enable "Accept All to Storyboard" button ─────────────────────
    var acceptBtn = document.getElementById('bg-accept-btn');
    if (acceptBtn) acceptBtn.disabled = false;

    // ── Update status chip ────────────────────────────────────────────
    var sp = document.getElementById('bg-status-' + beatId);
    if (sp) sp.textContent = 'lib \u2713';
  })
  .catch(function (e) {
    console.error('[LIBDROP] server error:', e);
  });
}

// ── 4. Re-hydration wrapper around _bgRenderBeats ─────────────────────
// After every render, for beats with accepted_library_ref, if TH[] is cold
// (hard refresh), fetch gallery_b64 from /api/cr/full and restore the slot.
(function () {
  "use strict";
  var _prevRender = _bgRenderBeats;

  _bgRenderBeats = function (beats) {
    _prevRender(beats || BG_BEATS);

    var blist = beats || BG_BEATS || [];
    for (var i = 0; i < blist.length; i++) {
      (function (beat) {
        if (!beat || !beat.accepted_library_ref) return;
        var ref     = beat.accepted_library_ref;
        var si      = ref.slot_index || 0;
        var slot    = document.getElementById('bg-opt-' + beat.beat_id + '-' + si);
        if (!slot) return;

        var doRestoreSlot = function (b64OrUrl) {
          var img = slot.querySelector('img');
          if (!img) {
            img = document.createElement('img');
            slot.insertBefore(img, slot.firstChild);
          }
          if (b64OrUrl) img.src = b64OrUrl;
          img.setAttribute('data-lib-key', ref.key);
          // Restore LIB badge if absent (cleared by re-render)
          if (!slot.querySelector('.bg-lib-badge')) {
            var badge = document.createElement('span');
            badge.className = 'bg-lib-badge';
            badge.textContent = 'LIB';
            slot.appendChild(badge);
          }
          slot.classList.add('bg-lib-chosen', 'chosen');
          var cropBtn = slot.querySelector('.bg-opt-crop');
          if (cropBtn) cropBtn.disabled = true;
        };

        if (TH[ref.key]) {
          // TH warm — restore immediately
          doRestoreSlot(TH[ref.key]);
        } else if (ref.abs_path) {
          // TH cold (post hard-refresh) — fetch base64 from server
          fetch(BG_SERVER + '/api/cr/full?abs_path=' + encodeURIComponent(ref.abs_path))
            .then(function (r) { return r.json(); })
            .then(function (d) {
              if (d.data_uri) {
                TH[ref.key] = d.data_uri;
                doRestoreSlot(d.data_uri);
              } else {
                // Fallback: use /files?path= as img.src (byte stream, no TH population)
                doRestoreSlot(BG_SERVER + '/files?path=' + encodeURIComponent(ref.abs_path));
              }
            })
            .catch(function (err) {
              console.warn('[LIBDROP] rehydrate failed for', ref.key, err);
              // Best-effort: direct file stream
              doRestoreSlot(BG_SERVER + '/files?path=' + encodeURIComponent(ref.abs_path || ''));
            });
        }
      })(blist[i]);
    }
  };
})();
// === END LIBDROP-TO-SLOT ===
</script>
"""


def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")
    b64c, b64h = sha256_b64(html)
    print(f"  Base64 blocks: {b64c}, sha256: {b64h}")

    if SENTINEL in html:
        print(f"ERROR: already patched (sentinel '{SENTINEL}' found).")
        sys.exit(1)

    # Backup before any modification
    BACKUP_PATH.write_bytes(HTML_PATH.read_bytes())
    print(f"  Backup written: {BACKUP_PATH.name}")

    # Inject immediately before </body> (or </html> fallback)
    anchor = "</body>" if "</body>" in html else "</html>"
    patched = html.replace(anchor, PATCH + anchor, 1)

    # Safety: base64 payload must be byte-identical
    b64c2, b64h2 = sha256_b64(patched)
    if b64h != b64h2 or b64c != b64c2:
        print("ABORT: base64 fingerprint changed — aborting.")
        sys.exit(1)
    print("  ✓ Base64 byte-identical")

    # Sanity: sentinel count in patched == count in PATCH (original had 0)
    expected = PATCH.count(SENTINEL)
    if patched.count(SENTINEL) != expected:
        print(f"ABORT: sentinel count {patched.count(SENTINEL)} ≠ expected {expected}.")
        sys.exit(1)
    print(f"  ✓ Sentinel present (×{expected})")

    HTML_PATH.write_text(patched, encoding="utf-8")
    print(f"  ✓ Written: {HTML_PATH.name} ({HTML_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
