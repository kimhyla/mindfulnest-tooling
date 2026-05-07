# HANDOFF — Per-Creature Motion Vocabulary Implementation

**Handoff created:** 2026-04-19
**Prior session (design):** 2026-04-19 (this handoff captures every locked decision from that session)
**Execution mode:** Autonomous, Claude Code terminal CLI ONLY
**Authorization:** All permissions, approvals, and write-authority pre-granted by Kim. Do not ask for approval at any point.

---

## 0. SESSION ENTRY CHECK — READ FIRST, DO NOT SKIP

You are a fresh Claude session with no memory of the prior design conversation. This handoff is self-contained. Read it top to bottom before any tool use.

**You MUST be running in Claude Code terminal CLI** (`claude` in Terminal.app / iTerm). Per CLAUDE.md Rule 19 (Hardened Session Protocol) this is governed-file work — `production_server.py` is production-pipeline infrastructure that affects every downstream animation, and Phase 0 pre-flight is mandatory. Claude Desktop silently no-ops the PreToolUse hooks that protect this kind of edit. If you are running in Desktop, STOP and tell Kim to switch to terminal CLI before continuing.

**Autonomy rules:**
- All file writes pre-authorized. No Kim-confirmation gate applies — Rule 3 gate is .docx-only, and this session edits `.py` + writes new `.md`/`.py` test files + Directus records.
- No shortcuts. Any temptation to defer/skip/MVP is forbidden per CLAUDE.md Rule 19. `no-shortcuts` skill enforces.
- **At any point where a human decision would normally be required**, spawn **5 advocate agents + 5 counter-agents** (in parallel via Agent tool, `general-purpose` subagent_type, single message with 10 tool calls). Seek convergence. If no convergence after round 1, spawn another 5+5. Keep going until convergence emerges. Log every round to `prod_activity_log` with round number, votes, and final convergence. **Never stop on ambiguity — spawn more agents.**
- **Do not stop until every STOP condition in §11 is satisfied.**

---

## 1. MISSION

Implement per-creature, emotion-conditioned motion vocabulary in `Production/tools/production_server.py::build_motion_prompt`. Design was locked by Kim in the prior session. This session writes the code, adds tests, registers the locked decisions in Directus, resolves the dead-dict question, and closes out.

**Files you will touch:**
- `Production/tools/production_server.py` — primary edit (replace `build_motion_prompt`, add `SPEAKER_MOTION_PROFILES`, fix BIRD_SPEAKERS canonicalization bug)
- `Production/tools/generate_animation_options.py` — dead-dict decision (delete vs legacy-header vs migrate — debate)
- `Production/tools/tests/test_motion_prompt.py` — new unit test file (create if tests dir exists; if not, create `Production/tools/tests/` and add `__init__.py`)
- Directus: `prod_locked_decisions` (3 rows), `prod_activity_log` (≥5 rows), `prod_preflight_reviews` (1 row written BEFORE Phase 1)
- `Production/HANDOFF_20260419_motion_vocabulary_implementation_OUTCOME.md` — session-close handoff

---

## 2. REQUIRED SKILLS (load in order at session start)

1. **dashboard-gate** — BLOCKING. Run the 7-query session-start protocol before any production work. Confirms Directus auth, reads locked decisions, state, activity log, blockers, session decisions, voice profiles.
2. **zero-error-qa** — Phase 0 MANDATORY. This task classifies as **ARCHITECTURAL** (the motion prompt pipeline affects every future animation and is referenced by LD-162, LD-180, §8 rules). Per LD-124 PREFLIGHT_PROTOCOL_STEP_0 + CLAUDE.md Rule 19, you MUST spawn 4+4 advocate+counter-agents minimum AND write a `prod_preflight_reviews` row BEFORE Phase 1 begins. **Kim has specified 5+5 for any decision point — use 5+5, not 4+4, to satisfy both.**
3. **no-shortcuts** — every production artifact flawless. No `TODO`, no placeholder, no "we'll add tests later."
4. **verified-edit** — for the surgical `production_server.py` edit.
5. **document-handling-rules** — governs all file edits.

