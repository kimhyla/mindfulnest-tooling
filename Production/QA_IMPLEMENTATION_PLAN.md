# QA Validation Suite — Implementation Plan

**Date:** April 14, 2026  
**Scope:** Automated validation for MindfulNest production artifacts  
**Audience:** Solo founder (Kim) + Claude production automation  

---

## Executive Summary

A **hybrid QA approach** for MindfulNest: Python scripts handle 95% of validation work (file integrity, schema compliance, asset registration). Playwright is **only** used for HTML storyboard runtime testing (image loading, export button, interactivity). This keeps the tooling simple, maintainable, and appropriate for a one-person team.

**Single command:** `python3 Production/tools/qa/run_all.py --module M1 --stage audio` produces a detailed report with pass/fail status for each test. Reports feed into Directus activity_log for persistent audit trail.

---

## Toolkit Architecture

```
Production/tools/qa/
├── validate_phase_b.py          # Phase B script validation
├── validate_module_json.py       # Module JSON schema & guardrails
├── validate_audio.py             # Audio file integrity
├── validate_storyboard.py        # Playwright: HTML runtime testing
├── run_all.py                    # Orchestrator + report generator
├── requirements.txt              # All dependencies
└── README.md                     # Usage & troubleshooting
```

### Hybrid Approach Rationale

- **Python validators** (validate_phase_b.py, validate_module_json.py, validate_audio.py): Parse files, check schema compliance, verify references. Fast, reliable, no UI needed.
- **Playwright only** (validate_storyboard.py): Test HTML storyboards for runtime issues — image render failures, missing drag-drop, export button crashes. Necessary because storyboard HTML has embedded JS that can fail silently.
- **No Playwright for non-HTML artifacts.** JSON schema checking, audio file integrity, and script validation are pure file I/O — Python handles it directly.

---

## File Structure & Test Specs

### 1. validate_phase_b.py

**Purpose:** Validate approved Phase B scripts before audio production.

**Inputs:**
- Phase B script file (`.md` or `.docx`)
- Reference: `Production/PIPELINE_BRAIN_v1.md` (stage definitions)

**Tests:**
- **Cue markers present**: Script contains `[CUE: ...]` markers for audio producer
- **Variable validation**: All personalization variables (`{childName}`, `{therapistName}`) are documented
- **Section structure**: Script has all required sections (Transition, Phase B Meditation, Resolution)
- **No clinical labels**: Script does not expose raw clinical terminology (e.g., "interoception") to child-facing dialogue
- **Duration estimate**: Script is 180–300 seconds (typical Phase B length)
- **UTF-8 encoding**: File encodes cleanly (no mangled characters)

**Output:**
```
PHASE_B_VALIDATION
├── module_id: M1
├── filename: M1_phase_b_script_v3.md
├── status: PASS
├── cue_markers_found: 8
├── variables_used: {childName}, {chosenGuideName}
├── duration_estimate_seconds: 240
├── warnings: none
└── flags: none
```

**Failure Mode:** If any test fails, output `status: FAIL` + specific line numbers where issues appear. Flag for Kim review (do not auto-fix).

---

### 2. validate_module_json.py

**Purpose:** Enforce schema compliance and guardrail checks on module JSON.

**Inputs:**
- Module JSON file (`module_M{N}_config.json`)
- Reference: `CANONICAL_DATA_MODEL_v1_12.md` (schema authority)
- Reference: `CLAUDE_MODULE_JSON_SCHEMA_GUARDRAILS_v2_3.md` (Q1-Q19 checklist)

