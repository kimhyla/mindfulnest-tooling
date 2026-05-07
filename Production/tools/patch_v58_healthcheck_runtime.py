#!/usr/bin/env python3
"""
Path B patch: storyboard v57 -> v58 — Fix-W.

INVARIANTS:
  - Patches v57 only (must contain _fixPInited..._fixV_installed)
  - </html> last-position structural close
  - Idempotency via _fixW_installed
  - SHA256 base64 byte-identical
  - Server-side /api/patch_health endpoint deployed first (Patch 3 prereq)

Fix-W (LD-pending PATCH_INVARIANT_PERSISTENCE_V1):
  Implements CLAUDE.md Rule 36 §36.3 runtime healthcheck.

  Registers window.__patchHealth array of assertion objects, one per prior
  Fix-X. Provides window.__patchHealthcheck() that runs all assertions on
  DOMContentLoaded+500ms and reports failures via console.warn + POST
  to /api/patch_health (logged to prod_activity_log).

  Each assertion has:
    - patch: "Fix-X" identifier
    - check: () => bool (true = invariant holds, false = violated)
    - msg: human-readable description for telemetry

Phase 0 preflight 187 (LD-pending PATCH_INVARIANT_PERSISTENCE_V1).
"""
import hashlib, os, re, sys
from pathlib import Path

_EVENT_DIR = Path(__file__).parent.parent / "Event_1"
SRC  = _EVENT_DIR / "storyboard_v57_prod.html"
DEST = _EVENT_DIR / "storyboard_v58_prod.html"
TMP  = _EVENT_DIR / "storyboard_v58_prod.html.tmp"

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

if "_fixW_installed" in html:
    print("ERROR: _fixW_installed already present", file=sys.stderr); sys.exit(2)

for sentinel, name in (("_fixPInited","P"), ("_fixQ_installed","Q"),
                       ("_fixR_installed","R"), ("_fixS_installed","S"),
                       ("_fixT_installed","T"), ("_fixU_installed","U"),
                       ("_fixV_installed","V")):
    if sentinel not in html:
        print(f"ERROR: source missing {sentinel} (Fix-{name}) — not v57", file=sys.stderr); sys.exit(2)
print("  Sentinel gate: P/Q/R/S/T/U/V all present")


def b64_sig(text):
    blobs = re.findall(r'base64,([A-Za-z0-9+/=]{100,})', text)
    h = hashlib.sha256()
    for b in blobs: h.update(b.encode())
    return h.hexdigest(), len(blobs)


hash_before, count_before = b64_sig(html)
print(f"Base64 blobs before: {count_before}, sha256: {hash_before[:16]}...")


