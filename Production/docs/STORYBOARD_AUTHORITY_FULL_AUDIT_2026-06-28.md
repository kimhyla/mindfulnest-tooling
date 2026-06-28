# Storyboard Authority — Full Audit (2026-06-28)

**Marker:** `STORYBOARD_AUTHORITY_FULL_AUDIT_2026-06-28`  
**Scope:** Beat Gen · Storyboard · Stitcher · Magic · Scope · Truth Stack  
**Branch baseline:** `fix/prompt-contradiction-gallery-closure` @ `82e8eff` — Tier C complete 2026-06-28

---

## Executive summary

| Layer | Status | Notes |
|-------|--------|-------|
| **Kling / Send to Stitcher** | ✅ Shipped | Single contract; CI strict audit A–L |
| **O3 job busy / gallery / prompt** | ✅ Shipped | Contract modules + client mirrors |
| **Stitch timeline / playback / single-owner** | ✅ Shipped | Atomic dur + mux-first URL |
| **Scope / event pin / build-sha** | ✅ Shipped | Dedicated port + client authority |
| **Magic render (compositor)** | ✅ Shipped | `magic_render_contract` + brightness fix |
| **Magic writeback** | ✅ Shipped | `write_magic_delivery()` — still/video/clear/assign |
| **BeatGenScope Layer 1** | ✅ Shipped | HTTP `_in_beatgen_scope` + async scope JSON on workers |
| **Data model (kling status fields)** | ✅ Documented | Write-cache spec; export uses disk authority |
| **Waveform time authority** | ✅ Shipped | WTA-1/SEEK-3 — e2e green |
| **Deploy / fleet** | ✅ Shipped | Fanout bundle + launchd cold-boot smoke |

**Bottom line:** Tier C closed. Regression locks in CI. See `TIER_C_FINAL_REPORT_2026-06-28.md` and `TIER_C_OPERATOR_MATRIX_2026-06-28.md`.

---

## Known debt (post–Tier C — tracked, non-blocking)

| ID | Issue | Status |
|----|-------|--------|
| OPS-ORPHAN | Orphan `kling_o3_clips` on disk without sidecar pointer | WARN in deploy smoke; ops cleanup |
| PERF-E2 | Event_2 intro session-state ~22s after cold boot | Within 120s gate; monitor |
| DATA-KLING-P2 | Remove redundant status reads in UI labels only | Phase 2 spec; export already disk-authoritative |

---

## What we found (real bugs / duplicate authorities)

### Fixed and CI-gated

1. **Send to Stitcher vs `kling_o3_status`** — server promoted clip on disk; client required status string → button dead.
2. **Duplicate `job_busy` predicate** in `bgStitchExport.ts`.
3. **`auto_pin`** gated on raw status instead of `beat_kling_stitch_export_ready`.
4. **Prompt textarea** read `kling_o3_prompt` instead of `_derived.display_prompt`.
5. **O3 submit latch** used status instead of `beatHasActiveO3DeliveryClip`.
6. **Server heal/reconcile** wrote `approved` outside `kling_stitch_readiness`.
7. **Pipeline finalize dict literals** in arlo/element/avatar pipelines.
8. **Event 3 magic brightness** — compositor gain/sign wrong for resolution sparkle visibility.

### Fixed in this follow-up (not yet on main)

9. **Magic writeback twin handlers** — ~260 lines duplicated between `handle_magic_still` / `handle_magic_video`; consolidated into `write_magic_delivery()` (partition-first, no sidecar-only 200).
10. **BeatGenScope dead code** — `beatgen_scope_ctx` existed but was never entered on HTTP; `_in_beatgen_scope` wraps 29 `/api/bg/*` POST routes + magic routes.

### Still open (architectural debt)

| ID | Issue | Risk | Target fix |
|----|-------|------|------------|
| L1-ASYNC | O3/Kling async workers, startup recover, export worker call `mutate_sidecar_locked` / `update_beat_locked` without typed scope | Cross-event sidecar contamination under race | Serialize `MN_BEATGEN_SCOPE_JSON` at job submit; enter scope in worker |
| L1-MUTATE | `mutate_sidecar_locked` has no scope param / mutation log | Weaker than `update_beat_locked` | Add `scope=` + `log_beatgen_mutation` parity |
| MAGIC-CLEAR | `handle_clear_magic_still`, `_handle_assign_image` clear paths bypass `write_magic_delivery` | display_order prune / split-brain | Route through `write_magic_delivery(clear_*)` |
| MAGIC-DO | Three `display_order` writers (BG segment sync, per-magic append, v2 patch replace) | Prune drops magic fields | Single `sync_partition_display_order_from_bg()` write path |
| DATA-KLING | `kling_o3_status` + `status` duplicate disk truth for O3 beats | Drift; heal on GET | Phase 2: status fields write-cache only; export never reads status for non-still beats |
| BG-INSERT | `handle_bg_insert_beat` missing `_assert_event_scope` | Scope leak | Add guard + scope wrapper |
| STITCH-EMPTY | `DEFAULT_SLOT_DUR_MS * 4` when job has no slots | Informational empty rail only | OK — not per-slot truth |

---

## Registry row-by-row

| Concept | Was | Now |
|---------|-----|-----|
| kling_stitch_export_ready | debt → | **shipped** |
| o3_gallery_active_clip | partial → | **shipped** (finalize path) |
| operator_display_prompt | debt → | **shipped** |
| magic_render_visible (compositor) | partial → | **shipped** |
| magic writeback | partial → | **partial+** (`write_magic_delivery`) |
| beatgen_scope_partition | partial → | **partial+** (HTTP wrapper) |
| bg_export_stitcher_job | partial → | **partial** (durability wired) |

---

## Gating vs simplification — decision log

| Question | Answer |
|----------|--------|
| Is gating the fix for stitch export? | **Yes** — one read gate (`beat_kling_stitch_export_ready`) replaces competing predicates. Not “another button check.” |
| Can we delete `kling_o3_status`? | **Not yet** — still-insert uses explicit approve; status is still stored for gallery UI labels. Export for O3/element beats already ignores status when disk clip + not busy. |
| Is sidecar fallback 200 on magic verify a patch? | **Yes** — removed; partition verify fail → 500. Sidecar is mirror only. |
| Is `_assert_event_scope` + rebind enough for Layer 1? | **No** — rebind sets globals; typed `BeatGenScope` object + context manager required for async/subprocess parity. HTTP wrapper is step 1. |

---

## Verification matrix (Tier C — 2026-06-28)

| Gate | Result |
|------|--------|
| `audit_authority_duplicates.sh --strict-subset` | PASS A–L |
| `verify_authority_registry_durability.sh` | PASS |
| `verify_storyboard_session_durability.sh` | PASS |
| GitHub CI e2e + CodeQL | PASS |
| Visual Event_1/2/3 + milestone | PASS — operator matrix doc |
| Fleet deploy 5111–5116 | PASS |
