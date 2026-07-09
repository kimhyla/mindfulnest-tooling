# Tech Spec — Element Char Ref Submit Parity v1

**Date:** 2026-07-09  
**Status:** Implementing  
**Branch:** `feat/o3-lifecycle-seal-v1` (or successor)  
**Marker:** `ELEMENT_CHAR_REF_SUBMIT_PARITY_V1`  
**Primary repro:** Event_6 `:5116`, `bg_arc1_event6_pre_beat_02` (Bork), megaphone baseline char ref vs Element frontal bytes

---

## Problem class

| ID | Symptom | Root cause |
|----|---------|------------|
| **C1** | Generate shows “Generating” then drops; no O3 job on disk | UI optimistic pending + submit rejected pre-job |
| **C2** | Session GET `_derived.can_generate=true` but submit 400 `ELEMENT_REGISTRATION_FAILED` | **Split-brain gates**: session/workbench used loose `char_ref_matches_element_images` + stale `element_char_ref_ok`; submit used strict `char_ref_aligned_for_intent_commit` |
| **C3** | Recurrence after Set as Element identity / voice refresh | Global registry moves; per-beat `reference_image` stale; sidecar flag `element_char_ref_ok: true` never recomputed on read |

This is **not** the O3 lifecycle seal class (terminal job truth). That arc is closed in PR #108. This is a separate **authority parity** class.

---

## 3×3 agent debate

### Agent A — Architecture (authority shape)

| Position | Argument | Verdict |
|----------|----------|---------|
| **A1** Patch session GET to special-case Bork/Event_6 | Fast unblock | **Reject** — symptom patch; cousins remain |
| **A2** Single submit-authority function shared by session GET, sidecar sync, intent commit | One truth; no stale sidecar trust | **Accept** |
| **A3** Auto-heal all beats to frontal on every registry read | Always aligned | **Reject** — mutates operator intent on read; violates workbench spec |

**A consensus:** `char_ref_aligned_for_intent_commit` (strict when `frontal_sha256` stamped) is the **only** char-ref gate for Element O3 generate paths. Session GET `_derived` recomputes every read.

---

### Agent B — Operator UX (workbench behavior)

| Position | Argument | Verdict |
|----------|----------|---------|
| **B1** Disable Generate when `_derived.can_generate === false` | Fail closed in UI; show inline error | **Accept** |
| **B2** Allow Generate; rely on submit error toast | Already have toast | **Reject** — causes C1 flash + wasted operator clicks |
| **B3** Hide char ref slot when misaligned | Less clutter | **Reject** — operator loses context for “Set as Element identity” |

**B consensus:** Generate disabled + inline hint from `_derived.element_char_ref_error`. Optimistic “Generating” only after preflight passes (no pending before char-ref gate).

---

### Agent C — Durability / QA (proof layer)

| Position | Argument | Verdict |
|----------|----------|---------|
| **C1** Unit tests only on mocked registry | Fast | **Reject** — missed live Event_6 split-brain |
| **C2** Contract tests + durability script grepping single authority + live curl on `:5116` beat 2 | Proves served code + gate fields | **Accept** |
| **C3** Manual Kim verification only | Human eyes | **Reject** — violates operator workflow rule |

**C consensus:** pytest matrix (stale sidecar ok + locked canonical), `verify_element_char_ref_submit_parity_durability.sh`, deploy fleet build-sha parity, live session GET + blocked submit proof.

---

## Structural fix (no patches)

### Invariants

1. **`char_ref_aligned_for_intent_commit`** — strict byte match when registry carries `frontal_sha256` (includes `auto_migrate_v1` stamps, not only explicit `visual_canonical_locked`).
2. **`resolve_beat_element_char_ref_gate`** — delegates to submit authority; **never** trusts persisted `element_char_ref_ok`; **never** uses looser pose-dir fallback than submit.
3. **`element_char_ref_gate` / `sync_element_char_ref_status`** — same authority for sidecar persistence (write path only).
4. **Session GET** — `_derived.element_char_ref_ok` / `can_generate` recomputed; top-level `element_char_ref_ok` mirrored from `_derived` on enrich.
5. **UI** — `beatElementCharRefOk` already prefers `_derived`; Generate pending only after preflight; explicit toast on `ELEMENT_REGISTRATION_FAILED` / `ELEMENT_VISUAL_MISMATCH`.

### Explicit non-goals

- No beat-specific Event_6 heal scripts.
- No re-expansion of `promote_frontal` / auto-register on Generate click.
- No read-time sidecar mutation on session GET.

### Operator unblock (data, not code)

When gate blocks: **Set as Element identity** on desired pose, or **Align char ref** to canonical frontal — then Generate.

---

## Verification matrix

| Layer | Command / check | Pass criteria |
|-------|-----------------|---------------|
| Unit | `pytest test_operator_workbench_contract.py test_element_visual_canonical_lock.py` | Stale `element_char_ref_ok: true` → `_derived.can_generate false` when bytes mismatch |
| Durability | `verify_element_char_ref_submit_parity_durability.sh` | Single authority wired; no stale-trust grep |
| Deploy | `deploy_storyboard_v59.sh --event Event_6` + fleet build-sha | All `:5111–5116` match HEAD |
| Live | curl session-state beat 2 | `_derived.can_generate=false`, error mentions canonical / Element |
| Visual | Beat Gen card beat 2 | Generate disabled; inline char-ref hint visible |

---

## Related specs

- `TECH_SPEC_ELEMENT_CHAR_REF_AUTHORITY_v1.md` (2026-07-04 — drop/register path)
- `TECH_SPEC_ELEMENT_VISUAL_CANONICAL_LOCK_v1.md` (frontal bytes + set_element_identity)
