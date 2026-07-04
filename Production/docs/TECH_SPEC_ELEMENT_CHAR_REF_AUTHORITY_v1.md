# Tech Spec — Element Char Ref Authority v1

**Date:** 2026-07-04  
**Status:** Implemented  
**Branch:** `fix/extract-dialogue-only-beat-types`  
**Primary repro:** Event_5 `:5115`, Benson Beat 1

## Problem

| ID | Symptom | Root cause |
|----|---------|------------|
| A | Auto-register on drop ineffective; stale gray baseline in video | Polluted `refer_images`; `add_element_pose` never promoted `frontal_image`; `already_matched` skipped when bytes ∈ refer but ≠ frontal |
| B | Add to Element 400 while slot shows image | UI uses `displayCharRef` (derived fallback); handler read sidecar `reference_image` only |

## Debate consensus (3×3)

- **Architecture:** Persisted vs derived authority split; strict registration alignment; Benson canonical paths under `Production/Benson/poses/`.
- **Blast radius:** `promote_frontal=True` only on explicit operator paths; Benson-first humanoid migration.
- **QA:** Contract tests + fleet build-sha `:5111–5116` + live `:5115` Benson Beat 1 curl.

## Invariants

1. `materialize_char_ref_abs_path(beat, body_abs_path)` — body → sidecar → implicit resolver.
2. `add_element_pose(..., promote_frontal=False)` — explicit paths set `frontal_image`.
3. Locked drop with path ≠ frontal → promote on register.
4. `BgTab.onAddElementPose` sends `{ beat_id, speaker, abs_path, promote_frontal: true }`.

## Verification

- `pytest tests/test_beat_ref_drop_lock.py tests/test_library_add_element_ui.py`
- `deploy_storyboard_v59.sh --event Event_5` + fleet build-sha parity
- Live curl Beat 1 gate + Benson registry frontal
