#!/usr/bin/env python3
"""
MindfulNest TTS Audition Workstation Builder (v3)
==================================================
Generates a self-contained HTML TTS audition interface for line-by-line dialogue review.
Upgraded from v1 review tool — now includes in-browser ElevenLabs regeneration,
Save to Disk per line, and Approve/Redo verdicts with export.

After TTS lines are batch-rendered, this tool lets Kim:
1. Listen to each line's TTS audio (click-to-play)
2. See and EDIT the text sent to ElevenLabs (emotional tags + [pause] markers)
3. REGENERATE any line in-browser via ElevenLabs API (same locked voice settings)
4. SAVE TO DISK — download regenerated audio as MP3 (prevents data loss on tab close)
5. Mark each line as Approved or Redo
6. Export verdicts to clipboard for Directus logging
7. Save All Approved — batch-downloads all approved lines

USAGE:
    python3 build_tts_review.py --config tts_config.json --output audition_player.html

    # WITH auto-registration to Directus (NEW):
    python3 build_tts_review.py --config tts_config.json --output audition_player.html \
      --module-id 1 --event-number 1 --build-mode config

    # OR with --registry flag to pull config from Directus (future):
    python3 build_tts_review.py --registry --module M1 --event 1 --output audition_player.html

CONFIG FORMAT (JSON):
{
  "title": "Event 1: Tessa's Fall — Story Scene TTS",
  "event_id": "m1_event_1",
  "api_key": "YOUR_ELEVENLABS_API_KEY",
  "model": "eleven_v3",
  "voice_settings": {"stability": 0.30, "similarity_boost": 0.80, "style": 0.30},
  "lines": [
    {
      "id": "line_02",
      "speaker": "Guide Bird",
      "voice_id": "7o9pyvsN0ob5GO6LBQp6",
      "text": "[sympathetic] Hello.... Are you OK...?",
      "audio_path": "/path/to/line_02_guide_bird.mp3",
      "filename": "line_02_guide_bird.mp3",
      "personalized": false
    }
  ]
}

FIELDS:
  api_key         — ElevenLabs API key (embedded in HTML for browser-side regen)
  model           — ElevenLabs model ID (default: eleven_v3)
  voice_settings  — stability, similarity_boost, style (locked per VOICE_ROSTER)
  voice_id        — per-line ElevenLabs voice ID (enables regeneration)
  filename        — output filename for Save to Disk (e.g., line_02_guide_bird.mp3)
  personalized    — true if line contains {childName} etc. (shows DEMO badge)

HISTORY:
  v1 (April 12, 2026) — Basic review: play, edit text, approve/regen cycle, export
  v2 (April 13, 2026) — Added ElevenLabs regeneration + base64 embedding
  v3 (April 13, 2026) — Added Save to Disk, Save All Approved, pulse reminder,
                          generic config format, voice_id per line, filename for download
  v4 (April 14, 2026) — Added post-build auto-registration: registers HTML to prod_visual_assets,
                          updates prod_modules tracking fields, logs to prod_activity_log
"""

import argparse
import base64
import json
import os
import sys
import time
import requests
from datetime import datetime
from pathlib import Path


