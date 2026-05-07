#!/usr/bin/env python3
"""Rule 7 Path B preflight 132: Phase B waveform-first authoring.

Applied on the PRE-PREFLIGHT-122 BASELINE restored from
.bak_ui_sync_playhead_20260420T041111Z on 2026-04-20. This is a CLEAN feature-add
(no layered workarounds) that implements the V3 spec's waveform-first authoring
flow per §Call 1 of TECH_SPEC_PREVIEW_STITCHED_V3_PHASE_B_20260419.md.

8-agent 4+4 convergence (2026-04-20) root-cause diagnosis: preflight 122-131
inverted the V3 spec by binding WS to the <video> via setMediaElement(pl),
forcing Kim to re-render a 29MB MP4 to verify every cue placement. The archived
patchers (Production/tools/archive/20260420_failed_wavesurfer_bindings/) contain
the full audit trail of what not to do.

THIS PATCH DOES:
  1. Fix getAudioDuration() to prioritize ws.getDuration() (baseline reads
     non-existent DOM ids and returns 0, breaking drag-drop timestamp math).
  2. Replace ws.on("click") no-op with ws.seekTo(pct) -- WaveSurfer owns its own
     audio (from ws.load), click scrubs its own playhead natively.
  3. Inject dropCueAtPlayhead(phase, item) helper that reads ws.getCurrentTime()
     (not pl.currentTime) -- cue placement is against the AUDIO timeline, never
     against the rendered video.
  4. Augment library-tile forEach to add click-to-drop + visible flash feedback.
  5. Inject installPlayButton(phase) that adds a [\u25B6 Play / \u23F8 Pause] button
     next to the waveform calling ws.playPause(). This is Kim's primary
     authoring control.
  6. Inject installDebugPanel() that shows live ws state (currentTime, duration,
     isPlaying, cues count, last click) in the bottom-right corner.
  7. Wrap Preview blob in new Blob([blob], {type:"video/mp4"}) to unblock
     Chrome's decoder when Kim does the final-review render.
  8. Preserve the <video> element for final-review playback -- just don't bind
     WS to it. Kim clicks Preview only when she wants to verify the composition.

Counter-gamma tightened patcher contract (idempotency, anchor uniqueness,
overlap guard, 32-URI base64 integrity, atomic rename, backup subdir with
prune-to-10) enforced throughout.
"""
from __future__ import annotations
import hashlib, os, re, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path("/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files")
TARGET = PROJECT_ROOT / "Production" / "Event_1" / "storyboard_v38_prod.html"
BACKUP_DIR = PROJECT_ROOT / "Production" / "Event_1" / ".storyboard_backups"
LD_BEGIN = "<!-- BEGIN LD V3 Phase B/A Authoring Panels"
LD_END = "<!-- END LD V3 Phase B/A Authoring Panels"
BACKUP_KEEP = 10

IDEMPOTENCY_TOKENS = [
    "preflight 132: waveform-first authoring",
    "preflight 132: dropCueAtPlayhead",
    "preflight 132: installPlayButton",
]

# ---- Edit 1: Replace getAudioDuration body ----
EDIT_1_OLD = """  function getAudioDuration(phase) {
    // Prefer lipsync player (final), then mix, then voice.
    var candidates = ["lipsync", "mix", "voice"];
    for (var i=0; i<candidates.length; i++) {
      var p = $("phase-"+phase+"-"+candidates[i]+"-player");
      if (p && p.duration && !isNaN(p.duration)) return p.duration;
    }
    return 0;
  }"""
