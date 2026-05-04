#!/usr/bin/env python3
"""Tier 3 CLIENT-SIDE widget wiring patcher for storyboard_v38_prod.html.

Rule 7 Path B (MANDATORY): reads v38 HTML into memory, applies STRING
REPLACEMENTS to <script> and <style> blocks ONLY, preserves every
base64 data URI byte-identical (SHA256 pre/post asserted), backs up the
original, then writes in place.

LD references (Phase 0 preflight 68):
  - LD-239: pause slider -> pathappPatch pause_after_ms (seconds * 1000)
  - LD-240: image dropdown -> pathappPatch image_override
  - LD-241: speaker dropdown -> pathappPatch speaker
  - LD-242: row reorder ▲▼ -> pathappPatch __global__ display_order
  - LD-243: + Add Line -> POST /api/v2/beat/create (creates scaffold)
  - LD-244: [pause] tag button -> dispatch blur after insertion (reuses
                                  existing dialogue onblur path;
                                  options.skip_tts_regen forwarded)
  - LD-256: speaker_mismatch stale-audio badge (MEDIUM severity CSS)
  - LD-257: display_order hydrate -> reorder L[] before render
  - LD-258: Add Line insert_after anchor (last anchor, or null for first)
  - LD-259: error fallback is RED TOAST never a silent client-only mutate

Widgets patched (6): pause / image / speaker / reorder / addLine / pause-tag
+ CSS (.audio-stale-badge) + _t3LegacyRefuse helper + window.TIER3_ENABLED.

Rule 7 Path B discipline enforced:
  * Single-match assertion for every surgical edit
  * Base64 data-URI extraction + sorted-concat SHA256 byte-identical gate
  * Backup BEFORE write (.bak_tier3_widgets_<UTC_TS>)
  * Post-write HTML sanity (</body>, </html>, <script> count unchanged)
  * Post-write Node --check on extracted script bodies
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

# --------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------
PROJECT_ROOT = pathlib.Path(
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
)
TARGET = PROJECT_ROOT / "Production" / "Event_1" / "storyboard_v38_prod.html"

# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
_B64_IMG_RE = re.compile(r"data:image/[a-zA-Z.+-]+;base64,[A-Za-z0-9+/=]+")


def _sha256_of_sorted_b64_uris(src: str) -> tuple[str, int]:
    uris = sorted(_B64_IMG_RE.findall(src))
    joined = "\n".join(uris).encode("utf-8")
    return hashlib.sha256(joined).hexdigest(), len(uris)


def _assert_single_match(hay: str, needle: str, label: str) -> None:
    count = hay.count(needle)
    if count != 1:
        raise SystemExit(
            f"[tier3-patcher] FATAL single-match assertion failed for "
            f"{label!r}: found {count} occurrences, expected exactly 1."
        )


def _count_substring(hay: str, needle: str) -> int:
    return hay.count(needle)


def _node_syntax_check_scripts(src: str) -> None:
    """Extract every <script>...</script> body, concat, run `node --check`.

    If node is missing from PATH, skip gracefully with a warning rather
    than failing — the test suite still enforces static signatures.
    """
    if shutil.which("node") is None:
        print("[tier3-patcher] WARN: node not on PATH; skipping syntax check.")
        return

    bodies = re.findall(r"<script[^>]*>(.*?)</script>", src, flags=re.DOTALL)
    if not bodies:
        print("[tier3-patcher] WARN: no <script> bodies found; skipping syntax check.")
        return

    # Concatenate with sentinel so one broken script doesn't poison the
    # others silently — node --check reports first error.
    concat = "\n;\n".join(bodies)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(concat)
        tmpname = tf.name

    try:
        result = subprocess.run(
            ["node", "--check", tmpname],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise SystemExit(
                "[tier3-patcher] FATAL node --check failed on concatenated "
                f"script bodies:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            )
        print("[tier3-patcher] node --check: OK")
    finally:
        os.unlink(tmpname)


# --------------------------------------------------------------------
# Surgical edits — each is exact string replacement with single-match guard.
# --------------------------------------------------------------------

# Widget 1 — Pause slider: ADD ps.onchange (NOT replace oninput)
#   Existing (line 200): ps.setAttribute("data-i",""+i);ps.oninput=...
#   We append ps.onchange right after the oninput line.
W1_OLD = (
    'ps.setAttribute("data-i",""+i);'
    'ps.oninput=function(){var x=parseInt(this.getAttribute("data-i"));'
    'L[x].p=parseFloat(this.value);'
    'document.getElementById("pv"+x).textContent=this.value+"s";};'
)
W1_NEW = (
    'ps.setAttribute("data-i",""+i);'
    'ps.oninput=function(){var x=parseInt(this.getAttribute("data-i"));'
    'L[x].p=parseFloat(this.value);'
    'document.getElementById("pv"+x).textContent=this.value+"s";};'
    # LD-239: on release, persist to server as ms.
    'ps.onchange=function(){'
    'var x=parseInt(this.getAttribute("data-i"));'
    'var v=parseFloat(this.value);'
    'var bid="beat_"+String(x+1).padStart(2,"0");'
    'var ms=Math.round(v*1000);'
    'var _psSi=(window._pathappWire&&window._pathappWire.ensureSaveInd)'
    '?window._pathappWire.ensureSaveInd(this,x,"pause"):null;'
    'var _psLegacy=_t3LegacyRefuse.bind(null,"pause",bid,"pause_after_ms","offline");'
    'if(window._pathappWire&&typeof window.pathappPatch==="function"){'
    'window._pathappWire.routedPatch(bid,"pause_after_ms",ms,_psSi,_psLegacy);'
    '}else{_psLegacy();}'
    '};'
)

# Widget 2 — Image dropdown: REPLACE is2.onchange to route to pathappPatch BEFORE render()
#   Existing (line 194): is2.onchange=function(){var x=parseInt(this.getAttribute("data-i"));L[x].i=this.value;render();};
W2_OLD = (
    'is2.onchange=function(){var x=parseInt(this.getAttribute("data-i"));'
    'L[x].i=this.value;render();};'
)
W2_NEW = (
    'is2.onchange=function(){'
    'var x=parseInt(this.getAttribute("data-i"));'
    'var newKey=this.value;'
    'var bid="beat_"+String(x+1).padStart(2,"0");'
    'L[x].i=newKey;'
    'var _isSi=(window._pathappWire&&window._pathappWire.ensureSaveInd)'
    '?window._pathappWire.ensureSaveInd(this,x,"imgsel"):null;'
    'var _isLegacy=_t3LegacyRefuse.bind(null,"image_dropdown",bid,"image_override","offline");'
    'if(window._pathappWire&&typeof window.pathappPatch==="function"){'
    'window._pathappWire.routedPatch(bid,"image_override",newKey,_isSi,_isLegacy);'
    '}else{_isLegacy();}'
    'render();'
    '};'
)

# Widget 3 — Speaker dropdown: REPLACE sl.onchange to route to pathappPatch BEFORE render()
#   Existing (line 167): sl.onchange=function(){var x=parseInt(this.getAttribute("data-i"));L[x].s=this.value;render();};
W3_OLD = (
    'sl.onchange=function(){var x=parseInt(this.getAttribute("data-i"));'
    'L[x].s=this.value;render();};'
)
W3_NEW = (
    'sl.onchange=function(){'
    'var x=parseInt(this.getAttribute("data-i"));'
    'var newSpk=this.value;'
    'var bid="beat_"+String(x+1).padStart(2,"0");'
    'L[x].s=newSpk;'
    'var _slSi=(window._pathappWire&&window._pathappWire.ensureSaveInd)'
    '?window._pathappWire.ensureSaveInd(this,x,"speaker"):null;'
    'var _slLegacy=_t3LegacyRefuse.bind(null,"speaker",bid,"speaker","offline");'
    'if(window._pathappWire&&typeof window.pathappPatch==="function"){'
    'window._pathappWire.routedPatch(bid,"speaker",newSpk,_slSi,_slLegacy);'
    '}else{_slLegacy();}'
    'render();'
    '};'
)

# Widget 3 companion — stale-audio badge render:
#   Existing (line 170): var tg=document.createElement("span");tg.className="at"+(ha?" h":"");tg.textContent=ha?"(TTS: "+l.a+")":"(no TTS yet)";tp.appendChild(tg);
W3B_OLD = (
    'var tg=document.createElement("span");'
    'tg.className="at"+(ha?" h":"");'
    'tg.textContent=ha?"(TTS: "+l.a+")":"(no TTS yet)";'
    'tp.appendChild(tg);'
)
W3B_NEW = (
    'var tg=document.createElement("span");'
    'tg.className="at"+(ha?" h":"");'
    'tg.textContent=ha?"(TTS: "+l.a+")":"(no TTS yet)";'
    'tp.appendChild(tg);'
    # LD-256: stale-audio badge when server flagged speaker_mismatch.
    'if(l.speaker_mismatch){'
    'var _sb=document.createElement("span");'
    '_sb.className="audio-stale-badge";'
    '_sb.textContent="\u26A0 audio stale (click Regen Audio)";'
    '_sb.title="Speaker changed after TTS was generated. Click Regen Audio to refresh.";'
    'tp.appendChild(_sb);'
    '}'
)

# Widget 4 — Row reorder ▲▼: REPLACE mv() to emit display_order after swap
#   Existing (line 215): function mv(i,d){var j=i+d;if(j<0||j>=L.length)return;var t=L[i];L[i]=L[j];L[j]=t;render();}
W4_OLD = (
    'function mv(i,d){var j=i+d;if(j<0||j>=L.length)return;'
    'var t=L[i];L[i]=L[j];L[j]=t;render();}'
)
W4_NEW = (
    'function mv(i,d){'
    'var j=i+d;'
    'if(j<0||j>=L.length)return;'
    'var t=L[i];L[i]=L[j];L[j]=t;'
    # Build new display_order from current L[] ordering.
    'var _newOrder=[];'
    'for(var _k=0;_k<L.length;_k++){'
    '_newOrder.push("beat_"+String(_k+1).padStart(2,"0"));'
    '}'
    'var _mvLegacy=_t3LegacyRefuse.bind(null,"reorder","__global__","display_order","offline");'
    'if(window._pathappWire&&typeof window.pathappPatch==="function"){'
    'window._pathappWire.routedPatch("__global__","display_order",_newOrder,null,_mvLegacy);'
    '}else{_mvLegacy();}'
    'render();'
    '}'
)

# Widget 5 — addLine(): REPLACE to POST /api/v2/beat/create first, then push on 200
#   Existing (line 216): function addLine(){L.push({s:SP[0],t:"(new line)",i:"master",a:null,p:0.5,g:"Custom"});render();window.scrollTo(0,document.body.scrollHeight);}
W5_OLD = (
    'function addLine(){L.push({s:SP[0],t:"(new line)",i:"master",a:null,p:0.5,g:"Custom"});'
    'render();window.scrollTo(0,document.body.scrollHeight);}'
)
W5_NEW = (
    'function addLine(){'
    # LD-243 / LD-258: call server first, use returned beat_id anchor.
    'var _insertAfter=null;'
    'for(var _ii=L.length-1;_ii>=0;_ii--){'
    'if(L[_ii]&&L[_ii].a){_insertAfter=L[_ii].a;break;}'
    '}'
    'var _addLegacy=_t3LegacyRefuse.bind(null,"add_line","<new>","create","offline");'
    'if(!window._pathappWire||typeof window.pathappPatch!=="function"){'
    '_addLegacy();return;'
    '}'
    'var _SERVER_V2="http://localhost:5111";'
    'fetch(_SERVER_V2+"/api/v2/beat/create",{'
    'method:"POST",'
    'headers:{"Content-Type":"application/json"},'
    'body:JSON.stringify({insert_after:_insertAfter})'
    '}).then(function(r){'
    'if(r.status===503){_addLegacy();return null;}'
    'if(!r.ok){throw new Error("create failed: HTTP "+r.status);}'
    'return r.json();'
    '}).then(function(d){'
    'if(!d)return;'
    'var anchorId=d.beat_id||d.anchor||null;'
    'if(!anchorId){throw new Error("create response missing beat_id");}'
    'L.push({s:SP[0],t:"(new line)",i:"master",a:anchorId,p:0.5,g:"Custom"});'
    'if(window.pathappToast){window.pathappToast("saved","\u2713 Line added ("+anchorId+")");}'
    'render();'
    'window.scrollTo(0,document.body.scrollHeight);'
    '}).catch(function(err){'
    'console.warn("[T3] addLine failed:",err);'
    '_t3LegacyRefuse("add_line","<new>","create",err.message||"network");'
    '});'
    '}'
)

# Widget 6 — [pause] tag button: APPEND blur dispatch after insertion
#   Existing onclick body ends with: L[idx].t=tael.value;tael.focus();}};
#   We replace the whole tael.focus() closing to also fire blur AFTER focus.
W6_OLD = (
    'tael.selectionStart=tael.selectionEnd=start+7;'
    'L[idx].t=tael.value;'
    'tael.focus();}};'
)
W6_NEW = (
    'tael.selectionStart=tael.selectionEnd=start+7;'
    'L[idx].t=tael.value;'
    'tael.focus();'
    # LD-244: programmatically fire blur so the existing dialogue
    # onblur handler persists the new text. skip_tts_regen is forwarded
    # via options on a wrapped pathappPatch call (handler below).
    'window._t3PauseBlurPending=true;'
    'setTimeout(function(){'
    'try{tael.dispatchEvent(new Event("blur"));}catch(e){console.warn("[T3] pause-blur dispatch:",e);}'
    'window._t3PauseBlurPending=false;'
    '},0);'
    '}};'
)

# Widget 6 companion — override ta.onblur skip_tts_regen forwarding.
# The existing onblur (in render()) calls pathappPatch without options.
# We need to forward {skip_tts_regen: true} when _t3PauseBlurPending is set.
# Strategy: wrap window.pathappPatch with a thin forwarder that inspects
# the flag.  Done as a standalone script at end-of-file (single block).
#
# This also adds:
#   - .audio-stale-badge CSS
#   - _t3LegacyRefuse helper
#   - window.TIER3_ENABLED flag
#   - display_order hydrate fix-up

T3_CSS_BLOCK = (
    "\n  /* Tier 3 LD-256 — stale-audio badge shown when server sets "
    "speaker_mismatch */\n"
    "  .audio-stale-badge {\n"
    "    color: #f39c12;\n"
    "    font-size: 10px;\n"
    "    margin-left: 4px;\n"
    "    font-weight: 600;\n"
    "  }\n"
)

# Injection anchor for CSS: append the new block inside the
# Phase 1.5 <style> block that already defines .pathapp-toast.
# Single-match anchor on the terminating "}" of the .error rule + newline + "</style>".
T3_CSS_OLD = (
    "  .pathapp-toast.error   { background: #e74c3c; }\n"
    "</style>\n"
)
T3_CSS_NEW = (
    "  .pathapp-toast.error   { background: #e74c3c; }\n"
    + T3_CSS_BLOCK
    + "</style>\n"
)

# The Tier 3 support script — appended right before </body></html>.
T3_SUPPORT_SCRIPT = """
<!-- BEGIN Tier 3 client-side widget support (injected by patch_v38_tier3_widgets.py) -->
<script>
(function() {
  /* Tier 3 — client-side feature flag.
     Mirrors server-side MINDFULNEST_T1_ENABLED which gates the
     entire v2 patch route (Tier 1 rollout). When Tier 1 is OFF the
     server returns 503 and legacyFallback runs, which for Tier 3
     is _t3LegacyRefuse (red toast). */
  window.TIER3_ENABLED = (typeof window.TIER1A_ENABLED === "undefined")
    ? true
    : !!window.TIER1A_ENABLED;

  /* LD-259: Tier 3 legacy fallback is a RED TOAST, never a silent
     client-only mutation.  Signature matches .bind(null, widget,
     beatId, field, reason) used throughout the patched widgets. */
  window._t3LegacyRefuse = function(widget, beatId, field, reason) {
    try {
      if (typeof window.pathappToast === "function") {
        window.pathappToast(
          "error",
          "\u26A0 Save failed for " + beatId + " " + field +
          ": " + reason + ". Refresh to retry."
        );
      }
    } catch (e) { /* no-op — must not throw */ }
    console.warn("[T3] save failed, no legacy fallback:",
                 widget, beatId, field, reason);
  };

  /* Widget 6 companion — forward {skip_tts_regen: true} to pathappPatch
     when the blur was triggered by the [pause] tag button.
     We wrap window.pathappPatch so the existing dialogue onblur
     handler (which has no knowledge of the tag button) still gets
     the skip flag.  The wrapper is only installed if pathappPatch
     already exists; it preserves the original return Promise. */
  window._t3PauseBlurPending = false;
  var _origPathappPatch = window.pathappPatch;
  if (typeof _origPathappPatch === "function") {
    window.pathappPatch = function(beatId, field, value, options) {
      options = options || {};
      if (field === "dialogue" && window._t3PauseBlurPending === true) {
        options.skip_tts_regen = true;
      }
      return _origPathappPatch.call(this, beatId, field, value, options);
    };
  }

  /* LD-257: apply server-side display_order to L[] AFTER the
     Phase 1 hydrate has seeded BEAT_VERSIONS and before any
     user interaction.  We poll briefly for both window.L and
     a sidecar fetch response, then reorder.
     Uses the v2 sidecar endpoint — same one pathappHydrate uses. */
  var _SERVER_V2 = "http://localhost:5111";
  async function _t3ApplyDisplayOrder() {
    if (!window.L || !Array.isArray(window.L)) return;
    try {
      var r = await fetch(_SERVER_V2 + "/api/v2/storyboard/L.json",
                          { cache: "no-store" });
      if (!r.ok) return;
      var side = await r.json();
      var order = side && side.display_order;
      if (!Array.isArray(order) || order.length === 0) return;
      // Build lookup: anchor -> L[] entry (using the beat_NN derived
      // from entry.a like pathappHydrate does).
      var byBeat = {};
      for (var i = 0; i < window.L.length; i++) {
        var e = window.L[i];
        if (!e || !e.a) continue;
        var m = /line_(\\d+)/.exec(e.a);
        if (!m) continue;
        byBeat["beat_" + m[1].padStart(2, "0")] = e;
      }
      var reordered = [];
      for (var k = 0; k < order.length; k++) {
        var be = byBeat[order[k]];
        if (be) reordered.push(be);
      }
      // Preserve any L[] entries that weren't in order (e.g. placeholder).
      for (var j = 0; j < window.L.length; j++) {
        if (reordered.indexOf(window.L[j]) === -1) reordered.push(window.L[j]);
      }
      if (reordered.length === window.L.length) {
        for (var q = 0; q < reordered.length; q++) window.L[q] = reordered[q];
        if (typeof render === "function") {
          try { render(); } catch (e) { console.warn("[T3] render after reorder:", e); }
        }
        console.log("[T3] applied display_order from sidecar");
      }
    } catch (e) {
      console.warn("[T3] display_order hydrate failed:", e);
    }
  }
  // Run after Phase 1 hydrate (DOMContentLoaded) — defer one tick.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function() {
      setTimeout(_t3ApplyDisplayOrder, 500);
    });
  } else {
    setTimeout(_t3ApplyDisplayOrder, 500);
  }

  console.log("[T3] Tier 3 widget support loaded. TIER3_ENABLED=",
              window.TIER3_ENABLED);
})();
</script>
<!-- END Tier 3 client-side widget support -->
"""

# Injection anchor: append right before </body></html>
T3_SUPPORT_OLD = "</body></html>\n"
T3_SUPPORT_NEW = T3_SUPPORT_SCRIPT.rstrip("\n") + "\n</body></html>\n"


# --------------------------------------------------------------------
# Main
# --------------------------------------------------------------------
def main() -> int:
    if not TARGET.exists():
        print(f"[tier3-patcher] FATAL target not found: {TARGET}", file=sys.stderr)
        return 2

    print(f"[tier3-patcher] reading {TARGET}")
    src = TARGET.read_text(encoding="utf-8")

    # --- Rule 7 Path B guard: base64 byte-identical across patch ---
    pre_sha, pre_n = _sha256_of_sorted_b64_uris(src)
    print(f"[tier3-patcher] pre-patch base64 URIs: {pre_n}  sha256={pre_sha}")

    # --- Apply surgical edits (order: by surface location, but
    # since each uses _assert_single_match on unique fingerprints
    # order is not load-bearing) ---
    edits = [
        ("W1 pause-slider onchange", W1_OLD, W1_NEW),
        ("W2 image-dropdown onchange", W2_OLD, W2_NEW),
        ("W3 speaker-dropdown onchange", W3_OLD, W3_NEW),
        ("W3B speaker_mismatch stale-badge render", W3B_OLD, W3B_NEW),
        ("W4 mv() reorder -> display_order", W4_OLD, W4_NEW),
        ("W5 addLine() -> POST /api/v2/beat/create", W5_OLD, W5_NEW),
        ("W6 [pause] tag -> dispatch blur", W6_OLD, W6_NEW),
        ("T3 CSS .audio-stale-badge", T3_CSS_OLD, T3_CSS_NEW),
        ("T3 support script @ EOF", T3_SUPPORT_OLD, T3_SUPPORT_NEW),
    ]

    patched = src
    for label, old, new in edits:
        _assert_single_match(patched, old, label)
        patched = patched.replace(old, new)
        print(f"[tier3-patcher] applied: {label}")

    # --- Rule 7 Path B guard: base64 URIs must match byte-for-byte ---
    post_sha, post_n = _sha256_of_sorted_b64_uris(patched)
    print(f"[tier3-patcher] post-patch base64 URIs: {post_n}  sha256={post_sha}")
    if (pre_sha, pre_n) != (post_sha, post_n):
        raise SystemExit(
            "[tier3-patcher] FATAL base64 SHA256 mismatch — aborting "
            "without writing.  Rule 7 Path B invariant violated."
        )
    print("[tier3-patcher] base64 byte-identical: OK")

    # --- HTML structural sanity ---
    for needle in ("</body>", "</html>"):
        if patched.count(needle) != src.count(needle):
            raise SystemExit(
                f"[tier3-patcher] FATAL {needle!r} count changed "
                f"({src.count(needle)} -> {patched.count(needle)}); aborting."
            )
    # <script> tag count must be src + 1 (we added one Tier 3 block)
    expected_delta = 1  # Tier 3 support <script>
    src_script_open = src.count("<script>") + src.count("<script ")
    post_script_open = patched.count("<script>") + patched.count("<script ")
    if post_script_open - src_script_open != expected_delta:
        raise SystemExit(
            f"[tier3-patcher] FATAL <script> open-tag delta unexpected: "
            f"pre={src_script_open} post={post_script_open} delta={post_script_open-src_script_open} "
            f"expected_delta={expected_delta}"
        )

    # --- Node syntax check on extracted script bodies ---
    _node_syntax_check_scripts(patched)

    # --- Backup before write ---
    ts = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    bak = TARGET.with_suffix(TARGET.suffix + f".bak_tier3_widgets_{ts}")
    shutil.copy2(TARGET, bak)
    print(f"[tier3-patcher] backup: {bak.name}")

    # --- Write ---
    TARGET.write_text(patched, encoding="utf-8")
    print(f"[tier3-patcher] wrote {TARGET} ({len(patched):,} bytes)")

    # --- Post-write static presence checks (belt + suspenders).
    # NOTE: the patched file uses the existing Phase 1.5 routedPatch
    # convention (which is itself a thin forwarder to window.pathappPatch),
    # not direct window.pathappPatch() calls — mirrors the drag-drop
    # image_override handler on line 396 which predates Tier 3. ---
    post = TARGET.read_text(encoding="utf-8")
    static_checks = [
        # W1: routedPatch carries the pause_after_ms field + payload.
        ('routedPatch(bid,"pause_after_ms"', 1, ">=", "W1 pause_after_ms routed"),
        # W3: exactly-one-speaker-routedPatch (the only speaker wiring).
        ('routedPatch(bid,"speaker"', 1, "==", "W3 speaker routed (exactly once)"),
        # W2: drag-drop + dropdown both push image_override => ≥2.
        ('"image_override"', 2, ">=", "W2 image_override field ≥2 (dropdown + drag-drop)"),
        # Pre-existing drag-drop image_override site preserved.
        ('routedPatch(_bid_drop,"image_override"', 1, ">=", "drag-drop image_override preserved"),
        # W4: display_order mutation wire.
        ('"display_order"', 1, ">=", "W4 display_order field"),
        ('routedPatch("__global__","display_order"', 1, ">=", "W4 __global__ display_order routed"),
        # T3 helper used at every widget site (≥6 bindings).
        ("_t3LegacyRefuse", 6, ">=", "T3 legacy refuse ≥6 uses"),
        # Stale-audio badge: CSS class + DOM class + runtime guard.
        ("audio-stale-badge", 2, ">=", "T3 stale-badge CSS + DOM use"),
        ("speaker_mismatch", 1, ">=", "T3 speaker_mismatch guard"),
        # Feature flag.
        ("window.TIER3_ENABLED", 1, ">=", "T3 feature flag"),
        # W5: create endpoint.
        ("/api/v2/beat/create", 1, ">=", "W5 addLine endpoint"),
    ]
    for needle, threshold, op, label in static_checks:
        c = post.count(needle)
        ok = (c >= threshold) if op == ">=" else (c == threshold)
        flag = "OK" if ok else "FAIL"
        print(f"[tier3-patcher] static {flag}: {label}  ({c} {op} {threshold})  needle={needle!r}")
        if not ok:
            raise SystemExit(
                f"[tier3-patcher] FATAL static check failed: {label} "
                f"needle={needle!r} count={c} op={op} threshold={threshold}"
            )

    print("[tier3-patcher] all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
