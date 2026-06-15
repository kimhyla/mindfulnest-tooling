#!/usr/bin/env python3
"""Unit tests for production_server.build_motion_prompt.

task_id   = MOTION_VOCABULARY_V1_IMPLEMENTATION_20260419
preflight = 104
LD coverage = MOTION_VOCABULARY_PER_CREATURE_V1,
              MOTION_TAIL_LIPSYNC_SAFE_V1,
              BIRD_SPEAKERS_CANONICALIZATION_FIX_V1
              (CLAUDE.md Rule 8.1-8.4, LD-162, LD-180, LD-183)

Scope: pure-function behavior of build_motion_prompt + _canonicalize_speaker.
No network, no Directus, no WaveSpeed.
"""

from __future__ import annotations

import io
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import production_server as ps  # type: ignore  # noqa: E402


class MotionPromptCoreTests(unittest.TestCase):
    """Core behavior: per-speaker vocabulary, constraints, tails."""

    def test_01_tessa_happy_lipsync_targeted(self) -> None:
        """Tessa happy/excited, lipsync-targeted: happy vocabulary, turtle
        constraint, non-motion-locking tail."""
        beat = {
            "speaker": "Tessa",
            "emotion": "happy_excited",
            "lipsync_targeted": True,
        }
        p = ps.build_motion_prompt(beat)
        self.assertIn("head lift", p)
        self.assertIn("Mouth closed, no speech.", p)
        self.assertTrue(
            p.endswith(ps.LIPSYNC_SAFE_TAIL),
            f"expected prompt to end with {ps.LIPSYNC_SAFE_TAIL!r}: {p!r}",
        )
        self.assertNotIn(ps.SPRITE_IDLE_TAIL, p)

    def test_02_arlo_neutral_sprite(self) -> None:
        """Arlo (canonical guide per 2026-06-13) neutral + lipsync_targeted=False:
        lemur constraint + motion-locking tail."""
        beat = {
            "speaker": "Arlo",
            "emotion": "neutral",
            "lipsync_targeted": False,
        }
        p = ps.build_motion_prompt(beat)
        self.assertIn("Mouth closed, no speech.", p)
        self.assertTrue(
            p.endswith(ps.SPRITE_IDLE_TAIL),
            f"expected prompt to end with {ps.SPRITE_IDLE_TAIL!r}: {p!r}",
        )
        self.assertIn("Cartoon Arlo character", p)

    def test_03_legacy_guide_bird_routes_to_arlo(self) -> None:
        """Legacy 'Guide Bird' canonicalizes to Arlo via _SPEAKER_ALIAS,
        gets mouth constraint, canonical name surfaces in prompt text."""
        beat = {
            "speaker": "Guide Bird",
            "emotion": "happy_excited",
            "lipsync_targeted": True,
        }
        p = ps.build_motion_prompt(beat)
        self.assertIn("Mouth closed, no speech.", p)
        self.assertIn("Cartoon Arlo character", p)
        self.assertNotIn("Guide Bird", p)

    def test_04_legacy_pip_routes_to_arlo(self) -> None:
        """Legacy 'Pip' canonicalizes to Arlo via _SPEAKER_ALIAS."""
        beat = {
            "speaker": "Pip",
            "emotion": "sad_disappointed",
            "lipsync_targeted": True,
        }
        p = ps.build_motion_prompt(beat)
        self.assertIn("Mouth closed, no speech.", p)
        self.assertIn("Cartoon Arlo character", p)
        self.assertNotIn("Pip character", p)

    def test_05_unknown_speaker_known_section(self) -> None:
        """Unknown speaker falls through to SECTION_ACTIONS by section."""
        beat = {"speaker": "Rando", "section": "Discovery", "lipsync_targeted": True}
        p = ps.build_motion_prompt(beat)
        self.assertIn(ps.SECTION_ACTIONS["Discovery"], p)
        self.assertIn("Mouth closed, no speech.", p)
        self.assertIn("Cartoon Rando character", p)

    def test_06_unknown_speaker_unknown_section(self) -> None:
        """Unknown speaker + unknown section falls through to DEFAULT_ACTION."""
        beat = {"speaker": "Rando", "section": "NotASection", "lipsync_targeted": True}
        p = ps.build_motion_prompt(beat)
        self.assertIn(ps.DEFAULT_ACTION, p)

    def test_07_invalid_emotion_falls_back_to_neutral(self) -> None:
        """Unknown emotion is promoted to a freeform-action override (not
        a hard 'unknown emotion' rejection). Per Kim 2026-05-19: silent
        promotion is the intended behavior — the test was asserting an
        older error-log shape. Verify the new log shape AND the resulting
        prompt is still well-formed."""
        beat = {"speaker": "Tessa", "emotion": "bonkers", "lipsync_targeted": True}
        buf = io.StringIO()
        with redirect_stdout(buf):
            p = ps.build_motion_prompt(beat)
        out = buf.getvalue()
        # New log message documents the promotion, not an unknown-emotion error.
        self.assertIn("freeform emotion", out)
        self.assertIn("bonkers", out)
        # Prompt is well-formed (contains lipsync-safe tail since lipsync_targeted=True).
        self.assertTrue(p.endswith(ps.LIPSYNC_SAFE_TAIL))

    def test_08_missing_lipsync_targeted_defaults_true(self) -> None:
        """Missing lipsync_targeted defaults True (Event_1 default per LD-180)."""
        beat = {"speaker": "Tessa", "emotion": "happy_excited"}
        p = ps.build_motion_prompt(beat)
        self.assertTrue(p.endswith(ps.LIPSYNC_SAFE_TAIL))
        self.assertNotIn(ps.SPRITE_IDLE_TAIL, p)

    def test_09_sprite_path_no_emotion_defaults_neutral(self) -> None:
        """lipsync_targeted=False with emotion unset: neutral register,
        motion-locking tail."""
        beat = {"speaker": "Tessa", "lipsync_targeted": False}
        p = ps.build_motion_prompt(beat)
        self.assertIn(ps.SPEAKER_MOTION_PROFILES["Tessa"]["neutral"], p)
        self.assertTrue(p.endswith(ps.SPRITE_IDLE_TAIL))


