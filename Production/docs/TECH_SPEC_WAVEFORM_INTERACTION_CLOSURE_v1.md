# TECH_SPEC — Waveform Interaction Closure v1

**Marker:** `WAVEFORM_INTERACTION_CLOSURE_V1`  
**Status:** Implementing  
**Date:** 2026-07-06  
**Extends:** `TECH_SPEC_WAVEFORM_TIME_AUTHORITY_v1.md`, `TECH_SPEC_PHASE_G_INTERACTION_WARM_PATH_V1.md`  
**Symptom class:** WTA-001..030 (playhead snap, silent drop/seek no-op, proof-surface mismatch)

---

## 1. 3×3 agent debate (synthesis)

### Round 1 — Diagnosis

| Agent | Position |
|-------|----------|
| **A (Architecture)** | Root cause is **composite surface** — five interaction owners on one DOM node. Fixes must be **invariant-based**, not symptom patches. |
| **B (QA)** | Root cause is **RC11 proof-surface mismatch** — fixture/grep green while Event_3 stem path red. Every ship needs **live operator-path Playwright** on `:5113`. |
| **C (UX)** | Root cause is **silent failure** — `if (durMs <= 0) return` with no toast. Operators interpret as “broken”; agents interpret as “handler present”. |

### Round 2 — Scope

| Agent | Position |
|-------|----------|
| **A** | Do **not** rewrite WaveSurfer. Finish WTA modules + one **interaction policy** module; forbid new pointer logic in `WaveformTimeline` body. |
| **B** | **Blast radius:** Phase A/B + Stitcher slot waveforms only. No Beat Gen / Storyboard image drops in this PR. |
| **C** | **WTA-5 ship now:** visible toast on rejected drop; “waveform loading — try again in a moment” after Generate stem. |

### Round 3 — Proof

| Agent | Position |
|-------|----------|
| **A** | Gates: `verify_waveform_interaction_closure.sh` = policy unit tests + grep + fixture e2e + **Event_3 live** stem drag + drop. |
| **B** | Deploy: **clean tree commit before deploy**; fleet `:5111–5116` build-sha; multipass x2; no `MN_ALLOW_DIRTY_DEPLOY` in closure arc. |
| **C** | Cursor rule: **waveform-interaction-invariants** — any PR touching `WaveformTimeline*` must run closure gate + live Event_3 proof. |

**Locked decision:** Implement WTA-13 (remount duration carry) + WTA-5 (loud drop reject) + live Event_3 proof + closure meta-gate. No new features inside `WaveformTimeline` this PR.

---

## 2. Invariants (must never regress)

| ID | Invariant |
|----|-----------|
| WTA-INV-1 | **One duration source** for drop, cue drag, seek math: `resolveTimelineDurationMs()` / authority — never bare `ws.getDuration()` when ref > 0. |
| WTA-INV-2 | **Never zero duration on audioSrc remount** until new `onReady` — carry prior ms (WTA-13). |
| WTA-INV-3 | **Seek bind isolated** from WaveSurfer mount effect (`waveformSeekController.ts`). |
| WTA-INV-4 | **Drop capture** on wrapper (`bindDropTargetCapture`) — never bubble-only on canvas child. |
| WTA-INV-5 | **Cue body pass-through** — block `pointer-events: none`; handles `auto` (SEEK-4 / WAVEFORM_CUE_HANDLE_V1). |
| WTA-INV-6 | **No silent reject** — drop when `!ready \|\| durationMs <= 0` → toast (WTA-5). |
| WTA-INV-7 | **Live proof** on operator path: Event_3 `:5113` Phase B stem — DROP-WC-LIVE-1 + SEEK-DRAG-B-STEM-LIVE-1. |

---

## 3. Implementation

### 3.1 `waveformInteractionPolicy.ts`

Pure functions:

- `assessWaveformInteractionReady({ isReady, durationMs, hasAudioOrDisplay })` → `{ ok } | { ok: false, reason, userMessage }`
- `waveformDropRejectToast(reason)` → toast payload

### 3.2 `WaveformTimeline.tsx`

- Drop handler: call policy; on reject → `pushToast` (warning, 4s TTL).
- Remount: carry duration (WTA-13, shipped in this branch).
- Seek drag start: clear stale `loadError` (WTA-13).

### 3.3 Gates

- `verify_waveform_interaction_closure.sh` — unit + grep + fixture e2e subset + invokes live Event_3 when `:5113` up.
- Extends `verify_phase_waveform_play_durability.sh` (WTA-13 markers).
- Extends `verify_live_fleet_interaction.sh` (Event_3 live block).

### 3.4 E2E

| Test | Surface | Pass criteria |
|------|---------|---------------|
| DROP-REJECT-1 | Fixture | Drop before ready → toast visible |
| REMOUNT-STEM-2 | Fixture | Mock audioSrc swap; duration attr stays > 0 during reload |
| DROP-WC-LIVE-1 | Event_3 live | cue count increases |
| SEEK-DRAG-B-STEM-LIVE-1 | Event_3 live | playhead > 25% duration after drag |

---

## 4. Blast radius

| Area | Risk | Mitigation |
|------|------|------------|
| Phase A/B producer | Drop toast noise | Only on rejected drop, not seek |
| Stitcher slot waveform | Same component | Policy uses `displayOnly` + peaks path |
| Beat Gen / Storyboard | None | Out of scope |
| Deploy fleet | Stale port | `restart_storyboard_fleet.sh` + build-sha parity |

---

## 5. Rollout checklist

1. Feature branch `fix/wta-interaction-closure-v1`
2. `verify_waveform_interaction_closure.sh` green
3. Commit (clean tree, waveform files only)
4. `deploy_storyboard_v59.sh --event Event_4` → log contains `[deploy] complete`
5. Fleet build-sha `:5111–5116` == HEAD
6. `verify_multipass_deploy_proof.sh` 1 and 2
7. Live Event_3 Playwright green

---

## 6. Success criteria

- Kim can Generate stem on Event_3 Phase B, drop watercolor within 2s, drag playhead — no silent no-op.
- Zero new grep-only “shipped” rows without live Event_3 proof.
- Closure gate runs in deploy preflight.
