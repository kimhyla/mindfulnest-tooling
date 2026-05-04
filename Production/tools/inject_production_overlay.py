#!/usr/bin/env python3
"""
inject_production_overlay.py — Storyboard Production Overlay injector (v1 MVP)

Injects a thin UI overlay (JS + CSS only) into an existing storyboard HTML so
Kim can drive animation production from the browser. All API calls, file I/O,
and state persistence happen in the companion Python server (production_server.py)
on http://localhost:5111 — this script only adds UI code.

CLAUDE.md Rule 7 compliance:
  - Only <script> and <style> blocks are added (Path B)
  - No raw HTML elements injected — all overlay DOM is built dynamically in JS
  - MD5-validates every embedded base64 image byte-for-byte before/after
  - Validates no API keys or external URLs leaked into output

CLI:
  python3 inject_production_overlay.py \\
      --input  Production/Event_1/storyboard_v14.html \\
      --output Production/Event_1/storyboard_v14_prod.html \\
      --event-id "Event_1"

  python3 inject_production_overlay.py --smoke-test
"""

from __future__ import annotations

# --- WA-C14 Doppler migration (per LD-208) ---
# credential_store reads from Doppler env vars first, falls back to API_KEYS_MASTER.md.
import os as _os, sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve()
while _p.parent != _p and _p.name != "Production":
    _p = _p.parent
if _p.name == "Production":
    _sys.path.insert(0, str(_p))
from lib.credential_store import get_secret  # noqa: E402
# --- end WA-C14 boilerplate ---

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants — API-key and external-URL denylists used by validation
# ---------------------------------------------------------------------------

# Key *prefixes* from Production/API_KEYS_MASTER.md. These must NEVER appear
# in an injected HTML. They are short enough to be unambiguous.
BANNED_KEY_FRAGMENTS = [
    get_secret("WAVESPEED_API_KEY"),  # WaveSpeed
    get_secret("ELEVENLABS_API_KEY"),  # ElevenLabs
]

# External hosts that must never appear in INJECTED code. We only check inside
# the injected block, not the whole file — the original storyboard may legally
# reference asset CDNs for <img>. The overlay must only talk to localhost.
BANNED_EXTERNAL_HOSTS = [
    "wavespeed.ai",
    "elevenlabs.io",
    "directus.mindfulnest",
    "api.openai.com",
    "api.anthropic.com",
]

INJECT_MARKER_START = "<!-- BEGIN PRODUCTION OVERLAY (injected) -->"
INJECT_MARKER_END = "<!-- END PRODUCTION OVERLAY (injected) -->"

SERVER_ORIGIN = "http://localhost:5111"


# ---------------------------------------------------------------------------
# Beat / image extraction
# ---------------------------------------------------------------------------

def _js_obj_to_json(js_str: str) -> str:
    """Convert JS object syntax ({s:"val",t:"val"}) to valid JSON."""
    # Add quotes around bare keys: s: -> "s":
    result = re.sub(r'(\{|,)\s*([a-zA-Z_]\w*)\s*:', r'\1"\2":', js_str)
    # Fix JS-escaped single quotes (\' is valid in JS strings, not in JSON)
    result = result.replace("\\'", "'")
    return result


