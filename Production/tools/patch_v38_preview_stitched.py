#!/usr/bin/env python3
"""LD-285 Preview-Stitched v2 patcher for storyboard_v38_prod.html.

Cloned from patch_v38_tier3_widgets.py (proven 3-shipped Path B template).
All Rule 7 Path B invariants enforced:
  * String-replacement patches against single-match anchors (no regex on
    HTML structure).
  * Base64 image data URIs SHA256'd pre + post; mismatch = abort + restore.
  * Backup written BEFORE patched output.
  * Post-patch sanity: </body> / </html> count unchanged, +1 <script> open
    tag (the new support block).
  * node --check on extracted scripts when node is on PATH.

Surgical edits:
  E1  preview-stitched bar appended into mount() before progressWrap.
  E2  pathappPatch fetch URL: route beatId === null to /api/v2/module/patch.
  E3  Tier "preview-stitched" support script appended at EOF (slider + button
      handlers, snapshot-on-start fetch, mp4 stream play, hydrate on load).
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

# --------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------
# Derive PROJECT_ROOT from this file's location instead of hardcoding so the
# patcher survives a project move (Phase 3 counter FAIL-1 fix; the cloned
# template patch_v38_tier3_widgets.py has the same hardcode latent — flagged
# for separate cleanup).
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGET = PROJECT_ROOT / "Production" / "Event_1" / "storyboard_v38_prod.html"

# --------------------------------------------------------------------
# Helpers (mirrors patch_v38_tier3_widgets.py)
# --------------------------------------------------------------------
_B64_IMG_RE = re.compile(r"data:image/[a-zA-Z.+-]+;base64,[A-Za-z0-9+/=]+")


def _sha256_of_sorted_b64_uris(src: str) -> tuple[str, int]:
    uris = sorted(_B64_IMG_RE.findall(src))
    joined = "\n".join(uris).encode("utf-8")
    return hashlib.sha256(joined).hexdigest(), len(uris)


def _assert_single_match(hay: str, needle: str, label: str) -> None:
    count = hay.count(needle)
    if count != 1:
        raise SystemExit(
            f"[preview-stitched-patcher] FATAL single-match assertion failed "
            f"for {label!r}: found {count} occurrences, expected exactly 1."
        )


def _node_syntax_check_scripts(src: str) -> None:
    if shutil.which("node") is None:
        print("[preview-stitched-patcher] WARN: node not on PATH; skipping syntax check.")
        return
    bodies = re.findall(r"<script[^>]*>(.*?)</script>", src, flags=re.DOTALL)
    if not bodies:
        print("[preview-stitched-patcher] WARN: no <script> bodies; skipping syntax check.")
        return
    concat = "\n;\n".join(bodies)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8",
    ) as tf:
        tf.write(concat)
        tmpname = tf.name
    try:
        result = subprocess.run(
            ["node", "--check", tmpname],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise SystemExit(
                "[preview-stitched-patcher] FATAL node --check failed:\n"
                f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            )
        print("[preview-stitched-patcher] node --check: OK")
    finally:
        os.unlink(tmpname)


# --------------------------------------------------------------------
# E1 — Inject preview-stitched bar into mount() before progressWrap.
# Anchor (line 651 in v38): `        root.appendChild(progressWrap);`
# We prepend `root.appendChild(previewBar);` immediately before, plus the
# preview bar construction. JS uses the existing `el(tag, attrs, kids)` helper
# (defined at the same scope, line 604).
# --------------------------------------------------------------------
E1_OLD = '        root.appendChild(progressWrap);\n'
E1_NEW = (
    '        var previewBar = el("div", {"class": "mn-preview-stitched-bar"}, [\n'
    '            el("label", {"for": "fade-beats-slider"}, ["Fade between beats: "]),\n'
    '            el("input", {\n'
    '                type: "range", id: "fade-beats-slider",\n'
    '                min: "0", max: "500", step: "50", value: "200",\n'
    '                "data-fade-pending": "false",\n'
    '            }),\n'
    '            el("span", {id: "fade-beats-label"}, ["200ms"]),\n'
    '            el("button", {id: "preview-stitched-btn", "class": "mn-secondary"}, ["\u25B6 Preview All Stitched"]),\n'
    '            el("span", {id: "fade-beats-saveind", "class": "save-ind pathapp-saveind"}, [""]),\n'
    '        ]);\n'
    '        var previewPlayer = el("video", {\n'
    '            id: "preview-stitched-player",\n'
    '            style: "display:none; max-width:100%; margin-top:8px;",\n'
    '            controls: "controls", preload: "metadata",\n'
    '        });\n'
    '        root.appendChild(previewBar);\n'
    '        root.appendChild(previewPlayer);\n'
    '        root.appendChild(progressWrap);\n'
)

# --------------------------------------------------------------------
# E2 — pathappPatch URL branch (counter (a) preflight 93 spec):
#   beatId === null  -> /api/v2/module/patch
#   beatId !== null  -> /api/v2/beat/<id>/patch  (existing)
# Anchor: the await fetch line at storyboard line 1899.
# --------------------------------------------------------------------
E2_OLD = (
    '      var resp = await fetch(SERVER_V2 + "/api/v2/beat/" + beatId + "/patch", {\n'
    '        method: "POST",\n'
    '        headers: {"Content-Type": "application/json"},\n'
    '        body: JSON.stringify(body),\n'
    '      });\n'
)
E2_NEW = (
    '      // LD-285 Preview Stitched v2: null beatId => module-level patch.\n'
    '      var __pathappUrl = (beatId === null)\n'
    '        ? SERVER_V2 + "/api/v2/module/patch"\n'
    '        : SERVER_V2 + "/api/v2/beat/" + beatId + "/patch";\n'
    '      // For module patches, drop expected_version + mutation_id (server\n'
    '      // does not version module-level fields per-beat).\n'
    '      var __pathappBody = (beatId === null)\n'
    '        ? {field: field, value: value}\n'
    '        : body;\n'
    '      var resp = await fetch(__pathappUrl, {\n'
    '        method: "POST",\n'
    '        headers: {"Content-Type": "application/json"},\n'
    '        body: JSON.stringify(__pathappBody),\n'
    '      });\n'
)

# --------------------------------------------------------------------
# E3 — preview-stitched support script appended just before </body></html>.
# Implements the slider debounce + button click handler with snapshot-on-start.
# Counter (j) LOW/MED: state fetch happens IMMEDIATELY before the POST so the
# snapshot is the freshest possible read.
# --------------------------------------------------------------------
PREVIEW_STITCHED_SCRIPT = """
<!-- BEGIN LD-285 Preview-Stitched v2 (injected by patch_v38_preview_stitched.py) -->
<style>
  .mn-preview-stitched-bar {
    display: flex; align-items: center; gap: 8px;
    padding: 6px 8px; margin: 4px 0;
    background: #1c2030; border-radius: 6px; font-size: 12px;
  }
  .mn-preview-stitched-bar label { color: #c9d1d9; }
  .mn-preview-stitched-bar input[type="range"] { width: 160px; }
  .mn-preview-stitched-bar #fade-beats-label {
    color: #8b949e; min-width: 48px; text-align: right;
  }
  #preview-stitched-btn { margin-left: 4px; }
  #preview-stitched-player { display: none; max-width: 100%; }