EDIT_1_NEW = """  function getAudioDuration(phase) {
    // preflight 132: waveform-first authoring.
    // WaveSurfer owns its own audio via ws.load(), so ws.getDuration() is the
    // primary source of truth. Prior code read non-existent DOM ids and returned 0.
    var ws = window["__phase_"+phase+"_ws"];
    if (ws && typeof ws.getDuration === "function") {
      var d = ws.getDuration();
      if (isFinite(d) && d > 0) return d;
    }
    // Fallback: look for any preview/media player that might have a src loaded.
    var candidates = ["preview", "lipsync", "mix", "voice"];
    for (var i=0; i<candidates.length; i++) {
      var p = $("phase-"+phase+"-"+candidates[i]+"-player");
      if (p && p.duration && !isNaN(p.duration)) return p.duration;
    }
    return 0;
  }"""
EDIT_1_VERIFY = "preflight 132: waveform-first authoring"

# ---- Edit 2: Replace ws.on("click") no-op with native seek ----
EDIT_2_OLD = """      ws.on("click", function(pct){
        // No-op — drag-drop handles cue creation; click scrubs.
      });"""
EDIT_2_NEW = """      ws.on("click", function(pct){
        // preflight 132: waveform click seeks WaveSurfer's own audio playhead.
        // WS's media is its internal <audio> (from ws.load), so seekTo scrubs
        // natively -- no external element binding needed.
        try { ws.seekTo(pct); } catch(_){}
      });"""
EDIT_2_VERIFY = "preflight 132: waveform click seeks"

# ---- Edit 3: Inject helper functions BEFORE init() (anchor doesn't collide) ----
EDIT_3_OLD = """  function init() {
    var mount = $("mn-phase-panels");"""
EDIT_3_NEW = """  // preflight 132: dropCueAtPlayhead -- shared helper for click-to-drop.
  // Reads ws.getCurrentTime() (NOT pl.currentTime) so cues land at the audio
  // playhead where Kim is actually listening. Never touches the <video> element.
  function dropCueAtPlayhead(phase, item) {
    var ws = window["__phase_"+phase+"_ws"];
    var ind = $("phase-"+phase+"-preview-ind");
    if (!ws || typeof ws.getCurrentTime !== "function") {
      if (ind) setSaveInd("phase-"+phase+"-preview-ind", "Audio not loaded yet", "#f85149");
      return;
    }
    var dur = getAudioDuration(phase);
    if (!dur) {
      if (ind) setSaveInd("phase-"+phase+"-preview-ind", "Audio not loaded yet", "#f85149");
      return;
    }
    var t_seconds = ws.getCurrentTime();
    if (!isFinite(t_seconds) || t_seconds < 0) t_seconds = 0;
    if (t_seconds >= dur - 0.05) t_seconds = dur - 0.05;
    var timestamp_ms = Math.round(t_seconds * 1000);
    var state = currentStateSnapshot();
    var cues = currentCues(phase, state);
    cues.push({
      timestamp_ms: timestamp_ms,
      key: item.getAttribute("data-key"),
      animation: "fade_in",
      duration_ms: 1500,
      cue_type: item.getAttribute("data-cue-type") || "png",
    });
    saveCues(phase, cues);
    if (ind) setSaveInd("phase-"+phase+"-preview-ind",
      "Cue at " + t_seconds.toFixed(2) + "s", "#2ea043");
  }

  // preflight 132: installPlayButton -- adds a primary play/pause control next
  // to the waveform. ws.playPause() toggles WaveSurfer's own audio playback.
  function installPlayButton(phase) {
    var waveEl = $("phase-"+phase+"-wave");
    var ws = window["__phase_"+phase+"_ws"];
    if (!waveEl || !ws || waveEl.dataset.mnP132PlayInstalled === "1") return;
    waveEl.dataset.mnP132PlayInstalled = "1";
    var btn = document.createElement("button");
    btn.className = "mn-primary";
    btn.id = "phase-"+phase+"-ws-playbtn";
    btn.textContent = "\u25B6 Play audio";
    btn.style.cssText = "margin: 6px 0; padding: 6px 12px;";
    btn.addEventListener("click", function() {
      try { ws.playPause(); } catch(e){ console.warn("[p132] playPause:", e); }
    });
    ws.on("play", function(){ btn.textContent = "\u23F8 Pause audio"; });
    ws.on("pause", function(){ btn.textContent = "\u25B6 Play audio"; });
    ws.on("finish", function(){ btn.textContent = "\u25B6 Play audio"; });
    waveEl.parentNode.insertBefore(btn, waveEl);
  }

  // preflight 132: installDebugPanel -- live visibility into ws/cue state.
  // Bottom-right corner, updates every 250ms. No DOM overlays on the waveform
  // (WS's native rendering is the only source of truth for cursor + progress).
  function installDebugPanel() {
    if (document.getElementById("mn-wc-debug")) return;
    var dbg = document.createElement("div");
    dbg.id = "mn-wc-debug";
    dbg.style.cssText = "position:fixed;bottom:6px;right:6px;background:rgba(0,0,0,0.82);color:#9cf;font:10px/1.35 ui-monospace,monospace;padding:6px 10px;border-radius:4px;border:1px solid #58a6ff;z-index:99998;max-width:360px;white-space:pre;pointer-events:none;";
    document.body.appendChild(dbg);
    var lastLibClick = "none";
    document.addEventListener("click", function(e) {
      var tile = e.target && e.target.closest && e.target.closest(".mn-wc-lib-item");
      if (tile) lastLibClick = tile.getAttribute("data-key") + " @ " + new Date().toLocaleTimeString();
    }, true);
    function tick() {
      try {
        var lines = ["[mn-debug] preflight 132"];
        ["b","a"].forEach(function(p){
          var ws = window["__phase_"+p+"_ws"];
          if (!ws) { lines.push(p.toUpperCase()+": WS not mounted"); return; }
          var state = currentStateSnapshot();
          var cuesJson = state["phase_"+p+"_watercolor_cues_json"] || "[]";
          var cuesCount = 0;
          try { cuesCount = JSON.parse(cuesJson).length; } catch(_){}
          lines.push(p.toUpperCase()+": t="+(ws.getCurrentTime ? ws.getCurrentTime().toFixed(2) : "?")+
            "/"+(ws.getDuration ? ws.getDuration().toFixed(2) : "?")+
            " playing="+(ws.isPlaying ? ws.isPlaying() : "?")+
            " cues="+cuesCount);
        });
        lines.push("last lib click: "+lastLibClick);
        dbg.textContent = lines.join("\\n");
      } catch(e) { dbg.textContent = "[mn-debug err] "+e.message; }
    }
    setInterval(tick, 250);
    tick();
  }

  function init() {
    var mount = $("mn-phase-panels");"""