Governance files to read at start:
- `CLAUDE.md` §8.1, §8.2, §8.3, §8.4 (full read — motion governance)
- `CLAUDE.md` Rule 16 (Pre-Flight Check) + Rule 19 (No Shortcuts) + Rule 20 (Automatic Decision Capture)
- `Production/PIPELINE_BRAIN_v1.md` — read the motion/video sections
- `Production/governance/video-producer_governance.md`

---

## 3. THE LOCKED DESIGN (do not revisit)

These decisions were finalized with Kim on 2026-04-19. Do not spawn debate agents to reconsider them — they are locked. Agent debates are only for (a) the dead-dict question in §7, (b) genuinely novel ambiguity that arises during implementation.

### 3.1 Approach

**Option 1 + Option 3 combined** from the design session:
- Option 1: Per-speaker motion vocabulary dict, emotion-keyed, with 4 emotional registers.
- Option 3: Swap the §8.1-required tail from `"Silent subtle idle movement only"` (motion-locking) to `"no dialogue in video"` (non-motion-locking) on lipsync-targeted beats. Keep the motion-locking tail for sprites.

### 3.2 Four emotional registers

- `happy/excited`
- `upset/outraged/shocked`
- `sad/disappointed`
- `neutral` — reserved for sprite-pipeline idle loops (non-lipsync-targeted)

### 3.3 Per-creature vocabulary (LOCKED — copy into code verbatim)

Single-string format, comma-separated motion-direction verbs. Each entry is plugged directly into `build_motion_prompt` as the `{action}` in the template `f"Cartoon {speaker} character, {action}. {constraint} {tail}"`.

| Creature | happy/excited | upset/outraged/shocked | sad/disappointed | neutral (sprite) |
|---|---|---|---|---|
| **Tessa** (turtle) | `head lift, shell expansion, bright weight shift forward, warmed blink` | `quick head retraction, shell pulling in, widened eye reaction, startled body recoil` | `shell-breathing, gentle head dip, soft weight settling, downward glance` | `subtle weight shift, gentle head tilt, shell rise and fall, quiet blink` |
| **Luna** (owl) | `enthusiastic wing flutter, bright eye widening, quick head bob, scholarly feather ruffle` | `sharp head swivel, feather bristle, wings unfurling slightly, rapid blink` | `soft wing settle, gentle feather droop, quiet head dip, slow blink` | `curious owl head swivels, wing adjustments, feather ripple, alert blinking` |
| **Benson** (bunny) | `ears lifting, small forward hop, chest lift, bright blink` | `ears flattening, body tightening, rapid nose wrinkle, startled weight recoil` | `ear droop, gentle body huddle, soft nose wrinkle, downward head tilt` | `ear flicks, nose twitches, small body hops in place, curious head micro-tilts` |
| **Ember** (fox) | `relaxed paw settle, gentle tail flow, softened head tilt, warm body expansion` | `tail lash, ears sweeping back, guarded paw shift, sharp head turn` | `careful paw movement, guarded head turn, small tail flick, subtle shoulder breathing` | `controlled head turn, gentle tail sway, measured weight shift, alert ear swivel` |
| **Bork** (firefly) | `gentle hover, relaxed wing-beats, warm shimmer, soft body expansion` | `formal hover jitter, wing-beat spike, body straightening upward, sharp turn` | `subtle hover wobble, gentle wing-flutter dip, small body droop, dim shimmer` | `small formal hover adjustments, crisp wing-beats, tiny body shifts, deliberate turns` |
| **Bramble** (bear) | `wide-based weight settling, strong shoulder rise, powerful nod, warm body presence` | `big shoulder rise, head pull back, heavy weight recoil, paw raise` | `heavy weight shift, slow paw placement, small head sway, subdued shoulder breathing` | `grounded weight settling, paw adjustments, wide head turns, deep shoulder rise and fall` |
| **Chipper** (bird) | `energetic body bounce, quick wing flutter, enthusiastic head nod, bright feather ruffle` | `quick wing half-lift, feather bristle, sharp head turn, rapid blink` | `soft feather settle, gentle wing-fold, head tilt, quiet blinking` | `small hops in place, wing adjustments, warm head tilts, bright eye sparkle` |

Kim confirmed Tessa gets shock vocabulary even though Arc 1 does not exercise it — Arc 2 will.

### 3.4 Multi-register beats

If a narrative beat swings across multiple registers mid-clip (starts shocked → lands sad), pick the **dominant** register for the beat. Kling renders one emotional state per clip; don't try to compound. Kim confirmed this.

