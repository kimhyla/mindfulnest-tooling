#!/usr/bin/env python3
"""
Rule 7 Path B patch: Add slot-preview Play/Pause button to stitch_editor.html

This patches ONLY <style> and <script> blocks. No structural HTML changes.
Adds a preview button in the bottom actions bar that:
1. Previews the CURRENTLY SELECTED slot (last interacted with, default slot 1)
2. Uses /api/stitch_editor/preview endpoint with a single-slot job
3. Plays in a small inline <video> element (240x135) next to the button
4. Toggles ▶ Play → ⏸ Pause
"""

import re
import sys
from pathlib import Path
from datetime import datetime

STITCH_PATH = Path(__file__).parent / "stitch_editor.html"

# New CSS to add (inserted before </style>)
NEW_CSS = '''
    /* ── SLOT PREVIEW in bottom bar (Path B patch) ── */
    #slotPreviewBtn {
      display: inline-flex; align-items: center; gap: 6px;
    }
    #slotPreviewBtn .spb-icon {
      font-size: 14px;
    }
    #slotPreviewVideo {
      max-width: 240px; max-height: 135px; border-radius: var(--radius);
      background: #000; display: none; margin-left: 8px;
    }
    #slotPreviewVideo.visible { display: inline-block; }
    #slotPreviewSpinner {
      display: none; margin-left: 8px; font-size: 11px; color: var(--muted);
    }
    #slotPreviewSpinner.loading { display: inline-block; }
'''

# New JS to add (inserted before </script>)
NEW_JS = '''
// ═══════════════════════════════════════════════════════════════════════════════
// SLOT PREVIEW — Bottom Bar Play/Pause (Path B patch — patch_stitch_slot_preview.py)
// ═══════════════════════════════════════════════════════════════════════════════

// Track which slot is "selected" (last interacted with)
let _selectedSlotId = null;

// Track slot focus on any slot interaction
document.addEventListener('click', (e) => {
  const slotEl = e.target.closest('.slot');
  if (slotEl) {
    const match = slotEl.id.match(/slot-(\\d+)/);
    if (match) _selectedSlotId = parseInt(match[1], 10);
  }
}, true);

// Also track on drag events into slots
document.addEventListener('drop', (e) => {
  const slotEl = e.target.closest('.slot');
  if (slotEl) {
    const match = slotEl.id.match(/slot-(\\d+)/);
    if (match) _selectedSlotId = parseInt(match[1], 10);
  }
}, true);

// State for slot preview
let _slotPreviewPlaying = false;
let _slotPreviewVideoEl = null;
let _slotPreviewBtnEl = null;
let _slotPreviewSpinnerEl = null;

// Inject the slot preview button + video element into bottomActions on DOMContentLoaded
window.addEventListener('DOMContentLoaded', () => {
  const bottomActions = document.getElementById('bottomActions');
  if (!bottomActions) return;

  // Create the button
  _slotPreviewBtnEl = document.createElement('button');
  _slotPreviewBtnEl.id = 'slotPreviewBtn';
  _slotPreviewBtnEl.className = 'btn btn-secondary';
  _slotPreviewBtnEl.innerHTML = '<span class="spb-icon">▶</span> Slot Preview';
  _slotPreviewBtnEl.title = 'Preview selected slot with audio mix';
  _slotPreviewBtnEl.onclick = toggleSlotPreview;

  // Create spinner
  _slotPreviewSpinnerEl = document.createElement('span');
  _slotPreviewSpinnerEl.id = 'slotPreviewSpinner';
  _slotPreviewSpinnerEl.textContent = 'Building…';

  // Create video element
  _slotPreviewVideoEl = document.createElement('video');
  _slotPreviewVideoEl.id = 'slotPreviewVideo';
  _slotPreviewVideoEl.controls = true;
  _slotPreviewVideoEl.preload = 'metadata';
  _slotPreviewVideoEl.addEventListener('ended', () => setSlotPreviewState(false));
  _slotPreviewVideoEl.addEventListener('pause', () => {
    if (_slotPreviewPlaying) setSlotPreviewState(false);
  });
  _slotPreviewVideoEl.addEventListener('play', () => setSlotPreviewState(true));

  // Insert after the existing Preview button (first child is ▶ Preview)
  const existingPreview = bottomActions.querySelector('button');
  if (existingPreview && existingPreview.nextSibling) {
    bottomActions.insertBefore(_slotPreviewBtnEl, existingPreview.nextSibling);
    bottomActions.insertBefore(_slotPreviewSpinnerEl, _slotPreviewBtnEl.nextSibling);
    bottomActions.insertBefore(_slotPreviewVideoEl, _slotPreviewSpinnerEl.nextSibling);
  } else {
    bottomActions.appendChild(_slotPreviewBtnEl);
    bottomActions.appendChild(_slotPreviewSpinnerEl);
    bottomActions.appendChild(_slotPreviewVideoEl);
  }
});

async function toggleSlotPreview() {
  // If currently playing, pause
  if (_slotPreviewPlaying && _slotPreviewVideoEl && !_slotPreviewVideoEl.paused) {
    _slotPreviewVideoEl.pause();
    return;
  }

  // If we have a loaded video that's paused, resume from beginning
  if (_slotPreviewVideoEl && _slotPreviewVideoEl.src && _slotPreviewVideoEl.paused && _slotPreviewVideoEl.currentTime > 0) {
    _slotPreviewVideoEl.currentTime = 0;
    _slotPreviewVideoEl.play().catch(e => toast(`Play error: ${e.message}`, 'error'));
    return;
  }

  // Determine which slot to preview
  let slotId = _selectedSlotId;
  if (!slotId && slots.length > 0) {
    slotId = slots[0].id;  // default to slot 1
  }

  const slot = slots.find(s => s.id === slotId);
  if (!slot) {
    toast('No slot selected', 'error');
    return;
  }
  if (!slot.videoPath) {
    toast('Selected slot has no video', 'error');
    return;
  }

  // Build a single-slot job for preview
  const singleSlotJob = {
    name: `slot_preview_${slotId}`,
    slots: [{
      id: slot.id,
      label: slot.label,
      video_path: slot.videoPath,
      video_dur_ms: slot.videoDurMs,
      ambient_bed_path: slot.ambientPath,
      ambient_volume: slot.ambientVol,
      sfx_cues: slot.sfxCues.map(c => ({
        id: c.id,
        source_path: c.path,
        name: c.name,
        offset_ms: c.offsetMs
      }))
    }],
    transitions: []  // no transitions for single slot
  };

  // Show loading spinner
  if (_slotPreviewSpinnerEl) _slotPreviewSpinnerEl.classList.add('loading');
  setStatus(`Building slot ${slot.label} preview…`);

  try {
    const r = await fetch('http://localhost:5111/api/stitch_editor/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(singleSlotJob)
    });

    if (!r.ok) {
      const e = await r.json();
      throw new Error(e.error || r.status);
    }

    const d = await r.json();

    // Hide spinner
    if (_slotPreviewSpinnerEl) _slotPreviewSpinnerEl.classList.remove('loading');

    // Set video source and show
    const previewUrl = (d.preview_url || '').startsWith('http')
      ? d.preview_url
      : `http://localhost:5111${d.preview_url}`;

    _slotPreviewVideoEl.src = previewUrl;
    _slotPreviewVideoEl.classList.add('visible');
    _slotPreviewVideoEl.load();
    _slotPreviewVideoEl.play().catch(e => toast(`Play error: ${e.message}`, 'error'));

    setStatus(`Slot preview ready — ${fmtMs(d.duration_ms || slot.videoDurMs)}`);

  } catch (e) {
    if (_slotPreviewSpinnerEl) _slotPreviewSpinnerEl.classList.remove('loading');
    toast(`Slot preview failed: ${e.message}`, 'error');
    setStatus('Slot preview error');
  }
}

function setSlotPreviewState(playing) {
  _slotPreviewPlaying = playing;
  if (_slotPreviewBtnEl) {
    const icon = _slotPreviewBtnEl.querySelector('.spb-icon');
    if (icon) icon.textContent = playing ? '⏸' : '▶';
    _slotPreviewBtnEl.title = playing ? 'Pause slot preview' : 'Preview selected slot with audio mix';
  }
}
'''