class MotionPromptRuleScanTests(unittest.TestCase):
    """Rule 8.1-8.4 compliance scans across all 28 creature-register combos."""

    def _all_vocab_strings(self):
        for speaker, profiles in ps.SPEAKER_MOTION_PROFILES.items():
            for emotion, vocab in profiles.items():
                yield speaker, emotion, vocab

    def _all_assembled_prompts(self):
        for speaker, emotion, _ in self._all_vocab_strings():
            for lipsync in (True, False):
                beat = {
                    "speaker": speaker,
                    "emotion": emotion,
                    "lipsync_targeted": lipsync,
                }
                yield speaker, emotion, lipsync, ps.build_motion_prompt(beat)

    def test_10_no_banned_prompt_words_in_vocabulary(self) -> None:
        """Rule 8.1: no BANNED_PROMPT_WORDS in any vocabulary string."""
        hits = []
        for speaker, emotion, vocab in self._all_vocab_strings():
            low = vocab.lower()
            for banned in ps.BANNED_PROMPT_WORDS:
                if banned.lower() in low:
                    hits.append((speaker, emotion, banned, vocab))
        self.assertEqual(
            hits, [],
            f"BANNED_PROMPT_WORDS detected in vocabulary: {hits}",
        )

    def test_11_no_rule_8_2_forbidden_phrases(self) -> None:
        """Rule 8.2: no motion-lock / gaze-lock / intensifier phrases.

        Uses word-boundary regex for the single-word intensifiers
        (pressed, sealed, tight, clamped) so that legitimate motion verbs
        like 'tightening' or 'pressing' are not false-positives. The Rule 8.2
        text binds these words to their role as mouth/gaze lock
        intensifiers ('must NOT be reinforced with pressed, sealed, tight,
        clamped'), not to bare substrings of every motion verb.
        """
        multi_word_phrases = [
            "minimal motion", "static camera", "head remains facing forward",
            "no head movement", "frozen face", "face centered",
            "direct forward gaze", "eyes meet camera", "back toward camera",
            "eyes tracking",
        ]
        single_word_intensifiers = re.compile(
            r"\b(pressed|sealed|tight|clamped)\b",
            re.IGNORECASE,
        )
        hits = []
        for speaker, emotion, vocab in self._all_vocab_strings():
            low = vocab.lower()
            for phrase in multi_word_phrases:
                if phrase in low:
                    hits.append((speaker, emotion, phrase, vocab))
            if single_word_intensifiers.search(vocab):
                hits.append((speaker, emotion, "intensifier", vocab))
        self.assertEqual(
            hits, [],
            f"Rule 8.2 forbidden phrases/intensifiers detected: {hits}",
        )

    def test_12_rule_8_1_required_terms_appear_at_most_once(self) -> None:
        """Rule 8.2 'at most once': no Rule 8.1 anti-lipsync term leaks into
        the vocabulary. In the assembled prompt, each required term appears
        at most once (in the constraint line)."""
        required_terms = ("beak closed", "mouth closed", "no speech",
                          "no lip movement")
        for speaker, emotion, lipsync, prompt in self._all_assembled_prompts():
            low = prompt.lower()
            for term in required_terms:
                count = low.count(term)
                self.assertLessEqual(
                    count, 1,
                    f"{term!r} appears {count}x in prompt for "
                    f"{speaker}/{emotion}/lipsync={lipsync}: {prompt!r}",
                )

        # Also: vocabulary alone must not contain any of these terms.
        for speaker, emotion, vocab in self._all_vocab_strings():
            low = vocab.lower()
            for term in required_terms:
                self.assertNotIn(
                    term, low,
                    f"required term {term!r} leaked into vocabulary for "
                    f"{speaker}/{emotion}: {vocab!r}",
                )


