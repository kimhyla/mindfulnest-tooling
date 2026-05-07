# Morning Handoff — 2026-04-17 AM

**Written autonomously overnight by Claude after Kim went to bed ~3:50 AM.**

## TL;DR — 60-second scan

1. **beat_05 lipsync: SOLVED.** Silence-compression approach works. Live at `Event_1/animation_clips/beat_05_lipsync.mp4` (9.27s). All dialogue intact, "I should have been more careful" lipsyncs cleanly. Two pauses shortened (1.38s→0.80s and 1.83s→0.80s).
2. **Tier 5 build: LANDED + REGISTERED (id=161).** Decisions 151/153/154/155 consolidated into one shared helper. Phase 4 adversarial fixes applied (CRITICAL newline escape, HIGH state-HTML rollback, MEDIUM reconcile + HTML dedup). Server restart needed to activate Python changes — do that first thing.
3. **2-lever Kling regen (cfg_scale=0.75): RAN AND FAILED.** Option D raw had good gaze but lipsync broke completely (intermittent mouth stamping, tail phrase dropped). You diagnosed this live via screenshots.
4. **FORENSIC RESEARCH complete (3 parallel agents).** Root cause: LatentSync (ByteDance under the hood) needs per-frame pixel variance + mouth geometry. Over-constrained Kling source = flat thin mouth line + frozen head = no signal for InsightFace landmarks or TREPA temporal loss.
5. **Locked decision registered (id=162) `LIPSYNC_SOURCE_MUST_PRESERVE_MOUTH_MOTION`.** Cascaded to CLAUDE.md Rule 8 §8.2 + PIPELINE_BRAIN_v1.md §19. SHORTCUT decision 160 closed as `outcome=failed`.
6. **Strategy 1 regen (Option E: negative-prompt-only gaze, cfg=0.5) RAN OVERNIGHT.** File: `beat_05_lipsync_strat1_exp_20260417-044454.mp4`. Theory: should preserve B's lipsync-friendly mouth + motion while pulling gaze forward via negatives only.
7. **Five QuickTime windows are open** for your 3-way (or more) A/B review (see below).

## The 3-way (or more) A/B for morning review

Five files to compare:

| Label | File | What it tests |
|---|---|---|
| **B (live baseline)** | `Event_1/animation_clips/beat_05_lipsync.mp4` | cfg=0.5, generic prompt, off-axis gaze, **good lipsync** |
| **D raw** | `Event_1/animation_clips/beat_05_option_D_kling_2lever_20260417-042007.mp4` | cfg=0.75, gaze+mouth+motion stacked, **gaze fixed** |
| **D lipsync** | `Event_1/animation_clips/beat_05_lipsync_2lever_exp_20260417-042007.mp4` | Above → ByteDance, **lipsync broke** |
| **E raw (NEW)** | `Event_1/animation_clips/beat_05_option_E_kling_strat1_20260417-044454.mp4` | Strategy 1: cfg=0.5, generic prompt, **gaze terms in negative prompt only** |
| **E lipsync (NEW)** | `Event_1/animation_clips/beat_05_lipsync_strat1_exp_20260417-044454.mp4` | E → ByteDance with silcomp audio |

**Strategy 1 hypothesis:** E should preserve B's lipsync-friendly mouth geometry + motion WHILE pulling gaze toward camera via suppression of "looking away/up/profile" in the negative prompt. Isolates the minimum lever needed.

**Morning verdict matrix:**

| Scenario | What to do |
|---|---|
| E looks good AND lipsync works AND gaze is forward | Promote E to live beat_05_lipsync.mp4. Document Strategy 1 as the new default pattern for beats 6-11. Seed the animation prompt library (SPEED-E) with E's prompt template. |
| E lipsync works but gaze didn't improve vs B | Kling's up-right gaze is more stubborn than hypothesized. Next step: try Strategy 2 (cfg=0.6 + positive prompt says only "eyes meet camera" — minimal positive lever). |
| E lipsync broke (like D did) | Means even the negative prompt was enough to destabilize LatentSync. Fall back to B as production default, investigate Kling start-end frame mode (future Lever 5) as the real gaze fix. |
| E looks uncanny / frozen | Unexpected, would mean the NEGATIVE prompt terms somehow constrained motion. Close Strategy 1, move to start-end frame mode. |

## Overnight review findings (agent with vision, programmatic comparison — Option D only)

An adversarial review agent extracted 5 frames from Option B (baseline) and Option D (2-lever) at 0.5s, 2.5s, 5.0s, 7.5s, 9.5s, and compared them visually. Logged to Directus activity_log id=111.

