# TECH_SPEC — Operator Pipeline Closure Audit v1

**Marker:** `OPERATOR_PIPELINE_CLOSURE_AUDIT_V1`  
**Status:** In progress → closure sign-off when master sheet all-green + deploy proof  
**Branch:** `audit/operator-pipeline-closure-v1` (renamed from `fix/four-files-sfx-live-preview`)  
**Master sheet:** `Production/docs/OPERATOR_PIPELINE_CLOSURE_MASTER_v1.md`  
**Session durability (Kim memory):** `Production/docs/SESSION_DURABILITY_OPERATOR_CLOSURE_20260703.md`

---

## 1. Goal

Map every remaining operator bug class → named ID → code location → durability gate → live proof. Close P0/P1 in this arc; defer P2 architectural debt with explicit risk acceptance — **no chat-only diagnosis**.

## 2. Agent debates (3×3) — decisions locked

### 2.1 Branch strategy

| WI | Option | Verdict |
|----|--------|---------|
| Rename to `audit/operator-pipeline-closure-v1` | Keeps 2 SFX commits; audit PR readable | **FOR** |
| Stay on `fix/four-files-sfx-live-preview` | Mixes naming | Against |
| Work on `main` | Loses prerequisite commits | Against |

**Verdict:** Rename branch; commit WIP that closes `stitch_mux_preview_lineage` + `stitch_slot_playback_mp4` partial registry rows before deploy.

### 2.2 Live proof scope (Option C — tiered)

| Layer | Scope |
|-------|--------|
| **Automated** | All `:5111–5116` build-sha + fleet curl + `phase_e_hydrate_live` + `verify_live_fleet_interaction` |
| **Deep manual** | **Mandatory:** Event_4 `:5114` (export-truth incident site), Event_1 `:5111` (intro/canonical tail). **Recommended:** Event_3 `:5113` (still-insert class) |
| **Out of deep scope** | Event_5/6 until Arc 1 production |

### 2.3 Fix batching vs Kim memory

| Concern | Mitigation |
|---------|------------|
| Forgetting where we were | **One markdown master sheet** updated every pass — not chat |
| Weeks vanishing | **Commit per pass** with `audit(passN):` prefix + gate output in master sheet |
| Splitting work loses context | **Single branch, single PR** — phases are commits inside one arc, not separate weeks |
| Architectural debt forgotten | Master sheet **Deferred** section with ID + risk + target spec — never silent |

**Fix scope this arc:** P0 + P1 (operator blockers + partial registry rows). L1-ASYNC class → deferred with gate stub, not silent.

---

## 3. Five-pass method

| Pass | Deliverable | Gate |
|------|-------------|------|
| P1 | Master closure sheet | Inventory reconcile |
| P2 | Authority scan | `audit_authority_duplicates.sh --strict-subset` |
| P3 | Session merge | `verify_operator_edit_surfaces_durability.sh` |
| P4 | Export truth | `verify_operator_export_truth_closure_durability.sh` |
| P5 | Live fleet | `verify_fast_and_flawless_done.sh` + deep Event_4/1 |

---

## 4. Proof log (2026-07-03)

| Check | Result | Evidence |
|-------|--------|----------|
| Fleet build-sha vs git | PASS (pre-WIP commit) | All `:5111–5116` = `ac7e79c` |
| `verify_fast_and_flawless_done.sh` | PASS | `/tmp/faf_audit_run.log` — live pass 9 green, DROP-WC-LIVE-1 |
| Authority strict audit A–L | PASS | `audit_authority_duplicates.sh --strict-subset` |
| Operator edit surfaces | PASS | Tier D hooks present + gate green |
| Export truth closure | PASS | FF-022–026 sub-gates |
| Registry partial rows | **2 open pre-commit** | `stitch_mux_preview_lineage`, `stitch_slot_playback_mp4` — WIP closes |

---

## 5. Deferred (P2 — not operator-blocking this arc)

| ID | Issue | Risk | Target |
|----|-------|------|--------|
| L1-ASYNC | Workers without typed `beatgen_scope_ctx` on all paths | Cross-event race | Beat Gen Category Fix Arc Session 3 |
| L1-MUTATE | `mutate_sidecar_locked` no scope param | Weaker audit trail | Same |
| MAGIC-DO | Three display_order writers | Magic field prune | Magic consolidation PR |
| DATA-KLING | Dual status fields | Label drift | Phase 2 write-cache |
| OPS-ORPHAN | Orphan clips on disk | WARN only | Ops cleanup |
| DROPBOX-CONFLICT | Conflicted copies in Event_* | Sidecar parse risk | Kim cleanup |

**Closed since 2026-06-28 audit:** BG-INSERT scope guard (audit L green), magic writeback consolidated (audit K green).

---

## 6. Sign-off criteria

- [x] WIP committed + deployed; fleet build-sha = `23b969f`
- [x] Registry partial rows → `shipped` (0 partial in authority_registry.py)
- [x] Master sheet P0/P1 green
- [x] Live SFX TRUTH-LIVE-1 green post-deploy
- [ ] Full FaF re-run on `23b969f` (prior run timed out mid-pass — non-blocking; pre-WIP FaF fully green)
