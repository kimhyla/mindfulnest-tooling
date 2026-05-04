#!/usr/bin/env python3
"""Per-beat fade-after override slider for storyboard_v38_prod.html (LD PER_ITEM_FADE_AFTER_OVERRIDE_V1).

Rule 7 Path B — JS-only patch (behavior change). Inserts a new "Fade after:"
slider into each beat's Animation Composer, between the existing Video Lead-in
controls and the Trim Start / Trim End group.

UI contract:
  <input type=range min=-1 max=1000 step=25>
    -1  = inherit global fade_between_beats_ms (label reads "inherit")
     N  = override this beat's outgoing-pair fade to N ms (label "Nms")
  onchange -> routedPatch(bk, "fade_after_ms", v === -1 ? null : v, ...)

Anchors (all single-match):
  A1  Insert label/slider/val declarations below the delayVal declaration.
  A2  Insert appendChild() calls into `tc` between delayVal and trimGroup.
  A3  Insert oninput + onchange handlers inside the IIFE at the
      same level as the delay slider handlers (dSlider.oninput...).
  A4  Add three new IIFE arguments (faSlider, faVal) at the IIFE call site.
  A5  Add three new IIFE parameters (faSlider, faVal) in the IIFE function signature.

All Rule 7 Path B invariants enforced:
  - Backup before write
  - Base64 SHA256 byte-identical pre + post
  - node --check on extracted scripts
  - Single-match single-anchor replacements
  - Idempotency marker for safe re-runs

V4 forward-compat note: the fade_after_ms KEY name is stable across scopes.
When V4 ships segment-level composers (Phase A / Phase B / etc.), the same
slider pattern applies to a segment composer — the server helper
resolve_pair_fades() already reads `fade_after_ms` from any metadata dict.
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

IDEM_MARKER = "/* fade-after-override v1 */"


def _sha256_sorted_b64(src: str) -> tuple[str, int]:
    uris = sorted(_B64_IMG_RE.findall(src))
    return hashlib.sha256("\n".join(uris).encode("utf-8")).hexdigest(), len(uris)


def _assert_single(hay: str, needle: str, label: str) -> None:
    n = hay.count(needle)
    if n != 1:
        raise SystemExit(
            f"[fade-override] FATAL single-match failed for {label!r}: "
            f"found {n}, expected 1.",
        )


def _node_check(src: str) -> None:
    if shutil.which("node") is None:
        print("[fade-override] WARN: node not on PATH; skipping syntax check.")
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
                f"[fade-override] FATAL node --check failed:\n"
                f"STDOUT: {r.stdout}\nSTDERR: {r.stderr}",
            )
        print("[fade-override] node --check: OK")
    finally:
        os.unlink(tmpname)


def main() -> int:
    if not TARGET.is_file():
        print(f"[fade-override] Target not found: {TARGET}", file=sys.stderr)
        return 2

    src = TARGET.read_text(encoding="utf-8")

    if IDEM_MARKER in src:
        print("[fade-override] Already patched (idempotency marker found); nothing to do.")
        return 0

    pre_hash, pre_n = _sha256_sorted_b64(src)
    print(f"[fade-override] Pre-patch base64 count={pre_n} SHA256={pre_hash[:16]}")

    # ------------------------------------------------------------------
    # A1: insert fade-after slider DECLARATIONS below the delayVal decl.
    # ------------------------------------------------------------------
    a1_before = (
        "            var delayVal = el(\"span\", { \"class\": \"mn-val\" }, [audioDelay.toFixed(1) + \"s\"]);\n"
        "\n"
        "            // ===== TRIM SLIDERS =====\n"
    )
    a1_after = (
        "            var delayVal = el(\"span\", { \"class\": \"mn-val\" }, [audioDelay.toFixed(1) + \"s\"]);\n"
        "\n"
        "            // ===== FADE AFTER OVERRIDE (per-beat outgoing fade) ===== " + IDEM_MARKER + "\n"
        "            // -1 sentinel = 'inherit global fade_between_beats_ms'; 0-1000 overrides this beat's outgoing pair.\n"
        "            // null over the wire = inherit; int = override. Item-agnostic on the server (resolve_pair_fades).\n"
        "            var faInitRaw = (b.phase_1 && b.phase_1.fade_after_ms != null) ? b.phase_1.fade_after_ms : -1;\n"
        "            var faLabel = el(\"label\", {}, [\"Fade after:\"]);\n"
        "            var faSlider = el(\"input\", {\n"
        "                type: \"range\", min: \"-1\", max: \"1000\", step: \"25\",\n"
        "                value: String(faInitRaw)\n"
        "            });\n"
        "            var faVal = el(\"span\", { \"class\": \"mn-val\" }, [faInitRaw === -1 ? \"inherit\" : (faInitRaw + \"ms\")]);\n"
        "\n"
        "            // ===== TRIM SLIDERS =====\n"
    )
    _assert_single(src, a1_before, "A1: faSlider declaration insertion")
    src2 = src.replace(a1_before, a1_after)

    # ------------------------------------------------------------------
    # A2: append fade-after slider into `tc` between delayVal and trimGroup.
    # ------------------------------------------------------------------
    a2_before = (
        "            tc.appendChild(delayVal);\n"
        "\n"
        "            trimGroup.appendChild(tsLabel);\n"
    )
    a2_after = (
        "            tc.appendChild(delayVal);\n"
        "            tc.appendChild(faLabel);\n"
        "            tc.appendChild(faSlider);\n"
        "            tc.appendChild(faVal);\n"
        "\n"
        "            trimGroup.appendChild(tsLabel);\n"
    )
    _assert_single(src2, a2_before, "A2: tc.appendChild(faSlider) insertion")
    src3 = src2.replace(a2_before, a2_after)

    # ------------------------------------------------------------------
    # A3: insert fade-after oninput + onchange handlers inside the IIFE,
    # directly after the `dSlider.onchange` block (same-scope pattern as
    # other trim sliders).
    # ------------------------------------------------------------------
    a3_before = (
        "                dSlider.onchange = function() {\n"
        "                    var v = parseFloat(this.value);\n"
        "                    fetch(SERVER + \"/api/beat/delay\", {\n"
        "                        method: \"POST\",\n"
        "                        headers: { \"Content-Type\": \"application/json\" },\n"
        "                        body: JSON.stringify({ beat: bk, audio_delay: v })\n"
        "                    }).catch(function(e) { console.error(\"delay save:\", e); });\n"
        "                };\n"
        "\n"
        "                // === Trim Start slider ===\n"
    )
    a3_after = (
        "                dSlider.onchange = function() {\n"
        "                    var v = parseFloat(this.value);\n"
        "                    fetch(SERVER + \"/api/beat/delay\", {\n"
        "                        method: \"POST\",\n"
        "                        headers: { \"Content-Type\": \"application/json\" },\n"
        "                        body: JSON.stringify({ beat: bk, audio_delay: v })\n"
        "                    }).catch(function(e) { console.error(\"delay save:\", e); });\n"
        "                };\n"
        "\n"
        "                // === Fade After slider === " + IDEM_MARKER + "\n"
        "                faSlider.oninput = function() {\n"
        "                    var raw = parseInt(this.value, 10);\n"
        "                    faVal.textContent = (raw === -1) ? \"inherit\" : (raw + \"ms\");\n"
        "                };\n"
        "                faSlider.onchange = function() {\n"
        "                    var raw = parseInt(this.value, 10);\n"
        "                    var payload = (raw === -1) ? null : raw;\n"
        "                    var _faLegacy = _t3LegacyRefuse.bind(null, faSlider, bk, \"fade_after_ms\", \"offline\");\n"
        "                    var _faSi = (window._pathappWire && window._pathappWire.ensureSaveInd)\n"
        "                        ? window._pathappWire.ensureSaveInd(faSlider, ri, \"fadeAfter\") : null;\n"
        "                    if (window._pathappWire && typeof window.pathappPatch === \"function\") {\n"
        "                        window._pathappWire.routedPatch(bk, \"fade_after_ms\", payload, _faSi, _faLegacy);\n"
        "                    } else {\n"
        "                        _faLegacy();\n"
        "                    }\n"
        "                };\n"
        "\n"
        "                // === Trim Start slider ===\n"
    )
    _assert_single(src3, a3_before, "A3: fadeAfter handler insertion anchor")
    src4 = src3.replace(a3_before, a3_after)

    # ------------------------------------------------------------------
    # A4: IIFE call site — pass faSlider + faVal as new trailing args.
    # ------------------------------------------------------------------
    a4_before = (
        "            })(k, rowIdx, tsSlider, teSlider, tsVal, teVal, vidEl, delaySlider, delayVal, prevBtn, trimBar, trimActive, trimPlayhead, trimInfo);\n"
    )
    a4_after = (
        "            })(k, rowIdx, tsSlider, teSlider, tsVal, teVal, vidEl, delaySlider, delayVal, prevBtn, trimBar, trimActive, trimPlayhead, trimInfo, faSlider, faVal);\n"
    )
    _assert_single(src4, a4_before, "A4: IIFE call site new args")
    src5 = src4.replace(a4_before, a4_after)

    # ------------------------------------------------------------------
    # A5: IIFE function signature — add faSlider, faVal params.
    # ------------------------------------------------------------------
    a5_before = (
        "            (function(bk, ri, tss, tes, tsv, tev, vid, dSlider, dVal, pBtn, tBar, tActive, tPlayhead, tInfo) {\n"
    )
    a5_after = (
        "            (function(bk, ri, tss, tes, tsv, tev, vid, dSlider, dVal, pBtn, tBar, tActive, tPlayhead, tInfo, faSlider, faVal) {\n"
    )
    _assert_single(src5, a5_before, "A5: IIFE signature new params")
    new_src = src5.replace(a5_before, a5_after)

    # ------------------------------------------------------------------
    # Post-patch SHA check (base64 images must be byte-identical).
    # ------------------------------------------------------------------
    post_hash, post_n = _sha256_sorted_b64(new_src)
    if pre_hash != post_hash or pre_n != post_n:
        raise SystemExit(
            f"[fade-override] FATAL base64 image integrity broken: "
            f"pre={pre_hash[:16]}({pre_n}) post={post_hash[:16]}({post_n}). "
            f"Aborted without write.",
        )
    print(f"[fade-override] Post-patch base64 count={post_n} SHA256={post_hash[:16]} (MATCH)")

    pre_scripts = src.count("<script")
    post_scripts = new_src.count("<script")
    if pre_scripts != post_scripts:
        raise SystemExit(
            f"[fade-override] FATAL script tag count changed: "
            f"{pre_scripts} -> {post_scripts}",
        )

    _node_check(new_src)

    ts = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup = TARGET.with_name(TARGET.name + f".bak_fade_after_override_{ts}")
    shutil.copy2(TARGET, backup)
    print(f"[fade-override] Backup: {backup}")

    TARGET.write_text(new_src, encoding="utf-8")
    print(f"[fade-override] Patched {TARGET} (size {len(new_src)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
