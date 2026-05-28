# Tech Spec — TTS / Kling Prompt Separation per Beat

**Version:** v1
**Status:** QUEUED (execution not scheduled)
**Authority:** LD-722 STORYBOARD_TTS_KLING_PROMPT_SEPARATION_DEFERRED_V1 (locked 2026-05-16)
**Reference doc:** `prod_reference_docs` id=224
**Spec doc location:** this file (`Production/docs/TECH_SPEC_TTS_KLING_PROMPT_SEPARATION_v1.md`)
**Spec doc written:** 2026-05-20 (during fabrication-scan remediation — the file was claimed by LD-722 + ref_doc 224 but never actually written; Kim caught it 2026-05-20 with "what other implementation specs or decisions were just left out?")
**Estimated execution effort:** 7-8 hours focused work

---

## §0 — Mandatory Operating Mode for Executing Sessions

This section is read FIRST by every terminal session executing any phase of this spec.

### §0.1 — Skill load + Phase 0 classification (Rule 19)
- Load `zero-error-qa` skill before any edit
- Classify task per Tier A/B/C
- This task is **Tier B (cross-cutting refactor)**: client + server + tests
- Write `prod_preflight_reviews` row via `try_post_or_queue` BEFORE any edit (Rule 35)

### §0.2 — Six-Layer Verification Contract
For every feature this phase touches, NOT done until all six verify:
1. UI element exists (the new `motion_prompt` textarea on each beat)
2. UI → backend wiring (`pathappPatch` `update_motion_prompt`)
3. Backend processing matches intent (server stores at `beat.motion_prompt`)
4. State update propagation (`/api/v2/event/<id>/state` returns the field)
5. UI re-render reflects new state (hydration on refresh shows persisted value)
6. End-to-end smoke: edit motion_prompt → Send for Lipsync → output reflects ONLY the motion field, not the dialogue

### §0.3 — Honest scope limits
- This spec is **mid-detail**, not full Cursor-cross-review-ready. The ORIGINAL tech-spec-skill output (two-Opus debate from 2026-05-16) was lost when the spec doc was never written to disk. This version is reconstructed from LD-722 + ref_doc 224.
- Before execution: regenerate the tech-spec via the `tech-spec` skill against this file as a starting point. The skill will surface gaps via 2-agent debate.

---

## §1 — Task

The MindfulNest storyboard couples ONE editable field (`beat.text`) to TWO downstream rendering passes:
1. **TTS audio** (ElevenLabs v3): reads `beat.text` to synthesize spoken dialogue
2. **Kling motion / FLUX end-frame**: reads `beat.text` through a dispatcher chain (`production_server.py:13077-13191` text-derived auto-synth + lines 13330-13363 `_motion_override` parenthetical stamp) to construct the visual motion prompt

Result: editing `beat.text` for dialogue tweaks silently re-synthesizes Kling visual output. All 20 live Event_1 beats have empty `end_frame_prompt` so auto-synth fires on every animation.

**Goal:** Split into two editable fields per beat — `beat.text` (TTS dialogue only) + `beat.motion_prompt` (the visual cue piped to FLUX Kontext / Kling start-end). Delete the text-derived fallback per Rule 27. No batch backfill — empty `motion_prompt` falls through to a deterministic speaker-only neutral-pose default that never reads `beat.text`.

## §2 — Governing Decisions

- **Rule 19** no shortcuts — fully ship the new field on both UIs (Preact + legacy `build_storyboard.py`)
- **Rule 22** app architecture watch list — no runtime TTS
- **Rule 27** delete obsolete workarounds — the text-derived auto-synth IS the obsolete workaround
- **Rule 35** Directus schema verify + `try_post_or_queue` read-back
- **§8.1** anti-lipsync banned words — `motion_prompt` is piped to Kling/FLUX so the input MUST be validated against `_BANNED_MOTION_WORDS` before send
- **§8.2** do-not-stack rule
- **§8.3** start-end pipeline default
- **LD-180** start-end universal default for Event 1
- **LD-443** must amend at execution time
- **LD-691, LD-699** body-key CI gate
- **LD-703** client surfaces skipped[] array
- **LD-718** endpoint-presence parity
- **LD-722** this LD (DEFERRED, governance authority)
- **LD-728** beat parenthetical convention v1 — visual cue, not voice direction
- **LD-733** TTS strip leading parenthetical (shipped 2026-05-20)
- **LD-756** trim semantics seconds-from-end (shipped 2026-05-20)

