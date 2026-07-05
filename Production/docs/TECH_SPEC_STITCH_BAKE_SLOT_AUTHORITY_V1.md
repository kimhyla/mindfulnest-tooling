# TECH_SPEC — Stitch Bake Slot Authority v1

**Status:** Implementing  
**Marker:** `STITCH_BAKE_SLOT_AUTHORITY_V1`  
**Extends:** `TECH_SPEC_STITCH_SINGLE_OWNER_V1.md`, `STORYBOARD_AUTHORITY_REGISTRY_V1`  
**Closes:** Event 3 Phase B slot overwrite on module bake (pipeline hash `de1b5803…` replacing operator-pinned `cedric_trim_v6`)

---

## 1. Problem class

> **Module bake was a hidden writer for `phase_b` stitch slot**, overwriting the operator's current slot (what Stitcher UI shows) with an auto-rebuilt pipeline hash preview before concat.

Symptoms:

- Operator pins manual trim (v6) → UI shows v6 → bake lands untrimmed Phase B (~204.8s).
- `_stitch_module_bake_audit.jsonl` shows `SLOT_CONTEXT` always using `phase_b_preview_de1b5803…` after every `BAKE_REQUEST`.

Root cause (authority split):

| Writer | When | Intended? |
|--------|------|-----------|
| `handle_phase_export_stitcher` / Send to Stitcher | Operator clicks Export | **Yes** |
| `update_stitch_slot_optional` (hold-insert tool) | Operator pins file | **Yes** |
| `stitch_save_job` | Operator saves slot edits | **Yes** |
| `ensure_phase_b_stitch_slot_for_bake` | Every module bake | **No** — violated STITCH_SINGLE_OWNER |

---

## 2. Invariant (STITCH_BAKE_SLOT_AUTHORITY_V1)

**What Stitcher UI shows for `phase_b` is what module bake uses.**

| Phase | Role |
|-------|------|
| **Read gate** | `validate_phase_b_stitch_slot_authority(h, job_name=…)` — read-only; returns current slot paths if on disk |
| **Bake preflight** | Lipsync delivery finalize (unchanged) + slot validation — **must not** call `stitch_upsert_event_slot` |
| **Write paths** | Unchanged from STITCH_SINGLE_OWNER: explicit export / pin / save only |

---

## 3. Blast radius

| Area | Risk | Mitigation |
|------|------|------------|
| **Module bake (all events)** | Bake fails if `phase_b` slot empty or paths missing | Clear error: "export Phase B to Stitcher first"; audit `PHASE_B_SLOT_AUTHORITY_FAILED` |
| **Stale sub-720 slot** | Operator could bake old slot if never re-exported | **By design** — UI = truth; operator must export when lipsync changes |
| **Milestone bakes** | Unaffected — preflight already skipped for milestone jobs |
| **Phase B Send to Stitcher** | Unchanged — still rebuilds pipeline export and upserts slot (explicit operator action) |
| **Lipsync delivery sharpen** | Unchanged — preflight still runs `finalize_phase_module_lipsync_delivery` when profile stale |
| **Client / JS bundle** | No client change | Server-only fix |
| **Existing canonical bakes** | Not retroactive | Re-bake after pinning correct slot |

---

## 4. Implementation map

| File | Change |
|------|--------|
| `server_handlers/phases.py` | Add `validate_phase_b_stitch_slot_authority`; demote `ensure_phase_b_stitch_slot_for_bake` to validate-only |
| `server_handlers/stitch_editor.py` | Pass `job_name`; progress text; audit `PHASE_B_SLOT_AUTHORITY_VALIDATED` |
| `authority_registry.py` | New concept `stitch_bake_slot_authority` |
| `STORYBOARD_AUTHORITY_REGISTRY_v1.md` | Registry row |
| `TECH_SPEC_STITCH_SINGLE_OWNER_V1.md` | Remove bake preflight from write paths |
| `tests/test_stitch_bake_slot_authority_v1.py` | Behavioral + source guards |
| `scripts/verify_stitch_bake_slot_authority_durability.sh` | Pre-deploy gate |

---

## 5. Verification

1. **Unit:** pinned v6 slot → preflight validates → `stitch_upsert_event_slot` not called → paths unchanged.
2. **Unit:** empty slot → preflight fails with actionable error.
3. **Durability script:** grep markers; pytest bundle.
4. **Deploy:** fleet build-sha parity on :5111–:5116.
5. **Live (Event 3):** pin v6 → module bake → audit `SLOT_CONTEXT` shows v6 dry, not `de1b5803`.

---

## 6. Audit events

| Event | When |
|-------|------|
| `PHASE_B_SLOT_AUTHORITY_VALIDATED` | Slot paths exist; bake proceeds |
| `PHASE_B_SLOT_AUTHORITY_FAILED` | Slot empty or paths missing |
| `PHASE_B_PREFLIGHT_FAILED` | Legacy wrapper when `ensure_phase_b_stitch_slot_for_bake` returns not ok |
