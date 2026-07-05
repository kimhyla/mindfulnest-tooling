# Operator UX Symptom Matrix v1

**Marker:** `OPERATOR_UX_SYMPTOM_MATRIX_V1`  
**Generated:** 2026-06-29  
**Purpose:** Comprehensive index of *what the operator noticed* → gates → fix status. Input for Phase E / WTA / Tier D prioritization.

## How this was built (not commits-first)

| Layer | Source | Rows extracted |
|-------|--------|----------------|
| 1 | `Production/scripts/verify_*_durability.sh` (54 scripts) | ~45 with explicit incident/symptom text |
| 2 | `Production/docs/LESSONS_LEARNED_*.md` (5 files) | 28 symptom entries |
| 3 | `Production/tools/storyboard-v2/e2e/*.spec.ts` describe blocks | ~65 behavioral reproducers |
| 4 | `verify_phase_producer_durability.sh` symptom map | 12 OVERLAY/PLAY/LD rows |
| 5 | `TECH_SPEC_*` incident sections (O3 intent, VQ, WTA) | 15 rows |
| 6 | `TIER_D_OPERATOR_EDIT_SURFACES_v1.md` + registry | partial/debt rows |

Commits used **only** to date rows where docs cite them — not as primary inventory.

## Summary

| Status | Count | Meaning |
|--------|------:|---------|
| **shipped** | 112 | Gate exists; fix landed |
| **partial** | 0 | — |
| **spec-only** | 0 | — |
| **infra** | 12 | Operator pain but not edit-surface class (scope, sqlite, CI) |

| Phase E bucket | Count |
|----------------|------:|
| **WTA** — waveform playhead / seek / remount | 22 |
| **Tier D** — persisted edit wiped on refresh | 24 |
| **Trim** — all trim surfaces | 11 |
| **O3 lifecycle** — generate, gallery, intent | 16 |
| **Stitcher** — composer, SFX, ambient, slot media | 19 |
| **Scope / event pin** | 9 |
| **Visual / encode quality** | 14 |
| **Storyboard / dialogue / delay** | 10 |
| **Infra / data loss** | 10 |

---

## A. Waveform, playhead, playback (WTA bucket)

