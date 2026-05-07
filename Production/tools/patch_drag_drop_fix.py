#!/usr/bin/env python3
"""
Path B patch: Fix drag-drop to use label-derived keys instead of index mapping.

Problem: initDrag() maps gallery images to IN keys by position index.
When images are injected, the positions don't match and drag-drop breaks.

Fix: Derive each image's drag key from its <p> label text. Also ensure
all gallery images have matching IN entries (for dropdown population).

This patch is idempotent — safe to run on any storyboard version.
"""
import re
import sys
from pathlib import Path


def patch(html_path: Path, output_path: Path):
    html = html_path.read_text(encoding="utf-8")

    # Snapshot base64 for safety
    old_b64 = re.findall(r'data:image/[^"]{100,}', html)

    # ─── 1. Replace initDrag() with label-based version ───
    old_initdrag = re.search(
        r'function initDrag\(\)\{.*?\n\}',
        html, re.DOTALL
    )
    if not old_initdrag:
        print("ERROR: Could not find initDrag() function")
        sys.exit(1)

    new_initdrag = '''function initDrag(){
  var ics=document.querySelectorAll(".ic");
  for(var i=0;i<ics.length;i++){
    var img=ics[i].querySelector("img");
    var p=ics[i].querySelector("p");
    if(!img||!p)continue;
    var key=p.textContent.replace(/\\.png$/i,"").replace(/\\s+/g,"_");
    img.setAttribute("draggable","true");
    img.setAttribute("data-imgkey",key);
    (function(img){
      img.addEventListener("dragstart",function(e){
        dragKey=this.getAttribute("data-imgkey");
        this.classList.add("dragging");
        e.dataTransfer.effectAllowed="copy";
        e.dataTransfer.setData("text/plain",dragKey);
      });
      img.addEventListener("dragend",function(){
        this.classList.remove("dragging");
        dragKey=null;
        var ts=document.querySelectorAll(".lr.drop-target");
        for(var j=0;j<ts.length;j++)ts[j].classList.remove("drop-target");
      });
    })(img);
  }
}'''

    html = html[:old_initdrag.start()] + new_initdrag + html[old_initdrag.end():]
    print(f"Replaced initDrag() (label-based, {len(new_initdrag)} chars)")

    # ─── 2. Sync IN with all gallery images ───
    # Extract all gallery image names
    gallery_names = re.findall(r'<div class="ic"><img[^>]+><p>([^<]+)</p></div>', html)
    gallery_keys = []
    for name in gallery_names:
        key = name.replace(".png", "").replace(" ", "_")
        gallery_keys.append((key, name))

    # Get current IN keys
    in_match = re.search(r'var IN=\{([^}]+)\}', html)
    if in_match:
        in_keys = re.findall(r'"([^"]+)":', in_match.group(1))
    else:
        in_keys = []

    # Add missing gallery images to IN (before "none")
    added = 0
    for key, display_name in gallery_keys:
        if key not in in_keys:
            entry = f'"{key}": "{display_name}", '
            html = html.replace('"none": "(No image)"', entry + '"none": "(No image)"', 1)
            print(f"  Added IN[\"{key}\"]")
            added += 1
    if added == 0:
        print("  IN already has all gallery keys")

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
    # Find latest _prod.html
    prods = sorted(event_dir.glob("storyboard_v*_prod.html"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not prods:
        print("ERROR: no _prod.html found")
        sys.exit(1)
    src = prods[0]
    # Version up
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
