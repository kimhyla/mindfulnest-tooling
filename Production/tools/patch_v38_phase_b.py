#!/usr/bin/env python3
"""V3 Phase B + Phase A authoring-panel patcher for storyboard_v38_prod.html.

Cloned from patch_v38_preview_stitched.py (V2, shipped earlier tonight).
All Rule 7 Path B invariants enforced:
  * String-replacement patches against single-match anchors.
  * Base64 image SHA256 pre + post; mismatch = abort + restore.
  * Backup BEFORE patched output.
  * Post-patch sanity: </body> / </html> count unchanged, +1 <script> open.
  * node --check on extracted scripts when node is on PATH.

Surgical edits:
  E1  Insert mn-phase-panels mount container after V2 preview player.
  E2  CSS + HTML template + JS support block appended at EOF.
       - Phase B panel (Cedric meditation, frame_x=40 LEFT)
       - Phase A panel (Chipper demo, frame_x=800 RIGHT)
       - Watercolor timeline widget (drag-on-waveform via WaveSurfer.js v7
         CDN-loaded; graceful fallback to plain strip on CDN load failure
         so the tool still functions offline).

Run from project root:
    python3 Production/tools/patch_v38_phase_b.py
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
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGET = PROJECT_ROOT / "Production" / "Event_1" / "storyboard_v38_prod.html"

WATERCOLOR_DIR = PROJECT_ROOT / "Production" / "assets" / "watercolor_library"
AMBIENT_DIR = PROJECT_ROOT / "Production" / "assets" / "ambient_library"
LIPSYNC_BASES_DIR = PROJECT_ROOT / "Production" / "assets" / "lipsync_bases"

# --------------------------------------------------------------------
# Helpers (mirror patch_v38_preview_stitched.py)
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
            f"[phase_b_patcher] FATAL single-match assertion failed "
            f"for {label!r}: found {count} occurrences, expected exactly 1."
        )


def _node_syntax_check_scripts(src: str) -> None:
    if shutil.which("node") is None:
        print("[phase_b_patcher] WARN: node not on PATH; skipping syntax check.")
        return
    bodies = re.findall(r"<script[^>]*>(.*?)</script>", src, flags=re.DOTALL)
    if not bodies:
        print("[phase_b_patcher] WARN: no <script> bodies; skipping syntax check.")
        return
    concat = "\n;\n".join(bodies)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8",
    ) as tf:
        tf.write(concat)
        tmpname = tf.name
    try:
        result = subprocess.run(
            ["node", "--check", tmpname],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise SystemExit(
                "[phase_b_patcher] FATAL node --check failed:\n"
                f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            )
        print("[phase_b_patcher] node --check: OK")
    finally:
        os.unlink(tmpname)


def _scan_library(dir_path: pathlib.Path,
                   exts: tuple[str, ...]) -> list[dict]:
    """Scan a library dir for files with given extensions; return sorted metadata."""
    out = []
    if not dir_path.is_dir():
        return out
    for entry in sorted(dir_path.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in exts:
            continue
        out.append({
            "key": entry.stem,
            "filename": entry.name,
            "cue_type": "png" if entry.suffix.lower() == ".png" else "video",
        })
    return out


# --------------------------------------------------------------------
# E1 — Inject mn-phase-panels container after V2 preview player.
# --------------------------------------------------------------------
# V2 patcher already inserted these lines in mount():
#     root.appendChild(previewBar);
#     root.appendChild(previewPlayer);
#     root.appendChild(progressWrap);
# We insert an mn-phase-panels container right after previewPlayer.
E1_OLD = (
    '        root.appendChild(previewBar);\n'
    '        root.appendChild(previewPlayer);\n'
    '        root.appendChild(progressWrap);\n'
)
E1_NEW = (
    '        root.appendChild(previewBar);\n'
    '        root.appendChild(previewPlayer);\n'
    '        // V3 Phase B/A authoring panels (populated by support script below).\n'
    '        var phasePanelsMount = el("div", {id: "mn-phase-panels"}, []);\n'
    '        root.appendChild(phasePanelsMount);\n'
    '        root.appendChild(progressWrap);\n'
)


# --------------------------------------------------------------------
# E2 — CSS + HTML template + JS support block at EOF.
# --------------------------------------------------------------------
def _build_phase_panels_script(watercolor_lib: list[dict],
                                ambient_lib: list[dict],
                                base_clips_lib: list[dict]) -> str:
    """Construct the full support script block (CSS + JS) with library data baked in."""
    # Python-side JSON-escape of the library lists.
    import json as _json
    watercolor_json = _json.dumps(watercolor_lib)
    ambient_json = _json.dumps([a["key"] for a in ambient_lib])
    base_clips_json = _json.dumps([b["key"] for b in base_clips_lib])

    # Build the full block with {placeholders} for library data only (all other
    # braces are literal JS/CSS; use %s-style formatting to avoid .format()
    # trampling every curly brace).
    block = """
