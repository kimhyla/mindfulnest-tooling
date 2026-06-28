# Tech Spec — Phase Module Lipsync Preview Contract (PMLPC) v1

**Status:** SPEC (pre-implementation)  
**Date:** 2026-06-22  
**LD tag:** `PHASE_MODULE_LIPSYNC_PREVIEW_V1`  
**Scope:** Phase A + Phase B module-level lipsync job lifecycle, preview `<video>` population, waveform audio priority, and server state hygiene.  
**Repos:** `mindfulnest-tooling` + Dropbox mirror + server restart.

---

## 1. Problem statement

After **Send for Lipsync**, operators see an empty preview area and a yellow “in progress” banner for long periods — or indefinitely when Kling stalls. Separately, **stem regen** or **base-clip change** wipes `phase_*_lipsync_file` from state, so the preview goes blank even when an older MP4 still exists on disk.

**Category:** Module lipsync treats “preview availability” as identical to “current lipsync job succeeded” and **destroys preview pins** on upstream changes instead of marking stale. Phase B lacks Phase A’s stale/orphan job timeouts.

**Incident trace (Event_2, 2026-06-22):**

1. Cedric v3 → `requires_regen: true`
2. New voice stem → `_phase_clear_lipsync_derived()` removed `lipsync_file` from state
3. Send for Lipsync → `polling` for ~8–20 min with **no preview** until Kling completes
4. Vendor task genuinely `processing` (not UI-only stuck) — but UX feels broken

---

## 2. Surfaces in scope

| Surface | Job submit | Poller | Preview UI | Stale handling |
|---------|------------|--------|------------|----------------|
| Phase B module | `POST /api/phase_b/lipsync` → Kling | `sweep_phase_module_lipsync_polls` | `PhaseProducer` `<video>` | **Missing timeout** |
| Phase A module | `POST /api/phase_b/lipsync` phase=a → ByteDance worker | `sweep_phase_a_lipsync_resume` | Same + stitched path | `PHASE_A_LIPSYNC_STALE_SEC` |
| Beat-level lipsync | BG / Storyboard | `LipsyncPollingThread` | StoryboardTab ▶ | `audio_regenerated_at` vs `file_mtime` |
| Stitcher slot video | N/A | N/A | Stitcher composer | N/A |

**In scope:** Phase A/B module paths in `server_handlers/phases.py`, `phase_lipsync_job_contract.py`, `PhaseProducer.tsx`.  
**Out of scope (reference only):** Beat lipsync freshness gate (`STORYBOARD_LIPSYNC_BUTTON_FRESHNESS_GATE_V1`) — PM LPC should **mirror** its “stale not absent” pattern, not replace beat logic.

---

## 3. Goals

1. **Preview never blank during in-flight job** if any prior lipsync file exists (stale overlay).
2. **Stem regen / base-clip change** marks stale without deleting `lipsync_file` + `lipsync_mtime`.
3. **Phase B job parity with Phase A** — `started_at`, stale timeout, orphan recovery.
4. **Explicit UI modes** driven by server enum — not inferred from missing fields.
5. **Single Python + TS contract** — same status enum, same busy rules.

## 4. Non-goals

- Changing Kling vendor or lipsync algorithm.
- Auto-resubmit on timeout (operator clicks Resend).
- Beat Gen sidecar lipsync changes.

---

## 5. State model

### 5.1 New fields (top-level `production_state.json`)

| Field | Type | When set |
|-------|------|----------|
| `phase_{a|b}_lipsync_started_at` | float epoch | On job submit (both phases) |
| `phase_{a|b}_lipsync_base_clip_id_at_bake` | string | On terminal success (already partially exists for B) |
| `phase_{a|b}_lipsync_preview_mode` | enum | Derived on read (optional cache) |

### 5.2 Preview mode enum (derived, server + client)