def extract_storyboard_data(html: str) -> dict:
    """Parse beat data from storyboard HTML.

    Supports two formats:
    1. Legacy: window.storyboardData = {...};  (JSON with "lines" array)
    2. Builder v14+: var SP=[...]; var L=[{s:,t:,i:,a:,p:,g:},...];
       where s=speaker (string or index), t=text, i=image key,
       a=audio key, p=pause, g=group/section.
    """
    # --- Try legacy format first ---
    legacy = re.search(
        r"window\.storyboardData\s*=\s*(\{.*?\})\s*;",
        html,
        re.DOTALL,
    )
    if legacy:
        try:
            return json.loads(legacy.group(1))
        except json.JSONDecodeError as exc:
            raise ValueError(f"window.storyboardData is not valid JSON: {exc}") from exc

    # --- Builder v14+ format: var SP=[...] + var L=[...] + var TH={...} ---
    sp_match = re.search(r'var SP\s*=\s*(\[.*?\])\s*;', html)
    l_match = re.search(r'var L\s*=\s*(\[.*?\])\s*;', html, re.DOTALL)
    th_match = re.search(r'var TH\s*=\s*\{', html)

    if not l_match:
        raise ValueError(
            "Could not find beat data in HTML — expected either "
            "`window.storyboardData = {...};` or `var L=[...];`. "
            "Is this a storyboard built by build_storyboard.py?"
        )

    # Parse speakers array
    speakers = []
    if sp_match:
        try:
            speakers = json.loads(sp_match.group(1))
        except json.JSONDecodeError:
            speakers = []

    # Parse lines array (JS object syntax -> JSON)
    raw_lines = _js_obj_to_json(l_match.group(1))
    try:
        lines_raw = json.loads(raw_lines)
    except json.JSONDecodeError as exc:
        raise ValueError(f"var L array is not parseable: {exc}") from exc

    # Normalize each beat to the canonical schema the rest of the code expects
    lines = []
    for idx, beat in enumerate(lines_raw):
        speaker_val = beat.get("s", "")
        # If speaker is a string (direct name), use it; if index, look up in SP
        if isinstance(speaker_val, int) and speakers:
            speaker = speakers[speaker_val] if speaker_val < len(speakers) else str(speaker_val)
        else:
            speaker = str(speaker_val)

        # Resolve image: TH dict has base64 data keyed by image key
        image_key = beat.get("i", "")
        # We'll look up TH[image_key] for MD5 checking
        image_data = None
        if image_key and th_match:
            th_pattern = re.escape(image_key) + r'\s*[=:]\s*"(data:image[^"]*)"'
            img_match = re.search(r'TH\["?' + re.escape(image_key) + r'"?\]\s*=\s*"(data:image[^"]*)"', html)
            if img_match:
                image_data = img_match.group(1)

        lines.append({
            "line_number": idx + 1,
            "speaker": speaker,
            "text": beat.get("t", ""),
            "image_key": image_key,
            "image": image_data,
            "audio_key": beat.get("a"),
            "pause": beat.get("p", 0),
            "section": beat.get("g", ""),
        })

    return {"lines": lines, "speakers": speakers}


def image_hashes(data: dict) -> list[tuple[int, str]]:
    """Return [(line_number, md5), ...] for every beat that has an image."""
    hashes: list[tuple[int, str]] = []
    for beat in data.get("lines", []):
        img = beat.get("image")
        if not img:
            continue
        # hash the full data URI — if any byte drifts we catch it
        h = hashlib.md5(img.encode("utf-8")).hexdigest()
        hashes.append((beat.get("line_number", -1), h))
    return hashes


def count_tags_outside_script_style(html: str) -> int:
    """Count opening tags that are NOT <script> or <style>.

    Used as a diff sentinel: if this number changes after injection, we
    accidentally added raw HTML elements and must abort.
    """
    # strip script + style contents so we don't count tags inside them
    stripped = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # count remaining opening tags (ignore closing tags and comments)
    tags = re.findall(r"<([a-zA-Z][a-zA-Z0-9]*)\b", stripped)
    return len(tags)


# ---------------------------------------------------------------------------
# The injected overlay — CSS + JS as Python string constants
# ---------------------------------------------------------------------------