def encode_audio(path):
    """Encode an audio file as base64."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def build_tts_review(config, output_path):
    """
    Build a self-contained HTML TTS audition workstation from a config dict.

    Args:
        config: dict with keys: title, event_id, api_key, model, voice_settings, lines
        output_path: where to write the HTML file
    """
    title = config.get("title", "TTS Audition Workstation")
    event_id = config.get("event_id", "event_unknown")
    api_key = config.get("api_key", "")
    model = config.get("model", "eleven_v3")
    voice_settings = config.get("voice_settings", {"stability": 0.30, "similarity_boost": 0.80, "style": 0.30})
    build_time = time.strftime("%B %d, %Y %I:%M %p")

    # Encode audio files
    audio_data = {}
    line_meta = []
    for line in config.get("lines", []):
        line_id = line.get("id", "unknown")
        audio_path = line.get("audio_path")
        if audio_path and os.path.exists(audio_path):
            audio_data[line_id] = encode_audio(audio_path)
            size_kb = round(os.path.getsize(audio_path) / 1024, 1)
            print(f"  Embedded {line_id}: {os.path.basename(audio_path)} ({size_kb} KB)")
        else:
            size_kb = 0
            if audio_path:
                print(f"  WARNING: Audio not found: {audio_path}")

        line_meta.append({
            "id": line_id,
            "speaker": line.get("speaker", "Unknown"),
            "voice_id": line.get("voice_id", ""),
            "text": line.get("text", ""),
            "filename": line.get("filename", f"{line_id}.mp3"),
            "personalized": line.get("personalized", False),
            "size_kb": size_kb,
        })

    # Build HTML
    # Generate line cards
    cards_html = ""
    for meta in line_meta:
        lid = meta["id"]
        color = "#4ecca3" if "guide" in meta["speaker"].lower() else "#e9a645"
        demo_tag = ' <span style="color:#e9a645;font-size:0.7em">[DEMO]</span>' if meta["personalized"] else ""

        cards_html += f"""
<div class="line-card" id="card-{lid}">
  <div class="top-row">
    <button class="play-btn idle" id="pbtn-{lid}" onclick="togglePlay('{lid}')">&#9654;</button>
    <div class="line-info">
      <span class="line-num">{lid}</span>
      <span class="speaker" style="color:{color}">{meta['speaker']}{demo_tag}</span>
      <span class="file-size">{meta['size_kb']} KB</span>
    </div>
    <div class="status-area">
      <span class="status-dot original" id="dot-{lid}"></span>
      <span class="status-label" id="slabel-{lid}">original</span>
    </div>
  </div>
  <audio id="aud-{lid}" preload="auto"></audio>
  <textarea id="txt-{lid}" class="line-text" data-voice="{meta['voice_id']}" rows="2">{meta['text']}</textarea>
  <div class="btn-row">
    <button class="regen-btn" id="regen-{lid}" onclick="regenerate('{lid}')">&#x1F504; Regenerate</button>
    <button class="save-btn" id="save-{lid}" onclick="saveToDisk('{lid}')">&#x1F4BE; Save to Disk</button>
    <div class="verdict-area" id="varea-{lid}">
      <button class="verdict-btn approve" onclick="setVerdict('{lid}','approved',this)">&#x2705; Approve</button>
      <button class="verdict-btn redo" onclick="setVerdict('{lid}','redo',this)">&#x1F504; Redo</button>
    </div>
    <span class="regen-count" id="rc-{lid}"></span>
    <span class="save-status" id="ss-{lid}"></span>
  </div>