| Mode | Conditions | UI |
|------|------------|-----|
| `none` | No `lipsync_file` on disk or in state | Placeholder text |
| `stale` | `lipsync_file` set + `requires_regen` true + not in-flight | Show video + amber banner “Stale — wrong stem/base — resend” |
| `in_flight` | `phase_lipsync_job_busy(status, task_id)` | Show last preview if any + progress banner with elapsed |
| `fresh` | `lipsync_file` set + `requires_regen` false + terminal success | Normal preview |

### 5.3 Change `_phase_clear_lipsync_derived`

**Current:** Deletes `lipsync_file`, `lipsync_mtime`, `lipsync_status`, etc.

**New split:**

```python
def _phase_mark_lipsync_stale(state, phase: str, reason: str) -> None:
    state[f"phase_{phase}_lipsync_requires_regen"] = True
    state[f"phase_{phase}_lipsync_stale_reason"] = reason  # e.g. stem_regen, base_clip_change
    # DO NOT pop lipsync_file / lipsync_mtime

def _phase_clear_lipsync_outputs(state, phase: str) -> None:
    """Only on explicit Reject Lipsync or successful replace."""
    ...  # existing pop list
```

**Call sites:**

| Event | Function |
|-------|----------|
| Voice stem regen | `_phase_mark_lipsync_stale(..., "stem_regen")` |
| Base clip change (cedric v3) | `_phase_mark_lipsync_stale(..., "base_clip_change")` |
| Stem cut apply | `_phase_mark_lipsync_stale(..., "stem_cut")` |
| Reject lipsync button | `_phase_clear_lipsync_outputs` + `requires_regen=True` |
| Lipsync success | `requires_regen=False`, update file/mtime |

---

## 6. Phase B job lifecycle parity

Add to `phases.py` (mirror Phase A constants):

```python
PHASE_B_LIPSYNC_STALE_SEC = 1200      # 20 min — match Phase A
PHASE_B_LIPSYNC_VENDOR_POLL_SEC = 900  # expect completion p99
```

### 6.1 On submit (`handle_phase_b_lipsync`)

- Set `phase_b_lipsync_started_at = time.time()`
- Do **not** clear `lipsync_file` (only update status/task_id/pending_out)

### 6.2 Extend `sweep_phase_module_lipsync_polls`

```python
if status == "polling":
    started = snap.get("phase_b_lipsync_started_at")
    if started and time.time() - started > PHASE_B_LIPSYNC_STALE_SEC:
        mutate_state(terminal_error="vendor_timeout")
    else:
        poll vendor...
```

### 6.3 Orphan recovery

If `polling` + `task_id` but server restarted < `PHASE_B_LIPSYNC_RESTART_ORPHAN_SEC` ago and no vendor progress → clear to `error: orphan` with resubmit hint.

(Reuse Phase A orphan pattern from `sweep_phase_a_lipsync_resume`.)

---

## 7. Client changes (`PhaseProducer.tsx`)

### 7.1 Preview source

```ts
function moduleLipsyncPreviewMode(slice): 'none' | 'stale' | 'in_flight' | 'fresh';

function previewVideoForPhase(slice, phase): PhasePreviewFile | null {
  if (phase === 'a') return phaseAPreviewFile(slice); // existing stitched logic
  const file = slice.lipsync_file;
  if (!file) return null;
  const mode = moduleLipsyncPreviewMode(slice);
  if (mode === 'none') return null;
  return { name: file, label: 'lipsync', kind: 'lipsync', previewMode: mode };
}
```

### 7.2 UI overlays on preview container

| Mode | Overlay |
|------|---------|
| `stale` | Amber bar: “Preview is stale ({reason}) — Send for Lipsync for new Cedric/stem” |
| `in_flight` | Semi-transparent + “Kling processing… {elapsed}m” |
| `fresh` | No overlay |

### 7.3 Waveform audio priority (unchanged logic, clearer modes)

- `stale` or `in_flight`: waveform uses stem if `requires_regen` (existing `priorityAudioFile`)
- Preview video can still show stale file while waveform shows stem

### 7.4 Progress message enhancement