## §3 — Approach (Kim's 3 locked judgment calls)

**Call 1 — Two editable fields per beat, NOT three.**
- `beat.text` (TTS dialogue) — existing field, unchanged storage
- `beat.motion_prompt` (NEW) — UI label "Kling animation"
- Kling motion-prompt itself stays §8.2-safe hard-coded via Fix 8 (`production_server.py:13460`) because exposing it would risk lipsync starvation when Kim authors freeform motion language
- Internally `beat.motion_prompt` is piped to FLUX Kontext as the end-frame visual anchor — which controls Kling output in start-end mode (LD-180 universal default)

**Call 2 — Delete BOTH obsolete code paths per Rule 27.**
- `production_server.py:13077-13191` text-derived auto-synth fallback: DELETE
- `production_server.py:13330-13363` `_motion_override` parenthetical stamp: DELETE
- No batch backfill — empty `motion_prompt` field uses a deterministic speaker-only neutral-pose default that NEVER reads `beat.text`. Each speaker has one default neutral pose phrase.

**Call 3 — BG sidecar untouched per 2026-04-23 architectural boundary.**
- `Production/beat_generator_state.json` = FLUX stills offline pipeline
- Storyboard tab = animation live
- Verified via `Production/HANDOFF_BEAT_GENERATOR_TAB_COMPLETE.md` lines 31, 227, 1086
- This task touches ONLY the storyboard pipeline

## §4 — Implementation Phases (6 phases)

### Phase 1 — Schema + field skeleton (~1h)

- Add `beat.motion_prompt: str | None` to v3 partition schema (`Production/lib/v3_partition.py`)
- Add validator for `motion_prompt` to `_V2_MODULE_FIELD_VALIDATORS` in `production_server.py`
- Add `update_motion_prompt` endpoint to dispatch table + endpoints.ts
- Server handler stub (no business logic yet) writes to `beat.motion_prompt` via `mutate_video_state`
- Tests: payload-validator dispatch test confirms `motion_prompt` accepted

### Phase 2 — Client UI (~2h)

- Add `<textarea>` next to existing dialogue textarea, labeled "Kling animation"
- New state `motionPromptValue` + debounce → `pathappPatch('update_motion_prompt', ...)`
- Show speaker-default-neutral when field is empty (placeholder, not stored)
- Hydration from `beat.motion_prompt` on bootstrap response

### Phase 3 — Server dispatcher rewrite (~2h)

- Read `beat.motion_prompt` directly in `_handle_add_options_startend` instead of text-derived auto-synth
- If empty: emit `_SPEAKER_NEUTRAL_POSE[speaker]` default — does NOT touch `beat.text`
- Strip `§8.1` banned-motion-words validator at submit time → return 400 if violated
- Delete `production_server.py:13077-13191` auto-synth block
- Delete `production_server.py:13330-13363` `_motion_override` parenthetical stamp

### Phase 4 — Legacy `build_storyboard.py` parity (~1h)

- If legacy HTML storyboard is still in use anywhere, mirror the two-field UI there
- Otherwise: confirm legacy is fully sunset and skip
- Per LD-722 "Touches both UIs (legacy build_storyboard.py + storyboard-v2 Preact)"

### Phase 5 — Tests (~1h)

- Server unit test: empty motion_prompt → neutral pose default; populated → exact pass-through
- Client unit test: motion_prompt edits hit `update_motion_prompt` endpoint with debounce
- E2E Playwright: type in motion_prompt + send for lipsync → output respects motion_prompt only
- Pytest body-key contract gate: `update_motion_prompt` endpoint declared

### Phase 6 — Smoke + lock (~1h)

