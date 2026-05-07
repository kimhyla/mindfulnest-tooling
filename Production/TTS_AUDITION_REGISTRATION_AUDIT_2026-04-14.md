# MindfulNest TTS Audition Tool Registration Audit
**Generated:** April 14, 2026  
**Scope:** Complete file-by-file comparison: Production disk files vs. Directus prod_visual_assets dashboard

---

## EXECUTIVE SUMMARY

### TTS Audio Content
- ✅ **10/10** story dialogue MP3s are registered in Directus `prod_visual_assets`
- ✅ All core TTS voice lines in `Production/Event_1/story_scene_tts_v2/` map to registered Directus records
- Status: **COMPLETE**

### Production Tools (HTML/Python)
- ❌ **6 of 7** TTS audition HTML review tools are **UNREGISTERED**
- ✅ Only `tts_audition_player_v3.html` is registered
- **CRITICAL:** The current tool `review_sheet_v7_final.html` is NOT in Directus
- Status: **NEEDS ATTENTION**

### Configuration & Test Assets
- ❓ `tts_audition_config.json` exists on disk but tracking status is unclear
- ❓ 5 gong candidate MP3s are not tracked (likely intentional as test files)

---

## DETAILED BREAKDOWN

### 1. Directus TTS Audio Records (10 registered)

All 10 records located in `prod_visual_assets` with `asset_type=tts_audio`:

| ID | Filename | Status | Event | Shot | Filepath |
|----|----------|--------|-------|------|----------|
| 16 | line_06_guide_bird_demo.mp3 | approved | 1 | 6 | Production/Event_1/story_scene_tts_v2/ |
| 17 | line_07_tessa.mp3 | approved | 1 | 7 | Production/Event_1/story_scene_tts_v2/ |
| [+8 more] | lines 02-05, 08-11 | approved | 1 | 2-11 | Production/Event_1/story_scene_tts_v2/ |

**Status:** All approved as of April 13, 2026

---

### 2. Directus Production Tool Records (3 registered)

All 3 records in `prod_visual_assets` with `asset_type=production_tool`:

| ID | Filename | Status |
|----|----------|--------|
| [X] | animation_review_M1E1_v1.html | approved |
| [X] | build_animation_review.py | approved |
| [X] | tts_audition_player_v3.html | approved |

**Status:** Only v3 of the TTS audition HTML is registered

---

### 3. Disk Files: Story Scene TTS (Production/Event_1/story_scene_tts_v2/)

**Core Dialogue Files (Base, No Trim):**
```
✅ line_02_guide_bird.mp3          → REGISTERED
✅ line_03_tessa.mp3               → REGISTERED
✅ line_04_guide_bird.mp3          → REGISTERED
✅ line_05_tessa.mp3               → REGISTERED
✅ line_06_guide_bird_demo.mp3     → REGISTERED
✅ line_07_tessa.mp3               → REGISTERED
✅ line_08_guide_bird.mp3          → REGISTERED
✅ line_09_tessa_demo.mp3          → REGISTERED
✅ line_10_guide_bird_demo.mp3     → REGISTERED
✅ line_11_guide_bird_demo.mp3     → REGISTERED
```

**Trimmed Variants (5s clips):**
```
- line_02_guide_bird_trim5s.mp3           → NOT TRACKED (intentional)
- line_03_tessa_trim5s.mp3                → NOT TRACKED (intentional)
- [8 more trim variants]
```

**Status:** ✅ 100% core dialogue files registered; trim variants intentionally untracked

---

### 4. Disk Files: Root Event_1 Directory (Production/Event_1/)