<!-- BEGIN LD V3 Phase B/A Authoring Panels (injected by patch_v38_phase_b.py) -->
<style>
  #mn-phase-panels { margin: 12px 0 4px; font-family: inherit; font-size: 13px; }
  .mn-phase-panel { margin: 8px 0; background: #1c2030; border-radius: 6px;
                    border: 1px solid #2a3040; overflow: hidden; }
  .mn-phase-panel > summary { padding: 8px 12px; cursor: pointer;
                              font-weight: 600; color: #c9d1d9;
                              background: linear-gradient(90deg,#242a3d,#1c2030);
                              user-select: none; }
  .mn-phase-panel > summary::marker { color: #58a6ff; }
  .mn-phase-panel-inner { padding: 10px 12px; display: grid;
                          grid-template-columns: 1fr; gap: 8px; }
  .mn-phase-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .mn-phase-row label { color: #c9d1d9; font-size: 12px; min-width: 80px; }
  .mn-phase-row input, .mn-phase-row select, .mn-phase-row textarea {
    background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;
    border-radius: 4px; padding: 4px 6px; font-family: inherit; font-size: 12px;
  }
  .mn-phase-row textarea { width: 100%%; min-height: 80px; resize: vertical; }
  .mn-phase-row button { background: #238636; color: white; border: 0;
                         border-radius: 4px; padding: 4px 10px; cursor: pointer;
                         font-size: 12px; }
  .mn-phase-row button:hover { background: #2ea043; }
  .mn-phase-row button:disabled { opacity: 0.5; cursor: not-allowed; }
  .mn-phase-row button.mn-secondary { background: #30363d; }
  .mn-phase-row button.mn-secondary:hover { background: #484f58; }
  .mn-phase-media { width: 100%%; margin-top: 4px; }
  .mn-phase-media audio, .mn-phase-media video { width: 100%%; max-width: 640px; }
  .mn-phase-disclaimer { color: #8b949e; font-size: 11px; font-style: italic;
                         margin: 4px 0; }
  .mn-phase-saveind { font-size: 11px; color: #8b949e; margin-left: 6px; }
  /* Watercolor timeline */
  .mn-wc-timeline { position: relative; height: 64px;
                    background: #0d1117; border: 1px solid #30363d;
                    border-radius: 4px; margin-top: 6px; overflow: hidden; }
  .mn-wc-waveform { position: absolute; left: 0; top: 0; right: 0; bottom: 0; }
  .mn-wc-strip-fallback { position: absolute; left: 0; top: 50%%;
                           height: 2px; right: 0; background: #30363d; }
  .mn-wc-marker { position: absolute; top: 4px; width: 26px; height: 56px;
                  background: rgba(88,166,255,0.15); border: 1px solid #58a6ff;
                  border-radius: 3px; cursor: grab; display: flex;
                  align-items: center; justify-content: center; font-size: 18px;
                  user-select: none; }
  .mn-wc-marker:hover { background: rgba(88,166,255,0.35); }
  .mn-wc-library { display: flex; gap: 6px; flex-wrap: wrap;
                   padding: 6px; background: #0d1117; border: 1px solid #30363d;
                   border-radius: 4px; margin-top: 6px; max-height: 120px;
                   overflow-y: auto; }
  .mn-wc-lib-item { width: 60px; height: 60px; background-size: cover;
                    background-position: center; border: 1px solid #30363d;
                    border-radius: 4px; cursor: grab; position: relative;
                    display: flex; align-items: flex-end; justify-content: center;
                    color: white; font-size: 10px; text-shadow: 0 0 2px black; }
  .mn-wc-lib-item[draggable="true"]:hover { border-color: #58a6ff; }
  .mn-wc-cue-popover { position: absolute; z-index: 10; background: #1c2030;
                       border: 1px solid #58a6ff; border-radius: 4px;
                       padding: 6px; display: flex; flex-direction: column;
                       gap: 4px; font-size: 11px; }
  .mn-phase-status-pill { display: inline-block; padding: 1px 6px;
                           border-radius: 8px; font-size: 10px;
                           background: #30363d; color: #c9d1d9; }
  .mn-phase-status-pill[data-status="approved"] { background: #238636; color: white; }
  .mn-phase-status-pill[data-status="needs_review"] { background: #9e6a03; color: white; }
</style>
<!-- WaveSurfer.js v7: CDN-loaded with SRI. Gracefully degrades to plain
     strip on network failure. -->
<script src="https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.min.js"
        onerror="window.__mnWaveSurferCDNFailed=true"
        crossorigin="anonymous"></script>
<script>
(function() {
  var SERVER_V2 = "http://localhost:5111";
  var WATERCOLOR_LIBRARY = __WATERCOLOR_LIBRARY_JSON__;
  var AMBIENT_LIBRARY = __AMBIENT_LIBRARY_JSON__;
  var BASE_CLIPS_LIBRARY = __BASE_CLIPS_LIBRARY_JSON__;
  var ANIMATIONS = ["fade_in", "slide_in", "gentle_pan"];

  function $(id) { return document.getElementById(id); }

  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (k === "class") n.className = attrs[k];
        else if (k === "style") n.setAttribute("style", attrs[k]);
        else n.setAttribute(k, attrs[k]);
      }
    }
    if (kids) {
      for (var i=0; i<kids.length; i++) {
        var kid = kids[i];
        if (typeof kid === "string") n.appendChild(document.createTextNode(kid));
        else if (kid) n.appendChild(kid);
      }
    }
    return n;
  }

  function renderPanel(phase, expanded) {
    // phase: "a" or "b"
    var speaker = phase === "b" ? "Cedric" : "Chipper";
    var panelLabel = phase === "b"
      ? "Phase B -- Cedric Meditation"
      : "Phase A -- Chipper Demo";
    var baseLabel = phase === "b" ? "Cedric base clip" : "Empty desk background";

    var det = el("details", {
      "class": "mn-phase-panel",
      "data-phase": phase,
    });
    if (expanded) det.setAttribute("open", "open");
    det.appendChild(el("summary", {}, [panelLabel,
      el("span", {"class": "mn-phase-status-pill", id: "phase-"+phase+"-status-pill"}, ["draft"])]));

    var inner = el("div", {"class": "mn-phase-panel-inner"}, []);

    // Script row
    var scriptRow = el("div", {"class": "mn-phase-row"}, [
      el("label", {"for": "phase-"+phase+"-script"}, ["Script ("+speaker+")"]),
    ]);
    var scriptArea = el("textarea", {
      id: "phase-"+phase+"-script",
      rows: "4", placeholder: "Paste "+speaker+" narration; use [pause 2s] for silences...",
    }, []);
    inner.appendChild(scriptRow);
    inner.appendChild(scriptArea);

    var regenRow = el("div", {"class": "mn-phase-row"}, [
      el("button", {id: "phase-"+phase+"-regen-btn"}, ["\\u{1F399} Regen Audio"]),
      el("span", {"class": "mn-phase-saveind", id: "phase-"+phase+"-regen-ind"}, [""]),
    ]);
    inner.appendChild(regenRow);
    var voicePlayer = el("audio", {
      id: "phase-"+phase+"-voice-player", controls: "controls", preload: "metadata",
    }, []);
    voicePlayer.style.display = "none";
    inner.appendChild(voicePlayer);

    // Mix row
    var ambientSel = el("select", {id: "phase-"+phase+"-ambient-sel"}, []);
    ambientSel.appendChild(el("option", {value: ""}, ["(pick ambient preset...)"]));
    for (var i=0; i<AMBIENT_LIBRARY.length; i++) {
      ambientSel.appendChild(el("option", {value: AMBIENT_LIBRARY[i]}, [AMBIENT_LIBRARY[i]]));
    }
    inner.appendChild(el("div", {"class": "mn-phase-row"}, [
      el("label", {}, ["Ambient bed"]), ambientSel,
      el("button", {id: "phase-"+phase+"-mix-btn"}, ["\\u{1F39B} Mix Audio"]),
      el("span", {"class": "mn-phase-saveind", id: "phase-"+phase+"-mix-ind"}, [""]),
    ]));
    var mixPlayer = el("audio", {
      id: "phase-"+phase+"-mix-player", controls: "controls", preload: "metadata",
    }, []);
    mixPlayer.style.display = "none";
    inner.appendChild(mixPlayer);

    // Lipsync row
    var baseSel = el("select", {id: "phase-"+phase+"-base-sel"}, []);
    baseSel.appendChild(el("option", {value: ""}, ["(pick base clip...)"]));
    for (var j=0; j<BASE_CLIPS_LIBRARY.length; j++) {
      baseSel.appendChild(el("option", {value: BASE_CLIPS_LIBRARY[j]}, [BASE_CLIPS_LIBRARY[j]]));
    }
    inner.appendChild(el("div", {"class": "mn-phase-row"}, [
      el("label", {}, [baseLabel]), baseSel,
      el("button", {id: "phase-"+phase+"-lipsync-btn"}, ["\\u{1F39E} Send for Lipsync"]),
      el("span", {"class": "mn-phase-saveind", id: "phase-"+phase+"-lipsync-ind"}, [""]),
    ]));
    var lipsyncPlayer = el("video", {
      id: "phase-"+phase+"-lipsync-player", controls: "controls", preload: "metadata",
    }, []);
    lipsyncPlayer.style.display = "none";
    inner.appendChild(lipsyncPlayer);

    // Watercolor timeline
    inner.appendChild(el("label", {}, ["Watercolor cues (drag onto strip)"]));
    var timeline = el("div", {"class": "mn-wc-timeline",
      id: "phase-"+phase+"-timeline"}, []);
    timeline.appendChild(el("div", {"class": "mn-wc-waveform",
      id: "phase-"+phase+"-wave"}, []));
    timeline.appendChild(el("div", {"class": "mn-wc-strip-fallback"}, []));
    inner.appendChild(timeline);
    var library = el("div", {"class": "mn-wc-library",
      id: "phase-"+phase+"-lib"}, []);
    for (var w=0; w<WATERCOLOR_LIBRARY.length; w++) {
      var item = WATERCOLOR_LIBRARY[w];
      var thumb = el("div", {
        "class": "mn-wc-lib-item",
        draggable: "true",
        "data-key": item.key,
        "data-cue-type": item.cue_type,
        title: item.key+" ("+item.cue_type+")",
        style: item.cue_type === "png"
          ? "background-image: url('"+SERVER_V2+"/api/phase_b/watercolor/"+item.filename+"');"
          : "background-color: #4080FF;",
      }, [item.key]);
      library.appendChild(thumb);
    }
    inner.appendChild(library);
    inner.appendChild(el("div", {"class": "mn-phase-disclaimer"}, [
      "Preview shows cue timing to \u00B150ms. Final render is frame-accurate."
    ]));

    // Preview button
    inner.appendChild(el("div", {"class": "mn-phase-row"}, [
      el("button", {id: "phase-"+phase+"-preview-btn", "class": "mn-secondary"},
         ["\u25B6 Preview Phase "+phase.toUpperCase()+" Stitched"]),
      el("span", {"class": "mn-phase-saveind", id: "phase-"+phase+"-preview-ind"}, [""]),
    ]));
    var previewPlayer = el("video", {
      id: "phase-"+phase+"-preview-player", controls: "controls", preload: "metadata",
    }, []);
    previewPlayer.style.display = "none";
    inner.appendChild(previewPlayer);

    det.appendChild(inner);
    return det;
  }

  function setSaveInd(elId, text, color) {
    var node = $(elId);
    if (!node) return;
    node.textContent = text || "";
    node.style.color = color || "#8b949e";
    if (text) setTimeout(function(){
      if (node.textContent === text) { node.textContent = ""; }
    }, 4000);
  }

  function hydratePanel(phase, state) {
    var scriptEl = $("phase-"+phase+"-script");
    if (scriptEl) scriptEl.value = state["phase_"+phase+"_script"] || "";
    var statusEl = $("phase-"+phase+"-status-pill");
    if (statusEl) {
      var s = state["phase_"+phase+"_status"] || "draft";
      statusEl.textContent = s;
      statusEl.setAttribute("data-status", s);
    }
    var ambSel = $("phase-"+phase+"-ambient-sel");
    if (ambSel) ambSel.value = state["phase_"+phase+"_ambient_preset_id"] || "";
    var baseSel = $("phase-"+phase+"-base-sel");
    var baseField = phase === "b"
      ? state["phase_b_cedric_base_clip_id"]
      : state["phase_a_empty_desk_bg_id"];
    if (baseSel) baseSel.value = baseField || "";
    // Load media if present.
    var vsf = state["phase_"+phase+"_voice_stem_file"];
    if (vsf) {
      var vp = $("phase-"+phase+"-voice-player");
      if (vp) {
        vp.src = SERVER_V2+"/api/phase_b/media/"+encodeURIComponent(vsf);
        vp.style.display = "block";
      }
    }
    var maf = state["phase_"+phase+"_mixed_audio_file"];
    if (maf) {
      var mp = $("phase-"+phase+"-mix-player");
      if (mp) {
        mp.src = SERVER_V2+"/api/phase_b/media/"+encodeURIComponent(maf);
        mp.style.display = "block";
      }
    }
    var lsf = state["phase_"+phase+"_lipsync_file"];
    if (lsf) {
      var lp = $("phase-"+phase+"-lipsync-player");
      if (lp) {
        lp.src = SERVER_V2+"/api/phase_b/media/"+encodeURIComponent(lsf);
        lp.style.display = "block";
      }
    }
    renderCues(phase, state);
  }

  function currentCues(phase, state) {
    var raw = state["phase_"+phase+"_watercolor_cues_json"] || "[]";
    try { return JSON.parse(raw); } catch (_) { return []; }
  }

  function renderCues(phase, state) {
    var tl = $("phase-"+phase+"-timeline");
    if (!tl) return;
    // Remove old markers (keep .mn-wc-waveform and .mn-wc-strip-fallback).
    var old = tl.querySelectorAll(".mn-wc-marker");
    for (var i=0; i<old.length; i++) old[i].remove();
    var cues = currentCues(phase, state);
    var audioDur = getAudioDuration(phase);
    if (!audioDur || audioDur < 0.1) audioDur = 60; // fallback width
    for (var j=0; j<cues.length; j++) {
      var cue = cues[j];
      var pct = Math.max(0, Math.min(1, (cue.timestamp_ms/1000) / audioDur));
      var marker = el("div", {
        "class": "mn-wc-marker",
        "data-idx": String(j),
        title: cue.key+" @ "+(cue.timestamp_ms/1000).toFixed(2)+"s ("+cue.animation+")",
        style: "left: "+(pct*100).toFixed(2)+"%%;",
      }, ["\\u{1F3A8}"]);
      (function(idx){
        marker.addEventListener("click", function(e){
          e.stopPropagation();
          showCuePopover(phase, idx, marker);
        });
      })(j);
      tl.appendChild(marker);
    }
  }

  function getAudioDuration(phase) {
    // Prefer lipsync player (final), then mix, then voice.
    var candidates = ["lipsync", "mix", "voice"];
    for (var i=0; i<candidates.length; i++) {
      var p = $("phase-"+phase+"-"+candidates[i]+"-player");
      if (p && p.duration && !isNaN(p.duration)) return p.duration;
    }
    return 0;
  }

  function showCuePopover(phase, idx, anchor) {
    document.querySelectorAll(".mn-wc-cue-popover").forEach(function(n){ n.remove(); });
    var state = currentStateSnapshot();
    var cues = currentCues(phase, state);
    var cue = cues[idx];
    if (!cue) return;
    var rect = anchor.getBoundingClientRect();
    var pop = el("div", {"class": "mn-wc-cue-popover",
      style: "left:"+(rect.left)+"px; top:"+(rect.bottom+4+window.scrollY)+"px;"}, []);
    var animSel = el("select", {}, []);
    for (var i=0; i<ANIMATIONS.length; i++) {
      var opt = el("option", {value: ANIMATIONS[i]}, [ANIMATIONS[i]]);
      if (ANIMATIONS[i] === cue.animation) opt.setAttribute("selected", "selected");
      animSel.appendChild(opt);
    }
    var durInput = el("input", {type: "number", min: "100", step: "100",
      value: String(cue.duration_ms)}, []);
    animSel.addEventListener("change", function() {
      cue.animation = animSel.value;
      cues[idx] = cue;
      saveCues(phase, cues);
    });
    durInput.addEventListener("change", function() {
      cue.duration_ms = parseInt(durInput.value, 10) || 1000;
      cues[idx] = cue;
      saveCues(phase, cues);
    });
    var delBtn = el("button", {"class": "mn-secondary"}, ["Delete"]);
    delBtn.addEventListener("click", function() {
      cues.splice(idx, 1);
      saveCues(phase, cues);
      pop.remove();
    });
    pop.appendChild(el("div", {}, ["Cue: "+cue.key]));
    pop.appendChild(el("div", {}, ["Animation: ", animSel]));
    pop.appendChild(el("div", {}, ["Duration ms: ", durInput]));
    pop.appendChild(delBtn);
    document.body.appendChild(pop);
    setTimeout(function(){
      document.addEventListener("click", function handler(e) {
        if (!pop.contains(e.target)) { pop.remove(); document.removeEventListener("click", handler); }
      });
    }, 50);
  }

  function saveCues(phase, cues) {
    if (typeof window.pathappPatch !== "function") {
      console.warn("[phase_"+phase+"] pathappPatch not available");
      return;
    }
    // pathappPatch(null, ...) routes to /api/v2/module/patch via V2 branch.
    window.pathappPatch(null, "phase_"+phase+"_watercolor_cues_json",
      JSON.stringify(cues), {
        saveind: $("phase-"+phase+"-preview-ind"),
      }).then(function() {
        // Re-hydrate to reflect server-normalized order.
        refreshState();
      }).catch(function(err) {
        setSaveInd("phase-"+phase+"-preview-ind",
                    "Save failed: "+(err && err.message || err), "#f85149");
      });
  }

  var __stateSnapshot = null;
  function currentStateSnapshot() { return __stateSnapshot || {}; }

  function refreshState() {
    return fetch(SERVER_V2+"/api/state", {cache: "no-store"})
      .then(function(r){ return r.ok ? r.json() : null; })
      .then(function(state) {
        if (!state) return null;
        __stateSnapshot = state;
        hydratePanel("b", state);
        hydratePanel("a", state);
        return state;
      }).catch(function(){ return null; });
  }

  function wireDragDrop(phase) {
    var tl = $("phase-"+phase+"-timeline");
    var lib = $("phase-"+phase+"-lib");
    if (!tl || !lib) return;
    lib.querySelectorAll(".mn-wc-lib-item").forEach(function(item) {
      item.addEventListener("dragstart", function(e) {
        e.dataTransfer.setData("text/plain",
          JSON.stringify({key: item.getAttribute("data-key"),
                          cue_type: item.getAttribute("data-cue-type")}));
      });
    });
    tl.addEventListener("dragover", function(e){ e.preventDefault(); });
    tl.addEventListener("drop", function(e){
      e.preventDefault();
      var payload;
      try { payload = JSON.parse(e.dataTransfer.getData("text/plain")); }
      catch (_) { return; }
      if (!payload || !payload.key) return;
      var rect = tl.getBoundingClientRect();
      var pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      var dur = getAudioDuration(phase) || 60;
      var timestamp_ms = Math.round(pct * dur * 1000);
      var state = currentStateSnapshot();
      var cues = currentCues(phase, state);
      cues.push({
        timestamp_ms: timestamp_ms,
        key: payload.key,
        animation: "fade_in",
        duration_ms: 1500,
        cue_type: payload.cue_type || "png",
      });
      saveCues(phase, cues);
    });
  }

  function wireButtons(phase) {
    var regenBtn = $("phase-"+phase+"-regen-btn");
    if (regenBtn) regenBtn.addEventListener("click", function() {
      var script = $("phase-"+phase+"-script").value || "";
      if (!script.trim()) {
        setSaveInd("phase-"+phase+"-regen-ind", "Script empty", "#f85149"); return;
      }
      // Save script via pathappPatch first (so it's on server if TTS fails).
      if (typeof window.pathappPatch === "function") {
        window.pathappPatch(null, "phase_"+phase+"_script", script, {}).catch(function(){});
      }
      regenBtn.disabled = true;
      var oldText = regenBtn.textContent;
      regenBtn.textContent = "\u23F3 Generating...";
      setSaveInd("phase-"+phase+"-regen-ind", "Calling ElevenLabs...", "#58a6ff");
      fetch(SERVER_V2+"/api/phase_b/regen_audio", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({phase: phase, script: script}),
      }).then(function(r) {
        return r.json().then(function(j){ return {ok: r.ok, body: j}; });
      }).then(function(res) {
        regenBtn.textContent = oldText;
        regenBtn.disabled = false;
        if (!res.ok) {
          setSaveInd("phase-"+phase+"-regen-ind",
            "Fail: "+(res.body.hint || res.body.error), "#f85149");
          return;
        }
        setSaveInd("phase-"+phase+"-regen-ind",
          "OK ("+res.body.duration_s+"s)", "#2ea043");
        refreshState();
      }).catch(function(err) {
        regenBtn.textContent = oldText;
        regenBtn.disabled = false;
        setSaveInd("phase-"+phase+"-regen-ind", "Error: "+err, "#f85149");
      });
    });
    var mixBtn = $("phase-"+phase+"-mix-btn");
    if (mixBtn) mixBtn.addEventListener("click", function() {
      var preset = $("phase-"+phase+"-ambient-sel").value;
      if (!preset) {
        setSaveInd("phase-"+phase+"-mix-ind", "Pick an ambient preset", "#f85149"); return;
      }
      mixBtn.disabled = true;
      setSaveInd("phase-"+phase+"-mix-ind", "Mixing...", "#58a6ff");
      fetch(SERVER_V2+"/api/phase_b/mix_audio", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({phase: phase, ambient_preset_id: preset}),
      }).then(function(r) {
        return r.json().then(function(j){ return {ok: r.ok, body: j}; });
      }).then(function(res) {
        mixBtn.disabled = false;
        if (!res.ok) {
          setSaveInd("phase-"+phase+"-mix-ind",
            "Fail: "+(res.body.hint || res.body.error), "#f85149");
          return;
        }
        setSaveInd("phase-"+phase+"-mix-ind", "OK", "#2ea043");
        refreshState();
      }).catch(function(err) {
        mixBtn.disabled = false;
        setSaveInd("phase-"+phase+"-mix-ind", "Error: "+err, "#f85149");
      });
    });
    var lipsyncBtn = $("phase-"+phase+"-lipsync-btn");
    if (lipsyncBtn) lipsyncBtn.addEventListener("click", function() {
      var base = $("phase-"+phase+"-base-sel").value;
      if (!base) {
        setSaveInd("phase-"+phase+"-lipsync-ind", "Pick a base clip", "#f85149"); return;
      }
      lipsyncBtn.disabled = true;
      setSaveInd("phase-"+phase+"-lipsync-ind", "ByteDance (~60-90s)...", "#58a6ff");
      fetch(SERVER_V2+"/api/phase_b/lipsync", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({phase: phase, base_clip_id: base}),
      }).then(function(r) {
        return r.json().then(function(j){ return {ok: r.ok, body: j}; });
      }).then(function(res) {
        lipsyncBtn.disabled = false;
        if (!res.ok) {
          setSaveInd("phase-"+phase+"-lipsync-ind",
            "Fail: "+(res.body.hint || res.body.error), "#f85149");
          return;
        }
        setSaveInd("phase-"+phase+"-lipsync-ind", "OK", "#2ea043");
        refreshState();
      }).catch(function(err) {
        lipsyncBtn.disabled = false;
        setSaveInd("phase-"+phase+"-lipsync-ind", "Error: "+err, "#f85149");
      });
    });
    var previewBtn = $("phase-"+phase+"-preview-btn");
    if (previewBtn) previewBtn.addEventListener("click", function() {
      previewBtn.disabled = true;
      var oldText = previewBtn.textContent;
      previewBtn.textContent = "\u23F3 Rendering...";
      setSaveInd("phase-"+phase+"-preview-ind", "Composing overlay...", "#58a6ff");
      fetch(SERVER_V2+"/api/phase_b/preview", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({phase: phase}),
      }).then(function(r) {
        if (!r.ok) {
          return r.json().then(function(j){
            throw new Error(j.hint || j.error || "HTTP "+r.status);
          });
        }
        return r.blob();
      }).then(function(blob) {
        var pl = $("phase-"+phase+"-preview-player");
        if (pl.dataset.lastUrl) {
          try { URL.revokeObjectURL(pl.dataset.lastUrl); } catch (_) {}
        }
        var url = URL.createObjectURL(blob);
        pl.dataset.lastUrl = url;
        pl.src = url;
        pl.style.display = "block";
        try { pl.play(); } catch (_) {}
        previewBtn.disabled = false;
        previewBtn.textContent = oldText;
        setSaveInd("phase-"+phase+"-preview-ind", "OK", "#2ea043");
      }).catch(function(err) {
        previewBtn.disabled = false;
        previewBtn.textContent = oldText;
        setSaveInd("phase-"+phase+"-preview-ind",
          "Fail: "+(err && err.message || err), "#f85149");
      });
    });
  }

  function tryMountWaveSurfer(phase) {
    if (window.__mnWaveSurferCDNFailed || typeof WaveSurfer === "undefined") {
      // Fallback: simple visual strip.
      return;
    }
    var waveEl = $("phase-"+phase+"-wave");
    if (!waveEl) return;
    try {
      var ws = WaveSurfer.create({
        container: waveEl,
        waveColor: "#30363d", progressColor: "#58a6ff",
        cursorColor: "#58a6ff", height: 56, interact: true,
      });
      ws.on("click", function(pct){
        // No-op — drag-drop handles cue creation; click scrubs.
      });
      // Load audio (prefer lipsync, then mix, then voice stem).
      var state = currentStateSnapshot();
      var audioFile = state["phase_"+phase+"_lipsync_file"]
                   || state["phase_"+phase+"_mixed_audio_file"]
                   || state["phase_"+phase+"_voice_stem_file"];
      if (audioFile) {
        ws.load(SERVER_V2+"/api/phase_b/media/"+encodeURIComponent(audioFile));
      }
      window["__phase_"+phase+"_ws"] = ws;
    } catch (e) { /* fall back to strip */ }
  }

  function init() {
    var mount = $("mn-phase-panels");
    if (!mount) return setTimeout(init, 50);
    mount.innerHTML = "";
    mount.appendChild(renderPanel("b", true));
    mount.appendChild(renderPanel("a", false));
    wireButtons("b"); wireButtons("a");
    wireDragDrop("b"); wireDragDrop("a");
    refreshState().then(function(){
      tryMountWaveSurfer("b"); tryMountWaveSurfer("a");
    });
    console.log("[phase_b_panels] LD V3 wired");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
</script>
<!-- END LD V3 Phase B/A Authoring Panels -->
"""
    # Substitute library JSON into the placeholder tokens.
    block = block % ()  # escape any stray % in the CSS (we wrote %% for literals)
    block = block.replace("__WATERCOLOR_LIBRARY_JSON__", watercolor_json)
    block = block.replace("__AMBIENT_LIBRARY_JSON__", ambient_json)
    block = block.replace("__BASE_CLIPS_LIBRARY_JSON__", base_clips_json)
    return block


# --------------------------------------------------------------------
# Main
# --------------------------------------------------------------------
def main() -> int:
    if not TARGET.exists():
        print(f"[phase_b_patcher] FATAL target not found: {TARGET}", file=sys.stderr)
        return 2

    print(f"[phase_b_patcher] reading {TARGET}")
    src = TARGET.read_text(encoding="utf-8")

    pre_sha, pre_n = _sha256_of_sorted_b64_uris(src)
    print(f"[phase_b_patcher] pre-patch base64 URIs: {pre_n}  sha256={pre_sha}")

    # Idempotency guard.
    if "<!-- BEGIN LD V3 Phase B/A Authoring Panels" in src:
        print(
            "[phase_b_patcher] support block ALREADY present -- "
            "patch already applied. Restore from .bak before re-running."
        )
        return 1

    # Scan libraries.
    watercolor_lib = _scan_library(WATERCOLOR_DIR, (".png", ".mov", ".mp4"))
    ambient_lib = _scan_library(AMBIENT_DIR, (".mp3",))
    base_clips_lib = _scan_library(LIPSYNC_BASES_DIR, (".mp4", ".mov"))
    print(f"[phase_b_patcher] libraries: watercolor={len(watercolor_lib)} "
          f"ambient={len(ambient_lib)} base_clips={len(base_clips_lib)}")

    e3_script = _build_phase_panels_script(watercolor_lib, ambient_lib, base_clips_lib)
    e3_old = "</body></html>"
    e3_new = e3_script.rstrip("\n") + "\n</body></html>"

    edits = [
        ("E1 mount mn-phase-panels container", E1_OLD, E1_NEW),
        ("E2 EOF phase-panels support block", e3_old, e3_new),
    ]
    patched = src
    for label, old, new in edits:
        _assert_single_match(patched, old, label)
        patched = patched.replace(old, new)
        print(f"[phase_b_patcher] applied: {label}")

    # Rule 7 Path B: base64 byte-identical.
    post_sha, post_n = _sha256_of_sorted_b64_uris(patched)
    print(f"[phase_b_patcher] post-patch base64 URIs: {post_n}  sha256={post_sha}")
    if (pre_sha, pre_n) != (post_sha, post_n):
        raise SystemExit(
            "[phase_b_patcher] FATAL base64 SHA256 mismatch -- aborting "
            "without writing. Rule 7 Path B invariant violated."
        )
    print("[phase_b_patcher] base64 byte-identical: OK")

    # Structural sanity.
    for needle in ("</body>", "</html>"):
        if patched.count(needle) != src.count(needle):
            raise SystemExit(
                f"[phase_b_patcher] FATAL {needle!r} count changed "
                f"({src.count(needle)} -> {patched.count(needle)})"
            )
    # Expected <script> delta: +1 inline block + +1 for WaveSurfer CDN script tag
    # (actually +2 <script ...> opens but the CDN one is self-closing <script src>
    # — counts as one open tag).
    src_open = src.count("<script>") + src.count("<script ")
    post_open = patched.count("<script>") + patched.count("<script ")
    # 2 new opens expected: the CDN WaveSurfer script tag + the inline support script.
    delta = post_open - src_open
    if delta != 2:
        raise SystemExit(
            f"[phase_b_patcher] FATAL <script> open delta unexpected: "
            f"pre={src_open} post={post_open} (delta {delta}, expected 2)"
        )

    _node_syntax_check_scripts(patched)

    # Backup BEFORE write.
    ts = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    bak = TARGET.with_suffix(TARGET.suffix + f".bak_phase_b_{ts}")
    shutil.copy2(TARGET, bak)
    print(f"[phase_b_patcher] backup: {bak.name}")

    TARGET.write_text(patched, encoding="utf-8")
    print(
        f"[phase_b_patcher] wrote {TARGET} "
        f"({len(patched):,} bytes; pre {len(src):,}; delta +{len(patched)-len(src)})"
    )

    # Post-write static-presence checks.
    post = TARGET.read_text(encoding="utf-8")
    # Static checks match patterns actually present in the patched HTML.
    # Element IDs are JS-concatenated at runtime ("phase-"+phase+"-script"),
    # not literal in source, so we check the runtime-constructor fragments.
    static_checks = [
        ("mn-phase-panels",                  1, ">=", "E1 mount container id"),
        ("LD V3 Phase B/A Authoring Panels", 2, ">=", "E2 BEGIN/END markers"),
        ('"phase-"+phase+"-script"',         1, ">=", "Phase B/A script textarea id builder"),
        ('renderPanel("b"',                  1, ">=", "Phase B panel render call"),
        ('renderPanel("a"',                  1, ">=", "Phase A panel render call"),
        ("/api/phase_b/regen_audio",         1, ">=", "regen_audio endpoint wired"),
        ("/api/phase_b/mix_audio",           1, ">=", "mix_audio endpoint wired"),
        ("/api/phase_b/lipsync",             1, ">=", "lipsync endpoint wired"),
        ("/api/phase_b/preview",             1, ">=", "preview endpoint wired"),
        ("wavesurfer.js@7",                  1, ">=", "WaveSurfer CDN load"),
        ("mn-wc-timeline",                   2, ">=", "Timeline widget class"),
        ("mn-wc-library",                    2, ">=", "Library panel class"),
        ("mn-wc-marker",                     1, ">=", "Marker class"),
        ('phase_"+phase+"_watercolor_cues_json',
                                              1, ">=", "Cues field pathappPatch call"),
        ("pathappPatch(null,",               1, ">=", "null-beat-id module-patch route"),
    ]
    for needle, threshold, op, label in static_checks:
        c = post.count(needle)
        ok = (c >= threshold) if op == ">=" else (c == threshold)
        flag = "OK" if ok else "FAIL"
        print(f"[phase_b_patcher] static {flag}: {label} ({c} {op} {threshold})")
        if not ok:
            raise SystemExit(f"[phase_b_patcher] FATAL static check: {label}")

    print("[phase_b_patcher] all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
