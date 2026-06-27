# TECH_SPEC_PHASE_B_LIPSYNC_DELIVERY_V1 — module lipsync voice_first_upscale parity

## Category-unlocker

- **Bug category:** Phase B module lipsync saves raw Kling Sync sub-720 MP4 (~720×544 @ ~1.2 Mbps) while beat-level lipsync runs `voice_first_upscale` (Lanczos 1280×720 @ ≤1.9 Mbps) before any stitch/bake path. Upscale + lean encode later accentuates shoulder/hair edge halos baked into raw Kling pixels.
- **Category fix:** Single choke point `finalize_phase_module_lipsync_delivery()` on every Phase B terminal lipsync write; preview cache hash includes delivery recipe; CLI re-encode for existing on-disk lipsync without new Kling job.
- **Fix type:** CATEGORY
- **Compelling reason (if PATCH):** n/a
- **Plan:** Implement shared delivery module → wire `_write_phase_b_lipsync_complete` → bump preview hash → re-encode Event_2 lipsync → regen Phase B preview → Stitcher export → module bake → ffprobe + browser proof.

## Forensic reproduce (Event_2, 2026-06-23)

| Stage | File | WxH | Bitrate |
|-------|------|-----|---------|
| Raw Kling lipsync (pre-fix) | `phase_b_lipsync_20260621-231016.mp4` | **720×544** | **~1.23 Mbps** |
| Beat lipsync contract (arlo) | post-download `_delivery_video` | **1280×720** | **≤1.9 Mbps** |
| Phase B pre-fix | raw download saved as-is | 720×544 | ~1.23 Mbps |
| Module final lean bake | `M2_event_2_final.mp4` | 1280×720 | ~942 kbps |

Edge halos visible at module ~251 s (4:11) in raw lipsync, Phase B preview, stitch preview, and lean bake — **not introduced by bake A/V fix**.

## Implementation steps

1. **`phase_module_lipsync_delivery.py`**
   - `finalize_phase_module_lipsync_delivery(path)` → in-place `voice_first_upscale` via `encode_delivery_video`.
   - Gate: output **1280×720**, bitrate ≤ `VOICE_FIRST_DELIVERY_MAX_BITRATE_BPS`.
   - Recipe id: `PHASE_MODULE_LIPSYNC_DELIVERY_V1`.

2. **`server_handlers/phases.py`**
   - `_write_phase_b_lipsync_complete`: call finalize before state write; persist `phase_b_lipsync_delivery_profile` + `phase_b_lipsync_delivery_recipe`.
   - `_phase_ensure_overlay_mp4`: hash includes `lipsync_delivery:PHASE_MODULE_LIPSYNC_DELIVERY_V1` (cache bust).

3. **`reencode_phase_module_lipsync_delivery.py`**
   - CLI: re-encode pinned `phase_b_lipsync_file` in-place with `.bak` — no Kling re-submit.

4. **Tests**
   - `test_phase_module_lipsync_delivery.py`: constants, wiring grep, mocked + integration tiny clip.
   - Extend `test_voice_first_delivery_profile.py`, `test_phase_b_panel.py` mock finalize.

5. **Runtime proof (Event_2)**
   - Re-encode lipsync → ffprobe 1280×720 ≤1.9 Mbps.
   - POST `/api/phase_b/preview` → new preview hash path.
   - Export phase_b to Stitcher → bake final → ffprobe A/V parity + browser module final at ~251 s.

---

## 3×3 agent debate (roles × rounds)

### Roles

| Role | Lens |
|------|------|
| **Pipeline engineer** | FFmpeg profiles, Kling raw vs delivery, stitch slot inputs |
| **QA / durability** | Positive ffprobe proof, no chat-only claims |
| **Operator UX** | No new ChatGPT/Kling unless halos remain after encode |

### Round 1 — Is choke-point delivery encode the right category?

| Role | Verdict |
|------|---------|
| Pipeline | Yes. Beat path already uses `voice_first_upscale`; Phase B gap is proven by code grep + 720×544 on disk. One function beats patching preview or bake separately. |
| QA | Yes. Reproduce is ffprobe-positive on existing file before any code change. |
| Operator | Yes. Kim should not regenerate PNG; CLI re-encode proves value without Kling spend first. |

### Round 2 — Step necessity

| Step | Pipeline | QA | Operator |
|------|----------|-----|----------|
| 1 Shared module | Single source; arlo + phase B can't drift | Unit + integration test | — |
| 2 Wire terminal write | All poller paths hit `_write_phase_b_lipsync_complete` | Grep contract | Auto on next Send for Lipsync |
| 3 Preview hash bump | Old 1.4 Mbps preview must not LRU-hit | Hash string in test | Preview regen after re-encode |
| 4 CLI re-encode | Existing modules without Kling | Before/after ffprobe in report | Agent-run, Kim doesn't terminal |
| 5 Stitch re-export + bake | Slot must carry new Phase B bytes | A/V parity gates still apply | Browser smoke at 4:11 |

**Consensus:** All five steps required. Re-encode alone without code = patch; code alone without Event_2 re-encode = unproven.

### Round 3 — Honest limits (anti-hallucination)

| Role | Verdict |
|------|---------|
| Pipeline | Delivery encode improves upscale quality; **cannot erase Kling shoulder halos** baked into pixels. Report honestly if halos persist. |
| QA | Acceptance = 1280×720 delivery shape + parity gates + browser plays; edge QA is visual compare before/after frames, not "halos gone" unless proven. |
| Operator | If halos remain after category fix, next lever is re-run Send for Lipsync (Kling), not another PNG. |

**Consensus:** Ship category fix with measured expectations; document limit in report.

---

## Acceptance criteria

| Gate | Threshold |
|------|-----------|
| Lipsync delivery WxH | 1280×720 |
| Lipsync delivery bitrate | ≤ 1,900,000 bps |
| `phase_b_lipsync_delivery_profile` | `voice_first_upscale` |
| Preview cache | New hash path under `preview/phase_b/` |
| Module bake A/V | drift ≤ 0.25 s (existing STITCH_MODULE_BAKE_AV_PARITY_V1) |
| Module final lean | ≤ 960 kbps, ≤ 80 MB |
