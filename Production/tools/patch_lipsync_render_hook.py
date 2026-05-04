#!/usr/bin/env python3
"""
Path B patch: Hook lip sync button injection into the render() cycle.

Problem: injectLipSyncButtons() runs once at page load via setTimeout.
When render() rebuilds row DOM, lip sync buttons are destroyed and never
re-created because render()'s wrapper only calls _injectAnimations.

Fix:
  1. Expose injectLipSyncButtons to window as window._injectLipSyncButtons
  2. Add window._injectLipSyncButtons() call to the render wrapper

This patch is idempotent — safe to run on any storyboard version.
"""
import re
import sys
from pathlib import Path


def patch(html_path: Path, output_path: Path):
    html = html_path.read_text(encoding="utf-8")

    # Snapshot base64 for safety
    old_b64 = re.findall(r'data:image/[^"]{100,}', html)

    changes = 0

    # ─── 1. Expose injectLipSyncButtons to window ───
    # Find the setTimeout line and add window assignment before it
    old_expose = "    // Run after a short delay to let the storyboard render\n    setTimeout(injectLipSyncButtons, 1000);"
    new_expose = "    // Expose for render() hook\n    window._injectLipSyncButtons = injectLipSyncButtons;\n\n    // Run after a short delay to let the storyboard render\n    setTimeout(injectLipSyncButtons, 1000);"

    if "window._injectLipSyncButtons" not in html:
        if old_expose in html:
            html = html.replace(old_expose, new_expose, 1)
            print("  [1] Exposed injectLipSyncButtons as window._injectLipSyncButtons")
            changes += 1
        else:
            print("WARNING: Could not find setTimeout(injectLipSyncButtons) pattern")
    else:
        print("  [1] Already exposed (skipping)")

    # ─── 2. Hook into render() wrapper ───
    # Current: render=function(){_baseRender();initDrag();setupDropZones();if(window._injectAnimations)window._injectAnimations();};
    # Target:  render=function(){_baseRender();initDrag();setupDropZones();if(window._injectAnimations)window._injectAnimations();if(window._injectLipSyncButtons)window._injectLipSyncButtons();};

    old_render = "if(window._injectAnimations)window._injectAnimations();};"
    new_render = "if(window._injectAnimations)window._injectAnimations();if(window._injectLipSyncButtons)window._injectLipSyncButtons();};"

    if "window._injectLipSyncButtons" not in html.split("render=function()")[1].split("};")[0] if "render=function()" in html else "":
        if old_render in html:
            html = html.replace(old_render, new_render, 1)
            print("  [2] Added _injectLipSyncButtons to render() wrapper")
            changes += 1
        else:
            print("WARNING: Could not find render wrapper pattern")
    else:
        print("  [2] Already in render wrapper (skipping)")

    if changes == 0:
        print("No changes needed — patch already applied")
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
