# Technical Spec: Storyboard v59 — Session 5.5a1 (Schema Migration + Cache Fix + LD Housekeeping)
**Date:** 2026-05-03
**Produced by:** medium-rigor compact spec (no agent debate; relies on Cursor v4 architectural approval of Option B)
**Status:** Awaiting Cursor v5 cross-review on this execution spec specifically
**Supersedes:** Nothing (this is a foundation session within the v3.1 spec sequence)

---

## 1. Task

S5.5a1 is the foundation session for Option B (video partitioning within events). It executes three things:

1. **Schema migration** — `Production/Event_*/production_state.json` files lift their flat fields into a `videos: {intro, phase_a, phase_b, win}` partition structure
2. **State helpers** — new methods on `StateManager` that read/write the partitioned state by `video_role`
3. **Cross-event cache leak fix** — clear `_image_overrides` and `_pending_override_keys` in `_handle_event_load` (Cursor v4 found this hidden hole — same bug class as the S5 StateManager fix)

Plus housekeeping:
4. PATCH 4 stale LDs to set their `superseded_by_id` FKs (LD-426, LD-431, LD-428, LD-429)
5. Add SUPERSEDED banner to `Production/tools/GPT_STILLS_TECH_SPEC_v1.md`
6. Verify gpt-4o Responses API still active (one curl probe)

S5.5a1 is FOUNDATION only — no handler refactor, no scope token expansion, no UI changes. Those are S5.5a2 / S5.5b / S5.5c.

---

## 2. Governing Decisions

**Locked decisions this spec respects:**

| LD | Why it constrains S5.5a1 |
|---|---|
| LD-456 SCOPE_VALIDATION_V1 | Existing `_assert_event_scope` pattern stays; S5.5a1 doesn't extend it (that's S5.5a2) |
| LD-458 EVENT_LOAD_GENERATION_LOCK_V1 | The `_handle_event_load` swap mechanism is being EXTENDED with cache clears under the same lock |
| LD-460 ASYNC_JOB_GENERATION_PIN_V1 | Existing async pin pattern stays; will be extended in S5.5a2 |
| LD-461 SCOPE_BODY_HELPER_V1 | `_scope_body` helper already exists; will be extended in S5.5a2 |
| LD-440 GPT_IMAGE_2_PRIMARY_MODEL_V1 | Locks gpt-image-2 as primary; LD-426 housekeeping reflects this |
| Rule 35 (Directus schema verification) | All Directus PATCHes use `try_post_or_queue` and consult `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` |
| Rule 19 (no shortcuts) | Schema migration MUST snapshot first; rollback path must work |
| Rule 27 (delete obsolete workarounds) | TECH_SPEC v1 stays on disk with SUPERSEDED banner — not deleted (other docs may reference it) |
| Rule 36 (patch invariant persistence) | Not applicable — no JS patches in this session |

**New LDs to register during S5.5a1:**

- `BG_VIDEO_PARTITION_V1` — locks the `videos: {intro, phase_a, phase_b, win}` schema as the canonical state.json structure for v59
- `VIDEO_ROLE_PER_REQUEST_V1` — locks the stateless-per-request `video_role` pattern (no server-side `active_video` cache, no `/api/video/load` endpoint; client maintains `activeVideo` signal locally and includes `scope_video_role` on every mutating request — the design Cursor v4 specifically validated)
- `IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1` — locks the cache-clear fix for `_image_overrides` + `_pending_override_keys` on event swap

---

## 3. Approach

### 3.1 Schema migration design

`Production/Event_*/production_state.json` currently has a flat structure:

**BEFORE (current flat schema):**
```json
{
  "event_id": "Event_1",
  "version": "v1",
  "beats": {
    "beat_01": {"text": "...", "speaker": "Tessa", ...},
    ...
  },
  "image_overrides": {"beat_01": "image_key_xyz"},
  "phase_a_script": "...",
  "phase_a_stitched_file": "phase_a_stitched_M1_v1.mp4",
  "phase_a_lipsync_file": "phase_a_lipsync_M1_v1.mp4",
  "phase_a_status": "draft",
  "phase_b_script": "...",
  "phase_b_lipsync_file": "phase_b_lipsync_M1_v1.mp4",
  "phase_b_watercolor_cues_json": [...],
  "phase_b_status": "draft",
  "created_at": "2026-04-22T...",
  "updated_at": "2026-04-22T..."
}
```