EDIT_3_VERIFY = "preflight 132: dropCueAtPlayhead"

# ---- Edit 4: Augment wireDragDrop library-item forEach with click ----
EDIT_4_OLD = """    lib.querySelectorAll(".mn-wc-lib-item").forEach(function(item) {
      item.addEventListener("dragstart", function(e) {
        e.dataTransfer.setData("text/plain",
          JSON.stringify({key: item.getAttribute("data-key"),
                          cue_type: item.getAttribute("data-cue-type")}));
      });
    });"""
EDIT_4_NEW = """    lib.querySelectorAll(".mn-wc-lib-item").forEach(function(item) {
      // preflight 132: dragstart unchanged; add click-to-drop-at-audio-playhead
      // with visible orange flash so Kim sees click reception instantly.
      item.addEventListener("dragstart", function(e) {
        item._wasDragged = true;
        e.dataTransfer.setData("text/plain",
          JSON.stringify({key: item.getAttribute("data-key"),
                          cue_type: item.getAttribute("data-cue-type")}));
      });
      item.addEventListener("dragend", function() {
        setTimeout(function(){ item._wasDragged = false; }, 50);
      });
      item.addEventListener("click", function() {
        if (item._wasDragged) return;
        try {
          if (item.animate) {
            item.animate([
              { transform: "scale(1)",   boxShadow: "0 0 0 0 rgba(255,165,0,0)" },
              { transform: "scale(0.88)", boxShadow: "0 0 10px 5px rgba(255,165,0,0.85)" },
              { transform: "scale(1)",   boxShadow: "0 0 0 0 rgba(255,165,0,0)" }
            ], { duration: 220, easing: "ease-out" });
          }
        } catch(_){}
        dropCueAtPlayhead(phase, item);
      });
    });"""