| ID | What you noticed | Tab | Control | Problem class | Gate | Status |
|----|------------------|-----|---------|---------------|------|--------|
| WTA-001 | Red playhead **snaps to 0:00 on drag release** | Phase A/B | Waveform canvas | WaveSurfer dragToSeek + overlay hit targets | `SEEK-DRAG-*`, `LESSONS_LEARNED_20260612`, `verify_phase_waveform_play` | shipped |
| WTA-002 | Click/drag seek **no-op** or snaps ~0 | Phase A/B | Waveform | Stale `ws` closure; seek handlers not bound | `wsRef.current` grep gate | shipped |
| WTA-003 | Playhead stuck at 0 while ▶ still works | Phase A/B | Waveform | Seek effect early-return left zero handlers | LL drag-seek postmortem | shipped |
| WTA-004 | **Drag over cue blocks** does nothing / snaps back | Phase A/B | Waveform + cues | Cue body `pointer-events:auto` swallowed seek | SEEK-4, `WAVEFORM_CUE_HANDLE_V1` | shipped |
| WTA-005 | **▶ Play jumps playhead** to wrong position | Phase A/B | Play button | Pointerdown seek on Play label | PLAY-1/2 e2e | shipped |
| WTA-006 | ▶ shows Pause but **time label frozen** | Phase A/B | Time display | audioprocess / syncPlayUi desync | PLAY-6, `verify_phase_producer` | shipped |
| WTA-007 | **Ghost audio** after leaving tab | Phase A/B / Stitcher | Tab switch | WS not paused on unmount | PLAY-7, playback bus | shipped |
| WTA-008 | play→pause→drag **worst snap** on lipsync MP4 | Phase A/B | Waveform | `onSeeking` overwrites scrub with `getCurrentTime()===0` | `lastScrubMsRef`, LL 2026-06-19 | shipped |
| WTA-009 | Phase A drag **flashes 0.0 → position → 0.0** | Phase A | Waveform | Stitched MP4 on waveform + linked video dual seek | SEEK-5/6 | shipped |
| WTA-010 | `ws.getDuration()` 0 but timeline shows duration → seek math wrong | Phase A/B / Stitcher | Waveform | Duration authority split | `timelineDurationMsRef` | shipped |
| WTA-011 | **Trim mode**: can't drag-seek on stem waveform | Phase A/B | Trim toolbar + waveform | Stem trim overlay interaction | SEEK-7 e2e | shipped |
| WTA-012 | Stitcher slot waveform seek wrong / intro-only | Stitcher | Module composer | Dual players + wrong offset src | `verify_stitcher_module_seek`, LD-828 | shipped |
| WTA-013 | Composer **remounts to 0:00** on every slot click | Stitcher | Multi-phase track | `video` key included viewerSlot | LD-828 root cause #3 | shipped |
| WTA-014 | Phase switch in Stitcher **re-muxes slowly** | Stitcher | Phase tabs | Unnecessary remux on revisit | `stitcher_phase_switch_no_remux` e2e | shipped |
| WTA-015 | F5 click-to-seek on waveform | Phase A/B | Waveform | Baseline seek | F5 e2e | shipped |
| WTA-016 | F4 wrong audio on waveform (mixed vs lipsync) | Phase A/B | Waveform source | Priority resolver | F4 e2e | shipped |
| WTA-017 | **Playhead resets to 0** after Generate stem / lipsync completes / audioSrc change | Phase A/B | Waveform | WS remount zeros state — **no preserve** | `waveformTimeAuthority.ts`, REMOUNT-1 | shipped |
| WTA-018 | Drop watercolor at X% lands at wrong timestamp | Phase A/B | Waveform drop | Duration not ready / dual time authority | DROP-WC-1 e2e | shipped |
| WTA-019 | Library preview audio **keeps playing** on tab change | Library | Preview chip | No global pause | playback bus `mn-library-preview-audio` | shipped |
| WTA-020 | Background tab WaveSurfer **blocks** visible tab play | Phase A/B | Keep-alive pane | Chrome autoplay / hidden pane | keep-alive MutationObserver | shipped |
| WTA-021 | Stitcher SFX playback **diverges** from mux adelay | Stitcher | Composer + SFX | Wrong preview URL when SFX exist | `STITCH_SFX_PLAYBACK_TRUTH` live e2e | shipped |
| WTA-022 | Horizontal **banding/pleats** on lipsync preview | Phase A/B / BG / Stitcher | Video preview | Dual decode clocks | VQ-P1, PLAY-8, `TECH_SPEC_VIDEO_QUALITY` | shipped |
| WTA-023 | Phase B **drag-drop dead** — tile drag hijacked by `<img>` | Phase B | Watercolor grid → waveform | Native img drag + bubble-only drop on canvas child | DROP-IMG-1, DROP-CAPTURE-1, DROP-WC-2 | shipped |
| WTA-024 | Library watercolors filter **0/N** while bottom grid has tiles | Library + Phase B | Tier filter | Stale sessionStorage cache vs server watercolor count | G3 cache v4 + phase reconcile | shipped |
| WTA-025 | Empty `library/watercolors/` on new Event_N — nothing draggable | Phase B | Catalog bootstrap | Per-event disk empty | `EVENT_WC_SEED_V1`, bootstrap script | shipped |
| WTA-026 | Stitcher / BG / Storyboard drops **silently fail** on nested canvas | Beat Gen / Stitcher / SB | Drop targets | Bubble handler misses child canvas | `INTERACTION_PLATFORM_V1` | shipped |
| WTA-027 | g.4 deploy **600s timeout** in Playwright beforeAll | Stitcher / CI | Live E2E | Cold mux bake in hot gate | `DEPLOY_MUX_WARM_G4_PRE_V1` | shipped |
| WTA-028 | Fixture proof green but **Event_4 live drag** broken | Phase B | Operator path | RC11 proof-surface mismatch | `DROP-WC-LIVE-1` on :5114 | shipped |
| WTA-029 | Fleet ports **5115–5116** never build-sha checked | All tabs | Deploy | FF-014 stopped at 5113 | `verify_live_fleet_interaction.sh` | shipped |
| WTA-030 | SEEK-8 fix verified on **Stitcher displayOnly** not Phase B stem | Phase B | Waveform seek | Wrong surface for operator symptom | Phase B stem drag + DROP-WC-LIVE-1 | shipped |

---

## B. Operator edit authority — refresh/poll clobber (Tier D bucket)