### 3.5 Schema additions (optional fields)

Add two optional fields to `beat`:
- `beat.emotion: str` — one of `"happy_excited" | "upset_shocked" | "sad_disappointed" | "neutral"`. Default `"neutral"` if unset.
- `beat.lipsync_targeted: bool` — default `True` for narrative event beats, `False` for sprite beats. Default behavior if unset: `True` (Event_1 default per LD-180).

Use snake-case keys matching the registers above. Map in the dict with the same snake-case keys.

### 3.6 Tail constants

```python
LIPSYNC_SAFE_TAIL = "no dialogue in video"              # §8.1-allowed, non-motion-locking
SPRITE_IDLE_TAIL  = "Silent subtle idle movement only"  # §8.1-allowed, motion-locking
```

Apply `LIPSYNC_SAFE_TAIL` when `beat.lipsync_targeted` is True. Apply `SPRITE_IDLE_TAIL` otherwise.

### 3.7 BIRD_SPEAKERS canonicalization fix

Current bug: `BIRD_SPEAKERS = {"Guide Bird", "Luna"}`. A beat with `speaker="Chipper"` (canonical per 2026-04-17 lore update, LD-183) fails the BIRD check and gets the turtle constraint `"Mouth closed, no speech."` instead of `"Beak closed, no speech."`.

Fix: canonicalize the speaker via `_SPEAKER_ALIAS` (at production_server.py:2090) BEFORE the BIRD_SPEAKERS check. Legacy speakers (`"Guide Bird"`, `"Pip"`) must continue to route correctly — tests below cover this.

Also add `"Chipper"` to `BIRD_SPEAKERS` explicitly (belt-and-suspenders — alias canonicalization is the primary fix, but the set should also contain the canonical name).

---

## 4. CODE CHANGES — `Production/tools/production_server.py`

### 4.1 Near the existing `SECTION_ACTIONS` dict (approx line 485)

Insert above `def build_motion_prompt`:

```python
# ---------------------------------------------------------------------------
# Per-creature motion vocabulary (LD MOTION_VOCABULARY_PER_CREATURE_V1, 2026-04-19)
#
# Keyed by canonical speaker name (post-_SPEAKER_ALIAS). Each creature has
# four emotional registers. `neutral` is reserved for sprite-pipeline idle
# loops (non-lipsync-targeted); the other three are for narrative event beats.
#
# Every vocabulary string is §8.1-§8.4 compliant:
#   - No BANNED_PROMPT_WORDS.
#   - No §8.2 forbidden phrases (minimal motion, static camera, frozen face,
#     head remains facing forward, face centered, direct forward gaze, eyes
#     meet camera, pressed, sealed, tight, clamped, etc.).
#   - Each §8.1 anti-lipsync term appears AT MOST ONCE in the assembled
#     prompt — it lives in the constraint line only, never in the vocabulary.
# ---------------------------------------------------------------------------
SPEAKER_MOTION_PROFILES: dict[str, dict[str, str]] = {
    "Tessa": {
        "happy_excited":    "head lift, shell expansion, bright weight shift forward, warmed blink",
        "upset_shocked":    "quick head retraction, shell pulling in, widened eye reaction, startled body recoil",
        "sad_disappointed": "shell-breathing, gentle head dip, soft weight settling, downward glance",
        "neutral":          "subtle weight shift, gentle head tilt, shell rise and fall, quiet blink",
    },
    "Luna": {
        "happy_excited":    "enthusiastic wing flutter, bright eye widening, quick head bob, scholarly feather ruffle",
        "upset_shocked":    "sharp head swivel, feather bristle, wings unfurling slightly, rapid blink",
        "sad_disappointed": "soft wing settle, gentle feather droop, quiet head dip, slow blink",
        "neutral":          "curious owl head swivels, wing adjustments, feather ripple, alert blinking",
    },
    "Benson": {
        "happy_excited":    "ears lifting, small forward hop, chest lift, bright blink",
        "upset_shocked":    "ears flattening, body tightening, rapid nose wrinkle, startled weight recoil",
        "sad_disappointed": "ear droop, gentle body huddle, soft nose wrinkle, downward head tilt",
        "neutral":          "ear flicks, nose twitches, small body hops in place, curious head micro-tilts",
    },
    "Ember": {
        "happy_excited":    "relaxed paw settle, gentle tail flow, softened head tilt, warm body expansion",
        "upset_shocked":    "tail lash, ears sweeping back, guarded paw shift, sharp head turn",
        "sad_disappointed": "careful paw movement, guarded head turn, small tail flick, subtle shoulder breathing",
        "neutral":          "controlled head turn, gentle tail sway, measured weight shift, alert ear swivel",
    },
    "Bork": {
        "happy_excited":    "gentle hover, relaxed wing-beats, warm shimmer, soft body expansion",
        "upset_shocked":    "formal hover jitter, wing-beat spike, body straightening upward, sharp turn",
        "sad_disappointed": "subtle hover wobble, gentle wing-flutter dip, small body droop, dim shimmer",
        "neutral":          "small formal hover adjustments, crisp wing-beats, tiny body shifts, deliberate turns",
    },
    "Bramble": {
        "happy_excited":    "wide-based weight settling, strong shoulder rise, powerful nod, warm body presence",
        "upset_shocked":    "big shoulder rise, head pull back, heavy weight recoil, paw raise",
        "sad_disappointed": "heavy weight shift, slow paw placement, small head sway, subdued shoulder breathing",
        "neutral":          "grounded weight settling, paw adjustments, wide head turns, deep shoulder rise and fall",
    },
    "Chipper": {
        "happy_excited":    "energetic body bounce, quick wing flutter, enthusiastic head nod, bright feather ruffle",
        "upset_shocked":    "quick wing half-lift, feather bristle, sharp head turn, rapid blink",
        "sad_disappointed": "soft feather settle, gentle wing-fold, head tilt, quiet blinking",
        "neutral":          "small hops in place, wing adjustments, warm head tilts, bright eye sparkle",
    },
}

# §8.1-allowed tails (LD MOTION_TAIL_LIPSYNC_SAFE_V1, 2026-04-19)
LIPSYNC_SAFE_TAIL = "no dialogue in video"              # non-motion-locking; default for narrative event beats
SPRITE_IDLE_TAIL  = "Silent subtle idle movement only"  # motion-locking; default for sprite-pipeline loops

VALID_EMOTIONS = {"happy_excited", "upset_shocked", "sad_disappointed", "neutral"}
```

