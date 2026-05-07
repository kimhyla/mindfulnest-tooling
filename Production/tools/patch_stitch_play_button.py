#!/usr/bin/env python3
"""
patch_stitch_play_button.py — Path B JS/CSS patch for Stitch Editor Play/Pause buttons.

Adds per-slot ▶/⏸ buttons that play the slot video inline, radio-style
(clicking a new slot pauses the current one).

Usage:
  python3 patch_stitch_play_button.py [--dry-run]

After running, rebuild the output HTML:
  python3 build_stitch_editor.py

Rule 7 compliance: reads template, patches ONLY <style> and <script> blocks,
writes a new version. Does NOT touch base64 image data (none in this file).
"""
import re
import sys
import shutil
import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
TEMPLATE = SCRIPT_DIR / "stitch_editor_template.html"

# ── CSS to inject (just before closing </style>) ─────────────────────────────
CSS_PATCH = """
    /* ── PER-SLOT PLAY/PAUSE ── */
    .slot-play-btn {
      position: absolute; top: 8px; right: 36px;
      background: rgba(15, 52, 96, 0.92); border: 1px solid var(--accent2);
      color: var(--text); border-radius: 50%; width: 32px; height: 32px;
      display: flex; align-items: center; justify-content: center;
      cursor: pointer; font-size: 14px; z-index: 10;
      transition: background .15s, border-color .15s;
      line-height: 1;
    }
    .slot-play-btn:hover { background: var(--accent2); border-color: var(--accent); }
    .slot-play-btn.playing { background: var(--accent); border-color: var(--accent); }

    .slot-inline-video {
      display: none; width: 100%; max-height: 160px; border-radius: 4px;
      background: #000; margin-top: 6px; outline: none;
    }
    .slot-inline-video.visible { display: block; }

    /* video-zone column grows when video is shown */
    .video-zone.has-inline-video { flex-direction: column; align-items: stretch; }
"""

# ── JS to inject (just before closing </script>) ──────────────────────────────
JS_PATCH = r"""
// ═══════════════════════════════════════════════════════════════════════════════
// PER-SLOT PLAY / PAUSE  (Path B patch — patch_stitch_play_button.py)
// ═══════════════════════════════════════════════════════════════════════════════

// Track which slotId is currently playing (null = none)
let _activeSlotPlayId = null;
// Map slotId → <video> element
const _slotVideoEls = {};

/**
 * Toggle play/pause for a slot's inline video.
 * Radio-style: starting one slot pauses any other that's playing.
 * Endpoint: GET http://localhost:5111/api/finder_video?path=<encoded>
 * (no probe param → serves bytes with Range support, perfect for <video>)
 */
function toggleSlotPlay(slotId) {
  const slot = slots.find(s => s.id === slotId);
  if (!slot || !slot.videoPath) {
    toast('Drop a video file onto this slot first', 'error');
    return;
  }

  const btn = document.getElementById(`playbtn-${slotId}`);
  const vzone = document.getElementById(`vzone-${slotId}`);

  // Pause any other currently-playing slot
  if (_activeSlotPlayId !== null && _activeSlotPlayId !== slotId) {
    _pauseSlot(_activeSlotPlayId);
  }

  // Get or create the inline <video> element for this slot
  let vid = _slotVideoEls[slotId];
  if (!vid) {
    vid = document.createElement('video');
    vid.id = `slotv-${slotId}`;
    vid.className = 'slot-inline-video';
    vid.controls = true;
    vid.preload = 'metadata';
    // Absolute URL per Rule 32 — uses finder_video endpoint (serves bytes, no probe)
    const encodedPath = encodeURIComponent(slot.videoPath);
    vid.src = `http://localhost:5111/api/finder_video?path=${encodedPath}`;
    vid.addEventListener('ended', () => _pauseSlot(slotId));
    vid.addEventListener('pause', () => {
      if (_activeSlotPlayId === slotId) {
        _setSlotPlayState(slotId, false);
        _activeSlotPlayId = null;
      }
    });
    // Append below the existing zone content (inside vzone)
    if (vzone) {
      vzone.classList.add('has-inline-video');
      vzone.appendChild(vid);
    }
    _slotVideoEls[slotId] = vid;
  }

  const isPlaying = _activeSlotPlayId === slotId && !vid.paused;
  if (isPlaying) {
    vid.pause();
    // pause event handler above cleans up state
  } else {
    vid.classList.add('visible');
    vid.play().catch(err => {
      toast(`Playback error: ${err.message}`, 'error');
    });
    _activeSlotPlayId = slotId;
    _setSlotPlayState(slotId, true);
  }
}

function _pauseSlot(slotId) {
  const vid = _slotVideoEls[slotId];
  if (vid && !vid.paused) vid.pause();
  _setSlotPlayState(slotId, false);
  if (_activeSlotPlayId === slotId) _activeSlotPlayId = null;
}

function _setSlotPlayState(slotId, playing) {
  const btn = document.getElementById(`playbtn-${slotId}`);
  if (btn) {
    btn.textContent = playing ? '⏸' : '▶';
    btn.title = playing ? 'Pause' : 'Play';
    btn.classList.toggle('playing', playing);
  }
}

/**
 * Clean up inline video elements when a slot is removed or the timeline
 * is re-rendered.  Called from removeSlot() and renderTimeline().
 */
function destroySlotVideo(slotId) {
  const vid = _slotVideoEls[slotId];
  if (vid) {
    vid.pause();
    vid.src = '';
    vid.remove();
    delete _slotVideoEls[slotId];
  }
  if (_activeSlotPlayId === slotId) _activeSlotPlayId = null;
}

// Patch removeSlot to also destroy inline video
const _origRemoveSlot = removeSlot;
removeSlot = function(slotId) {
  destroySlotVideo(slotId);
  _origRemoveSlot(slotId);
};

// Patch renderTimeline to destroy inline videos before re-render
// (they'll be recreated on next Play click)
const _origRenderTimeline = renderTimeline;
renderTimeline = function() {
  // destroy all inline videos (DOM nodes get wiped on re-render anyway)
  Object.keys(_slotVideoEls).forEach(id => destroySlotVideo(+id));
  _origRenderTimeline();
};
"""