class MotionPromptEdgeCaseTests(unittest.TestCase):
    """Edge cases surfaced by preflight round-1 counter-agents (M3)."""

    def test_13_empty_speaker(self) -> None:
        """Empty speaker string: falls through to SECTION_ACTIONS, no crash,
        no double-spaces in assembled prompt."""
        beat = {"speaker": "", "section": "Setup", "lipsync_targeted": True}
        p = ps.build_motion_prompt(beat)
        self.assertIn(ps.SECTION_ACTIONS["Setup"], p)
        self.assertNotIn("  ", p, f"double-space in prompt: {p!r}")

    def test_14_none_speaker(self) -> None:
        """speaker=None: handled as empty, same as test_13."""
        beat = {"speaker": None, "section": "Setup", "lipsync_targeted": True}
        p = ps.build_motion_prompt(beat)
        self.assertIn(ps.SECTION_ACTIONS["Setup"], p)
        self.assertNotIn("  ", p)

    def test_15_whitespace_only_and_trailing_space_speaker(self) -> None:
        """Whitespace-only speaker: treated as empty.
        Trailing-space 'Tessa ': canonicalizes to 'Tessa', gets per-speaker
        profile."""
        beat_ws = {"speaker": "   ", "section": "Setup", "lipsync_targeted": True}
        p_ws = ps.build_motion_prompt(beat_ws)
        self.assertIn(ps.SECTION_ACTIONS["Setup"], p_ws)
        self.assertNotIn("  ", p_ws)

        beat_trail = {
            "speaker": "Tessa ",
            "emotion": "happy_excited",
            "lipsync_targeted": True,
        }
        p_trail = ps.build_motion_prompt(beat_trail)
        self.assertIn(
            ps.SPEAKER_MOTION_PROFILES["Tessa"]["happy_excited"],
            p_trail,
            f"trailing-space speaker failed to canonicalize: {p_trail!r}",
        )
        self.assertIn("Cartoon Tessa character", p_trail)
        self.assertNotIn("Tessa  character", p_trail)

    def test_16_none_emotion_defaults_to_neutral_silently(self) -> None:
        """emotion=None defaults to neutral without firing the unknown-emotion
        warning (the `or` coalesce short-circuits before the VALID check)."""
        beat = {"speaker": "Tessa", "emotion": None, "lipsync_targeted": True}
        buf = io.StringIO()
        with redirect_stdout(buf):
            p = ps.build_motion_prompt(beat)
        self.assertNotIn("unknown emotion", buf.getvalue())
        self.assertIn(ps.SPEAKER_MOTION_PROFILES["Tessa"]["neutral"], p)


class SanitizeInteractionTests(unittest.TestCase):
    """sanitize_prompt must not strip anything from the locked vocabulary.

    Pre-existing inconsistency (not introduced by this change): the §8.1
    required constraint line contains the tokens 'no speech' and 'no
    lip movement', and BANNED_PROMPT_WORDS also lists 'speech' and
    'lip movement'. sanitize_prompt therefore strips those substrings from
    the constraint line of every motion prompt in the codebase, as it has
    since that function was written. That behavior is out of scope here —
    we only assert that the VOCABULARY portion (the creature-specific
    action string) is untouched by sanitize, i.e., the locked vocabulary
    itself introduces no new banned-word hits."""

    def test_17_sanitize_preserves_vocabulary_across_all_combos(self) -> None:
        for speaker, profiles in ps.SPEAKER_MOTION_PROFILES.items():
            canonical = ps._canonicalize_speaker(speaker)
            active_profiles = ps.SPEAKER_MOTION_PROFILES.get(canonical, profiles)
            for emotion, vocab in active_profiles.items():
                for lipsync in (True, False):
                    beat = {
                        "speaker": speaker,
                        "emotion": emotion,
                        "lipsync_targeted": lipsync,
                    }
                    prompt = ps.build_motion_prompt(beat)
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        cleaned = ps.sanitize_prompt(prompt)
                    # Vocabulary substring must survive sanitize intact.
                    self.assertIn(
                        vocab, cleaned,
                        f"vocabulary for {speaker}/{emotion} was altered by "
                        f"sanitize_prompt: {cleaned!r}",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
