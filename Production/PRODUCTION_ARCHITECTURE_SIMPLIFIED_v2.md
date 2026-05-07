# MindfulNest Production Architecture — Simplified Reference
**Version:** 2.0 (Lean edition)  
**Date:** April 14, 2026  
**For the full version with all details, see:** `PRODUCTION_ARCHITECTURE_MASTER_v1.md`

---

## 1. The Four Tools We Have

| Tool | What It Does | Input → Output |
|------|-------------|----------------|
| **Storyboard** (`build_storyboard.py`) | Edit dialogue, assign images, lock sequence | Lines JSON → Locked Sequence JSON |
| **Cropper** (`build_cropper.py`) | Crop master into 4:3 close-ups (≥600px) | PNG image → Crop PNGs |
| **TTS Audition** (`build_tts_review.py`) | Review voice audio, regenerate, approve | Config JSON → Approved MP3s |
| **Animation Review** (`build_animation_review.py`) | Pick best clip from 3 options per beat | Manifest JSON → Picks JSON |

All tools: self-contained HTML, base64-embedded assets, localStorage persistence, JSON export, auto-register in Directus.

---

## 2. The Seven Rules That Matter Most

1. **Never edit HTML directly.** Always use the Python builder or JS-only patches via Python.
2. **Export before rebuild.** Kim's browser edits live in localStorage, not on disk. Always ask her to export first.
3. **Version-up, never overwrite.** New version = new filename. Always.
4. **When in doubt, patch; don't rebuild.** JS-only patch preserves everything. Rebuilds risk losing state.
5. **Dashboard first.** Query Directus before work, log as you go.
6. **Open files for Kim.** Use Finder. Never give her a file path.
7. **Run --audit-previous on every rebuild.** Catches regressions before they reach Kim.

---

## 3. What Gets Produced — And When

### Produce NOW (full video):
- **Story Scene** — the animated narrative intro (storyboard → crops → TTS → animation → lip sync → ffmpeg)
- **Resolution** — the emotional payoff scene (same pipeline)

### Produce NOW (audio only):
- **Buy-In / Phase A** — Guide Bird voice stems (TTS). Park for app integration.
- **Phase B** — Myrrhin meditation audio (TTS + ambient + gong + breathCycle cue points). Full audio production. Park visuals.
- **Win / Map Return** — Sound effects, creature dialogue TTS. Park for app integration.

### Produce LATER (after app architecture is locked):
- **Phase A visuals/interaction** — Runtime React component. Format depends on app (Lovable, Cursor, etc.)
- **Phase B visuals** — Runtime Phaser breathing circle + color-coded particles (not video). Syncs to produced audio cue points.
- **Win UI animations** — Coins, spell card, decoration item.
- **Map Return** — Sprite positioning, zone features.

**Why this order:** Audio is format-agnostic (MP3 is MP3). Interactive/visual configs are tightly coupled to the app engine. Produce what's universal now; defer what depends on architecture decisions.

---

## 4. Video Production Pipeline (Story Scene + Resolution)

```
Image Selection (Kim picks in Finder)
    → Cropper (4:3 crops, ≥600px)
    → Storyboard (assign images to dialogue, export locked sequence)
    → TTS Audition (approve voice stems per line)
    → Animation Generation (Kling v3, 3 options per beat)
    → Animation Review (pick winners; re-generate if none work)
    → ByteDance LatentSync (lip sync)
    → FFmpeg Assembly (transitions + audio mix → final video)
    → Kim reviews in QuickTime → approve or redo
```

**Transitions:** Hardcoded conventions — hard cut within segments, 0.5s crossfade between segments, 1.5s fade to/from black for Phase B entry/exit. Override dropdown available per beat in animation review if conventions don't work.

---

## 5. Audio-Only Pipeline (Buy-In / Phase A / Phase B)

**Buy-In + Phase A:**
```
Skeleton dialogue → ElevenLabs TTS (Guide Bird) → TTS Audition → Approve → Register in Directus → Park
```

**Phase B (full production):**
```
Approved script → Myrrhin TTS (stability 0.30, speed 0.50) → Vosk cue extraction → breathCycle → ambient bed + gong → ffmpeg mix → Kim listen-through → Register in Directus → Park
```

---

## 6. Approval Gates

| Gate | What Kim Decides | Tool |
|------|-----------------|------|
| Image selection | Which master images to use | Finder |
| Storyboard lock | Dialogue, image assignments, pauses | Storyboard export |
| TTS approval | Voice quality per line | TTS Audition verdicts |
| Animation pick | Best clip per beat (re-gen if none work) | Animation Review picks |
| Listen-through | Final video/audio quality | QuickTime Player |

---

## 7. What's Next (Priority Order)

1. **Finish M1 Story Scene video** — transition conventions → lip sync → assembly → Kim review
2. **Produce M1 Resolution video** — same pipeline
3. **Produce all remaining M1 audio** — Buy-In, Phase A, Phase B voice stems + Phase B full mix
4. **Build the app** — lock runtime architecture (React, Phaser, database, game engine)
5. **Wire audio into app** — finish Buy-In/Phase A/Phase B using actual app architecture

---

## 8. Key References

| Document | What It Covers |
|----------|---------------|
| `PIPELINE_BRAIN_v1.md` | Full pipeline stages, 9 skills, APIs, safety, step-by-step walkthrough |
| `PRODUCTION_ARCHITECTURE_MASTER_v1.md` | Complete version of this doc — all 19 rules, universal container plan, transition debate, risks |
| `API_KEYS_MASTER.md` | All API credentials (read at runtime, never hardcode) |
| `HANDOFF_TEMPLATE.md` | End-of-session handoff (fill out every time) |
| `.auto-memory/MEMORY.md` | Memory index for session-to-session context |

---

## 9. Session Checklist

At the start of every production session:
1. Run staleness scan (character names, technique names, version drift)
2. Load `dashboard-gate` skill FIRST
3. Run 7-query Directus protocol
4. Check storyboard freshness (`prod_modules` tracking fields)

At the end of every production session:
1. Fill out `HANDOFF_TEMPLATE.md`
2. Register any new assets in Directus
3. Log session decisions to `prod_activity_log`

---

*This is the simplified version. For full details on the universal container refactor, transition design debate (5 proposals), 19 battle-tested rules, risk mitigations, and the complete tool architecture audit, see `PRODUCTION_ARCHITECTURE_MASTER_v1.md`.*