| ID | What you noticed | Tab | Control | Problem class | Gate | Status |
|----|------------------|-----|---------|---------------|------|--------|
| D-001 | Beat Gen prompt **snaps back**, caret jumps to end mid-type | Beat Gen | O3 prompt textarea | Controlled value + poll clobber | `verify_prompt_edit_durability` | shipped |
| D-002 | Phase script **overwritten** after blur/generate race | Phase A/B | Script textarea | `scriptDraft` + refreshAll | `useProtectedPromptField`, `verify_operator_edit_surfaces` | shipped |
| D-003 | Watercolor cue **vanished** after resize / tab focus | Phase A/B | Cue blocks | Hydrate blind-wipe | `CUE-HYDRATE-1`, `usePhaseWatercolorCues` | shipped |
| D-004 | Cue **resize lost** on focus refresh | Phase A/B | Cue handles | Same hydrate class | Tier D merge rules | shipped |
| D-005 | Amber stem cut **reverted** on refresh before Apply | Phase A/B | Stem cut handles | Dual stateSlice | `usePhaseStemCut` | shipped |
| D-006 | Stitcher SFX block **jumped back** after save refresh | Stitcher | SFX cues | GET after save clobber | `STITCH_SAVE_REFRESH_LOCAL_CUES_V1`, G3–G5 | shipped |
| D-007 | BG ref boxes **lost** on session refresh | Beat Gen | Char/bg ref tiles | Server beat merge | `preserveRefBoxesOnServerBeatMerge` | shipped |
| D-008 | O3 prompt **stripped/morphed** after Generate | Beat Gen | Prompt + refs | O3 intent spec, `verify_o3_generation_intent` | shipped |
| D-009 | Textarea **snaps back** immediately after Generate | Beat Gen | Prompt | intent latch before refreshState | shipped |
| D-010 | Phase ambient preset **reverts** before save ack | Phase B | Ambient `<select>` | `usePhaseAmbientPreset` | shipped |
| D-011 | Stitcher ambient bed **reverts** on refresh | Stitcher | Ambient per slot | `mergeStitchAmbientBedOnHydrate` | shipped |
| D-012 | Storyboard dialogue cell **rolls back** mid-edit | Storyboard | contenteditable | `useStoryboardDialogueField`, S3 e2e | shipped |
| D-013 | Storyboard **trim front/back** fields reset mid-edit | Storyboard | LD-756 inputs | `useStoryboardTrimFields` | shipped |
| D-014 | BG O3 trim overlay **resets mid-drag** before Apply Trim | Beat Gen | Amber keep-window | `useBgO3CutSession`, `verify_o3_trim_overlay` | shipped |
| D-015 | BG numeric trim draft **clobbered** on poll | Beat Gen | Trim numeric fields | `useBgO3TrimNumericDraft` | shipped |
| D-016 | Phase base clip picker **desync** | Phase A/B | Base clip picker | `usePhaseBaseClipPicker`, PHASE-CLIP-HYDRATE-1 | shipped |
| D-017 | Cue drag **HTTP 0 / Failed to fetch** spam | Phase A/B | Cue handles | LL-WCU-2, pointerup commit | shipped |
| D-018 | Gallery slot / trim fields **stale after session refresh** | Beat Gen | O3 gallery | `mergeBeatsOnSessionHydrate` | shipped |
| D-019 | `pathappPatch` **overwrote event_id** caller owned | All tabs | Mutations | scope injection bug | `F-STORYBOARD-001` e2e | shipped |
| D-020 | Display order **empty vs undefined** broke UI | Storyboard | Beat list | JS falsy on `[]` | `DISPLAY_ORDER_STRICT_V1` e2e | shipped |
| D-021 | Storyboard refresh after magic complete **lost local edits** | Storyboard | Beat cards | `useStoryboardDialogueField` + session merge | S3 retroactive e2e | shipped |
| D-022 | Delay field **reverts** after save | Storyboard | Audio delay | T-5..T-9 durability | `delay_durability.spec` | shipped |
| D-023 | Stitch slot **durable fields dropped** on partial client patch | Stitcher | Slot metadata | Partial patch merge | `STITCH_SAVE_SLOT_DURABLE_MERGE_V1` | shipped |
| D-024 | Producer tab switch shows **reload spinner** | Phase A/B | Tab keep-alive | Full remount | `producer_session_tab_switch` e2e | shipped |

