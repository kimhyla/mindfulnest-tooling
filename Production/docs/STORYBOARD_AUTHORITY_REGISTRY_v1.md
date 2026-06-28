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
| **o3_gallery_active_clip** — active delivery pointer | disk | `kling_o3_video_path` + `is_user_selectable_o3_video` | `finalize_kling_delivery_clip` | shipped | `BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1.md` |
| **o3_job_busy** — block edits during generation | derived | `beat_o3_operator_busy` / `beatO3JobBusy` | terminal.json + `o3_current_job_id` lifecycle | shipped | same |
| **kling_stitch_export_ready** — Send to Stitcher per beat | disk | `beat_kling_stitch_export_ready` / `beatKlingStitchExportReady` | `finalize_kling_delivery_clip`, `sync_kling_stitch_status_from_active_clip` | shipped | `kling_stitch_readiness.py` |
| **still_insert_stitch_approve** — still beat export gate | explicit_approve | same contract (still branch) | `kling_o3_still_stitch_approved` | shipped | same |
| **magic_render_visible** — magic sparkle contract | disk | `magic_render_contract` compositor kwargs + durability tests | `write_magic_delivery` | shipped | `HOW_TO_MAKE_VISIBLE_MAGIC.md` |
| **bg_export_stitcher_job** — async BG→Stitcher job truth | disk | `readBgExportBusyLatch` + poll terminal | export job API | shipped | inline `BG_EXPORT_TO_STITCHER_ASYNC_V1` |

### Stitcher

| Concept | Shape | Read gate | Write path | Status | Spec |
|---------|-------|-----------|------------|--------|------|
| **stitch_slot_timeline_dur** — rail/SFX geometry duration | derived | `stitchSlotTimelineDurMs` / `ensure_stitch_slot_timeline_dur_ms` | ffprobe on load_job; persist `video_dur_ms` | shipped | `TECH_SPEC_STITCH_TRUTH_CONTRACT_V2.md` |
| **stitch_playback_url** — composer video when SFX exist | derived | `resolveSlotPlaybackPreviewUrl` | mux artifact bake | shipped | `TECH_SPEC_STITCH_SFX_PLAYBACK_TRUTH_V1.md` |
| **stitch_single_owner** — who mutates slot video post-export | disk | `STITCH_SINGLE_OWNER_V1` load_job read-only | export path owns ingest | shipped | `TECH_SPEC_STITCH_SINGLE_OWNER_V1.md` |

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