**AFTER (videos partition):**
```json
{
  "event_id": "Event_1",
  "version": "v2",
  "videos": {
    "intro": {
      "video_role": "intro",
      "video_label": null,
      "beats": {"beat_01": {...}, ...},
      "image_overrides": {"beat_01": "image_key_xyz"}
    },
    "phase_a": {
      "video_role": "phase_a",
      "phase_a_script": "...",
      "phase_a_stitched_file": "phase_a_stitched_M1_v1.mp4",
      "phase_a_lipsync_file": "phase_a_lipsync_M1_v1.mp4",
      "phase_a_status": "draft"
    },
    "phase_b": {
      "video_role": "phase_b",
      "phase_b_script": "...",
      "phase_b_lipsync_file": "phase_b_lipsync_M1_v1.mp4",
      "phase_b_watercolor_cues_json": [...],
      "phase_b_status": "draft"
    },
    "win": {
      "video_role": "win",
      "video_label": null,
      "beats": {},
      "image_overrides": {}
    }
  },
  "active_video": "intro",
  "created_at": "2026-04-22T...",
  "updated_at": "2026-05-03T..."
}
```

**Lift rules:**
- `beats` → `videos.intro.beats` (default — current behavior IS intro per architecture)
- `image_overrides` → `videos.intro.image_overrides`
- `phase_a_*` fields → `videos.phase_a.{field_name}`
- `phase_b_*` fields → `videos.phase_b.{field_name}`
- Top-level metadata (event_id, version, created_at, updated_at) stays at top
- New empty `videos.win` partition added (placeholder for future win/resolution work)
- New `active_video: "intro"` field added (client-side default; NOT a server-cached value per VIDEO_ROLE_PER_REQUEST_V1)
- `version` bumps from `"v1"` to `"v2"` for migration detection

**Idempotency:** the migration script detects already-migrated files via `state.get("version") == "v2"` and skips.

**Migration script:** `Production/scripts/migrate_state_to_videos_partition.py`

**Per-file safety procedure:**
1. Snapshot to `Production/Event_<N>/.backups/state/<TS>_pre_videos_migration.json` (existing snapshot directory)
2. Read flat state.json
3. Construct new partitioned dict per lift rules above
4. Validate via JSON schema check (write a small JSON Schema validator in the script)
5. Atomic write via `Production/lib/atomic_json_write.py` (tmp+rename)
6. Verify post-write read returns the expected `version: "v2"` + `videos` key
7. If validation fails at any step: restore from snapshot, halt entire migration, exit non-zero

**Post-migration validation:** script prints `OK <event>: migrated, version=v2, videos=[intro, phase_a, phase_b, win]` per file. Exit 0 only if all events succeed.

### 3.2 State helpers

Add these methods to the `StateManager` class in `production_server.py` (around line 811 where `StateManager.__init__` lives):

