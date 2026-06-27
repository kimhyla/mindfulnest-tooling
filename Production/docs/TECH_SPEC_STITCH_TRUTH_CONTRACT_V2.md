# TECH_SPEC — Stitch Truth Contract V2

**Status:** Shipped (`b49fb04` + live E2E gate)  
**Branch:** `fix/build-sha-drift-banner`  
**Supersedes / extends:** `TECH_SPEC_STITCH_SFX_PLAYBACK_TRUTH_V1.md`, `TECH_SPEC_WAVEFORM_TIME_AUTHORITY_v1.md`, `SCOPE_CLIENT_AUTHORITY_SPEC_v1.md`

---

## 1. Purpose

Close every remaining gap from the Stitch playback / edit truth audit with **complexity-reducing category fixes** — one invariant per truth layer, not symptom patches.

---

## 2. Inventory — every fix from audit (transcribed)

### 2.1 Already shipped (`STITCH_SFX_PLAYBACK_TRUTH_V1`, commit `f27e5aa`)

| # | Fix | Layer |
|---|-----|-------|
| A1 | `resolveSlotPlaybackPreviewUrl` returns `undefined` (not dry `/files`) when slot requires mux/ambient and no artifact | Playback |
| A2 | `isStitchMuxPlaybackUrl` — URL lineage gate | Playback |
| A3 | `stitchSlotTimelineDurMs` — mux_preview_duration_ms → video_dur_ms | Timeline |
| A4 | `saveJobSlots` queues `pendingMuxBuildsRef` on geometry change | Mux lifecycle |
| A5 | Session cache rekey `stitchJobSessionKey` (not bare `eventId`) | Identity |
| A6 | Milestone `hydrate_milestone_standalone_from_disk` on load | Server hydrate |
| A7 | `handle_stitch_preview` uses `stitch_state_store_for_job` | Server store routing |
| A8 | `composerUsingMux` requires mux URL lineage | UI truth |
| A9 | Waveform drop/sync uses `slotTimelineDurMs` prop | Timeline |

### 2.2 This spec (V2 — remaining gaps)

| # | Category | Fix |
|---|----------|-----|
| B1 | **STITCH_SLOT_TIMELINE_ATOMIC_V1** | Server: slot with `video_path` MUST have `video_dur_ms` before load_job response; ffprobe on missing; fallback `mux_preview_duration_ms`; persist |
| B2 | **STITCH_SLOT_TIMELINE_ATOMIC_V1** | Client: ALL rail/drop/total duration UI uses `stitchSlotTimelineDurMs`; never `DEFAULT_SLOT_DUR_MS` when mux duration exists |
| B3 | **STITCH_MUX_PAUSE_ON_GEOMETRY_V1** | On SFX/ambient geometry change: pause composer immediately; remove defer-while-playing; mux src swaps as soon as ready |
| B4 | **STITCH_MUX_PAUSE_ON_GEOMETRY_V1** | `buildSlotPreview` failure path: never bind dry when `stitchSlotRequiresMuxedPreview` |
| B5 | **STITCH_GUARD_PORT_TOPOLOGY_V1** | Shared `dedicated_port_env.sh`; durability guards use pinned event on port; never `event/load Event_2` on `:5111` |
| B6 | **STITCH_GUARD_PORT_TOPOLOGY_V1** | Fix `verify_bg_ref_app_context_durability.sh` live curl (409 reproducer) |
| B7 | Tests + source guards for B1–B6 | Durability gates |

### 2.3 Explicitly out of scope (product / separate track)

| Item | Reason |
|------|--------|
| Event_2 full Phase A Avatar Pro bake | Content pipeline, not stitch truth |
| Web Audio real-time SFX preview | Product decision; mux MP4 remains delivery |
| Hub-port multi-event `event/load` swap tests | Only on non-dedicated ports; dedicated ports use 409 contract |

---

## 3. Invariants (causeless causes → enforcement)

### 3.1 Playback invariant (A — shipped)

> If `sfx_cues.length > 0` (or ambient mix required), playback `src` MUST be mux/ambient artifact URL or `undefined`.

### 3.2 Timeline invariant (B1–B2)

> If `video_path` is set, `video_dur_ms > 0` MUST be on wire before client renders timeline chrome.

**Server:** `ensure_stitch_slot_timeline_dur_ms(h, slot)` — ffprobe; else copy `mux_preview_duration_ms`.  
**Client:** `stitchSlotTimelineDurMs(slot)` everywhere; `DEFAULT_SLOT_DUR_MS` only for empty slots / tests.

### 3.3 Geometry → playback invariant (B3–B4)

> When stitch slot geometry changes, composer pauses; mux rebuild completes; new mux binds immediately (no defer-while-playing).

### 3.4 Guard topology invariant (B5–B6)

> Live-smoke scripts on port P may only mutate/read scope for `Event_{P-5110}`. Cross-event `event/load` expects 409 on dedicated ports — never `-sf` fail.

---

## 4. Implementation map

| File | Change |
|------|--------|
| `server_handlers/stitch_editor.py` | `STITCH_SLOT_TIMELINE_ATOMIC_V1`, `ensure_stitch_slot_timeline_dur_ms`, load_job persist |
| `StitcherTab.tsx` | `stitchSlotTimelineDurMs` rail/drop; pause on geometry; remove defer refs; dry bind guard in buildSlotPreview |
| `dedicated_port_env.sh` | port ↔ event helpers |
| `verify_bg_ref_app_context_durability.sh` | port-topology live smoke |
| `test_stitch_slot_timeline_atomic.py` | server contract |
| `test_stitch_mux_pause_geometry.py` | source guards |
| `stitchSlotTimelineAtomic.test.ts` | client rail uses mux dur |
| `stitch_sfx_playback_truth_live.spec.ts` | live milestone E2E (pause → mux → offset) |
| `verify_stitch_sfx_playback_truth_durability.sh` | deploy gate + optional live Playwright |

---

## 5. Proof plan (Full QA)

1. **Reproduce:** disk `video_dur_ms: null`, UI rail 30.0s; `verify_bg_ref` exit 22 on 409.
2. **Unit:** pytest + node tests for B1–B6 markers.
3. **API:** `stitch/load_job` milestone → `video_dur_ms > 0`.
4. **Deploy:** `deploy_storyboard_v59.sh` session durability exit 0.
5. **Browser:** `localhost:5112/?video=intro&milestone=milestone1_arc1` — rail shows ~94.1s; SFX drop → pause → mux → audible.

---

## 6. 3×3 debate summary

| | Pro category | Con patch | Resolution |
|---|-------------|-----------|------------|
| 30s rail | Atomic dur on server + one client helper | Client-only mux read | **Category** — server persists dur |
| 409 guard | Port-topology shared helper | `\|\| true` on bg-ref | **Category** — align harness with EVENT_DEDICATED_PORT_V1 |
| Mux defer | Pause-on-geometry | Keep defer + banner | **Category** — Kim approved pause rule |

**Risk:** ffprobe on load adds latency → only slots missing `video_dur_ms`.  
**Risk:** auto-pause on save may surprise → status msg "Paused — rebuilding SFX preview".

---

## 7. Sibling bugs closed by V2

- False 30s multiphase rail width
- SFX drop cap using 30s instead of 94s
- `moduleTimelineDurMs` sum wrong
- Deploy blocked by bg-ref 409
- Mux ready but user still hears old audio while playing after drop
- `buildSlotPreview` dry fallback on mux failure for SFX slots
