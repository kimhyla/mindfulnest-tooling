# Safety Fixes Round 3 — Diff Report (April 11, 2026)

**Protocol:** Verified-Edit (Phase 0–4)
**Corrections:** 17 planned across 7 files
**Source:** 5-agent comprehensive audit + 6-agent counter-verification + Kim approval

---

## Summary: All 17 Planned Corrections Landed ✅

| Fix | ID | File | Status |
|-----|----|------|--------|
| Phase B filename fix | F1a | video-producer | ✅ Applied |
| Naming convention fix | F1b | video-producer | ✅ Applied |
| Blocker check | F2a | phase-b-writer | ✅ Applied |
| Blocker check | F2b | phase-a-designer | ✅ Applied |
| Blocker check | F2c | module-json-builder | ✅ Applied |
| Blocker check | F2d | intake-briefer | ✅ Applied |
| Blocker check | F2e | narrative-generator | ✅ Applied |
| Blocker check | F2f | video-producer | ✅ Applied |
| Rejection workflow | F3 | phase-b-writer | ✅ Applied |
| Concurrent session guard | F4 | dashboard-ops | ✅ Applied |
| Mandatory re-auth | F5a | video-producer | ✅ Applied |
| Mandatory re-auth | F5b | phase-b-writer | ✅ Applied |
| Read-before-write | F6a | phase-b-writer | ✅ Applied |
| Read-before-write | F6b | phase-a-designer | ✅ Applied |
| Read-before-write | F6c | module-json-builder | ✅ Applied |
| Intake handoff | F7 | intake-briefer | ✅ Applied |
| Event 0 guard | F8 | narrative-generator | ✅ Applied |

audio-producer received no Round 3 edits — already compliant from Rounds 1-2.

---

## Per-File Diffs

### 1. video-producer/SKILL.md

**F1a — Phase B output filename**
```diff
- - Output: `M[N]_PHASE_B_FINAL_MIX.mp3`
+ - Output: `m[N]_phase_b_complete_mix.mp3` (produced by audio-producer skill)
```

**F1b — Naming convention example**
```diff
- **Naming convention:** `M1_TESSA_INTRO.mp4`, `M1_TESSA_RESOLUTION.mp4`, `M1_PHASE_B_FINAL_MIX.mp3`
+ **Naming convention:** `M1_TESSA_INTRO.mp4`, `M1_TESSA_RESOLUTION.mp4`, `m1_phase_b_complete_mix.mp3`
```

**F2f — Blocker check (Pipeline Stage Verification)**
```diff
  echo "$VALID_STAGES" | grep -qw "$STAGE" || { echo "ERROR: ..."; exit 1; }
+ STATUS=$(curl -s "$DIRECTUS_URL/items/prod_modules?filter[module_id][_eq]=$MODULE_ID&fields=stage_status" \
+   -H "Authorization: Bearer $TOKEN" | jq -r '.data[0].stage_status')
+ [ "$STATUS" = "blocked" ] && { echo "ERROR: Module is blocked at stage '$STAGE'. Resolve blocker before proceeding."; exit 1; }
```

**F5a — Mandatory re-auth section** (inserted before "After Step 4")
```diff
+ ### MANDATORY: Re-Authenticate Before Each Dashboard Update
+ Video production sessions span 2-4 hours. The initial token WILL expire...
+ [bash block with re-auth pattern]
```

### 2. phase-b-writer/SKILL.md

**F2a — Blocker check**
```diff
  [ "$STAGE" != "phase_b" ] && { echo "ERROR: ..."; exit 1; }
+ [ "$STATUS" = "blocked" ] && { echo "ERROR: Module is blocked..."; exit 1; }
```

**F3 — Rejection workflow** (inserted after sequence reminder)
```diff
+ ### If Kim Rejects Phase B
+ If Kim says "no," "not ready," or flags issues:
+ 1. Do NOT record an approval. Do NOT advance.
+ 2. Set stage_status = 'in_progress' [curl command]
+ 3. Create blocker record if needed [curl command]
+ 4-6. Log, revise, re-present
```