OVERLAY_CSS = r"""
/* --- Production Overlay CSS ------------------------------------------ */
#mn-prod-overlay {
    position: fixed; top: 0; left: 0; right: 0;
    background: #1c1f26; color: #e8ecf1;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    padding: 12px 18px; z-index: 99999;
    border-bottom: 2px solid #3b82f6;
    box-shadow: 0 4px 14px rgba(0,0,0,0.4);
    font-size: 13px; line-height: 1.45;
}
#mn-prod-overlay h2 { margin: 0 0 6px 0; font-size: 15px; font-weight: 600; }
#mn-prod-overlay button {
    background: #3b82f6; color: white; border: none;
    padding: 8px 14px; border-radius: 6px; font-weight: 600;
    cursor: pointer; font-size: 13px;
}
#mn-prod-overlay button:disabled { opacity: 0.5; cursor: not-allowed; }
#mn-prod-overlay button.mn-secondary {
    background: transparent; border: 1px solid #3b82f6; color: #3b82f6;
}
#mn-prod-overlay .mn-health {
    float: right; font-size: 12px; padding: 4px 8px;
    border-radius: 4px; background: #2a2f3a;
}
#mn-prod-overlay .mn-health.ok  { color: #22c55e; }
#mn-prod-overlay .mn-health.bad { color: #ef4444; }
#mn-prod-overlay .mn-progress {
    height: 8px; background: #2a2f3a; border-radius: 4px;
    margin: 8px 0; overflow: hidden;
}
#mn-prod-overlay .mn-progress-bar {
    height: 100%; background: linear-gradient(90deg, #3b82f6, #22c55e);
    width: 0%; transition: width 0.4s ease;
}
#mn-prod-overlay .mn-row { margin: 6px 0; }
#mn-prod-overlay .mn-beat-card {
    background: #242933; border-radius: 6px; padding: 8px;
    margin: 6px 0; border: 1px solid #2f3541;
}
#mn-prod-overlay .mn-beat-card video {
    max-width: 200px; border-radius: 4px; display: inline-block;
    margin-right: 6px; vertical-align: middle;
}
#mn-prod-overlay .mn-banner {
    background: #ef4444; color: white; padding: 8px;
    margin: 6px 0; border-radius: 4px; font-weight: 600;
}
#mn-prod-overlay .mn-banner.mn-warn { background: #eab308; color: #1c1f26; }
#mn-prod-body-pad { height: 220px; } /* push storyboard content down */
"""


