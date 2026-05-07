#!/usr/bin/env python3
"""Fix sticky top bar by moving bulky panels OUT of the sticky root.

Kim's 2026-04-19 feedback: "it doesnt stay stuck in the top row basically
thats the problem... even closing the preview still leaves the problem intact."

Root cause (confirmed via DOM inspection):
  #mn-prod-overlay CSS has `position: sticky; top: 0` AND contains every
  major UI element — title, health, previewBar, previewPlayer, phasePanelsMount
  (Phase B + Phase A), progressWrap, statusLine, exportBtn — all in a single
  flex-wrap row. When the Phase B panel expands, the root container grows
  taller than the viewport. Sticky positioning only works when the element is
  shorter than its scroll container; once taller, the browser falls back to
  normal flow and the "sticky" bar scrolls off-screen like any other element.

Fix (structural, single-anchor Path B patch):
  Keep only { title, health, previewBar, previewPlayer } in the sticky root.
  Move { phasePanelsMount, progressWrap, statusLine, exportBtn } into a new
  sibling container #mn-lower inserted immediately AFTER the root. Those
  bulky, expandable panels now flow normally below the sticky header, and
  Kim can scroll past them to reach the dialogue rows + per-beat trim
  sliders. The top bar stays pinned at the top throughout.

No JS logic changes. Pure DOM restructure at mount() time. All existing
event wiring / ID lookups unaffected (elements are still in the DOM under
the same IDs, just under a different parent).
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


def _sha256_sorted_b64(src):
    uris = sorted(_B64_IMG_RE.findall(src))
    return hashlib.sha256("\n".join(uris).encode("utf-8")).hexdigest(), len(uris)


def _assert_single(hay, needle, label):
    n = hay.count(needle)
    if n != 1:
        raise SystemExit(
            f"[sticky-fix] FATAL single-match failed for {label!r}: "
            f"found {n}, expected 1.",
        )


def _node_check(src):
    if shutil.which("node") is None:
        print("[sticky-fix] WARN: node not on PATH; skipping syntax check.")
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
                f"[sticky-fix] FATAL node --check failed:\n"
                f"STDOUT: {r.stdout}\nSTDERR: {r.stderr}",
            )
        print("[sticky-fix] node --check: OK")
    finally:
        os.unlink(tmpname)


def main():
    src = TARGET.read_text(encoding="utf-8")

    if "id: \"mn-lower\"" in src:
        print("[sticky-fix] Already patched; nothing to do.")
        return 0

    pre_hash, pre_n = _sha256_sorted_b64(src)
    print(f"[sticky-fix] Pre-patch base64 count={pre_n} SHA256={pre_hash[:16]}")

    # A1: split root.appendChild chain. Move phase panels + progress + status
    # + export into a new sibling container.
    a1_before = (
        "        root.appendChild(previewBar);\n"
        "        root.appendChild(previewPlayer);\n"
        "        // V3 Phase B/A authoring panels (populated by support script below).\n"
        "        var phasePanelsMount = el(\"div\", {id: \"mn-phase-panels\"}, []);\n"
        "        root.appendChild(phasePanelsMount);\n"
        "        root.appendChild(progressWrap);\n"
        "        root.appendChild(statusLine);\n"
        "        root.appendChild(exportBtn);\n"
        "\n"
        "        document.body.insertBefore(root, document.body.firstChild);\n"
        "    }"
    )
    a1_after = (
        "        root.appendChild(previewBar);\n"
        "        root.appendChild(previewPlayer);\n"
        "\n"
        "        // preflight 106 sticky fix: phase panels + progress + export\n"
        "        // live in a separate container BELOW the sticky root, so the\n"
        "        // top bar stays compact enough to actually stick.\n"
        "        var phasePanelsMount = el(\"div\", {id: \"mn-phase-panels\"}, []);\n"
        "        var lowerContainer = el(\"div\", {id: \"mn-lower\"}, [\n"
        "            phasePanelsMount, progressWrap, statusLine, exportBtn,\n"
        "        ]);\n"
        "\n"
        "        document.body.insertBefore(root, document.body.firstChild);\n"
        "        // Insert lower container immediately after the sticky root so it\n"
        "        // sits above the original v38 dialogue table in normal flow.\n"
        "        if (root.nextSibling) {\n"
        "            document.body.insertBefore(lowerContainer, root.nextSibling);\n"
        "        } else {\n"
        "            document.body.appendChild(lowerContainer);\n"
        "        }\n"
        "    }"
    )
    _assert_single(src, a1_before, "A1: mount() root.appendChild chain + insertBefore")
    src2 = src.replace(a1_before, a1_after)

    # A2: add #mn-lower CSS block so it has spacing + doesn't inherit sticky flex.
    a2_before = "  #mn-phase-panels { margin: 12px 0 4px; font-family: inherit; font-size: 13px; }"
    a2_after = (
        "  /* preflight 106 sticky fix: lower container hosts bulky panels + progress\n"
        "     below the sticky top bar so the top bar stays short enough to stick. */\n"
        "  #mn-lower { padding: 8px 18px; background: #0d1117; }\n"
        "  #mn-phase-panels { margin: 12px 0 4px; font-family: inherit; font-size: 13px; }"
    )
    _assert_single(src2, a2_before, "A2: #mn-phase-panels CSS rule")
    new_src = src2.replace(a2_before, a2_after)

    post_hash, post_n = _sha256_sorted_b64(new_src)
    if pre_hash != post_hash or pre_n != post_n:
        raise SystemExit(
            f"[sticky-fix] FATAL base64 integrity: pre={pre_hash[:16]}({pre_n}) "
            f"post={post_hash[:16]}({post_n}).",
        )
    print(f"[sticky-fix] Post-patch base64 count={post_n} SHA256={post_hash[:16]} (MATCH)")
    if src.count("<script") != new_src.count("<script"):
        raise SystemExit("[sticky-fix] FATAL script tag count changed")
    _node_check(new_src)

    ts = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup = TARGET.with_name(TARGET.name + f".bak_sticky_fix_{ts}")
    shutil.copy2(TARGET, backup)
    print(f"[sticky-fix] Backup: {backup}")
    TARGET.write_text(new_src, encoding="utf-8")
    print(f"[sticky-fix] Patched {TARGET} (size {len(new_src)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