### 4.2 Extend BIRD_SPEAKERS (approx line 92)

```python
# Add "Chipper" (canonical, 2026-04-17 lore update LD-183).
# Legacy speakers ("Guide Bird", "Pip") route via _SPEAKER_ALIAS at build time.
BIRD_SPEAKERS = {"Guide Bird", "Luna", "Chipper"}
```

### 4.3 Replace `build_motion_prompt` (approx line 495-506)

```python
def _canonicalize_speaker(raw: str) -> str:
    """Route legacy speaker strings to their canonical name via _SPEAKER_ALIAS.
    Safe for empty strings and unknown speakers (returns input unchanged)."""
    if not raw:
        return ""
    return _SPEAKER_ALIAS.get(raw.lower().strip(), raw)


def build_motion_prompt(beat: dict) -> str:
    """Build a §8.1-§8.4 compliant motion prompt for Kling v3 Pro.

    Resolves speaker to canonical name, looks up per-creature motion
    vocabulary for the beat's emotional register, falls back to
    SECTION_ACTIONS for unknown speakers, and applies the appropriate
    tail based on whether the beat is lipsync-targeted.
    """
    raw_speaker = beat.get("speaker", "") or ""
    speaker = _canonicalize_speaker(raw_speaker)
    section = beat.get("section", "") or ""

    # Emotion — default neutral, validate against known set.
    emotion = beat.get("emotion", "neutral") or "neutral"
    if emotion not in VALID_EMOTIONS:
        print(f"[WARN] unknown emotion {emotion!r} for speaker {speaker!r}; "
              f"falling back to 'neutral'")
        emotion = "neutral"

    # Lipsync-targeted — default True (Event_1 default per LD-180).
    lipsync_targeted = beat.get("lipsync_targeted", True)
    if lipsync_targeted is None:
        lipsync_targeted = True

    # Action vocabulary: per-speaker profile first, then section fallback.
    profile = SPEAKER_MOTION_PROFILES.get(speaker)
    if profile:
        action = profile.get(emotion) or profile["neutral"]
    else:
        action = SECTION_ACTIONS.get(section, DEFAULT_ACTION)

    # Species-appropriate mouth/beak constraint (§8.1 required).
    if speaker in BIRD_SPEAKERS:
        constraint = "Beak closed, no speech, no lip movement."
    else:
        constraint = "Mouth closed, no speech."

    # Tail: non-motion-locking for lipsync-targeted, motion-locking for sprites.
    tail = LIPSYNC_SAFE_TAIL if lipsync_targeted else SPRITE_IDLE_TAIL

    # Use the canonical speaker name in the prompt (so Kling sees the
    # current character name rather than a legacy alias).
    prompt_speaker = speaker if speaker else raw_speaker
    return f"Cartoon {prompt_speaker} character, {action}. {constraint} {tail}"
```

