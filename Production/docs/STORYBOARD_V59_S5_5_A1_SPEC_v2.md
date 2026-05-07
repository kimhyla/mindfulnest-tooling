# Technical Spec: Storyboard v59 — Session 5.5a1 v2 (Foundation Tools — Migration Script + Helpers + Cache Fix + LD Housekeeping)
**Date:** 2026-05-03
**Produced by:** medium-rigor compact spec, v2 incorporates all Cursor v5 findings + Option C re-scope
**Status:** EXECUTABLE — Cursor v5 explicitly listed required edits and stated "after those edits, SHIP." This v2 folds them in. No further Cursor cycle required unless Kim wants extra safety.
**Supersedes:** `STORYBOARD_V59_S5_5_A1_SPEC_v1.md`
**Classification:** ARCHITECTURAL (new schema design, new StateManager pattern, cache hot-path change) — **but LOW-RISK execution** because (a) migration is dry-run only, not applied, (b) helpers are additive, no existing methods modified, (c) cache fix is 2 lines in an atomic block already proven safe by S5, (d) LD writes are reversible. Phase 0 preflight required per Rule 16; 4+4 advocate/counter NOT required (Cursor v4 + v5 reviews ARE the architectural review per LD-124).

---

## Changelog v1 → v2

| Section | v1 → v2 change | Source |
|---|---|---|
| §1 Task | RE-SCOPED: migration script written + dry-run tested ONLY; NOT applied. Application moves to S5.5a2 alongside handler refactor (atomic together) | Cursor v5 release-blocker (Q1) |
| §3.1 Schema lift | RULE-BASED via regex `^phase_a_` / `^phase_b_`; explicit homes for module-level fields (`module_sfx_cues`, `latest_preview_stitched_path`, `full_module_segment_boundaries`, `fade_between_beats_ms`, `_module_version`, `display_order`); enumerated lift list dropped | Cursor v5 Q1 |
| §3.2 State helpers | Timezone-aware datetime, "no nested mutate_state" doc, create_video logic cleanup, active_video write-path constraint documented | Cursor v5 Q3 |
| §3.3 Cache fix | `_pending_override_keys = {}` (dict, not `set()` — was a code bug in v1) + add explicit debug log line for verification | Cursor v5 Q4 |
| §3.4 NEW | Active_video constraint section: write-paths MUST IGNORE active_video; only `scope_video_role` from request body chooses partition | Cursor v5 Q2 |
| §4 Implementation order | LD housekeeping moved to LAST (after script + helpers + cache verified) | Cursor v5 Q6 |
| §5 Files | Migration script changes from "applied" to "exists + dry-run tested only" | Re-scope Option C |
| §7 Error handling | Removed "migration runs to completion" failure modes (not applicable in v2); added migration script dry-run failure modes | Re-scope |
| §8 Verification | Fixed gate #7 (sys.path / run-from-correct-directory); added explicit cache-clear log line check; gpt-4o probe accepts 200 OR 401/403 | Cursor v5 Q7, Q8 |
| §9 Rollback | Much simpler since no migration applied; rollback is just code revert | Re-scope |
| §10 Out of scope | Updated to clarify migration APPLICATION + handler refactor are S5.5a2 (atomic together) | Re-scope |
| §11 (was Cursor v5 questions) | Superseded by Cursor v5 verdict; replaced with "S5.5a2 dependencies" | v5 closed |

---

## 1. Task

S5.5a1 v2 is the FOUNDATION-TOOLS session for Option B (video partitioning within events). It writes the tools needed for the migration in S5.5a2, but does NOT apply the migration. Concretely:

1. **Migration script** — `Production/scripts/migrate_state_to_videos_partition.py` is written + dry-run tested; NOT executed in apply mode this session
2. **State helpers** — 5 new methods added to `StateManager` class. No existing methods touched. No handlers updated to use them yet
3. **Cross-event cache leak fix** — clear `_image_overrides` and `_pending_override_keys` in `_handle_event_load` (Cursor v4 finding — same bug class as the S5 StateManager fix)
4. **LD housekeeping** — PATCH 4 stale LDs to set their `superseded_by_id` FKs (LD-426, LD-431, LD-428, LD-429); add SUPERSEDED banner to TECH_SPEC v1; register 3 new LDs (`BG_VIDEO_PARTITION_V1`, `VIDEO_ROLE_PER_REQUEST_V1`, `IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1`)
5. **gpt-4o probe** — one curl; document outcome in activity log

**What S5.5a1 v2 explicitly does NOT do:**
- Apply the schema migration to actual `production_state.json` files
- Refactor any handler to use the new helpers
- Extend scope tokens, async pins, magic POSTs, BG sidecar, or StitchEditorState
- Touch v59 client code

