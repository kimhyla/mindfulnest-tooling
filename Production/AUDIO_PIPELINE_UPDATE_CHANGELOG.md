# Audio Pipeline Update — Change Log
## February 24, 2026

### Root Cause
When mixing M2 Phase B audio, breath tones (inhale/exhale wind sounds) were consistently placed at the wrong timestamps. The automation was using waveform energy analysis to guess which speech segment corresponded to which script word — and guessing wrong. The word "breathe" appeared 4 times in the M2 script (twice in descriptive context, twice as actual breathing instructions), and the system picked occurrence #1 instead of occurrence #3.

### Solution: Vosk Speech-to-Text with Word Timestamps
Instead of guessing from waveform energy, run offline speech-to-text (vosk) on the voice stem to get exact word-level timestamps. Then match cue words to their correct occurrences using script-level cue markers.

### Documents Updated

| # | Document | Version | Key Changes |
|---|----------|---------|-------------|
| 1 | PHASE_B_AUDIO_ASSEMBLY_GUIDE | v1.1 → v1.3 | Method B rewritten: vosk STT replaces "future" ElevenLabs Forced Alignment. New §2.2.1 Disambiguation Rule. New §2.2.2 Script Cue Markers spec. §1.2 updated (Forced Alignment → vosk). §4.4 updated (forced alignment data → vosk STT). Volume defaults updated (bed 0.08, worked example 0.08). M2 module notes completed. Checklist updated. |
| 2 | PHASE_B_AUDIO_ENGINE_ARCHITECTURE | v1.0 → v1.1 | §6.2 updated with disambiguation warning. §6.3 rewritten: vosk is proven method, not "future." Ambient bed default lowered from 0.15 to 0.08 in schema, volume table, code examples, and all 4 worked example JSON configs. |
| 3 | M2_PHASE_B_MEDITATION_SCRIPT | v1.0 → v1.1 | "The air feels different now" removed from Transition 1. Voice direction and source traceability updated. |
| 4 | ELEVENLABS_SOUND_RECIPE | v1.0 → v1.1 | Assembly section updated: vosk-based cue mapping reference. Ambient bed 15-20% → 8%. "The air feels different now" removed from quoted M2 script. |
| 5 | PHASE_B_PRODUCTION_PROCESS | v1.1 → v1.2 | New Step 9b: Embed Audio Cue Markers in script before handoff to assembly. Process summary table updated. |
| 6 | PHASE_B_SOUND_PRODUCTION_BRIEF | v1.0 → v1.1 | M2 timeline: "The air feels different now" removed from Transition section. |
| 7 | MINDFULNEST_COWORK_PLUGIN_SPEC | v2.5 → v2.6 | Ambient bed volume defaults updated from 0.20-0.25 to 0.08 in both system prompt and /audio-assemble command. |

### Documents NOT Changed (confirmed clean)
- M3_PHASE_B_MEDITATION_SCRIPT_v2_CORRECTED.md — Does not contain "the air feels different now." Confirmed clean.
- MODULE_AUTHORING_GUIDE_v4_3.md — No audio pipeline references to update.
- CANONICAL_DATA_MODEL_v1_2.md — No changes needed.
- SEED_MODULES_APPROVED_v1_1.md / LOCK_RECORD — No changes needed (module content not affected).

### Voice Decision
- M1: Myrrdin voice LOCKED (approved mix unchanged)
- M2: Myrrdin voice (new mix with vosk-corrected tone placement)
- M3: Cornelius voice (locked from prior session — Myrrdin re-record recommended but not urgent)
- M4-M13: Myrrdin preferred (decision confirmed Feb 24)

### New Learnings Codified
1. **Never use waveform energy analysis to identify script words.** Use STT.
2. **Cue words can appear multiple times in a script.** The system must disambiguate by counting occurrences and matching to script-level markers.
3. **Generate counting phrases as whole sentences, not individual number clips.** ElevenLabs produces better prosody with full context.
4. **Lighter ambient bed (0.08 gain) reduces cognitive load** for children vs. the original 0.20 default.
