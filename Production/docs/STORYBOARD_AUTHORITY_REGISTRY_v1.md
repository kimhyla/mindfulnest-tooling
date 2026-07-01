# Storyboard Authority Registry v1

**Status:** Active — 2026-06-28  
**Marker:** `STORYBOARD_AUTHORITY_REGISTRY_V1`  
**Machine index:** `Production/tools/authority_registry.py`  
**Durability gate:** `Production/scripts/verify_authority_registry_durability.sh`

---

## Why this exists

Most Storyboard / Beat Gen / Stitcher regressions share one root cause:

> **Two or more places each believe they decide the same concept**, with no declared winner.

Examples: `kling_o3_status === 'approved'` vs active clip on disk; client scope vs server pin; `video_dur_ms ?? 30s` vs mux duration; GET-sidecar heal vs disk truth.

This registry is the **concept index** — not a function audit. Each row names **one authority** for one operator-facing question.

---

## How to read a row

| Column | Meaning |
|--------|---------|
| **Concept** | The question operators care about |
| **Shape** | `disk` = file/path wins · `derived` = computed on read · `explicit_approve` = human gate required |
| **Read gate** | Only function/module that may enable export, playback, or blocking UI |
| **Write path** | Function(s) that may pin the authoritative value |
| **Status** | `shipped` = contract enforced in CI · `partial` = spec exists, wiring incomplete · `debt` = known duplicate predicates remain |

**Rule for new features:** If a PR adds a button enable or export gate, it must either call an existing read gate or add a registry row + contract module in the same PR.

---

## Registry

### Scope & partition

| Concept | Shape | Read gate | Write path | Status | Spec |
|---------|-------|-----------|------------|--------|------|
| **event_scope** — authoritative `event_id` on dedicated port | derived | Client: `readAuthoritativeEventId` · Server: dedicated port pin | `syncAuthoritativeClientScope`, server `event/load` 409 | shipped | `SCOPE_CLIENT_AUTHORITY_SPEC_v1.md` |
| **beatgen_scope_partition** — which DB/JSON owns this beat | disk | `BeatGenScope` / `scope_from_app` | `beatgen_scope_ctx` on HTTP + async workers | shipped | `TECH_SPEC_BEATGEN_TRUTH_STACK_V1.md` |
| **sqlite_sidecar_authority** — beat rows authoritative store | disk | `sqlite_authority_enabled()` | per-event `beatgen_eventN.db` | shipped | `TECH_SPEC_BEATGEN_PER_EVENT_SQLITE_V1.md` |
| **build_sha_drift** — stale JS bundle vs server | derived | `checkBuildShaDrift` | deploy writes bundled sha | shipped | `SCOPE_CLIENT_AUTHORITY_SPEC_v1.md` |

### Beat Gen operator workbench

| Concept | Shape | Read gate | Write path | Status | Spec |
|---------|-------|-----------|------------|--------|------|
| **operator_still_scene** — Ken Burns source PNG | disk | `resolve_beat_still_scene_abs_path` | `write_still_scene_source` | shipped | `BG_OPERATOR_WORKBENCH_AUTHORITY_SPEC_v1.md` |
| **operator_display_prompt** — textarea text | derived | `_derived.display_prompt` via `active_beat_prompt_for_generation_mode` | mode-specific stored fields; **never** heal `kling_o3_prompt` on GET | shipped | same |
| **o3_gallery_active_clip** — active delivery pointer | disk | `resolve_o3_gallery_option` + `kling_o3_video_path` | `finalize_kling_delivery_clip`, `normalize_o3_gallery_options` | shipped | `TECH_SPEC_OPERATOR_EXPORT_TRUTH_CLOSURE_V1.md` |
| **o3_gallery_option_identity** — gallery key ↔ path | disk | `resolve_o3_gallery_option` | `normalize_o3_gallery_options` | shipped | same |
| **o3_clip_audio_contract** — still/O3 audio shape | disk | `probe_o3_clip_audio_contract` | `stamp_o3_option_audio_contract` | shipped | same |
| **o3_job_busy** — block edits during generation | derived | `beat_o3_operator_busy` / `beatO3JobBusy` | terminal.json + `o3_current_job_id` lifecycle | shipped | same |
| **kling_stitch_export_ready** — Send to Stitcher per beat | disk | `beat_kling_stitch_export_ready` / `beatKlingStitchExportReady` | `finalize_kling_delivery_clip`, `sync_kling_stitch_status_from_active_clip` | shipped | `kling_stitch_readiness.py` |
| **still_insert_stitch_approve** — still beat export gate | explicit_approve | same contract (still branch) | `kling_o3_still_stitch_approved` | shipped | same |
| **kling_o3_export_trim** — trim window materialized on export | disk | `prepare_beats_for_stitch_export` | `set_o3_option_trim` | shipped | `beat_generator.py` |
| **magic_render_visible** — magic sparkle contract | disk | `magic_render_contract` compositor kwargs + durability tests | `write_magic_delivery` | shipped | `HOW_TO_MAKE_VISIBLE_MAGIC.md` |
| **bg_export_stitcher_job** — async BG→Stitcher job truth | disk | `readBgExportBusyLatch` + poll terminal | export job API | shipped | inline `BG_EXPORT_TO_STITCHER_ASYNC_V1` |
| **o3_job_truth_stack** — terminal/disk/sidecar read parity | derived | `resolve_beat_o3_truth` | `close_o3_attempt` | shipped | `TECH_SPEC_CROSS_PIPELINE_G1_G8_CLOSURE_v1.md` |
| **o3_failed_redo_heal** — restore prior clip after failed regen | disk | `restore_last_good_o3_delivery_after_failed_attempt` | same | shipped | same |
| **o3_subprocess_lifecycle** — shutdown finalize live jobs | explicit_approve | `load_intent_terminal` | `finalize_live_o3_jobs_before_shutdown` | shipped | same |
| **cr_library_milestone_scope** — library CR event_dir on milestone | derived | `_resolve_cr_library_scope` | `assert_production_scope` | shipped | same |
| **directus_has_crop_disk_fallback** — has_crop when Directus slow | disk | `_enrich_has_crop_from_disk` | same | shipped | same |
| **library_client_cache_coherence** — bust sessionStorage after mutations | derived | `invalidateLibrarySessionCache` | crop/upload/delete handlers | shipped | same |
| **bg_o3_stitch_export_lineage** — invalidate stitch preview on export change | derived | `compute_bg_segment_o3_export_lineage_sig` | `invalidate_stitch_slots_for_o3_export_change` | shipped | same |