---

## C. Trim (all surfaces)

| ID | What you noticed | Tab | Control | Gate | Status |
|----|------------------|-----|---------|------|--------|
| TR-001 | BG O3 trim **false reject** / handles past clip end | Beat Gen | Gallery amber overlay | `verify_o3_trim_overlay`, `normalizeO3KeepWindow` | shipped |
| TR-002 | BG playback vs export **duration mismatch** broke trim math | Beat Gen | Overlay timeline | `resolveO3PlaybackDurationS` | shipped |
| TR-003 | **Preview Trim** button wrong window | Storyboard | LD-755 Preview Trim | LD-755 marker | shipped |
| TR-004 | Storyboard trim front/back **semantics wrong** (absolute vs from-end) | Storyboard | LD-756 fields | LD-787 e2e, LD-756 markers | shipped |
| TR-005 | Phase stem cut amber region **wrong after refresh** | Phase A/B | Waveform cut | `usePhaseStemCut` | shipped |
| TR-006 | Apply Cut didn't refresh preview until navigate away | Phase A/B | Apply Cut btn | commit `0534970` | shipped |
| TR-007 | Stitch **per-slot trim handles** missing | Stitcher | Slot waveform G9 | G9 e2e | shipped |
| TR-008 | Stitch trim edit **doesn't persist** | Stitcher | G10 trim drag | G10 e2e | shipped |
| TR-009 | Kling export used **untrimmed** clip after trim set | Beat Gen | Send to Stitcher | `materialize_kling_o3_trimmed_clip` grep | shipped |
| TR-010 | BG trim overlay **mid-drag poll clobber** | Beat Gen | Overlay drag | `useBgO3CutSession` | shipped |
| TR-011 | Storyboard trim **mid-edit poll clobber** | Storyboard | Numeric trim | `useStoryboardTrimFields` | shipped |
| TR-012 | Export shipped **untrimmed** when option trim ≠ beat authority | Beat Gen | Send to Stitcher | `prepare_beats_for_stitch_export` | shipped |

---

## D. Beat Gen — O3 / gallery / generate lifecycle

| ID | What you noticed | Tab | Gate | Status |
|----|------------------|-----|------|--------|
| O3-001 | Generate button **disabled** falsely after debounce re-ran Element gate | Beat Gen | `verify_bg_generate_gate` | shipped |
| O3-002 | Generate click **no spinner** — silent stall | Beat Gen | `verify_bg_generate_gate` | shipped |
| O3-003 | UI shows **idle** while O3 job running | Beat Gen | `verify_bg_o3_submit_ui_reattach` | shipped |
| O3-004 | Good g7 **overwritten**, no g8 | Beat Gen | `verify_o3_prompt_lineage_durability` | shipped |
| O3-005 | Char ref **ignored** (pose from Element not drop) | Beat Gen | intent commit char ref gate | shipped |
| O3-006 | `(female raccoon)` **stripped** from prompt after Generate | Beat Gen | intent verbatim pytest | shipped |
| O3-007 | Kling done but gallery **lags** lifecycle | Beat Gen | commit `d7a0760` close gallery before terminal | shipped |
| O3-008 | Orphan recovery says **done** when sidecar errno 11 | Beat Gen | `verify_o3_sidecar_checkpoint` | shipped |
| O3-009 | **Beats disappeared** on cold boot | Beat Gen | beatgen sqlite / mirror union | shipped |
| O3-010 | Cross-event **beat loss** | Beat Gen | per-event SQLite | shipped |
| O3-011 | Insert beat **blank row** wrong voice (Beat 13) | Beat Gen | `verify_insert_beat_form_first` | shipped |
| O3-012 | Char ref drag **500** AppContext error | Beat Gen | `verify_bg_ref_app_context` | shipped |
| O3-013 | Library **empty grid** / wrong speaker on ref | Beat Gen | commit `96f61e8` | shipped |
| O3-014 | Segment dropdown **empty vs loading** indistinguishable | Beat Gen | `F-BG-001` e2e | shipped |
| O3-015 | Beat jump nav **broken** | Beat Gen | `BG_BEAT_JUMP_NAV_V1` e2e | shipped |
| O3-016 | Send to Stitcher gated on raw **approved** not delivery clip | Beat Gen | `verify_kling_stitch_readiness` | shipped |