FIX_W = r"""
<script>
// =====================================================================
// Fix-W: Rule 36 PATCH_INVARIANT_PERSISTENCE_V1 runtime healthcheck
// (2026-05-02)
//
// INVARIANTS:
//   - Server endpoint POST /api/patch_health deployed (production_server.py).
//   - Each assertion below tests an invariant a prior patch depended on.
//   - Assertions run after DOMContentLoaded + 500ms — non-blocking.
//   - Failures: console.warn + POST to /api/patch_health (logged to
//     prod_activity_log action=patch_invariant_violation).
//
// Per CLAUDE.md Rule 36 §36.3.
// LD: PATCH_INVARIANT_PERSISTENCE_V1 (preflight 187)
// =====================================================================
(function FixW() {
  "use strict";
  if (window._fixW_installed) return;
  window._fixW_installed = true;
  console.log("[Fix-W] Rule 36 healthcheck registered");

  window.__patchHealth = window.__patchHealth || [];

  // ── Assertions per prior patch ──────────────────────────────────────
  // Format: { patch: "Fix-X", check: () => bool, msg: "..." }
  // Each check returns true if invariant holds, false if violated.
  window.__patchHealth.push(
    {
      patch: "Fix-P (LD-446)",
      check: function () { return window._fixPInited === true; },
      msg: "Fix-P sentinel _fixPInited not set — library lib-drop fix may have regressed"
    },
    {
      patch: "Fix-Q (LD-447)",
      check: function () { return window._fixQ_installed === true; },
      msg: "Fix-Q sentinel _fixQ_installed not set — dialogue/image save visibility may have regressed"
    },
    {
      patch: "Fix-R (LD-448)",
      check: function () { return window._fixR_installed === true; },
      msg: "Fix-R sentinel _fixR_installed not set — lib-image crop routing may have regressed"
    },
    {
      patch: "Fix-S (LD-449)",
      check: function () { return window._fixS_installed === true; },
      msg: "Fix-S sentinel _fixS_installed not set — disabled-cropBtn observer may have regressed"
    },
    {
      patch: "Fix-T (LD-450)",
      check: function () { return window._fixT_installed === true; },
      msg: "Fix-T sentinel _fixT_installed not set — lib CSS regressions fix may have regressed"
    },
    {
      patch: "Fix-T size constraint (Bug 1 — Add Image button)",
      check: function () {
        var labels = document.querySelectorAll("label.mn-lib-upload-btn");
        for (var i = 0; i < labels.length; i++) {
          if (labels[i].offsetHeight > 60) return false;
        }
        return true;
      },
      msg: "label.mn-lib-upload-btn rendered taller than 60px — Fix-T/V7 height constraint regression"
    },
    {
      patch: "Fix-U (LD-451) sentinel",
      check: function () { return window._fixU_installed === true; },
      msg: "Fix-U sentinel not set — scroll-reset wrap may have regressed"
    },
    {
      patch: "Fix-U scrollable element",
      check: function () {
        var inner = document.getElementById("mn-lib-scroll-inner");
        if (!inner) return false;
        var cs = getComputedStyle(inner);
        return cs.overflowY === "auto" || cs.overflowY === "scroll";
      },
      msg: "#mn-lib-scroll-inner missing or not scrollable — Fix-U scroll-reset target invariant broken"
    },
    {
      patch: "Fix-V (LD-452) sentinel",
      check: function () { return window._fixV_installed === true; },
      msg: "Fix-V sentinel not set — library delete UI may have regressed"
    }
  );

  // ── The healthcheck runner ──────────────────────────────────────────
  window.__patchHealthcheck = function () {
    var failures = [];
    for (var i = 0; i < window.__patchHealth.length; i++) {
      var entry = window.__patchHealth[i];
      try {
        if (!entry.check()) {
          failures.push({ patch: entry.patch, msg: entry.msg });
        }
      } catch (err) {
        failures.push({
          patch: entry.patch,
          msg: "assertion threw: " + (err && err.message || err)
        });
      }
    }
    if (failures.length > 0) {
      console.warn("[Fix-W] " + failures.length + " patch invariant violation(s):");
      failures.forEach(function (f) {
        console.warn("  " + f.patch + " — " + f.msg);
        // Best-effort POST to server (logged to prod_activity_log)
        try {
          fetch("http://localhost:5111/api/patch_health", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ patch: f.patch, msg: f.msg })
          }).catch(function () {});
        } catch (e) { /* offline/no-server — silent */ }
      });
    } else {
      console.log("[Fix-W] all " + window.__patchHealth.length
        + " patch invariants holding ✓");
    }
    return { passed: window.__patchHealth.length - failures.length, failed: failures.length, failures: failures };
  };

  // Auto-run after DCL + 500ms
  function _scheduleCheck() {
    setTimeout(window.__patchHealthcheck, 500);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _scheduleCheck);
  } else {
    _scheduleCheck();
  }
})();
// === END Fix-W ===
</script>
"""

MARKER = "</html>"
pos = html.rfind(MARKER)
patched = html[:pos] + FIX_W + html[pos:]
print(f"Injected Fix-W ({len(FIX_W):,} chars)")

hash_after, count_after = b64_sig(patched)
if hash_before != hash_after or count_before != count_after:
    print("INTEGRITY FAIL", file=sys.stderr); sys.exit(3)
print(f"Base64 verified: {count_after} blobs unchanged")

TMP.write_text(patched, encoding="utf-8")
verify = TMP.read_text(encoding="utf-8")
hv, cv = b64_sig(verify)
if hv != hash_after or cv != count_after:
    TMP.unlink(missing_ok=True); sys.exit(4)
for s in ("_fixPInited", "_fixQ_installed", "_fixR_installed",
          "_fixS_installed", "_fixT_installed", "_fixU_installed",
          "_fixV_installed", "_fixW_installed"):
    if s not in verify:
        print(f"VERIFY FAIL — missing {s}", file=sys.stderr); TMP.unlink(missing_ok=True); sys.exit(4)
print("Tmp readback verified, all 8 sentinels (P/Q/R/S/T/U/V/W) present")

os.replace(TMP, DEST)
print(f"\nPatch complete.")
print(f"  Source:  {SRC.name} ({len(html):,} chars)")
print(f"  Output:  {DEST.name} ({len(patched):,} chars)")
print(f"  Delta:   +{len(patched) - len(html):,} chars")