```python
def get_beats(self, video_role: str) -> dict:
    """Returns the beats dict for the given video_role partition.
    
    Reads fresh from state.json on every call (no caching, per the lesson
    from S5's StateManager state_path bug).
    """
    state = self.read_state()
    videos = state.get("videos", {})
    if video_role not in videos:
        return {}  # Empty partition; caller decides if that's OK
    return videos[video_role].get("beats", {})

def mutate_video_state(self, video_role: str, mutator_fn: callable) -> dict:
    """Atomic mutation of a single video_role partition.
    
    mutator_fn receives the partition dict and mutates it in place.
    Wraps the existing mutate_state pattern but scopes the mutation
    to one video partition.
    """
    def _wrapped_mutator(state):
        if "videos" not in state:
            state["videos"] = {}
        if video_role not in state["videos"]:
            state["videos"][video_role] = {"video_role": video_role, "beats": {}}
        mutator_fn(state["videos"][video_role])
        state["updated_at"] = datetime.utcnow().isoformat() + "Z"
    return self.mutate_state(_wrapped_mutator)

def list_videos(self) -> list:
    """Returns list of all video partitions in the current event.
    
    Each entry: {video_role, video_label, has_beats: bool, beat_count: int}
    """
    state = self.read_state()
    videos = state.get("videos", {})
    return [
        {
            "video_role": v.get("video_role", role),
            "video_label": v.get("video_label"),
            "has_beats": bool(v.get("beats")),
            "beat_count": len(v.get("beats", {}))
        }
        for role, v in videos.items()
    ]

def create_video(self, video_role: str, video_label: str = None) -> bool:
    """Adds a new video partition under the current event.
    
    Returns True if created, False if already existed.
    """
    if video_role not in {"intro", "phase_a", "phase_b", "win", "standalone"}:
        raise ValueError(f"Invalid video_role: {video_role!r}. Must be intro/phase_a/phase_b/win/standalone.")
    state = self.read_state()
    if "videos" not in state:
        state["videos"] = {}
    if video_role in state["videos"]:
        return False
    def _mutator(state):
        state["videos"][video_role] = {
            "video_role": video_role,
            "video_label": video_label,
            "beats": {} if video_role in {"intro", "win", "standalone"} else None,
            f"{video_role}_status": "draft" if video_role in {"phase_a", "phase_b"} else None
        }
    self.mutate_state(_mutator)
    return True

def validate_video_role(self, video_role: str) -> bool:
    """Returns True if video_role is a valid partition in current state."""
    if video_role not in {"intro", "phase_a", "phase_b", "win", "standalone"}:
        return False
    state = self.read_state()
    return video_role in state.get("videos", {})
```

These helpers don't replace `read_state()` / `mutate_state()` — they layer on top for video-partition-aware operations. The 30+ handlers that need to use these helpers get refactored in S5.5a2.

### 3.3 Cache fix in `_handle_event_load`

Per Cursor v4 finding: `_image_overrides` and `_pending_override_keys` are cleared in `_handle_storyboard_switch` (lines 4215-4218) but NOT in `_handle_event_load`. So switching events leaves Event_1's image overrides in memory, can serve to Event_2 requests.

**Fix in `_handle_event_load` (around line 5775):**

```python
# Inside the event_load_lock atomic block, alongside existing event_dir/state_path swap:

# Clear cross-event cache surfaces (Cursor v4 finding — same bug class as
# the S5 StateManager state_path fix; image_overrides was cleared in
# _handle_storyboard_switch but missed in _handle_event_load until now)
self.app._image_overrides = {}
self.app._pending_override_keys = set()
```

This goes inside the existing `event_load_lock` block, after the StateManager re-pointing (which the S5 fix already does atomically).

---

## 4. Implementation Steps

### Phase 0 — Preflight (mandatory)

1. Open `prod_preflight_reviews` row:
   - `task_type=architectural`
   - `claude_summary`: "S5.5a1 — schema migration to videos partition + StateManager helpers + image_overrides/pending_override_keys cache clear on event load + LD housekeeping. Architecture per Cursor v4 review on STORYBOARD_V59_SPEC_v3_1 + Option B confirmation. Foundation for S5.5a2/b/c."
   - References: preflight #193 (S5), #192 (S4), #191 (S3), #190 (S2), #189 (S1.5)
   - DO NOT re-run 4+4 advocate/counter — Cursor v4 cross-review IS the architectural review

### Phase A — LD housekeeping (do FIRST; no code changes; lowest risk)