# ── SLOT HTML PATCH: inject play button into buildSlotEl ─────────────────────
# We patch the slot-header div in buildSlotEl to add the play button.
# Target: the line after slot-remove button close tag, still inside slot-header.

# Old slot-header close pattern inside buildSlotEl (unique in file):
OLD_SLOT_HEADER = """        <button class="slot-remove" onclick="removeSlot(${slot.id})" title="Remove segment">✕</button>
      </div>"""

NEW_SLOT_HEADER = """        <button class="slot-remove" onclick="removeSlot(${slot.id})" title="Remove segment">✕</button>
        <button class="slot-play-btn" id="playbtn-${slot.id}"
                onclick="event.stopPropagation(); toggleSlotPlay(${slot.id})"
                title="Play">▶</button>
      </div>"""


def patch(template_path: Path, dry_run: bool = False) -> None:
    text = template_path.read_text(encoding="utf-8")

    # 1. Verify patch targets exist (fail fast)
    errors = []
    if "</style>" not in text:
        errors.append("Could not find </style> tag")
    if "</script>" not in text:
        errors.append("Could not find </script> tag")
    if OLD_SLOT_HEADER not in text:
        errors.append("Could not find slot-header close pattern (already patched?)")
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Guard: don't double-patch
    if "slot-play-btn" in text:
        print("SKIP: patch already applied (slot-play-btn found in template). No changes made.")
        return

    # 2. Inject CSS before </style>
    text = text.replace("  </style>", CSS_PATCH + "  </style>", 1)

    # 3. Inject play button into slot-header HTML
    text = text.replace(OLD_SLOT_HEADER, NEW_SLOT_HEADER, 1)

    # 4. Inject JS before the LAST </script> (there are several inline script blocks in <head>)
    last_idx = text.rfind("</script>")
    if last_idx == -1:
        print("ERROR: could not find last </script>", file=sys.stderr)
        sys.exit(1)
    text = text[:last_idx] + JS_PATCH + "\n</script>" + text[last_idx + len("</script>"):]

    # Verify we actually made exactly the right number of replacements
    assert text.count("slot-play-btn") >= 3, "Expected >=3 occurrences of slot-play-btn after patch"
    assert text.count("toggleSlotPlay") >= 2, "Expected >=2 occurrences of toggleSlotPlay"

    if dry_run:
        print("DRY RUN — no files written. Patch would succeed.")
        return

    # Backup original before writing
    backup = template_path.with_suffix(".html.pre_play_button_backup")
    shutil.copy2(template_path, backup)
    print(f"Backup: {backup.name}")

    template_path.write_text(text, encoding="utf-8")
    print(f"Patched: {template_path.name} ({len(text):,} chars)")
    print("Next: python3 build_stitch_editor.py")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    args = parser.parse_args()
    patch(TEMPLATE, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
