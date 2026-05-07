#!/usr/bin/env python3
"""
Phase 1.5 — Wire 4 widget handlers to route through window.pathappPatch(beatId, field, value).

Path A++ continuation of Phase 1 (which shipped window.pathappPatch + save-indicator CSS).
This patcher targets <script> and <style> blocks ONLY and asserts byte-identical base64
image data URIs before/after. No structural HTML changes.

Widgets wired:
  1. Dialogue textarea onblur    -> pathappPatch(beatId, 'dialogue', text)
  2. Drop-to-assign-image drop   -> pathappPatch(beatId, 'image_override', image_key)
  3. A/B/C radio select          -> pathappPatch(beatId, 'selected_option', optNum)
  4. Trim start/end slider       -> pathappPatch(beatId, 'trim_start'|'trim_end', v)

Behavior:
  * Every wired handler shows a yellow (saving) indicator immediately.
  * On v2 200 -> green (saved) pulse.
  * On v2 503 -> falls back to legacy handler (existing fetch to /api/beat/...).
  * On conflict (409) / network error -> red (error) indicator + console.warn.
  * If window.pathappPatch is undefined for any reason, original handler runs.

Writes output in-place (v38 stays v38). Auto-creates timestamped backup first.

Rule 7 Path B compliance: base64 data URIs extracted, SHA256'd, asserted identical
before/after. If any drift, script restores backup and exits non-zero.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
V38 = PROJECT_ROOT / "Production" / "Event_1" / "storyboard_v38_prod.html"
TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
BACKUP = V38.with_suffix(f".html.bak_phase1_5_{TS}")

# -----------------------------------------------------------------------------
# Base64 extraction + integrity check
# -----------------------------------------------------------------------------
# Matches data:image/...;base64,AAA...  up to the closing quote/paren.
# We pull the actual base64 payload and SHA256 it so we can diff
# the set of base64 blobs before vs after patching.
DATA_URI_RE = re.compile(r"data:image/[a-zA-Z0-9.+-]+;base64,([A-Za-z0-9+/=]+)")


def base64_fingerprints(text: str) -> list[str]:
    """SHA256 every base64 image payload in the text, return sorted list."""
    payloads = DATA_URI_RE.findall(text)
    hashes = [hashlib.sha256(p.encode("ascii")).hexdigest() for p in payloads]
    hashes.sort()
    return hashes


# -----------------------------------------------------------------------------
# JS snippets injected for widget wiring
# -----------------------------------------------------------------------------
# Helper used by every wired widget. Defined once, reused everywhere.
# Placed at top of the file after pathappPatch is exposed (window.pathappPatch).
PATHAPP_WIRING_HELPER = """
<!-- BEGIN Phase 1.5 widget-wiring helpers (injected __TS__) -->
<style>
  /* Extra pulse animations for save indicators — Phase 1.5.
     Phase 1 shipped color-only states; this adds a subtle pulse so
     Kim's eye is drawn to the indicator when a save is in flight. */
  @keyframes pathapp-pulse-yellow {
    0%   { opacity: 0.5; }
    50%  { opacity: 1.0; }
    100% { opacity: 0.5; }
  }
  @keyframes pathapp-pulse-green {
    0%   { opacity: 1.0; transform: scale(1.0); }
    40%  { opacity: 1.0; transform: scale(1.15); }
    100% { opacity: 1.0; transform: scale(1.0); }
  }
  .pathapp-saveind.saving {
    animation: pathapp-pulse-yellow 1.2s ease-in-out infinite;
  }
  .pathapp-saveind.saved {
    animation: pathapp-pulse-green 1.5s ease-out 1;
  }
  .pathapp-saveind.error {
    /* solid red, no pulse — keep eye on it until user acts */
    animation: none;
  }
