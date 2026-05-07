#!/usr/bin/env python3
"""Lip-sync UX fixes + Move-to-A button Path B patch for storyboard_v38_prod.html.

Task 1 — three Lip Sync button state fixes (Kim's report, April 19 2026):
  Fix A: hard mismatch detection in `applyCompletedButtonState`. Even when
         `bs.source_changed` is false, if `bs.source_option` does not match
         the currently selected option (read from the DOM — `.mn-anim-opt
         .selected` index under `#r{rowIdx}`), force Re-run state so Kim can
         trigger a fresh lipsync rather than being stuck on a stale file.
  Fix B: always-available "🔁 Re-send for Lip Sync" secondary link inside
         `.mn-lipsync-row`. Never disabled by the "done" preview-toggle
         branch — always fires the POST /api/lipsync submit path.
  Fix C: polling/submitting state text now carries the task_id ("⏳
         Processing... (task abc12345)") so Kim can see something is in
         flight. When `status="submitting"` and `task_id` is null, shows
         "⏳ Submitting... (connecting to ByteDance)" distinctly.

Task 2 — "🔒 Move to A" button per Option B / Option C card:
  In the options loop (b.options.length > 1), after the radio for each card
  where i > 0, append a small button that POSTs to
  `/api/v2/beat/{beat_id}/swap_to_a` with body `{"from_slot": i + 1}`.
  On success: toast "Swapped — Option A now contains your preserved pick.
  B and C are free to regenerate." and call `render()`.
  On error: red toast with `error` + `hint` from the JSON response.

All Rule 7 Path B invariants enforced:
  - Backup written BEFORE patched output.
  - Base64 image SHA256 pre + post must match (22 images expected).
  - node --check on extracted script bodies.
  - Single-match assertion on every anchor.
  - Script-tag count unchanged (NO new <script> tags).
  - Idempotency marker — re-running this patcher is a no-op.
  - Does NOT touch production_server.py (sibling agent owns the
    /api/v2/beat/{beat_id}/swap_to_a endpoint).
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
_IDEM_MARKER = "/* PATCH v38 lipsync-ux + move-to-a applied */"


def _sha256_sorted_b64(src: str) -> tuple[str, int]:
    uris = sorted(_B64_IMG_RE.findall(src))
    return hashlib.sha256("\n".join(uris).encode("utf-8")).hexdigest(), len(uris)


def _assert_single(hay: str, needle: str, label: str) -> None:
    n = hay.count(needle)
    if n != 1:
        raise SystemExit(
            f"[lipsync-ux] FATAL single-match failed for {label!r}: "
            f"found {n}, expected 1.",
        )


def _node_check(src: str) -> None:
    if shutil.which("node") is None:
        print("[lipsync-ux] WARN: node not on PATH; skipping syntax check.")
        return
    bodies = re.findall(r"<script[^>]*>(.*?)</script>", src, flags=re.DOTALL)
    concat = "\n;\n".join(bodies)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8",
    ) as tf:
        tf.write(concat)
        tmpname = tf.name
    try:
        r = subprocess.run(
            ["node", "--check", tmpname],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            raise SystemExit(
                f"[lipsync-ux] FATAL node --check failed:\n"
                f"STDOUT: {r.stdout}\nSTDERR: {r.stderr}",
            )
        print("[lipsync-ux] node --check: OK")
    finally:
        os.unlink(tmpname)


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------

# --- A1 (Fix A + helper install) --------------------------------------------
# Insert a DOM-based selected-option reader AND an idempotency marker just
# BEFORE the `applyCompletedButtonState` function, then rewrite its
# source-mismatch detection logic.
A1_BEFORE = (
    "    var _lipsyncRows = {};\n"
    "\n"
    "    function applyCompletedButtonState(beatKey, bs, btn, stat, video, preview) {\n"
    "        // Shared completed-state renderer used by initial inject + polling +\n"
    "        // periodic refresh. Keeps the three paths in sync.\n"
    "        // Decision 181 TTS_AUTO_REGEN_ON_TEXT_EDIT (April 17 2026): also\n"
    "        // flip to Re-run when lipsync.audio_changed is true (audio was\n"
    "        // regenerated after the lipsync completed → stale audio track).\n"
    "        var reason = null;\n"
    "        if (bs.source_changed) reason = \"Selected clip changed — re-run recommended (was opt \" +\n"
    "            (bs.source_option != null ? bs.source_option : \"?\") + \")\";\n"
    "        else if (bs.audio_changed) reason = \"Audio regenerated after lipsync — re-run recommended\";\n"
)

A1_AFTER = (
    "    var _lipsyncRows = {};\n"
    "\n"
    "    " + _IDEM_MARKER + "\n"
    "    // Fix A helper (April 19 2026): read currently-selected option index\n"
    "    // for a beatKey directly from the DOM. Returns 1-based option index\n"
    "    // or null if no selected card is rendered. Used to detect\n"
    "    // source_option mismatch even when the server flag source_changed is\n"
    "    // stale / false.\n"
    "    function _currentSelectedOption(beatKey) {\n"
    "        var m = /^beat_(\\d+)$/.exec(beatKey);\n"
    "        if (!m) return null;\n"
    "        var rowIdx = parseInt(m[1], 10) - 1;\n"
    "        var row = document.getElementById(\"r\" + rowIdx);\n"
    "        if (!row) return null;\n"
    "        var section = row.querySelector(\".mn-anim-section\");\n"
    "        if (!section) return null;\n"
    "        var cards = section.querySelectorAll(\".mn-anim-opt\");\n"
    "        if (!cards.length) return null;\n"
    "        for (var i = 0; i < cards.length; i++) {\n"
    "            if (cards[i].classList.contains(\"selected\")) return i + 1;\n"
    "        }\n"
    "        return null;\n"
    "    }\n"
    "\n"
    "    function applyCompletedButtonState(beatKey, bs, btn, stat, video, preview) {\n"
    "        // Shared completed-state renderer used by initial inject + polling +\n"
    "        // periodic refresh. Keeps the three paths in sync.\n"
    "        // Decision 181 TTS_AUTO_REGEN_ON_TEXT_EDIT (April 17 2026): also\n"
    "        // flip to Re-run when lipsync.audio_changed is true (audio was\n"
    "        // regenerated after the lipsync completed → stale audio track).\n"
    "        var reason = null;\n"
    "        // Fix A (April 19 2026): hard mismatch detection. Even when the\n"
    "        // server's source_changed flag is stale / false, if the lipsync\n"
    "        // file was produced from a DIFFERENT option than the one\n"
    "        // currently selected, force Re-run state so Kim can trigger a\n"
    "        // fresh lipsync instead of being stuck on a stale file.\n"
    "        var curSel = _currentSelectedOption(beatKey);\n"
    "        if (bs.source_option != null && curSel != null && bs.source_option !== curSel) {\n"
    "            reason = \"Lipsync source was option \" + bs.source_option +\n"
    "                \" but selected is \" + curSel + \" — re-run recommended.\";\n"
    "        }\n"
    "        else if (bs.source_changed) reason = \"Selected clip changed — re-run recommended (was opt \" +\n"
    "            (bs.source_option != null ? bs.source_option : \"?\") + \")\";\n"
    "        else if (bs.audio_changed) reason = \"Audio regenerated after lipsync — re-run recommended\";\n"
)

# --- A2 (Fix C part 1) ------------------------------------------------------
# Rewrite the polling / submitting branch in createLipSyncRow so it shows
# task_id (or a distinct "connecting to ByteDance" message when task_id is
# null and status is submitting).
A2_BEFORE = (
    "        } else if (beatStatus && (beatStatus.status === \"polling\" || beatStatus.status === \"submitting\")) {\n"
    "            lsBtn.textContent = \"\\u23F3 Lip Sync Processing...\";\n"
    "            lsBtn.className = \"mn-lipsync-btn polling\";\n"
    "            lsBtn.disabled = true;\n"
    "            startPolling(beatKey, lsBtn, lsStat, lsVideo, lsPreview);\n"
    "        } else if (beatStatus && beatStatus.status === \"failed\") {\n"
)

A2_AFTER = (
    "        } else if (beatStatus && (beatStatus.status === \"polling\" || beatStatus.status === \"submitting\")) {\n"
    "            // Fix C (April 19 2026): surface task_id on Processing so Kim\n"
    "            // can see something is actually in flight; distinct text for\n"
    "            // the orphan submitting-without-task_id state.\n"
    "            if (beatStatus.status === \"submitting\" && !beatStatus.task_id) {\n"
    "                lsBtn.textContent = \"\\u23F3 Submitting... (connecting to ByteDance)\";\n"
    "            } else if (beatStatus.task_id) {\n"
    "                lsBtn.textContent = \"\\u23F3 Processing... (task \" + String(beatStatus.task_id).substring(0, 8) + \")\";\n"
    "            } else {\n"
    "                lsBtn.textContent = \"\\u23F3 Lip Sync Processing...\";\n"
    "            }\n"
    "            lsBtn.className = \"mn-lipsync-btn polling\";\n"
    "            lsBtn.disabled = true;\n"
    "            startPolling(beatKey, lsBtn, lsStat, lsVideo, lsPreview);\n"
    "        } else if (beatStatus && beatStatus.status === \"failed\") {\n"
)

# --- A3 (Fix C part 2) ------------------------------------------------------
# Also update startPolling's live status-text render so the task_id surfaces
# during active polling, not only at initial render.
A3_BEFORE = (
    "                } else {\n"
    "                    stat.textContent = \"Processing... (\" + bs.status + \")\";\n"
    "                }\n"
)

A3_AFTER = (
    "                } else {\n"
    "                    // Fix C (April 19 2026): include task_id suffix so Kim\n"
    "                    // sees progress; distinct message when submitting has\n"
    "                    // not yet returned a task_id (orphan pre-sweep window).\n"
    "                    if (bs.status === \"submitting\" && !bs.task_id) {\n"
    "                        stat.textContent = \"Submitting... (connecting to ByteDance)\";\n"
    "                    } else if (bs.task_id) {\n"
    "                        stat.textContent = \"Processing... (\" + bs.status + \", task \" + String(bs.task_id).substring(0, 8) + \")\";\n"
    "                    } else {\n"
    "                        stat.textContent = \"Processing... (\" + bs.status + \")\";\n"
    "                    }\n"
    "                }\n"
)

# --- A4 (Fix B) -------------------------------------------------------------
# Extract the submit body into a shared function `submitLipSync`, wire the
# primary click handler through it, and add a secondary "🔁 Re-send" anchor
# that ALWAYS calls submitLipSync (bypassing the .done preview-toggle
# branch). The new anchor is appended to .mn-lipsync-row next to lsBtn.
A4_BEFORE = (
    "        lsBtn.addEventListener(\"click\", function() {\n"
    "            if (lsBtn.disabled) return;\n"
    "            if (lsBtn.classList.contains(\"done\")) {\n"
    "                lsPreview.classList.toggle(\"visible\");\n"
    "                return;\n"
    "            }\n"
    "            if (!confirm(\"Send \" + beatKey + \" for lip sync? Cost: ~$0.15.\\nThis submits the selected clip + TTS audio to ByteDance LipSync.\")) return;\n"
    "\n"
    "            lsBtn.disabled = true;\n"
    "            lsBtn.textContent = \"\\u23F3 Submitting...\";\n"
    "            lsBtn.className = \"mn-lipsync-btn polling\";\n"
    "            lsStat.textContent = \"Sending to ByteDance LipSync...\";\n"
    "\n"
    "            fetch(SERVER + \"/api/lipsync\", {\n"
    "                method: \"POST\",\n"
    "                headers: { \"Content-Type\": \"application/json\" },\n"
    "                body: JSON.stringify({ beat: beatKey })\n"
    "            }).then(function(resp) { return resp.json(); }).then(function(data) {\n"
    "                if (data.error) {\n"
    "                    lsBtn.disabled = false;\n"
    "                    lsBtn.textContent = \"\\u274C Retry Lip Sync\";\n"
    "                    lsBtn.className = \"mn-lipsync-btn\";\n"
    "                    lsStat.textContent = \"Error: \" + data.error;\n"
    "                    return;\n"
    "                }\n"
    "                lsBtn.textContent = \"\\u23F3 Processing (\" + (data.clip || beatKey) + \")...\";\n"
    "                lsStat.textContent = \"Submitted. Audio: \" + (data.audio || \"?\") + \". Polling for result...\";\n"
    "                startPolling(beatKey, lsBtn, lsStat, lsVideo, lsPreview);\n"
    "            }).catch(function(err) {\n"
    "                lsBtn.disabled = false;\n"
    "                lsBtn.textContent = \"\\u274C Retry Lip Sync\";\n"
    "                lsBtn.className = \"mn-lipsync-btn\";\n"
    "                lsStat.textContent = \"Network error: \" + err.message;\n"
    "            });\n"
    "        });\n"
    "\n"
    "        lsRow.appendChild(lsBtn);\n"
    "        lsRow.appendChild(lsStat);\n"
    "        parentRow.appendChild(lsRow);\n"
    "        parentRow.appendChild(lsPreview);\n"
)

A4_AFTER = (
    "        // Fix B (April 19 2026): shared submit path so the primary\n"
    "        // button and the always-available \"Re-send\" secondary link fire\n"
    "        // identical POST /api/lipsync requests. Skips the .done\n"
    "        // preview-toggle branch when called from Re-send.\n"
    "        function submitLipSync(isResend) {\n"
    "            var prompt = isResend\n"
    "                ? (\"Re-send \" + beatKey + \" for lip sync? Cost: ~$0.15.\\nThis force-submits the currently selected clip + TTS audio to ByteDance LipSync regardless of prior state.\")\n"
    "                : (\"Send \" + beatKey + \" for lip sync? Cost: ~$0.15.\\nThis submits the selected clip + TTS audio to ByteDance LipSync.\");\n"
    "            if (!confirm(prompt)) return;\n"
    "\n"
    "            lsBtn.disabled = true;\n"
    "            lsBtn.textContent = \"\\u23F3 Submitting...\";\n"
    "            lsBtn.className = \"mn-lipsync-btn polling\";\n"
    "            lsStat.textContent = \"Sending to ByteDance LipSync...\";\n"
    "\n"
    "            fetch(SERVER + \"/api/lipsync\", {\n"
    "                method: \"POST\",\n"
    "                headers: { \"Content-Type\": \"application/json\" },\n"
    "                body: JSON.stringify({ beat: beatKey })\n"
    "            }).then(function(resp) { return resp.json(); }).then(function(data) {\n"
    "                if (data.error) {\n"
    "                    lsBtn.disabled = false;\n"
    "                    lsBtn.textContent = \"\\u274C Retry Lip Sync\";\n"
    "                    lsBtn.className = \"mn-lipsync-btn\";\n"
    "                    lsStat.textContent = \"Error: \" + data.error;\n"
    "                    return;\n"
    "                }\n"
    "                lsBtn.textContent = \"\\u23F3 Processing (\" + (data.clip || beatKey) + \")...\";\n"
    "                lsStat.textContent = \"Submitted. Audio: \" + (data.audio || \"?\") + \". Polling for result...\";\n"
    "                startPolling(beatKey, lsBtn, lsStat, lsVideo, lsPreview);\n"
    "            }).catch(function(err) {\n"
    "                lsBtn.disabled = false;\n"
    "                lsBtn.textContent = \"\\u274C Retry Lip Sync\";\n"
    "                lsBtn.className = \"mn-lipsync-btn\";\n"
    "                lsStat.textContent = \"Network error: \" + err.message;\n"
    "            });\n"
    "        }\n"
    "\n"
    "        lsBtn.addEventListener(\"click\", function() {\n"
    "            if (lsBtn.disabled) return;\n"
    "            if (lsBtn.classList.contains(\"done\")) {\n"
    "                lsPreview.classList.toggle(\"visible\");\n"
    "                return;\n"
    "            }\n"
    "            submitLipSync(false);\n"
    "        });\n"
    "\n"
    "        // Fix B (April 19 2026): always-available Re-send secondary link.\n"
    "        // Smaller / lighter than the primary; never disabled by the\n"
    "        // \"done\" preview-toggle branch — always fires submitLipSync so\n"
    "        // Kim can force a fresh lipsync even when the button says Done.\n"
    "        var lsResend = document.createElement(\"a\");\n"
    "        lsResend.href = \"javascript:void(0)\";\n"
    "        lsResend.className = \"mn-lipsync-resend\";\n"
    "        lsResend.textContent = \"\\uD83D\\uDD01 Re-send\";\n"
    "        lsResend.title = \"Force re-send this beat to ByteDance LipSync, even if a completed file exists.\";\n"
    "        lsResend.style.cssText = \"margin-left:10px;font-size:11px;color:#9ab;\"\n"
    "            + \"text-decoration:underline;cursor:pointer;opacity:0.85;\"\n"
    "            + \"user-select:none;\";\n"
    "        lsResend.addEventListener(\"click\", function(ev) {\n"
    "            ev.preventDefault();\n"
    "            if (lsBtn.disabled) return;  // in-flight; wait for poll\n"
    "            submitLipSync(true);\n"
    "        });\n"
    "\n"
    "        lsRow.appendChild(lsBtn);\n"
    "        lsRow.appendChild(lsStat);\n"
    "        lsRow.appendChild(lsResend);\n"
    "        parentRow.appendChild(lsRow);\n"
    "        parentRow.appendChild(lsPreview);\n"
)

# --- A5 (Task 2 — Move to A) ------------------------------------------------
# In the options loop (multi-option branch), after the radio is appended,
# add a "🔒 Move to A" button visible only for i > 0 (Option B and C).
A5_BEFORE = (
    "                    if (isSelected) radio.checked = true;\n"
    "                    (function(beatKey, on) {\n"
    "                        radio.onchange = function() { selectBeat(beatKey, on); };\n"
    "                    })(k, optNum);\n"
    "                    optCard.appendChild(radio);\n"
    "\n"
    "                    optionsRow.appendChild(optCard);\n"
    "                });\n"
)

A5_AFTER = (
    "                    if (isSelected) radio.checked = true;\n"
    "                    (function(beatKey, on) {\n"
    "                        radio.onchange = function() { selectBeat(beatKey, on); };\n"
    "                    })(k, optNum);\n"
    "                    optCard.appendChild(radio);\n"
    "\n"
    "                    // Task 2 (April 19 2026): \"Move to A\" button, visible\n"
    "                    // only on Option B (i=1) and Option C (i=2). Posts to\n"
    "                    // /api/v2/beat/{beat_id}/swap_to_a so Kim can lock a\n"
    "                    // preferred pick into slot A and free B+C to\n"
    "                    // regenerate.\n"
    "                    if (i > 0) {\n"
    "                        var moveBtn = el(\"button\", {\n"
    "                            \"class\": \"mn-move-to-a\",\n"
    "                            \"title\": \"Move this option into slot A so it's preserved. Option A contents will swap into this slot.\",\n"
    "                            \"style\": \"margin-top:4px;padding:3px 8px;font-size:11px;\"\n"
    "                                + \"background:#2a3a4a;color:#cde;border:1px solid #456;\"\n"
    "                                + \"border-radius:4px;cursor:pointer;display:block;\"\n"
    "                        }, [\"\\uD83D\\uDD12 Move to A\"]);\n"
    "                        (function(beatKey, fromSlot, btnEl) {\n"
    "                            btnEl.addEventListener(\"click\", function(ev) {\n"
    "                                ev.preventDefault();\n"
    "                                ev.stopPropagation();\n"
    "                                if (btnEl.disabled) return;\n"
    "                                btnEl.disabled = true;\n"
    "                                var origText = btnEl.textContent;\n"
    "                                btnEl.textContent = \"\\u23F3 Swapping...\";\n"
    "                                fetch(SERVER + \"/api/v2/beat/\" + beatKey + \"/swap_to_a\", {\n"
    "                                    method: \"POST\",\n"
    "                                    headers: { \"Content-Type\": \"application/json\" },\n"
    "                                    body: JSON.stringify({ from_slot: fromSlot })\n"
    "                                }).then(function(resp) {\n"
    "                                    return resp.json().then(function(data) {\n"
    "                                        return { ok: resp.ok, status: resp.status, data: data };\n"
    "                                    });\n"
    "                                }).then(function(res) {\n"
    "                                    if (!res.ok || (res.data && res.data.error)) {\n"
    "                                        var errMsg = (res.data && res.data.error) || (\"HTTP \" + res.status);\n"
    "                                        var hint = res.data && res.data.hint ? \" — \" + res.data.hint : \"\";\n"
    "                                        if (typeof window.pathappToast === \"function\") {\n"
    "                                            window.pathappToast(\"error\", \"Move to A failed: \" + errMsg + hint);\n"
    "                                        } else {\n"
    "                                            alert(\"Move to A failed: \" + errMsg + hint);\n"
    "                                        }\n"
    "                                        btnEl.disabled = false;\n"
    "                                        btnEl.textContent = origText;\n"
    "                                        return;\n"
    "                                    }\n"
    "                                    if (typeof window.pathappToast === \"function\") {\n"
    "                                        window.pathappToast(\"saved\", \"Swapped — Option A now contains your preserved pick. B and C are free to regenerate.\");\n"
    "                                    }\n"
    "                                    if (typeof render === \"function\") render();\n"
    "                                }).catch(function(err) {\n"
    "                                    if (typeof window.pathappToast === \"function\") {\n"
    "                                        window.pathappToast(\"error\", \"Move to A network error: \" + err.message);\n"
    "                                    } else {\n"
    "                                        alert(\"Move to A network error: \" + err.message);\n"
    "                                    }\n"
    "                                    btnEl.disabled = false;\n"
    "                                    btnEl.textContent = origText;\n"
    "                                });\n"
    "                            });\n"
    "                        })(k, optNum, moveBtn);\n"
    "                        optCard.appendChild(moveBtn);\n"
    "                    }\n"
    "\n"
    "                    optionsRow.appendChild(optCard);\n"
    "                });\n"
)


def main() -> int:
    if not TARGET.is_file():
        print(f"[lipsync-ux] Target not found: {TARGET}", file=sys.stderr)
        return 2

    src = TARGET.read_text(encoding="utf-8")

    # Idempotency: if already patched, exit success.
    if _IDEM_MARKER in src:
        print("[lipsync-ux] Already patched (idempotency marker found); "
              "nothing to do.")
        return 0

    # Pre-patch SHA of all base64 images.
    pre_hash, pre_n = _sha256_sorted_b64(src)
    print(f"[lipsync-ux] Pre-patch base64 count={pre_n} "
          f"SHA256={pre_hash[:16]}")
    if pre_n != 22:
        print(f"[lipsync-ux] WARN: expected 22 base64 images, found {pre_n}. "
              f"Proceeding but verify output.")

    # Pre-patch script-tag count.
    pre_scripts = src.count("<script")

    # Apply anchors in order. Each must be unique before replacement.
    _assert_single(src, A1_BEFORE, "A1: applyCompletedButtonState header")
    src = src.replace(A1_BEFORE, A1_AFTER)

    _assert_single(src, A2_BEFORE, "A2: createLipSyncRow polling branch")
    src = src.replace(A2_BEFORE, A2_AFTER)

    _assert_single(src, A3_BEFORE, "A3: startPolling processing branch")
    src = src.replace(A3_BEFORE, A3_AFTER)

    _assert_single(src, A4_BEFORE, "A4: createLipSyncRow submit handler")
    src = src.replace(A4_BEFORE, A4_AFTER)

    _assert_single(src, A5_BEFORE, "A5: options loop radio append")
    src = src.replace(A5_BEFORE, A5_AFTER)

    # Post-patch SHA check (base64 images must be byte-identical).
    post_hash, post_n = _sha256_sorted_b64(src)
    if pre_hash != post_hash or pre_n != post_n:
        raise SystemExit(
            f"[lipsync-ux] FATAL base64 image integrity broken: "
            f"pre={pre_hash[:16]}({pre_n}) post={post_hash[:16]}({post_n}). "
            f"Aborted without write.",
        )
    print(f"[lipsync-ux] Post-patch base64 count={post_n} "
          f"SHA256={post_hash[:16]} (MATCH)")

    # Script-tag count sanity — we must NOT have added any <script> tags.
    post_scripts = src.count("<script")
    if pre_scripts != post_scripts:
        raise SystemExit(
            f"[lipsync-ux] FATAL script tag count changed: "
            f"{pre_scripts} -> {post_scripts}",
        )
    print(f"[lipsync-ux] Script tag count unchanged ({pre_scripts}).")

    # Node syntax check on concatenated script bodies.
    _node_check(src)

    # Backup BEFORE write.
    ts = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup = TARGET.with_name(
        TARGET.name + f".bak_lipsync_ux_and_swap_{ts}",
    )
    shutil.copy2(TARGET, backup)
    print(f"[lipsync-ux] Backup: {backup}")

    # Write.
    TARGET.write_text(src, encoding="utf-8")
    print(f"[lipsync-ux] Patched {TARGET} (size {len(src)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
