#!/usr/bin/env python3
"""
Rule 7 Path B patch v2: Fix race condition + button state in slot preview

Fixes issues found by counter-agent QA:
1. Add _buildingInProgress flag to prevent race condition
2. Disable button during fetch
3. Add AbortController to cancel stale fetches
4. Improve error message for empty slots case
"""

import re
import sys
from pathlib import Path
from datetime import datetime

STITCH_PATH = Path(__file__).parent / "stitch_editor.html"

# Old JS to find (the state variables section)
OLD_STATE = '''// State for slot preview
let _slotPreviewPlaying = false;
let _slotPreviewVideoEl = null;
let _slotPreviewBtnEl = null;
let _slotPreviewSpinnerEl = null;'''

# New JS with fix
NEW_STATE = '''// State for slot preview
let _slotPreviewPlaying = false;
let _slotPreviewVideoEl = null;
let _slotPreviewBtnEl = null;
let _slotPreviewSpinnerEl = null;
let _slotPreviewBuildingInProgress = false;
let _slotPreviewAbortController = null;'''

# Old toggleSlotPreview function start
OLD_TOGGLE_START = '''async function toggleSlotPreview() {
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
  }'''

# Fixed version
NEW_TOGGLE_START = '''async function toggleSlotPreview() {
  // If currently playing, pause
  if (_slotPreviewPlaying && _slotPreviewVideoEl && !_slotPreviewVideoEl.paused) {
    _slotPreviewVideoEl.pause();
    return;
  }

  // Guard against rapid clicks while building
  if (_slotPreviewBuildingInProgress) {
    return;  // Already building, ignore click
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

  // Handle empty slots case
  if (slots.length === 0) {
    toast('Add a slot first', 'error');
    return;
  }

  const slot = slots.find(s => s.id === slotId);
  if (!slot) {
    toast('No slot selected', 'error');
    return;
  }
  if (!slot.videoPath) {
    toast('Selected slot has no video', 'error');
    return;
  }'''

# Old fetch section
OLD_FETCH = '''  // Show loading spinner
  if (_slotPreviewSpinnerEl) _slotPreviewSpinnerEl.classList.add('loading');
  setStatus(`Building slot ${slot.label} preview…`);

  try {
    const r = await fetch('http://localhost:5111/api/stitch_editor/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(singleSlotJob)
    });'''

# Fixed version with AbortController and button disable
NEW_FETCH = '''  // Cancel any in-flight fetch
  if (_slotPreviewAbortController) {
    _slotPreviewAbortController.abort();
  }
  _slotPreviewAbortController = new AbortController();

  // Show loading state
  _slotPreviewBuildingInProgress = true;
  if (_slotPreviewBtnEl) _slotPreviewBtnEl.disabled = true;
  if (_slotPreviewSpinnerEl) _slotPreviewSpinnerEl.classList.add('loading');
  setStatus(`Building slot ${slot.label} preview…`);

  try {
    const r = await fetch('http://localhost:5111/api/stitch_editor/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(singleSlotJob),
      signal: _slotPreviewAbortController.signal
    });'''

# Old spinner hide after success
OLD_SUCCESS_CLEANUP = '''    // Hide spinner
    if (_slotPreviewSpinnerEl) _slotPreviewSpinnerEl.classList.remove('loading');'''

NEW_SUCCESS_CLEANUP = '''    // Reset loading state
    _slotPreviewBuildingInProgress = false;
    if (_slotPreviewBtnEl) _slotPreviewBtnEl.disabled = false;
    if (_slotPreviewSpinnerEl) _slotPreviewSpinnerEl.classList.remove('loading');'''

# Old error cleanup
OLD_ERROR_CLEANUP = '''  } catch (e) {
    if (_slotPreviewSpinnerEl) _slotPreviewSpinnerEl.classList.remove('loading');
    toast(`Slot preview failed: ${e.message}`, 'error');
    setStatus('Slot preview error');
  }'''

NEW_ERROR_CLEANUP = '''  } catch (e) {
    // Reset loading state
    _slotPreviewBuildingInProgress = false;
    if (_slotPreviewBtnEl) _slotPreviewBtnEl.disabled = false;
    if (_slotPreviewSpinnerEl) _slotPreviewSpinnerEl.classList.remove('loading');
    // Don't toast on abort (user initiated cancel by starting new preview)
    if (e.name !== 'AbortError') {
      toast(`Slot preview failed: ${e.message}`, 'error');
      setStatus('Slot preview error');
    }
  }'''


def patch_html():
    if not STITCH_PATH.exists():
        print(f"ERROR: {STITCH_PATH} not found")
        sys.exit(1)

    html = STITCH_PATH.read_text(encoding='utf-8')
    original_len = len(html)

    # Check if v2 already patched
    if '_slotPreviewBuildingInProgress' in html:
        print("v2 already patched — skipping")
        return False

    # Check if v1 was patched (required before v2)
    if 'patch_stitch_slot_preview.py' not in html:
        print("ERROR: v1 patch not found — run patch_stitch_slot_preview.py first")
        sys.exit(1)

    # Apply patches in order
    patches = [
        (OLD_STATE, NEW_STATE, "state variables"),
        (OLD_TOGGLE_START, NEW_TOGGLE_START, "toggleSlotPreview start"),
        (OLD_FETCH, NEW_FETCH, "fetch with AbortController"),
        (OLD_SUCCESS_CLEANUP, NEW_SUCCESS_CLEANUP, "success cleanup"),
        (OLD_ERROR_CLEANUP, NEW_ERROR_CLEANUP, "error cleanup"),
    ]

    for old, new, desc in patches:
        if old not in html:
            print(f"ERROR: Could not find '{desc}' section")
            sys.exit(1)
        html = html.replace(old, new, 1)
        print(f"  Patched: {desc}")

    # Sanity check
    if 'const SERVER_BASE' not in html or 'MindfulNest Stitch Editor' not in html:
        print("ERROR: Sanity check failed — patched HTML missing expected content")
        sys.exit(1)

    # Write back
    STITCH_PATH.write_text(html, encoding='utf-8')
    new_len = len(html)

    print(f"SUCCESS: Applied v2 fixes to {STITCH_PATH.name}")
    print(f"  Original: {original_len:,} bytes")
    print(f"  Patched:  {new_len:,} bytes (+{new_len - original_len:,})")
    print(f"  Timestamp: {datetime.now().isoformat()}")

    return True


if __name__ == '__main__':
    patch_html()
