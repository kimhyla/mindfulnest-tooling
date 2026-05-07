#!/usr/bin/env python3
"""
Path B patch: Make drag-drop notify the server when an image is assigned to a beat.

Problem: When Kim drags a new image onto a beat line, the browser updates L[idx].i
and calls render(), but the server still has the OLD image cached. So "Generate B+C"
sends the wrong image to WaveSpeed.

Fix: After updating L[idx].i, POST to /api/assign-image with the beat ID and image key.
The server looks up the full-res gallery image and caches it for animation generation.

Also adds duplicate-guard to setupDropZones() to prevent stacking drop hints on re-render.
"""
import re
import sys
from pathlib import Path


def patch(html_path: Path, output_path: Path):
    html = html_path.read_text(encoding="utf-8")
    old_b64 = re.findall(r'data:image/[^"]{100,}', html)
    changes = 0

    # ─── 1. Add server notification to drag-drop handler ───
    old_drop = 'if(!isNaN(idx)&&idx>=0&&idx<L.length){L[idx].i=key;render();}'
    new_drop = '''if(!isNaN(idx)&&idx>=0&&idx<L.length){L[idx].i=key;render();
        fetch("http://localhost:5111/api/assign-image",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({beat:"beat_"+String(idx+1).padStart(2,"0"),image_key:key})}).catch(function(){});}'''

    if old_drop in html:
        html = html.replace(old_drop, new_drop, 1)
        print("  [1] Added /api/assign-image POST to drag-drop handler")
        changes += 1
    else:
        print("  [1] WARNING: drag-drop handler pattern not found")

    # ─── 2. Add duplicate guard to setupDropZones ───
    old_setup = 'function setupDropZones(){\n  var rows=document.querySelectorAll(".lr");\n  for(var i=0;i<rows.length;i++){\n    var hint=document.createElement("div");'
    new_setup = 'function setupDropZones(){\n  var rows=document.querySelectorAll(".lr");\n  for(var i=0;i<rows.length;i++){\n    if(rows[i].querySelector(".drop-hint"))continue;\n    var hint=document.createElement("div");'

    if old_setup in html:
        html = html.replace(old_setup, new_setup, 1)
        print("  [2] Added duplicate guard to setupDropZones")
        changes += 1
    else:
        print("  [2] WARNING: setupDropZones pattern not found — trying flexible match")
        # Try just the hint creation line
        if 'if(rows[i].querySelector(".drop-hint"))continue;' not in html:
            old_hint = '    var hint=document.createElement("div");\n    hint.className="drop-hint";'
            new_hint = '    if(rows[i].querySelector(".drop-hint"))continue;\n    var hint=document.createElement("div");\n    hint.className="drop-hint";'
            if old_hint in html:
                html = html.replace(old_hint, new_hint, 1)
                print("  [2b] Added duplicate guard (flexible match)")
                changes += 1

    if changes == 0:
        print("No changes needed")
        return

    # ─── 3. Verify base64 images preserved ───
    new_b64 = re.findall(r'data:image/[^"]{100,}', html)
    if len(old_b64) != len(new_b64):
        print(f"WARNING: base64 count changed ({len(old_b64)} → {len(new_b64)})")
    for i, (a, b) in enumerate(zip(old_b64, new_b64)):
        if a != b:
            print(f"CRITICAL: base64 image {i} corrupted. Aborting.")
            sys.exit(1)
    print(f"Verified: {len(old_b64)} base64 images preserved byte-identical")

    output_path.write_text(html, encoding="utf-8")
    diff = len(html) - len(html_path.read_text(encoding="utf-8"))
    print(f"Patched: {html_path.name} → {output_path.name} ({diff:+d} chars)")


if __name__ == "__main__":
    event_dir = Path(__file__).parent.parent / "Event_1"
    prods = sorted(event_dir.glob("storyboard_v*_prod.html"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not prods:
        print("ERROR: no _prod.html found")
        sys.exit(1)
    src = prods[0]
    ver = re.search(r'_v(\d+)_', src.name)
    if ver:
        new_ver = int(ver.group(1)) + 1
        dst_name = src.name.replace(f"_v{ver.group(1)}_", f"_v{new_ver}_")
    else:
        dst_name = src.stem + "_fixed" + src.suffix
    dst = event_dir / dst_name

    print(f"Source: {src.name}")
    print(f"Target: {dst_name}")
    patch(src, dst)