**F5b — Mandatory re-auth note** (inserted before dashboard section)
```diff
+ ### MANDATORY: Re-Authenticate Before Dashboard Updates
+ Phase B production sessions can exceed 15 minutes...
```

**F6a — Read-Before-Write Rule** (inserted before Step 0)
```diff
+ ### Read-Before-Write Rule
+ Before generating or regenerating ANY Phase B script content:
+ 1. Re-read the current .docx or .md draft from disk...
+ 2. If the file has changed since you last wrote it... STOP
+ 3. Never generate a new document purely from memory.
```

### 3. phase-a-designer/SKILL.md

**F2b — Blocker check**
```diff
+ STATUS=$(curl -s ... | jq -r '.data[0].stage_status')
  [ "$STAGE" != "phase_a_json" ] && { echo "ERROR: ..."; exit 1; }
+ [ "$STATUS" = "blocked" ] && { echo "ERROR: Module is blocked..."; exit 1; }
```

**F6b — Read-Before-Write Rule** (inserted before Step 1)
```diff
+ ### Read-Before-Write Rule
+ Before generating or regenerating ANY Phase A beat sheet:
+ 1. Re-read the current beat sheet from disk...
+ 2. If the file has changed... STOP and ask Kim
+ 3. Never generate a new document purely from memory.
```

### 4. module-json-builder/SKILL.md

**F2c — Blocker check**
```diff
+ STATUS=$(curl -s ... | jq -r '.data[0].stage_status')
  [ "$STAGE" != "phase_a_json" ] && { echo "ERROR: ..."; exit 1; }
+ [ "$STATUS" = "blocked" ] && { echo "ERROR: Module is blocked..."; exit 1; }
```

**F6c — Read-Before-Write Rule** (inserted before Step 1)
```diff
+ ### Read-Before-Write Rule
+ Before generating or regenerating ANY module JSON:
+ 1. Re-read the current module_M{N}_config.json from disk if one exists...
+ 2. If the file has changed... STOP and ask Kim
+ 3. Always read the current Phase A beat sheet and Phase B script from disk...
```

### 5. intake-briefer/SKILL.md

**F2d — Blocker check**
```diff
+ STATUS=$(curl -s ... | jq -r '.data[0].stage_status')
  [ "$STAGE" != "intake" ] && { echo "ERROR: ..."; exit 1; }
+ [ "$STATUS" = "blocked" ] && { echo "ERROR: Module is blocked..."; exit 1; }
```

**F7 — Intake → kim_seeds handoff**
```diff
- 3. **No hard gate** — automatically advances to `kim_seeds` stage
+ 3. **No hard gate** — advance to `kim_seeds` stage after all briefs are created:
+    ```bash
+    curl -s -X PATCH "$BASE/items/prod_modules/$MODULE_ID" ... '{"current_stage": "kim_seeds", "stage_status": "not_started"}'
+    curl -s -X POST "$BASE/items/prod_activity_log" ... (log advancement)
+    ```
```

### 6. narrative-generator/SKILL.md

**F2e — Blocker check**
```diff
+ STATUS=$(curl -s ... | jq -r '.data[0].stage_status')
  echo "$VALID_STAGES" | grep -qw "$STAGE" || { echo "ERROR: ..."; exit 1; }
+ [ "$STATUS" = "blocked" ] && { echo "ERROR: Module is blocked..."; exit 1; }
```

**F8 — Event 0 guard**
```diff
  Before running the narrative generation pipeline:
+ - [ ] **This is NOT Event 0 (Opening Storybook).** Event 0 is pre-produced — no narrative generation. If this is Event 0, STOP immediately.
  - [ ] Module has **Phase B approval**...
```

### 7. dashboard-ops/SKILL.md