</style>
<script>
(function() {
  var SERVER_V2 = "http://localhost:5111";
  function $(id) { return document.getElementById(id); }

  function init() {
    var slider = $("fade-beats-slider");
    var label  = $("fade-beats-label");
    var btn    = $("preview-stitched-btn");
    var player = $("preview-stitched-player");
    if (!slider || !btn || !player) {
      // mount() hasn't run yet — try again next tick.
      return setTimeout(init, 50);
    }

    // Hydrate from current state.
    fetch(SERVER_V2 + "/api/state", {cache: "no-store"})
      .then(function(r) { return r.ok ? r.json() : null; })
      .then(function(state) {
        if (!state) return;
        var v = state.fade_between_beats_ms;
        if (typeof v === "number" && !isNaN(v)) {
          slider.value = String(v);
          label.textContent = String(v) + "ms";
        }
      })
      .catch(function() { /* keep default */ });

    // Debounced save on slider input — uses existing pathappPatch with null
    // beatId (E2 branch) so we get the same save-ind / toast feedback.
    var debounceTimer = null;
    slider.addEventListener("input", function(e) {
      var v = parseInt(e.target.value, 10);
      label.textContent = String(v) + "ms";
      slider.setAttribute("data-fade-pending", "true");
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function() {
        if (typeof window.pathappPatch !== "function") {
          slider.setAttribute("data-fade-pending", "false");
          return;
        }
        window.pathappPatch(null, "fade_between_beats_ms", v, {
          saveind: $("fade-beats-saveind"),
        }).then(function() {
          slider.setAttribute("data-fade-pending", "false");
        }).catch(function() {
          slider.setAttribute("data-fade-pending", "false");
        });
      }, 300);
    });

    // Preview button: snapshot-on-start, stream blob URL into <video>.
    btn.addEventListener("click", async function() {
      // P07 double-fire protection: disable immediately.
      if (btn.disabled) return;
      // Wait for any pending fade-save to settle so the server's snapshot
      // and the URL the user is about to see actually match.
      if (slider.getAttribute("data-fade-pending") === "true") {
        if (typeof window.pathappToast === "function") {
          window.pathappToast("saving", "Saving fade...");
        }
        await new Promise(function(r) { setTimeout(r, 400); });
      }
      btn.disabled = true;
      var oldText = btn.textContent;
      btn.textContent = "\u23F3 Generating...";
      try {
        // Counter (j): fetch state AS LATE AS POSSIBLE before POST.
        var stateResp = await fetch(SERVER_V2 + "/api/state", {cache: "no-store"});
        if (!stateResp.ok) throw new Error("state fetch HTTP " + stateResp.status);
        var snapshot = await stateResp.json();
        var resp = await fetch(SERVER_V2 + "/api/preview_stitched", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            state_snapshot: snapshot,
            fade_between_beats_ms: parseInt(slider.value, 10),
          }),
        });
        if (!resp.ok) {
          var errBody = null;
          try { errBody = await resp.json(); } catch (_) {}
          var hint = (errBody && (errBody.hint || errBody.error)) || ("HTTP " + resp.status);
          if (typeof window.pathappToast === "function") {
            window.pathappToast("error", "Preview failed: " + hint);
          } else {
            alert("Preview failed: " + hint);
          }
          return;
        }
        var blob = await resp.blob();
        // Revoke any prior URL to avoid memory leak across multiple plays.
        if (player.dataset.lastUrl) {
          try { URL.revokeObjectURL(player.dataset.lastUrl); } catch (_) {}
        }
        var url = URL.createObjectURL(blob);
        player.dataset.lastUrl = url;
        player.src = url;
        player.style.display = "block";
        try { await player.play(); } catch (_) { /* user must click play */ }
      } catch (err) {
        if (typeof window.pathappToast === "function") {
          window.pathappToast("error", "Preview error: " + (err && err.message || err));
        } else {
          console.warn("[preview-stitched]", err);
        }
      } finally {
        btn.disabled = false;
        btn.textContent = oldText;
      }
    });

    console.log("[preview-stitched] LD-285 v2 wired");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