EDIT_4_VERIFY = "preflight 132: dragstart unchanged"

# ---- Edit 5: Call installPlayButton after ws is stored on window ----
EDIT_5_OLD = """      window["__phase_"+phase+"_ws"] = ws;
    } catch (e) { /* fall back to strip */ }
  }"""
EDIT_5_NEW = """      window["__phase_"+phase+"_ws"] = ws;
      // preflight 132: installPlayButton after WS is live. ws.on("ready")
      // ensures the play button only fires playPause when audio is decoded.
      try { ws.on("ready", function(){ installPlayButton(phase); }); } catch(_){}
      // Also install immediately in case "ready" already fired (cache hit).
      try { installPlayButton(phase); } catch(_){}
    } catch (e) { /* fall back to strip */ }
  }"""
EDIT_5_VERIFY = "preflight 132: installPlayButton after WS is live"

# ---- Edit 6: Call installDebugPanel at end of init() ----
EDIT_6_OLD = """    console.log("[phase_b_panels] LD V3 wired");
  }"""
EDIT_6_NEW = """    console.log("[phase_b_panels] LD V3 wired + preflight 132 waveform-first");
    // preflight 132: debug panel for live visibility into ws state + cues.
    try { installDebugPanel(); } catch(e){ console.warn("[p132] debug panel:", e); }
  }"""
EDIT_6_VERIFY = "preflight 132 waveform-first"

# ---- Edit 7: Wrap blob in explicit video/mp4 type for Preview re-render ----
EDIT_7_OLD = """        var url = URL.createObjectURL(blob);
        pl.dataset.lastUrl = url;
        pl.src = url;"""
EDIT_7_NEW = """        // preflight 132: explicit video/mp4 type on the Blob unblocks Chrome's
        // media decoder. Bare fetch().blob() stalls at rs=1 even with all bytes
        // buffered. See Production/tools/archive/.../README.md for full history.
        var typedBlob = new Blob([blob], {type: "video/mp4"});
        var url = URL.createObjectURL(typedBlob);
        pl.dataset.lastUrl = url;
        pl.src = url;
        pl.preload = "auto";"""
EDIT_7_VERIFY = "preflight 132: explicit video/mp4 type"

EDITS = [
    # (tag, old, new, verify_token, allow_overlap)
    # allow_overlap=True for prepend-style inserts where the NEW code by design
    # contains the OLD anchor (and idempotency token still guards re-run).
    ("1_getAudioDuration",       EDIT_1_OLD, EDIT_1_NEW, EDIT_1_VERIFY, False),
    ("2_ws_click_seek",          EDIT_2_OLD, EDIT_2_NEW, EDIT_2_VERIFY, False),
    ("3_helper_functions",       EDIT_3_OLD, EDIT_3_NEW, EDIT_3_VERIFY, True),   # prepend
    ("4_library_click",          EDIT_4_OLD, EDIT_4_NEW, EDIT_4_VERIFY, False),
    ("5_install_playbutton",     EDIT_5_OLD, EDIT_5_NEW, EDIT_5_VERIFY, False),
    ("6_install_debug_panel",    EDIT_6_OLD, EDIT_6_NEW, EDIT_6_VERIFY, False),
    ("7_blob_mime_wrap",         EDIT_7_OLD, EDIT_7_NEW, EDIT_7_VERIFY, False),
]

B64_RE = re.compile(r'data:(?:image|audio|video|application)/[a-zA-Z0-9+.\-]+;base64,[A-Za-z0-9+/=]+')