def _build_overlay_js(event_id: str) -> str:
    """Build the injected JS. event_id is embedded as a safe JSON literal."""
    event_id_literal = json.dumps(event_id)
    server_literal = json.dumps(SERVER_ORIGIN)
    return r"""
/* --- Production Overlay JS ------------------------------------------- */
(function () {
    "use strict";
    var SERVER = __SERVER__;      // e.g. "http://localhost:5111"
    var EVENT_ID = __EVENT_ID__;
    var videoPlaying = false;
    var queuedUpdate = null;
    var statusTimer = null;
    var healthTimer = null;

    // ---------- small helpers ----------
    function el(tag, attrs, kids) {
        var e = document.createElement(tag);
        if (attrs) {
            for (var k in attrs) {
                if (k === "style") { e.setAttribute("style", attrs[k]); }
                else if (k.indexOf("on") === 0) { e[k] = attrs[k]; }
                else { e.setAttribute(k, attrs[k]); }
            }
        }
        (kids || []).forEach(function (k) {
            if (k == null) return;
            e.appendChild(typeof k === "string" ? document.createTextNode(k) : k);
        });
        return e;
    }
    function api(path, opts) {
        return fetch(SERVER + path, opts || {}).then(function (r) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            return r.json();
        });
    }
    function setStatus(msg, kind) {
        var b = document.getElementById("mn-status-line");
        if (b) { b.textContent = msg; b.className = "mn-row " + (kind || ""); }
    }

    // ---------- mount overlay shell ----------
    function mount() {
        // push content down so overlay doesn't cover anything
        var pad = el("div", { id: "mn-prod-body-pad" });
        document.body.insertBefore(pad, document.body.firstChild);

        var root = el("div", { id: "mn-prod-overlay" });
        var health = el("span", { id: "mn-health", "class": "mn-health" }, ["checking..."]);
        var title = el("h2", null, ["MindfulNest Production Overlay"]);
        title.appendChild(health);

        var testCheckbox = el("input", { type: "checkbox", id: "mn-test-mode" });
        var testLabel = el("label", { "for": "mn-test-mode", style: "margin-left:6px;" }, [
            " Test Mode (1-3 beats only)"
        ]);
        var fireBtn = el("button", { id: "mn-fire-btn", onclick: fireAway }, ["Fire Away — Generate All"]);
        var exportBtn = el("button", {
            id: "mn-export-btn",
            "class": "mn-secondary",
            style: "margin-left:8px;",
            onclick: exportSelections,
            disabled: "disabled"
        }, ["Export Selections"]);

        var progressWrap = el("div", { "class": "mn-progress" }, [
            el("div", { id: "mn-progress-bar", "class": "mn-progress-bar" })
        ]);
        var statusLine = el("div", { id: "mn-status-line", "class": "mn-row" },
            ["Ready. Event: " + EVENT_ID]);
        var beatList = el("div", { id: "mn-beat-list" });

        root.appendChild(title);
        root.appendChild(el("div", { "class": "mn-row" }, [testCheckbox, testLabel]));
        root.appendChild(el("div", { "class": "mn-row" }, [fireBtn, exportBtn]));
        root.appendChild(progressWrap);
        root.appendChild(statusLine);
        root.appendChild(beatList);
        document.body.insertBefore(root, document.body.firstChild);
    }

    // ---------- health ----------
    function pollHealth() {
        api("/api/health").then(function (r) {
            var h = document.getElementById("mn-health");
            h.textContent = "Online (" + (r.uptime_seconds | 0) + "s)";
            h.className = "mn-health ok";
        }).catch(function () {
            var h = document.getElementById("mn-health");
            h.textContent = "Offline — ask Claude to restart";
            h.className = "mn-health bad";
        });
    }

    // ---------- fire away ----------
    function fireAway() {
        var btn = document.getElementById("mn-fire-btn");
        btn.disabled = true;
        var testMode = document.getElementById("mn-test-mode").checked;
        setStatus("Submitting beats to Kling...");
        api("/api/animate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                mode: testMode ? "test" : "all",
                options_per_beat: 3
            })
        }).then(function (r) {
            setStatus("Submitted " + r.submitted + " jobs — first results in ~40s");
            if (statusTimer) clearInterval(statusTimer);
            statusTimer = setInterval(pollStatus, 10000);
            pollStatus();
        }).catch(function (e) {
            setStatus("Failed to submit: " + e.message, "mn-banner");
            btn.disabled = false;
        });
    }

    // ---------- status polling ----------
    function pollStatus() {
        api("/api/animate/status").then(function (s) {
            if (videoPlaying) { queuedUpdate = s; return; }
            renderStatus(s);
        }).catch(function () { /* server hiccup — next tick */ });
    }

    function renderStatus(s) {
        var pct = s.total_beats ? Math.round(100 * s.completed / s.total_beats) : 0;
        document.getElementById("mn-progress-bar").style.width = pct + "%";
        setStatus(
            s.completed + "/" + s.total_beats + " ready, " +
            (s.polling || 0) + " processing, " +
            (s.failed || 0) + " failed  —  $" +
            (s.cost_so_far || 0).toFixed(2) + " of $" +
            ((s.cost_so_far || 0) + (s.budget_remaining || 0)).toFixed(2)
        );

        var list = document.getElementById("mn-beat-list");
        list.innerHTML = "";
        var beats = s.beats || {};
        var keys = Object.keys(beats).sort();
        var allSelected = keys.length > 0;
        keys.forEach(function (k) {
            var b = beats[k];
            var card = el("div", { "class": "mn-beat-card" });
            card.appendChild(el("strong", null, [k + " — " + (b.status || "")]));
            if (b.status === "completed" && b.options) {
                b.options.forEach(function (opt, i) {
                    var v = el("video", { src: SERVER + opt.url, controls: "controls" });
                    v.addEventListener("play",  function () { videoPlaying = true; });
                    v.addEventListener("pause", function () { flushQueued(); });
                    v.addEventListener("ended", function () { flushQueued(); });
                    card.appendChild(v);
                    var radio = el("input", {
                        type: "radio",
                        name: "sel-" + k,
                        value: String(i + 1),
                        onchange: function () { selectBeat(k, i + 1); }
                    });
                    if (b.selected_option === i + 1) radio.checked = true;
                    card.appendChild(radio);
                });
                var redo = el("button", {
                    "class": "mn-secondary",
                    style: "margin-left:8px;",
                    onclick: function () { redoBeat(k); }
                }, ["Re-Do"]);
                card.appendChild(redo);
                if (b.selected_option == null) allSelected = false;
            } else if (b.status === "failed") {
                card.appendChild(el("span", null, [" — failed: " + (b.error || "unknown")]));
                allSelected = false;
            } else {
                allSelected = false;
            }
            list.appendChild(card);
        });
        document.getElementById("mn-export-btn").disabled = !allSelected;
    }

    function flushQueued() {
        videoPlaying = false;
        if (queuedUpdate) { renderStatus(queuedUpdate); queuedUpdate = null; }
    }

    // ---------- select / redo / export ----------
    function selectBeat(beat, option) {
        api("/api/select", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ beat: beat, selected_option: option })
        }).then(pollStatus);
    }
    function redoBeat(beat) {
        setStatus("Re-generating " + beat + "...");
        api("/api/animate/redo", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ beat: beat, options_per_beat: 3 })
        }).then(pollStatus);
    }
    function exportSelections() {
        fetch(SERVER + "/api/export", { method: "POST" })
            .then(function (r) { return r.blob(); })
            .then(function (blob) {
                var url = URL.createObjectURL(blob);
                var a = document.createElement("a");
                a.href = url; a.download = "animation_selections.json"; a.click();
                URL.revokeObjectURL(url);
                setStatus("Exported to Downloads folder.");
            });
    }

    // ---------- boot ----------
    function boot() {
        mount();
        pollHealth();
        healthTimer = setInterval(pollHealth, 30000);
        // hydrate from existing state (in case we resumed mid-run)
        api("/api/animate/status").then(renderStatus).catch(function () {});
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
""".replace("__SERVER__", server_literal).replace("__EVENT_ID__", event_id_literal)


