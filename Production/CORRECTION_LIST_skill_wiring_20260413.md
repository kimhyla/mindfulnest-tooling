# Master Correction List: Wire prod_scripts into Production Skills
## Date: April 13, 2026

---

## File A: `.claude/skills/dashboard-gate/SKILL.md`

### A1 — Add Query 8 to the 7-Query Table (targeted)
- **Old text:** `| 7 | `GET /items/prod_voice_profiles?filter[character_name][_eq]=Myrrhin` | Locked voice settings (stability, speed, model) | Use correct TTS parameters |`
- **New text:** (append new row after row 7)
```
| 7 | `GET /items/prod_voice_profiles?filter[character_name][_eq]=Myrrhin` | Locked voice settings (stability, speed, model) | Use correct TTS parameters |
| 8 | `GET /items/prod_scripts?filter[module_id][_eq]={id}` | Script registry: type, version, status, file paths, Kim verdict | Know which scripts exist, their approval state, and where they live on disk |
```

### A2 — Update "Run ALL seven" instruction to "Run ALL eight" (targeted)
- **Old text:** `Run ALL seven. Not some. Not "the relevant ones." All seven.`
- **New text:** `Run ALL eight. Not some. Not "the relevant ones." All eight.`

### A3 — Add disk-vs-registry validation step after query table (targeted)
- **Insert after:** The query table (after row 8 from A1)
- **Location:** Between the query table and "### Step 3: Synthesize Before Proceeding"
- **New content to insert before Step 3:**
```

### Step 2b: Disk-vs-Registry Validation (Scripts)

After running query 8, compare the registry against what actually exists on disk:

1. For each record in `prod_scripts`, check that `file_path` points to a file that exists
2. Check the disk for script files matching `Production/Event_{N}/` patterns that are NOT in the registry
3. Compare `current_version` in Directus against the highest version number found on disk

**If registry says v10 but disk has v11:** The registry is stale. Update `prod_scripts` to reflect the disk version before proceeding.
**If registry has a file that doesn't exist on disk:** Flag as RED — the file may have been moved or deleted. Ask Kim.
**If disk has scripts not in the registry:** Register them now (POST to `prod_scripts`) before proceeding.

This step prevents the registry from becoming a source of false confidence. The disk is always ground truth; the registry is a convenience index that must stay in sync.
```

### A4 — Update Dashboard State Summary to include script registry (targeted)
- **Old text:** `- Resumption notes (if any)`
- **New text:**
```
- Resumption notes (if any)
- Script registry: number of registered scripts, their types and statuses, any disk-vs-registry mismatches found
```

### A5 — Update Self-Check Protocol with prod_scripts question (targeted)
- **Old text:** `7. Am I about to contradict a locked decision? (If yes → STOP → ask Kim)`
- **New text:**
```
7. Am I about to contradict a locked decision? (If yes → STOP → ask Kim)
8. Is every script I'm using registered in `prod_scripts` with correct version and status?
```

### A6 — Update "7-query" reference in Rule 1 to "8-query" (targeted)
- **Old text:** `Do not generate TTS, run ffmpeg, create audio files, write scripts, or advance module stages without having completed the 7-query session start protocol in this session.`
- **New text:** `Do not generate TTS, run ffmpeg, create audio files, write scripts, or advance module stages without having completed the 8-query session start protocol in this session.`

---

## File B: `.claude/skills/audio-producer/SKILL.md`

### B1 — Add prod_scripts pre-check to Step 0 checklist (targeted)
- **Old text:** `- [ ] Read `Production/API_KEYS_MASTER.md` for current ElevenLabs API key`
- **New text:**
```
- [ ] Read `Production/API_KEYS_MASTER.md` for current ElevenLabs API key
- [ ] Query `prod_scripts` for this module's Phase B scripts: `GET /items/prod_scripts?filter[module_id][_eq]={id}&filter[script_type][_in]=phase_b_meditation,phase_b_tts_input`. Verify status is `approved` or `audio_locked`. If status is `draft` or `needs_revision`, STOP — the script is not ready for audio production.
```

### B2 — Add prod_scripts post-action to Post-Mix section (targeted)
- **Old text:** `3. Advance `current_stage` to `listen_through`, `stage_status` to `not_started``
- **New text:**
```
3. Advance `current_stage` to `listen_through`, `stage_status` to `not_started`
4. Update `prod_scripts` for the Phase B TTS input: PATCH status to `audio_locked`, add note with voice stem filename and mix filename
5. Log script registry update in `prod_activity_log`: "M{N} Phase B TTS input locked — audio produced from v{X}"
```

---

## File C: `.claude/skills/video-producer/SKILL.md`

### C1 — Add script lookup pre-check to Gate 0 checklist (targeted)
- **Old text:** `- [ ] Does a Phase B script exist and is it approved? If not, note as prerequisite.`
- **New text:**
```
- [ ] Does a Phase B script exist and is it approved? If not, note as prerequisite.
- [ ] Query `prod_scripts` for ALL scripts for this module: `GET /items/prod_scripts?filter[module_id][_eq]={id}`. Verify: Buy-In script exists and status is `approved`; Phase A script exists; Phase B script exists and status is `approved` or `audio_locked`; Resolution script exists and status is `approved`. Any missing or unapproved script = note as prerequisite before production.
```

### C2 — Add script registry reference to Step 3 TTS generation (targeted)
- **Old text:** `Batch-render dialogue lines from Step 1 that have FINALIZED text. This covers Story Scene dialogue, Buy-In script (if written), and Resolution dialogue from the skeleton.`
- **New text:** `Batch-render dialogue lines from Step 1 that have FINALIZED text. This covers Story Scene dialogue, Buy-In script (if written and registered in `prod_scripts` as approved), and Resolution dialogue from the skeleton. Before rendering, cross-check script versions against `prod_scripts` to ensure you're using the latest approved version.`

---

## Verification Checklist
- [ ] A1-A6: dashboard-gate has 8 queries, disk validation, updated summary, updated self-check, updated rule reference
- [ ] B1-B2: audio-producer has pre-check and post-action
- [ ] C1-C2: video-producer has script lookup pre-check and TTS cross-check
- [ ] All edits are surgical (Edit tool, not Write)
- [ ] No changelogs or version history were modified
- [ ] Formatting (tables, headers, markdown) is intact
