# Tech Spec: Stitch Export Operator Closure v1

**Code:** `STITCH_EXPORT_OPERATOR_CLOSURE_V1`  
**Status:** Shipped  
**Scope:** Beat Gen Send to Stitcher — readiness authority, preflight manifest, UI parity, CI gates  
**Related:** `KLING_STITCH_READINESS_V1`, `STORYBOARD_AUTHORITY_REGISTRY_V1`

## Problem

1. Split readiness predicates — nav, Send button, and option tiles used different heuristics.
2. Generic export errors — `BEATS_NOT_APPROVED` did not name the beat or fix.
3. No preflight — operator discovered blockers only after clicking Send.

Layer B (trim/magic/TTS clip resolution) is unchanged — `prepare_beats_for_stitch_export` + `resolve_beat_stitch_export_clip_path`.

## Architecture

- **Layer A (this spec):** `beat_kling_stitch_export_ready` → `_derived` on session GET; preflight manifest; auto preflight on Send (silent if OK).
- **Layer B (unchanged):** materialize trim/magic/TTS at concat time.

## Deliverables

| Phase | Deliverable |
|-------|-------------|
| 1 | `_derived.stitch_export_ready`, block_label, fix_instruction; option tile uses `stitchExportReady` |
| 2 | `bg_stitch_export_preflight.py`, GET `/api/bg/export-to-stitcher-preflight`, client gate, audit jsonl |
| 3 | Durability scripts, pytest, vitest, authority registry gates |

## Git / deploy invariant

All events share one `Production/tools` tree on Dropbox. Deploy rsyncs **from git → Dropbox**. Runtime code must exist in `mindfulnest-tooling` or the next clean deploy will revert operator fixes for every event.