---

## E. Phase A/B producer — lipsync, overlay, export

| ID | What you noticed | Tab | Gate | Status |
|----|------------------|-----|------|--------|
| PA-001 | Watercolor overlay **covers whole screen** | Phase A/B | OVERLAY-1 | shipped |
| PA-002 | Overlay **too large** / wrong bbox | Phase A/B | OVERLAY-2 geometry | shipped |
| PA-003 | Animated cue **pink/magenta frame** | Phase A/B | OVERLAY-3 chromakey | shipped |
| PA-004 | Animated watercolor **frozen** while audio plays | Phase A/B | OVERLAY-4 loop sync | shipped |
| PA-005 | **Two video players** on Phase A tab | Phase A | LD-829, F17 e2e | shipped |
| PA-006 | Export to Stitcher **appeared dead** / wrong error | Phase B | LL-WCU-4 payload shape | shipped |
| PA-007 | Preview overlay **stuck minutes** first run | Phase B | LL-WCU-3 veryfast preset | shipped |
| PA-008 | Lipsync on **stale stem** (old dialogue baked) | Phase A/B | `verify_phase_voice_stem_pin` | shipped |
| PA-009 | Waveform shows **stem** but lipsync video stale — confusing | Phase A/B | stale lipsync badge LD-809, `stale_lipsync_ui_gate` | shipped |
| PA-010 | ▶ lipsync plays **4.2s** old clip; beat says 9.4s | Storyboard | F-STALE-LIPSYNC-UI-001 | shipped |
| PA-011 | Phase B accent **drift** on eleven_v3 stem | Phase B | `verify_elevenlabs_tts_stitching` | shipped |
| PA-012 | Suggest Script **wrong module** (Event_N id) | Phase A/B | `verify_module_event_id_suggest_script` | shipped |
| PA-013 | F7 drop watercolor → cue at wrong position | Phase A/B | F7 e2e | shipped |
| PA-014 | F8/F9 cue popover edit/delete | Phase A/B | F8/F9 e2e | shipped |
| PA-015 | CUE-RESIZE: only **right handle** worked | Phase A/B | CUE-RESIZE-1/2, LL-WCU-1 | shipped |
| PA-016 | Resolution slot **vanished** after Phase B export | Stitcher | LL stitcher canonical job | shipped |
| PA-017 | Stitcher showed **raw lipsync** without watercolors | Stitcher | overlay bake on export | shipped |
| PA-018 | Animate hands: **whole frame sliced/moved** | Phase B | LL-WCA-3 wc_v13 | shipped |
| PA-019 | White **holes** in animated cue | Phase B | LL-WCA-4 underlay | shipped |
| PA-020 | Re-animate but preview shows **old** behavior | Phase B | LL-WCA-7 recipe hash bump | shipped |
| PA-021 | F15 ambient preset selector empty/wrong | Phase B | F15, F-AMBIENT-001, AMBIENT-HYDRATE-1 | shipped |
| PA-022 | F10/F11 Phase A base clip pick | Phase A | F10/F11, PHASE-CLIP-HYDRATE-1 | shipped |

---

## F. Stitcher — slots, media, ambient, layout