def sha256_b(d): return hashlib.sha256(d).hexdigest()
def extract_b64(t): return [(m.group(0).split(",",1)[0], sha256_b(m.group(0).encode("ascii"))) for m in B64_RE.finditer(t)]
def locate_ld(t):
    a = t.find(LD_BEGIN); b = t.find(LD_END)
    if a < 0 or b < 0: raise RuntimeError("sentinels missing")
    return a, b + len(LD_END)
def atomic_write(p, data):
    with tempfile.NamedTemporaryFile(dir=str(p.parent), prefix=p.name+".tmp_", delete=False) as f:
        f.write(data); f.flush(); os.fsync(f.fileno()); tmp = Path(f.name)
    os.replace(str(tmp), str(p))
def prune():
    baks = sorted(BACKUP_DIR.glob("*.bak_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for o in baks[BACKUP_KEEP:]:
        try: o.unlink()
        except OSError: pass

def main():
    dry = "--dry-run" in sys.argv
    raw = TARGET.read_bytes()
    if len(raw) < 3_000_000: return 2
    txt = raw.decode("utf-8")
    print(f"Target: {TARGET}\n  size: {len(raw):,}  pre-SHA: {sha256_b(raw)[:16]}...")

    hits = [t for t in IDEMPOTENCY_TOKENS if t in txt]
    if len(hits) == len(IDEMPOTENCY_TOKENS): print("  IDEMPOTENT: already applied"); return 0
    if hits: print(f"  PARTIAL: {hits}", file=sys.stderr); return 7

    ld_a, ld_b = locate_ld(txt); ld = txt[ld_a:ld_b]
    pre_b64 = extract_b64(txt); print(f"  base64 URIs: {len(pre_b64)}")

    for tag, old, new, tok, allow_overlap in EDITS:
        if ld.count(old) != 1: print(f"ANCHOR FAIL [{tag}]: region-count={ld.count(old)}", file=sys.stderr); return 3
        if txt.count(old) != ld.count(old): print(f"SCOPE FAIL [{tag}]", file=sys.stderr); return 3
        if (not allow_overlap) and (old in new): print(f"OVERLAP FAIL [{tag}]", file=sys.stderr); return 3
    print(f"  anchors verified: {len(EDITS)}")

    patched = txt
    for tag, old, new, tok, allow_overlap in EDITS:
        if patched.count(old) != 1: print(f"DRIFT [{tag}]", file=sys.stderr); return 4
        patched = patched.replace(old, new, 1)
        print(f"  edit {tag}: {len(new)-len(old):+d} chars")

    post_b64 = extract_b64(patched)
    if post_b64 != pre_b64: print("BASE64 DRIFT", file=sys.stderr); return 5
    print(f"  base64: {len(post_b64)}/{len(pre_b64)} identical")
    for tag, old, new, tok, allow_overlap in EDITS:
        if tok not in patched: print(f"TOKEN MISSING [{tag}]", file=sys.stderr); return 6
    print(f"  verify tokens: all present")

    if dry: print(f"\n[DRY RUN] delta: {len(patched.encode('utf-8'))-len(raw):+d} bytes"); return 0

    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = BACKUP_DIR / f"{TARGET.name}.bak_preflight132_waveform_first_{ts}"
    bak.write_bytes(raw); print(f"  backup: {bak.name}")
    atomic_write(TARGET, patched.encode("utf-8"))
    print(f"  post-SHA: {sha256_b(TARGET.read_bytes())[:16]}...")
    prune()
    print("\n--- PREFLIGHT 132 APPLIED ---")
    print("Kim: close and reopen the tab. You should see:")
    print("  (1) A [\u25B6 Play audio] button above the waveform.")
    print("  (2) Click it -- waveform cursor advances in real-time.")
    print("  (3) Click a library tile at any moment -- cue drops at the audio playhead.")
    print("  (4) Click anywhere on the waveform -- audio jumps there.")
    print("  (5) Bottom-right debug panel shows live ws state + cues count.")
    print("  (6) Click Preview Phase B Stitched ONLY when you're ready to see the final video.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
