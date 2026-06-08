# Phase A Chipper Pipeline v1

**Status:** Locked operational doc (June 2026)  
**Canonical code:** `mindfulnest-tooling/Production/`  
**Runtime state + media:** Dropbox `Production/Event_1/`  
**Storyboard:** `localhost:5111` → Phase A tab

---

## Architecture (LD-280)

Phase A ships as **one stitched MP4** (`phase_a_stitched_*.mp4`) built from three segments:

| Segment | Source | Notes |
|---------|--------|-------|
| Fly-in | Kling start→end | Empty desk still → Chipper still (**same crop/zoom**) |
| Sitting | Kling idle base → **Kling LipSync** | Dialogue middle; review before stitch |
| Fly-out | Kling start→end | Chipper still → empty desk still |

**Banned:** wide fly-in/out that changes bird scale at xfade joins. Use **closeup_match** bookends.

**UI quirk:** Phase A video player shows **lipsync middle only**. Full composite = stitched file or `/files?path=…`.

---

## Locked still / crop assets (Event_1)

| File | Role |
|------|------|
| `phase_a_chipper_closeup_newstyle_v2.png` | Full desk still (ChatGPT Jun 7) |
| `phase_a_chipper_closeup_crop_v3.png` | 800×600 desk crop (cropper) — **preferred for bookends + wide idle** |
| `phase_a_empty_desk_crop_v3.png` | Empty desk, **same bbox** as v3 Chipper crop |
| `phase_a_chipper_beak_crop_v4.png` | Tighter face crop — rejected (zoom + teeth worse) |
| `phase_a_chipper_wide_crop_v5.png` | Copy of v3 desk crop for F/G wide batch |

**Do not reuse** yellow-bg isolated portrait stills for production stitch.

---

## State keys (`production_state.json`)

| Key | Purpose |
|-----|---------|
| `phase_a_flyin_file` | **Pinned** fly-in MP4 for stitch (must respect on restitch) |
| `phase_a_flyout_file` | **Pinned** fly-out MP4 for stitch |
| `phase_a_lipsync_file` | Latest lipsync middle (may be withbed after mix) |
| `phase_a_stitched_file` | Canonical 3-clip output |
| `phase_a_chipper_sitting_clip_id` | Base clip id in `assets/lipsync_bases/` |
| `phase_a_flyin_flyout_status` | `running` \| `done` \| `error:…` during bookend regen |

---

## CLI scripts (all under `Production/tools/`)

| Script | Purpose |
|--------|---------|
| `phase_a_flyin_flyout_closeup_match_v1.py` | Regenerate closeup_match fly-in/out; pins to state |
| `phase_a_chipper_lipsync_base.py` | Single idle base from still → `assets/lipsync_bases/` |
| `phase_a_chipper_candidate_batch.py` | Batch idle variants + lipsync → `Event_1/phase_a_idle_candidates/` |
| `scripts/phase_a_restitch_from_state.py` | Restitch using **pinned** fly-in/out + latest raw lipsync |

### Candidate review workflow (no auto-stitch until Kim picks)

1. Run candidate batch (variants in script config).
2. Review lipsync URLs under `phase_a_idle_candidates/`.
3. Copy winner to `assets/lipsync_bases/<clip_id>.mp4`.
4. Regenerate closeup_match bookends from matching stills if crop changed.
5. Pin fly-in/out in state → restitch.

---

## Hallucinations: prompting vs model limits

| Artifact | Idle (Kling i2v) | LipSync (Kling Sync) |
|----------|------------------|----------------------|
| Teeth / fangs | Partially steerable via prompts | **Not prompt-controllable** — model defaults to human talking-head |
| Wing “arm” gesticulation | Partially steerable | Often **worse** during dialogue |
| Zoom / framing | Steerable (locked camera prompts) | Can drift |

**Prompt-only is insufficient** for tooth-free dialogue. Next approaches (in order):

1. **Kling Elements** — pass `element_list` for Chipper (`character_subjects.json` → `element_id`); add wing pose refs to `refer_images`.
2. **ChatGPT wing refs as start still** — frame zero must show correct tucked wings; prompts reinforce but don't replace pixels.
3. **Composite pipeline** — static body plate + beak-only lipsync overlay (Rhubarb / 2D mouth).
4. **Different vendor** for mouth-only pass.

ChatGPT reference PNGs **help idle generation** when used as the **start image** or registered in `character_subjects.json`. They **do not** fix LipSync teeth without a compositing strategy.

---

## API routes

| Route | Handler |
|-------|---------|
| `POST /api/phase_a/regen_flyin_flyout` | Background: closeup_match script → pin → auto-stitch |
| `POST /api/phase_a/regen_base_clip` | Background: idle base from `phase_a_chipper_closeup_newstyle_v2.png` |
| `POST /api/phase_a/lipsync` | Existing — Kling LipSync on selected base clip |
| `POST /api/phase_a/mix_audio` | Mix + triggers `_auto_assemble_phase_a_stitched` |

---

## Deploy

```bash
cd ~/Projects/mindfulnest-tooling
bash Production/scripts/deploy_storyboard_v59.sh
```

Deploy is **tooling → Dropbox rsync**. Scripts edited only in Dropbox are **ephemeral** and will be deleted on next deploy.

---

## QA checklist

1. `python3 -m pytest Production/tools/tests/test_phase_a_stitch_resolve.py -v`
2. Deploy script completes with sha256 + curl build-sha smoke
3. `curl -s http://localhost:5111/api/health` → ok
4. Pinned stitch: state `phase_a_flyin_file` used even when older `phase_a_flyout_v4_*.mp4` exists