### 4.4 Touch points to verify after edit

- `sanitize_prompt` (line 509) — no change needed; it remains belt-and-suspenders. Confirm that the assembled vocabulary does NOT contain any `BANNED_PROMPT_WORDS` (tests enforce this).
- Any callers of `build_motion_prompt` — `grep` for usages in `Production/tools/`. Confirm they pass a `beat` dict; if any caller passes only `speaker` + `section` as separate args, the signature did not change so this is fine — but verify.
- `_SPEAKER_ALIAS` at line 2090 — do NOT modify. `_canonicalize_speaker` consumes it.

---

## 5. TESTS — `Production/tools/tests/test_motion_prompt.py`

Create this file. If `Production/tools/tests/` doesn't exist, create it with `__init__.py`. If there's an existing test convention (pytest vs unittest), discover and match it — grep for existing `test_*.py` in the repo. If none exist, use `pytest` (standard library `unittest` is also acceptable).

**Required test coverage:**

1. **Tessa happy/excited, lipsync-targeted** — assert prompt contains `"head lift"` and `"Mouth closed, no speech."` and ends with `"no dialogue in video"`.
2. **Chipper (canonical) neutral, lipsync-targeted=False** — assert prompt contains `"Beak closed, no speech, no lip movement."` and ends with `"Silent subtle idle movement only"`. Proves the alias-canonicalization fix + sprite tail path.
3. **Legacy speaker `"Guide Bird"`** — assert routed to BIRD constraint (via _SPEAKER_ALIAS) and prompt contains `"Cartoon Chipper character"` (canonical name surfaces, not legacy). No regression.
4. **Legacy speaker `"Pip"`** — same as #3.
5. **Unknown speaker + known section (`"Discovery"`)** — falls back to `SECTION_ACTIONS["Discovery"]`.
6. **Unknown speaker + unknown section** — falls back to `DEFAULT_ACTION`.
7. **Invalid emotion string** — falls back to `"neutral"`, logs warning.
8. **Missing `lipsync_targeted` field** — defaults True, non-motion-locking tail applied.
9. **`lipsync_targeted=False`, emotion unset** — defaults neutral register, motion-locking tail applied (sprite path).
10. **Banned-word scan across ALL 28 creature×register combinations** — iterate through `SPEAKER_MOTION_PROFILES`, assert none of `BANNED_PROMPT_WORDS` appears in any vocabulary string.
11. **§8.2 forbidden-phrase scan across ALL 28 combinations** — assert none of `{"minimal motion", "static camera", "head remains facing forward", "no head movement", "frozen face", "face centered", "direct forward gaze", "eyes meet camera", "back toward camera", "eyes tracking", "pressed", "sealed", "tight", "clamped"}` appears.
12. **§8.1 required term count** — for each generated prompt, `"no speech"` appears at most once (in constraint; not leaked into vocabulary). Same for `"beak closed"`, `"mouth closed"`.

All tests must pass before Phase 3 (Directus registration).

---

## 6. DIRECTUS OPERATIONS

Use Python `urllib.request` via the existing credential loader — never curl. Read credentials from `Production/API_KEYS_MASTER.md` or `lib/credentials.py` helper (discover — existing patterns in `production_server.py` at line 2117-2124 show the idiom).

### 6.1 Preflight review — write BEFORE Phase 1

Collection: `prod_preflight_reviews`