2. PATCH 4 stale LDs via `Production/lib/directus.py::try_post_or_queue` (consult `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`):
   - LD-426 GPT_STILLS_ENDPOINT_V1: set `superseded_by_id=440`, `status="superseded"`, append note "Superseded by LD-440 GPT_IMAGE_2_PRIMARY_MODEL_V1 (2026-04-28). Code path moved from gpt-image-1 to gpt-image-2."
   - LD-431 BEAT_GENERATOR_RESPONSES_API_WIRING_PENDING_V1: set `superseded_by_id=440`, `status="superseded"`, append note "Superseded by LD-440. Wiring complete; gpt-4o demoted to fallback per A/B test."
   - LD-428 OPENAI_ORG_VERIFICATION_SUBMITTED_V1: set `superseded_by_id=430`, `status="superseded"`, append note "Superseded by LD-430 OPENAI_ORG_VERIFICATION_CLEARED_V1 (2026-04-27 ~13:13 UTC, HTTP 200 confirmed)."
   - LD-429 GPT_STILLS_RESPONSES_API_PRIMARY_V1: set `superseded_by_id=440`, `status="superseded"`, append note "Superseded by LD-440. gpt-image-2 is primary; gpt-4o demoted to fallback per Kim's A/B verdict."

3. Add SUPERSEDED banner to `Production/tools/GPT_STILLS_TECH_SPEC_v1.md`:
   - Insert at top of doc (before existing content):
     ```markdown
     > ⚠️ **SUPERSEDED 2026-05-03** — This spec describes the original gpt-image-1 prompt with `_GPT_SPECIES_ANCHOR` text descriptions. The current production architecture is:
     > - **Model:** `gpt-image-2` per LD-440 (was gpt-image-1 in this doc)
     > - **Prompt:** image-led ~380-char per LD-439 (was 1152-char species-anchor in this doc)
     > - **Code source of truth:** `Production/tools/beat_generator.py:934-947` for `build_gpt_still_prompt()`
     > Refer to LD-439 + LD-440 for current architecture; this doc is retained for historical context only.
     ```

### Phase B — Cache fix (small, surgical, low risk)

4. Edit `production_server.py:_handle_event_load` (around line 5775) inside the existing `event_load_lock` block. Add the 2-line cache clear per §3.3.

5. Verify via py_compile: `python3 -m py_compile Production/tools/production_server.py`

### Phase C — State helpers (no breaking changes; additive only)

6. Add the 5 helper methods to `StateManager` class per §3.2 (around line 811). All methods are NEW; no existing methods touched.

7. Verify via py_compile.

### Phase D — Schema migration script

8. Write `Production/scripts/migrate_state_to_videos_partition.py` per §3.1 lift rules. Idempotent (detects `version: "v2"` and skips). Snapshots before mutation. Atomic write via `atomic_json_write`. Validation step. Per-file rollback on failure.

9. Smoke test the script in `--dry-run` mode (just print what WOULD be migrated, no writes). Verify it identifies all `Production/Event_*/production_state.json` files correctly.

### Phase E — Run migration

10. Stop the v59 server first (`pkill -f production_server.py`) to prevent in-flight requests during migration.

11. Run migration: `python3 Production/scripts/migrate_state_to_videos_partition.py`

12. Verify each event's state.json has `version: "v2"` and `videos` key per Phase F gates below.

13. Restart server with doppler env: `nohup doppler run --project mindfulnest --config dev -- python3 Production/tools/production_server.py --event-dir Production/Event_1 --storyboard storyboard_v59_prod.html --event-id Event_1 > /tmp/prodserver_s5_5_a1.log 2>&1 &`

### Phase F — Register new LDs