**Tests:**
- **JSON structure**: Valid JSON, not truncated, parses completely
- **Required fields present**: moduleId, title, spellName, domain, creatureId, phaseAConfig, guidedAudioRef
- **Enum compliance**: domain ∈ {breathing, watching, kindness, courage, bodysensing, selfgrounding}, creatureId ∈ {tessa, luna, benson, ember, bork, bramble}
- **Unique spell name** (Q19): spellName not duplicated across all modules in registry
- **Cross-field consistency**: creature-domain-stone mapping matches Arc 1 reference table (M1=Tessa/bodysensing, etc.)
- **No arc/narrative references** (Q8): moduleId, title, dialogue contain zero arc/bar/event references (modules are context-free)
- **Dialogue source fidelity**: phaseAConfig text matches original Phase A beat sheet verbatim (sampled spot-check against disk file)
- **File reference validity**: guidedAudioRef, phaseBVisualRef, backgroundRef, rescueCreatureVisual point to files that exist on disk (or are expected during audio stage)

**Output:**
```
MODULE_JSON_VALIDATION
├── module_id: bodysensing_magic_hands
├── filename: module_M1_config.json
├── status: PASS
├── schema_score: 100% (26/26 required fields)
├── enum_checks: PASS (domain, creatureId, techniqueId)
├── guardrail_q1_q19: PASS
│   ├── Q8_context_free: PASS
│   ├── Q19_unique_spell: PASS
│   ├── all_others: PASS
├── fidelity_spot_check: PASS (5 cues sampled, 100% match original)
├── file_refs_exist: PASS (all refs found or expected at stage)
└── warnings: none
```

**Failure Mode:** Report failing guardrails by question number (e.g., "Q8 FAIL: moduleId contains arc reference"). Do not auto-fix semantic issues; flag for Kim.

---

### 3. validate_audio.py

**Purpose:** Validate audio asset integrity after production.

**Inputs:**
- Audio file path (`.mp3`)
- Expected file: `Production/Event_{N}/m{N}_phase_b_complete_mix.mp3`

**Tests:**
- **File exists**: Audio file found at expected path
- **Valid MP3**: File header is valid, not corrupted
- **Duration**: Actual duration matches metadata claim (within 5 seconds tolerance)
- **Bitrate**: 128 kbps or higher (acceptable quality threshold)
- **No clipping**: Peak amplitude <-0.5dB (early warning for distortion)
- **Silence detection**: First 0.5 seconds and last 0.5 seconds not completely silent (fade-in/out verification)
- **Mono/stereo**: Confirm channel count (production spec: mono or stereo, no 5.1)

**Dependencies:** `librosa`, `scipy`

**Output:**
```
AUDIO_VALIDATION
├── filepath: Production/Event_1/m1_phase_b_complete_mix.mp3
├── status: PASS
├── file_size_mb: 3.2
├── duration_seconds: 242
├── bitrate_kbps: 192
├── channels: 1 (mono)
├── peak_amplitude_db: -2.1
├── fade_in_detected: true
├── fade_out_detected: true
└── warnings: none
```

**Failure Mode:** Missing file = `status: FAIL, error: not_found`. Invalid MP3 = `status: FAIL, error: corrupt_or_invalid`. Duration mismatch = `status: WARN, delta_seconds: 8` (non-blocking, but logged).

---

### 4. validate_storyboard.py (Playwright)

**Purpose:** Runtime test for storyboard HTML — image rendering, interactivity, export.

**Inputs:**
- Storyboard HTML file (`storyboard_M{N}_v{V}.html`)
- Browser: Chromium (Playwright-managed)

**Tests:**
- **HTML loads**: Page navigates, no 404 or script errors in console
- **Images render**: All `<img>` tags load without errors; image `src` attributes are valid data URLs or absolute paths
- **Drag-drop functional**: If storyboard has drag-drop (`.draggable`), verify one image can be dragged and dropped
- **Export button exists**: Button with class/id `export` or similar exists in DOM
- **Export click works**: Click export; file download triggered (verify via browser event, not full file I/O)
- **No console errors**: Page logs zero uncaught exceptions during interaction

**Dependencies:** `playwright`, `pytest`

