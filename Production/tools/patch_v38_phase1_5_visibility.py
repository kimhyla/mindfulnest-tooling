#!/usr/bin/env python3
"""
Phase 1.5 visibility fix — Path B (JS-only) patcher.

Adds a fixed-position toast notification to storyboard_v38_prod.html so every
pathappPatch state transition (saving / saved / error) is unmissably visible
in the top-right corner.

Discipline (Rule 7 Path B — behavior-only):
  1. Read HTML as text.
  2. Assert injection anchors are unique.
  3. String-replace CSS before the terminal </style>.
  4. String-replace a new <script> block before </body></html>.
  5. Extract all base64 data URIs before + after; SHA256 must match byte-for-byte.
  6. Write timestamped backup BEFORE overwriting.
  7. Static checks + /api/v2/beat curl test + production_state.json sanity.

This patcher does NOT rebuild. It does NOT touch images. It does NOT regenerate
HTML. It surgically inserts two string blocks and verifies pixel data is
untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Absolute paths — we never assume cwd (Rule 7 + Rule 3).
PROJECT_ROOT = Path(
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
)
HTML_PATH = PROJECT_ROOT / "Production" / "Event_1" / "storyboard_v38_prod.html"
STATE_PATH = PROJECT_ROOT / "Production" / "Event_1" / "production_state.json"
TOOLS_LIB = PROJECT_ROOT / "Production" / "tools"

sys.path.insert(0, str(TOOLS_LIB))

# ------------------------------------------------------------------
# CSS block — appended INSIDE the final </style>.
# ------------------------------------------------------------------
CSS_BLOCK = """
  /* Phase 1.5 visibility fix — fixed-position toast (2026-04-18) */
  .pathapp-toast {
    position: fixed; top: 80px; right: 20px; z-index: 99999;
    padding: 10px 16px; border-radius: 6px; font-size: 14px;
    font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3); pointer-events: none;
    opacity: 0; transform: translateX(20px); transition: opacity 0.2s, transform 0.2s;
    color: #fff;
  }
  .pathapp-toast.visible { opacity: 1; transform: translateX(0); }
  .pathapp-toast.saving  { background: #d4a017; }
  .pathapp-toast.saved   { background: #27ae60; }
  .pathapp-toast.error   { background: #e74c3c; }
"""

# The anchor string must be unique. The terminal </style> at line 2014 is the
# only </style> that directly follows the `.pathapp-saveind.error` rule block.
# We anchor on that multi-line context so the replace is unambiguous even
# though `</style>` itself appears 4 times in the file.
CSS_ANCHOR = """  .pathapp-saveind.error {
    /* solid red, no pulse — keep eye on it until user acts */
    animation: none;
  }
</style>"""

CSS_REPLACEMENT = (
    """  .pathapp-saveind.error {
    /* solid red, no pulse — keep eye on it until user acts */
    animation: none;
  }
"""
    + CSS_BLOCK
    + "</style>"
)

# ------------------------------------------------------------------
# JS block — prepended before the terminal </body></html>.
# ------------------------------------------------------------------
TOAST_SCRIPT = """<script>
(function() {
  /* Phase 1.5 visibility fix — wrap pathappSetSaveInd with a toast alongside.
     Does NOT replace the inline save-ind span; the toast is purely additive. */
  var _toastEl = null;
  var _toastHideTimer = null;
  function _ensureToast() {
    if (_toastEl) return _toastEl;
    _toastEl = document.createElement("div");
    _toastEl.className = "pathapp-toast";
    _toastEl.setAttribute("role", "status");
    _toastEl.setAttribute("aria-live", "polite");
    document.body.appendChild(_toastEl);
    return _toastEl;
  }
  function _showToast(state, msg) {
    var el = _ensureToast();
    el.className = "pathapp-toast " + state + " visible";
    el.textContent = msg;
    if (_toastHideTimer) clearTimeout(_toastHideTimer);
    var durationMs = state === "error" ? 6000 : (state === "saved" ? 2500 : 0);
    if (durationMs > 0) {
      _toastHideTimer = setTimeout(function() {
        el.className = "pathapp-toast " + state;  /* drop .visible */
      }, durationMs);
    }
  }
  window.pathappToast = _showToast;
  // Monkey-patch pathappSetSaveInd so toast fires alongside every span update.
  var _origSet = window.pathappSetSaveInd;
  if (typeof _origSet === "function") {
    window.pathappSetSaveInd = function(span, state, msg) {
      _origSet(span, state, msg);
      var label = state === "saving" ? "\\u23F3 Saving\\u2026"
                : state === "saved"  ? "\\u2713 Saved"
                : state === "error"  ? "\\u26A0\\uFE0E Error: " + (msg || "unknown")
                : msg || state;
      _showToast(state, label);
    };
  }
  console.log("[phase1.5-viz] toast installed");
})();
</script>
</body></html>"""

BODY_ANCHOR = "</body></html>"


# ------------------------------------------------------------------
# Helpers.
# ------------------------------------------------------------------

def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _base64_uri_sha(html: str) -> str:
    """SHA256 of the sorted concatenation of every base64 data URI in the file.

    Any image or audio mutation shifts this hash; a behavior-only patch must
    leave it untouched.
    """
    # data:<mime>;base64,<payload>[...]   — payload ends at first quote or )
    pattern = re.compile(r'data:[^;,\s"]+;base64,([A-Za-z0-9+/=]+)')
    payloads = sorted(m.group(1) for m in pattern.finditer(html))
    digest = hashlib.sha256()
    for p in payloads:
        digest.update(p.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest() + f"  (n={len(payloads)})"


def _assert_unique(text: str, needle: str, label: str) -> None:
    count = text.count(needle)
    if count != 1:
        raise SystemExit(
            f"ABORT: expected exactly 1 occurrence of {label}, found {count}."
        )


def _one_body_close_near_tail(text: str) -> None:
    tail_start = max(0, len(text) - 8000)
    tail = text[tail_start:]
    count = tail.count("</body>")
    if count != 1:
        raise SystemExit(
            f"ABORT: expected exactly 1 </body> in final 200 lines, found {count}."
        )


def _static_checks(patched: str) -> dict:
    checks = {
        "pathapp-toast occurrences (>=4 expected)": patched.count("pathapp-toast"),
        "window.pathappToast occurrences (1 expected)": patched.count("window.pathappToast"),
        "_origSet(span, state, msg) occurrences (1 expected)": patched.count(
            "_origSet(span, state, msg)"
        ),
    }
    errors = []
    if checks["pathapp-toast occurrences (>=4 expected)"] < 4:
        errors.append("pathapp-toast count < 4")
    if checks["window.pathappToast occurrences (1 expected)"] != 1:
        errors.append("window.pathappToast count != 1")
    if checks["_origSet(span, state, msg) occurrences (1 expected)"] != 1:
        errors.append("_origSet(...) count != 1")
    checks["_errors"] = errors
    return checks


def _curl_test() -> dict:
    """POST a tiny patch to /api/v2/beat/beat_99_test/patch and verify applied."""
    import urllib.request
    import urllib.error

    body = json.dumps({"field": "dialogue", "value": "viz test"}).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:5111/api/v2/beat/beat_99_test/patch",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw)
            return {
                "http_status": resp.status,
                "status_field": parsed.get("status"),
                "raw": raw[:500],
            }
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")[:500]
        return {"http_status": e.code, "status_field": None, "raw": raw}
    except Exception as e:
        return {"http_status": None, "status_field": None, "raw": f"EXC {e!r}"}


def _state_sanity() -> dict:
    size = STATE_PATH.stat().st_size
    try:
        with STATE_PATH.open("r") as fh:
            json.load(fh)
        valid = True
        err = None
    except Exception as e:
        valid = False
        err = repr(e)
    return {"size_bytes": size, "valid_json": valid, "error": err}


# ------------------------------------------------------------------
# Main patch flow.
# ------------------------------------------------------------------

def main() -> int:
    print(f"[phase1.5-viz] Reading: {HTML_PATH}")
    original = HTML_PATH.read_text(encoding="utf-8")
    original_size = len(original)

    # Anchor sanity.
    _assert_unique(original, CSS_ANCHOR, "CSS anchor (terminal </style> after pulse block)")
    _assert_unique(original, BODY_ANCHOR, "</body></html>")
    _one_body_close_near_tail(original)

    # Belt and suspenders: refuse to double-patch.
    if "pathapp-toast" in original:
        raise SystemExit(
            "ABORT: pathapp-toast already present in file — refusing to double-patch."
        )

    # Base64 SHA before.
    sha_before = _base64_uri_sha(original)
    print(f"[phase1.5-viz] base64 SHA before: {sha_before}")

    # Apply patches.
    patched = original.replace(CSS_ANCHOR, CSS_REPLACEMENT, 1)
    if patched == original:
        raise SystemExit("ABORT: CSS replace was a no-op.")
    patched = patched.replace(BODY_ANCHOR, TOAST_SCRIPT, 1)
    if BODY_ANCHOR not in patched:
        raise SystemExit("ABORT: </body></html> missing after script injection.")

    # Base64 SHA after — must be identical.
    sha_after = _base64_uri_sha(patched)
    print(f"[phase1.5-viz] base64 SHA after:  {sha_after}")
    if sha_before != sha_after:
        raise SystemExit(
            "ABORT: base64 payload hash changed — pixel data was mutated. "
            "Not writing output. Backup not created."
        )

    # Static checks on the patched string (before committing to disk).
    static_pre = _static_checks(patched)
    print(f"[phase1.5-viz] static checks (in-memory): {static_pre}")
    if static_pre.get("_errors"):
        raise SystemExit(f"ABORT: static checks failed: {static_pre['_errors']}")

    # Backup BEFORE overwriting.
    ts = _utc_ts()
    backup_path = HTML_PATH.with_name(
        f"{HTML_PATH.name}.bak_phase1_5_viz_{ts}"
    )
    print(f"[phase1.5-viz] Writing backup: {backup_path}")
    shutil.copy2(HTML_PATH, backup_path)

    # Write patched file.
    HTML_PATH.write_text(patched, encoding="utf-8")
    new_size = len(patched)
    print(
        f"[phase1.5-viz] Wrote {HTML_PATH}  "
        f"({original_size:,} -> {new_size:,} bytes, +{new_size - original_size:,})"
    )

    # Re-read from disk and re-run checks, to catch any encoding surprises.
    redisk = HTML_PATH.read_text(encoding="utf-8")
    static_post = _static_checks(redisk)
    print(f"[phase1.5-viz] static checks (on-disk): {static_post}")
    if static_post.get("_errors"):
        # Restore and abort.
        shutil.copy2(backup_path, HTML_PATH)
        raise SystemExit(
            f"ABORT: on-disk static checks failed after write: {static_post['_errors']} — restored from backup."
        )

    # Curl smoke test against v2 patch endpoint.
    curl = _curl_test()
    print(f"[phase1.5-viz] curl /api/v2/beat/beat_99_test/patch: {curl}")
    if curl.get("status_field") != "applied":
        # Restore and abort.
        shutil.copy2(backup_path, HTML_PATH)
        raise SystemExit(
            f"ABORT: v2 patch endpoint did NOT return status=applied — restored from backup."
        )

    # production_state.json sanity.
    state = _state_sanity()
    print(f"[phase1.5-viz] production_state.json sanity: {state}")
    if not state["valid_json"] or state["size_bytes"] <= 10_000:
        shutil.copy2(backup_path, HTML_PATH)
        raise SystemExit(
            f"ABORT: production_state.json failed sanity — restored HTML from backup."
        )

    # Summary ledger (human-readable).
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "file": str(HTML_PATH),
        "backup": str(backup_path),
        "original_size_bytes": original_size,
        "patched_size_bytes": new_size,
        "base64_sha_before": sha_before,
        "base64_sha_after": sha_after,
        "base64_identical": sha_before == sha_after,
        "static_checks_ondisk": static_post,
        "curl_test": curl,
        "state_sanity": state,
    }
    print("\n[phase1.5-viz] SUMMARY:")
    print(json.dumps(summary, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