**Duplicate Copies:**
```
✅ line_02_guide_bird.mp3          → REGISTERED (also in story_scene_tts_v2/)
✅ line_03_tessa.mp3               → REGISTERED (also in story_scene_tts_v2/)
✅ line_04_guide_bird.mp3          → REGISTERED (also in story_scene_tts_v2/)
✅ line_05_tessa.mp3               → REGISTERED (also in story_scene_tts_v2/)
✅ line_06_guide_bird_demo.mp3     → REGISTERED (also in story_scene_tts_v2/)
✅ line_07_tessa.mp3               → REGISTERED (also in story_scene_tts_v2/)
✅ line_08_guide_bird.mp3          → REGISTERED (also in story_scene_tts_v2/)
✅ line_09_tessa_demo.mp3          → REGISTERED (also in story_scene_tts_v2/)
✅ line_10_guide_bird_demo.mp3     → REGISTERED (also in story_scene_tts_v2/)
✅ line_11_guide_bird_demo.mp3     → REGISTERED (also in story_scene_tts_v2/)

❌ line_04_guide_bird (1).mp3      → NOT REGISTERED (corrupted filename: space + parenthesis)
```

**Status:** ❌ 1 unregistered duplicate with malformed name (appears to be OS auto-duplicate)

---

### 5. Disk Files: TTS Audition HTML Tools (Production/Event_1/)

**UNREGISTERED (6 files):**
```
❌ tts_audition_player_v2.html        (v2 — older version)
❌ tts_audition_player_v3_rebuilt.html (v3 rebuilt — intermediate build)
❌ review_sheet_v4.html               (v4 — older batch review)
❌ review_sheet_v5.html               (v5 — older batch review)
❌ review_sheet_v6.html               (v6 — older batch review)
❌ review_sheet_v7_final.html         (v7 final — **CURRENT TOOL**)
```

**REGISTERED (1 file):**
```
✅ tts_audition_player_v3.html        (v3 — listed in Directus production_tool)
```

**Status:** 🔴 **CRITICAL** — Current tool `review_sheet_v7_final.html` is NOT registered. Only stale v3 is in Directus.

---

### 6. Disk Files: TTS Audition Config

**Config File:**
```
❓ tts_audition_config.json            → Not tracked separately
```

**Status:** Unclear whether config should be tracked independently or embedded in tool

---

### 7. Disk Files: Gong Candidates (Production/Event_1/)

**Audio Test Files:**
```
❓ gong_candidate_1.mp3              → Not tracked (exploratory/test)
❓ gong_candidate_2.mp3              → Not tracked (exploratory/test)
❓ gong_candidate_3.mp3              → Not tracked (exploratory/test)
❓ gong_candidate_4.mp3              → Not tracked (exploratory/test)
❓ gong_candidate_5.mp3              → Not tracked (exploratory/test)
```

**Status:** Likely intentional (test assets); not needed in production registry

---

## CRITICAL ISSUES

### ISSUE #1: TTS Audition HTML Tools Mostly Unregistered
**SEVERITY:** 🔴 HIGH

**Problem:**
- 6 of 7 TTS audition HTML tools are missing from `prod_visual_assets`
- The **CURRENT tool** `review_sheet_v7_final.html` is NOT registered
- Only `tts_audition_player_v3.html` is in Directus (possibly stale)

**Impact:**
- No audit trail for which HTML review tool was approved by Kim
- Unclear which version is the canonical source of truth
- Build reproducibility is compromised
- Cannot track which version Kim used for approvals

**Recommendation:**
1. Identify the current active TTS audition tool (is it `review_sheet_v7_final.html`?)
2. Register the CURRENT tool in Directus as `asset_type=production_tool`
3. Clean up / remove older versions (v2, v4, v5, v6, _rebuilt)
4. Update or replace the v3 Directus record with the current version

---

### ISSUE #2: Corrupted Filename in Root Event_1
**SEVERITY:** 🟡 MEDIUM

**Problem:**
- `line_04_guide_bird (1).mp3` is a malformed duplicate
- Filename contains space + parenthesis (filesystem naming error)
- Not registered in Directus