</div>"""

    # Audio data JS
    audio_js_lines = []
    for lid, b64 in audio_data.items():
        audio_js_lines.append(f'AUDIO_DATA["{lid}"] = "data:audio/mpeg;base64,{b64}";')
    audio_js = "\n".join(audio_js_lines)

    # Filenames map for Save to Disk
    filenames_js = json.dumps({m["id"]: m["filename"] for m in line_meta})
    line_ids_js = json.dumps([m["id"] for m in line_meta])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:20px;max-width:960px;margin:0 auto}}
h1{{text-align:center;color:#4ecca3;margin-bottom:4px;font-size:1.5em}}
.subtitle{{text-align:center;color:#888;margin-bottom:6px;font-size:0.85em}}
.version-badge{{text-align:center;color:#e9a645;margin-bottom:20px;font-size:0.75em}}
.line-card{{background:#16213e;border-radius:12px;padding:16px 20px;margin-bottom:14px;border:1px solid #0f3460;transition:border-color 0.2s}}
.line-card:hover{{border-color:#4ecca3}}
.line-card.playing{{border-color:#4ecca3;box-shadow:0 0 12px rgba(78,204,163,0.25)}}
.line-card.regenerating{{border-color:#e9a645;box-shadow:0 0 12px rgba(233,166,69,0.25)}}
.top-row{{display:flex;align-items:center;gap:12px;margin-bottom:10px}}
.play-btn{{width:44px;height:44px;border-radius:50%;border:none;cursor:pointer;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:18px;transition:all 0.15s}}
.play-btn.idle{{background:#4ecca3;color:#1a1a2e}}
.play-btn.active{{background:#e94560;color:#fff}}
.line-info{{flex:1;display:flex;gap:10px;align-items:baseline}}
.line-num{{font-weight:700;font-size:0.95em}}
.speaker{{font-size:0.85em;font-weight:600}}
.file-size{{font-size:0.7em;color:#666}}
.status-area{{display:flex;align-items:center;gap:6px}}
.status-dot{{width:10px;height:10px;border-radius:50%;display:inline-block}}
.status-dot.original{{background:#4ecca3}}
.status-dot.regenerated{{background:#e9a645}}
.status-dot.saved{{background:#2ecc71}}
.status-label{{font-size:0.7em;color:#888}}
.line-text{{width:100%;background:#0f3460;color:#e0e0e0;border:1px solid #1a1a4e;border-radius:8px;padding:10px;font-family:inherit;font-size:0.85em;resize:vertical;margin-bottom:10px}}
.btn-row{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
.regen-btn{{background:#533483;color:#fff;border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:0.8em;transition:all 0.15s}}
.regen-btn:hover{{background:#6c44a2}}
.regen-btn.loading{{opacity:0.5;cursor:wait}}
.save-btn{{background:#1a6b3c;color:#fff;border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:0.8em;transition:all 0.15s}}
.save-btn:hover{{background:#22874c}}
.save-btn.pulse{{animation:pulse-save 1s ease-in-out infinite}}
@keyframes pulse-save{{0%,100%{{box-shadow:0 0 0 0 rgba(46,204,113,0.4)}}50%{{box-shadow:0 0 12px 4px rgba(46,204,113,0.4)}}}}
.save-btn.saved{{background:#2ecc71;color:#1a1a2e}}
.verdict-btn{{padding:6px 12px;border:none;border-radius:6px;cursor:pointer;font-size:0.8em;transition:all 0.15s}}
.verdict-btn.approve{{background:#0a3d2a;color:#4ecca3}}
.verdict-btn.approve:hover,.verdict-btn.approve.selected{{background:#4ecca3;color:#1a1a2e}}
.verdict-btn.redo{{background:#3d1a0a;color:#e94560}}
.verdict-btn.redo:hover,.verdict-btn.redo.selected{{background:#e94560;color:#fff}}
.regen-count{{font-size:0.7em;color:#888}}
.save-status{{font-size:0.7em;color:#2ecc71}}
.footer{{text-align:center;margin-top:20px}}
.export-btn{{background:#4ecca3;color:#1a1a2e;border:none;padding:10px 24px;border-radius:8px;cursor:pointer;font-size:0.9em;font-weight:600;margin:4px}}
.export-btn:hover{{background:#6ee6bb}}
.toast{{position:fixed;bottom:20px;right:20px;background:#4ecca3;color:#1a1a2e;padding:12px 20px;border-radius:8px;font-weight:600;opacity:0;transition:opacity 0.3s;z-index:999;pointer-events:none}}
.toast.show{{opacity:1}}
</style>
</head>
<body>
<h1>TTS Audition Workstation</h1>
<div class="subtitle">{title} | {len(line_meta)} Lines | ElevenLabs {model}</div>
<div class="version-badge">v3 — Save to Disk enabled | Built {build_time}</div>

{cards_html}

<div class="footer">
  <button class="export-btn" onclick="exportVerdicts()">&#x1F4CB; Export Verdicts</button>
  <button class="export-btn" onclick="saveAllApproved()" style="background:#2ecc71">&#x1F4E6; Save All Approved to Disk</button>
</div>
<div class="toast" id="toast"></div>

<script>
// === CONFIG (injected by builder) ===
var API_KEY = '{api_key}';
var MODEL = '{model}';
var SETTINGS = {json.dumps(voice_settings)};
var FILENAMES = {filenames_js};
var LINE_IDS = {line_ids_js};
var AUDIO_DATA = {{}};
{audio_js}

// === STATE ===
var currentPlaying = null;
var verdicts = {{}};
var regenCounts = {{}};
var unsavedRegens = {{}};

// Initialize audio elements from embedded data
document.addEventListener('DOMContentLoaded', function() {{
  for (var lid in AUDIO_DATA) {{
    var aud = document.getElementById("aud-" + lid);
    if (aud) aud.src = AUDIO_DATA[lid];
  }}
}});

function showToast(msg) {{
  var t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("show");
  setTimeout(function(){{ t.classList.remove("show"); }}, 3000);
}}

function togglePlay(lid) {{
  var a = document.getElementById("aud-" + lid);
  var b = document.getElementById("pbtn-" + lid);
  var c = document.getElementById("card-" + lid);
  if (currentPlaying && currentPlaying !== lid) {{
    var pa = document.getElementById("aud-" + currentPlaying);
    var pb = document.getElementById("pbtn-" + currentPlaying);
    var pc = document.getElementById("card-" + currentPlaying);
    pa.pause(); pa.currentTime = 0;
    pb.innerHTML = "&#9654;"; pb.className = "play-btn idle";
    pc.classList.remove("playing");
  }}
  if (a.paused) {{
    a.play(); b.innerHTML = "&#9724;"; b.className = "play-btn active"; c.classList.add("playing"); currentPlaying = lid;
  }} else {{
    a.pause(); a.currentTime = 0; b.innerHTML = "&#9654;"; b.className = "play-btn idle"; c.classList.remove("playing"); currentPlaying = null;
  }}
  a.onended = function() {{ b.innerHTML = "&#9654;"; b.className = "play-btn idle"; c.classList.remove("playing"); currentPlaying = null; }};
}}

async function regenerate(lid) {{
  var txt = document.getElementById("txt-" + lid).value;
  var voiceId = document.getElementById("txt-" + lid).getAttribute("data-voice");
  var btn = document.getElementById("regen-" + lid);
  var card = document.getElementById("card-" + lid);

  if (!API_KEY) {{ alert("No ElevenLabs API key configured. Add api_key to config JSON."); return; }}
  if (!voiceId) {{ alert("No voice_id for this line. Add voice_id to config JSON."); return; }}

  btn.classList.add("loading"); btn.disabled = true;
  card.classList.add("regenerating");

  try {{
    var resp = await fetch("https://api.elevenlabs.io/v1/text-to-speech/" + voiceId, {{
      method: "POST",
      headers: {{"xi-api-key": API_KEY, "Content-Type": "application/json"}},
      body: JSON.stringify({{text: txt, model_id: MODEL, voice_settings: SETTINGS}})
    }});
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    var blob = await resp.blob();
    var url = URL.createObjectURL(blob);
    var aud = document.getElementById("aud-" + lid);
    aud.src = url;
    aud._blob = blob;

    var dot = document.getElementById("dot-" + lid);
    var sl = document.getElementById("slabel-" + lid);
    dot.className = "status-dot regenerated";
    regenCounts[lid] = (regenCounts[lid] || 0) + 1;
    sl.textContent = "regen #" + regenCounts[lid] + " (unsaved)";
    document.getElementById("rc-" + lid).textContent = regenCounts[lid] + " regeneration" + (regenCounts[lid] > 1 ? "s" : "");

    unsavedRegens[lid] = true;
    var saveBtn = document.getElementById("save-" + lid);
    saveBtn.classList.add("pulse");
    saveBtn.classList.remove("saved");
    document.getElementById("ss-" + lid).textContent = "";

    setTimeout(function() {{ togglePlay(lid); }}, 200);
    showToast("Line " + lid + " regenerated — click Save to Disk to persist!");
  }} catch(e) {{
    alert("Regeneration failed for " + lid + ": " + e.message + "\\n\\nIf CORS error: serve via localhost (python3 -m http.server 8765)");
  }} finally {{
    btn.classList.remove("loading"); btn.disabled = false;
    card.classList.remove("regenerating");
  }}
}}

function saveToDisk(lid) {{
  var aud = document.getElementById("aud-" + lid);
  var src = aud.src;
  var filename = FILENAMES[lid] || (lid + ".mp3");

  if (aud._blob) {{
    var url = URL.createObjectURL(aud._blob);
    triggerDownload(url, filename, lid);
  }} else if (src && src.startsWith("data:audio")) {{
    fetch(src).then(function(r) {{ return r.blob(); }}).then(function(blob) {{
      aud._blob = blob;
      var url = URL.createObjectURL(blob);
      triggerDownload(url, filename, lid);
    }});
  }} else if (src && src.startsWith("blob:")) {{
    fetch(src).then(function(r) {{ return r.blob(); }}).then(function(blob) {{
      var url = URL.createObjectURL(blob);
      triggerDownload(url, filename, lid);
    }});
  }} else {{
    alert("No audio data available for " + lid);
  }}
}}

function triggerDownload(url, filename, lid) {{
  var a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);

  unsavedRegens[lid] = false;
  var saveBtn = document.getElementById("save-" + lid);
  saveBtn.classList.remove("pulse"); saveBtn.classList.add("saved");
  var dot = document.getElementById("dot-" + lid);
  var sl = document.getElementById("slabel-" + lid);
  if (regenCounts[lid]) {{
    sl.textContent = "regen #" + regenCounts[lid] + " (saved)";
    dot.className = "status-dot saved";
  }}
  document.getElementById("ss-" + lid).textContent = "saved \\u2713";
  showToast(filename + " saved to disk!");
}}

async function saveAllApproved() {{
  var approvedLines = [];
  for (var k in verdicts) {{ if (verdicts[k] === "approved") approvedLines.push(k); }}
  if (approvedLines.length === 0) {{ alert("No lines approved yet."); return; }}
  for (var i = 0; i < approvedLines.length; i++) {{
    saveToDisk(approvedLines[i]);
    await new Promise(function(r) {{ setTimeout(r, 300); }});
  }}
  showToast(approvedLines.length + " approved files saved!");
}}

function setVerdict(lid, v, el) {{
  verdicts[lid] = v;
  var row = el.parentElement;
  row.querySelectorAll(".verdict-btn").forEach(function(b) {{ b.classList.remove("selected"); }});
  el.classList.add("selected");
}}

function exportVerdicts() {{
  var report = "=== TTS AUDITION VERDICTS ===\\n" + "{title}\\nExported: " + new Date().toISOString() + "\\n\\n";
  LINE_IDS.forEach(function(lid) {{
    var v = verdicts[lid] || "pending";
    var txt = document.getElementById("txt-" + lid).value.substring(0, 80);
    var rc = regenCounts[lid] || 0;
    var saved = unsavedRegens[lid] ? "UNSAVED" : (rc > 0 ? "saved" : "original");
    report += lid + ": " + v.toUpperCase() + " | regens:" + rc + " | " + saved + " | " + txt + "...\\n";
  }});
  navigator.clipboard.writeText(report);
  showToast("Verdicts copied to clipboard!");
}}
</script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)

    file_size = os.path.getsize(output_path)
    print(f"\nTTS Audition Workstation written: {output_path}")
    print(f"  Size: {file_size // 1024} KB | Lines: {len(line_meta)} | Model: {model}")
    print(f"  Features: Play, Edit, Regenerate, Save to Disk, Approve/Redo, Export Verdicts")
    return output_path


def register_build_in_directus(output_path, module_id, event_number, line_count, build_mode="config"):
    """
    Post-build auto-registration function: registers the TTS audition HTML in Directus.

    Args:
        output_path: str — Path to the built HTML file
        module_id: int — Module ID (e.g., 1 for M1)
        event_number: int — Event number (e.g., 1 for Event 1)
        line_count: int — Number of lines in the audition
        build_mode: str — "config" or "registry" (default: "config")

    Returns:
        dict — Result with keys: success, asset_id, module_updated, activity_logged, errors
    """
    result = {
        "success": False,
        "asset_id": None,
        "module_updated": False,
        "activity_logged": False,
        "errors": []
    }

    try:
        # Step 1: Read Directus credentials from API_KEYS_MASTER.md
        script_dir = os.path.dirname(os.path.abspath(__file__))
        api_keys_path = os.path.join(script_dir, "..", "API_KEYS_MASTER.md")

        if not os.path.exists(api_keys_path):
            result["errors"].append(f"API_KEYS_MASTER.md not found at {api_keys_path}")
            return result

        # Extract Directus credentials from API_KEYS_MASTER.md
        with open(api_keys_path) as f:
            keys_content = f.read()

        # Parse credentials (simple regex extraction)
        import re
        email_match = re.search(r"Admin Email\s*\|\s*`?([^`|]+)`?", keys_content)
        password_match = re.search(r"Admin Password\s*\|\s*`?([^`|]+)`?", keys_content)
        url_match = re.search(r"URL:\s*(https://[^\s]+)", keys_content)

        if not (email_match and password_match and url_match):
            result["errors"].append("Could not extract Directus credentials from API_KEYS_MASTER.md")
            return result

        email = email_match.group(1).strip()
        password = password_match.group(1).strip()
        directus_url = url_match.group(1).strip()

        print(f"[Directus] Authenticating as {email}...")

        # Step 2: Authenticate with Directus
        auth_response = requests.post(
            f"{directus_url}/auth/login",
            json={"email": email, "password": password},
            timeout=10
        )

        if auth_response.status_code != 200:
            result["errors"].append(f"Directus auth failed: {auth_response.status_code} {auth_response.text}")
            return result

        token = auth_response.json().get("data", {}).get("access_token")
        if not token:
            result["errors"].append("No access token in auth response")
            return result

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Step 3: Check if this TTS review HTML is already registered in prod_visual_assets
        filename = os.path.basename(output_path)

        print(f"[Directus] Checking for existing asset: {filename}")

        check_response = requests.get(
            f"{directus_url}/items/prod_visual_assets",
            params={"filter[filename][_eq]": filename},
            headers=headers,
            timeout=10
        )

        if check_response.status_code != 200:
            result["errors"].append(f"Asset check failed: {check_response.status_code}")
            return result

        existing_assets = check_response.json().get("data", [])

        # Step 4: POST (new) or PATCH (update) prod_visual_assets
        asset_payload = {
            "filename": filename,
            "filepath": f"Production/Event_{event_number}/tts_audition_player_v3.html",
            "shot_number": 1,  # TTS audition is a single-file tool, not a series
            "module_id": module_id,  # Must be integer, not string
            "asset_type": "tts_audition_tool",
            "status": "built",
            "notes": f"TTS audition workstation for {line_count} lines, built via build_tts_review.py"
        }

        if existing_assets:
            # PATCH existing
            asset_id = existing_assets[0]["id"]
            print(f"[Directus] Updating asset {asset_id}...")

            update_response = requests.patch(
                f"{directus_url}/items/prod_visual_assets/{asset_id}",
                json=asset_payload,
                headers=headers,
                timeout=10
            )

            if update_response.status_code not in (200, 204):
                result["errors"].append(f"Asset update failed: {update_response.status_code} {update_response.text}")
                return result

            result["asset_id"] = asset_id
        else:
            # POST new
            print(f"[Directus] Creating new asset: {filename}")

            create_response = requests.post(
                f"{directus_url}/items/prod_visual_assets",
                json=asset_payload,
                headers=headers,
                timeout=10
            )

            if create_response.status_code not in (200, 201):
                result["errors"].append(f"Asset creation failed: {create_response.status_code} {create_response.text}")
                return result

            result["asset_id"] = create_response.json().get("data", {}).get("id")

        # Step 5: Update prod_modules TTS audition tracking fields
        print(f"[Directus] Updating module {module_id} tracking fields...")

        current_iso_time = datetime.utcnow().isoformat() + "Z"

        module_payload = {
            "tts_audition_status": "built",
            "tts_audition_built_at": current_iso_time,
            "tts_audition_build_mode": build_mode
        }

        module_update_response = requests.patch(
            f"{directus_url}/items/prod_modules/{module_id}",
            json=module_payload,
            headers=headers,
            timeout=10
        )

        if module_update_response.status_code not in (200, 204):
            result["errors"].append(f"Module update failed: {module_update_response.status_code}")
            # Log error but don't fail entire operation
            print(f"  WARNING: Module update failed (non-blocking): {module_update_response.text}")
        else:
            result["module_updated"] = True

        # Step 6: Log to prod_activity_log with action="tts_audition_build"
        print(f"[Directus] Logging activity...")

        activity_payload = {
            "action": "tts_audition_build",
            "details": {
                "output_path": output_path,
                "module_id": module_id,
                "event_number": event_number,
                "line_count": line_count,
                "build_mode": build_mode,
                "asset_id": result["asset_id"],
                "filename": filename,
                "timestamp": current_iso_time
            }
        }

        activity_response = requests.post(
            f"{directus_url}/items/prod_activity_log",
            json=activity_payload,
            headers=headers,
            timeout=10
        )

        if activity_response.status_code not in (200, 201):
            result["errors"].append(f"Activity log failed: {activity_response.status_code}")
            # Log error but don't fail entire operation
            print(f"  WARNING: Activity log failed (non-blocking): {activity_response.text}")
        else:
            result["activity_logged"] = True

        result["success"] = True
        print(f"[Directus] ✓ TTS audition registered successfully")

    except Exception as e:
        result["errors"].append(f"Exception during registration: {str(e)}")
        print(f"[Directus] ERROR: {str(e)}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Build MindfulNest TTS Audition Workstation (v3)")
    parser.add_argument("--config", required=True, help="Path to JSON config file")
    parser.add_argument("--output", required=True, help="Output HTML path")
    parser.add_argument("--module-id", type=int, help="Module ID for Directus registration (e.g., 1 for M1)")
    parser.add_argument("--event-number", type=int, help="Event number for Directus registration")
    parser.add_argument("--build-mode", default="config", help="Build mode: 'config' or 'registry' (default: config)")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    output_path = build_tts_review(config, args.output)

    # Post-build auto-registration
    if args.module_id is not None and args.event_number is not None:
        line_count = len(config.get("lines", []))
        print(f"\n[Post-Build] Registering TTS audition in Directus...")
        reg_result = register_build_in_directus(
            output_path,
            args.module_id,
            args.event_number,
            line_count,
            build_mode=args.build_mode
        )

        if not reg_result["success"]:
            print(f"[Post-Build] WARNING: Registration failed (non-blocking)")
            for error in reg_result["errors"]:
                print(f"  - {error}")
        else:
            print(f"[Post-Build] ✓ Registered with asset_id: {reg_result['asset_id']}")
    else:
        print("\n[Post-Build] Skipping Directus registration (--module-id and --event-number required)")



if __name__ == "__main__":
    main()