| Category | Verdict | Detail |
|---|---|---|
| Gaze | **D BETTER** | Pupils more camera-facing in D, especially first half. B has pupils consistently pointing up-and-camera-right (looking ABOVE camera). D returns to camera more often, less extreme off-axis drift. |
| Mouth visibility | **D BETTER** | D's head axis is flatter throughout. B tilts up/chin-lifts in the last third. Flatter head = ByteDance has an easier mouth target for the tail phrase — directly addresses the Options A/B/C failure mode. |
| Naturalness | **NATURAL** | Clear head translation, subtle tilt, evolving eye expression across frames. cfg_scale=0.75 did NOT produce the stiff mannequin the Phase 0 counter-agent warned about. Expression shifts from neutral → resigned → sad, appropriate to the apology line. |
| Artifacts | **None** | Character identity, shell harness, backpack straps, forest backdrop all stable across all 10 frames. |
| Lipsync file delta | **Identical 9.272993s** | 2-lever lipsync is 18.7% smaller / 19% lower bitrate — suggests less residual head-drift motion for ByteDance to overlay. Size drop = good signal here, not a quality regression. |

**Agent's overall recommendation: PROMOTE D, conditional on you eye-confirming the tail phrase "I should have been more careful" actually lipsyncs on playback.** I can't watch/listen to verify that last mile.

Phase 0 risks that were hypothetical: **both proved unfounded at cfg_scale=0.75.** The graduated approach (0.5 → 0.75 instead of → 1.0) vindicated — we have the prompt-adherence win without the uncanny freeze.

> **❗ NOTE (written later, after you reviewed playback):** the programmatic review above was FILE-LEVEL ONLY and missed what playback revealed. D's lipsync broke completely. The "conditional on eye-confirming playback" disclaimer was load-bearing. What actually happened — and why — is documented in the next section. **Do not promote D.**

## Forensic investigation (after your "lipsync went all nuts" feedback)

Spawned three parallel research agents. Findings consolidated:

### 1. Mouth-region frame forensics (B vs D source)
- **Option B mouth** (cfg=0.5, generic prompt): wide lip line with visible seam depth, corner shadows, mouth-interior hints at some frames, clear cheek-plane vs lip-plane separation. Expression actually CHANGES across timestamps (small smile beats, head tilts rotate the mouth axis).
- **Option D mouth** (cfg=0.75, stacked gaze+mouth+motion prompt): a thin, narrow, downturned frown line painted on a flat face. No seam depth, no corner shadows, no interior hints. Across 7 sampled timestamps (1s through 9s), **frame-to-frame indistinguishable.**
- **D's post-lipsync:** over-stamped at 1-3s (mouth bleeds past lip zone into cheek pixels, visible "double-chin" ghost), under-stamped at 5-7s (frown shows through almost unchanged), collapses at 9s. Intermittent, not consistent failure.

### 2. Architecture research (why this happens)
ByteDance LipSync = **LatentSync** under the hood. Uses:
1. **InsightFace landmark detection** to affine-align the face every frame.
2. **TREPA temporal-consistency loss** that needs per-frame variation to anchor alignment.
3. **Fixed rectangular mask** over the face region — regenerates the whole mouth from audio + surrounding context.

When Kling produces a source with near-zero head motion + uniform flat mouth pixels (exactly what "cfg=0.75 + mouth closed + minimal motion + head facing forward" stacks produce), InsightFace landmarks jitter → affine misalignment → mask "swims" → intermittent stamping. Kling's own docs call cfg_scale 0.7-1.0 "Precise Mode" and note artifacts "concentrate in the mouth region" there.

**One-sentence version:** we over-constrained the source so thoroughly that ByteDance had neither mouth geometry to stamp onto nor motion signal to track against.

### 3. Combination strategy (3 ranked options)
- **Strategy 1 (recommended — RAN TONIGHT as Option E):** cfg=0.5, generic motion prompt, gaze control via **negative prompt only**. Preserves B's lipsync-friendly recipe; relies on suppressing Kling's default "look away/up" tendency to pull gaze forward.
- **Strategy 2:** middle-ground cfg=0.6 + only "eyes meet camera" in positive (no mouth/motion locks).
- **Strategy 3:** Kling start-end frame mode — provide both first AND last frame as camera-facing stills, let Kling interpolate between the two anchors. Future work (~2hr implementation).

## The load-bearing lesson (LOCKED — Directus id=162)

