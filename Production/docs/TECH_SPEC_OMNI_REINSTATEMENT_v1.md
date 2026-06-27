# Tech Spec — Omni Kling Reinstatement v1

**Date:** 2026-06-25  
**Branch:** `fix/omni-reinstatement-v1`  
**Goal:** Restore pre-Avatar-Pro Omni Beat Gen reliability at all deployment layers.

## Problem (evidence)

1. **Prompt-box law regression (`127b328`):** `o3_prompt_is_avatar_pro_poisoned()` treats any prompt lacking `@Image1 (` as Avatar poison; `_migrate_sidecar` runs heal before skip guard → operator text rewritten. Pytest: `test_o3_prompt_box_law.py` failures.
2. **Runtime sidecar pollution:** Milestone sidecar has 16 stale O3 busy fields (`heal_milestone_speak_beats_omni.py --dry-run`).
3. **Deploy drift (when present):** Event HTML `build-sha` must equal `git HEAD`; Dropbox parity must exit 0.

## Category fixes (not patches)

| ID | Category | Fix |
|----|----------|-----|
| R1 | Prompt authority collision | Poison detect = **positive Avatar markers only**; never infer poison from missing `@Image1`. Respect `o3_prompt_box_law` in heal. |
| R2 | Job-truth runtime data | Run `heal_milestone_speak_beats_omni.py` on milestone JSON sidecar (clear stale busy fields). |
| R3 | Deploy durability | `deploy_storyboard_v59.sh` → parity exit 0 → restart → served `build-sha` = HEAD. |

## Out of scope

- Phase B Avatar Pro lipsync (unchanged per `67c5bdc`).
- Re-defaulting speak beats to Avatar Pro (`eb5c350` stays reverted).

## Proof gates

- `verify_o3_intro_contract.sh` — 0 failures
- `verify_tooling_dropbox_parity.py` — exit 0
- `verify_beatgen_deploy_smoke.sh 5112` — milestone session ≥1 beat
- Browser: Event_2 milestone BG, hard refresh, build-sha match

## Rollback

- Git revert on branch
- Sidecar backup: `*.bak_omni_*` from heal script