**Why deferred:** Cursor v5 release-blocker (Q1) — applying the lift-only migration without simultaneously refactoring the ~30 handlers that read `state.beats` would break the server. Migration application + handler refactor MUST ship atomically. They land together in S5.5a2.

---

## 2. Governing Decisions

(Same as v1 except Cursor v5 review now informs this v2.)

**Locked decisions this spec respects:**

| LD | Why it constrains S5.5a1 v2 |
|---|---|
| LD-456 SCOPE_VALIDATION_V1 | Existing `_assert_event_scope` pattern stays untouched in S5.5a1; extension lands in S5.5a2 |
| LD-458 EVENT_LOAD_GENERATION_LOCK_V1 | The `_handle_event_load` swap mechanism is being EXTENDED (additively) with cache clears under the same lock |
| LD-460 ASYNC_JOB_GENERATION_PIN_V1 | Existing async pin pattern stays untouched in S5.5a1; extension to include `video_role` lands in S5.5a2 (acceptable deferral while only intro partition exists per Cursor v5 Q9) |
| LD-461 SCOPE_BODY_HELPER_V1 | `_scope_body` helper exists; will be extended in S5.5a2 to handle `scope_video_role` |
| LD-440 GPT_IMAGE_2_PRIMARY_MODEL_V1 | Locks gpt-image-2 as primary; LD-426 housekeeping in this session reflects this (PATCH supersession FK) |
| LD-430 OPENAI_ORG_VERIFICATION_CLEARED_V1 | gpt-4o verification confirmed cleared 2026-04-27; we re-probe in this session as housekeeping |
| Rule 35 (Directus schema verification) | All Directus PATCHes use `try_post_or_queue` and consult `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` |
| Rule 19 (no shortcuts) | Migration script must snapshot first; rollback paths must work; dry-run must run cleanly before any future apply |
| Rule 27 (delete obsolete workarounds) | TECH_SPEC v1 stays on disk with SUPERSEDED banner — not deleted (other docs may reference it) |
| Rule 36 (patch invariant persistence) | Not applicable — no JS patches in this session |

**New LDs to register during S5.5a1 v2:**

