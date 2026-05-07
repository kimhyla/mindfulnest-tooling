#!/usr/bin/env python3
"""
Display fix — CRFIX-LIBFIX-V10 (2026-04-25)

Root cause: the library-drop acceptance path (LIBDROP-TO-SLOT) sets
beat.accepted_image_key and updates the status chip to "lib ✓" but
never calls _injectAcceptedPreview — so the green-bordered thumbnail
never appears in the beat card header after a lib drag-drop.

The FLUX option path (V8) was already fixed. This V10 fixes the lib path.

Fix: intercept /api/bg/accept-lib-image fetch responses; extract abs_path
from the request body; call /api/cr/full?abs_path=... to get the full-res
data URI; inject it via _injectAcceptedPreview.
"""

import hashlib, re, sys, tempfile, shutil
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_pre_crfix_libfixv10_backup.html"

SENTINEL = "CRFIX-LIBFIX-V10"


def sha256_b64(html: str):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()


PATCH = """\

<script>
// =====================================================================
// CRFIX-LIBFIX-V10: Inject thumbnail after library-drop acceptance (2026-04-25)
// LIBDROP-TO-SLOT sets "lib ✓" status chip but never calls _injectAcceptedPreview.
// This interceptor catches /api/bg/accept-lib-image responses, fetches the
// full-res image via /api/cr/full?abs_path=..., and injects the thumbnail.
// =====================================================================
document.addEventListener("DOMContentLoaded", function () {
  var _origFetch = window.fetch;

  window.fetch = function (url, opts) {
    var p = _origFetch.apply(this, arguments);

    if (typeof url === "string" && url.indexOf("/api/bg/accept-lib-image") !== -1) {
      // Parse the request body to get beat_id and abs_path
      var beatId  = null;
      var absPath = null;
      var libKey  = null;
      try {
        var body = JSON.parse((opts && opts.body) || "{}");
        beatId  = body.beat_id  || null;
        absPath = body.abs_path || null;
        libKey  = body.key      || null;
      } catch (e) { /* malformed body — skip */ }

      if (beatId && (absPath || libKey)) {
        p = p.then(function (resp) {
          var respClone = resp.clone();
          respClone.json().then(function (d) {
            if (!d || !d.ok) return;

            // Try TH[] first (free if the image was already loaded)
            var src = (typeof TH !== "undefined" && libKey) ? TH[libKey] : null;

            if (src && typeof window._injectAcceptedPreview === "function") {
              window._injectAcceptedPreview(beatId, src);
              return;
            }

            // Fallback: fetch full-res from server using abs_path
            if (!absPath) return;
            _origFetch(BG_SERVER + "/api/cr/full?abs_path=" + encodeURIComponent(absPath))
              .then(function (r) { return r.json(); })
              .then(function (imgd) {
                var imgSrc = imgd && imgd.data_uri;
                if (!imgSrc) return;
                // Cache in TH[] for future re-renders
                if (libKey && typeof TH !== "undefined") TH[libKey] = imgSrc;
                if (typeof window._injectAcceptedPreview === "function") {
                  window._injectAcceptedPreview(beatId, imgSrc);
                }
              })
              .catch(function (e) {
                console.warn("[V10] /api/cr/full fetch failed:", e);
              });
          }).catch(function () {});
          return resp;
        });
      }
    }

    return p;
  };

  console.log("[V10] /api/bg/accept-lib-image intercepted — lib thumbnail will inject on drop.");
});
// === END CRFIX-LIBFIX-V10 ===
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

    if "CRFIX-LIBFIX-V9" not in html:
        print("ERROR: CRFIX-LIBFIX-V9 not found — apply earlier patches first.")
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
    print("  • /api/bg/accept-lib-image responses now intercepted")
    print("  • After successful lib drop: fetches full-res via /api/cr/full?abs_path=...")
    print("  • Calls _injectAcceptedPreview(beatId, data_uri) → green thumbnail appears")
    print("  • Caches in TH[] so future re-renders can also find it")
    print()
    print("Cmd+Shift+R to reload, then drag a library image onto an option slot.")


if __name__ == "__main__":
    main()
