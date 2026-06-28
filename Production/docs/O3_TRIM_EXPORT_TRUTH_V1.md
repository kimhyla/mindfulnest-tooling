# O3 Trim Export Truth — Tech Spec v1

**Status:** Implemented (2026-06-22)  
**Owner:** mindfulnest-tooling (`storyboard-v2`, `beat_generator.py`, `server_handlers/background.py`, `media_playback_cache.py`)  
**Event proof target:** Event_2 intro Beat Gen (`http://127.0.0.1:5112/?event=Event_2`)  
**Branch:** `feat/bg-job-truth-complete`

---

## Problem class

Cut UI, Apply Cut, Preview Cut, and Send to Stitcher must agree on **one timeline** per O3 option (`video_path` + trim window). Today they can diverge because:

| Layer | Symptom | Root cause |
|-------|---------|------------|
| Overlay handles | Drag on wrong timeline | Client uses stale `<video>.duration` (`loadedDuration` not reset on clip change) |
| Apply Cut | Sidecar has no trim | Wrong `trim_back` math from wrong duration; `pendingCut` cleared even on failed persist |
| Preview Cut | Full clip, “playing cut preview” | Preview uses **saved** trim; empty sidecar → server copies full file; UI treats any preview URL as success |
| Export | Full clip in stitch slot | Export path is correct **when trim exists** — upstream gates failed |

**Partial validation:** When trim is saved with server-correct math (e.g. diagnostic apply with ffprobe-aligned values), preview and export respect it. That confirms the export materializer is not the bug — **truth alignment before persist** is.

---

## Relationship to prior specs

| Spec | What it covers | This spec |
|------|----------------|-----------|
| `BG_O3_PER_OPTION_CUT_TRIM_SPEC_v1.md` | Per-option cut-out vs trim, waveform UI debate | **Keep-window trim** (`trim_start_s` + `trim_back_s`) shipped via overlay; this spec fixes **duration truth**, not cut-out ffmpeg |
| `BG_O3_FFMPEG_DURABILITY_SPEC_v1.md` L1–L5 | Dropbox staging, bake-on-apply, export retry | **Orthogonal** — L3 bake runs after honest persist; export still uses `_kling_o3_export_clip_path` |
| `STORYBOARD_UNIFIED_PLAYBACK_SPEC_v1.md` §7.3 | No auto preview on play; explicit Preview Cut | **Enforces** honest preview contract; playback cache URL unchanged |

---

## Target contract — four gates

### Gate 1 — Server-owned duration (`TRIM_TRUTH_DURATION_V1`)

- **Source:** `POST /api/media/playback_resolve` → ffprobe on canonical `video_path` (already in `resolve_playback_url`; expose as `raw_duration_s`).
- **Client:** On selected tile with clip, fetch truth **before** enabling cut overlay math. **Never** derive trim window from `<video>.duration`.
- **Reset:** Clear `loadedDuration` and `sourceDurationS` when `video_path` / canonical URL changes.

### Gate 2 — Persist-or-fail Apply (`TRIM_TRUTH_PERSIST_V1`)

- Server already validates via `set_o3_option_trim` (ffprobe on exact `video_path`).
- Response must include `{ raw_duration_s, effective_duration_s, trim_start, trim_back }`.
- Client: if shortening requested (`trim_start > 0.05` or `trim_back > 0.05`) and `effective_duration_s >= raw_duration_s - 0.05` → error toast, **keep `pendingCut`**.
- Success toast only when shortening honored or explicit clear.

### Gate 3 — Honest Preview (`TRIM_TRUTH_PREVIEW_V1`)

- `preview_only` POST uses same validation as persist (in-memory `set_o3_option_trim`).
- Server: if shortening requested but `effective_duration_s` not shorter → `400 TRIM_PREVIEW_UNCHANGED`.
- Client: same check on response before `swapVideoToPreview`.
- No “playing cut preview” when scratch file is full length.

### Gate 4 — Export same resolver (`TRIM_TRUTH_EXPORT_V1`)

- No change to `materialize_kling_o3_trimmed_clip` / `_kling_o3_export_clip_path` — already ffprobe-based.
- **Tests:** start-only, end-only, both-handle, stale-UI-duration rejection, preview-unchanged rejection.