**`LIPSYNC_SOURCE_MUST_PRESERVE_MOUTH_MOTION`** (severity HIGH, registered April 17, 2026, 04:50 UTC):

When a Kling clip is intended for downstream ByteDance LipSync, the source MUST preserve natural mouth geometry + per-frame micro-motion. Specifically:
- `cfg_scale ≤ 0.5` (Rule 8.1 default, no deviation on lipsync-targeted clips)
- Prompt MUST NOT contain motion-locking language (`"minimal motion"`, `"static camera"`, `"head remains facing forward"`, etc.)
- Rule 8.1 anti-lipsync terms (`"beak closed"`, `"mouth closed"`) stay required but must appear AT MOST ONCE, NOT reinforced with intensifiers (`"pressed"`, `"sealed"`, `"tight"`, `"clamped"`)
- Gaze control via **negative prompt only** — do NOT add positive-prompt gaze language to lipsync-targeted clips

**Do-not-stack rule:** on any lipsync-targeted clip, combining ANY TWO of `{cfg > 0.5, gaze lock, mouth lock beyond minimum, motion lock}` is forbidden.

### Cascade trail (Rule 18 Two-Write + Rule 20 Automatic Capture)
- ✅ Directus `prod_locked_decisions` id=162 (active)
- ✅ Directus `prod_locked_decisions` id=160 closed as `status=superseded, outcome=failed`
- ✅ Directus `prod_activity_log` id=112 (registration trail)
- ✅ `CLAUDE.md` Rule 8 — added §8.2 "Lipsync pipeline incompatibility"
- ✅ `Production/PIPELINE_BRAIN_v1.md` §19 — appended lipsync-targeted Kling rules section
- ✅ `Production/MORNING_HANDOFF_2026-04-17_AM.md` (this doc) — full capture

## Option E (Strategy 1) overnight review findings — agent forensic analysis

Logged to Directus activity_log id=113. TL;DR: **PROMOTE E pending your playback confirmation. MEDIUM-HIGH confidence.**

### File-level comparison

| File | Duration | Size | Observation |
|---|---|---|---|
| B raw | 10.04s | 5.94 MB | baseline |
| D raw | 10.04s | 3.88 MB | 65% of B — less motion energy |
| **E raw** | 10.04s | **4.58 MB** | **77% of B, 118% of D — intermediate motion** |
| B lipsync | 9.27s | 808 KB | — |
| D lipsync | 9.27s | 657 KB | — |
| **E lipsync** | 9.27s | **681 KB** | **closer to D — YELLOW flag (noted below)** |

### Frame-level findings

**Gaze (head + eyes):** E's head stays camera-facing at all 5 timestamps — **win over B.** Eyes still drift up at 2.5s and 5.0s, partial win. Negatives suppressed head rotation but not eye-direction. **Net: clear improvement over B, not as fully-pinned as D.**

**Motion / expression:** E has real frame-to-frame variance, especially 5.0s → 7.5s (head tilts down, eyes lower into a sorrowful pose not seen in B or D). **Not frozen like D, not as expressive as B.**

**Mouth geometry:** E has 3D volume, corner shadows, plane separation between upper/lower jaw. Not as wide as B's smile, but not D's flat thin frown. **Stampable.**

**Post-lipsync stamping:** At all 5 sampled timestamps (0.5s, 2.5s, 5.0s, 7.5s, 9.0s), mouth stamps are consistent, plausible, and integrated. **No "giving up" region like D had at 5-7s. No double-chin ghost. No bleed-past-lip artifacts.**

### The yellow flag

E lipsync file size (681 KB) sits closer to D's failed version (657 KB) than to B's success (808 KB). Could indicate:
- **Benign:** E has less motion than B → compressor found less to encode → smaller file. B lipsync compresses well at 808 KB; similar-motion E should compress similarly.
- **Concerning:** Source was just flat enough for mild LatentSync drift, which would show as phoneme misalignment only audible on playback, not visible in frame samples.

**Only your ears can disambiguate.** Frame-level signals are CONSISTENT and B-pattern-like; lipsync size is NEAR BUT NOT MATCHING D-pattern.

### Strategy 1 hypothesis — validated

The forensic agent's verdict: **Strategy 1 is the right lever family.** Negative-prompt-only gaze suppression preserves the mouth + motion characteristics LatentSync needs. The weakness is that negatives are softer than positives — head pose pulls forward, but eye direction still drifts. If you want fully-camera-pinned eyes, Strategy 2 (mild positive `"eyes meet camera"` at cfg=0.6, no motion lock) might land it without re-breaking lipsync.