# ---------------------------------------------------------------------------
# Injection
# ---------------------------------------------------------------------------

def inject_overlay(html: str, event_id: str) -> str:
    if INJECT_MARKER_START in html:
        raise ValueError(
            "Input HTML already contains the production overlay marker. "
            "Re-run the storyboard builder to get a clean source first."
        )

    css_block = f"<style>\n{OVERLAY_CSS}\n</style>"
    js_block = f"<script>\n{_build_overlay_js(event_id)}\n</script>"
    injection = f"\n{INJECT_MARKER_START}\n{css_block}\n{js_block}\n{INJECT_MARKER_END}\n"

    # Insert right before </body>; fall back to end of file.
    if "</body>" in html:
        return html.replace("</body>", injection + "</body>", 1)
    return html + injection


def validate_output(original: str, output: str, event_id: str) -> dict:
    """Run the 6 BLOCKING validation checks. Returns manifest dict on success;
    raises ValueError on any failure."""
    report: dict = {"checks": {}}

    # 1. Beat count + 6. beat data character-identical
    orig_data = extract_storyboard_data(original)
    out_data = extract_storyboard_data(output)
    if len(orig_data.get("lines", [])) != len(out_data.get("lines", [])):
        raise ValueError("Beat count changed during injection")
    if json.dumps(orig_data, sort_keys=True) != json.dumps(out_data, sort_keys=True):
        raise ValueError("Beat array content changed during injection")
    report["checks"]["beat_count_ok"] = True
    report["checks"]["beat_data_identical"] = True

    # 2. Beat integrity
    for beat in out_data.get("lines", []):
        if "speaker" not in beat or "text" not in beat:
            raise ValueError(f"Beat missing required field: {beat}")
    report["checks"]["beat_integrity_ok"] = True

    # 3. Image MD5 byte-identity
    orig_hashes = image_hashes(orig_data)
    out_hashes = image_hashes(out_data)
    if orig_hashes != out_hashes:
        raise ValueError("Embedded image MD5 drifted — bytes changed during injection")
    report["checks"]["image_md5_ok"] = True
    report["image_count"] = len(orig_hashes)

    # 4. No API keys in output (ENTIRE file — keys must never leak)
    for frag in BANNED_KEY_FRAGMENTS:
        if frag in output:
            raise ValueError("API key fragment found in output HTML — ABORT")
    report["checks"]["no_api_keys"] = True

    # 5. Localhost only — check inside the injected block for external URLs
    start = output.find(INJECT_MARKER_START)
    end = output.find(INJECT_MARKER_END)
    if start < 0 or end < 0:
        raise ValueError("Injection markers missing from output")
    injected = output[start:end]
    for host in BANNED_EXTERNAL_HOSTS:
        if host in injected:
            raise ValueError(f"External host '{host}' found in injected block")
    # Every fetch() in injected block must reference SERVER (localhost) or /api
    for m in re.finditer(r"fetch\s*\(\s*([^,)]+)", injected):
        arg = m.group(1)
        if "SERVER" not in arg and '"/api' not in arg and "'/api" not in arg:
            # Allow template SERVER+"/api/..."
            if "localhost:5111" not in arg:
                raise ValueError(f"Non-localhost fetch in injected JS: {arg}")
    report["checks"]["localhost_only"] = True

    # Rule 7 sentinel — non-script/style tag count must not change
    orig_tagcount = count_tags_outside_script_style(original)
    out_tagcount = count_tags_outside_script_style(output)
    if orig_tagcount != out_tagcount:
        raise ValueError(
            f"Raw HTML elements were added (tag count {orig_tagcount} -> {out_tagcount}). "
            "Rule 7 violation — only <script>/<style> may be injected."
        )
    report["checks"]["no_raw_html_added"] = True

    report["event_id"] = event_id
    report["beat_count"] = len(orig_data.get("lines", []))
    return report


