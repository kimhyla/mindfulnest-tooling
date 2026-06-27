# STITCH_MODULE_BAKE_AV_PARITY_V1 — module bake A/V parity gate

## Category-unlocker

- **Bug category:** Module bake ships when video and audio stream durations diverge; validation trusts container `format.duration` (longest stream = audio) so truncated video + full audio passes every gate.
- **Category fix:** Reuse Beat Gen's `assert_stitch_export_clips_av_aligned` / `av_duration_drift_s` at every stitch pipeline boundary; extend `preview_cache_is_valid` and `stitch_cached_mp4_playable` to reject A/V drift > 250 ms.
- **Fix type:** CATEGORY
- **Compelling reason (if PATCH):** n/a
- **Plan:** Gate slot finals pre-concat, gate stitch preview post-concat, harden cache validity, gate bake pre/post lean encode, delete corrupt cache, re-bake Event_2, ffprobe + browser proof.

## Forensic reproduce (Event_2, 2026-06-22)

| File | Video (s) | Audio (s) | Drift (s) |
|------|-----------|-----------|-----------|
| `stitch_preview_57bf1ba8547d.mp4` | 202.708 | 380.831 | **178.123** |
| `M2_event_2_final.mp4` | 202.708 | 380.854 | **178.146** |

Video ends after intro + Phase A + black boundaries; Phase B/resolution audio concatenated but video not. `concat -c copy` partial write; `preview_cache_is_valid` used format duration (~381 s) → corrupt LRU hit.

**Secondary destroyer (found during QA):** `ensure_mp4_playback_timestamps` → `normalize_mp4_browser_playback_timeline` re-encoded good 132 MB aligned concat down to 82 MB / 178 s drift before bake encode ran.

## Implementation steps

1. **`credentials_lib/ffmpeg_stitch.py`**
   - `preview_cache_is_valid`: reject when `av_duration_drift_s(path) > STITCH_EXPORT_AV_MAX_DRIFT_S` (0.25 s).
   - Marker comment: `STITCH_MODULE_BAKE_AV_PARITY_V1`.

2. **`production_server.py` — `_stitch_build_pipeline`**
   - Before concat: `assert_stitch_export_clips_av_aligned(slot_finals)`.
   - After concat / before return: if drift on `out_path` > threshold → `purge_stitch_cache_mp4` + `RuntimeError`.

3. **`server_handlers/stitch_editor.py`**
   - `stitch_cached_mp4_playable`: reject when A/V drift > threshold.
   - `_run_stitch_bake_core`: assert pipeline output + final `bake_path` A/V aligned before finalize.

4. **Tests**
   - `test_stitch_module_bake_av_parity.py`: misaligned fixture blocked; pipeline/bake source grep contracts.
   - Extend `test_stitch_cache_and_boundaries.py`: misaligned mp4 fails `preview_cache_is_valid`.
   - Extend `verify_stitch_slot_preview_video_durability.sh`: grep A/V parity markers.

5. **Runtime repair**
   - Delete corrupt `stitch_preview_57bf1ba8547d.mp4`.
   - Re-run module bake for Event_2; ffprobe canonical `M2_event_2_final.mp4` (v ≈ a ≈ 381 s, drift < 0.25 s).
   - Browser: module final preview plays past Phase A without black + audio-only tail.

---

## 3×3 agent debate (roles × rounds)

Three roles debate each implementation step across three rounds. Consensus: all five steps are necessary; no step alone is sufficient.

### Roles

| Role | Lens |
|------|------|
| **Pipeline engineer** | FFmpeg concat, cache LRU, partial writes |
| **QA / durability** | Tests, deploy parity, positive evidence |
| **Operator UX** | Storyboard bake failure messages, re-bake path |

### Round 1 — Is the problem class real?

| Role | Verdict |
|------|---------|
| Pipeline | Yes. Format duration follows audio; truncated video is invisible to current gate. Observed 178 s drift on disk. |
| QA | Yes. Reproduce is ffprobe-positive, not hypothetical. Must gate stream durations, not container. |
| Operator | Yes. Symptom (Phase A video then black + overlapping audio) matches stream mismatch exactly. |

### Round 2 — Step-by-step necessity

| Step | Pipeline | QA | Operator |
|------|----------|-----|----------|
| 1 `preview_cache_is_valid` A/V | Blocks corrupt LRU hits — without this, step 2 re-concat skipped | Contract test with misaligned fixture | Prevents "done" bake from stale cache |
| 2 Pre/post concat gates | Catches bad slot finals and bad concat output at source | Grep + integration test on `_stitch_build_pipeline` | Fail fast with clear error vs shipping M2 |
| 3 Bake pre/post encode | Encode can't fix missing video frames; post gate catches encoder regressions | Bake handler grep + ffprobe on output | Module preview trustworthy after bake |
| 4 Tests + verify script | Anti-regression matrix | Required for full QA commit | CI/pre-push catches reintroduction |
| 5 Delete + re-bake | Data fix alone is patch; gates + re-bake is category proof | ffprobe before/after is acceptance | Browser smoke is user-path proof |

**Consensus:** Implement 1–4 in code; 5 in QA pass. Deleting cache without 1–4 would be a patch.

### Round 3 — Error-proof / anti-hallucination

| Risk | Mitigation |
|------|------------|
| Claim fix works without re-bake | Mandatory ffprobe on new `M2_event_2_final.mp4` |
| Gate never runs | pytest + grep contracts on call sites |
| Threshold too loose | Reuse existing `STITCH_EXPORT_AV_MAX_DRIFT_S = 0.25` (Beat Gen parity) |
| Deploy not live | Mirror tooling → Dropbox + restart; curl health |
| Browser still broken | Play module preview past Phase A boundary in Storyboard UI |

**Unanimous:** Ship only when unit tests green, corrupt file removed, new bake drift < 0.25 s, browser plays full module.

## Acceptance criteria

| Check | Pass |
|-------|------|
| Misaligned clip rejected by `assert_stitch_export_clips_av_aligned` | ✓ |
| `preview_cache_is_valid` rejects v/a drift > 250 ms | ✓ |
| `_stitch_build_pipeline` gates pre/post concat | ✓ |
| `_run_stitch_bake_core` gates pre/post encode | ✓ |
| Event_2 re-bake: M2 v ≈ a, drift < 0.25 s | ✓ |
| Browser module preview past Phase A | ✓ |

## QA commands

```bash
cd Production/tools && python3 -m pytest tests/test_stitch_module_bake_av_parity.py tests/test_stitch_export_av_drift_gate.py tests/test_stitch_cache_and_boundaries.py -v
bash Production/scripts/verify_stitch_slot_preview_video_durability.sh
# mirror Production/tools + Production/lib → Dropbox, restart server
# POST /api/stitch_editor/bake, poll status, ffprobe M2_event_2_final.mp4
```