**Output:**
```
STORYBOARD_VALIDATION
├── filepath: Production/Event_1/storyboard_M1_v13.html
├── status: PASS
├── page_load: OK (0 console errors)
├── images_found: 11
├── images_rendered: 11 (100%)
├── drag_drop: FUNCTIONAL
├── export_button: FOUND (id="export-btn")
├── export_click: TRIGGERED
└── warnings: none
```

**Failure Mode:** 
- Image render fail = `status: FAIL, failed_images: [list]`
- Console error = `status: FAIL, console_error: [error text]`
- Export button missing = `status: FAIL, issue: export_button_missing`

**Why Playwright here and nowhere else:** Storyboard HTML is runtime-composed with embedded JS. Drag-drop and export button are dynamic features that require a real browser to test. JSON schema validation or file parsing cannot catch JS bugs; Playwright can.

---

### 5. run_all.py (Orchestrator)

**Purpose:** Run all validators in sequence, collect results, produce summary report.

**CLI Signature:**
```bash
python3 Production/tools/qa/run_all.py \
  --module M1 \
  --stage audio \
  [--output report.json] \
  [--directus-log]
```

**Behavior:**
1. Check module status in Directus (verify stage matches requested stage)
2. Locate all artifacts for the module at that stage
3. Run appropriate validators:
   - `audio` stage: validate_audio.py
   - `phase_a_json` stage: validate_module_json.py
   - `phase_b` stage: validate_phase_b.py
   - `listen_through` stage: all three + validate_storyboard.py (full QA before Kim approval gate)
4. Aggregate results into structured report
5. Print summary to stdout
6. (Optional) Log results to Directus activity_log for audit trail

**Output Format:**
```json
{
  "session_id": "20260414_m1_audio",
  "module_id": "M1",
  "stage": "audio",
  "run_timestamp": "2026-04-14T17:45:23Z",
  "overall_status": "PASS",
  "test_results": {
    "validate_audio": {
      "status": "PASS",
      "file": "Production/Event_1/m1_phase_b_complete_mix.mp3",
      "details": { ... }
    },
    "validate_module_json": {
      "status": "PASS",
      "file": "module_M1_config.json",
      "details": { ... }
    },
    "validate_phase_b": {
      "status": "WARN",
      "file": "M1_phase_b_script_v3.md",
      "details": { ... }
    },
    "validate_storyboard": { ... }
  },
  "summary": "3 PASS, 1 WARN, 0 FAIL",
  "next_step": "Review storyboard spacing; otherwise ready for listen-through"
}
```

**Directus Integration (optional `--directus-log`):**
- POST to `prod_activity_log` with action="qa_validation", details=full report
- Updates `prod_modules.qa_status` and `prod_modules.qa_timestamp`
- Enables dashboard to show "Last QA run: 2 hours ago, all PASS"

---

### 6. requirements.txt

```
playwright==1.45.0
pytest==7.4.3
librosa==0.10.0
scipy==1.11.0
pillow==10.0.0
requests==2.31.0
jsonschema==4.20.0
pyyaml==6.0
```

---

### 7. README.md

**Usage:**
```bash
# Validate all artifacts for M1 at audio stage
python3 run_all.py --module M1 --stage audio

# Validate and log to Directus
python3 run_all.py --module M1 --stage listen_through --directus-log

# Save detailed report
python3 run_all.py --module M2 --stage phase_a_json --output qa_m2_report.json

# List all validators available
python3 run_all.py --list-validators
```

**Troubleshooting:**
- Playwright not installed: `pip install -r requirements.txt`
- Module not found: Check `--module` spelling; Directus must have module registered
- Stage mismatch: Validator checks module's current_stage in Directus; if mismatch, reports error + suggests correct stage

---

## Pipeline Integration

### When Does QA Run?