### Morning verdict paths (updated with Option E data)

| E's lipsync on playback | Action |
|---|---|
| **Works cleanly** | Promote E to live. Close strategy chain. Register `STRATEGY_1_VALIDATED_GAZE_VIA_NEG_PROMPT` as follow-up locked decision. Use Strategy 1's prompt template as the default for beats 6-11 + seed the animation prompt library (SPEED-E). |
| **Works but eye drift bothers you** | Keep E. Separately test Strategy 2 (~$0.60) to see if mild positive-prompt eye language pins the eyes without re-breaking the mouth. |
| **Still breaks** | The yellow-flag-on-file-size hypothesis wins. Means even negative prompts destabilized LatentSync subtly. Fall back to B as production. Long-term fix = Kling start-end frame mode (Lever 5, future ~2hr build). |
| **Uncanny / frozen** | Unexpected. Would mean negatives somehow constrained motion. Abandon Strategy 1 family, move to start-end frame. |

## AFTERNOON UPDATE — Start-end frame pipeline V1 VALIDATED (April 17, 13:49)

**Status:** beat_05 now uses the new start-end-frame pipeline. Live file `beat_05_lipsync.mp4` is the start-end V1 output. Prior silcomp winner preserved.

### What was built

- **`tools/kling_startend_pipeline.py`** — reusable CLI. Flags: `--beat`, `--end-prompt`, `--end-image`, `--positive-prompt`, `--duration`, `--dry-run`, `--skip-lipsync`, `--silcomp-audio`, `--video-trim-s`. Hard-coded defaults only for beat_05 Tessa (V1 scope).
- **`Production/governance/kling_startend_pipeline_governance.md`** — per-skill governance checklist per Rule 17.
- **CLAUDE.md §8.3 + §8.4** — cascaded rule set with "when to use §8.3 vs §8.4" routing guide.
- **PIPELINE_BRAIN §19** — new decision rows + "routing guide for beats 6-11."

### Validation evidence (beat_05)

| Version | Lipsync size | Opening | Tail | Gaze |
|---|---|---|---|---|
| B (silcomp) | 808 KB | ✅ | ✅ | off-axis |
| D | 657 KB | ❌ | ❌ | camera-facing |
| E / F / F-trims | 681-767 KB | mixed | mixed | various |
| **Start-end V1** | **957 KB** | **✅** | **✅** | **camera-facing** |

Kim's verdict: "works good enough — not exactly perfect — I'm satisfied."

### Routing guide for beats 6-11

| Beat / creature | Pipeline | Why |
|---|---|---|
| **beat_02 Luna** (owl discovery, excited, some open-beak) | **V2 work required** — Rule 8.1 beak-closed conflicts with Luna excited states. Defer. |
| **beat_06+ single-creature closed-mouth dialogue** | **§8.3 start-end via `kling_startend_pipeline.py`** — once Luna-or-equivalent provides second-creature validation. |
| **Action beats** (Bramble knocks, Bork loudspeaker) | **§8.4 silcomp-only** with default `_handle_animate` — gaze doesn't matter when creature isn't addressing viewer. |
| **Open-mouth excited beats** | NOT SUPPORTED. V2+ work with Rule 8.1 relaxation for specific creatures. |

### Recommended next step (when you're back)

