#!/usr/bin/env python3
"""
Path B patch: Add "Send to Storyboard" buttons to the cropper tool.

Each crop gets a button that POSTs the crop's data URI directly to the
production server's /api/inject-image endpoint. The image appears in the
storyboard's Available Images library immediately on reload.

This is the cropper → storyboard pipeline bridge.
"""
import re
import sys
from pathlib import Path


def patch(html_path: Path, output_path: Path):
    html = html_path.read_text(encoding="utf-8")

    # Snapshot base64 images for safety
    old_b64 = re.findall(r'data:image/[^"]{100,}', html)

    # ─── 1. Add the sendToStoryboard() function before the closing </script> ───
    SEND_FUNC = r'''
// ─── SEND TO STORYBOARD ─────────────────────────────────────────────────
var STORYBOARD_SERVER = "http://localhost:5111";

function sendToStoryboard(masterId, idx) {
  var c = allCrops[masterId][idx];
  if (!c || !c.dataUrl) { alert("No crop data to send."); return; }

  var key = c.name.replace(/\s+/g, "_").replace(/\.png$/i, "");
  var statusEl = document.getElementById("headerStatus");
  statusEl.textContent = "\u23F3 Sending " + c.name + " to storyboard...";
  statusEl.style.color = "#ffa";

  // Generate a small thumbnail (80px) using a temp canvas
  var thumbUri = c.dataUrl; // fallback
  try {
    var img = new Image();
    img.src = c.dataUrl;
    var thumbCanvas = document.createElement("canvas");
    var ratio = 80 / Math.min(img.naturalWidth || c.w, img.naturalHeight || c.h);
    thumbCanvas.width = Math.round((img.naturalWidth || c.w) * ratio);
    thumbCanvas.height = Math.round((img.naturalHeight || c.h) * ratio);
    var tctx = thumbCanvas.getContext("2d");
    tctx.drawImage(img, 0, 0, thumbCanvas.width, thumbCanvas.height);
    thumbUri = thumbCanvas.toDataURL("image/png");
  } catch(e) { /* use full image as thumb fallback */ }

  fetch(STORYBOARD_SERVER + "/api/inject-image", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: key,
      data: c.dataUrl,
      thumbnail: thumbUri
    })
  }).then(function(resp) { return resp.json(); }).then(function(data) {
    if (data.error) {
      statusEl.textContent = "\u274C Error: " + data.error;
      statusEl.style.color = "#f88";
      return;
    }
    statusEl.textContent = "\u2705 " + c.name + " added to storyboard library! Reload storyboard to see it.";
    statusEl.style.color = "#8f8";
  }).catch(function(err) {
    statusEl.textContent = "\u274C Server error: " + err.message + " — is the production server running?";
    statusEl.style.color = "#f88";
  });
}

function sendAllToStoryboard() {
  var queue = [];
  for (var mid in allCrops) {
    allCrops[mid].forEach(function(c, i) {
      if (c.dataUrl) queue.push({ mid: mid, idx: i });
    });
  }
  if (queue.length === 0) { alert("No crops to send."); return; }
  if (!confirm("Send " + queue.length + " crop(s) to the storyboard library?")) return;

  var sent = 0;
  function sendNext() {
    if (sent >= queue.length) {
      document.getElementById("headerStatus").textContent = "\u2705 All " + queue.length + " crops sent to storyboard!";
      document.getElementById("headerStatus").style.color = "#8f8";
      return;
    }
    var item = queue[sent];
    sendToStoryboard(item.mid, item.idx);
    sent++;
    setTimeout(sendNext, 500); // small delay between sends
  }
  sendNext();
}
'''

    # Find the last </script> tag and insert before it
    last_script_close = html.rfind("</script>")
    if last_script_close < 0:
        print("ERROR: No </script> found")
        sys.exit(1)

    html = html[:last_script_close] + SEND_FUNC + "\n" + html[last_script_close:]
    print("Inserted sendToStoryboard() function")

    # ─── 2. Add "Send to Storyboard" button next to each "Save PNG" button ───
    old_save_btn = '''html += '<button onclick="event.stopPropagation(); saveSingle(\\'' + master.id + '\\',' + i + ')">Save PNG</button>';'''
    new_save_btn = '''html += '<button onclick="event.stopPropagation(); saveSingle(\\'' + master.id + '\\',' + i + ')">Save PNG</button>';
      html += '<button onclick="event.stopPropagation(); sendToStoryboard(\\'' + master.id + '\\',' + i + ')" style="background:#2a6; color:white; border:none; padding:2px 6px; border-radius:3px; cursor:pointer; font-size:10px;">\\u27A1 Storyboard</button>';'''

    if old_save_btn not in html:
        print("WARNING: Could not find Save PNG button pattern — trying alternate")
        # Try a simpler match
        old_save_btn = "saveSingle(\\'"
        if old_save_btn not in html:
            print("ERROR: Cannot find Save PNG button in crop list renderer")
            sys.exit(1)

    html = html.replace(old_save_btn, new_save_btn, 1)
    print("Added per-crop 'Storyboard' button")

    # ─── 3. Add "Send All to Storyboard" button next to "Save All Crops" ───
    old_saveall = '<button id="btnSaveAll" class="primary" disabled>Save All Crops</button>'
    new_saveall = old_saveall + '\n  <button id="btnSendAllSB" class="primary" disabled onclick="sendAllToStoryboard()" style="background:#2a6;">&#10145; Send All to Storyboard</button>'
    html = html.replace(old_saveall, new_saveall, 1)
    print("Added 'Send All to Storyboard' button in header")

    # Enable the Send All button when Save All gets enabled
    # Find where btnSaveAll.disabled = false and add btnSendAllSB too
    html = html.replace(
        "document.getElementById('btnSaveAll').disabled = false",
        "document.getElementById('btnSaveAll').disabled = false; document.getElementById('btnSendAllSB').disabled = false",
    )
    html = html.replace(
        "document.getElementById('btnSaveAll').disabled = true",
        "document.getElementById('btnSaveAll').disabled = true; document.getElementById('btnSendAllSB').disabled = true",
    )
    print("Wired Send All button enable/disable")

    # ─── 4. Verify base64 images preserved ───
    new_b64 = re.findall(r'data:image/[^"]{100,}', html)
    if len(old_b64) != len(new_b64):
        print(f"WARNING: base64 count changed ({len(old_b64)} → {len(new_b64)})")
    for i, (a, b) in enumerate(zip(old_b64, new_b64)):
        if a != b:
            print(f"CRITICAL: base64 image {i} corrupted. Aborting.")
            sys.exit(1)
    print(f"Verified: {len(old_b64)} base64 images preserved byte-identical")

    output_path.write_text(html, encoding="utf-8")
    diff = len(html) - html_path.read_text(encoding="utf-8").__len__()
    print(f"Patched: {html_path.name} → {output_path.name} ({diff:+d} chars)")


if __name__ == "__main__":
    event_dir = Path(__file__).parent.parent / "Event_1"
    src = event_dir / "image_selector_cropper_m1e1_v1.html"
    dst = event_dir / "image_selector_cropper_m1e1_v2.html"
    if len(sys.argv) > 1:
        src = Path(sys.argv[1])
    if len(sys.argv) > 2:
        dst = Path(sys.argv[2])
    patch(src, dst)
