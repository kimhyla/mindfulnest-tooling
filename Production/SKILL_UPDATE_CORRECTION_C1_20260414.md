# Correction C1: Video Extension / Clip Chaining — Multi-Clip Mandatory

**Date:** April 14, 2026
**Task:** Update video-producer skill (line 199) to make multi-clip mandatory and forbid freeze-frame extension.

## Status

**File System Constraint:** The original skill file at `/sessions/admiring-quirky-noether/mnt/.claude/skills/video-producer/SKILL.md` is located in a read-only mounted volume (`ro` bindfs). Direct editing via the Edit tool fails with `EROFS: read-only file system`.

**Solution:** Updated working copy created in writable project folder: `Production/SKILL_video-producer_UPDATED_20260414.md`

## Change Summary

**Location:** Line 199
**Section:** Step 5: Animate Clips (Seedance 2.0 / Kling 3.0)

### Old Text (Pre-correction)
```
**Video extension / clip chaining:** Generate initial clip → feed last frame as input to next generation → scene continues with new motion prompt. Supported by Seedance 2.0 and Kling 3.0. This is how you build 50+ second continuous sequences from 4-5 second clips.
```

### New Text (Post-correction)
```
**Video extension / clip chaining (MANDATORY — no freeze frames):** When audio exceeds the animation tool's max clip duration (5s for Kling/Seedance), generate continuation clips by extracting the last frame of clip N and submitting it as input for clip N+1 with the same motion prompt. Concatenate all clips seamlessly, then trim to exact audio duration. NEVER use freeze-frame extension (tpad/stop_mode=clone) — frozen frames are forbidden in production output. This is how you build 50+ second continuous sequences from 4-5 second clips. Cost: ~$0.375 per additional 5s clip (EvoLink). Locked rule as of April 14, 2026.
```

## Verification

**Pre-replacement grep counts:**
- "MANDATORY — no freeze frames": 0 matches (expected)
- "Generate initial clip → feed last frame": 1 match (original text present)
- "frozen frames are forbidden": 0 matches (expected)

**Post-replacement grep counts (in updated file):**
- "MANDATORY — no freeze frames": **1 match** ✓
- "Generate initial clip → feed last frame": **0 matches** ✓ (successfully replaced)
- "frozen frames are forbidden": **1 match** ✓

## Key Changes Explained

1. **MANDATORY flag** — Establishes multi-clip chaining as non-negotiable rule
2. **Clear instruction** — Specifies exact mechanism: extract last frame N → feed to N+1 with same prompt
3. **Freeze-frame prohibition** — Explicitly forbids tpad/stop_mode=clone extension
4. **Cost note** — ~$0.375 per 5s continuation clip (EvoLink)
5. **Locked date** — April 14, 2026 (immutable decision)

## Next Steps

The updated file requires deployment to the read-only skills volume. This may require:
1. A build system update to copy the corrected skill from project folder to `.claude/skills/`
2. Manual intervention by the system administrator to unlock and update the mounted skill directory
3. Contact with the Cowork platform if this is a system-level configuration

**Action required:** Transfer `SKILL_video-producer_UPDATED_20260414.md` content to `/sessions/admiring-quirky-noether/mnt/.claude/skills/video-producer/SKILL.md` (requires write access to read-only volume).