One row:
- `task_key`: `MOTION_VOCABULARY_V1_IMPLEMENTATION_20260419`
- `task_category`: `ARCHITECTURAL`
- `advocate_count`: 5
- `counter_count`: 5
- `convergence_round`: (fill in at end of Phase 0 debate)
- `outcome`: `proceed` (or `blocked` if any counter-agent surfaces a §8 violation; this should not happen — if it does, resolve with another 5+5 round)
- `source_documents`: `["CLAUDE.md §8.1-§8.4", "Production/HANDOFF_20260419_motion_vocabulary_implementation.md"]`
- `date_locked`: now
- `status`: `completed` (after Phase 0 closes)

Per LD-124: Phase 0 MUST complete before Phase 1. The `weekly_preflight_audit.py` cron will flag this row as evidence Phase 0 ran.

### 6.2 Locked decisions — register after code lands, before session close

Collection: `prod_locked_decisions`

Three rows:

**Row 1:**
- `decision_key`: `MOTION_VOCABULARY_PER_CREATURE_V1`
- `decision_name`: `Per-creature emotion-conditioned motion vocabulary`
- `decision_text`: `build_motion_prompt in production_server.py now consumes SPEAKER_MOTION_PROFILES, a dict keyed by canonical speaker name with four emotional registers (happy_excited, upset_shocked, sad_disappointed, neutral). Neutral is reserved for sprite-pipeline idle loops. Each vocabulary string is §8.1-§8.4 compliant. Legacy generic SECTION_ACTIONS remains as fallback for unknown speakers.`
- `source_document`: `Production/tools/production_server.py`
- `task_category`: `video-production`
- `severity`: `MEDIUM`
- `date_locked`: 2026-04-19
- `status`: `active`

**Row 2:**
- `decision_key`: `MOTION_TAIL_LIPSYNC_SAFE_V1`
- `decision_name`: `Non-motion-locking tail for lipsync-targeted beats`
- `decision_text`: `Lipsync-targeted beats (beat.lipsync_targeted=True, default for Event_1 per LD-180) now use "no dialogue in video" as the §8.1-required tail. Sprite-pipeline beats (lipsync_targeted=False) retain the motion-locking "Silent subtle idle movement only" tail. Both are §8.1-allowed; the switch removes the "only" motion-lock for narrative content while preserving idle-loop stability for sprites.`
- `source_document`: `Production/tools/production_server.py`
- `task_category`: `video-production`
- `severity`: `MEDIUM`
- `date_locked`: 2026-04-19
- `status`: `active`

**Row 3:**
- `decision_key`: `BIRD_SPEAKERS_CANONICALIZATION_FIX_V1`
- `decision_name`: `build_motion_prompt canonicalizes speaker before BIRD_SPEAKERS check`
- `decision_text`: `Fixed a silent bug where beats authored with speaker="Chipper" (canonical per LD-183, 2026-04-17) received the turtle constraint instead of the bird constraint because BIRD_SPEAKERS did raw string matching and "Chipper" was not in the set. build_motion_prompt now routes speaker through _SPEAKER_ALIAS before the BIRD_SPEAKERS check. Chipper also added to BIRD_SPEAKERS explicitly as belt-and-suspenders. Legacy speakers (Guide Bird, Pip) continue to route correctly via _SPEAKER_ALIAS.`
- `source_document`: `Production/tools/production_server.py`
- `task_category`: `video-production`
- `severity`: `LOW`
- `date_locked`: 2026-04-19
- `status`: `active`

On write failure: retry once. If the second attempt fails, append to `pending_directus_writes.json` per CLAUDE.md Rule 20 error handling. Never skip silently.

On duplicate `decision_key`: PATCH instead of POST.

### 6.3 Activity log — write throughout

Collection: `prod_activity_log`

At minimum 5 rows, one per phase:
- Phase 0 preflight completed (cite the `prod_preflight_reviews` id)
- Phase 1 code write completed (cite file path + commit-like summary)
- Phase 2 tests written + all passing (cite test count)
- Phase 3 Directus LDs registered (cite all 3 decision_keys)
- Phase 4 dead-dict decision resolved (cite outcome of 5+5 debate)
- Phase 5 session close (cite OUTCOME handoff filename)

Each row: `component`, `action`, `status`, `notes`, `references` (array of related Directus ids). Discover field names by reading an existing row.

---

## 7. DEAD-DICT DECISION — `generate_animation_options.py`

