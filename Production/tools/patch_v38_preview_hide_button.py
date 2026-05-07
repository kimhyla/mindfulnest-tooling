#!/usr/bin/env python3
"""Add Hide Preview button + constrain preview video height (preflight 106 follow-up).

Kim's 2026-04-19 feedback: 'i cant see how to x out of the video preview ... wheres
the widget?' The preview <video> element renders inline below the top bar and eats
the viewport, blocking scroll access to the per-beat Animation Composer trim
sliders embedded inside each dialogue row.

Fix (single-file Path B patch):
  A1  Preview player inline style: add `max-height: 40vh; display: block;` to the
      style attr. Default stays hidden via display:none; when shown, max-height
      caps it at 40% of viewport so the rest of the page stays visible. NOTE:
      we keep `display:none` in the initial style (the support script sets
      `display:block` on load). The 40vh max-height applies whenever visible.
  A2  Hide button: append a `✕ Hide` button to the previewBar row, visible only
      when the player is visible. Clicking it sets player.style.display=none.
      Button itself toggled visible/hidden by the same support script that
      manages the player.
  A3  Support script: after `player.style.display = "block"` (where it reveals
      the video), also reveal the Hide button. The Hide button's onclick hides
      both the video AND itself.

Rule 7 Path B: base64 image SHA256 pre/post, node --check, single-match assertions,
backup-before-write.
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

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGET = PROJECT_ROOT / "Production" / "Event_1" / "storyboard_v38_prod.html"

_B64_IMG_RE = re.compile(r"data:image/[a-zA-Z.+-]+;base64,[A-Za-z0-9+/=]+")


def _sha256_sorted_b64(src: str) -> tuple[str, int]:
    uris = sorted(_B64_IMG_RE.findall(src))
    return hashlib.sha256("\n".join(uris).encode("utf-8")).hexdigest(), len(uris)


def _assert_single(hay: str, needle: str, label: str) -> None:
    n = hay.count(needle)
    if n != 1:
        raise SystemExit(
            f"[preview-hide] FATAL single-match failed for {label!r}: "
            f"found {n}, expected 1.",
        )


def _node_check(src: str) -> None:
    if shutil.which("node") is None:
        print("[preview-hide] WARN: node not on PATH; skipping syntax check.")
        return
    bodies = re.findall(r"<script[^>]*>(.*?)</script>", src, flags=re.DOTALL)
    concat = "\n;\n".join(bodies)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False,
                                     encoding="utf-8") as tf:
        tf.write(concat); tmpname = tf.name
    try:
        r = subprocess.run(["node", "--check", tmpname],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise SystemExit(
                f"[preview-hide] FATAL node --check failed:\n"
                f"STDOUT: {r.stdout}\nSTDERR: {r.stderr}",
            )
        print("[preview-hide] node --check: OK")
    finally:
        os.unlink(tmpname)


def main() -> int:
    src = TARGET.read_text(encoding="utf-8")

    # Idempotency marker.
    if "id: \"preview-stitched-hide-btn\"" in src:
        print("[preview-hide] Already patched; nothing to do.")
        return 0

    pre_hash, pre_n = _sha256_sorted_b64(src)
    print(f"[preview-hide] Pre-patch base64 count={pre_n} SHA256={pre_hash[:16]}")

    # A1: add max-height to preview player inline style.
    a1_before = (
        '        var previewPlayer = el("video", {\n'
        '            id: "preview-stitched-player",\n'
        '            style: "display:none; max-width:100%; margin-top:8px;",\n'
        '            controls: "controls", preload: "metadata",\n'
        '        });'
    )
    a1_after = (
        '        var previewPlayer = el("video", {\n'
        '            id: "preview-stitched-player",\n'
        '            style: "display:none; max-width:100%; max-height:40vh; margin-top:8px;",\n'
        '            controls: "controls", preload: "metadata",\n'
        '        });'
    )
    _assert_single(src, a1_before, "A1: preview player style")
    src2 = src.replace(a1_before, a1_after)

    # A2: add Hide button to previewBar row (between save-ind and end of array).
    a2_before = (
        '            el("button", {id: "preview-stitched-btn", "class": "mn-secondary"}, ["\u25B6 Preview All Stitched"]),\n'
        '            el("span", {id: "fade-beats-saveind", "class": "save-ind pathapp-saveind"}, [""]),\n'
        '        ]);'
    )
    a2_after = (
        '            el("button", {id: "preview-stitched-btn", "class": "mn-secondary"}, ["\u25B6 Preview All Stitched"]),\n'
        '            el("button", {id: "preview-stitched-hide-btn", "class": "mn-secondary", '
        'style: "display:none; margin-left:4px;"}, ["\u2715 Hide Preview"]),\n'
        '            el("span", {id: "fade-beats-saveind", "class": "save-ind pathapp-saveind"}, [""]),\n'
        '        ]);'
    )
    _assert_single(src2, a2_before, "A2: previewBar children array")
    src3 = src2.replace(a2_before, a2_after)

    # A3: wire Hide button + reveal it when player is shown.
    # Support script sets player.style.display = "block" when stitch succeeds.
    # Find that line and add hide-button reveal + click handler hookup.
    a3_before = '    console.log("[preview-stitched] LD-285 v2 wired");'
    a3_after = (
        '    // preflight 106 UX: Hide Preview button reveals on show, hides both on click.\n'
        '    var hideBtn = document.getElementById("preview-stitched-hide-btn");\n'
        '    if (hideBtn) {\n'
        '      hideBtn.onclick = function () {\n'
        '        var p = document.getElementById("preview-stitched-player");\n'
        '        if (p) { try { p.pause(); } catch (e) {} p.style.display = "none"; }\n'
        '        hideBtn.style.display = "none";\n'
        '      };\n'
        '      // Observe player display to toggle hide button visibility.\n'
        '      var playerEl = document.getElementById("preview-stitched-player");\n'
        '      if (playerEl) {\n'
        '        var mo = new MutationObserver(function () {\n'
        '          hideBtn.style.display = (playerEl.style.display === "none" || !playerEl.style.display) ? "none" : "inline-block";\n'
        '        });\n'
        '        mo.observe(playerEl, { attributes: true, attributeFilter: ["style"] });\n'
        '      }\n'
        '    }\n'
        '    console.log("[preview-stitched] LD-285 v2 wired");'
    )
    _assert_single(src3, a3_before, "A3: support script console.log anchor")
    new_src = src3.replace(a3_before, a3_after)

    # Post-patch checks.
    post_hash, post_n = _sha256_sorted_b64(new_src)
    if pre_hash != post_hash or pre_n != post_n:
        raise SystemExit(
            f"[preview-hide] FATAL base64 integrity: pre={pre_hash[:16]}({pre_n}) "
            f"post={post_hash[:16]}({post_n}).",
        )
    print(f"[preview-hide] Post-patch base64 count={post_n} SHA256={post_hash[:16]} (MATCH)")

    if src.count("<script") != new_src.count("<script"):
        raise SystemExit("[preview-hide] FATAL script tag count changed")

    _node_check(new_src)

    ts = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup = TARGET.with_name(TARGET.name + f".bak_preview_hide_{ts}")
    shutil.copy2(TARGET, backup)
    print(f"[preview-hide] Backup: {backup}")
    TARGET.write_text(new_src, encoding="utf-8")
    print(f"[preview-hide] Patched {TARGET} (size {len(new_src)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
