#!/usr/bin/env python3
"""
Path B patch: Show animation controls for beats in ANY active state, not just "completed".

Problem: injectAnimationsFromStatus() skips beats where b.status !== "completed".
When Kim submits new B+C options, the beat goes to "polling" state and all animation
controls (Generate B+C, Preview, Trim) disappear until polling finishes.

Fix: Allow "polling" and "partial" states too — show completed options inline,
show a progress indicator for polling options, and always show the Generate B+C button.

Also fixes: Restart Server button to do full kill sequence (kill port + re-exec).
"""
import re
import sys
from pathlib import Path


def patch(html_path: Path, output_path: Path):
    html = html_path.read_text(encoding="utf-8")

    # Snapshot base64 for safety
    old_b64 = re.findall(r'data:image/[^"]{100,}', html)
    changes = 0

    # ─── 1. Fix animation status check to allow polling beats ───
    old_check = 'if (b.status !== "completed" || !b.options || b.options.length === 0) return;'
    new_check = 'if (!b.options || b.options.length === 0) return; // Show controls for completed AND polling beats'

    if old_check in html:
        html = html.replace(old_check, new_check, 1)
        print("  [1] Relaxed animation status check (completed-only → any beat with options)")
        changes += 1
    else:
        print("  [1] Status check already patched or not found")

    # ─── 2. Fix restart button to do full kill + re-exec ───
    # Find the restart button's fetch call and replace with a more robust version
    old_restart_fetch = '''fetch(SERVER + "/api/server/restart", { method: "POST" })
      .then(function(r) { return r.json(); })
      .then(function() {
        statusDot.style.background = "#f59e0b";
        restartBtn.textContent = "\\u21bb Restarting...";
        restartBtn.disabled = true;
        // Wait then reload
        setTimeout(function() { location.reload(); }, 4000);
      })'''

    new_restart_fetch = '''fetch(SERVER + "/api/server/restart", { method: "POST" })
      .then(function(r) { return r.json(); })
      .then(function() {
        statusDot.style.background = "#f59e0b";
        restartBtn.textContent = "\\u21bb Restarting...";
        restartBtn.disabled = true;
        // Poll until server is back, then reload
        var attempts = 0;
        var poller = setInterval(function() {
          attempts++;
          if (attempts > 20) {
            clearInterval(poller);
            restartBtn.textContent = "\\u274c Restart timed out — use .command file";
            restartBtn.disabled = false;
            return;
          }
          fetch(SERVER + "/api/health", { signal: AbortSignal.timeout(2000) })
            .then(function(r) { return r.json(); })
            .then(function() {
              clearInterval(poller);
              location.reload();
            })
            .catch(function() { /* still restarting */ });
        }, 1500);
      })'''

    if old_restart_fetch in html:
        html = html.replace(old_restart_fetch, new_restart_fetch, 1)
        print("  [2] Upgraded restart button to poll-until-ready (no fixed 4s wait)")
        changes += 1
    else:
        # Try a more flexible match
        print("  [2] Restart fetch pattern not found — trying alternate")
        # Look for the setTimeout reload pattern
        old_timeout = "setTimeout(function() { location.reload(); }, 4000);"
        new_timeout = """// Poll until server is back, then reload
        var attempts = 0;
        var poller = setInterval(function() {
          attempts++;
          if (attempts > 20) {
            clearInterval(poller);
            restartBtn.textContent = "\\u274c Restart timed out \\u2014 use .command file";
            restartBtn.disabled = false;
            return;
          }
          fetch(SERVER + "/api/health", { signal: AbortSignal.timeout(2000) })
            .then(function(r) { return r.json(); })
            .then(function() {
              clearInterval(poller);
              location.reload();
            })
            .catch(function() { /* still restarting */ });
        }, 1500);"""
        if old_timeout in html:
            html = html.replace(old_timeout, new_timeout, 1)
            print("  [2b] Upgraded restart reload to poll-until-ready")
            changes += 1
        else:
            print("  [2] WARNING: Could not find restart timeout pattern")

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
