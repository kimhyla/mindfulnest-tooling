# HANDOFF — Per-Creature Motion Vocabulary Implementation (OUTCOME)

**Session:** MOTION_VOCABULARY_V1_IMPLEMENTATION_20260419
**Session date:** 2026-04-19
**Execution mode:** Autonomous (Claude Code terminal CLI)
**Parent handoff:** `HANDOFF_20260419_motion_vocabulary_implementation.md`
**Preflight row:** `prod_preflight_reviews` id=104
**Status:** COMPLETE — every STOP condition in the parent §11 is satisfied.

---

## 1. Summary

Per-creature, emotion-conditioned motion vocabulary now lives in `Production/tools/production_server.py`. `build_motion_prompt` was replaced with a 4-branch resolver that (a) canonicalizes the speaker through `_SPEAKER_ALIAS`, (b) looks up one of 28 creature×register vocabulary strings in a new `SPEAKER_MOTION_PROFILES` dict, (c) chooses constraint and tail per `BIRD_SPEAKERS` membership and the `beat.lipsync_targeted` flag (default `True` per LD-180). The silent Chipper→turtle-constraint bug (raw-string `BIRD_SPEAKERS` check) is fixed at the canonicalization step and belt-and-suspendered by adding `"Chipper"` to the set. 17 unit tests pass, smoke test passes, invariants 15/15 pass, Event_1 sanity run shows 0 §8.2 violations across 10 narrative beats. Three locked decisions registered in Directus (ids 307, 308, 309). Dead-dict question (`MOTION_PROMPTS` in `generate_animation_options.py`) resolved by 20-agent debate converging on **Option B+** (legacy header + runtime gate requiring `--allow-legacy-prompts`).

---

## 2. Files Changed

| File | Change | Net lines |
|---|---|---|
| `Production/tools/production_server.py` | Added `SPEAKER_MOTION_PROFILES` (7×4=28 strings), `LIPSYNC_SAFE_TAIL`, `SPRITE_IDLE_TAIL`, `VALID_EMOTIONS`, `_canonicalize_speaker`, replaced `build_motion_prompt` with emotion-aware version; added `"Chipper"` to `BIRD_SPEAKERS`; updated `run_smoke_test` assertions for new default tail + canonical-name surfacing | +~95 |
| `Production/tools/tests/test_motion_prompt.py` | NEW — 17 unittest cases | +307 |
| `Production/tools/generate_animation_options.py` | Legacy banner above `MOTION_PROMPTS`; new `--allow-legacy-prompts` flag; CLI entry refuses without flag, emits WARN with flag | +~40 |
| `Production/tools/_session_20260419_motion_vocab_directus_ops.py` | NEW — session helper for Directus writes (preflight / LDs / activity log) with retry + `pending_directus_writes.json` fallback per Rule 20 | +275 |

---

## 3. Directus Writes

### 3.1 Preflight review
- `prod_preflight_reviews` id=104 (`task_type=architectural`, 5 advocate + 5 counter agents, `approved_to_proceed=True`, 3 BLOCKs converted to 5 mitigations M1–M5 baked into implementation)

