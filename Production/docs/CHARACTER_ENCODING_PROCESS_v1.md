# Character Encoding Process v1

**Locked 2026-05-14.** This doc is the canonical process for setting up any new MindfulNest character (creature, NPC, narrator) so the production pipeline does not generate unexpected motion, voice contamination, or AI hallucinations. Distilled from the 2026-05-13/14 3+3 Opus debate on the Chipper-jumping recurrence + the meta-headwinds audit + the TTS stage-direction-leak bug.

Governing LDs: **LD-148** (eleven_v3 for all characters) · **LD-307** (motion vocabulary per creature) · **LD-331** (watercolor bbox) · **LD-443** (stage-direction extraction) · **LD-148** + **LD-688** (voice-profile completeness) · **LD-689** (Chipper neutral rewrite) · **LD-690** (TTS strip stage direction)

## Scope

When you encode a new character or revise an existing one, this process applies to:
- Voice profile (ElevenLabs voice_id + settings + emotional register)
- Motion vocabulary (Kling motion prompts per emotional register)
- Stage-direction conventions in beat text
- Pipeline registration (Directus + lockfile + voice cache)
- Verification protocol before locking the character

## Rule 1 — The three text channels MUST be distinct

`beat.text` is the single source for three orthogonal channels. Confusing them is the most common bug class in this pipeline:

| Channel | Format in beat.text | Consumed by | Stripped from | Locked by |
|---|---|---|---|---|
| **Spoken dialogue** | Plain words: `"It says 'stay loose and light'"` | ElevenLabs TTS | nothing (it IS the speech) | Rule 11 source fidelity |
| **Visual motion direction** | `(parenthetical of 3+ chars)`: `"(walks forward, gently)"` | Kling positive prompt via `_motion_override` | TTS payload (via `_clean_text_for_tts`) | LD-443 + LD-690 |
| **Emotional register** | `[bracket tag]`: `[warm]`, `[excited]`, `[whisper]` | ElevenLabs v3 native emotional audio | nothing (v3 reads the tag) | VOICE_ROSTER_LOCKED_v2.md §Emotional Direction |
| **Cue marker** | `[pause]`, `[break]`, `[silence]` | TTS pause via `... ` ellipsis | Kling prompts (not motion direction) | LD-690 |

**Authoring rule:** write spoken dialogue plainly. Bracket emotional state. Parenthesize visual motion. Use `[pause]` for breath/silence. Do not nest. Do not put motion cues in brackets or emotion cues in parens.

## Rule 2 — Motion vocabulary must NEVER contain locomotion or VFX verbs in `neutral`

Per LD-689 (closing the Chipper-jumping recurrence), the neutral register is the FALLBACK for every beat with no parenthetical + no emotion. Therefore neutral vocabulary must describe **idle stance**, NOT action.

**Forbidden in any speaker's neutral string:**
- Locomotion verbs: `hop`, `hops`, `jump`, `bounce`, `walk`, `run`, `flap`, `fly`, `move`, `dance`
- VFX verbs: `sparkle`, `glow`, `shimmer`, `glitter`, `pulse`, `light up`, `radiate`
- Repetition cues that imply movement: `in place`, `up and down`, `back and forth`
- Rule 8.1 banned words (the existing `BANNED_PROMPT_WORDS` set)
- Rule 8.2 motion-locking phrases (`minimal motion`, `static camera`, `head remains facing`, `frozen face`, `pressed`, `sealed`, `clamped`)

**Required structure** (3-4 micro-motion verbs, in-domain anatomy):
```
"<head micro-motion>, <wing/limb micro-adjustment>, <texture/breath ripple>, <blink/gaze cue>"
```

Reference patterns (LD-307-compliant):
- Tessa neutral: `"subtle weight shift, gentle head tilt, shell rise and fall, quiet blink"`
- Chipper neutral (LD-689): `"gentle head micro-tilt, quiet wing adjustments, soft feather ripple, attentive blink"`
- Ember neutral: `"controlled head turn, gentle tail sway, measured weight shift, alert ear swivel"`

**Open Kim-decision items** (do NOT auto-rewrite without consent):
- Benson neutral contains `"small body hops in place"` — same word-shape as Chipper's deleted string. Bunny hops are species-natural; pending Kim direction.

## Rule 3 — Voice profile must be COMPLETE at character lock time

Per LD-688 V1_VOICE_PROFILE_COMPLETENESS_V1. A character is NOT "encoded" until all four artifacts agree:

| # | Artifact | Required content | Verification |
|---|---|---|---|
| 1 | `prod_voice_profiles` Directus row | `character_name`, `elevenlabs_voice_id` (20-char), `stability`, `similarity_boost`, `style`, `speed` (nullable), `model='eleven_v3'`, `notes` (provenance trail) | `directus_search` returns 1 row matching name |
| 2 | `content-lockfiles/voice_profiles.toml` | `[characters.<lower>]` section with all 5 fields populated | TOML parses + `elevenlabs_voice_id != ""` |
| 3 | `_SPEAKER_ALIAS` in `production_server.py:3637` | All legacy aliases mapped to canonical name | grep matches |
| 4 | `SPEAKER_MOTION_PROFILES` in `production_server.py:910` | 4 emotional registers (happy_excited / upset_shocked / sad_disappointed / neutral), Rule 2 compliant | unit test calls `build_motion_prompt(speaker=X, emotion=neutral)` returns sane string |

If ANY of the 4 is missing, the server-side warning at boot fires (`[voice-profiles] WARN: V1-required voice profiles MISSING from Directus`). That warning is **not optional ceremony** — it surfaces the gap on every server start until closed.

## Rule 4 — Pre-lock verification (Kim-eye smoke, P1 from headwinds agent)

**Before locking a new character LD, the verification MUST run against real Kim production data, not synthetic test fixtures.** This is the load-bearing rule that fixes the recurring-bug class C7 (smoke verifies code, not user experience) per the 2026-05-14 headwinds meta-audit.

For each new/revised character, run:

1. **TTS smoke:** Pick a real beat with the character as speaker. POST `/api/beat/regenerate_audio`. Verify:
   - Response `ok: true`, `voice_id` matches the registered profile
   - `audio_duration_s` is sane for the text length (target ~10-15 chars/sec)
   - **Listen to the MP3** — confirm no parenthetical text spoken, no `[pause]` read literally
   - If parentheticals exist in text, verify they were stripped (cleaner log line + duration drop vs pre-fix)

2. **Motion smoke:** Pick a real beat with `emotion=neutral` and no parenthetical. Call `build_motion_prompt` with that beat dict. Verify:
   - Output contains the new neutral vocabulary
   - No banned words (Rule 8.1) — `sanitize_prompt` returns clean
   - No motion-locking phrases (Rule 8.2)

3. **End-to-end smoke** (paid, ~$0.45 + $0.15 lipsync): Click Generate B+C in the storyboard on a real beat. Watch the actual Kling output. Confirm character behavior matches design intent — NOT a synthetic prompt run.

The LD that locks the character must include a `kim_eye_smoke_evidence` field in `details` with the actual beat_id used + the resulting audio/video file paths.

## Rule 5 — Discovery-first protocol (P2 from headwinds agent)

**Before composing any character fix, search for existing authoritative data.** Voice IDs for Luna/Benson/Ember/Bork/Bramble were in `Production/VOICE_ROSTER_LOCKED_v2.md` for 40 days before LD-688 incorrectly framed them as user-pending input. This 30-second discovery search would have prevented the wasted scaffold.

Mandatory pre-fix searches (record results in the Phase 0 declaration line):
- `find . -name "*VOICE*" -o -name "*ROSTER*" -o -name "*CHARACTER*" 2>/dev/null` for voice/character questions
- `directus_search prod_reference_docs` for `doc_title _icontains <topic>`
- `directus_search prod_locked_decisions` for `decision_text _icontains <topic>` (last 60 days)
- `grep -ril "<character_name>" Canon/ Production/docs/`

Output goes in Phase 0 declaration: `Authoritative sources consulted: <list>`. If a source EXISTS and contains an answer, the fix design must use it — not invent a parallel mechanism.

## Rule 6 — AI-prompt hallucination minimization

The end-frame FLUX Kontext prompt path (`_SAFE_NEUTRAL_POSE` at production_server.py:13090) demonstrates the working pattern when no parenthetical is authored:

**Use static posture descriptors, not motion verbs**, when the AI lacks specific direction:
- Good: `"head tilted gently to one side, attentive expression"`
- Bad: `"small hops in place, wing adjustments, warm head tilts, bright eye sparkle"`

Motion verbs invite the model to invent action; posture descriptors anchor it to a stable pose. The same principle applies to the Kling motion-prompt fallback per LD-689.

**Negative-prompt discipline** (per Rule 8.2, validated again in 2026-05-14 Counter B): NEVER add motion-locking phrases (`"standing still"`, `"frozen"`, `"no movement"`) to lipsync-targeted clips. Doing so starves ByteDance LatentSync's mouth-region micro-motion signal. Use POSTURE descriptors in the positive prompt instead.