</style>
<script>
(function() {
  /* Phase 1.5 widget wiring — routes 4 widgets through window.pathappPatch.
     Defined lazily: each wired handler calls window.pathappPatch at invocation
     time (not bind time), so ordering with Phase 1 boot is irrelevant. */

  // beat_NN helper — matches existing idiom ("beat_"+String(idx+1).padStart(2,"0"))
  function _beatId(idx) {
    var s = String(idx + 1);
    if (s.length < 2) s = "0" + s;
    return "beat_" + s;
  }

  // Ensure a save-indicator span exists for a row. Reuses dialogue's
  // existing <span id="saveindN"> where present; creates a new
  // .pathapp-saveind span next to the widget otherwise.
  function _ensureSaveInd(widgetEl, rowIdx, kind) {
    var existing = document.getElementById("saveind" + rowIdx);
    if (existing) {
      if (!existing.classList.contains("pathapp-saveind")) {
        existing.classList.add("pathapp-saveind");
      }
      return existing;
    }
    // Widget-local indicator keyed by kind+row to avoid collisions.
    var pid = kind + "_" + rowIdx;
    var selector = '.pathapp-saveind[data-pid="' + pid + '"]';
    var parent = widgetEl && widgetEl.parentNode;
    if (!parent) return null;
    var span = parent.querySelector(selector);
    if (span) return span;
    span = document.createElement("span");
    span.className = "pathapp-saveind";
    span.setAttribute("data-pid", pid);
    span.style.marginLeft = "6px";
    parent.appendChild(span);
    return span;
  }

  // Fire-and-observe: call pathappPatch; run legacy on 503 or when missing.
  function _routedPatch(beatId, field, value, saveIndSpan, legacyFn) {
    if (typeof window.pathappPatch !== "function") {
      // Phase 1 missing — run legacy directly.
      try { legacyFn && legacyFn(); } catch (e) { console.warn("[phase1.5] legacy call failed:", e); }
      return;
    }
    try {
      var p = window.pathappPatch(beatId, field, value, {
        saveind: saveIndSpan,
        legacyFallback: legacyFn,
      });
      // pathappPatch returns a Promise that resolves to { status, ... }
      if (p && typeof p.then === "function") {
        p.then(function(result) {
          // On 503 the helper already ran legacyFallback internally.
          // On 409 or other errors the save-ind already shows red.
          // No extra action needed here — this .then is a safety hook.
        }).catch(function(err) {
          console.warn("[phase1.5]", field, "patch threw:", err);
        });
      }
    } catch (e) {
      console.warn("[phase1.5] pathappPatch threw synchronously:", e);
      try { legacyFn && legacyFn(); } catch (e2) {}
    }
  }

  // Expose for the wired handlers below.
  window._pathappWire = {
    beatId: _beatId,
    ensureSaveInd: _ensureSaveInd,
    routedPatch: _routedPatch,
  };
})();
</script>
<!-- END Phase 1.5 widget-wiring helpers -->
""".replace("__TS__", TS)


# -----------------------------------------------------------------------------
# Widget 1: Dialogue onblur
# -----------------------------------------------------------------------------
# Original (line 177, one line):
#   ta.onblur=function(){var idx=parseInt(this.getAttribute("data-i"));var bid="beat_"+(idx<9?"0":"")+(idx+1);var txt=this.value;var si=document.getElementById("saveind"+idx);...};
#
# Strategy: wrap the whole onblur. Call pathappPatch first with legacyFallback =
# the original body. pathappPatch handles save-ind (saving/saved/error). The
# legacy fallback only fires on 503 (rollback mode) — it's the full original
# fetch to /api/beat/update_text which also regenerates audio.

DIALOGUE_OLD = r'ta.onblur=function(){var idx=parseInt(this.getAttribute("data-i"));var bid="beat_"+(idx<9?"0":"")+(idx+1);var txt=this.value;var si=document.getElementById("saveind"+idx);if(si){si.textContent="💾 saving + 🎙 regenerating audio (5–8s)…";si.style.color="#888";}fetch(SERVER+"/api/beat/update_text",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({beat:bid,text:txt})}).then(function(r){return r.json();}).then(function(d){if(!si)return;if(d.error){si.textContent="✗ "+d.error.substring(0,60);si.style.color="#e74c3c";return;}var tr=d.tts_regen||{};if(tr.ok){si.textContent="✓ saved + 🎙 audio regen ("+(tr.audio_duration_s||0).toFixed(2)+"s, "+(tr.elapsed_s||0).toFixed(1)+"s call)";si.style.color="#2ecc71";}else if(tr.skipped){si.textContent="✓ saved"+(tr.reason==="no_text_change"?"":" ("+tr.reason+")");si.style.color="#2ecc71";}else{si.textContent="✓ saved but 🎙✗ audio regen failed: "+((tr.error||"unknown").substring(0,60));si.style.color="#f39c12";}}).catch(function(err){if(si){si.textContent="✗ "+err.message;si.style.color="#e74c3c";}});};'

DIALOGUE_NEW = r'''ta.onblur=function(){var self=this;var idx=parseInt(self.getAttribute("data-i"));var bid="beat_"+(idx<9?"0":"")+(idx+1);var txt=self.value;var si=document.getElementById("saveind"+idx);if(si&&!si.classList.contains("pathapp-saveind"))si.classList.add("pathapp-saveind");var legacyBlurFallback=function(){if(si){si.textContent="💾 saving + 🎙 regenerating audio (5–8s)…";si.style.color="#888";}fetch(SERVER+"/api/beat/update_text",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({beat:bid,text:txt})}).then(function(r){return r.json();}).then(function(d){if(!si)return;if(d.error){si.textContent="✗ "+d.error.substring(0,60);si.style.color="#e74c3c";return;}var tr=d.tts_regen||{};if(tr.ok){si.textContent="✓ saved + 🎙 audio regen ("+(tr.audio_duration_s||0).toFixed(2)+"s, "+(tr.elapsed_s||0).toFixed(1)+"s call)";si.style.color="#2ecc71";}else if(tr.skipped){si.textContent="✓ saved"+(tr.reason==="no_text_change"?"":" ("+tr.reason+")");si.style.color="#2ecc71";}else{si.textContent="✓ saved but 🎙✗ audio regen failed: "+((tr.error||"unknown").substring(0,60));si.style.color="#f39c12";}}).catch(function(err){if(si){si.textContent="✗ "+err.message;si.style.color="#e74c3c";}});};if(window._pathappWire&&typeof window.pathappPatch==="function"){window._pathappWire.routedPatch(bid,"dialogue",txt,si,legacyBlurFallback);}else{legacyBlurFallback();}};'''


# -----------------------------------------------------------------------------
# Widget 2: Drop handler (image override)
# -----------------------------------------------------------------------------
# Original (lines 386-393):
#   row.addEventListener("drop",function(e){
#     e.preventDefault();this.classList.remove("drop-target");
#     var key=e.dataTransfer.getData("text/plain");
#     if(!key)return;
#     var idx=parseInt(this.id.replace("r",""));
#     if(!isNaN(idx)&&idx>=0&&idx<L.length){L[idx].i=key;render();
#     fetch("http://localhost:5111/api/assign-image",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({beat:"beat_"+String(idx+1).padStart(2,"0"),image_key:key})}).catch(function(){});}
#   });

DROP_OLD = '''      row.addEventListener("drop",function(e){
        e.preventDefault();this.classList.remove("drop-target");
        var key=e.dataTransfer.getData("text/plain");
        if(!key)return;
        var idx=parseInt(this.id.replace("r",""));
        if(!isNaN(idx)&&idx>=0&&idx<L.length){L[idx].i=key;render();
        fetch("http://localhost:5111/api/assign-image",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({beat:"beat_"+String(idx+1).padStart(2,"0"),image_key:key})}).catch(function(){});}
      });'''

DROP_NEW = '''      row.addEventListener("drop",function(e){
        e.preventDefault();this.classList.remove("drop-target");
        var key=e.dataTransfer.getData("text/plain");
        if(!key)return;
        var idx=parseInt(this.id.replace("r",""));
        if(!isNaN(idx)&&idx>=0&&idx<L.length){L[idx].i=key;render();
        var _bid_drop="beat_"+String(idx+1).padStart(2,"0");
        var _dropLegacy=function(){fetch("http://localhost:5111/api/assign-image",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({beat:_bid_drop,image_key:key})}).catch(function(){});};
        var _dropRow=document.getElementById("r"+idx);
        var _dropSi=(window._pathappWire&&window._pathappWire.ensureSaveInd)?window._pathappWire.ensureSaveInd(_dropRow,idx,"drop"):null;
        if(window._pathappWire&&typeof window.pathappPatch==="function"){window._pathappWire.routedPatch(_bid_drop,"image_override",key,_dropSi,_dropLegacy);}else{_dropLegacy();}}
      });'''


# -----------------------------------------------------------------------------
# Widget 3: A/B/C pick button — selectBeat()
# -----------------------------------------------------------------------------
# Original (line 1207-1213):
#   function selectBeat(beat, option) {
#       api("/api/select", {
#           method: "POST",
#           headers: { "Content-Type": "application/json" },
#           body: JSON.stringify({ beat: beat, selected_option: option })
#       }).then(pollStatus);
#   }

SELECT_OLD = '''    function selectBeat(beat, option) {
        api("/api/select", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ beat: beat, selected_option: option })
        }).then(pollStatus);
    }'''

SELECT_NEW = '''    function selectBeat(beat, option) {
        // Phase 1.5: route through v2 pathappPatch; keep legacy /api/select as fallback.
        var _selectLegacy = function() {
            api("/api/select", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ beat: beat, selected_option: option })
            }).then(pollStatus);
        };
        // Try to find an existing radio for this beat+option to anchor the save-ind near.
        var _anchorEl = document.querySelector('input[type="radio"][name="sel-' + beat + '"]');
        var _selectIdx = parseInt(String(beat).replace(/^beat_/, ""), 10) - 1;
        var _selectSi = null;
        if (window._pathappWire && window._pathappWire.ensureSaveInd && _anchorEl) {
            _selectSi = window._pathappWire.ensureSaveInd(_anchorEl, _selectIdx, "select");
        }
        if (window._pathappWire && typeof window.pathappPatch === "function") {
            window._pathappWire.routedPatch(beat, "selected_option", option, _selectSi, _selectLegacy);
            // Also fire pollStatus so the video swap happens regardless of v2 result.
            setTimeout(function() { try { pollStatus(); } catch (e) {} }, 200);
        } else {
            _selectLegacy();
        }
    }'''


# -----------------------------------------------------------------------------
# Widget 4: Trim sliders (trim_start + trim_end onchange)
# -----------------------------------------------------------------------------
# Originals at lines 1053 (tss.onchange) and 1071 (tes.onchange).

TRIM_START_OLD = '''                tss.onchange = function() {
                    var v = parseFloat(this.value);
                    var endV = window._beatTrims[ri].end || null;
                    fetch(SERVER + "/api/beat/trim", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ beat: bk, trim_start: v, trim_end: endV })
                    }).catch(function(e) { console.error("trim save:", e); });
                };'''

TRIM_START_NEW = '''                tss.onchange = function() {
                    var v = parseFloat(this.value);
                    var endV = window._beatTrims[ri].end || null;
                    var _trimStartLegacy = function() {
                        fetch(SERVER + "/api/beat/trim", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ beat: bk, trim_start: v, trim_end: endV })
                        }).catch(function(e) { console.error("trim save:", e); });
                    };
                    var _trimStartSi = (window._pathappWire && window._pathappWire.ensureSaveInd)
                        ? window._pathappWire.ensureSaveInd(tss, ri, "trimStart") : null;
                    if (window._pathappWire && typeof window.pathappPatch === "function") {
                        window._pathappWire.routedPatch(bk, "trim_start", v, _trimStartSi, _trimStartLegacy);
                    } else {
                        _trimStartLegacy();
                    }
                };'''

TRIM_END_OLD = '''                tes.onchange = function() {
                    var v = parseFloat(this.value);
                    var startV = window._beatTrims[ri].start || 0;
                    fetch(SERVER + "/api/beat/trim", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ beat: bk, trim_start: startV, trim_end: v })
                    }).catch(function(e) { console.error("trim save:", e); });
                };'''

TRIM_END_NEW = '''                tes.onchange = function() {
                    var v = parseFloat(this.value);
                    var startV = window._beatTrims[ri].start || 0;
                    var _trimEndLegacy = function() {
                        fetch(SERVER + "/api/beat/trim", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ beat: bk, trim_start: startV, trim_end: v })
                        }).catch(function(e) { console.error("trim save:", e); });
                    };
                    var _trimEndSi = (window._pathappWire && window._pathappWire.ensureSaveInd)
                        ? window._pathappWire.ensureSaveInd(tes, ri, "trimEnd") : null;
                    if (window._pathappWire && typeof window.pathappPatch === "function") {
                        window._pathappWire.routedPatch(bk, "trim_end", v, _trimEndSi, _trimEndLegacy);
                    } else {
                        _trimEndLegacy();
                    }
                };'''


# -----------------------------------------------------------------------------
# Patch orchestration
# -----------------------------------------------------------------------------

REPLACEMENTS = [
    ("dialogue_onblur", DIALOGUE_OLD, DIALOGUE_NEW),
    ("drop_handler", DROP_OLD, DROP_NEW),
    ("select_beat", SELECT_OLD, SELECT_NEW),
    ("trim_start", TRIM_START_OLD, TRIM_START_NEW),
    ("trim_end", TRIM_END_OLD, TRIM_END_NEW),
]


def main() -> int:
    if not V38.exists():
        print(f"FATAL: v38 not found at {V38}", file=sys.stderr)
        return 2

    original = V38.read_text(encoding="utf-8")

    # Fingerprint ALL base64 image data URIs BEFORE patch.
    before_hashes = base64_fingerprints(original)
    print(f"[phase1.5] base64 image count BEFORE: {len(before_hashes)}")

    # Create backup.
    shutil.copyfile(V38, BACKUP)
    print(f"[phase1.5] backup written: {BACKUP.name}")

    # Apply each replacement; each must match exactly once.
    patched = original
    for name, old, new in REPLACEMENTS:
        count = patched.count(old)
        if count != 1:
            print(
                f"FATAL: replacement '{name}' matched {count} times (expected 1). "
                "Aborting. Backup preserved; v38 untouched.",
                file=sys.stderr,
            )
            return 3
        patched = patched.replace(old, new, 1)
        print(f"[phase1.5] applied: {name}")

    # Inject the wiring-helper style+script block.
    # Place AFTER the Phase 1 <script> block that ends with "pathappHydrate();" + its </script>.
    # We anchor on the closing </script> of the Phase 1 block which is unique.
    phase1_end_marker = (
        "  // Run hydration on DOM ready\n"
        "  if (document.readyState === \"loading\") {\n"
        "    document.addEventListener(\"DOMContentLoaded\", pathappHydrate);\n"
        "  } else {\n"
        "    pathappHydrate();\n"
        "  }\n"
        "})();\n"
        "</script>"
    )
    if patched.count(phase1_end_marker) != 1:
        print(
            f"FATAL: Phase 1 end-marker not found uniquely (found {patched.count(phase1_end_marker)}). "
            "Cannot place wiring helper.",
            file=sys.stderr,
        )
        return 4
    patched = patched.replace(
        phase1_end_marker,
        phase1_end_marker + "\n" + PATHAPP_WIRING_HELPER,
        1,
    )
    print("[phase1.5] injected wiring-helper block after Phase 1 boot")

    # Fingerprint AFTER patch and assert byte-identical image set.
    after_hashes = base64_fingerprints(patched)
    print(f"[phase1.5] base64 image count AFTER:  {len(after_hashes)}")

    if before_hashes != after_hashes:
        print(
            "FATAL: base64 image fingerprints differ before vs after. "
            "Restoring backup and aborting.",
            file=sys.stderr,
        )
        # Restore from backup (backup already == original on disk).
        shutil.copyfile(BACKUP, V38)
        # Diff summary
        before_set = set(before_hashes)
        after_set = set(after_hashes)
        missing = before_set - after_set
        extra = after_set - before_set
        print(f"  missing hashes: {len(missing)}", file=sys.stderr)
        print(f"  extra hashes:   {len(extra)}", file=sys.stderr)
        return 5

    # All base64 data URIs survived byte-identical. Safe to write.
    V38.write_text(patched, encoding="utf-8")

    # Combined SHA over every base64 payload — the value we report in the morning note.
    combined = hashlib.sha256(("\n".join(before_hashes)).encode("ascii")).hexdigest()
    print(f"[phase1.5] combined base64-fingerprint SHA256: {combined}")
    print(f"[phase1.5] wrote patched v38 ({len(patched)} chars)")
    print(f"[phase1.5] backup: {BACKUP}")
    print("[phase1.5] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