14. Register 3 new LDs via `try_post_or_queue`:
    - `BG_VIDEO_PARTITION_V1` (HIGH severity, task_category=architectural) — decision_text: "state.json is partitioned by video_role: {intro, phase_a, phase_b, win}. Each partition holds beats + image_overrides + role-specific fields. Top-level metadata (event_id, version, created_at, updated_at) and active_video (client default) stay top-level."
    - `VIDEO_ROLE_PER_REQUEST_V1` (HIGH severity, task_category=architectural) — decision_text: "video_role is read from request body on every mutating call (scope_video_role field). NO server-side cache of active_video. NO /api/video/load endpoint (unlike /api/event/load). Client maintains activeVideo signal locally; switching is instant + no server call. This intentionally avoids the cache-invalidation bug class that hit StateManager.state_path in S5 (LD-460 mitigation pattern)."
    - `IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1` (MEDIUM severity, task_category=bug_fix) — decision_text: "self.app._image_overrides and self.app._pending_override_keys MUST be cleared inside event_load_lock in _handle_event_load. Same bug class as the S5 StateManager state_path fix — server-side caches not following event swap → cross-event data leak. Cursor v4 finding."

### Phase G — Verify gpt-4o status (housekeeping)

15. Curl probe: `curl -s -X POST https://api.openai.com/v1/responses -H "Authorization: Bearer $ANTHROPIC_API_KEY" -H "Content-Type: application/json" -d '{"model":"gpt-4o","input":[{"role":"user","content":[{"type":"input_text","text":"ping"}]}]}'`
    
    Wait — that uses Anthropic key not OpenAI. Correct version: `curl -s -X POST https://api.openai.com/v1/responses -H "Authorization: Bearer $(doppler secrets get OPENAI_API_KEY --project mindfulnest --config dev --plain)" -H "Content-Type: application/json" -d '{"model":"gpt-4o","input":[{"role":"user","content":[{"type":"input_text","text":"ping"}]}]}'`
    
    Expect HTTP 200 with `status: "completed"`. If 403 with "must be verified" error, escalate to Kim (verification may have lapsed). Document outcome in `prod_activity_log`.

---

## 5. Files Created / Modified

| Path | Action | Why |
|---|---|---|
| `Production/Event_*/production_state.json` (each event) | MIGRATED via script | Schema lift to videos partition |
| `Production/Event_*/.backups/state/<TS>_pre_videos_migration.json` (each event) | CREATED | Pre-migration snapshot for rollback |
| `Production/scripts/migrate_state_to_videos_partition.py` | CREATED | Migration script (idempotent, atomic, per-file rollback) |
| `Production/tools/production_server.py` | MODIFIED | +5 StateManager helpers (~80 lines) + 2-line cache clear in _handle_event_load |
| `Production/tools/GPT_STILLS_TECH_SPEC_v1.md` | MODIFIED | SUPERSEDED banner at top (5 lines) |
| `Production/docs/STORYBOARD_V59_S5_5_A1_SPEC_v1.md` | CREATED (this file) | Spec for traceability |

---

## 6. Directus Writes Required

| Collection | Writes | Purpose |
|---|---|---|
| `prod_locked_decisions` | PATCH LD-426 (superseded_by_id=440, status=superseded) | LD housekeeping |
| `prod_locked_decisions` | PATCH LD-431 (superseded_by_id=440, status=superseded) | LD housekeeping |
| `prod_locked_decisions` | PATCH LD-428 (superseded_by_id=430, status=superseded) | LD housekeeping |
| `prod_locked_decisions` | PATCH LD-429 (superseded_by_id=440, status=superseded) | LD housekeeping |
| `prod_locked_decisions` | POST `BG_VIDEO_PARTITION_V1` (HIGH, architectural) | Lock the new schema |
| `prod_locked_decisions` | POST `VIDEO_ROLE_PER_REQUEST_V1` (HIGH, architectural) | Lock the stateless-per-request pattern |
| `prod_locked_decisions` | POST `IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1` (MEDIUM, bug_fix) | Lock the cache fix |
| `prod_preflight_reviews` | POST one row | Phase 0 preflight |
| `prod_activity_log` | POST one row at end | session_complete with metrics |

All writes via `Production/lib/directus.py::try_post_or_queue` (Rule 35). Field names verified against `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`.

---

## 7. Error Cases and Handling

Per Rule 19: no silent failures.