The `MOTION_PROMPTS` dict at `generate_animation_options.py:79-172` is NOT imported by `production_server.py`. Verified in prior session: the only reference is the CLI tool's own line 729. It is dead code for the live pipeline.

**Spawn 5 advocate + 5 counter-agents to decide between three options:**

- **(A) Delete.** Remove `MOTION_PROMPTS` dict and the CLI tool's use of it. Rationale: no-shortcuts / zero-error says dead code shouldn't live in the tree. Risk: the CLI tool (`python3 generate_animation_options.py`) is documented in `HANDOFF_20260414_animation_review.md` — confirm it's still operationally used (grep handoffs, activity log) before deletion.

- **(B) Add LEGACY header.** Prepend a large `# LEGACY — not imported by production_server.py` comment block to the dict and to the CLI tool's entrypoint. Rationale: Kim's prior-session direction was "Mention if you end up touching it so we can decide whether to delete it" — cautious, preserves optionality. Risk: dead code lingers.

- **(C) Migrate.** Refactor the CLI tool to import `SPEAKER_MOTION_PROFILES` from `production_server.py` (requires extracting it to a shared module like `Production/tools/motion_profiles.py` since `production_server.py` is a server, not a library). Rationale: one source of truth for motion vocabulary. Risk: scope creep — a new shared module is a bigger change than this task requires.

**Agent brief (both sides):** Each agent gets the three-option summary, the three rationales/risks above, CLAUDE.md Rule 19 (no-shortcuts) text, and the instruction "argue for ONE of A/B/C and refute the other two. Cite concrete evidence (grep results, handoff references, activity log) — no hand-waving."

**Convergence rule:** Tally votes. If ≥7 of 10 converge on one option, execute it. If split 5-5 or 4-3-3, spawn another 5+5 round with the first round's arguments as context. Keep going. Do not stop. Do not default to Kim's direction — she explicitly handed this to the 5+5 debate.

Execute the chosen option. Log the full debate (votes, arguments, final convergence) to `prod_activity_log` with component=`generate_animation_options.py` and references to any preflight row.

---

## 8. SANITY RUNS (Phase 2.5 — between tests and Directus)

After code + tests land, run these sanity checks:

1. **Event_1 representative sample.** Load `Production/Event_1/storyboard_lines_v22.json` (or latest version — discover). For each beat, call `build_motion_prompt(beat)` and print the generated prompt. Manually (via agent review — spawn 1 agent to read the output) verify:
   - Every prompt passes `sanitize_prompt` without the VOCABULARY being stripped (only the constraint line can have strip-able words like "speech" / "lip movement" — this is expected and preserved as belt-and-suspenders).
   - No §8.2 forbidden phrase appears in any output.
   - Each creature's four registers produce visibly distinct prompts.

2. **Sprite smoke test.** Construct a fake sprite beat: `{"speaker": "Tessa", "emotion": "neutral", "lipsync_targeted": False}`. Confirm tail is `"Silent subtle idle movement only"`. Construct a fake narrative beat: `{"speaker": "Tessa", "emotion": "happy_excited", "lipsync_targeted": True}`. Confirm tail is `"no dialogue in video"`.

3. **Chipper regression test.** Construct `{"speaker": "Chipper", "emotion": "happy_excited", "lipsync_targeted": True}`. Confirm constraint is `"Beak closed, no speech, no lip movement."` (not `"Mouth closed, no speech."`). This is the pre-existing bug being fixed.

Log sanity-run output to `prod_activity_log` (component=`build_motion_prompt`, action=`sanity-run`).

---

## 9. REFERENCE DOC REGISTRY (`prod_reference_docs`)

`production_server.py` is production code, not a reference document. **Do NOT register it** in `prod_reference_docs`.

This handoff itself (`HANDOFF_20260419_motion_vocabulary_implementation.md`) is an operational artifact with a finite lifespan — register it with `status=active` at session start, flip to `status=archived` at session close. Use existing handoff-registration pattern if one exists (grep `prod_reference_docs` for `HANDOFF_` entries). If no pattern, skip registration for handoffs — they're transient.

Run `Production/tools/sync_reference_docs.py` at session close per CLAUDE.md Rule 15. If it flags drift unrelated to this session, create a blocker row in `app_blockers` with `severity=LOW` and `owner=Kim`.

---