def write_manifest(manifest_path: Path, manifest: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

SAMPLE_HTML_TEMPLATE = """<!doctype html>
<html><head><title>sample</title></head>
<body>
<div id="stage"></div>
<script>
window.storyboardData = %s;
</script>
</body></html>
"""


def run_smoke_test() -> int:
    """Self-contained smoke test. No disk writes outside /tmp.

    Builds a tiny in-memory storyboard, injects, validates, and reports.
    Returns 0 on success, non-zero on failure.
    """
    print("[smoke] building synthetic storyboard...")
    # 1x1 transparent PNG, base64 — short enough to be safe, real enough to hash
    tiny_png = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4"
        "nGNgAAIAAAUAAen63NgAAAAASUVORK5CYII="
    )
    data = {
        "module": "SMOKE",
        "event": 0,
        "lines": [
            {
                "line_number": 1,
                "speaker": "Guide Bird",
                "text": "{childName}, this is a smoke test.",
                "image": tiny_png,
                "audio_key": "smoke_001",
                "section": "Setup",
                "pause_ms": 500,
            },
            {
                "line_number": 2,
                "speaker": "Tessa",
                "text": "Hello world.",
                "image": tiny_png,
                "audio_key": "smoke_002",
                "section": "Discovery",
                "pause_ms": 500,
            },
        ],
    }
    html = SAMPLE_HTML_TEMPLATE % json.dumps(data)

    print("[smoke] injecting overlay...")
    out = inject_overlay(html, event_id="SMOKE_Event_0")

    print("[smoke] validating...")
    report = validate_output(html, out, event_id="SMOKE_Event_0")

    # Double-check marker presence + that injected block is before </body>
    assert INJECT_MARKER_START in out
    assert INJECT_MARKER_END in out
    assert out.index(INJECT_MARKER_END) < out.index("</body>")

    # Must contain the overlay mount function
    assert "mn-prod-overlay" in out, "overlay id missing from output"
    assert "localhost:5111" in out, "server origin missing from injected JS"

    print("[smoke] PASS — all checks green")
    print(json.dumps(report, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Inject production overlay into a storyboard HTML.")
    ap.add_argument("--input", help="Path to source storyboard HTML")
    ap.add_argument("--output", help="Path to write _prod.html")
    ap.add_argument("--event-id", help='Event identifier, e.g. "Event_1"')
    ap.add_argument("--smoke-test", action="store_true", help="Run self-test and exit")
    args = ap.parse_args()

    if args.smoke_test:
        return run_smoke_test()

    if not (args.input and args.output and args.event_id):
        ap.error("--input, --output, and --event-id are required (or use --smoke-test)")

    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.is_file():
        print(f"ERROR: input not found: {in_path}", file=sys.stderr)
        return 2

    html = in_path.read_text(encoding="utf-8")
    out_html = inject_overlay(html, event_id=args.event_id)
    report = validate_output(html, out_html, event_id=args.event_id)

    out_path.write_text(out_html, encoding="utf-8")
    print(f"wrote {out_path} ({len(out_html)} bytes)")

    # manifest
    project_root = Path(__file__).resolve().parents[2]
    manifest_path = project_root / "Production" / ".auto-memory" / "production_overlay_manifest.json"
    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_file": str(in_path),
        "output_file": str(out_path),
        "event_id": args.event_id,
        "beat_count": report["beat_count"],
        "image_validation": {
            "total_images": report["image_count"],
            "all_hashes_match": report["checks"]["image_md5_ok"],
        },
        "security_validation": {
            "api_keys_found": 0,
            "all_fetches_localhost": report["checks"]["localhost_only"],
            "no_raw_html_added": report["checks"]["no_raw_html_added"],
        },
        "status": "PASSED — all checks green",
    }
    write_manifest(manifest_path, manifest)
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