| ID | What you noticed | Tab | Gate | Status |
|----|------------------|-----|------|--------|
| ST-001 | Slot preview **black video**, audio plays | Stitcher | `verify_stitch_slot_preview_video` | shipped |
| ST-002 | 38s video, **16s waveform** audio cut off | Stitcher | `verify_stitch_slot_audio_extract` | shipped |
| ST-003 | Ambient save **wiped other slots** | Stitcher | `verify_stitch_ambient` merge_slots | shipped |
| ST-004 | Ambient volume **too loud** vs speech | Stitcher | canonical 0.15 gate | shipped |
| ST-005 | G17 multi-phase track **selection lost** | Stitcher | G17 e2e | shipped |
| ST-006 | G6 module SFX drop | Stitcher | G6 e2e | shipped |
| ST-007 | G7/G8 transition selectors | Stitcher | G7/G8 e2e | shipped |
| ST-008 | Viewer layout: **second waveform** spurious | Stitcher | `STITCH_VIEWER_SLOT_LAYOUT` e2e | shipped |
| ST-009 | Phase switch composer **instant pool** | Stitcher | `stitcher_phase_switch_instant_pool` | shipped |
| ST-010 | StitcherTab mutation **wrong channel** | Stitcher | AF.1 e2e | shipped |
| ST-011 | Event stitch job **missing** on new event | Stitcher | `verify_event_stitch_job_bootstrap` | shipped |
| ST-012 | Slot timeline duration **wrong** for SFX geometry | Stitcher | `verify_stitch_slot_timeline_atomic` | shipped |
| ST-013 | Slot export **full media** regression | Stitcher | `verify_stitch_slot_export_full_media` | shipped |
| ST-014 | Canonical transition SFX | Stitcher | `verify_stitch_canonical_transitions` | shipped |
| ST-015 | Boundary fade wrong on phase join | Stitcher | `verify_phase_boundary_fade` | shipped |
| ST-016 | Rebake loop on ambient hydrate | Stitcher | commit `63d1fed` | shipped |
| ST-017 | Production Map **missing rows** | Global | G12 e2e | shipped |
| ST-018 | Map cell click **wrong event** | Global | G13 e2e | shipped |
| ST-019 | Bake final MP4 quality soft/blocky | Stitcher | VQ spec + bake pipeline | shipped |
| ST-020 | Hard refresh **empty composer** on ambient/SFX slots | Stitcher | `STITCH_MUX_INTERIM_DRY_VIDEO_V1` | shipped |

---

## G. Scope, event pin, build drift

| ID | What you noticed | Tab | Gate | Status |
|----|------------------|-----|------|--------|
| SC-001 | URL `?event=Event_2` but UI on Event_1 | All | `verify_scope_deep_link` | shipped |
| SC-002 | Tab says Event_2, server pinned Event_1 | All | `verify_scope_mismatch_auto_heal` | shipped |
| SC-003 | **Endless reload** ping-pong on poll | All | `verify_scope_poll_adopt` | shipped |
| SC-004 | Build stale — Submit silently wrong | All | `SCOPE_CLIENT_AUTHORITY` e2e | shipped |
| SC-005 | BG segment **doesn't refetch** on scope change | Beat Gen | `BG_TAB_SCOPE_SYNC_V1` e2e | shipped |
| SC-006 | Dedicated port **5112** scope pin wrong in e2e | CI | `scope_dedicated_port_authority` | shipped |
| SC-007 | Event library paths **wrong event** after load | Beat Gen | `verify_event_library_scope` | shipped |
| SC-008 | Cold boot **90s timeout** false fail deploy | CI | beatgen smoke 180s | shipped |
| SC-009 | Milestone vs event **authority chain** wrong | Milestone | `verify_milestone_partition_resolver` | shipped |
| SC-010 | Deploy while tab open — **manual reload** required | All | `checkBuildShaDriftAndAutoReload` | shipped |

---

## H. Storyboard, magic, library, parity

| ID | What you noticed | Tab | Gate | Status |
|----|------------------|-----|------|--------|
| SB-001 | Magic trail **diagonal** not on shell path | Storyboard | LL magic path surface LD-828 | shipped |
| SB-002 | Path picker drew on **still** not lipsync frame | Storyboard | LD-828 dim lock | shipped |
| SB-003 | Rollback dialogue **reverts** edit | Storyboard | `useStoryboardDialogueField`, S3 e2e | shipped |
| SB-004 | Library SFX **disappeared** from panel | Library | `verify_library_audio` #1 | shipped |
| SB-005 | MP3 upload **grayed out** | Library | `verify_library_audio` #2 | shipped |
| SB-006 | Ambient preview **0:00** (spaced filename) | Library | `verify_library_audio` #3 | shipped |
| SB-007 | Library tile **sizing** wrong | Library | R5 e2e | shipped |
| SB-008 | Drag-drop wiring broken | Library/BG | R2 e2e | shipped |
| SB-009 | Behavioral parity gaps (dialogue, crop, export) | Multi | `behavioral-parity.spec` executable rows | shipped |
| SB-010 | Video encode **soft/blotchy** previews | All previews | VQ-P3..P6 | shipped |

---

## I. Spec-only / open gaps (Phase E candidates)