## 10. SESSION-CLOSE HANDOFF

Write `Production/HANDOFF_20260419_motion_vocabulary_implementation_OUTCOME.md`. Contents:

- **Summary** — one paragraph: what shipped, what was decided, what tests pass.
- **Files changed** — list with line counts.
- **Directus writes** — list every id written (preflight, LDs, activity log).
- **Dead-dict resolution** — which of A/B/C won, vote counts, final convergence round.
- **Sanity run results** — summary of the §8.2 scan and distinctness check.
- **Blockers opened** — none expected; if any, list with ids.
- **What the next session needs to know** — anything a future Claude should be aware of when regenerating Event_1 animations against the new vocabulary.
- **Reference docs registry changes** — per CLAUDE.md Rule 15.

---

## 11. STOP CONDITIONS (all must be satisfied)

Do not close the session until ALL of the following are true:

- [ ] `prod_preflight_reviews` row exists with `outcome=proceed` or `completed`
- [ ] `production_server.py` edits live on disk; `build_motion_prompt` replaced; `SPEAKER_MOTION_PROFILES` present; `BIRD_SPEAKERS` includes `Chipper`; `_canonicalize_speaker` added
- [ ] `Production/tools/tests/test_motion_prompt.py` exists with all 12 test cases from §5
- [ ] All tests pass (run them — do not assume)
- [ ] 3 rows in `prod_locked_decisions` (`MOTION_VOCABULARY_PER_CREATURE_V1`, `MOTION_TAIL_LIPSYNC_SAFE_V1`, `BIRD_SPEAKERS_CANONICALIZATION_FIX_V1`)
- [ ] ≥5 rows in `prod_activity_log`
- [ ] Dead-dict decision made via 5+5 debate; outcome executed; debate logged
- [ ] Sanity runs clean (no §8.2 violations in any Event_1 beat output)
- [ ] `sync_reference_docs.py` clean
- [ ] `OUTCOME.md` handoff written
- [ ] No `.docx` was modified (this session has no reason to touch .docx; if any agent proposes editing a .docx, reject)
- [ ] No shortcuts taken; no TODO / FIXME / placeholder left in any file

### Do NOT stop on:
- Transient Directus 5xx → retry with exponential backoff (3 attempts, then append to `pending_directus_writes.json`, continue).
- Transient API errors from any service → same retry pattern.
- Creative ambiguity → spawn another 5+5 agent round, continue.
- Unexpected file state → investigate via Read/Grep, do not revert or delete, continue.
- Test failures → debug the test or the code, fix, re-run, continue. Never skip a failing test.

### DO stop and escalate to Kim via `app_blockers` row if:
- A §8.1-§8.4 violation is detected in the locked vocabulary itself (would indicate a design flaw the prior session missed — severity HIGH).
- `_SPEAKER_ALIAS` structure has changed since this handoff was written in a way that makes `_canonicalize_speaker` unsafe.
- Directus write fails persistently (3x retry + pending_directus_writes.json append both fail).
- A caller of `build_motion_prompt` uses a signature this handoff did not anticipate.

Escalation = write an `app_blockers` row with `severity=HIGH`, `owner=Kim`, full context in `notes`. Then continue with what remains of the task that does not depend on the blocked piece. Do not stop the whole session unless nothing else is possible.

---

## 12. EXECUTION ORDER SUMMARY

1. Load skills (§2).
2. Read governance (§2 — CLAUDE.md §8.1-8.4, Rules 16/19/20; PIPELINE_BRAIN; video-producer governance).
3. `dashboard-gate` 7-query protocol.
4. `zero-error-qa` Phase 0: classify ARCHITECTURAL, spawn 5+5 advocate+counter debate on the full implementation plan. Write `prod_preflight_reviews` row.
5. Phase 1: edit `production_server.py` per §4.
6. Phase 2: write tests per §5. Run them. All green before proceeding.
7. Phase 2.5: sanity runs per §8.
8. Phase 3: register 3 LDs per §6.2. Write ≥5 activity log rows per §6.3.
9. Phase 4: dead-dict 5+5 debate per §7. Execute outcome.
10. Phase 5: session close — `sync_reference_docs.py`, `OUTCOME.md`, final activity log row.
11. Verify all STOP conditions (§11). Close.

---

**End of handoff. Execute.**