---

## Non-goals

- Waveform-under-video UI from `BG_O3_PER_OPTION_CUT_TRIM_SPEC_v1.md` (separate track)
- Middle cut-out (`cut_start_s`/`cut_end_s`) — edge trim only for overlay path
- Kid-app playback (LD-280)

---

## API changes

### `POST /api/media/playback_resolve`

Response adds alias (backward compatible):

```json
{
  "ok": true,
  "playback_url": "...",
  "duration_s": 5.042,
  "raw_duration_s": 5.042
}
```

### `POST /api/bg/kling-o3-trim` (preview_only)

New error when trim request does not shorten:

```json
{
  "ok": false,
  "error_code": "TRIM_PREVIEW_UNCHANGED",
  "error_message": "Preview would be full clip — adjust handles and Apply Cut first"
}
```

---

## UI changes (`BgOptionTile`)

1. `resolveClipPlaybackTruth(path)` → bind `sourceDurationS` from server.
2. Overlay uses `sourceDurationS` only (not `loadedDuration`).
3. Reset `loadedDuration` on clip URL change.
4. `applyDraftCut`: clear `pendingCut` only after persist success.
5. `applyCutPreview`: abort on `TRIM_PREVIEW_UNCHANGED` or missing honest preview.

---

## Test matrix

| ID | Scenario | Expected |
|----|----------|----------|
| T1 | `set_o3_option_trim` end crop on 5s clip | `effective_duration_s` ≈ 3s |
| T2 | `set_o3_option_trim` start crop only | `trim_start_s` honored |
| T3 | Preview request with trim_back on 5s, effective unchanged | `400 TRIM_PREVIEW_UNCHANGED` |
| T4 | `o3_trim_shortening_requested` helper | true/false edge cases |
| T5 | playback_resolve | `raw_duration_s` matches ffprobe |
| T6 | Export path with saved trim | materialize called with correct window |

---

## 3×3 agent debate (pre-implementation)

Three reviewers evaluated every gate for regression coverage. Subagents unavailable (usage limit); review performed inline from code + prior specs.

| Reviewer | Score | Verdict | Key finding |
|----------|-------|---------|-------------|
| **A — Comprehensiveness** | 7/10 | REVISE → addressed | Must include stale `loadedDuration` reset, playback_resolve duration wiring (not new endpoint), middle-cut path unchanged, bake-on-apply failure path (`O3_TRIM_BAKE_FAILED`) unchanged |
| **B — Appropriateness** | 8/10 | APPROVE | `playback_resolve` is correct probe surface (same file as export); build order G1→G2→G3→G4; do not defer pendingCut or preview honesty |
| **C — Accuracy** | 8/10 | APPROVE | Confirmed: `loadedDuration` not reset today (BgTab ~4352); preview copies full file when no trim (background `_trim_preview_url` else branch); `duration_s` already in `resolve_playback_url` (~104) but client ignores it |

**Consensus:** Ship all four gates in one category fix. Use existing `duration_s`/`raw_duration_s` from playback resolve. No new trim probe endpoint. Tests for preview-unchanged + start/end trim.

---

## Deploy & QA

1. `pytest` — `test_o3_trim_export_truth_v1.py`, `test_kling_o3_trim_durability.py`, `test_o3_per_option_trim.py`, `test_media_playback_cache.py`
2. `deploy_storyboard_v59.sh --event Event_2`
3. Restart `:5112`, verify `build-sha`
4. Browser: Beat 5 — drag end handle → Apply Cut → Preview Cut → duration shortens
5. curl: trim POST returns `effective_duration_s < raw_duration_s`

---

## References

- `Production/tools/beat_generator.py` — `set_o3_option_trim`, `resolve_kling_o3_trim_window`, `_kling_o3_export_clip_path`
- `Production/tools/server_handlers/background.py` — `handle_bg_kling_o3_trim`
- `Production/tools/storyboard-v2/src/components/BgTab.tsx` — `BgOptionTile`
- `Production/tools/storyboard-v2/src/components/bg/BgO3CutOverlay.tsx`
- `Production/tools/media_playback_cache.py` — `resolve_playback_url`
