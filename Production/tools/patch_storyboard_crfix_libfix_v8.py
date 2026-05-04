#!/usr/bin/env python3
"""
Display fix — CRFIX-LIBFIX-V8 (2026-04-25)

Root cause: _bgAcceptFluxOption (LIBFIX-V3) sets beat.accepted_image_key
and updates the status chip but never calls _injectAcceptedPreview because
that function didn't exist when LIBFIX-V3 was written.

Fix: wrap _bgAcceptFluxOption to call window._injectAcceptedPreview(beatId, TH[key])
immediately after the original logic runs. TH[] is already populated by the
time a user clicks the button because _bgRenderBeats filled it when displaying
the flux option slots.
"""

import hashlib, re, sys, tempfile, shutil
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_crfix_libfixv8_backup.html"

SENTINEL = "CRFIX-LIBFIX-V8"


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


PATCH = """\

<script>
// =====================================================================
// CRFIX-LIBFIX-V8: Wire thumbnail into "Use This" accept flow (2026-04-25)
// _bgAcceptFluxOption (LIBFIX-V3) never called _injectAcceptedPreview.
// This wrapper adds that call so the chosen still badge appears immediately.
// =====================================================================
document.addEventListener("DOMContentLoaded", function () {
  var _origAccept = window._bgAcceptFluxOption;
  if (typeof _origAccept !== "function") return;

  window._bgAcceptFluxOption = function (beatId, slotIndex, slotEl) {
    _origAccept.apply(this, arguments);

    // Find the key that was just accepted
    var blist = Array.isArray(BG_BEATS) ? BG_BEATS : [];
    var acceptedKey = null;
    for (var i = 0; i < blist.length; i++) {
      if (blist[i].beat_id === beatId) {
        acceptedKey = blist[i].accepted_image_key;
        break;
      }
    }

    // Inject thumbnail — TH[] is already populated from the render pass
    if (acceptedKey && typeof window._injectAcceptedPreview === "function") {
      var src = (typeof TH !== "undefined") ? TH[acceptedKey] : null;
      if (src) {
        window._injectAcceptedPreview(beatId, src);
      } else {
        // TH cold (unlikely but possible on fresh load): try the slot image directly
        var img = slotEl && slotEl.querySelector("img");
        if (img && img.src) {
          window._injectAcceptedPreview(beatId, img.src);
        }
      }
    }
  };

  console.log("[V8] _bgAcceptFluxOption wrapped — thumbnail will show on Use This.");
});
// === END CRFIX-LIBFIX-V8 ===
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

    if "CRFIX-LIBFIX-V7" not in html:
        print("ERROR: CRFIX-LIBFIX-V7 not found — apply earlier patches first.")
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
    print("  • _bgAcceptFluxOption now calls _injectAcceptedPreview after setting key")
    print("  • Chosen still thumbnail appears immediately when '✓ Use This' is clicked")
    print("  • Fallback: uses slot img.src if TH[] is cold")
    print()
    print("Cmd+Shift+R to reload, then click '✓ Use This' on any option.")


if __name__ == "__main__":
    main()