</script>
<!-- END LD-285 Preview-Stitched v2 -->
"""

E3_OLD = "</body></html>"
E3_NEW = PREVIEW_STITCHED_SCRIPT.rstrip("\n") + "\n</body></html>"


# --------------------------------------------------------------------
# Main
# --------------------------------------------------------------------
def main() -> int:
    if not TARGET.exists():
        print(f"[preview-stitched-patcher] FATAL target not found: {TARGET}", file=sys.stderr)
        return 2

    print(f"[preview-stitched-patcher] reading {TARGET}")
    src = TARGET.read_text(encoding="utf-8")

    pre_sha, pre_n = _sha256_of_sorted_b64_uris(src)
    print(f"[preview-stitched-patcher] pre-patch base64 URIs: {pre_n}  sha256={pre_sha}")

    # Idempotency / re-run protection: if the support script is already there,
    # bail with a clear message rather than corrupting the file.
    if "<!-- BEGIN LD-285 Preview-Stitched v2" in src:
        print(
            "[preview-stitched-patcher] support script ALREADY present — "
            "patch already applied. Restore from .bak before re-running."
        )
        return 1

    edits = [
        ("E1 mount() preview-stitched bar", E1_OLD, E1_NEW),
        ("E2 pathappPatch URL branch", E2_OLD, E2_NEW),
        ("E3 EOF support script", E3_OLD, E3_NEW),
    ]

    patched = src
    for label, old, new in edits:
        _assert_single_match(patched, old, label)
        patched = patched.replace(old, new)
        print(f"[preview-stitched-patcher] applied: {label}")

    # Rule 7 Path B guard: base64 byte-identical
    post_sha, post_n = _sha256_of_sorted_b64_uris(patched)
    print(f"[preview-stitched-patcher] post-patch base64 URIs: {post_n}  sha256={post_sha}")
    if (pre_sha, pre_n) != (post_sha, post_n):
        raise SystemExit(
            "[preview-stitched-patcher] FATAL base64 SHA256 mismatch — aborting "
            "without writing. Rule 7 Path B invariant violated."
        )
    print("[preview-stitched-patcher] base64 byte-identical: OK")

    # HTML structural sanity
    for needle in ("</body>", "</html>"):
        if patched.count(needle) != src.count(needle):
            raise SystemExit(
                f"[preview-stitched-patcher] FATAL {needle!r} count changed "
                f"({src.count(needle)} -> {patched.count(needle)})"
            )
    expected_delta = 1  # E3 adds one <script> open
    src_open = src.count("<script>") + src.count("<script ")
    post_open = patched.count("<script>") + patched.count("<script ")
    if post_open - src_open != expected_delta:
        raise SystemExit(
            f"[preview-stitched-patcher] FATAL <script> open delta unexpected: "
            f"pre={src_open} post={post_open}"
        )

    # Node syntax check (warn-only if node not on PATH)
    _node_syntax_check_scripts(patched)

    # Backup before write
    ts = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    bak = TARGET.with_suffix(TARGET.suffix + f".bak_preview_stitched_{ts}")
    shutil.copy2(TARGET, bak)
    print(f"[preview-stitched-patcher] backup: {bak.name}")

    # Write
    TARGET.write_text(patched, encoding="utf-8")
    print(
        f"[preview-stitched-patcher] wrote {TARGET} "
        f"({len(patched):,} bytes; pre {len(src):,}; delta +{len(patched)-len(src)})"
    )

    # Post-write static presence
    post = TARGET.read_text(encoding="utf-8")
    static_checks = [
        ("mn-preview-stitched-bar", 2, ">=", "E1 preview bar class (CSS + DOM)"),
        ("preview-stitched-btn",    2, ">=", "E1 preview button id (CSS or both DOMs)"),
        ("fade-beats-slider",       2, ">=", "E1 slider id (DOM + JS getElementById)"),
        ("/api/v2/module/patch",    1, ">=", "E2 module patch URL"),
        ("/api/preview_stitched",   1, ">=", "E3 preview stitched POST"),
        ("LD-285 Preview-Stitched", 2, ">=", "E3 BEGIN/END markers"),
    ]
    for needle, threshold, op, label in static_checks:
        c = post.count(needle)
        ok = (c >= threshold) if op == ">=" else (c == threshold)
        flag = "OK" if ok else "FAIL"
        print(
            f"[preview-stitched-patcher] static {flag}: {label} "
            f"({c} {op} {threshold})"
        )
        if not ok:
            raise SystemExit(
                f"[preview-stitched-patcher] FATAL static check failed: {label}"
            )

    print("[preview-stitched-patcher] all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