| Failure | Detection | Response |
|---|---|---|
| Migration script: per-file validation fails after lift | JSON Schema check post-construct | Restore from snapshot for that file; halt entire migration; exit non-zero with file path |
| Migration script: atomic_json_write fails | `atomic_json_write` raises | Restore from snapshot; halt; exit non-zero |
| Migration script: snapshot write fails | OS-level error | Halt before any state mutation; exit non-zero with reason |
| State helper: invalid video_role passed | `validate_video_role` returns False | Caller (handler) returns HTTP 400; helper itself raises ValueError |
| `_handle_event_load` cache clear: somehow `_image_overrides` not a dict | Defensive: `try/except AttributeError` like the S5 fix | Log warning; continue (don't break event load over a cache type issue) |
| LD PATCH: Directus 404 on LD ID | `try_post_or_queue` returns error | Log warning; queue for retry; don't halt session |
| LD POST: duplicate decision_key | Directus returns 400 with conflict | Log; PATCH the existing entry instead per Rule 20 pattern |
| gpt-4o probe: HTTP 403 "must be verified" | curl status check | Document in activity log; surface to Kim; don't halt session (gpt-image-2 is primary anyway, gpt-4o is fallback) |

---

## 8. Verification

S5.5a1 is NOT complete until ALL pass:

1. ✅ `python3 -m py_compile Production/tools/production_server.py` — clean
2. ✅ `python3 Production/scripts/migrate_state_to_videos_partition.py --dry-run` — identifies all event state.json files; shows expected lift
3. ✅ Migration runs to completion; every `Production/Event_*/production_state.json` has `version: "v2"` and a `videos` key with at least `intro`
4. ✅ Each event has a corresponding `.backups/state/<TS>_pre_videos_migration.json` snapshot
5. ✅ Server restarts cleanly with doppler env; `/api/health` returns 200
6. ✅ `curl http://localhost:5111/api/v2/event/Event_1/state` returns the partitioned state shape
7. ✅ Helper sanity check via inline Python: `from production_server import AppContext; sm = StateManager(...); sm.list_videos()` returns the expected partitions
8. ✅ Cache clear sanity test: `curl -X POST http://localhost:5111/api/event/load -H "Content-Type: application/json" -d '{"arc_number":1,"event_id":"Event_2","module_id":"M2","scope_event_id":"Event_2"}'` — verify in server logs that `_image_overrides` was cleared
9. ✅ All 4 LD PATCHes return 200 from Directus; verify by reading back each LD and confirming `superseded_by_id` is set
10. ✅ All 3 new LDs registered; verify by listing LDs and confirming the new keys appear with correct severity
11. ✅ TECH_SPEC v1 doc has SUPERSEDED banner at top
12. ✅ gpt-4o probe documented in activity log (regardless of pass/fail)
13. ✅ `prod_preflight_reviews` row exists with task_type=architectural
14. ✅ `prod_activity_log` session_complete row exists with metrics

---

## 9. Rollback

If migration fails partway:
- Per-file: snapshot restoration is automatic in the script
- Whole-event: `cp Production/Event_<N>/.backups/state/<TS>_pre_videos_migration.json Production/Event_<N>/production_state.json`
- All events: bash loop over `.backups/state/` directories

If StateManager helpers cause runtime errors after restart:
- Revert `production_server.py` via `git diff` review + targeted revert
- Server restart with reverted code

If LD PATCHes cause confusion (someone reads stale data):
- LD PATCHes are reversible (set `superseded_by_id=null`, `status="active"`)
- No data loss

If cache clear breaks something unexpected:
- Remove the 2 added lines from `_handle_event_load`
- Revert + restart

All operations have <5 minute recovery time. Schema migration has the largest blast radius but is per-file rollback-safe.

---

## 10. Out of Scope (V1)

These land in S5.5a2/b/c — NOT this session:

- ❌ Server handler refactor (~30 handlers updated to use new helpers via `state.get_beats(video_role)` instead of `state.beats`)
- ❌ Scope token expansion to include `scope_video_role`
- ❌ Async pin extension to include `video_role` in pin tuple
- ❌ Magic POSTs (LD-468/469/470) extended to carry `scope_video_role`
- ❌ BG sidecar `active_context` extension to include `video_role`
- ❌ StitchEditorState job naming with `video_role`
- ❌ v59 client `VideoSelector` component
- ❌ Bug fixes from Cursor v4 (Bug 1-4, Bug 6, Bug 7) — those are S5.5b
- ❌ Beat Generator UI build (Option B+) — that's S5.5c

---

## 11. Cursor Cross-Review Questions (v5 — for THIS spec)

1. **Schema lift rules** in §3.1 — are they complete? Any flat fields I missed that need to land in a specific partition? Specifically check if there are any orphan top-level fields beyond what I listed (image_overrides, phase_a_*, phase_b_*, beats).

2. **`active_video` field** — is putting it at top level (vs inside `videos`) the right call? It's a client default per VIDEO_ROLE_PER_REQUEST_V1, but it does live IN state.json. Risk: a future handler reads `state["active_video"]` server-side and re-introduces the cache bug class.

3. **State helper signatures** in §3.2 — does `mutate_video_state(video_role, mutator_fn)` correctly compose with the existing `mutate_state` pattern? Will it deadlock if the mutator_fn calls another state operation?

4. **Cache fix** in §3.3 — are there OTHER cache surfaces in `_handle_event_load`'s scope that I missed (similar to `_image_overrides` and `_pending_override_keys`)? Specifically check `_beats_cache`, `_storyboard_list_cache`, BG sidecar caches, anything in `_GPT_JOBS` / `_LIPSYNC_JOBS` / `_MAGIC_JOBS` dicts that might persist across event swaps.

5. **Migration idempotency** in §3.1 — is `state.get("version") == "v2"` enough to detect already-migrated, or could a partially-migrated file (interrupted mid-write) leave `version=v1` with partial `videos` key? If yes, what's the safer detection?

6. **Migration order** — Phase A (LD housekeeping) before Phase B/C/D (code + migration) — is that the right order? Pros: lowest-risk first. Cons: if Phases B-D fail, the LDs say "superseded" but the new architecture isn't actually live yet.

7. **gpt-4o probe** in Phase G — is the curl format correct? Are there gotchas with `/v1/responses` that would make a "ping" probe return 400 even when verification IS active?

8. **Atomic write under load** — migration is run with server stopped (Phase E step 10), but is there ANY other process that might write to state.json during the migration window? E.g., a cron job, a background script.

9. **Async pin extension deferral** — Cursor v4 said async pin needs to be extended to include `video_role`. I'm deferring that to S5.5a2. Is it safe to ship S5.5a1 (schema migrated) without the async pin extension yet, given that the existing async handlers will write to `videos.intro.beats` by virtue of being unchanged + the migration putting their work in intro? Or does this create a window of risk?

10. **Helper method placement** — adding 5 methods to `StateManager` class in `production_server.py` — is this the right home, or should they live in a separate module that StateManager imports? File is already 13K+ lines.

---

## 12. Cursor Verdict Format

Please respond with:

```
## Schema lift rules (Q1)
[any missed fields]

## active_video placement (Q2)
[verdict + reasoning]

## State helper signatures (Q3)
[OK or fix needed]

## Cache surface audit (Q4)
[other surfaces to clear]

## Migration idempotency (Q5)
[stronger check needed?]

## Phase ordering (Q6)
[reordering recommended?]

## gpt-4o probe (Q7)
[curl shape correct?]

## Concurrent writers during migration (Q8)
[risk assessment]

## Async pin deferral risk (Q9)
[safe to defer or not]

## Helper placement (Q10)
[file/module recommendation]

## Anything else missed
[free-form]

## Verdict
[SHIP S5.5a1 AS-IS / REVISE BEFORE SHIP / RETHINK]
```

If SHIP: I write the executable handoff next message and Kim pastes it into terminal.
If REVISE: I write spec v2 with your edits folded in, Kim sends back to you, then we ship.

---

**End of S5.5a1 spec v1. Awaiting Cursor v5 cross-review.**