- `BG_VIDEO_PARTITION_V1` — locks the `videos: {intro, phase_a, phase_b, win}` schema as the canonical state.json structure for v59
- `VIDEO_ROLE_PER_REQUEST_V1` — locks the stateless-per-request `video_role` pattern (no server-side cache of active partition; no `/api/video/load` endpoint; client maintains `activeVideo` signal locally and sends `scope_video_role` on every mutating request — the design Cursor v4 specifically validated, derived from S5's StateManager bug lesson)
- `IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1` — locks the cache-clear fix for `_image_overrides` + `_pending_override_keys` on event swap

---

## 3. Approach

### 3.1 Schema migration design — RULE-BASED LIFT (Cursor v5 Q1 fix)

`Production/Event_*/production_state.json` currently has a flat structure with many fields. The lift rules are RULE-BASED per Cursor v5 finding (enumerated list missed real fields):

**Lift rules (applied by `migrate_state_to_videos_partition.py` in dry-run mode):**

```python
# Rule 1: Top-level metadata STAYS at top level
TOP_LEVEL_KEEP = {
    'event_id', 'version', 'created_at', 'updated_at',
    '_module_version',
    'module_sfx_cues',
    'latest_preview_stitched_path',
    'full_module_segment_boundaries',
    'fade_between_beats_ms',
    'active_video',  # NEW field added at top level (client default; see §3.4)
}

# Rule 2: Beats and intro-related fields → videos.intro
INTRO_LIFT = {
    'beats': 'videos.intro.beats',
    'image_overrides': 'videos.intro.image_overrides',
    'display_order': 'videos.intro.display_order',
}

# Rule 3: Regex-based phase lift
# Any key matching ^phase_a_ → videos.phase_a.{key}
# Any key matching ^phase_b_ → videos.phase_b.{key}

# Rule 4: NEW empty videos.win partition (placeholder for future win/resolution work)
videos.win = {
    'video_role': 'win',
    'video_label': None,
    'beats': {},
    'image_overrides': {},
}

# Rule 5: Each populated partition gets video_role + video_label fields
# (video_label defaults to None for migrated; user sets via "+ New video" UI later)
```

**Example BEFORE (v1 flat):**
```json
{
  "event_id": "Event_1",
  "version": "v1",
  "_module_version": 1,
  "beats": { "beat_01": {...}, ... },
  "display_order": ["beat_01", ...],
  "image_overrides": { "beat_01": "img_xyz" },
  "module_sfx_cues": [...],
  "latest_preview_stitched_path": "...",
  "full_module_segment_boundaries": {...},
  "fade_between_beats_ms": 250,
  "phase_a_script": "...",
  "phase_a_voice_stem_file": "...",
  "phase_a_mixed_audio_file": "...",
  "phase_a_lipsync_file": "...",
  "phase_a_stitched_file": "...",
  "phase_a_status": "draft",
  "phase_b_script": "...",
  "phase_b_voice_stem_file": "...",
  "phase_b_lipsync_file": "...",
  "phase_b_lipsync_mtime": 12345,
  "phase_b_watercolor_cues_json": [...],
  "phase_b_ambient_preset_id": "calm_water",
  "phase_b_status": "draft",
  "created_at": "2026-04-22T...",
  "updated_at": "2026-04-22T..."
}
```

**Example AFTER (v2 partitioned):**
```json
{
  "event_id": "Event_1",
  "version": "v2",
  "_module_version": 1,
  "module_sfx_cues": [...],
  "latest_preview_stitched_path": "...",
  "full_module_segment_boundaries": {...},
  "fade_between_beats_ms": 250,
  "active_video": "intro",
  "videos": {
    "intro": {
      "video_role": "intro",
      "video_label": null,
      "beats": { "beat_01": {...}, ... },
      "display_order": ["beat_01", ...],
      "image_overrides": { "beat_01": "img_xyz" }
    },
    "phase_a": {
      "video_role": "phase_a",
      "video_label": null,
      "phase_a_script": "...",
      "phase_a_voice_stem_file": "...",
      "phase_a_mixed_audio_file": "...",
      "phase_a_lipsync_file": "...",
      "phase_a_stitched_file": "...",
      "phase_a_status": "draft"
    },
    "phase_b": {
      "video_role": "phase_b",
      "video_label": null,
      "phase_b_script": "...",
      "phase_b_voice_stem_file": "...",
      "phase_b_lipsync_file": "...",
      "phase_b_lipsync_mtime": 12345,
      "phase_b_watercolor_cues_json": [...],
      "phase_b_ambient_preset_id": "calm_water",
      "phase_b_status": "draft"
    },
    "win": {
      "video_role": "win",
      "video_label": null,
      "beats": {},
      "image_overrides": {}
    }
  },
  "created_at": "2026-04-22T...",
  "updated_at": "2026-05-03T..."
}
```

**Migration script `Production/scripts/migrate_state_to_videos_partition.py`:**

Modes:
- `--dry-run` (default if no flag) — print proposed lift per file; no writes
- `--apply` — actually apply migration (used in S5.5a2 only)
- `--validate` — verify all event state.json files are at version v2

**Per-file safety procedure (apply mode — for S5.5a2):**
1. Snapshot to `Production/Event_<N>/.backups/state/<TS>_pre_videos_migration.json`
2. Read flat state.json
3. Construct new partitioned dict per lift rules (Rules 1-5 above)
4. Validate via JSON Schema check
5. Atomic write via `Production/lib/atomic_json_write.py` (tmp+rename)
6. Verify post-write read returns expected `version: "v2"` + `videos` key
7. If validation fails at any step: restore from snapshot, halt entire migration, exit non-zero

**Idempotency check (Cursor v5 Q5 fix):**
```python
def is_already_migrated(state: dict) -> bool:
    """Strong idempotency: must have version=v2 AND videos key AND intro partition."""
    if state.get("version") != "v2":
        return False
    videos = state.get("videos")
    if not isinstance(videos, dict):
        return False
    if "intro" not in videos:
        return False
    # Optional: full JSON Schema validation here
    return True

def is_partial_migration(state: dict) -> bool:
    """Detect interrupted migration: has videos key but version still v1.
    Fail closed in this case — restore from snapshot, manual inspection required."""
    return ("videos" in state) and (state.get("version") != "v2")

# Per-file logic:
if is_already_migrated(state):
    print(f"SKIP: {path} already migrated")
    continue
if is_partial_migration(state):
    raise RuntimeError(
        f"FAIL CLOSED: {path} has videos key but version != v2 — "
        f"likely interrupted prior migration. Manual inspection required. "
        f"Restore from .backups/state/<TS>_pre_videos_migration.json if needed."
    )
# ...proceed with migration
```

**Migration script user warning (printed at start):**
```
⚠️  Before running --apply mode:
   1. Stop the v59 server (pkill -f production_server.py)
   2. Close any text editors with state.json files open
   3. Pause Dropbox sync if you can (this minimizes write conflicts during atomic rename)
   4. Confirm no background scripts are writing to Production/Event_*/production_state.json
   
   --dry-run mode is safe to run with server up. Apply mode is NOT.
```

### 3.2 State helpers (Cursor v5 Q3 fixes)

Add 5 methods to `StateManager` class in `production_server.py` (around line 811). All NEW; no existing methods modified.

```python
from datetime import datetime, timezone

def get_beats(self, video_role: str) -> dict:
    """Returns the beats dict for the given video_role partition.
    
    Reads fresh from state.json on every call (no caching, per the lesson
    from S5's StateManager state_path bug — VIDEO_ROLE_PER_REQUEST_V1).
    
    Returns empty dict if partition doesn't exist or has no beats.
    Caller must validate video_role first via validate_video_role().
    """
    state = self.read_state()
    videos = state.get("videos", {})
    if video_role not in videos:
        return {}
    return videos[video_role].get("beats", {})

def mutate_video_state(self, video_role: str, mutator_fn: callable) -> dict:
    """Atomic mutation of a single video_role partition.
    
    mutator_fn receives the partition dict and mutates it in place.
    
    IMPORTANT: do NOT call mutate_state() or mutate_video_state() inside
    mutator_fn — Python's RLock allows nested acquisition by the same thread,
    but nested logical mutations risk inconsistent snapshots and harder-to-
    debug write conflicts. If a handler needs multiple partition mutations,
    sequence them via separate mutate_video_state calls (each atomic on its
    own).
    """
    def _wrapped_mutator(state):
        if "videos" not in state:
            state["videos"] = {}
        if video_role not in state["videos"]:
            # Auto-create empty partition with required role marker
            state["videos"][video_role] = {
                "video_role": video_role,
                "video_label": None,
            }
            # Beats partitions get empty dict; phase partitions don't
            if video_role in {"intro", "win", "standalone"}:
                state["videos"][video_role]["beats"] = {}
                state["videos"][video_role]["image_overrides"] = {}
        mutator_fn(state["videos"][video_role])
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return self.mutate_state(_wrapped_mutator)

def list_videos(self) -> list:
    """Returns list of all video partitions in the current event.
    
    Each entry: {video_role, video_label, has_beats: bool, beat_count: int}
    """
    state = self.read_state()
    videos = state.get("videos", {})
    result = []
    for role, partition in videos.items():
        beats = partition.get("beats", {})
        result.append({
            "video_role": partition.get("video_role", role),
            "video_label": partition.get("video_label"),
            "has_beats": bool(beats),
            "beat_count": len(beats) if isinstance(beats, dict) else 0,
        })
    return result

def create_video(self, video_role: str, video_label: str = None) -> bool:
    """Adds a new video partition under the current event.
    
    Returns True if created, False if partition with this role already exists.
    Raises ValueError if video_role is not in the canonical set.
    """
    VALID_ROLES = {"intro", "phase_a", "phase_b", "win", "standalone"}
    if video_role not in VALID_ROLES:
        raise ValueError(
            f"Invalid video_role: {video_role!r}. Must be one of {sorted(VALID_ROLES)}."
        )
    
    state = self.read_state()
    if video_role in state.get("videos", {}):
        return False
    
    def _mutator(state):
        if "videos" not in state:
            state["videos"] = {}
        partition = {
            "video_role": video_role,
            "video_label": video_label,
        }
        if video_role in {"intro", "win", "standalone"}:
            partition["beats"] = {}
            partition["image_overrides"] = {}
        elif video_role in {"phase_a", "phase_b"}:
            partition[f"{video_role}_status"] = "draft"
            # Other phase fields populated lazily on first write
        state["videos"][video_role] = partition
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    self.mutate_state(_mutator)
    return True

def validate_video_role(self, video_role: str) -> bool:
    """Returns True if video_role is in the canonical enum AND exists in current state."""
    VALID_ROLES = {"intro", "phase_a", "phase_b", "win", "standalone"}
    if video_role not in VALID_ROLES:
        return False
    state = self.read_state()
    return video_role in state.get("videos", {})
```

These helpers don't replace `read_state()` / `mutate_state()` — they layer on top for video-partition-aware operations. The 30+ handlers that need to use these helpers get refactored in S5.5a2 (atomically with the migration application).

### 3.3 Cache fix in `_handle_event_load` (Cursor v5 Q4 fix)

Per Cursor v4 finding: `_image_overrides` and `_pending_override_keys` are cleared in `_handle_storyboard_switch` (lines 4215-4218) but NOT in `_handle_event_load`. So switching events leaves Event_1's image overrides in memory, can serve to Event_2 requests.

**Fix in `_handle_event_load` (around line 5775):**

```python
# Inside the event_load_lock atomic block, alongside existing event_dir/state_path swap:

# Clear cross-event cache surfaces (Cursor v4 finding — same bug class as
# the S5 StateManager state_path fix; image_overrides was cleared in
# _handle_storyboard_switch but missed in _handle_event_load until now).
# Per IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1.
try:
    self.app._image_overrides = {}
    self.app._pending_override_keys = {}  # CORRECTED: dict, not set (matches L4216-4217 pattern)
    print(f"[event/load] cleared image override cache (event swap to {new_event_id})", flush=True)
except AttributeError:
    # Defensive: if attributes don't exist (race condition), don't break event load
    pass
```

The print line is intentional — verification gate #8 reads the server log to confirm cache clear fired.

**What we INTENTIONALLY do NOT clear here (Cursor v5 Q4):**
- `invalidate_beats_cache()` and `_storyboard_list_cache` — already cleared at lines 5788-5790 (existing S5 fix)
- `_MAGIC_JOBS / _LIPSYNC_JOBS / _FLUX_JOBS` — addressed by LD-460 generation pin; wiping would strand clients mid-poll
- BG sidecar — different contract (not RAM cache for event swap; needs a separate LD if extended)

### 3.4 Active_video write-path constraint (Cursor v5 Q2 — NEW section)

`active_video` is a top-level field in state.json that records the client's last-selected video partition. It exists as a UX convenience — when Kim reloads v59, the Video dropdown defaults to wherever she was last working.

**CRITICAL CONSTRAINT (locked via `VIDEO_ROLE_PER_REQUEST_V1` LD):**

NO server handler may use `state["active_video"]` to choose a partition for a mutating operation. Partition selection comes ONLY from `body["scope_video_role"]` on the request. This rule prevents reintroducing the cache-invalidation bug class that hit `StateManager.state_path` in S5 — `active_video` is persisted state, not RAM cache, but it would still create silent wrong-partition writes if a handler ignored the request scope and read state["active_video"] instead.

**Enforcement:**
- LD `VIDEO_ROLE_PER_REQUEST_V1` decision_text explicitly bans this pattern
- S5.5a2 handler refactor will add lint/audit script catching `state["active_video"]` reads in mutating handler paths (not in S5.5a1)
- Code reviewers (human + Claude) flag this pattern when seen

**What active_video IS allowed for:**
- v59 client reads it on boot to set default Video dropdown selection
- v59 client writes it (via pathappPatch) when user changes Video dropdown — purely a UX persistence
- Read-only handlers (e.g., `/api/video/list`) may use it to mark which partition is "current" in the response, for UI display only

---

## 4. Implementation Steps

### Phase 0 — Preflight (mandatory per Rule 16)

1. Open `prod_preflight_reviews` row:
   - `task_type=architectural`
   - `claude_summary`: "S5.5a1 v2 — foundation tools for Option B (videos partition). Migration script (dry-run only) + StateManager helpers + image_overrides cache clear + LD housekeeping. Migration application + handler refactor deferred to S5.5a2 atomic. Architecture per Cursor v4 (Option B approval) + Cursor v5 (execution-spec review) — neither requires re-running 4+4 advocate/counter."
   - References: preflight #193 (S5), #192 (S4), #191 (S3), #190 (S2), #189 (S1.5)

### Phase A — Cache fix (small, surgical, low risk; do FIRST so the rest of the session benefits)

2. Edit `production_server.py:_handle_event_load` (around line 5775) inside the existing `event_load_lock` block. Add the cache clear per §3.3 (corrected `_pending_override_keys = {}` per Cursor v5 Q4).

3. Verify via py_compile: `python3 -m py_compile Production/tools/production_server.py`

### Phase B — State helpers (additive only; no breaking changes)

4. Add the 5 helper methods to `StateManager` class per §3.2. All methods are NEW; no existing methods touched. Use `from datetime import datetime, timezone` if not already imported.

5. Verify via py_compile.

6. Sanity-test each helper via inline Python (run from `Production/tools/` directory to satisfy import paths per Cursor v5 Q8 fix to gate #7):
   ```bash
   cd "Production/tools" && python3 -c "
   import sys
   sys.path.insert(0, '.')
   from production_server import StateManager
   from pathlib import Path
   sm = StateManager(Path('../Event_1'), 'Event_1')
   print('list_videos:', sm.list_videos())
   print('validate_video_role(intro):', sm.validate_video_role('intro'))
   print('validate_video_role(garbage):', sm.validate_video_role('garbage'))
   "
   ```
   Expected: `list_videos` returns `[]` since current state.json is unmigrated (no `videos` key); `validate_video_role` returns False for both because state has no `videos` key. This is correct — confirms helpers don't crash on pre-migration state.

### Phase C — Migration script (write + dry-run only; NOT applied)

7. Write `Production/scripts/migrate_state_to_videos_partition.py` per §3.1:
   - Default mode is `--dry-run`
   - `--apply` mode reserved for S5.5a2 (script accepts the flag but in S5.5a1 we never invoke with `--apply`)
   - Strong idempotency check per §3.1 (version=v2 + videos key + intro partition)
   - Partial-migration detection (videos exists but version != v2) → fail closed
   - User warning printed at start of `--apply` mode (close editors, pause Dropbox)
   - Per-file snapshot before write
   - Atomic write via `Production/lib/atomic_json_write.py`
   - Validation: lift produces all expected keys; no orphan top-level fields except those in `TOP_LEVEL_KEEP` set

8. Run script in dry-run mode against actual state files:
   ```bash
   python3 Production/scripts/migrate_state_to_videos_partition.py --dry-run
   ```
   Expected output: per-file lift preview showing which fields go to which partition. Should identify all `Production/Event_*/production_state.json` files and process each. Exit 0 if all dry-run lifts are valid (no orphan fields, no schema violations).

9. **Audit dry-run output for orphan top-level fields.** Any field in actual state.json that doesn't match any lift rule (not in TOP_LEVEL_KEEP, not matching `^phase_a_` or `^phase_b_`, not in INTRO_LIFT) is an ORPHAN. Script must FAIL CLOSED on orphan detection — log all orphans, exit non-zero. This catches schema drift between this spec's lift rules and the actual production state.

10. If orphans found: STOP. Add the field to the appropriate rule (TOP_LEVEL_KEEP, INTRO_LIFT, or document why it should be dropped). Re-run dry-run. Iterate until zero orphans.

### Phase D — gpt-4o probe (housekeeping; informational)

11. Curl probe (per Cursor v5 Q7 fix — accept 200 OR 401/403 with clear body as auth proven; document any 400 body):
    ```bash
    OPENAI_KEY=$(doppler secrets get OPENAI_API_KEY --project mindfulnest --config dev --plain)
    curl -s -w "\nHTTP=%{http_code}\n" -X POST https://api.openai.com/v1/responses \
      -H "Authorization: Bearer $OPENAI_KEY" \
      -H "Content-Type: application/json" \
      -d '{"model":"gpt-4o","input":[{"role":"user","content":[{"type":"input_text","text":"ping"}]}]}'
    ```
    Outcomes:
    - HTTP 200 + `status: "completed"` → gpt-4o Responses API ACTIVE; activity log entry: `gpt4o_responses_api_active_confirmed`
    - HTTP 401/403 with clear "must be verified" body → org verification has lapsed since LD-430; surface to Kim immediately; activity log entry with body
    - HTTP 400 with schema validation error → route works, auth works, just a probe shape issue; non-blocking; log body for next-time fix
    - Any other → log body, treat as inconclusive

### Phase E — LD housekeeping (REORDERED to LAST per Cursor v5 Q6)

12. PATCH 4 stale LDs via `Production/lib/directus.py::try_post_or_queue` (consult `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`):
    - LD-426 GPT_STILLS_ENDPOINT_V1: set `superseded_by_id=440`, `status="superseded"`, append note "Superseded by LD-440 GPT_IMAGE_2_PRIMARY_MODEL_V1 (2026-04-28). Code path moved from gpt-image-1 to gpt-image-2."
    - LD-431 BEAT_GENERATOR_RESPONSES_API_WIRING_PENDING_V1: set `superseded_by_id=440`, `status="superseded"`, append note "Superseded by LD-440. Wiring complete; gpt-4o demoted to fallback per A/B test."
    - LD-428 OPENAI_ORG_VERIFICATION_SUBMITTED_V1: set `superseded_by_id=430`, `status="superseded"`, append note "Superseded by LD-430 OPENAI_ORG_VERIFICATION_CLEARED_V1 (2026-04-27 ~13:13 UTC, HTTP 200 confirmed)."
    - LD-429 GPT_STILLS_RESPONSES_API_PRIMARY_V1: set `superseded_by_id=440`, `status="superseded"`, append note "Superseded by LD-440. gpt-image-2 is primary; gpt-4o demoted to fallback per Kim's A/B verdict."

13. Add SUPERSEDED banner to `Production/tools/GPT_STILLS_TECH_SPEC_v1.md`:
    - Insert at top of doc (before existing content):
      ```markdown
      > ⚠️ **SUPERSEDED 2026-05-03** — This spec describes the original gpt-image-1 prompt with `_GPT_SPECIES_ANCHOR` text descriptions. Current production architecture is:
      > - **Model:** `gpt-image-2` per LD-440 (was gpt-image-1 in this doc)
      > - **Prompt:** image-led ~380-char per LD-439 (was 1152-char species-anchor in this doc)
      > - **Code source of truth:** `Production/tools/beat_generator.py:934-947` for `build_gpt_still_prompt()`
      > Refer to LD-439 + LD-440 for current architecture; this doc is retained for historical context only.
      ```

14. Register 3 new LDs via `try_post_or_queue`:
    - `BG_VIDEO_PARTITION_V1` (HIGH severity, task_category=architectural) — decision_text: "state.json is partitioned by video_role: {intro, phase_a, phase_b, win}. Each partition holds beats + image_overrides + role-specific fields. Top-level metadata (event_id, version, created_at, updated_at, _module_version, module_sfx_cues, latest_preview_stitched_path, full_module_segment_boundaries, fade_between_beats_ms, active_video) stays top-level. Migration script lives at Production/scripts/migrate_state_to_videos_partition.py. Apply mode reserved for S5.5a2."
    - `VIDEO_ROLE_PER_REQUEST_V1` (HIGH severity, task_category=architectural) — decision_text: "video_role is read from request body (scope_video_role) on every mutating call. NO server-side cache of active_video. NO /api/video/load endpoint. Client maintains activeVideo signal locally; switching is instant + no server call. CRITICAL CONSTRAINT: handlers MUST NOT use state['active_video'] for partition selection — only body['scope_video_role']. active_video is purely a UX persistence (last-selected partition) for client default. Designed to avoid the cache-invalidation bug class that hit StateManager.state_path in S5 (LD-460 mitigation pattern)."
    - `IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1` (MEDIUM severity, task_category=bug_fix) — decision_text: "self.app._image_overrides (dict) and self.app._pending_override_keys (dict) MUST be cleared inside event_load_lock in _handle_event_load. Same bug class as the S5 StateManager state_path fix — server-side caches not following event swap → cross-event data leak. Cursor v4 finding."

### Phase F — Final verification + close session

15. Run the full verification gate (§8). All checks must pass.

16. Append `prod_activity_log` row: `action='session_complete'`, `details={session: '5.5a1', migration_script_dryrun: 'green', helpers_added: 5, cache_fix_landed: true, lds_patched: 4, lds_added: 3, gpt4o_status: '<from probe>'}`.

17. Tell Kim plainly: "Session 5.5a1 v2 done. Foundation tools shipped. Next: Session 5.5a2 applies migration + refactors handlers atomically."

---

## 5. Files Created / Modified

| Path | Action | Why |
|---|---|---|
| `Production/scripts/migrate_state_to_videos_partition.py` | CREATED | Migration script (dry-run mode only in S5.5a1; apply mode reserved for S5.5a2) |
| `Production/tools/production_server.py` | MODIFIED (~80 lines added) | +5 StateManager helpers + 4-line cache clear in _handle_event_load |
| `Production/tools/GPT_STILLS_TECH_SPEC_v1.md` | MODIFIED | SUPERSEDED banner at top (~6 lines) |
| `Production/docs/STORYBOARD_V59_S5_5_A1_SPEC_v2.md` | EXISTS (this file) | Spec for traceability |
| `Production/Event_*/production_state.json` | UNCHANGED | Migration NOT applied in S5.5a1 (deferred to S5.5a2) |
| `Production/Event_*/.backups/state/` | UNCHANGED | No snapshots created (no migration applied) |

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
| `prod_activity_log` | POST one row at start (gpt4o_probe outcome) | Probe result |
| `prod_activity_log` | POST one row at end (session_complete) | Session metrics |

All writes via `Production/lib/directus.py::try_post_or_queue` (Rule 35). Field names verified against `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`.

---

## 7. Error Cases and Handling

Per Rule 19: no silent failures.

| Failure | Detection | Response |
|---|---|---|
| Migration script: orphan top-level field detected in dry-run | `is_orphan_field()` check | Log all orphans; exit non-zero with field names; halt. Add fields to lift rules; re-run |
| Migration script: dry-run validation fails | JSON Schema check on proposed lift | Log per-file failure; exit non-zero; do NOT proceed to LD housekeeping until fixed |
| Migration script: `--apply` mode invoked accidentally during S5.5a1 | Script defaults to `--dry-run` | Even if `--apply` passes by mistake, the user warning + 5-second confirm prompt requires explicit ack |
| State helper: invalid video_role passed | `validate_video_role` returns False | Caller responsible for HTTP 400; helper itself raises ValueError on `create_video` with bad role |
| State helper: helper called on pre-migration state | `read_state` returns no `videos` key | Helper returns empty result (sane default); does not crash. After migration these helpers find data |
| `_handle_event_load` cache clear: attribute missing | `try/except AttributeError` | Log warning; continue (don't break event load) |
| LD PATCH: Directus 404 on LD ID | `try_post_or_queue` returns error | Log warning; queue for retry; don't halt session |
| LD POST: duplicate decision_key | Directus returns 400 with conflict | Log; PATCH the existing entry instead per Rule 20 |
| gpt-4o probe: 401/403 "must be verified" | curl status check | Document in activity log; surface to Kim; don't halt (gpt-image-2 is primary, gpt-4o is fallback) |
| gpt-4o probe: 400 schema error | curl status check | Document body in activity log; treat as inconclusive; non-blocking |

---

## 8. Verification

S5.5a1 v2 is NOT complete until ALL pass:

1. ✅ `python3 -m py_compile Production/tools/production_server.py` — clean
2. ✅ `python3 Production/scripts/migrate_state_to_videos_partition.py --dry-run` — exits 0; identifies all event state.json files; shows expected lift; reports zero orphan fields
3. ✅ State helpers sanity check via inline Python (run from `Production/tools/` per Cursor v5 Q8 fix) — all 5 methods callable; return expected types on pre-migration state
4. ✅ Cache clear sanity test: `curl -X POST http://localhost:5111/api/event/load -H "Content-Type: application/json" -d '{"arc_number":1,"event_id":"Event_2","module_id":"M2","scope_event_id":"Event_2"}'` — verify in `/tmp/prodserver_*.log` that `[event/load] cleared image override cache (event swap to Event_2)` appears
5. ✅ All 4 LD PATCHes return 200 from Directus; verify by reading back each LD and confirming `superseded_by_id` is set
6. ✅ All 3 new LDs registered; verify by listing LDs and confirming the new keys appear with correct severity
7. ✅ TECH_SPEC v1 doc has SUPERSEDED banner at top
8. ✅ gpt-4o probe documented in activity log (regardless of outcome)
9. ✅ `prod_preflight_reviews` row exists with task_type=architectural
10. ✅ `prod_activity_log` session_complete row exists with metrics
11. ✅ Server still running + healthy via `/api/health` (no regressions from cache fix)
12. ✅ Existing Playwright suite still passes (no regressions)

---

## 9. Rollback

Much simpler than v1 since no migration applied:

| Failure scope | Rollback |
|---|---|
| Code changes (helpers, cache fix) | `git diff` review + targeted revert; server restart |
| Migration script | Just delete the file (no state.json files were touched) |
| LD PATCHes | Reversible — set `superseded_by_id=null`, `status="active"` |
| New LDs | Mark `status="superseded"` if needed |
| TECH_SPEC banner | Delete the inserted banner block |

Recovery time: <5 minutes for any failure mode.

No state.json snapshots needed because no state.json files were modified.

---

## 10. Out of Scope (V1 — what S5.5a2 does)

These land in S5.5a2 (atomic together — migration application requires handler refactor, and vice versa):

- ❌ APPLY the schema migration (run `migrate_state_to_videos_partition.py --apply`)
- ❌ Server handler refactor (~30 handlers updated to use `state.get_beats(video_role)` instead of `state.beats`)
- ❌ Scope token expansion to include `scope_video_role` (extends `_assert_event_scope`)
- ❌ Async pin extension to include `video_role` in pin tuple (extends LD-460 pattern — acceptable deferral per Cursor v5 Q9 because intro is the only used partition pre-S5.5a2)
- ❌ Magic POSTs (LD-468/469/470) extended to carry `scope_video_role`
- ❌ BG sidecar `active_context` extension to include `video_role`
- ❌ StitchEditorState job naming with `video_role`
- ❌ v59 client `VideoSelector` component
- ❌ Bug fixes from Cursor v4 (Bug 1-4, Bug 6, Bug 7) — those are S5.5b
- ❌ Beat Generator UI build (Option B+) — that's S5.5c

---

## 11. S5.5a2 Dependencies (next session expects these from S5.5a1)

S5.5a2 will require these S5.5a1 artifacts:

- `Production/scripts/migrate_state_to_videos_partition.py` exists, dry-run-tested, with `--apply` mode coded
- `StateManager` has 5 helper methods (`get_beats`, `mutate_video_state`, `list_videos`, `create_video`, `validate_video_role`)
- `_handle_event_load` clears `_image_overrides` and `_pending_override_keys` (so S5.5a2's handler refactor doesn't reintroduce the cache leak)
- LDs registered: `BG_VIDEO_PARTITION_V1`, `VIDEO_ROLE_PER_REQUEST_V1`, `IMAGE_OVERRIDES_CLEAR_ON_EVENT_LOAD_V1`
- LDs PATCHed: 426, 431, 428, 429 with proper `superseded_by_id`

S5.5a2's first action will be: stop server → `python3 Production/scripts/migrate_state_to_videos_partition.py --apply` → verify all event state.json files have `version: "v2"` + `videos` key → THEN refactor handlers (atomic with the migration).

---

**End of S5.5a1 v2 spec. Ready for terminal CLI execution.**