**Impact:**
- Potential confusion about which version is canonical
- File appears to be an auto-generated copy created by macOS Finder when a file is duplicated
- Clutter in Event_1 root directory

**Recommendation:**
1. Verify if this is an accidental duplicate created by Finder
2. Delete this file; keep only `Production/Event_1/story_scene_tts_v2/line_04_guide_bird.mp3`
3. Or, if it's intentional, rename to a valid filename and register in Directus

---

### ISSUE #3: TTS Config JSON Not Tracked
**SEVERITY:** 🟡 LOW

**Problem:**
- `tts_audition_config.json` exists on disk but is not in `prod_visual_assets`

**Impact:**
- Config file is not versioned or approved in dashboard
- No audit trail for config changes
- Unclear if changes to config are reflected in tool behavior

**Recommendation:**
1. Determine if config should be tracked separately or embedded in HTML tool
2. If separate: Register as `asset_type=config` (similar pattern exists for one record)
3. If embedded: Confirm and document that config is internal to the HTML tool

---

## REGISTRATION SUMMARY TABLE

| Asset Category | Disk Count | Registered | Missing | % Registered |
|---|---|---|---|---|
| Story TTS v2 (base files) | 10 | 10 | 0 | **100%** ✅ |
| Story TTS v2 (trim variants) | 10 | 0 | 10 | 0% (intentional) |
| Root Event_1 duplicates | 11 | 10 | 1 | 90% ❌ |
| TTS Audition HTML tools | 7 | 1 | 6 | **14%** ❌ |
| TTS Config JSON | 1 | 0 | 1 | 0% ❓ |
| Gong candidates | 5 | 0 | 5 | 0% (intentional) |
| **TOTAL** | **44** | **21** | **23** | **48%** |

**Note:** Overall registration is 48% because many files are temporary/intermediate builds, old versions, and test assets. The **critical issue is the HTML tools at 14%** — essential production tools should be 100% registered.

---

## RECOMMENDATIONS

### Immediate Actions (This Week)
1. **Identify current TTS audition tool** — Is `review_sheet_v7_final.html` the active tool?
2. **Register the current tool in Directus** with correct version number and approval status
3. **Delete or archive older versions** (v2, v4, v5, v6, _rebuilt)
4. **Delete `line_04_guide_bird (1).mp3`** as an accidental OS duplicate
5. **Clarify tts_audition_config.json** — Register separately or confirm it's embedded

### Medium-term Actions (Next Sprint)
6. **Update Directus production_tool collection** to include all current production tools
7. **Add "Tool Version" field** to track active versions across tool types
8. **Implement approval workflow** for production tool versions (similar to audio assets)
9. **Update build scripts** to auto-register HTML tools on generation

### Long-term Actions (Q2 2026)
10. **Establish production tool versioning convention** — Consistent numbering across all tools
11. **Create tool deprecation policy** — When to archive vs. delete old versions
12. **Implement tool lineage tracking** — Track which tool versions were used for which module approvals
13. **Add tool audit logs to activity_log** — Track who reviewed/approved which tool versions

---

## APPENDIX: File Inventory by Location

### Production/Event_1/story_scene_tts_v2/
- 10 base dialogue MP3s (all registered)
- 10 trimmed variants (not tracked)

### Production/Event_1/ (root)
- 11 duplicate copies of dialogue MP3s
- 7 TTS audition HTML tools (6 unregistered)
- 1 TTS audition config JSON
- 5 gong candidate MP3s
- 4 phase B complete mix MP3s (not tracked)
- 13 voice stem MP3s (not tracked)
- Plus: 50+ other production files (stills, videos, test files)

### Total MP3 files in Production directory: 202
- 10 registered as tts_audio
- ~20 registered as audio_clip (animation, phase B, etc.)
- ~172 untracked (intermediate versions, test files, stems)

---

**End of Audit Report**  
*For questions or clarifications, review the detailed tables above or check Directus prod_visual_assets directly.*