def patch_html():
    if not STITCH_PATH.exists():
        print(f"ERROR: {STITCH_PATH} not found")
        sys.exit(1)

    html = STITCH_PATH.read_text(encoding='utf-8')
    original_len = len(html)

    # Check if already patched
    if 'patch_stitch_slot_preview.py' in html:
        print("Already patched — skipping")
        return False

    # Patch CSS: insert before </style>
    css_pattern = r'(</style>)'
    if not re.search(css_pattern, html):
        print("ERROR: Could not find </style> tag")
        sys.exit(1)

    html = re.sub(css_pattern, NEW_CSS + r'\n  \1', html, count=1)

    # Patch JS: insert before </script> (the main script block, not the CDN ones)
    # Find the last </script> which is the main app script
    js_insertions = list(re.finditer(r'</script>', html))
    if len(js_insertions) < 1:
        print("ERROR: Could not find </script> tag")
        sys.exit(1)

    # Insert before the last </script>
    last_script_end = js_insertions[-1]
    html = html[:last_script_end.start()] + NEW_JS + '\n' + html[last_script_end.start():]

    # Verify the HTML still has the original content (sanity check)
    if 'const SERVER_BASE' not in html or 'MindfulNest Stitch Editor' not in html:
        print("ERROR: Sanity check failed — patched HTML missing expected content")
        sys.exit(1)

    # Write back
    STITCH_PATH.write_text(html, encoding='utf-8')
    new_len = len(html)

    print(f"SUCCESS: Patched {STITCH_PATH.name}")
    print(f"  Original: {original_len:,} bytes")
    print(f"  Patched:  {new_len:,} bytes (+{new_len - original_len:,})")
    print(f"  Timestamp: {datetime.now().isoformat()}")

    return True


if __name__ == '__main__':
    patch_html()