| ID | What you noticed | Bucket | Doc | Status |
|----|------------------|--------|-----|--------|
| GAP-001 | Playhead **0:00 after audio remount** | WTA | REMOUNT-1 + `verify_waveform_time_authority.sh` | **shipped** |
| GAP-002 | Single `waveformTimeAuthority.ts` module | WTA | WTA-0 shipped | **shipped** |
| GAP-003 | `verify_waveform_time_authority.sh` grep gate | WTA | WTA-3 | **shipped** |
| GAP-004 | BG trim overlay mid-drag poll | Tier D | `useBgO3CutSession` | **shipped** |
| GAP-005 | Storyboard LD-756 trim mid-edit | Tier D | `useStoryboardTrimFields` | **shipped** |
| GAP-006 | Phase ambient + Stitcher ambient refresh | Tier D | ambient merge hooks | **shipped** |
| G1 | Failed O3 redo leaves sidecar running / prior clip not restored | O3 | `O3_FAILED_REDO_HEAL_V1` + `verify_o3_failed_redo_heal_durability.sh` | **shipped** |
| G2 | O3 subprocess lost on server restart — paid work orphaned | O3 | `O3_SUBPROCESS_LIFECYCLE_V1` + `verify_o3_subprocess_lifecycle_durability.sh` | **shipped** |
| G3 | Terminal / disk / sidecar / UI disagree after O3 attempt | O3 | `O3_JOB_TRUTH_STACK_V1` + `verify_o3_job_truth_durability.sh` | **shipped** |
| G4 | Sidecar beats disappear / mirror stale / JSON conflicts | Sidecar | `verify_beatgen_truth_stack_durability.sh` | **shipped** |
| G5 | Crop/upload lands in wrong library root on milestone scope | Library | `verify_event_library_scope_durability.sh` | **shipped** |
| G6 | Master tile shows uncropped when delivery exists / Directus timeout | Library | `DIRECTUS_HAS_CROP_DISK_FALLBACK_V1` | **shipped** |
| G7 | Library sessionStorage stale after crop/upload/delete; ghost tiles after refetch | Library | `LIBRARY_CLIENT_CACHE_COHERENCE_V2` | **shipped** |
| G8 | Trim/cut/option change doesn't invalidate stitch slot preview | Stitch | `BG_O3_STITCH_EXPORT_LINEAGE_V1` | **shipped** |

---

## J. Infra / data (operator-visible but not edit-surface)

| ID | Symptom | Gate |
|----|---------|------|
| INF-001 | Beat Gen lock convoy / slow cold boot | `verify_bg_scope_activation_cold_boot` |
| INF-002 | Session-state GET lock contention freeze | read-only GET commit |
| INF-003 | Dropbox conflict copies in sidecar | beatgen siblings S5 |
| INF-004 | Truth stack wrong partition write | `verify_beatgen_truth_stack` |
| INF-005 | Directus export register missing | `verify_bg_directus_export` |
| INF-006 | LaunchAgent provision missing on new Event_N | `verify_event_server_provision` |
| INF-007 | Lorelai Element name drift | `verify_lorelai_element_name` |
| INF-008 | Baseline image library missing | `verify_baseline_image_library` |
| INF-009 | Per-event library durability | `verify_per_event_library` |
| INF-010 | Authority duplicate predicates | `verify_authority_registry` |

---

## Cross-reference: e2e describe index (behavioral only)

Full list lives in `Production/tools/storyboard-v2/e2e/*.spec.ts`. High-signal groups:

- **Phase waveform:** `phase_waveform_playback.spec.ts` (8 describes)
- **Phase features:** `s5_5f_smoke.spec.ts` (F3–F17)
- **Stitcher:** `s5_5g_smoke.spec.ts` (G3–G13), stitch phase switch specs
- **Scope:** `scope_*`, `f_storyboard_001`, `storyboard-v59-bg-scope-sync`
- **Beat Gen:** `bg_golden_path`, `bg_beat_nav_jump`, `layer_b_option_b_bg_session_state`
- **Retroactive:** S1–S6 `retroactive_s*.spec.ts`
- **Architectural:** `architectural_fix.spec.ts` AF.1/AF.2

---

## Maintenance

Re-generate when adding any `verify_*_durability.sh` with an Incident/Symptom header:

```bash
# Future: scripts/extract_operator_symptom_matrix.sh
grep -l 'Incident\|Symptom\|Root cause' Production/scripts/verify_*_durability.sh
```

**Do not** rebuild from `git log --grep` alone.