```ts
phaseLipsyncProgressMessage(phase, startedAt?: number): string
// append "Elapsed 12m" when startedAt set
```

### 7.5 Files contract

Extend `phaseLipsyncJobContract.ts` + `phase_lipsync_job_contract.py` with:

- `phase_lipsync_preview_mode(state, phase) -> str`
- `PHASE_B_LIPSYNC_STALE_SEC` constant (client displays warning near limit)

---

## 8. Server read path hygiene

### 8.1 `handle_v2_event_state` / bootstrap

When projecting phase fields:

- Always emit top-level `phase_b_lipsync_file` if file exists on disk even when `requires_regen` (state pin may be missing — reconcile from disk with mtime check).
- Emit `phase_{a|b}_lipsync_preview_mode` for client (optional additive field).

### 8.2 Disk/state reconcile (category fix for “file on disk, not in state”)

```python
def _phase_reconcile_lipsync_file_from_disk(state, phase, event_dir) -> None:
    """If state missing lipsync_file but newest phase_{phase}_lipsync_*.mp4 exists, re-pin with requires_regen=True."""
```

Run on event load and after stale mark — prevents orphan files invisible to UI.

---

## 9. Implementation phases

### PMLPC-0 — Contract + stale mark (server, 1 PR)

1. Split `_phase_clear_lipsync_derived` → mark vs clear.
2. Update stem regen, base clip canonical scripts to use mark.
3. Pytest: stem regen retains `lipsync_file` key.
4. TS: `moduleLipsyncPreviewMode` + stale overlay.

### PMLPC-1 — Phase B timeout + started_at (server, 1 PR)

1. `lipsync_started_at` on B submit.
2. Stale sweep in `sweep_phase_module_lipsync_polls`.
3. Pytest: mock poll processing + started_at old → terminal error.

### PMLPC-2 — Disk reconcile + event state projection (server, 1 PR)

1. Re-pin lipsync file from disk when missing.
2. Add `lipsync_preview_mode` to v2 state response.

### PMLPC-3 — UI + E2E (client, 1 PR)

1. Preview overlays for stale/in_flight.
2. `e2e/phase_lipsync_preview.spec.ts`:
   - Stale: file in state + requires_regen → video visible + banner
   - In-flight: polling + file → video visible + progress
   - Stem regen mock → file key retained

---

## 10. Test plan

| Test | Layer | Criteria |
|------|-------|----------|
| `test_stem_regen_retains_lipsync_file` | pytest | After regen_audio, `lipsync_file` key present, `requires_regen` true |
| `test_phase_b_lipsync_stale_timeout` | pytest | polling + old started_at → error status |
| `test_reconcile_lipsync_from_disk` | pytest | state missing file, disk has mp4 → re-pinned stale |
| `PMLPC-stale-ui` | Playwright | video element visible when stale |
| `PMLPC-inflight-ui` | Playwright | polling shows elapsed, keeps last preview |
| Manual Event_2 | operator | Send lipsync → see old Cedric with “in flight” overlay until new completes |

---

## 11. Rollout

1. Python changes → Dropbox mirror + `curl -X POST .../api/server/restart`
2. Storyboard bundle build (preview overlays)
3. No migration script — reconcile on read handles legacy state
4. Optional one-shot: run reconcile on Event_1/Event_2 to re-pin `phase_b_lipsync_20260619-215332.mp4` as stale until new job completes

---

## 12. Risks

| Risk | Mitigation |
|------|------------|
| Showing wrong Cedric during in-flight confuses Kim | Banner: “Showing previous preview — new render in progress” |
| Stale file plays wrong audio on waveform | Waveform already prefers stem when `requires_regen` |
| Disk reconcile pins wrong file | Only pin newest matching `phase_{b}_lipsync_*.mp4` pattern |

---

## 13. Success criteria

- No blank preview panel during 8–20 min Kling wait when any prior lipsync exists.
- Phase B `polling` never lasts > 20 min without terminal error.
- Stem regen never removes `lipsync_file` from state (pytest enforced).