- Browser smoke per DS-21
- Lock `STORYBOARD_TTS_KLING_PROMPT_SEPARATION_IMPL_V1` on success
- Supersede LD-722 with `superseded_by_id` pointing to the new IMPL LD
- Update PIPELINE_BRAIN_v1.md to reference the new field

## §5 — Files Modified

| File | Change |
|---|---|
| `Production/lib/v3_partition.py` | Add `motion_prompt` to beat schema |
| `Production/tools/production_server.py` | Add update_motion_prompt handler; rewrite `_handle_add_options_startend` to read motion_prompt; delete lines 13077-13191 and 13330-13363 |
| `Production/tools/storyboard-v2/src/api/endpoints.ts` | Add `update_motion_prompt` mutation endpoint |
| `Production/tools/storyboard-v2/src/components/StoryboardTab.tsx` | Add motion_prompt textarea + state + hydration |
| `Production/tools/build_storyboard.py` | (If legacy still used) mirror the two-field UI |
| `Production/scripts/body_key_contract_baseline.json` | Add `motion_prompt` entry |
| `Production/lib/rule_8_validator.py` | Verify present per LD-722 reopen condition (c) |
| `Production/tools/tests/test_motion_prompt.py` | New test file |
| `Production/tools/storyboard-v2/e2e/motion_prompt.spec.ts` | New e2e test |
| `Production/PIPELINE_BRAIN_v1.md` | Document new field + workflow |

## §6 — Directus Writes Required

- `prod_locked_decisions` POST: `STORYBOARD_TTS_KLING_PROMPT_SEPARATION_IMPL_V1` (lock at completion via `try_post_or_queue`)
- `prod_locked_decisions` PATCH on LD-722: `status=superseded`, `superseded_by_id=<new LD id>`
- `prod_activity_log` POST per phase: `motion_prompt_phase_<N>_complete` with marker string
- `prod_reference_docs` PATCH ref doc id=224: `status=superseded` once IMPL ships

All writes via `try_post_or_queue` per Rule 35. Field names verified against `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`.

## §7 — Error Cases and Handling

| Error case | Handling |
|---|---|
| User submits motion_prompt with §8.1 banned word | Server 400 with explicit `BANNED_MOTION_WORD` code + which word; client toast surfaces |
| `motion_prompt` empty AND `speaker` unknown | Server falls through to `_SPEAKER_NEUTRAL_POSE['_default']` (generic neutral); warns in stderr |
| Race: user edits motion_prompt during in-flight Send for Lipsync | guardOrToast pattern (LD-792) blocks the lipsync click while save is in flight |
| Legacy beat with no motion_prompt field | Hydration treats missing as empty (placeholder shown); next save populates the field |

No silent fallbacks per Rule 19.

## §8 — Verification (6-Layer)

| Layer | Gate | Test |
|---|---|---|
| 1 UI exists | New textarea visible on every beat | Playwright DOM probe `[data-testid=beat-N-motion-prompt]` |
| 2 UI → backend | `pathappPatch('update_motion_prompt', ...)` fires on debounced edit | Network capture in Playwright |
| 3 Server processing | Handler writes `beat.motion_prompt` to state.json | unit test + state-after-PATCH assertion |
| 4 State propagation | `/api/v2/event/<id>/state` returns `motion_prompt` field | curl probe |
| 5 UI re-render | Hydration on bootstrap shows persisted value | Playwright reload-and-assert |
| 6 E2E smoke | Edit motion_prompt → Send for Lipsync → output frame visually matches motion_prompt only (NOT text) | Kim browser smoke + visual diff |

## §9 — Rollback

Per phase:
- **Phase 1**: revert schema change + endpoint stub — no data persisted yet
- **Phase 2**: revert client commit — server still accepts field (no-op for users without UI)
- **Phase 3**: KEEP the new `motion_prompt` read path; restore the deleted auto-synth block as a fallback. NOT a clean rollback — would require careful migration. **Recommendation: don't merge Phase 3 unless Phase 5 tests are green.**
- **Phase 4-6**: cosmetic; rollback by revert

`.deploy_backups/<timestamp>/` snapshot taken automatically via `deploy_storyboard_v59.sh`.

## §10 — Out of Scope (V1)

