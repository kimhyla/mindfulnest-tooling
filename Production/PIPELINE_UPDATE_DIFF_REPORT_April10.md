# Pipeline Documentation Update — Diff Report
**Date:** April 10, 2026
**Trigger:** Kim confirmed Pixar 3D visual style + research findings on Seedance 2.0, Kling 3.0, FLUX Kontext, keyframe workflows

---

## Documents Modified (3)

### Document 1: `video_pipeline/ELEVENLABS_VIDEO_PRODUCTION_HANDOFF_April5_2026.md`
**Backup:** `ELEVENLABS_VIDEO_PRODUCTION_HANDOFF_April5_2026_backup_20260410.md`
**Edits applied:** 11 (9 original + 2 validator-caught fixes)

| ID | Section | What Changed |
|----|---------|-------------|
| A1 | STYLE NOTES | Painterly → Pixar 3D as current style. Style history preserved. LoRA noted as unnecessary. |
| A2 | PROVEN VIDEO PIPELINE | Entire pipeline table replaced: Runway Gen-4 → FLUX Kontext, Seedance 1.5 → Seedance 2.0/Kling 3.0/Pika Pikaframes. Added keyframe, video extension, and clip chaining capabilities. |
| A3 | API Endpoints | New endpoints for FLUX Kontext, Seedance 2.0, Kling 3.0, Pika. Old Runway/Seedance 1.5 endpoints moved to archived section. |
| A4 | Lip Sync section | Kling 3.0 reclassified from "rejected" to "adopted for animation (not lip sync)." |
| A5 | Visual Assets header | "Painterly Style" → "Pixar 3D Style" |
| A6 | Character Images | Added note about 382+ images in Production/ subfolders as primary refs. |
| A7 | Phase 3 workflow | Updated validation steps to use FLUX Kontext + Seedance 2.0 + video extension testing. |
| A8 | DO NOT WASTE TIME ON | LoRA training marked obsolete. |
| A9 | API Keys table | Updated for Replicate, WaveSpeed, Kling endpoints. |
| V1 | Opening paragraph (line 5) | **Validator fix:** Painterly described as current → updated to say "superseded by Pixar 3D." |
| V2 | Cost estimate (line 25) | **Validator fix:** ~$0.25-0.35 → ~$0.38-0.48 (corrected math: $0.08 FLUX + $0.15-0.25 animation + $0.15 LipSync). |

### Document 2: `Production/MODULE_PRODUCTION_MASTER_PLAN_v2_0.md`
**Backup:** `MODULE_PRODUCTION_MASTER_PLAN_v2_0_backup_20260410.md`
**Edits applied:** 4

| ID | Section | What Changed |
|----|---------|-------------|
| B1 | Stage 9 (full section) | "AUDIO PRODUCTION" → "AUDIO + VIDEO PRODUCTION." Added 9B: Video Pipeline subsection with FLUX Kontext, Seedance/Kling, ByteDance LipSync, and video quality checks. |
| B2 | Pipeline summary (ASCII) | Stage 9 line updated to include video tools. |
| B3 | Batch workflow table | "AUDIO" session → "AUDIO + VIDEO" session, time updated to ~10 min/module. |
| B4 | Key Principle 8 | "Audio is automated" → "Audio and video are automated." Added video pipeline tools and "watch-through" to Kim's quality gate. |

### Document 3: `Canon/ARC_PRODUCTION_BIBLE_v2_10.md`
**Backup:** `ARC_PRODUCTION_BIBLE_v2_10_backup_20260410.md`
**Edits applied:** 2 (1 original + 1 validator-caught fix)

| ID | Section | What Changed |
|----|---------|-------------|
| C1 | §1.1a (after narrative events paragraph) | NEW paragraph inserted: "Visual Production Pipeline (Updated April 10, 2026)" — describes 3-stage pipeline, keyframe workflow, video extension, costs, and reference to Handoff doc. |
| V3 | Cost in C1 paragraph | **Validator fix:** ~$0.25-0.35 → ~$0.38-0.48 (matching corrected math from V2). |

---

## Validation Results

| Document | Editing Agent | Self-Verification | Independent Validator | Fixes Applied |
|----------|:---:|:---:|:---:|:---:|
| Handoff (Doc 1) | ✅ 9/9 | ✅ CLEAN | ❌ 2 issues found → FIXED | +2 fixes (V1, V2) |
| Master Plan (Doc 2) | ✅ 4/4 | ✅ CLEAN | ✅ PASS | None needed |
| Arc Prod Bible (Doc 3) | ✅ 1/1 | ✅ CLEAN | ✅ PASS | +1 fix (V3, cost) |

**Final status: ALL 3 DOCUMENTS PASS** after validator-driven corrections.

---

## Key Decisions Documented

1. **Visual style: Pixar 3D** (supersedes painterly, April 10 2026)
2. **FLUX Kontext replaces Runway Gen-4** for scene still generation ($0.08/img)
3. **Seedance 2.0 / Kling 3.0 replace Seedance 1.5** for animation
4. **Keyframe-to-keyframe generation** now a core capability
5. **Video extension / clip chaining** enables long continuous sequences
6. **LoRA training: OBSOLETE** — 382+ existing character images sufficient
7. **Cost per dialogue scene: ~$0.38-0.48** (corrected from earlier $0.26 estimate)

---

*Backups of all three original files are in their respective folders with `_backup_20260410` suffix.*