Run the pipeline on **beat_02 Luna** (or any single-creature-dialogue beat that isn't Tessa) to attempt the second-creature validation that would promote §8.3 from "Tessa-only" to general. Pattern:

```
python3 tools/kling_startend_pipeline.py --beat beat_02 \
    --end-prompt "Same character, same outfit, same lighting, same cartoon 3D Pixar-style. Luna the owl softens her expression slightly, eyes momentarily lower with a warm glow of 'oh, I see!' awareness. Beak still closed, no speech. Head tilted subtly with attentive listening posture." \
    --dry-run
```

Start with `--dry-run` to preview the Kontext end frame before spending $0.45 on Kling. If it looks right, re-run without `--dry-run` for full pipeline.

## Final overnight Directus state

| ID | Collection | Key/Title | Status |
|---|---|---|---|
| 23 | prod_preflight_reviews | Tier 5 build | approved |
| 24 | prod_preflight_reviews | Kling 2-lever regen | approved |
| 52 | prod_reference_docs | MORNING_HANDOFF_2026-04-17_AM | active |
| 109 | prod_activity_log | tier5_build_landed | logged |
| 110 | prod_activity_log | kling_2lever_regen_submitted_and_recovered | logged |
| 111 | prod_activity_log | kling_2lever_adversarial_review_complete | logged (D findings) |
| 112 | prod_activity_log | locked_decision_registered_and_superseded | logged |
| 113 | prod_activity_log | kling_strat1_adversarial_review_complete | logged (E findings) |
| 160 | prod_locked_decisions | SHORTCUT_RULE8_CFG_TEST_BEAT05 | **superseded** (failed) |
| 161 | prod_locked_decisions | TIER5_BUILD_LANDED | active (needs restart) |
| **162** | prod_locked_decisions | **LIPSYNC_SOURCE_MUST_PRESERVE_MOUTH_MOTION** | **active** |

Total overnight cost: **$1.20** (two Kling regens at $0.60 each, both completed successfully).

Total file assets created/preserved overnight:
- beat_05_lipsync.mp4 (silcomp winner, live)
- beat_05_option_D_kling_2lever_*.mp4 + beat_05_lipsync_2lever_exp_*.mp4 (D, failed lipsync)
- beat_05_option_E_kling_strat1_*.mp4 + beat_05_lipsync_strat1_exp_*.mp4 (E, pending playback)
- All prior versions preserved in `Event_1/preserved_winners/`

Sleep well. I'll be here when you wake up.

## Morning A/B review — three questions

Open QuickTime, compare these:

### Question 1: Does the new Option D (2-lever Kling) look better than Option B (no levers)?
- **Option B** (source of silcomp winner): `animation_clips/beat_05_option_2.mp4`
- **Option D** (new, 2 levers): see manifest at `Event_1/beat_05_kling_2lever_manifest_*.json`
- **Look for:** Does Tessa's gaze hold the camera more consistently in D? Is the mouth more visible throughout? Is there still subtle natural motion, or does cfg_scale=0.75 make it look frozen/uncanny?

### Question 2: Does D's lipsync beat the silcomp winner?
- **Silcomp winner** (live): `animation_clips/beat_05_lipsync.mp4`
- **D's lipsync**: `animation_clips/beat_05_lipsync_2lever_exp_*.mp4`
- **Look for:** Tighter phoneme matching on "I should have been more careful"? Less mouth-drift?

### Question 3: Natural or uncanny?
If D looks frozen or unnatural, the cfg_scale=0.75 over-weighted the negative prompt — the counter-agent's CRITICAL concern. In that case: revert, close `SHORTCUT_RULE8_CFG_TEST_BEAT05` as `status=failed`, keep silcomp winner, and the lessons-learned note below explains what we learned.

## Decision tree based on your verdict

**If D WINS (better gaze AND better lipsync, natural motion):**
- Promote D's lipsync to `beat_05_lipsync.mp4`
- Validate on Luna (beat_02) with same 2-lever prompt template
- If Luna also wins → amend Rule 8 via new `RULE8_CFG_SCALE_AMENDMENT` decision + CLAUDE.md cascade via pipeline-sync
- The 2-lever prompt template (GAZE_PROMPT in `tools/beat_05_kling_2lever_experiment.py`) becomes the seed for the SPEED-E animation prompt library

**If D is WORSE (uncanny/frozen/off):**
- Keep silcomp winner as beat_05 live
- Close `SHORTCUT_RULE8_CFG_TEST_BEAT05` as `status=superseded, outcome=failed`
- Document failure mode in lessons learned (feeds back to prompt library design)
- Next creative attempts for beats 6-11 use the silcomp pattern (compress silences > 1.0s to 0.8s, keep Rule 8 cfg_scale=0.5, improve prompts without cfg_scale change)

**If D is COMPARABLE (no clear win):**
- The levers don't move the needle enough to amend Rule 8
- Close SHORTCUT as `status=inconclusive`
- Proceed with silcomp pattern for beats 6-11

## What you need to do FIRST in the morning

1. **Restart the production server** — Tier 5 Python changes are merged but not yet running. Restart activates: `_patch_storyboard_L_field` helper, `_handle_assign_image` rollback on HTML failure, lipsync source_changed tracking, mark_done reconcile. HTML changes (Re-run button, 10s refresher, shared renderer) are live on next page reload.
2. **Run the three A/B comparisons above** (Option B vs D, silcomp lipsync vs D lipsync, uncanny check)
3. **Apply the decision tree** based on your verdict
4. **If Tier 5 behavior is all good,** mark decisions 151/153/154/155 as `status=closed` in Directus (they're consolidated by `TIER5_BUILD_LANDED` id=161)

## Directus state as of handoff

| Collection | ID | Key | Status |
|---|---|---|---|
| prod_preflight_reviews | 23 | Tier 5 build | approved |
| prod_preflight_reviews | 24 | Kling 2-lever regen | approved |
| prod_locked_decisions | 160 | SHORTCUT_RULE8_CFG_TEST_BEAT05 | active (awaiting A/B verdict) |
| prod_locked_decisions | 161 | TIER5_BUILD_LANDED | active (needs server restart) |
| prod_activity_log | 109 | tier5_build_landed | logged |

## Tier 5 Phase 4 fixes applied (pending server restart)

All five counter-agent findings from the adversarial review addressed:

1. **CRITICAL — Newline escape** in `_patch_storyboard_L_field`. Multi-line dialogue edits would have killed the storyboard's script block on next load.
2. **HIGH — `_handle_assign_image` now returns 500 + rolls back** state + in-memory override if HTML patch fails. Previously it silently returned 200 with stale HTML (the exact bug class decision 154 exists to prevent).
3. **MEDIUM — `mark_done` reconciles `source_changed`** when lipsync completes. Covers the gap where the user changed selection while lipsync was in flight.
4. **MEDIUM — Three completed-state renderers deduped** into `applyCompletedButtonState`. Matches `patch_lipsync_buttons.py` script. One place to audit.

## Lessons learned — to be expanded together

Some patterns that emerged tonight (draft — we'll refine together after A/B):

### The "server state vs HTML file snapshot divergence" is a systemic bug class
Four separate bugs this session all had the same shape. One shared helper + one shared UI refresher is the architectural fix. Decision 161 `TIER5_BUILD_LANDED` captures this.

### ByteDance lipsync's tail-drop failure mode
When audio duration ≥ video duration - 0.2s, and the source video has any mouth-drift in its tail frames, ByteDance can silently drop the final phonemes. **Fix pattern:** keep `audio_duration + 0.4s ≤ video_duration` as a hard rule. If audio is too long, compress silences (not words) to buy tail room.

### Silence-compression as a creative-preserving fix
ElevenLabs TTS output has significant silence (~46% of beat_05's 9.88s was silence). Compressing the longest pauses preserves all spoken words AND all within-phrase pacing — only dramatic pauses get tightened. Documented as pattern:

```
For lipsync pipeline, pre-process audio:
  1. ffmpeg silencedetect at -32dB / 150ms threshold
  2. For each silence > 1.0s, compress to 0.8s (concat demuxer)
  3. Target audio_duration + 0.4s ≤ video_duration (Kling max 10s → audio ≤ 9.6s)
  4. Video trim to audio_duration + 0.4s (tail room for mouth close)
```

Future candidate for Tier 4 stitch pipeline.

### WaveSpeed polling still fragile
Tonight's Kling regen hit the same urllib-stuck-state pattern we fixed for production_server earlier today. The fresh-connection-per-poll pattern recovered it. **Action:** standalone scripts like `beat_05_kling_2lever_experiment.py` should use the same `http.client + OP_NO_TICKET` pattern as `production_server.WaveSpeedClient`. Or — better — refactor them to import WaveSpeedClient directly instead of re-rolling.

### Kim's domain knowledge continues to improve verdicts
Three times tonight Kim pushed back on my initial framing and it produced a better outcome:
1. "Apply the same treatment to the start" — I'd only compressed one silence; she told me to do two. The second compression is what made the silcomp winner viable.
2. "The levers might create better results... let's find out tomorrow" — she refused to let me declare victory on silcomp alone; the 2-lever test gives us actual data to decide.
3. "Follow zero-error QA, prove successful execution at each step" — she insisted on the full discipline, which caught the 8s duration self-defeating issue in Phase 0 BEFORE we spent $0.60 on a guaranteed-to-fail test.

## What's next (beats 6-11)

Once A/B is resolved, beats 6, 7, 8, 9, 11 already have Kling clips and just need lipsync. Beat 10 is `failed` status and needs resubmit.

Per the emerging pattern, the pipeline for each is:
1. Silence-compress audio (via the experiment script's splice_audio_multi helper, generalized)
2. Trim video to audio_duration + 0.4s
3. Submit lipsync
4. Pre-fail CDN check + fresh-connection recovery if polling stalls

Worth building the silence-compression + trim + submit as a single `Production/tools/lipsync_beat.py --beat beat_06` CLI before doing beats 6-11 — would turn 5 more beats into a 15-minute task instead of 5 manual runs.