- BG sidecar / FLUX offline pipeline changes (Kim Call 3)
- Voice profile changes — `beat.speaker` selector is unchanged
- Audio_delay / trim / lipsync flows
- Per-speaker motion-prompt defaults beyond the canonical neutral-pose entries
- Multi-language motion prompts

## §11 — Dependencies

**Hard:**
- LD-677 `Production/lib/rule_8_validator.py` present + tracked in git (verify before Phase 1)
- LD-180 start-end universal default for Event 1 (motion_prompt only matters in start-end mode)

**Soft:**
- LD-697 backend extraction deferred — this work is additive and sharpens the seam extraction will follow
- LD-733 TTS leading-paren strip (shipped 2026-05-20) — interacts with motion_prompt because the leading paren WAS the text-derived motion hint

## §12 — Cursor Cross-Review Prompt (paste verbatim before execution)

```
Review the tech spec at Production/docs/TECH_SPEC_TTS_KLING_PROMPT_SEPARATION_v1.md.
Validate: (1) the 3 Kim judgment calls are coherent and complete;
(2) the 6 phases are dependency-ordered;
(3) the file list in §5 is exhaustive vs the dispatcher refactor scope;
(4) Phase 3's deletion of lines 13077-13191 + 13330-13363 does not break any
test/handler/script not listed. Flag any §8.1 banned-word interactions I missed.
Output: PASS / FAIL_BLOCKING / FAIL_NONBLOCKING per finding.
```

## §13 — Notes for Executing Sessions

- Read `Production/docs/LESSONS_LEARNED_20260514_15_STORYBOARD_SILENT_DROP_CASCADE_V1.md` (ref doc id=223) BEFORE Phase 1 — same silent-coupling bug class
- Read this spec + LD-722 + ref doc 224 fully before any edit
- Per LD-722 §0.5 don't rely on memory — re-read every file referenced
- Tail-end Cursor verifier subagent per LD-722 §0.6

## §14 — Pre-execution Checklist

```
[ ] §0 read fully (Mandatory Operating Mode)
[ ] zero-error-qa skill loaded
[ ] Phase 0 classification: Tier B
[ ] prod_preflight_reviews row written
[ ] LD-722 + ref_doc 224 + lessons doc 223 read
[ ] Production/lib/rule_8_validator.py present + tracked (LD-677)
[ ] grep verified: no non-empty end_frame_prompt across Event_*/production_state.json
[ ] body_key_contract_baseline.json reviewed
[ ] Cursor cross-review run on this spec (§12)
```

## §15 — Honest Gap-Flags

- This spec is **mid-detail**, not the original Opus debate output (which was lost). Before execution, regenerate via `tech-spec` skill against this file as the starting point.
- `_SPEAKER_NEUTRAL_POSE` dict in §3 Call 2 is referenced but not currently in the code — Phase 1 needs to define it (one entry per speaker: Tessa, Chipper, Luna, Cedric, Benson, Ember, Bork, Bramble, Grizzle).
- Phase 3 deletion of lines 13077-13191 / 13330-13363 should be done against the LATEST `production_server.py` HEAD at execution time, not the 2026-05-16 snapshot — line numbers will drift.
- The `motion_prompt` length cap (likely 500-1000 chars to match end_frame_prompt) is NOT specified in this spec — pick a reasonable bound at Phase 1 + document in `BEAT_PARENTHETICAL_CONVENTION_v1.md`.

## §16 — Reference Index

- LD-722: `STORYBOARD_TTS_KLING_PROMPT_SEPARATION_DEFERRED_V1`
- LD-728: `BEAT_PARENTHETICAL_CONVENTION_V1`
- LD-733: `TTS_STRIP_LEADING_PARENTHETICAL_V3` (shipped 2026-05-20)
- LD-180: start-end universal default
- Ref doc 223: Lessons learned 2026-05-14/15 storyboard silent drop cascade
- Ref doc 224: this spec's parent record
- File: `Production/HANDOFF_BEAT_GENERATOR_TAB_COMPLETE.md`
- File: `Production/PIPELINE_BRAIN_v1.md`