1. **Automatic after phase-b-writer:** Phase B script saved → Claude runs `validate_phase_b.py` immediately → flags any structural issues before audio production
2. **Automatic after module-json-builder:** JSON assembled → Claude runs `validate_module_json.py` immediately → guardrail check, report findings
3. **Manual before listen-through gate:** Kim is about to approve audio for a module → Claude runs full `run_all.py --stage listen_through` to ensure all artifacts pass before Kim's review
4. **On-demand:** Kim can request QA on any module at any stage via dashboard or chat ("Run QA on M2")

### Directus Updates

QA validators **do not modify** Directus state — they only report. The `run_all.py --directus-log` option logs results to activity_log for transparency. This keeps validation read-only and prevents accidental state corruption.

### Output to Kim

Summary report always prints to stdout. Full JSON report saved optionally (`--output`). If using `--directus-log`, Kim can see results in the dashboard activity timeline.

---

## Test Coverage by Stage

| Stage | Validators Run | Blocking? |
|-------|---|---|
| phase_b | validate_phase_b.py | No (flags only) |
| phase_a_json | validate_module_json.py | No (flags only) |
| audio | validate_audio.py | No (flags only) |
| listen_through | all + validate_storyboard.py | **Yes** — blocks Kim's approval gate |

---

## Scope Exclusions

**Not in this QA suite:**
- Unit tests for Python builders (that's separate; use pytest on each builder)
- End-to-end app testing (storyboard rendering is the closest we get)
- Video file validation (video-producer handles its own checks; too expensive to re-validate)
- TTS voice quality (audio-producer handles voice audition separately)

**Rationale:** QA suite focuses on **artifact integrity and schema compliance**, not creative quality. Creative approval is Kim's domain (phase-b-writer, storyboard-producer, audio-producer all include Kim review gates). QA is the safety net that catches mechanical errors.

---

## Example Run

```bash
$ python3 qa/run_all.py --module M1 --stage listen_through --directus-log

=== MindfulNest QA Validation Suite ===
Module: M1 (bodysensing_magic_hands)
Stage: listen_through
Timestamp: 2026-04-14T17:45:23Z

Running validators...

[1/4] validate_phase_b.py
  File: Production/M1_phase_b_script_v3.md
  Status: PASS (8 cue markers, 240s duration)
  
[2/4] validate_module_json.py
  File: module_M1_config.json
  Status: PASS (26/26 fields, Q1-Q19 all pass)
  
[3/4] validate_audio.py
  File: Production/Event_1/m1_phase_b_complete_mix.mp3
  Status: PASS (242s duration, -2.1dB peak, mono)
  
[4/4] validate_storyboard.py
  File: Production/Event_1/storyboard_M1_v13.html
  Status: PASS (11/11 images render, drag-drop works, export OK)

=== SUMMARY ===
Overall: PASS (4/4 validators, 0 warnings)
Ready for listen-through approval gate.

Logged to Directus activity_log.
```

---

## Files Created / Modified

- **New:** `Production/tools/qa/validate_phase_b.py`
- **New:** `Production/tools/qa/validate_module_json.py`
- **New:** `Production/tools/qa/validate_audio.py`
- **New:** `Production/tools/qa/validate_storyboard.py`
- **New:** `Production/tools/qa/run_all.py`
- **New:** `Production/tools/qa/requirements.txt`
- **New:** `Production/tools/qa/README.md`

All tools register themselves in the `Tool Persistence Checklist` (reference_tool_persistence_checklist.md).

---

## Next Steps

1. Create `/qa/` directory structure
2. Implement each validator module (start with validate_module_json.py — highest confidence in schema)
3. Test run_all.py against existing M1 artifacts (should PASS)
4. Integrate with pipeline.py to auto-trigger after phase-b-writer, module-json-builder, audio-producer
5. Verify Directus logging works with sample run
6. Document in README with examples + troubleshooting

**Estimated implementation time:** 4–6 hours (Python validation) + 2–3 hours (Playwright setup + storyboard testing) = ~8 hours total.
