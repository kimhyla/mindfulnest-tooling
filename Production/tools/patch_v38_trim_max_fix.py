#!/usr/bin/env python3
"""Trim slider initial-max race fix (preflight 106) for storyboard_v38_prod.html.

Context:
- Per-beat Trim Start / Trim End sliders ALREADY exist (lines 864-889) with
  proper CSS and dynamic `loadedmetadata` listeners (lines 917-966) that set
  `tss.max = String(dur)` once video metadata loads.
- BUG: initial slider max is hardcoded to "10" (lines 866, 870, 877). If Kim
  drags the trim_end slider to the right (intending "keep full clip") BEFORE
  the video's metadata event fires, the onchange persists trim_end=10.0 even
  when the clip is only 5.5s or 6.2s long. Server-side `trim_normalized`
  clamps at render time so the preview output is correct, but the stored UI
  state is wrong and confusing.
- FIX: raise initial maxDur default to 60s (safe for any realistic beat clip
  length), keep max slider attribute in sync. The metadata listener still
  clamps to the actual `dur` once the video preload fires. Value persisted
  before metadata load will be clamped by the existing listener block
  (lines 931-935) on page reload / option-selection click.

Event-agnostic: the existing JS uses `window._beatTrims[rowIdx]` indexed by
row position and `section.querySelector("video")` — zero hardcoded beat IDs
or event references. This patch preserves that property.

Single anchor edit:
  E1  "var maxDur = 10;\n" -> "var maxDur = 60;  // preflight 106: initial safe default; metadata listener clamps to actual dur\n"
      Also replace both slider `max: "10"` attributes with `max: String(maxDur)`.

All Rule 7 Path B invariants enforced:
  - Backup written BEFORE patched output.
  - Base64 image SHA256 pre + post must match.
  - node --check on extracted scripts.
  - Single-match assertion on each anchor.
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
            f"[trim-max-fix] FATAL single-match failed for {label!r}: "
            f"found {n}, expected 1.",
        )


def _node_check(src: str) -> None:
    if shutil.which("node") is None:
        print("[trim-max-fix] WARN: node not on PATH; skipping syntax check.")
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
                f"[trim-max-fix] FATAL node --check failed:\n"
                f"STDOUT: {r.stdout}\nSTDERR: {r.stderr}",
            )
        print("[trim-max-fix] node --check: OK")
    finally:
        os.unlink(tmpname)


def main() -> int:
    if not TARGET.is_file():
        print(f"[trim-max-fix] Target not found: {TARGET}", file=sys.stderr)
        return 2

    src = TARGET.read_text(encoding="utf-8")

    # Idempotency: if already patched, exit success.
    idem_marker = "var maxDur = 60;  // preflight 106"
    if idem_marker in src:
        print("[trim-max-fix] Already patched (idempotency marker found); nothing to do.")
        return 0

    # Pre-patch SHA of all base64 images.
    pre_hash, pre_n = _sha256_sorted_b64(src)
    print(f"[trim-max-fix] Pre-patch base64 count={pre_n} SHA256={pre_hash[:16]}")

    # Anchor 1: the maxDur declaration.
    a1_before = "            var trimGroup = el(\"div\", { \"class\": \"mn-trim-group\" });\n            var maxDur = 10;\n"
    a1_after = (
        "            var trimGroup = el(\"div\", { \"class\": \"mn-trim-group\" });\n"
        "            var maxDur = 60;  // preflight 106: initial safe default; metadata listener clamps to actual dur\n"
    )
    _assert_single(src, a1_before, "A1: maxDur declaration")
    src2 = src.replace(a1_before, a1_after)

    # Anchor 2: trim_start slider max attribute.
    a2_before = (
        "            var tsLabel = el(\"label\", {}, [\"Trim Start:\"]);\n"
        "            var tsSlider = el(\"input\", {\n"
        "                type: \"range\", min: \"0\", max: \"10\", step: \"0.1\",\n"
        "                value: String(trimStart)\n"
        "            });"
    )
    a2_after = (
        "            var tsLabel = el(\"label\", {}, [\"Trim Start:\"]);\n"
        "            var tsSlider = el(\"input\", {\n"
        "                type: \"range\", min: \"0\", max: String(maxDur), step: \"0.1\",\n"
        "                value: String(trimStart)\n"
        "            });"
    )
    _assert_single(src2, a2_before, "A2: tsSlider initial max")
    src3 = src2.replace(a2_before, a2_after)

    # Anchor 3: trim_end slider max attribute + null-safe initial value.
    a3_before = (
        "            var teLabel = el(\"label\", {}, [\"Trim End:\"]);\n"
        "            var teSlider = el(\"input\", {\n"
        "                type: \"range\", min: \"0\", max: \"10\", step: \"0.1\",\n"
        "                value: String(trimEnd || 0)\n"
        "            });"
    )
    a3_after = (
        "            var teLabel = el(\"label\", {}, [\"Trim End:\"]);\n"
        "            var teSlider = el(\"input\", {\n"
        "                type: \"range\", min: \"0\", max: String(maxDur), step: \"0.1\",\n"
        "                // preflight 106: null trim_end -> slider at max (= 'full'); metadata listener refines\n"
        "                value: String(trimEnd != null ? trimEnd : maxDur)\n"
        "            });"
    )
    _assert_single(src3, a3_before, "A3: teSlider initial max + value")
    new_src = src3.replace(a3_before, a3_after)

    # Post-patch SHA check (base64 images must be byte-identical).
    post_hash, post_n = _sha256_sorted_b64(new_src)
    if pre_hash != post_hash or pre_n != post_n:
        raise SystemExit(
            f"[trim-max-fix] FATAL base64 image integrity broken: "
            f"pre={pre_hash[:16]}({pre_n}) post={post_hash[:16]}({post_n}). "
            f"Aborted without write.",
        )
    print(f"[trim-max-fix] Post-patch base64 count={post_n} SHA256={post_hash[:16]} (MATCH)")

    # Script-tag count sanity.
    pre_scripts = src.count("<script")
    post_scripts = new_src.count("<script")
    if pre_scripts != post_scripts:
        raise SystemExit(
            f"[trim-max-fix] FATAL script tag count changed: {pre_scripts} -> {post_scripts}",
        )

    # Node syntax check.
    _node_check(new_src)

    # Backup.
    ts = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup = TARGET.with_name(TARGET.name + f".bak_trim_max_fix_{ts}")
    shutil.copy2(TARGET, backup)
    print(f"[trim-max-fix] Backup: {backup}")

    # Write.
    TARGET.write_text(new_src, encoding="utf-8")
    print(f"[trim-max-fix] Patched {TARGET} (size {len(new_src)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
