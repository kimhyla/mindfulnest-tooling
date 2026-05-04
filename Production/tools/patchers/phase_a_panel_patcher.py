"""
phase_a_panel_patcher.py — Path B JS-only patch for Phase A panel build.

Wires:
  1. The existing Phase A "Regen Audio" button (already calls
     POST /api/phase_b/regen_audio with {phase: "a", script: ...} —
     verified at storyboard_v38_prod.html:3097-3131) is left UNCHANGED.
  2. NEW persistent voice-setting sliders (stability / similarity_boost /
     style) injected ONLY into the Phase A panel. Sliders PATCH
     prod_voice_profiles id=2 (Chipper) via the new server route
     POST /api/voice/profile_update on debounced change. Hydrate from
     GET /api/voice/profile/2 on panel mount.

Per HANDOFF_PHASE_A_STORYBOARD_PANEL_20260420.md tightened scope (Kim
locked 2026-04-20). Governing LDs read in full per Rule 16:
  • LD-302 ARCH_V3_PHASE_B_A_SYNTHESIS_20260419  (panel-as-extension)
  • LD-303 PREVIEW_STITCHED_V3_SHIPPED_20260419  (prior panel ship)
  • LD-349 PHASE_A_GUIDE_BIRD_DEMOS_ARC_1_V1     (Chipper demos)
  • LD-350 PHASE_A_NO_FIXED_DURATION_CEILING_V1  (no runtime cap)
  • LD-280 RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1  (production-only TTS)
  • LD-183 LORE_UPDATE_WIZARD_BIRD_RENAME_20260417  (Chipper canonical)

Discipline (CLAUDE.md Rule 7 Path B):
  • Sentinel-anchored injection: PHASE_A_PANEL_PATCH_{START,END}
  • SHA256 base64 image manifest: byte-identical pre/post (22 URIs expected)
  • Node syntax check on the injected <script> block before deploy
  • Atomic os.replace; timestamped .bak_phase_a_panel_<TS> with 10-file prune
  • Idempotent: aborts on second run unless --force-replace

Phase 0 (4+4 advocate/counter) gates resolved:
  C1 — id mix-up: hardcoded PROFILE_ID=2 in JS + server-side guard {1,2,3}
       white-list with Kim-friendly read-back ("Updated Chipper voice").
  C2 — phase param: verified `/api/phase_b/regen_audio` branches on phase
       (production_server.py:7401-7524). No clobber risk.
  C3 — slider PATCH storm: 250ms trailing-edge debounce per slider; PATCH
       on `change` (pointerup), not `input`.
  C4 — re-patch: sentinel idempotency check; --force-replace excises
       sentinel-to-sentinel block and re-inserts.

Usage:
  python3 phase_a_panel_patcher.py [--dry-run] [--force-replace]
                                    [--target <html_path>]

Default target:
  Production/Event_1/storyboard_v38_prod.html
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TARGET = REPO_ROOT / "Production" / "Event_1" / "storyboard_v38_prod.html"

SENTINEL_START = "/* PHASE_A_PANEL_PATCH_START v2 (sliders+qa) */"
SENTINEL_END = "/* PHASE_A_PANEL_PATCH_END v2 */"
# v1 sentinels also recognized for excise — for clean upgrade from the
# initial ship to the QA-counter-fix version.
SENTINEL_START_V1 = "/* PHASE_A_PANEL_PATCH_START v1 (sliders) */"
SENTINEL_END_V1 = "/* PHASE_A_PANEL_PATCH_END v1 */"

# Anchor: the patch is injected immediately before the closing </body></html>
# (after the existing LD V3 phase panels script block).
INJECT_ANCHOR_RE = re.compile(r"</body>\s*</html>\s*$", re.IGNORECASE)

BASE64_IMG_RE = re.compile(r"data:image/[a-zA-Z0-9.+-]+;base64,([A-Za-z0-9+/=]+)")

PATCH_BLOCK = """\
<!-- """ + SENTINEL_START + """ -->
<script>
""" + SENTINEL_START + """
(function() {
  // Phase A voice-settings sliders. Persistent: writes to
  // prod_voice_profiles id=2 (Chipper) via /api/voice/profile_update.
  // Kim locked persistent semantics (option A) 2026-04-20.
  var SERVER_V2 = "http://localhost:5111";
  var PROFILE_ID = 2;            // Chipper. NEVER change without Kim approval.
  var PROFILE_NAME = "Chipper";  // Read-back label.
  var DEBOUNCE_MS = 250;
  var FIELDS = ["stability", "similarity_boost", "style"];
  // F1 fix: track hydration. PATCH is BLOCKED until first successful
  // hydrate, so a 5xx blip can't trigger silent zero-out destruction
  // of Chipper's persisted settings on first slider interaction.
  var __hydrated = false;
  var __hydrateAttempts = 0;
  var __hydrateMaxAttempts = 5;

  function $(id) { return document.getElementById(id); }

  function debounce(fn, ms) {
    var t = null;
    return function() {
      var args = arguments, self = this;
      if (t) clearTimeout(t);
      t = setTimeout(function(){ fn.apply(self, args); }, ms);
    };
  }

  function setStatus(text, color) {
    var el = $("phase-a-voice-status");
    if (!el) return;
    el.textContent = text || "";
    el.style.color = color || "#8b949e";
    if (text && color !== "#f85149") {
      setTimeout(function(){
        if (el.textContent === text) { el.textContent = ""; }
      }, 3000);
    }
  }

  function setSlidersDisabled(disabled) {
    for (var i=0; i<FIELDS.length; i++) {
      var s = $("phase-a-voice-" + FIELDS[i]);
      if (s) {
        s.disabled = disabled;
        s.style.opacity = disabled ? "0.4" : "1.0";
      }
    }
  }

  function buildSliderRow(field, labelText) {
    var wrap = document.createElement("div");
    wrap.className = "mn-phase-row";
    wrap.style.cssText = "display:flex;align-items:center;gap:8px;margin:4px 0;";

    var lbl = document.createElement("label");
    lbl.textContent = labelText;
    lbl.style.cssText = "min-width:120px;font-size:12px;color:#c9d1d9;";
    lbl.htmlFor = "phase-a-voice-" + field;

    var slider = document.createElement("input");
    slider.type = "range";
    slider.min = "0";
    slider.max = "1";
    slider.step = "0.01";
    slider.id = "phase-a-voice-" + field;
    slider.disabled = true;  // F1 fix: disabled until first successful hydrate
    slider.style.cssText = "flex:1;accent-color:#9370b8;opacity:0.4;";

    var val = document.createElement("span");
    val.id = "phase-a-voice-" + field + "-val";
    val.style.cssText = "min-width:42px;font-family:ui-monospace,monospace;font-size:12px;color:#58a6ff;text-align:right;";
    val.textContent = "—";

    // Live value display (cheap, no PATCH).
    slider.addEventListener("input", function() {
      val.textContent = parseFloat(slider.value).toFixed(2);
    });
    // Debounced PATCH only on change (pointerup).
    slider.addEventListener("change", debouncedSave);

    wrap.appendChild(lbl);
    wrap.appendChild(slider);
    wrap.appendChild(val);
    return wrap;
  }

  function readSliders() {
    var out = {id: PROFILE_ID};
    for (var i=0; i<FIELDS.length; i++) {
      var f = FIELDS[i];
      var s = $("phase-a-voice-" + f);
      if (s) out[f] = parseFloat(s.value);
    }
    return out;
  }

  function writeSliders(profile) {
    // F6 fix: client display 2 decimals (matches step=0.01 + server
    // round(2)); avoids destroying any 3+ decimal historical values
    // Kim retunes via Directus UI directly. Server round() now matches.
    for (var i=0; i<FIELDS.length; i++) {
      var f = FIELDS[i];
      var s = $("phase-a-voice-" + f);
      var v = $("phase-a-voice-" + f + "-val");
      var raw = profile && profile[f];
      // F1 fix: if the field is null/missing, leave the value display
      // dim and the slider at its DOM default but DO NOT enable
      // interaction for that specific field. Treat null as unknown,
      // never as 0.
      if (raw == null || isNaN(parseFloat(raw))) {
        if (s) { s.disabled = true; s.style.opacity = "0.4"; }
        if (v) v.textContent = "—";
        continue;
      }
      var num = parseFloat(raw);
      if (s) {
        s.value = num.toFixed(2);
        s.disabled = false;
        s.style.opacity = "1.0";
      }
      if (v) v.textContent = num.toFixed(2);
    }
  }

  var debouncedSave = debounce(function() {
    if (!__hydrated) {
      // F1 fix: refuse to PATCH if we never confirmed the current
      // server state. Otherwise a hydrate-failure leaves sliders at
      // 0.00 and the next slider interaction silently overwrites
      // Chipper's real settings with zeroes.
      setStatus("Save blocked: not yet hydrated", "#f85149");
      return;
    }
    var payload = readSliders();
    setStatus("Saving " + PROFILE_NAME + "…", "#58a6ff");
    fetch(SERVER_V2 + "/api/voice/profile_update", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    }).then(function(r) {
      return r.json().then(function(j){ return {ok: r.ok, body: j}; });
    }).then(function(res) {
      if (!res.ok) {
        setStatus("Save failed: " + (res.body.hint || res.body.error || "unknown"), "#f85149");
        return;
      }
      var name = (res.body && res.body.character_name) || PROFILE_NAME;
      // Read-back name confirmation per Phase 0 C1 mitigation.
      var idGuard = (res.body && res.body.id != null) ? res.body.id : PROFILE_ID;
      if (idGuard !== PROFILE_ID || name.toLowerCase() !== PROFILE_NAME.toLowerCase()) {
        setStatus("⚠ Server returned id=" + idGuard + " name=" + name + " (expected id=" + PROFILE_ID + " name=" + PROFILE_NAME + ")", "#f85149");
        return;
      }
      setStatus("✓ Saved " + name + " (id=" + PROFILE_ID + ")", "#2ea043");
    }).catch(function(err) {
      setStatus("Save error: " + (err && err.message || err), "#f85149");
    });
  }, DEBOUNCE_MS);

  function hydrate() {
    __hydrateAttempts += 1;
    setStatus("Hydrating from prod_voice_profiles id=" + PROFILE_ID + "…", "#58a6ff");
    fetch(SERVER_V2 + "/api/voice/profile/" + PROFILE_ID, {cache: "no-store"})
      .then(function(r){
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function(j) {
        // Read-back name guard before trusting the data (Phase 0 C1).
        if (!j || j.id !== PROFILE_ID || (j.character_name || "").toLowerCase() !== PROFILE_NAME.toLowerCase()) {
          throw new Error("Read-back mismatch: got id=" + (j && j.id) + " name=" + (j && j.character_name));
        }
        writeSliders(j);
        __hydrated = true;
        setStatus("");
      }).catch(function(err) {
        if (__hydrateAttempts < __hydrateMaxAttempts) {
          // F7 mitigation: retry transient failures with backoff.
          var delayMs = 500 * Math.pow(2, __hydrateAttempts - 1);
          setStatus("Hydrate failed (attempt " + __hydrateAttempts + "/" + __hydrateMaxAttempts + "); retrying in " + (delayMs/1000) + "s…", "#f85149");
          setTimeout(hydrate, delayMs);
          return;
        }
        // Permanent fail: leave sliders DISABLED (F1 fix), surface error.
        setSlidersDisabled(true);
        setStatus("Hydrate failed (" + (err && err.message || err) + "); restart server then refresh page", "#f85149");
      });
  }

  function inject() {
    var regenInd = $("phase-a-regen-ind");
    if (!regenInd || !regenInd.parentNode) return false;
    if ($("phase-a-voice-block")) return true;  // already injected

    var block = document.createElement("div");
    block.id = "phase-a-voice-block";
    block.style.cssText = "margin:8px 0 4px;padding:8px 10px;background:#161b22;border:1px solid #30363d;border-radius:4px;";

    var header = document.createElement("div");
    header.style.cssText = "display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;";
    var title = document.createElement("div");
    title.style.cssText = "font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:0.5px;";
    title.textContent = "Chipper voice settings (persistent → prod_voice_profiles id=" + PROFILE_ID + ")";
    var status = document.createElement("span");
    status.id = "phase-a-voice-status";
    status.style.cssText = "font-size:11px;color:#8b949e;";
    header.appendChild(title);
    header.appendChild(status);
    block.appendChild(header);

    block.appendChild(buildSliderRow("stability", "Stability"));
    block.appendChild(buildSliderRow("similarity_boost", "Similarity"));
    block.appendChild(buildSliderRow("style", "Style"));

    var note = document.createElement("div");
    note.style.cssText = "font-size:10px;color:#6e7681;margin-top:4px;font-style:italic;";
    note.textContent = "Changes save automatically (250ms debounce) and apply to the NEXT Regen Audio call. Cedric (id=1) is untouched (server-side allow-list rejects writes to id≠2).";
    block.appendChild(note);

    // Insert AFTER the regen row (which contains regen button + indicator).
    var regenRow = regenInd.parentNode;
    if (regenRow.nextSibling) {
      regenRow.parentNode.insertBefore(block, regenRow.nextSibling);
    } else {
      regenRow.parentNode.appendChild(block);
    }
    // Reset hydration state — could be a re-injection after panel re-mount.
    __hydrated = false;
    __hydrateAttempts = 0;
    hydrate();
    return true;
  }

  // F8 fix: re-inject on every Phase A panel re-mount. The storyboard's
  // refreshState() pipeline does NOT clear #mn-phase-panels.innerHTML
  // today, but init() does once on first mount; if a future patch or
  // hot-reload re-runs init(), our slider block is destroyed with
  // its parent. MutationObserver watches the mount and re-injects.
  function watchMount() {
    var mount = $("mn-phase-panels");
    if (!mount) return false;
    if (mount.__phaseAPanelObserver) return true;
    var obs = new MutationObserver(function() {
      // Cheap: inject() is itself idempotent (checks for existing block).
      try { inject(); } catch (e) { console.warn("[phase_a_panel_patch] re-inject failed", e); }
    });
    obs.observe(mount, {childList: true, subtree: true});
    mount.__phaseAPanelObserver = obs;
    return true;
  }

  // Phase A panel mounts dynamically inside #mn-phase-panels via the
  // existing init(); we wait for `phase-a-regen-ind` to appear, then
  // inject. F9 fix: if it never appears, surface a visible warning
  // banner instead of silent console.warn.
  function tryInject(attempt) {
    attempt = attempt || 0;
    watchMount();  // attach observer ASAP, regardless of inject success
    if (inject()) return;
    if (attempt > 100) {
      // ~10 seconds elapsed at 100ms cadence. Surface visible warning.
      var mount = $("mn-phase-panels") || document.body;
      if (mount && !$("phase-a-voice-failwarn")) {
        var w = document.createElement("div");
        w.id = "phase-a-voice-failwarn";
        w.style.cssText = "margin:8px 0;padding:10px 12px;background:#3a1410;border:1px solid #f85149;border-radius:4px;color:#f85149;font-size:12px;";
        w.textContent = "⚠ Phase A voice slider injection timed out — phase-a-regen-ind never appeared. Sliders are NOT loaded. Reload the page; if it persists, the panel HTML may have changed and the patcher anchor needs updating.";
        mount.parentNode ? mount.parentNode.insertBefore(w, mount) : mount.appendChild(w);
      }
      console.warn("[phase_a_panel_patch] phase-a-regen-ind never appeared; aborting");
      return;
    }
    setTimeout(function(){ tryInject(attempt + 1); }, 100);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function(){ tryInject(0); });
  } else {
    tryInject(0);
  }
})();
""" + SENTINEL_END + """
</script>
<!-- """ + SENTINEL_END + """ -->
"""


# ---------- helpers ----------

def sha256_image_manifest(html: str) -> list[str]:
    """Return SHA256 hex of every base64 image payload in document order."""
    return [hashlib.sha256(m.group(1).encode("ascii")).hexdigest()
            for m in BASE64_IMG_RE.finditer(html)]


def node_check_script(script_text: str) -> tuple[bool, str]:
    """Run `node --check` on the patch script body. Returns (ok, msg)."""
    if shutil.which("node") is None:
        return False, "node not found on PATH"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tf:
        tf.write(script_text)
        path = tf.name
    try:
        r = subprocess.run(["node", "--check", path],
                           capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            return True, "ok"
        return False, (r.stderr or r.stdout).strip()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def extract_inner_script(patch_block: str) -> str:
    """Pull the IIFE body out of the wrapping <script>...</script> for node --check."""
    m = re.search(r"<script>\s*(.*?)\s*</script>", patch_block, flags=re.DOTALL)
    if not m:
        raise RuntimeError("could not extract inner script for syntax check")
    return m.group(1)


def backup_target(target: Path, label: str = "phase_a_panel") -> Path:
    bdir = target.parent / ".storyboard_backups"
    bdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%dT%H%M%SZ")
    bak = bdir / f"{target.name}.bak_{label}_{ts}"
    shutil.copy2(target, bak)
    # Prune older backups for THIS label only (don't touch other patchers').
    pattern = f"{target.name}.bak_{label}_*"
    siblings = sorted(bdir.glob(pattern))
    while len(siblings) > 10:
        try:
            siblings[0].unlink()
        except OSError:
            pass
        siblings.pop(0)
    return bak


def _excise_pair(html: str, start_marker: str, end_marker: str) -> str:
    s = html.find(start_marker)
    if s < 0:
        return html
    # Walk back to nearest preceding "<!--" or "<script>" — but don't
    # cross OTHER sentinel pairs (counter-agent F12 fix: a sibling
    # patch's own `<script>` block is not part of OUR block).
    pre_anchor = html.rfind("<!--", 0, s)
    pre_script = html.rfind("<script>", 0, s)
    block_start = max(pre_anchor, pre_script)
    if block_start < 0:
        block_start = s
    # F12 hardening: refuse to cross a foreign closing sentinel/script.
    # Scan from candidate block_start..s for any `</script>` or `*_END`
    # marker that would indicate we walked into someone else's block.
    middle = html[block_start:s]
    if "</script>" in middle:
        # Some other patch closed inside our walkback — start AFTER it.
        block_start = block_start + middle.rfind("</script>") + len("</script>")
        # And walk forward to the next `<!--` or `<script>`.
        nxt = min(
            (html.find(t, block_start, s) for t in ("<!--", "<script>")),
            key=lambda x: (x if x >= 0 else 10**18),
        )
        if nxt >= 0:
            block_start = nxt

    e = html.find(end_marker, s)
    if e < 0:
        raise RuntimeError(
            f"found {start_marker} without matching {end_marker} — manual cleanup needed"
        )
    after_end = e + len(end_marker)
    end_script = html.find("</script>", after_end)
    if end_script < 0:
        block_end = after_end
    else:
        block_end = end_script + len("</script>")
        m = re.match(r"\s*<!--\s*" + re.escape(end_marker) + r"\s*-->", html[block_end:])
        if m:
            block_end += m.end()
    # Trim leading newline left over from the gap so size delta stays clean.
    out = html[:block_start] + html[block_end:]
    return out


def excise_existing(html: str) -> str:
    """Remove existing PHASE_A_PANEL_PATCH_START..END block (incl wrapping <script>).

    Recognizes both the current (v2) and v1 sentinels so the QA-counter
    upgrade replaces the v1 ship cleanly.
    """
    out = html
    if SENTINEL_START in out:
        out = _excise_pair(out, SENTINEL_START, SENTINEL_END)
    if SENTINEL_START_V1 in out:
        out = _excise_pair(out, SENTINEL_START_V1, SENTINEL_END_V1)
    return out


# ---------- main ----------

def run(target: Path, dry_run: bool, force_replace: bool) -> int:
    if not target.is_file():
        print(f"FATAL: target not found: {target}", file=sys.stderr)
        return 2
    print(f"[patch] target = {target}")

    original_html = target.read_text(encoding="utf-8")
    original_size = len(original_html.encode("utf-8"))
    pre_manifest = sha256_image_manifest(original_html)
    print(f"[patch] base64 images pre-patch: {len(pre_manifest)} URIs")

    # Idempotency check (recognize both v2 and v1 sentinels so the QA
    # upgrade replaces the initial ship cleanly).
    has_v2 = SENTINEL_START in original_html
    has_v1 = SENTINEL_START_V1 in original_html
    has_sentinel = has_v2 or has_v1
    if has_sentinel and not force_replace:
        which = "v2" if has_v2 else "v1"
        print(f"[patch] ABORT: sentinel ({which}) already present. Re-run with "
              "--force-replace to excise and re-insert.")
        return 3

    working_html = excise_existing(original_html) if has_sentinel else original_html
    if has_sentinel:
        labels = [n for n, ok in (("v2", has_v2), ("v1", has_v1)) if ok]
        print(f"[patch] excised existing sentinel block(s): {labels} (--force-replace)")

    # Anchor check
    if not INJECT_ANCHOR_RE.search(working_html):
        print("[patch] ABORT: could not find </body></html> anchor", file=sys.stderr)
        return 4

    # Build new HTML
    new_html = INJECT_ANCHOR_RE.sub(PATCH_BLOCK + r"</body></html>", working_html)

    # Verify base64 manifest unchanged
    post_manifest = sha256_image_manifest(new_html)
    if pre_manifest != post_manifest:
        print(f"[patch] ABORT: image manifest drift. pre={len(pre_manifest)} post={len(post_manifest)}",
              file=sys.stderr)
        # Show first 3 diffs for debugging
        for i, (a, b) in enumerate(zip(pre_manifest, post_manifest)):
            if a != b:
                print(f"  diff @ idx {i}: {a[:12]}... -> {b[:12]}...", file=sys.stderr)
                if i >= 2:
                    break
        return 5
    print(f"[patch] base64 images post-patch: {len(post_manifest)} URIs (byte-identical ✓)")

    # Node syntax check on the injected IIFE body
    inner = extract_inner_script(PATCH_BLOCK)
    ok, msg = node_check_script(inner)
    if not ok:
        print(f"[patch] ABORT: node --check failed on injected script:\n{msg}", file=sys.stderr)
        return 6
    print("[patch] node --check passed on injected script ✓")

    # Sanity: new size is bigger than old (we ADDED a block)
    new_size = len(new_html.encode("utf-8"))
    delta = new_size - original_size
    if delta <= 0:
        print(f"[patch] ABORT: new size <= original ({new_size} vs {original_size}). "
              f"This looks wrong.", file=sys.stderr)
        return 7
    print(f"[patch] size delta: +{delta} bytes ({original_size} → {new_size})")

    if dry_run:
        print("[patch] DRY RUN: would write file. Skipping backup + write.")
        return 0

    bak = backup_target(target)
    print(f"[patch] backed up to {bak.name}")

    # Atomic write
    tmp = target.with_suffix(target.suffix + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(new_html, encoding="utf-8")
        os.replace(tmp, target)
    except Exception as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"[patch] FATAL: atomic write failed: {exc}", file=sys.stderr)
        return 8

    # Re-verify on disk
    final_html = target.read_text(encoding="utf-8")
    final_manifest = sha256_image_manifest(final_html)
    if final_manifest != pre_manifest:
        print("[patch] FATAL: post-write manifest drift detected. Restore from backup.",
              file=sys.stderr)
        return 9
    if SENTINEL_START not in final_html or SENTINEL_END not in final_html:
        print("[patch] FATAL: sentinels missing in written file. Restore from backup.",
              file=sys.stderr)
        return 10

    print(f"[patch] OK — wrote {target}")
    print(f"[patch] sentinel start at byte offset {final_html.find(SENTINEL_START)}")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", default=str(DEFAULT_TARGET),
                   help="storyboard HTML to patch (default: storyboard_v38_prod.html)")
    p.add_argument("--dry-run", action="store_true",
                   help="verify everything but do not write")
    p.add_argument("--force-replace", action="store_true",
                   help="excise existing sentinel block before inserting (idempotent re-run)")
    args = p.parse_args(argv)
    return run(Path(args.target), args.dry_run, args.force_replace)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