### Stitcher

| Concept | Shape | Read gate | Write path | Status | Spec |
|---------|-------|-----------|------------|--------|------|
| **stitch_slot_timeline_dur** — rail/SFX geometry duration | derived | `stitchSlotTimelineDurMs` / `export_clip_timeline_duration_s` | ffprobe on load_job; persist `video_dur_ms` | shipped | `TECH_SPEC_OPERATOR_EXPORT_TRUTH_CLOSURE_V1.md` |
| **stitch_export_timeline_duration** — BG export concat duration | derived | `export_clip_timeline_duration_s` | `normalize_for_concat` | shipped | same |
| **stitch_mux_preview_lineage** — post-export playback artifact | disk | `stitch_slot_needs_playback_artifact_bake` | `ensure_stitch_slot_playback_artifacts_on_export` | partial | same |
| **stitch_ambient_loop_seam_budget** — ambient loop seams | derived | `build_ambient_bed_filter_lane` | `STITCH_AMBIENT_FULL_PERIOD_TILE_V2` | shipped | same |
| **stitch_playback_url** — composer video when SFX exist | derived | `resolveSlotPlaybackPreviewUrl` | mux artifact bake | shipped | `TECH_SPEC_STITCH_SFX_PLAYBACK_TRUTH_V1.md` |
| **stitch_single_owner** — who mutates slot video post-export | disk | `STITCH_SINGLE_OWNER_V1` load_job read-only | export path owns ingest | shipped | `TECH_SPEC_STITCH_SINGLE_OWNER_V1.md` |

### Phase producer (Tier D — operator edit surfaces)

| Concept | Shape | Read gate | Write path | Status | Spec |
|---------|-------|-----------|------------|--------|------|
| **phase_watercolor_cue_geometry** — waveform cue markers during edit + refresh | disk | `mergeWatercolorCuesOnHydrate` / `usePhaseWatercolorCues` | `v2_module_patch` → `phase_*_watercolor_cues_json` | shipped | `TIER_D_OPERATOR_EDIT_SURFACES_v1.md` |
| **phase_stem_cut_geometry** — stem cut handles during edit + refresh | disk | `mergeOperatorFieldOnHydrate` / `usePhaseStemCut` | `v2_module_patch` → `phase_*_voice_stem_cut_*_s` | shipped | `TECH_SPEC_OPERATOR_EDIT_AUTHORITY_v1.md` |
| **phase_script_draft** — script textarea during poll/focus refresh | disk | `useProtectedPromptField` | `v2_module_patch` → `phase_*_script` | shipped | `TECH_SPEC_OPERATOR_EDIT_AUTHORITY_v1.md` |
| **stitch_sfx_cue_geometry** — slot SFX rail geometry | disk | `mergeStitchJobSlotsClientPatch` | `stitch_save_job` slot `sfx_cues` | shipped | `TECH_SPEC_STITCH_TRUTH_CONTRACT_V2.md` |

---

## Allowed non-gate uses (not duplicate authority)

These read sidecar fields for **display/heal**, not export gates:

- **Gallery slot placement** (`BgTab` `kling_o3_status === 'approved'` when pinning active clip into option row UI)
- **Stale lipsync error suppression** (approved + clip on disk → hide hosting error banner)
- **Still-insert demotion** (`normalize_still_insert_approval_status`)
- **Pin approved delivery** (`auto_pin_approved_kling_o3_delivery`) — *debt: should call stitch contract*

---

## Known debt (tracked, not CI-fatal yet)

| Item | Issue | Target fix |
|------|-------|------------|
| BeatGenScope on every handler | globals can tear mid-session | Truth Stack Layer 1 |
| Magic writeback | partition + sidecar parallel paths | single `write_magic_delivery()` |
| `auto_pin_approved_kling_o3_delivery` | ~~checks raw `kling_o3_status`~~ | **fixed** — uses `beat_kling_stitch_export_ready` |
| BG export stitcher bootstrap | new async path | finish `verify_event_stitch_job_bootstrap_durability` wiring |
| `beatPromptText` in BgTab | ~~read `kling_o3_prompt` directly~~ | **fixed** — prefers `_derived.display_prompt` |

---

## Enforcement

| Layer | What |
|-------|------|
| **Machine registry** | `authority_registry.py` — concept ids, markers, forbidden client patterns |
| **Durability script** | `verify_authority_registry_durability.sh` — multipass grep + pytest bundle |
| **Session deploy** | wired into `verify_storyboard_session_durability.sh` |
| **Parity tests** | per-concept pytest/vitest (stitch, O3 job, scope, operator workbench) |

When superseding a concept, update this doc, `authority_registry.py`, and the durability script in the **same change** that removes the old predicate.