### 3.2 Locked decisions
- `prod_locked_decisions` id=307 — `MOTION_VOCABULARY_PER_CREATURE_V1` (MEDIUM)
- `prod_locked_decisions` id=308 — `MOTION_TAIL_LIPSYNC_SAFE_V1` (HIGH; severity upgraded from MEDIUM per counter-agent C4's LD-162 concern during preflight)
- `prod_locked_decisions` id=309 — `BIRD_SPEAKERS_CANONICALIZATION_FIX_V1` (LOW)

### 3.3 Activity log (6 rows)
- `prod_activity_log` 811 — `preflight_completed`
- `prod_activity_log` 861 — `locked_decisions_registered`
- `prod_activity_log` 862 — `code_write_completed`
- `prod_activity_log` 863 — `tests_written_and_passing`
- `prod_activity_log` 864 — `sanity_runs_completed`
- `prod_activity_log` 865 — `dead_dict_resolved_option_b_plus`

### 3.4 Blockers
- `app_blockers` id=224 — LOW, `prod_reference_docs drift (51 issues, unrelated to motion vocab session)`. Opened per Rule 15 session-end sync safety net.

### 3.5 Pending writes
None. One earlier `prod_activity_log` attempt failed (JSON-typed `details` was sent as string); replayed successfully after schema fix. `pending_directus_writes.json` never received a persistent row.

---

## 4. Dead-Dict Resolution — Option B+

### 4.1 Vote trace (20 agents, 3 rounds)

| Round | Agents | A (delete) | B (legacy header) | B+ (header + runtime gate) | C (migrate) |
|---|---|---|---|---|---|
| R1 | 5 advocates + 5 counters | 4 | 5 | — | 1 |
| R2 | 5 | 1 | 1 | 3 | 0 |
| R3 (acceptability reframe) | 5 | 0 | 1 | 4 | 0 |
| **Cumulative** | **20** | **5** | **7** | **7** | **1** |

### 4.2 Convergence argument

B+ reached 7 first-choice votes (= Kim's "strong" threshold) AND is a strict superset of B. Combined B/B+ = 14/20. Round 3 acceptability check: 100% live-with B+, 100% live-with B, 60% live-with A. R2-5 (swing vote) summary: "B+ is the strict superset of B that the A camp can accept and the B camp already wanted."

### 4.3 Execution

- Legacy banner inserted above `MOTION_PROMPTS` dict in `generate_animation_options.py` (cites Rule 8.2 violations, LD-162, LD-183, points to `SPEAKER_MOTION_PROFILES`).
- `--allow-legacy-prompts` argparse flag added to `main()`.
- Without flag: `sys.exit(2)` with a detailed REFUSED message enumerating the §8 violations.
- With flag: loud WARN banner to stderr, then normal execution path.
- Dry-run test: PASS (refused without flag; proceeded with flag + WARN).

---

## 5. Preflight Mitigations (M1–M5) — All Applied

| ID | Origin | Mitigation | Status |
|---|---|---|---|
| M1 | Counter C2 | `run_smoke_test` updated to set `lipsync_targeted` on both narrative (True) and sprite (False) test beats; added canonical-name-surfacing assertion | Done (production_server.py smoke PASS) |
| M2 | Counter C1 | Test 11's §8.2 scan uses word-boundary regex `\b(pressed\|sealed\|tight\|clamped)\b` so "body tightening" (legitimate motion verb) does not false-positive on the `tight` intensifier | Done (test 11 passes) |
| M3 | Counter C3 | `_canonicalize_speaker` strips whitespace; tests 13–16 cover None / empty / whitespace-only / trailing-space / None-emotion edge cases | Done (all pass) |
| M4 | Counter C4 | `MOTION_TAIL_LIPSYNC_SAFE_V1` severity upgraded MEDIUM → HIGH; `decision_text` now cites LD-162 `LIPSYNC_SOURCE_MUST_PRESERVE_MOUTH_MOTION` as the rationale | Done (LD 308 written with HIGH) |
| M5 | Counter C5 | This §5 documents the scope gap — `kling_startend_pipeline.py` line 96 `DEFAULT_POSITIVE_PROMPT` is independent of `build_motion_prompt`. See §7 below. | Done |

---

## 6. Sanity Run Results

### Event_1 representative sample (`storyboard_lines_v22.json`)
- 11 beats loaded, 1 stage-direction beat skipped (no speaker vocabulary path), 10 narrative beats scanned.
- **§8.2 violations: 0** (both multi-word phrases and word-boundary intensifier regex).
- **Sanitize strip audit: 0** vocabulary substrings lost to `sanitize_prompt` — all 10 assembled prompts retain their creature-register vocabulary intact. (The pre-existing constraint-line strip of `"speech"` / `"dialogue"` / `"lip movement"` by `sanitize_prompt` is out of scope; see §7.2.)
- Tessa 4-register distinctness: verified (happy_excited / upset_shocked / sad_disappointed / neutral all produce visibly distinct prompts).

### Sprite smoke
- `{"speaker": "Tessa", "emotion": "neutral", "lipsync_targeted": False}` → tail is `"Silent subtle idle movement only"` (motion-locking). **PASS**
- `{"speaker": "Tessa", "emotion": "happy_excited", "lipsync_targeted": True}` → tail is `"no dialogue in video"` (non-motion-locking). **PASS**

### Chipper regression
- All 6 alias forms (`Chipper`, `chipper`, `Guide Bird`, `guide bird`, `Pip`, `pip`) route to bird constraint (`"Beak closed, no speech, no lip movement."`) AND surface canonical name `"Cartoon Chipper character"` in the prompt. **PASS**
- LD `BIRD_SPEAKERS_CANONICALIZATION_FIX_V1` verified.

---

## 7. What The Next Session Needs To Know

### 7.1 Regenerating Event_1 animations against the new vocabulary

The three live call sites for `build_motion_prompt` in `production_server.py` (lines 4401, 4777, 5075) are unchanged structurally — they continue to call `sanitize_prompt(build_motion_prompt(beat))` with a beat dict. Event_1 beats in `storyboard_lines_v22.json` do **not** currently carry `emotion` or `lipsync_targeted` keys. Under the new code, every Event_1 beat therefore gets:
- `emotion` = `"neutral"` (default)
- `lipsync_targeted` = `True` (default per LD-180)
- → creature's **neutral** register vocabulary + non-motion-locking `"no dialogue in video"` tail

If Event_1 regen is planned against richer emotional registers, the storyboard authoring needs to add `emotion` keys per beat. This is NOT required for functional correctness — neutral registers are already an improvement over the generic `SECTION_ACTIONS` fallback — but it unlocks the full 4-register expressiveness.

### 7.2 Pre-existing `sanitize_prompt` / constraint-line inconsistency (out of scope, not introduced here)

`BANNED_PROMPT_WORDS` contains `"speech"`, `"dialogue"`, and `"lip movement"`. The §8.1-required constraint line also contains those tokens (`"no speech"`, `"no lip movement"`, plus the `"no dialogue in video"` tail). `sanitize_prompt` therefore strips those words from the constraint line of every assembled prompt (it has done so since the function was written). End result shipped to Kling today: `"Cartoon X character, [vocab]. Mouth closed, no . no in video"`. This session preserved the original behavior — test 17 scopes the no-op assertion to the vocabulary portion only. **If the next session wants to fix this**, the right change is probably in `sanitize_prompt` itself (e.g., whitelist `"no speech"`, `"no dialogue"`, `"no lip movement"` as allowed constraint phrasings) rather than in the vocabulary. File an LD if you go that direction.

### 7.3 §8.3 kling_startend_pipeline scope gap (M5)

`kling_startend_pipeline.py` uses its own `DEFAULT_POSITIVE_PROMPT` at line 96 and does NOT route through `build_motion_prompt`. Per LD-180, the §8.3 start-end pipeline is the universal default for Event_1 lipsync-targeted beats. This means the new `SPEAKER_MOTION_PROFILES` vocabulary currently applies only to the legacy single-image Kling path in `production_server.py` (call sites 4401, 4777, 5075, 7232) — NOT to §8.3 start-end clips. Counter-agent C5 flagged this in preflight; it is a known scope limitation and documented here as M5. A follow-up task could route `kling_startend_pipeline.py` through `build_motion_prompt` to unify vocabulary across both paths; that's architectural work requiring its own preflight.

### 7.4 Dead-dict status — B+ follow-through

`generate_animation_options.py::MOTION_PROMPTS` is gated but present. If EvoLink credits are topped up and someone tries to generate Options B+C for Event_1 remaining beats (1, 2, 4, 7, 8, 9, 10 per Apr 14 handoff Step 2), they must either (a) migrate the image-keyed prompts to route through `SPEAKER_MOTION_PROFILES`, or (b) pass `--allow-legacy-prompts` accepting the §8.2 violations. Recommendation: when revival is imminent, do (a) — this becomes a natural follow-up to §7.3 above (a shared `motion_profiles.py` module extracted from `production_server.py`).

---

## 8. Reference Docs Registry Changes

- **Handoffs are transient** — the parent handoff (`HANDOFF_20260419_motion_vocabulary_implementation.md`) and this OUTCOME are not registered in `prod_reference_docs`. Per the parent §9: "handoffs are transient."
- `production_server.py` is production code, not a reference document — not registered.
- `test_motion_prompt.py` is a test artifact — not registered.
- `sync_reference_docs.py` flagged 51 pre-existing drift issues unrelated to this session. Logged as `app_blockers` id=224 (LOW, owner=Kim) per Rule 15 session-end sync safety net.

---

## 9. STOP Conditions (§11) — All Satisfied

- [x] `prod_preflight_reviews` id=104 exists, `approved_to_proceed=True`
- [x] `production_server.py` edits live; `build_motion_prompt` replaced; `SPEAKER_MOTION_PROFILES` present; `BIRD_SPEAKERS` includes `Chipper`; `_canonicalize_speaker` added
- [x] `Production/tools/tests/test_motion_prompt.py` exists with 17 cases (12 from parent §5 spec + 5 edge-case tests added per M3)
- [x] All tests pass (17/17) — verified via `python3 -m unittest tests.test_motion_prompt`
- [x] 3 rows in `prod_locked_decisions` (307 vocabulary, 308 tail, 309 bird-fix)
- [x] 6 rows in `prod_activity_log` (≥5 required)
- [x] Dead-dict decision made via 5+5(+5+5+5) debate; outcome B+ executed; debate logged
- [x] Sanity runs clean (0 §8.2 violations across 10 Event_1 narrative beats)
- [x] `sync_reference_docs.py` ran; 51 pre-existing drift issues logged to `app_blockers` 224 (LOW)
- [x] `OUTCOME.md` handoff written (this file)
- [x] No `.docx` was modified this session
- [x] No shortcuts taken; no TODO / FIXME / placeholder left in any file

---

**End of OUTCOME handoff.**
