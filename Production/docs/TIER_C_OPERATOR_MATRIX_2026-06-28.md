# Tier C Operator Acceptance Matrix (2026-06-28)

**Marker:** `TIER_C_OPERATOR_MATRIX_2026-06-28`  
**Branch:** `fix/prompt-contradiction-gallery-closure` @ `82e8eff` (+ deploy smoke fix pending commit)  
**Build SHA served:** `82e8eff`  
**Bundle fanout SHA256:** `d2a2042b46e8bd56ed6a71945f0ce16e512cf1b62dfea7ae42f6ed6d45f076a0` (Event_1/2/3 match)

Legend: **PASS** = verified this session | **AUTO** = CI/read-only smoke | **VIS** = browser visual spot-check

## Tab × Event (read-only / load)

| Tab | Event_1 (:5111) | Event_2 (:5112) | Event_3 (:5113) | Milestone (Event_2) |
|-----|-----------------|-----------------|-----------------|---------------------|
| Beat Generator | AUTO + VIS | AUTO + VIS | AUTO + VIS | PASS (11 beats via `verify_beatgen_deploy_smoke`) |
| Cropper | AUTO | AUTO | AUTO | — |
| Storyboard (route) | AUTO | AUTO | AUTO | — |
| Phase A | AUTO | AUTO | AUTO | — |
| Phase B | AUTO | AUTO | AUTO | — |
| Stitcher | AUTO + VIS | AUTO + VIS | AUTO + VIS | — |
| Production Map | AUTO | AUTO | AUTO | — |

**Evidence — tab smokes (Event_1 :5111):** `smoke_beatgen.py`, `smoke_cropper.py`, `smoke_storyboard.py`, `smoke_phase_a.py`, `smoke_phase_b.py`, `smoke_stitcher.py`, `smoke_production_map.py` — all exit 0.

**Evidence — per-event session-state after deploy restart:**
- Event_1 intro: deploy curl smoke + beatgen smokes
- Event_2 intro: 23 beats, milestone `milestone1_arc1`: 11 beats (`verify_beatgen_deploy_smoke.sh 5112`)
- Event_3 intro: 12 beats (`verify_beatgen_deploy_smoke.sh 5113`)

**Evidence — visual (browser):**
- Event_1: tabs render, BG beat cards + library, Stitcher library tier filter active
- Event_2: Event_2 pin, library populated, BG loading → reconciling (expected post-restart)
- Event_3: Event_3 pin, resolution segment "EVENT 3: EMBER'S SWEETROSE", BG + library loaded

## Export / action gates (architecture — not manual click-through)

| Action | Authority | Gate | Status |
|--------|-----------|------|--------|
| Send to Stitcher | `beat_kling_stitch_export_ready` | audit A–H + session-lockin pytest | PASS |
| BG async export latch | `beat_o3_operator_busy` | registry + e2e | PASS |
| O3 gallery active clip | disk path + `beatHasActiveO3DeliveryClip` | audit + e2e | PASS |
| Magic writeback | `write_magic_delivery` | audit J + pytest | PASS |
| Stitch rail duration | `stitchSlotTimelineDurMs` | session-lockin | PASS |
| Waveform scrub | WTA-1 / SEEK-3 | e2e 175/179 | PASS |
| Scope dedicated port | server truth + `scopeReconcile` | e2e + deploy smoke | PASS |

## Fleet deploy proof

| Check | Result |
|-------|--------|
| `deploy_storyboard_v59.sh --event Event_1` | PASS (snapshot `20260628T162039Z`, build-sha curl smoke) |
| Fanout bundle SHA Event_1/2/3 | PASS (identical sha256) |
| `verify_tooling_launcher.sh` 5111–5116 | PASS HTTP 200 tooling server |
| `verify_beatgen_deploy_smoke.sh` 5112/5113 | PASS (after launchd cold-boot fix) |

## Performance spot-check (session GET intro)

| Port | Event | Latency |
|------|-------|---------|
| 5111 | Event_1 | ~7.2s |
| 5112 | Event_2 | ~21.6s (cold boot / reconcile — within 120s gate) |
| 5113 | Event_3 | ~5.9s |

Note: Event_2 first session-state after restart is slower due to sidecar reconcile; deploy smoke now waits on valid JSON (EVENT_SERVER_COLD_BOOT_WAIT_V1).

## Open ops visibility (non-blocking)

- Orphan `kling_o3_clips` on Event_2/3 disk without sidecar pointer — WARN only in deploy smoke; does not block export authority.
