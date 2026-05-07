#!/usr/bin/env python3
"""
Path B patch — Fix-G: Segment click persists beats (2026-04-25)
Root cause: _bgLoadSegments() segment onclick clears BG_BEATS=[] and calls
_bgRenderBeats([]) immediately — never checks sidecar for previously saved beats.
Every click requires re-extraction even when beats were already saved.

Fix: wrap _bgLoadSegments so segment item onclick calls /api/bg/set-active-context
(new server endpoint) which returns saved beats. If beats found → render them.
If none → show "Extract Beats" prompt as before (no regression).
"""

import hashlib, re, sys
from pathlib import Path

PROJECT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
HTML_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod.html"
BACKUP_PATH = PROJECT / "Production/Event_1/storyboard_v43_prod_prefixg_backup.html"

def sha256_b64(html):
    b64s = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', html)
    return len(b64s), hashlib.sha256(("".join(b64s)).encode()).hexdigest()

PATCH = """\

<script>
// =====================================================================
// FIX-G SEGMENT CLICK PERSISTENCE (2026-04-25)
// Root cause: _bgLoadSegments segment onclick did BG_BEATS=[]; _bgRenderBeats([])
// immediately, discarding any previously saved beats for that segment.
// Fix: wrap _bgLoadSegments to use /api/bg/set-active-context which returns
// saved beats from the sidecar. Renders them if found; shows empty prompt if not.
// =====================================================================
(function () {
  "use strict";

  var _bgLoadSegments_orig = _bgLoadSegments;

  window._bgLoadSegments = _bgLoadSegments = function (arcNum) {
    fetch(BG_SERVER + "/api/bg/segments?arc_number=" + arcNum)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var list = document.getElementById("bg-seg-list");
        if (!list) return;
        list.innerHTML = "";
        var wrap = document.getElementById("bg-seg-wrap");
        if (wrap) wrap.style.display = "block";

        (d.segments || []).forEach(function (seg) {
          var item = document.createElement("div");
          item.className = "bg-seg-item";
          item.textContent = seg.name;

          item.onclick = function () {
            document.querySelectorAll(".bg-seg-item").forEach(function (x) {
              x.classList.remove("sel");
            });
            this.classList.add("sel");
            BG_SEG = seg;
            BG_ARC = arcNum;

            var acts = document.getElementById("bg-actions");
            if (acts) acts.style.display = "flex";

            // Show loading state while we check sidecar
            var container = document.getElementById("bg-beats");
            if (container) {
              container.innerHTML = '<div class="bg-empty">Loading\u2026</div>';
            }

            // Ask server to switch active context + return any saved beats
            fetch(BG_SERVER + "/api/bg/set-active-context", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                arc_number: arcNum,
                event_id: seg.event_id,
                phase: seg.phase || "full"
              })
            })
              .then(function (r) { return r.json(); })
              .then(function (data) {
                var saved = data.beats || [];
                BG_BEATS = saved;
                _bgRenderBeats(BG_BEATS);

                var genBtn = document.getElementById("bg-gen-all-btn");
                var acceptBtn = document.getElementById("bg-accept-btn");
                if (genBtn) genBtn.disabled = BG_BEATS.length === 0;
                if (acceptBtn) acceptBtn.disabled = BG_BEATS.length === 0;
              })
              .catch(function (e) {
                console.error("[BG] set-active-context error:", e);
                BG_BEATS = [];
                _bgRenderBeats([]);
              });
          };

          list.appendChild(item);
        });

        if (typeof _bgLoadGroups === "function") _bgLoadGroups(arcNum);
      })
      .catch(function (e) { console.error("[BG] segments error:", e); });
  };

})();
// === END FIX-G SEGMENT CLICK PERSISTENCE ===
</script>
"""

def main():
    print(f"Reading {HTML_PATH.name}...")
    html = HTML_PATH.read_text(encoding="utf-8")
    b64c, b64h = sha256_b64(html)
    print(f"  Base64 blocks: {b64c}, sha256: {b64h}")

    if "FIX-G SEGMENT CLICK PERSISTENCE" in html:
        print("ERROR: already patched.")
        sys.exit(1)

    BACKUP_PATH.write_bytes(HTML_PATH.read_bytes())
    print(f"  Backup: {BACKUP_PATH.name}")

    anchor = "</body>" if "</body>" in html else "</html>"
    patched = html.replace(anchor, PATCH + anchor, 1)

    b64c2, b64h2 = sha256_b64(patched)
    if b64h != b64h2 or b64c != b64c2:
        print("ABORT: base64 changed."); sys.exit(1)
    print("  ✓ Base64 byte-identical")

    HTML_PATH.write_text(patched, encoding="utf-8")
    print(f"  ✓ Written: {HTML_PATH.name} ({HTML_PATH.stat().st_size // 1024} KB)")

if __name__ == "__main__":
    main()
