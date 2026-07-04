# Magic Source Binding Contract v1

**Code:** `MAGIC_SOURCE_BINDING_V1`  
**Status:** Implementing  
**Scope:** Beat Gen + Storyboard magic-on-still / magic-on-video (all events)

---

## Problem

Magic composites were stored **per beat** without remembering **which still or video** they were drawn on. When the active O3 clip changed (harvest, slot select, import), orphan magic could hijack O3 tile playback and stitch export.

Event_3 `bg_arc1_event3_post_beat_01`: agent smoke test left `magic_video_path` from June 2026; harvest landed on `g1_delivery.mp4` (8.1s) but UI played 4.5s orphan magic.

---

## Product rules (Kim)

1. Magic persists on the **exact still/video it was layered on**.
2. Switch tabs or O3 containers away and back → magic returns when that same file is active again.
3. Magic clears only when:
   - operator **redoes** magic (explicit replace), or
   - operator **replaces** the underlying still/video (new file in that slot / new image).
4. O3 option tiles **always play the Kling/harvest clip** — never silent magic override.
5. Magic preview uses **Preview magic** buttons only, gated to the active bound source.
6. Agent/curl smoke tests must not write production canonical magic without explicit intent.

---

## 3×3 debate (spec validation)

|  | **Simplicity** | **Blast radius** | **Kim UX truth** |
|--|----------------|------------------|------------------|
| **A — Full binding (this spec)** | One predicate + two source fields; no special-case harvest/POV | Touches preview, stitch export, write path, enrich API | Matches “magic on this file” exactly |
| **B — Clear magic on any O3 change** | Simpler code | Low | **Wrong** — magic lost when clicking to container 2 and back |
| **C — O3 tile decouple only** | Smallest diff | Misses stitch export orphans | Fixes preview only; Send to Stitcher could still export wrong clip |

|  | **Durability** | **Agent safety** | **Legacy beats** |
|--|----------------|------------------|------------------|
| **A — Full binding** | Source path in sidecar + partition; preserved in merge | `production_intent` gate on write | No source → magic **inactive** (safe); explicit clear for beat_01 |
| **B — Clear on change** | Easy to regress multi-slot magic | Unchanged | Wipes valid magic on slot switch |
| **C — UI only** | Server export still wrong | Unchanged | Orphans remain “canonical” server-side |

|  | **Testability** | **Deploy risk** | **Verdict** |
|--|-----------------|-----------------|-------------|
| **A** | Matrix: bound/unbound, slot switch, replace, legacy | Python + JS bundle; fleet sync | **Ship** |
| **B** | Easy | Low | Reject (UX) |
| **C** | Partial | UI-only false greens | Reject (incomplete) |

**Consensus:** Ship **A** with **O3 tile override removed** (Option 2). Not a separate “Option 5 project” — minimal binding fields only.

---

## Schema

New durable fields (partition + BG sidecar via `_MAGIC_SYNC_FIELDS`):

| Field | Set when | Used for |
|-------|----------|----------|
| `magic_video_source_path` | `handle_magic_video` success | Bind video magic to resolved FFmpeg source (trim-aware) |
| `magic_still_source_path` | `handle_magic_still` success | Bind still magic to source image path |

Cleared with magic via `_MAGIC_VIDEO_CLEAR_FIELDS` / `_MAGIC_STILL_CLEAR_FIELDS` / image assign.

---

## Core predicate (server)

```python
magic_video_applies_to_path(beat, target_video_path, event_dir) -> bool
magic_video_applies_to_active(beat, event_dir) -> bool  # vs kling_o3_video_path
magic_still_applies_to_active(beat, event_dir) -> bool
resolve_active_magic_layer(beat, event_dir)  # returns still|video|null; null if bound source ≠ active
```

**Legacy:** `magic_video_path` present but **no** `magic_video_source_path` → **does not apply** (orphan-safe).

---

## Invalidation (replace, not slot switch)

| Event | Behavior |
|-------|----------|
| Select different O3 container | Magic metadata **kept**; predicate false until bound file active again |
| Import/replace video at slot (new path) | Clear video magic if bound to **replaced** path |
| Assign new storyboard image | Clear all magic (existing) |
| `clear_magic_video` / `clear_magic_still` | Clear fields (existing still + new video) |
| Redo magic | New write replaces paths + binding |

---

## Playback surfaces

| Surface | Rule |
|---------|------|
| O3 option tile | **Always** canonical O3 / playback_resolve URL — **no** magic override |
| Preview magic (still/video) buttons | Only enabled when `magic_*_applies_to_active` |
| Send to Stitcher / export | `resolve_beat_stitch_export_clip_path` uses magic only when predicate true |

---

## Agent smoke gate

`POST /api/storyboard/magic_video|magic_still`:

- With `production_intent: true` (path_picker UI): normal `write_magic_delivery`.
- Without: render to `{event_dir}/_magic_smoke/`, **no** partition/sidecar write; response `{ smoke: true }`.

---

## Remediation

Event_3 `bg_arc1_event3_post_beat_01`: `POST /api/storyboard/clear_magic_video` after deploy.

---

## Acceptance tests

1. Beat with legacy magic, no source → O3 tile duration = active clip; export = O3; preview magic disabled.
2. Magic on g3, active g1 → no magic preview; select g3 → preview magic works.
3. Magic on g3, import replaces g3 path → magic cleared.
4. Smoke POST without `production_intent` → no `magic_video_path` in session-state.
5. Event_3 post beat_01 → 8.1s harvest audible in O3 tile after clear + hard refresh.

---

## Blast radius

| Area | Risk | Mitigation |
|------|------|------------|
| Intro/resolution beats with valid magic | Medium | Binding set on next redo; legacy inactive until re-magic |
| StoryboardTab preview | Low | Same predicate via enrich |
| Stitch export | Medium | Predicate gates export path |
| path_picker | Low | Adds `production_intent: true` |
| Agent scripts | Low | Smoke-only unless intent flag |

---

## Deploy + QA checklist

- [ ] pytest `test_magic_source_binding_v1.py` + `test_magic_active_layer.py`
- [ ] Commit before deploy
- [ ] `deploy_storyboard_v59.sh --event Event_3` + fleet build-sha parity
- [ ] Restart `:5113`; curl session-state beat_01
- [ ] ffprobe O3 tile URL duration ≈ 8.1s
- [ ] Multipass deploy proof x2