**F4 — Concurrent Session Safety** (inserted after Operational Rules)
```diff
+ ## Concurrent Session Safety
+ Kim frequently uses multiple Claude threads simultaneously...
+ ### Read-Before-Write Rule
+ Before ANY PATCH to prod_modules, re-read the module's current state:
+ [bash block with state comparison and warning]
+ ### Rules
+ 1. Re-read before every PATCH.
+ 2. If the module has moved since you last read it, STOP.
+ 3. Log all writes with session context.
+ 4. One module per thread.
```

---

## Independent Validation Results

**Validator 1** (mechanism sweep — read all 7 files cold):

| Skill | A: Blocker Check | B: Read-Before-Write | C: Concurrent Safety | D: Event 0 Guard |
|-------|:-:|:-:|:-:|:-:|
| video-producer | ✅ PASS | EXEMPT | EXEMPT | EXEMPT |
| phase-b-writer | ✅ PASS | ✅ PASS | EXEMPT | EXEMPT |
| phase-a-designer | ✅ PASS | ✅ PASS | EXEMPT | EXEMPT |
| module-json-builder | ✅ PASS | ✅ PASS | EXEMPT | EXEMPT |
| intake-briefer | ✅ PASS | EXEMPT | EXEMPT | EXEMPT |
| narrative-generator | ✅ PASS | EXEMPT | EXEMPT | ✅ PASS |
| dashboard-ops | EXEMPT | EXEMPT | ✅ PASS | EXEMPT |

**Verdict: ALL PASS**

**Validator 2** (specific fix verification):

| Check | Result |
|-------|--------|
| 1. Filename consistency | ✅ PASS — old name GONE, new name PRESENT |
| 2. Rejection workflow | ✅ PASS — section with curl commands present |
| 3. Mandatory re-auth | ✅ PASS — both files have sections in correct position |
| 4. Intake handoff | ✅ PASS — curl for kim_seeds advancement present |
| 5. Retired terminology | ✅ PASS — zero hits in active content |
| 6. Changelog entries | ✅ PASS — all 7 edited files have Round 3 entries (audio-producer correctly has no entry — it received no Round 3 edits) |

**Verdict: ALL PASS**

---

## Backups Created

| File | Backup |
|------|--------|
| video-producer/SKILL.md | SKILL_backup_round3_20260411.md |
| phase-b-writer/SKILL.md | SKILL_backup_round3_20260411.md |
| phase-a-designer/SKILL.md | SKILL_backup_round3_20260411.md |
| module-json-builder/SKILL.md | SKILL_backup_round3_20260411.md |
| intake-briefer/SKILL.md | SKILL_backup_round3_20260411.md |
| narrative-generator/SKILL.md | SKILL_backup_round3_20260411.md |
| dashboard-ops/SKILL.md | SKILL_backup_round3_20260411.md |

---

## Cumulative Safety Status (All 3 Rounds)

After Rounds 1, 2, and 3, all 8 production skills now have:

| Mechanism | Coverage |
|-----------|----------|
| Pipeline Stage Verification | 6/6 applicable skills (+ blocker check) |
| Version-Up Rule | 8/8 skills |
| Pre-Write Kim Confirmation Gate | 8/8 skills |
| Blocker-Blind Fix | 6/6 Pipeline Stage Verification blocks |
| Read-Before-Write Rule | 3/3 content-producing skills |
| Concurrent Session Safety | 1/1 (dashboard-ops, referenced by all) |
| Rejection Workflow | 1/1 (phase-b-writer, the hard gate skill) |
| Token TTL Mandatory Re-Auth | 2/2 long-session skills |
| Intake → Kim Seeds Handoff | 1/1 (intake-briefer) |
| Event 0 Guard | 2/2 applicable skills (video-producer + narrative-generator) |
| Filename Consistency | Resolved (audio→video alignment) |

**Retired terminology:** ZERO hits across all 8 files in active content.
