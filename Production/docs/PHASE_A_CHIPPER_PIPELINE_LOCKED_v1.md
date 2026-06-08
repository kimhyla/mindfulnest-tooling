# Phase A Chipper Pipeline — Locked Decisions v1

**Status:** ACTIVE (Kim session 2026-06-01, durability pass 2026-06-08)  
**Scope:** Module 1 Event 1 — Chipper fly-in / close-up middle / fly-out  
**Enforcement:** Code + tests (not chat memory)

---

## Architecture (three segments)

| Segment | Source | Lipsync? |
|---------|--------|----------|
| Fly-in (~5s) | Kling start/end on v3 PNGs (empty desk ↔ bird on desk) | No |
| Middle | Close-up idle base → lipsync | **Yes** |
| Fly-out (~5s) | Kling start/end (bird on desk → empty desk) | No |

**Stitch order:** fly-in + **raw** lipsync middle + fly-out + continuous ambient bed (`meditation_pretty_v1` default).

**Storyboard player:** Phase A tab shows **stitched** video (`phase_a_stitched_file`), not middle-only. Open middle previews via direct file URL.

---

## Vendor split (HARD)

| Phase | Character | Lipsync vendor | Endpoint |
|-------|-----------|----------------|----------|
| **A** | Chipper (bird) | **ByteDance LatentSync raw** (`bytedance-tight`) | `/api/phase_a/lipsync` |
| **B** | Cedric (human) | **Kling Sync** | `/api/phase_b/lipsync` |

### Rejected approaches (do not reintroduce)

1. **Kling Sync on bird close-up** — human arms on wings, human teeth, gaze drift.
2. **ByteDance + beak face composite** (`maskedmerge`) — “ghost bird” duplicate beside real bird.
3. **Single 33s ByteDance pass without §8.5 split** — exceeds ~10s training window; use segmented `bytedance-tight`.

---

## Canonical code paths

| Role | File |
|------|------|
| ByteDance-tight lipsync | `Production/tools/phase_a_chipper_bytedance_lipsync.py` |
| CLI (lipsync + restitch) | `Production/tools/phase_a_v3_execute_fix.py` |
| Stitch input resolution | `Production/tools/phase_a_stitch_lib.py` |
| Auto-stitch + ambient | `production_server._auto_assemble_phase_a_stitched` |
| Server lipsync (Phase A) | `server_handlers/phases.handle_phase_a_lipsync` |
| Server lipsync (Phase B) | `server_handlers/phases.handle_phase_b_lipsync` |
| Restitch API | `POST /api/phase_a/restitch` |
| Tests | `Production/tools/tests/test_phase_a_stitch_resolve.py` |

---

## ByteDance-tight pipeline (middle)

1. **Audio prep:** `_silcomp_audio` + loudnorm + auto-preroll (§8.4).
2. If audio ≤ 7s: forward-loop idle base → trim → one ByteDance job.
3. If audio > 7s: silence-boundary split (§8.5), one job per chunk, concat.
4. **Per chunk:** forward-loop base (not pingpong), trim with `trim_start=0.0` always.
5. **Output:** raw full-frame ByteDance MP4 — **no** face composite.
6. On server complete: write `phase_a_lipsync_*`, then **auto-stitch**.

---

## State field contracts

| Field | Purpose |
|-------|---------|
| `phase_a_flyin_file` | Pinned fly-in mp4 (prefer `closeup_match_*`) |
| `phase_a_flyout_file` | Pinned fly-out mp4 |
| `phase_a_lipsync_file` | Pinned middle (raw, no `withbed`) |
| `phase_a_stitched_file` | Canonical stitched output (UI player) |
| `phase_a_chipper_sitting_clip_id` | Library base for lipsync |
| `phase_a_voice_stem_file` | TTS source for ByteDance prep |
| `phase_a_ambient_preset_id` | Bed applied at stitch (default `meditation_pretty_v1`) |

**Resolver rule:** pinned state beats glob. Lipsync resolver accepts `phase_a_lipsync_*` **and** `chipper_lipsync_*`.

---

## Bookend generation

| Role | Script |
|------|--------|
| Closeup-matched fly-in/out | `phase_a_flyin_flyout_closeup_match_v1.py` |
| Idle base regen | `phase_a_chipper_lipsync_base.py` |

API: `POST /api/phase_a/regen_flyin_flyout`, `POST /api/phase_a/regen_base_clip`

---

## QA checklist (multipass)

```bash
cd Production/tools
python3 -m pytest tests/test_phase_a_stitch_resolve.py -q

# With server on :5111:
python3 ../scripts/phase_a_restitch_from_state.py

# Verify pinned middle is used (check canonical.raw_lipsync in JSON response)
```

---

## Lessons learned (2026-06-01)

- Kling Sync assumes human faces; cartoon birds need ByteDance raw.
- Face composite ghosting came from blur bleed + misaligned source frames — default OFF.
- `trim_start = (i * 2.0) % base_dur` broke last segment when modulo ≈ base duration → 0s video.
- Storyboard “same video” reports usually mean **stitched** file unchanged — check middle URL separately.
- May 2026 global Kling default was correct for Cedric, wrong for Chipper — vendor split is mandatory.