## Rule 7 — TTS stage-direction stripping is MANDATORY

Per LD-690. Every ElevenLabs TTS request MUST go through `_clean_text_for_tts()`. NEVER send `beat.text` verbatim.

The cleaner contract:
- **Strip:** `(parenthetical)` of 3+ chars, `[pause]`/`[break]`/`[silence]` cue brackets
- **Replace:** cue brackets with `" ... "` (v3 reads ellipsis as natural pause; safer than `<break/>` SSML)
- **Preserve:** v3 native audio tags via `TTS_V3_NATIVE_TAGS` allowlist (`[warm]`, `[gentle]`, `[whisper]`, `[excited]`, etc.)
- **Preserve:** spoken dialogue byte-for-byte (Rule 11 source fidelity)

Any new TTS submission site in the codebase MUST call the cleaner. Direct ElevenLabs calls bypassing the cleaner are a Rule 19 violation.

## Rule 8 — Lock the character with an invariant, not just an intent

Per the headwinds agent's P4 recommendation. When locking a character LD, the `notes` field must include an INVARIANT clause:

> **Invariant:** all V1 voice profiles in `prod_voice_profiles` AND `content-lockfiles/voice_profiles.toml`. Test: server load. Fails when row count < 8.

This converts the LD from "we did the thing" (documentation) to "the thing remains true" (verification). A weekly cron can then audit the invariant; a failure is a recurrence signal that fires automatically rather than waiting for Kim to notice.

## Process flowchart (when adding/revising a character)

```
0. Discovery-first protocol (Rule 5) — search for existing data BEFORE designing
   ↓
1. If voice_id exists in any authoritative source: use it
   If not: Kim picks via ElevenLabs voice library, documents in VOICE_ROSTER doc
   ↓
2. Author motion vocabulary (Rule 2) — 4 emotional registers + neutral idle
   Run Rule 8.1 banned-word check + Rule 8.2 motion-lock check (scripted)
   ↓
3. Register character in all 4 artifacts (Rule 3):
   prod_voice_profiles row → content-lockfiles/voice_profiles.toml → _SPEAKER_ALIAS → SPEAKER_MOTION_PROFILES
   ↓
4. Server restart + DS-22 fresh-import verification
   ↓
5. Kim-eye smoke (Rule 4): real beat + Regen Audio + listen + Animate + watch
   ↓
6. Lock LD with invariant clause (Rule 8) + Kim-eye-smoke evidence
   ↓
7. Sync code change to tooling repo (LD-505 durability)
```

## What this process FORECLOSES (deliberately)

- **Synthesizing voice IDs as fallbacks** (Rule 5) — never substitute Tessa's voice for an unregistered character. Surface the gap loudly, ask Kim, find the locked roster.
- **Authoring vague motion strings that AI will "fill in"** (Rule 6) — every neutral string is a fixed POSTURE, not a motion seed.
- **Sending raw beat.text to ElevenLabs** (Rule 7) — the cleaner is mandatory, not a polish step.
- **Locking LDs without real-data verification** (Rule 4) — synthetic smoke is insufficient; the discipline is "use Kim's actual production state."
- **Adding more discipline rules and memory files** (per headwinds agent's explicit recommendation) — discipline density is past marginal return. This doc is content discipline (character-domain rules), not process meta-discipline.

## Open follow-ups (not blocking)

- **Benson neutral** (`"small body hops in place"`) — Kim decision pending: rewrite to match Chipper-stillness pattern, or preserve as species-natural bunny vocabulary
- **Luna neutral** — Counter B flagged `"alert blinking"` could trigger Kling rapid-flicker; no observed regression yet; leave unless Kim flags
- **Lady Willow + Mountain King** (Arc 2) — voice IDs locked in VOICE_ROSTER_LOCKED_v2.md but NOT registered in Directus; defer until Arc 2 production
- **Pattern-recognition gate at LD lock time** (headwinds P3) — wire into `lock_decision.py` so duplicate-fix LDs surface; ~2 hours infra work
- **Storyboard tool extraction** (headwinds P5) — defer until V1 ships; production_server.py is now 18,760 lines and the single biggest source of recurring bugs

## Provenance

- Authored 2026-05-14 by Claude Opus 4.7 in autonomous mode
- Inputs: 3+3 Opus debate Chipper jumping (Advocates A/B/C + Counters A/B/C, full memos in agent task results 2026-05-13/14), TTS bug investigation, headwinds meta-audit
- Locks: LD-689, LD-690 today; references LD-148, LD-307, LD-331, LD-443, LD-688
- This doc itself will be registered as `prod_reference_docs` for cross-session discoverability
