# Storyboard v59 — Authoring Workflow IMPLEMENTATION HANDOFF

**Status:** READY FOR IMPLEMENTATION (fresh terminal session executes; tech-spec session 2026-05-05/06 terminates after this doc lands)
**Spec:** `Production/docs/STORYBOARD_V59_AUTHORING_WORKFLOW_SPEC_v2.md` (59,213 bytes / 648 lines, Cursor APPROVE 2026-05-06; supersedes v1 forensic record at `STORYBOARD_V59_AUTHORING_WORKFLOW_SPEC_v1.md`)
**Branch:** `claude/post-redeploy-bug-triage` (HEAD: `fafdfed Δ-architecture-tighten`)
**Pattern:** post-redeploy-bug-triage handoff (`Production/docs/STORYBOARD_V59_POST_REDEPLOY_TERMINAL_HANDOFF.md`, prod_reference_docs id=199)
**Atomic commits:** C-0 → C-16 (16 commits; architecture C-0..C-10 + ride-alongs C-12..C-14 + smoke C-15 + PR C-16)

---

## 0. Read this first

This handoff is **self-contained** for a fresh terminal session. The dual-Opus tech-spec session does not need to be re-read; the spec at `Production/docs/STORYBOARD_V59_AUTHORING_WORKFLOW_SPEC_v2.md` is the architectural source of truth.

**Before starting any commit:**

1. **Verify K-finding line citations are still on disk** (stale-cache check). The spec's K-finding line numbers were verified 2026-05-05 against `production_server.py`. If any line has drifted (e.g., a small unrelated commit shifted line numbers), re-verify with `grep -n` and update the spec + this doc inline before the relevant commit.
2. **Confirm branch state.** You should be on `claude/post-redeploy-bug-triage` at `fafdfed`. If main has moved, rebase before starting; rebase conflicts on `production_server.py` are likely if any K-finding-touched line has been edited.
3. **Confirm DS-7 server staleness.** Local: `pkill -f "production_server.py.*Event_1"` then re-launch before any test run that exercises a server. CI: workflow handles automatically.
4. **Confirm Production/.recovery_audit.jsonl is gitignored** before C-7. Add to `.gitignore` in C-7 if absent.

**Do not bundle.** Each C-N is a separate atomic commit per DS-12. CI must be GREEN between commits 1-8 and 10 (commits 9, 12, 13, 14 are operational/feature/deploy and may stay GREEN throughout). Mid-phase checkpoints are forbidden per DS-12.

**No `--no-verify` on commits unless explicitly authorized.** No `--no-edit` on rebases (the flag does not exist for rebase per DS-12).

**No silent shortcuts.** When a Discipline Standard cannot be met, halt and surface to Kim.

---

## 1. Executive summary (1 page)

The v59 authoring-workflow architecture has 9 K-class structural bugs (K1-K8 + D5) that share one root cause: state mutations on `production_server.py` are scattered across handlers that each re-derive partition resolution by hand, hardcoding `videos.intro` and bypassing the partition-aware mutator wrapper. The pre-LD-456 cross-event Accept-All leak (2026-05-01) caused 18 Event-2 narrative beats to land in `Event_1/intro` (17 stranded beats + 1 orphan stub `Event_2/beat_04`); the leak was structurally closed by LD-456 SCOPE_VALIDATION_V1 (C5 ratified) but the data damage persisted.

**Architectural fix (SCOPE-ROUTER + GRAFT, SR+G v1):**
- New `Production/tools/scope_router.py` module: `resolve(body)` + `mutate_partition(scope, fn)` + `graft(...)`. Mandatory router for all beat-touching mutations.
- `_assert_event_scope` defaults flip `allow_missing=False, allow_missing_video_role=False` for all mutating handlers.
- AST grep CI gate bans hardcoded `videos.intro` lifts and direct top-level `state["beats"]` writes outside the router.
- DISPLAY_ORDER_STRICT_V2: defense-in-depth prune in both `mutate_state` AND `mutate_video_state`.
- Speaker canonicalization at write boundary; `or "Guide Bird"` literal removed.
- New `/api/beat/graft` endpoint: COPY default + `move=true` flag + cross-event via `--source-event` server restart flag + pre-render-only invariant + audit JSONL + Directus mirror + idempotency (mutation_id + content fingerprint) + pre-image backup.

**Salvage decision: EXECUTE** (per Q2 gates 1-4 all pass; conditional on Kim's 15-min prep window at C-9 execution time).

**Implementation order (Kim RR-4 refinement):** snapshot → 8 K-fixes (K4 deferred) → cornerstone → LDs → salvage → K4 LAST (now safe, Event_1/intro empty either way) → ride-alongs (C6/C7/C8) → final smoke → PR.

**10 LDs to file:** 6 HARD + 4 SOFT (per spec §9). C8's deploy LD `STORYBOARD_DEPLOY_PROCESS_V1` adds an 11th SOFT LD landing in C-14.

**Out of scope:** Event_1 content recovery (ships via saved scene mp4); Storyboard reorder/add/delete UI; rendered-beat grafts; Tessa's Fall recreation; Milestone unification; cleanup of `Production/scripts/.oneshot/`.

---

## 2. Pre-flight requirements (run once at session start)

```bash
# (a) On branch + at expected head
git status --short
git log --oneline -3   # expect HEAD = fafdfed Δ-architecture-tighten

# (b) Stale-cache check — spec K-finding lines still where they were
grep -n "def _handle_beat_update_text" Production/tools/production_server.py
grep -n "def _handle_bg_accept_beats"  Production/tools/production_server.py
grep -n "def _handle_bg_add_beat"      Production/tools/production_server.py
grep -n "def _assert_event_scope"      Production/tools/production_server.py
grep -n "def _find_beat_audio"         Production/tools/production_server.py
grep -n "DISPLAY_ORDER_STRICT_V1 prune" Production/tools/production_server.py
# Expected anchors: K1≈12048, K2≈9001, K3≈9279, K6≈4734, K7≈8990, K4≈1198, D5≈4083, RR-1≈2459
# If line numbers have drifted, update §3 of the spec + this doc inline before C-1.

# (c) Server staleness check
pkill -f "production_server.py.*Event" 2>/dev/null || true

# (d) Fixture pinning verified
ls -la Production/Event_e2e_fixture/storyboard_v59_prod.html
ls -la Production/Event_e2e_fixture/storyboard_v59_prod.L.json

# (e) Directus reachability (DS-8)
python3 -c "from Production.lib.directus import try_post_or_queue; print('OK')"

# (f) .recovery_audit.jsonl gitignored (will create if missing in C-7)
grep -q "^Production/.recovery_audit.jsonl$" .gitignore || echo "(will add in C-7)"
```

If any check fails, halt and surface to Kim before C-0.

---

## 3. Test pinning matrix (commit ↔ tests)

Per DS-1 + DS-2 (TDD RED → GREEN): write tests FIRST in C-1, watch CI red, then commit fixes one at a time and watch each turn green.

| Commit | Tests pinned GREEN by this commit |
|---|---|
| C-0 | (none — operational snapshot) |
| C-1 | (RED suite — all expected to fail) |
| C-2 | TVMC-K1.1, TVMC-D5.1 |
| C-3 | TVMC-K2.1, TVMC-K7.1, TVMC-K7.2 |
| C-4 | TVMC-K3.1 |
| C-5 | TVMC-K6.1 |
| C-6 | TVMC-K8.1 |
| C-7 | GR.1, GR.2, GR.3, GR.4, GR.5, GR.6, SCR.1, SCR.2, SCR.3 |
| C-8 | (manual: `mn-lds list` shows 10 architecture LDs) |
| C-9 | (manual: 18 beats land in Event_2/intro display_order; speakers canonicalized) |
| C-10 | TVMC-K4.1, TVMC-K4.2, SCR.4 (WARNING test documents expected destructive prune) |
| C-12 | (new C6 tests — Production Map per-role + 5-state glyph) |
| C-13 | (visual: Storyboard scope banner CSS render correct) |
| C-14 | (manual: deploy script self-test — rsync + sha256 verify both events) |
| C-15 | full Playwright e2e + LD-519 endpoint catalog gate + AST grep gates + sidecar regen + manual smoke on Event_1 (READ-ONLY saved video) + Event_2 (post-salvage full UI) |
| C-16 | (PR open; CI green per DS-12) |

---

## 4. Atomic commits (the order is canonical)

### C-0 — Pre-snapshot Event_1/intro state (defensive)

**Subject:** `C-0 (authoring-workflow) — defensive pre-snapshot of Event_1/intro state before K-fixes`

**Scope:** no code change; one defensive snapshot file produced.

**Procedure:**
```bash
UTC_TS=$(date -u +%Y%m%dT%H%M%SZ)
SRC="$DROPBOX/Production/Event_1/production_state.json"
DEST="$DROPBOX/Production/Event_1/.backups/state/preimage_pre_K4_${UTC_TS}.json"
mkdir -p "$(dirname "$DEST")"
cp "$SRC" "$DEST"
ls -la "$DEST"
shasum -a 256 "$SRC" "$DEST"   # confirm matching hashes
```

**Why:** if salvage in C-9 fails or skips AND any subsequent commit (specifically C-10's K4 prune in `mutate_state`) runs against Event_1/intro before Event_1/intro/beats is empty, beats 12-17 will be pruned. C-0 is the rollback safety net.

**Commit content:** add a `prod_activity_log` row via `try_post_or_queue` recording `action="defensive_snapshot_pre_K4"`, `details={src,dest,sha256_match:true,snapshot_ts}`, then commit `.backups/state/preimage_pre_K4_<UTC>.json` IF the .backups/state dir is in-tree (verify); else commit only the activity-log evidence.

**Success criteria:**
- Snapshot file present at expected path
- `shasum -a 256` confirms src + dest match
- Activity-log row visible via `mn-activity tail --filter action=defensive_snapshot_pre_K4`

**Test contract:** none (operational).

**LD pinned:** none.

**Rollback if needed:** delete the snapshot file; revert the activity-log row via `try_post_or_queue` with `action="defensive_snapshot_revert"`.

---

### C-1 — `scope_router.py` introduced + RED test suite

**Subject:** `C-1 (authoring-workflow) — scope_router.py introduced; RED tests pin K-fix prevention claims`

**Scope:**
- NEW `Production/tools/scope_router.py` (~150 lines)
- NEW `Production/tools/storyboard-v2/e2e/scope_router_red.spec.ts`
- NEW `Production/tools/storyboard-v2/e2e/beat_graft_red.spec.ts` (skeleton; turns GREEN in C-7)
- UPDATE `.github/workflows/playwright_e2e.yml` (APPEND new spec files per DS-10; do NOT use globs)

**Code-diff outline:**

`scope_router.py`:
```python
from dataclasses import dataclass
from typing import Optional, Callable

_VALID_VIDEO_ROLES = {"intro", "resolution", "standalone"}

@dataclass(frozen=True)
class ResolvedScope:
    event_id: str
    video_role: str
    beat_id: Optional[str] = None
    mutation_id: Optional[str] = None

class ScopeError(Exception):
    def __init__(self, code: str, http_status: int, detail: dict):
        self.code = code
        self.http_status = http_status
        self.detail = detail

def resolve(body: dict, server_event_dir_name: str, *, require_beat_id=False) -> ResolvedScope:
    """Validate body's scope keys against state. Raises ScopeError on violation."""
    body = body or {}
    event_id = body.get("scope_event_id") or body.get("event_id")
    if event_id is None:
        raise ScopeError("scope_required", 400, {"hint": "v59 clients must include scope_event_id."})
    if event_id != server_event_dir_name:
        raise ScopeError("scope_mismatch", 409, {
            "expected_event_id": server_event_dir_name, "got": event_id,
        })
    video_role = body.get("scope_target_video") or body.get("scope_video_role")
    if video_role is None:
        raise ScopeError("video_role_required", 400, {"hint": "v59 clients must include scope_target_video."})
    if video_role not in _VALID_VIDEO_ROLES:
        raise ScopeError("video_role_invalid", 400, {
            "valid": sorted(_VALID_VIDEO_ROLES), "got": video_role,
        })
    beat_id = body.get("beat_id")
    if require_beat_id and not beat_id:
        raise ScopeError("beat_id_required", 400, {})
    mutation_id = body.get("mutation_id")
    return ResolvedScope(event_id=event_id, video_role=video_role, beat_id=beat_id, mutation_id=mutation_id)

def mutate_partition(state_manager, scope: ResolvedScope, mutator_fn: Callable[[dict], None]) -> None:
    """Single allowed entry to partition writes. Wraps StateManager.mutate_video_state."""
    state_manager.mutate_video_state(scope.video_role, mutator_fn)

# graft() lands in C-7 with full audit/idempotency/pre-image
```

`scope_router_red.spec.ts` (PINS prevention claims; expected to FAIL until C-2..C-6 land):
- `K1` — edits to `resolution` role land in `videos.resolution.beats` not `videos.intro.beats`
- `K2` — Accept-All writes to `videos.<role>.beats`, NOT top-level `state.beats`
- `K3` — `bg_add_beat` derives segment from scope, not hardcoded event_id=2
- `K4` — beat with `display_order` excluding it gets pruned on `mutate_state` (not just `mutate_video_state`)
- `K5` — N/A in this spec; covered by `beat_graft_red.spec.ts`
- `K6` — POST without `event_id` returns 400, not 200
- `K7` — Accept-All speaker `""` does NOT default to "Guide Bird"
- `K8` — `partition.beats[bid].speaker` and `phase_1.speaker` mirror after `patch_state` writes
- `D5` — `patch_state` for trim with `scope_target_video=resolution` lands in `videos.resolution`, not `videos.intro`

**AST grep CI gate** (added in C-2 file, but pinned in C-1 spec):
```bash
# .github/workflows/playwright_e2e.yml (or sibling step):
grep -rn 'state\.setdefault("videos", *{}).setdefault("intro"' Production/tools/production_server.py \
  | grep -v "scope_router.py" | grep -v "lib/state_manager.py" \
  && exit 1 || true
grep -rn '"beats", *{}' Production/tools/production_server.py \
  | grep -v "scope_router.py" | grep -v "lib/state_manager.py" | grep -v "videos\..*\.beats" \
  && exit 1 || true
```

**Success criteria:**
- New `scope_router.py` importable: `python3 -c "from Production.tools.scope_router import resolve, mutate_partition, ScopeError; print('OK')"`
- Playwright workflow appends new spec files (NOT replacing existing entries — DS-10)
- CI red on the new RED tests as expected (DS-2 RED phase)

**Test contract:** RED suite expected to fail.

**LD pinned:** `SCOPE_ROUTER_V1` (HARD) — committed but not yet enforced until C-2..C-6.

**Rollback:** revert C-1 if `scope_router.py` import fails or CI workflow misconfigured.

---

### C-2 — K1 + D5 fix (`_handle_beat_update_text` + `patch_state._apply` route via scope_router)

**Subject:** `C-2 (authoring-workflow) — K1+D5 — _handle_beat_update_text + patch_state._apply route via scope_router; videos.intro hardcode removed`

**Scope:**
- `Production/tools/production_server.py:12048-12110` (`_handle_beat_update_text`)
- `Production/tools/production_server.py:4079-4185` (`patch_state._apply`)

**Code-diff outline:**

`_handle_beat_update_text` rewrite:
```python
def _handle_beat_update_text(self, body):
    from Production.tools import scope_router
    try:
        scope = scope_router.resolve(body, self.app.event_dir.name, require_beat_id=True)
    except scope_router.ScopeError as e:
        return self._send_json(e.http_status, {"error": e.code, **e.detail})
    new_text = body.get("text") or ""
    tts_exists = _find_beat_audio(self.app.event_dir, scope.beat_id, app=self.app) is not None
    now_iso = datetime.now(timezone.utc).isoformat()

    def update_partition(partition, _bid=scope.beat_id, _t=new_text, _stale=tts_exists, _ts=now_iso):
        beats = partition.setdefault("beats", {})
        b = beats.setdefault(_bid, {})
        old = b.get("text")
        b["text"] = _t
        b["text_last_updated_at"] = _ts
        if _stale and old != _t:
            b["text_modified_after_tts"] = True

    self.app.state.mutate_video_state(scope.video_role, update_partition)
```

`patch_state._apply` rewrite (line 4079-4185):
- Resolve target partition from `body.get("scope_target_video") or body.get("scope_video_role") or "intro"` (validated against `_VALID_VIDEO_ROLES`; 400 on invalid).
- Replace `intro_partition = state.setdefault("videos", {}).setdefault("intro", {...})` with `target_partition = state.setdefault("videos", {}).setdefault(target_video, {"video_role": target_video, "video_label": None})`.
- ALL field handlers (image_override, selected_option, trim, pause_after_ms, fade_after_ms, speaker, display_order) operate on `target_partition` not the hardcoded `intro_partition`.

**Success criteria:**
- TVMC-K1.1 GREEN (Playwright e2e): role='resolution' edit lands in `videos.resolution.beats`
- TVMC-D5.1 GREEN (Playwright e2e): role='resolution' trim lands in `videos.resolution.beats[bid].phase_1.trim_start`
- AST grep gate FROM C-1 still passes (the hardcoded literal removed in this commit)

**Test contract:** TVMC-K1.1, TVMC-D5.1 GREEN.

**LD pinned:** `SCOPE_ROUTER_V1` (HARD) — partial enforcement.

**Rollback:** revert C-2; the RED tests turn red again. No state damage (mutation channel still works for intro role; only `resolution`/`standalone` paths re-corrupt).

---

### C-3 — K2 + K7 fix (`_handle_bg_accept_beats` writes to partition; speaker canonicalized at boundary)

**Subject:** `C-3 (authoring-workflow) — K2+K7 — bg_accept_beats writes to videos.<role>.beats; speaker canonicalized at write boundary; "Guide Bird" literal removed`

**Scope:**
- `Production/tools/production_server.py:8936-9007` (`_handle_bg_accept_beats`)

**Code-diff outline:**

```python
def _handle_bg_accept_beats(self, body):
    from Production.tools import scope_router
    try:
        scope = scope_router.resolve(body, self.app.event_dir.name)
    except scope_router.ScopeError as e:
        return self._send_json(e.http_status, {"error": e.code, **e.detail})
    beats_raw = body.get("beats") or []
    bg = _bg_module()
    # Mark sidecar status accepted (lines 8956-8964 unchanged)
    # Delete L.json sidecar (lines 8967-8973 unchanged)
    # NEW: write into partition not legacy state.beats
    state_seeds = {}
    storyboard_pos = 0
    for beat in beats_raw:
        if not beat.get("accepted_image_key"):
            continue
        sb_bid = f"beat_{storyboard_pos + 1:02d}"
        canonicalized = _canonicalize_speaker(beat.get("speaker") or "")
        # ↑ DROP `or "Guide Bird"` — empty stays empty (LD-520 fail-loud at TTS)
        state_seeds[sb_bid] = {
            "speaker": canonicalized,
            "text": beat.get("dialogue_text") or "",
        }
        storyboard_pos += 1
    if not state_seeds:
        return self._send_json(200, {"ok": True, "seeded": []})

    def _seed_partition(partition, _data=state_seeds):
        pbeats = partition.setdefault("beats", {})
        pdo = partition.setdefault("display_order", [])
        for bid, fields in _data.items():
            b = pbeats.setdefault(bid, {})
            b["speaker"] = fields["speaker"]
            b["text"] = fields["text"]
            if bid not in pdo:
                pdo.append(bid)

    self.app.state.mutate_video_state(scope.video_role, _seed_partition)
    self._send_json(200, {"ok": True, "seeded": list(state_seeds.keys())})
```

**Success criteria:**
- TVMC-K2.1 GREEN: Accept-All seeds `videos.<role>.beats`, NOT top-level `state.beats`
- TVMC-K7.1 GREEN: Accept-All on beat with `speaker=""` lands `speaker=""` (NOT "Guide Bird")
- TVMC-K7.2 GREEN: Accept-All on beat with `speaker="Guide Bird"` lands `speaker="Chipper"` (canonicalized)
- AST grep gate: `grep -n 'state.setdefault("beats"' Production/tools/production_server.py | grep -v "lib/state_manager.py" | grep -v "scope_router.py"` returns 0 (or only allowlisted)

**Test contract:** TVMC-K2.1, TVMC-K7.1, TVMC-K7.2 GREEN.

**LD pinned:** `SCOPE_ROUTER_V1` (HARD), `SPEAKER_WRITE_BOUNDARY_CANONICALIZATION_V1` (HARD).

**Rollback:** revert C-3; Accept-All re-corrupts top-level state.beats.

---

### C-4 — K3 fix (`_handle_bg_add_beat` derives segment from scope)

**Subject:** `C-4 (authoring-workflow) — K3 — bg_add_beat derives BG sidecar segment from (scope.event_id, scope.video_role); arc=1/event=2/phase=pre hardcode removed`

**Scope:**
- `Production/tools/production_server.py:9264-9316` (`_handle_bg_add_beat`)
- New helper in `_bg_module()` or `bg.py`: `get_seg_entry_for_scope(scope_event_id, video_role) -> dict`

**Code-diff outline:**

```python
def _handle_bg_add_beat(self, body):
    from Production.tools import scope_router
    try:
        scope = scope_router.resolve(body, self.app.event_dir.name)
    except scope_router.ScopeError as e:
        return self._send_json(e.http_status, {"error": e.code, **e.detail})
    after_beat_id = body.get("after_beat_id")
    bg = _bg_module()
    with bg._sidecar_lock:
        sidecar = bg.read_sidecar()
        # Derive segment from scope, NOT hardcoded
        arc_number, event_id_int, phase = _resolve_bg_segment_for_scope(scope.event_id, scope.video_role)
        seg = bg.get_seg_entry(sidecar, arc_number=arc_number, event_id=event_id_int, phase=phase)
        # rest of handler unchanged (insert_after, beat_id assignment, write)
        ...

def _resolve_bg_segment_for_scope(scope_event_id: str, video_role: str) -> tuple[int, int, str]:
    """Map scope to BG sidecar (arc_number, event_id, phase). Inverse of segment-key shape."""
    # arc_number derived from scope_event_id naming convention (Event_<arc>_<event>)
    # phase derived from video_role: intro→pre, resolution→post, standalone→main
    arc_number = 1  # current single-arc deployment; refactor when multi-arc lands
    try:
        event_id_int = int(scope_event_id.replace("Event_", ""))
    except ValueError:
        raise ValueError(f"cannot parse event_id from scope_event_id={scope_event_id!r}")
    phase_map = {"intro": "pre", "resolution": "post", "standalone": "main"}
    phase = phase_map.get(video_role)
    if phase is None:
        raise ValueError(f"no BG sidecar phase mapping for video_role={video_role!r}")
    return (arc_number, event_id_int, phase)
```

**AST grep CI gate add:**
```bash
grep -rn 'arc_number=1, event_id=2, phase="pre"' Production/tools/production_server.py \
  && exit 1 || true
```

**Success criteria:**
- TVMC-K3.1 GREEN: `bg_add_beat` with `scope_event_id=Event_1, scope_target_video=intro` writes to `arc=1, event=1, phase="pre"` segment
- AST grep gate confirms hardcode removed
- Existing `bg_add_beat` callers from BgTab in `Event_2/intro` continue to work (regression check)

**Test contract:** TVMC-K3.1 GREEN.

**LD pinned:** `BG_HARDCODED_SCOPE_PURGE_V1` (HARD).

**Rollback:** revert C-4; BG add-beat re-targets Event_2 unconditionally.

---

### C-5 — K6 fix (`_assert_event_scope` defaults flip strict)

**Subject:** `C-5 (authoring-workflow) — K6 — _assert_event_scope defaults flip allow_missing=False on mutating handlers; ~30 call-site audit`

**Scope:**
- `Production/tools/production_server.py:4734-4827` (`_assert_event_scope` itself stays; defaults at call sites flip)
- ~30 call sites in `_handle_*` mutation handlers (audit during commit)

**Procedure:**

1. Grep for all `_assert_event_scope` call sites:
   ```bash
   grep -n "_assert_event_scope" Production/tools/production_server.py
   ```
2. Classify each call site:
   - **Mutation handler** (writes state): flip to `allow_missing=False, allow_missing_video_role=False`
   - **Read-only probe** (state_snapshot, event_load, production_map etc.): keep `allow_missing=True`
3. Call-site update pattern:
   ```python
   # Before:
   if not self._assert_event_scope(body):
       return
   # After (mutation handler):
   if not self._assert_event_scope(body, allow_missing=False, allow_missing_video_role=False):
       return
   ```
4. Add startup assertion in `__init__` or `serve_forever`:
   ```python
   _SCOPE_STRICT_HANDLERS = [
       "_handle_beat_update_text", "_handle_bg_accept_beats", "_handle_bg_add_beat",
       "_handle_bg_delete_beat", "_handle_bg_reorder_beats", "_handle_bg_update_beat",
       "_handle_v2_patch_state", "_handle_beat_finalize", "_handle_beat_use_as_final",
       "_handle_beat_delay", "_handle_beat_trim", "_handle_select", "_handle_assign_image",
       "_handle_animate", "_handle_lipsync_submit", "_handle_beat_graft",  # added in C-7
       # ... full list per audit
   ]
   print(f"[scope-guard] STRICT enabled on {len(_SCOPE_STRICT_HANDLERS)} mutation handlers", flush=True)
   ```

**Success criteria:**
- TVMC-K6.1 GREEN: POST `/api/beat/update_text` WITHOUT `event_id` → HTTP 400 `code:"scope_required"`
- Existing pathappPatch flows still pass (client auto-injects per LD-461; flip just turns on receiver)
- Startup log shows STRICT enabled on N handlers

**Test contract:** TVMC-K6.1 GREEN.

**LD pinned:** `SCOPE_REQUIRED_DEFAULTS_V1` (HARD).

**Rollback:** revert C-5; v58 fallback paths (which were already deprecated) re-permit silent default.

---

### C-6 — K8 fix (speaker dual-store mirror contract)

**Subject:** `C-6 (authoring-workflow) — K8 — speaker dual-store mirror contract; partition.beats[bid].speaker canonical; phase_1.speaker mirror→deprecate`

**Scope:**
- `Production/tools/production_server.py:4170-4175` (`patch_state` speaker case)
- Read-site audit for any `phase_1.speaker` direct read; wrap in `_resolve_beat_speaker(beat)` helper
- `Production/tools/production_server.py` near line 745 (`_canonicalize_speaker`): NEW helper `_resolve_beat_speaker`

**Code-diff outline:**

```python
def _resolve_beat_speaker(beat: dict) -> str:
    """Read-side canonical speaker resolution. Top-level wins; phase_1.speaker is read-compat shim."""
    s = beat.get("speaker")
    if s:
        return s
    s_phase1 = beat.get("phase_1", {}).get("speaker") or ""
    return s_phase1
```

`patch_state._apply` speaker case (line 4170-4175):
```python
elif _f == "speaker":
    canonical = _canonicalize_speaker(_v or "") or ""
    beat = beats.setdefault(_bid, {})
    beat["speaker"] = canonical                          # ← canonical write target
    beat.setdefault("phase_1", {})["speaker"] = canonical  # ← write-time mirror (read-compat shim)
```

Audit read sites — wrap each `beat["phase_1"]["speaker"]` direct read in `_resolve_beat_speaker(beat)`:
```bash
grep -n 'phase_1.*speaker\|phase_1\["speaker"\]\|phase_1.get("speaker")' Production/tools/production_server.py
```
Update each; commit each as part of C-6.

**Success criteria:**
- TVMC-K8.1 GREEN: `patch_state` speaker write lands BOTH `partition.beats[bid].speaker` AND `partition.beats[bid].phase_1.speaker` with canonicalized value
- All `phase_1.speaker` readers wrapped in `_resolve_beat_speaker`
- Existing TTS path at `production_server.py:3366` reads top-level (no change needed)

**Test contract:** TVMC-K8.1 GREEN.

**LD pinned:** `SPEAKER_DUAL_STORE_DEPRECATION_V1` (SOFT).

**Rollback:** revert C-6; dual-store divergence latent again.

---

### C-7 — Pillar 7 cornerstone `/api/beat/graft`

**Subject:** `C-7 (authoring-workflow) — Pillar 7 cornerstone — /api/beat/graft endpoint; audit JSONL + Directus mirror; idempotency; pre-image; pre-render-only`

**Scope:**
- `Production/tools/production_server.py` — NEW `_handle_beat_graft` handler
- `Production/tools/storyboard-v2/src/api/endpoints.ts` — register `beat_graft` in `MUTATION_ENDPOINTS`
- `Production/tools/scope_router.py` — extend with `graft(...)` function
- `.gitignore` — add `Production/.recovery_audit.jsonl` (gitignored — durable audit log; never committed)
- NEW `Production/tools/storyboard-v2/e2e/beat_graft.spec.ts` (replaces `beat_graft_red.spec.ts` from C-1; rename or merge per session preference)

**Endpoint shape (per spec §6.1):**

```
POST /api/beat/graft
Body: {
  source: { event_id, video_role, beat_id },
  target: { event_id, video_role, position },
  speaker_override: str | null,
  move: bool = false,
  mutation_id: str  // mandatory
}
```

**Handler skeleton:**

```python
def _handle_beat_graft(self, body):
    from Production.tools import scope_router
    # 1) Validate body shape
    src = body.get("source") or {}
    tgt = body.get("target") or {}
    move = bool(body.get("move", False))
    mutation_id = body.get("mutation_id")
    speaker_override = body.get("speaker_override")
    if not mutation_id:
        return self._send_json(400, {"error": "mutation_id_required"})

    # 2) Idempotency dedup cache
    if mutation_id in _GRAFT_DEDUP:
        return self._send_json(200, {**_GRAFT_DEDUP[mutation_id], "status": "dedup"})

    # 3) Validate target scope (server pin must equal target.event_id)
    if tgt.get("event_id") != self.app.event_dir.name:
        return self._send_json(409, {"error": "scope_mismatch",
            "expected": self.app.event_dir.name, "got": tgt.get("event_id")})

    # 4) Validate cross-event source requires --source-event flag
    cross_event = (src.get("event_id") != tgt.get("event_id"))
    if cross_event:
        if self.app.source_event_dir is None or self.app.source_event_dir.name != src.get("event_id"):
            return self._send_json(409, {"error": "cross_event_requires_explicit_source",
                "hint": "restart server with --source-event Production/<src_event>"})
        source_event_dir = self.app.source_event_dir
    else:
        source_event_dir = self.app.event_dir

    # 5) Load source state; locate source beat
    source_state = _load_event_state(source_event_dir)
    src_partition = source_state.get("videos", {}).get(src.get("video_role"), {})
    src_beats = src_partition.get("beats", {})
    src_beat = src_beats.get(src.get("beat_id"))
    if src_beat is None:
        return self._send_json(404, {"error": "source_beat_not_found"})

    # 6) Pre-render-only invariant (RR-1 mitigation)
    phase_1 = src_beat.get("phase_1", {})
    if phase_1.get("status") == "completed":
        return self._send_json(400, {"error": "graft_pre_render_only",
            "reason": "source.phase_1.status==completed"})
    for opt in phase_1.get("options", []) or []:
        if opt.get("file") or opt.get("lipsync_task_id"):
            return self._send_json(400, {"error": "graft_pre_render_only",
                "reason": "source.phase_1.options[].file or lipsync_task_id non-empty"})

    # 7) Pre-image snapshots
    utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pre_image_paths = []
    for ev_dir in {source_event_dir, self.app.event_dir}:
        bdir = ev_dir / ".backups" / "state"
        bdir.mkdir(parents=True, exist_ok=True)
        bpath = bdir / f"{utc}_pre_graft_{mutation_id}.json"
        atomic_json_write(str(bpath), _load_event_state(ev_dir))
        pre_image_paths.append(str(bpath))

    # 8) Resolve final speaker
    raw_speaker = speaker_override if speaker_override is not None else src_beat.get("speaker", "")
    canonical_speaker = _canonicalize_speaker(raw_speaker or "") or ""
    speaker_source = ("override" if speaker_override is not None else
                      ("alias:" + raw_speaker + "->" + canonical_speaker
                       if canonical_speaker and raw_speaker.lower() != canonical_speaker.lower()
                       else ("untouched" if canonical_speaker else "empty")))

    # 9) Content fingerprint check (replay safety)
    target_state = _load_event_state(self.app.event_dir)
    tgt_partition = target_state.setdefault("videos", {}).setdefault(tgt.get("video_role"),
        {"video_role": tgt.get("video_role"), "video_label": None})
    tgt_beats_existing = tgt_partition.get("beats", {})
    if src.get("beat_id") in tgt_beats_existing:
        existing = tgt_beats_existing[src.get("beat_id")]
        if (existing.get("text") == src_beat.get("text")
            and existing.get("speaker") == canonical_speaker):
            result = {"ok": True, "status": "already_present", "beat_id": src.get("beat_id")}
            _GRAFT_DEDUP[mutation_id] = result
            return self._send_json(200, result)

    # 10) Apply target write via mutate_video_state (prune runs)
    target_position = tgt.get("position")
    def _insert_target(partition, _bid=src.get("beat_id"), _payload=src_beat,
                       _spk=canonical_speaker, _pos=target_position):
        pbeats = partition.setdefault("beats", {})
        pdo = partition.setdefault("display_order", [])
        new_beat = dict(_payload)
        new_beat["speaker"] = _spk
        new_beat.setdefault("phase_1", {})["speaker"] = _spk  # mirror per K8
        pbeats[_bid] = new_beat
        if _bid in pdo:
            pdo.remove(_bid)
        clamped_pos = max(0, min(_pos if _pos is not None and _pos >= 0 else len(pdo), len(pdo)))
        pdo.insert(clamped_pos, _bid)
    self.app.state.mutate_video_state(tgt.get("video_role"), _insert_target)

    # 11) Optional move=true: delete source beat (cross-event uses path-based atomic write)
    if move:
        if cross_event:
            # cross-event delete: write source state directly via path resolution
            src_state_now = _load_event_state(source_event_dir)
            src_partition_now = src_state_now.setdefault("videos", {}).setdefault(src.get("video_role"), {})
            src_partition_now.get("beats", {}).pop(src.get("beat_id"), None)
            src_do = src_partition_now.get("display_order")
            if isinstance(src_do, list) and src.get("beat_id") in src_do:
                src_do.remove(src.get("beat_id"))
            atomic_json_write(str(source_event_dir / "production_state.json"), src_state_now)
        else:
            # same-event delete: scope_router.mutate_partition
            def _delete_source(partition, _bid=src.get("beat_id")):
                partition.get("beats", {}).pop(_bid, None)
                do = partition.get("display_order")
                if isinstance(do, list) and _bid in do:
                    do.remove(_bid)
            self.app.state.mutate_video_state(src.get("video_role"), _delete_source)

    # 12) Audit log: file JSONL + Directus mirror
    target_state_after = _load_event_state(self.app.event_dir)
    audit_row = {
        "schema_version": 1, "action": "beat_graft",
        "ts": datetime.now(timezone.utc).isoformat(),
        "mutation_id": mutation_id,
        "source": {"event_id": src.get("event_id"), "video_role": src.get("video_role"),
                   "beat_id": src.get("beat_id")},
        "target": {"event_id": tgt.get("event_id"), "video_role": tgt.get("video_role"),
                   "beat_id": src.get("beat_id"),
                   "position": target_position,
                   "post_image_version": target_state_after.get("version", 0)},
        "move": move, "cross_event": cross_event,
        "speaker_resolved": canonical_speaker, "speaker_source": speaker_source,
        "actor": "production_server_v59",
        "pre_image_paths": pre_image_paths,
        "ok": True,
    }
    audit_file = AUDIT_LOG_PATH  # = Production/.recovery_audit.jsonl
    with open(audit_file, "a") as f:
        f.write(json.dumps(audit_row) + "\n")
    try:
        try_post_or_queue("prod_activity_log", {"action": "beat_graft", "details": audit_row,
                                                "performed_by": "production_server_v59"})
    except Exception:
        pass  # JSONL is durable source of truth; Directus mirror is best-effort

    result = {"ok": True, "status": ("moved" if move else "copied"),
              "pre_image_paths": pre_image_paths,
              "audit_log_path": str(audit_file),
              "target_display_order": (target_state_after.get("videos", {}).get(tgt.get("video_role"), {}).get("display_order", [])),
              "beat_id": src.get("beat_id")}
    _GRAFT_DEDUP[mutation_id] = result
    return self._send_json(200, result)
```

**Add `--source-event` CLI flag** to server's argparse:
```python
parser.add_argument("--source-event", type=Path, default=None,
                    help="Optional source event_dir for cross-event graft. Required when /api/beat/graft body's source.event_id != server-pinned event.")
self.app.source_event_dir = args.source_event
```

**`endpoints.ts` extension:**
```typescript
export const MUTATION_ENDPOINTS = new Set<MutationKey>([
  // ... existing entries ...
  "beat_graft",
]);
```

**`scope_router.py` extension** (the `graft` function delegates to `_handle_beat_graft` semantically; or expose as a state-manager-level helper if preferred — lighter approach is to keep handler-level and skip a `scope_router.graft` helper this commit).

**Add `AUDIT_LOG_PATH` constant** + `_GRAFT_DEDUP` LRU cache (size 256, same shape as `_PATCH_STATE_DEDUP:4072`).

**Add `Production/.recovery_audit.jsonl` to `.gitignore`.**

**Success criteria:**
- GR.1 GREEN: same-event same-role graft writes target; pre-image present; audit JSONL row + Directus mirror; idempotent replay returns dedup
- GR.2 GREEN: missing mutation_id → HTTP 400
- GR.3 GREEN: source beat missing → HTTP 404 + audit row `beat_graft_failed`
- GR.4 GREEN: source beat with `phase_1.status="completed"` → HTTP 400 `code:"graft_pre_render_only"`
- GR.5 GREEN: cross-event graft without `--source-event` → HTTP 409 `code:"cross_event_requires_explicit_source"`
- GR.6 GREEN: `move=true` deletes source after target write
- SCR.3 GREEN: cross-event graft against Event_1 + Event_2 fixture mirror succeeds; both pre-images present; audit log + Directus mirror records `move:true`

**Test contract:** GR.1-GR.6 + SCR.3 GREEN.

**LD pinned:** `BEAT_GRAFT_RECOVERY_MECHANISM_V1` (HARD).

**Rollback:** revert C-7; recovery mechanism gone but no state damage (handler is opt-in).

---

### C-8 — Register architecture LDs in Directus

**Subject:** `C-8 (authoring-workflow) — register 10 architecture LDs in Directus prod_locked_decisions`

**Scope:** Directus inserts via `Production/lib/directus.try_post_or_queue` per DS-8.

**LDs to register** (subjects + severity per spec §9):

```
SCOPE_ROUTER_V1                          HARD  server+client
SCOPE_REQUIRED_DEFAULTS_V1               HARD  server
DISPLAY_ORDER_STRICT_V2                  HARD  server
BG_HARDCODED_SCOPE_PURGE_V1              HARD  server
SPEAKER_WRITE_BOUNDARY_CANONICALIZATION_V1  HARD  server
BEAT_GRAFT_RECOVERY_MECHANISM_V1         HARD  server+client
SPEAKER_DUAL_STORE_DEPRECATION_V1        SOFT  server
SPEAKER_CANONICALIZATION_TO_CHIPPER_V1   SOFT  server
EVENT_1_SHIPS_VIA_SAVED_VIDEO_V1         SOFT  content+architecture
STORYBOARD_REORDER_UI_DEFERRED_V1        SOFT  UX
```

**Procedure per LD (DS-8 + DS-9):**
```python
from Production.lib.directus import try_post_or_queue, get_field_choices
# (a) Verify enum choices
sev_choices = get_field_choices("prod_locked_decisions", "severity")
assert "HARD" in sev_choices and "SOFT" in sev_choices, "DS-9 enum drift"
# (b) Insert with explicit fields per DS-8 schema reference
ld_payload = {
    "code": "SCOPE_ROUTER_V1",
    "severity": "HARD",
    "scope_domain": "production",   # per DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE
    "task_category": "all",          # if no specific fit per DS-8
    "decision_text": "All beat-touching mutations route through scope_router.resolve + scope_router.mutate_partition. Direct state.setdefault('videos',{}).setdefault('intro'...) and direct state.setdefault('beats'...) banned outside scope_router.py and StateManager. AST grep CI gate enforces. Subsumes K1, K2, K3, D5 prevention.",
    "rationale": "Phase 4 synthesis; dual-Opus tech-spec session 2026-05-05; Cursor APPROVE 2026-05-06.",
    "linked_session": "post-redeploy-bug-triage-authoring-workflow-tech-spec-2026-05-05",
}
res = try_post_or_queue("prod_locked_decisions", ld_payload)
# (c) Read-back per DS-8
read_back = directus.get(f"prod_locked_decisions/{res['id']}")
assert read_back.severity == "HARD" and read_back.code == "SCOPE_ROUTER_V1"
```

Repeat for each of the 10 LDs.

**Success criteria:**
- `mn-lds list` shows all 10 architecture LDs (1 of which is C-14's deploy LD if you batch C-14 LD here — recommend NOT, file C-14 LD with C-14 commit)
- Each LD has matching `decision_text` from spec §9

**Test contract:** manual; `mn-lds list | grep -E "SCOPE_ROUTER_V1|SCOPE_REQUIRED_DEFAULTS_V1|...|STORYBOARD_REORDER_UI_DEFERRED_V1"` returns 10 matches

**LD pinned:** all 10 LDs themselves.

**Rollback:** revert each Directus row via `try_post_or_queue` with `status="archived"` (per existing convention).

---

### C-9 — Salvage execution (per spec §7 EXECUTE per Q2 gates)

**Subject:** `C-9 (authoring-workflow) — Salvage — redistribute 17 Event-2 beats from Event_1/intro to Event_2/intro via /api/beat/graft; speaker canonicalize 3 affected beats; orphan stub patch_state for Event_2/beat_04`

**Scope:** one-shot script + manual operator step.

**Pre-execution Kim-prep window (Q2 gate 4 timebox = 15 min):**

Kim hand-orders the 17 source beats into a target order in a JSON map. If prep exceeds 15 minutes, **SALVAGE SKIPS** — see §6 below.

**Salvage script template** (`Production/scripts/.oneshot/redistribute_event2_beats_<UTC>.py`):

```python
#!/usr/bin/env python3
"""C-9 salvage script — redistribute 17 Event-2 narrative beats from Event_1/intro to Event_2/intro.
Pre-conditions:
  - Server restarted with --event-dir Production/Event_2 --source-event Production/Event_1
  - C-1..C-8 architecture commits landed
  - C-7 /api/beat/graft endpoint live
Bounded-effort gate per spec §7.1: gates 1-4 PASS. Estimated 20-30 min total session time.
"""
import json, requests, uuid, sys
from pathlib import Path

SERVER = "http://localhost:8001"
ARC = 1
SOURCE_EVENT = "Event_1"
TARGET_EVENT = "Event_2"
ROLE = "intro"

# Map populated by Kim during 15-min prep window
# Format: list of (target_position, source_beat_id, optional_speaker_override)
# Speaker override = None means inherit (will canonicalize Guide Bird → Chipper at write boundary)
MAP = [
    # (0, "beat_01", None),
    # (1, "beat_02", None),
    # ...
    # (16, "beat_17", None),
]

def graft_one(target_pos: int, source_bid: str, spk_override: str | None) -> dict:
    body = {
        "source": {"event_id": SOURCE_EVENT, "video_role": ROLE, "beat_id": source_bid},
        "target": {"event_id": TARGET_EVENT, "video_role": ROLE, "position": target_pos},
        "speaker_override": spk_override,
        "move": True,
        "mutation_id": str(uuid.uuid4()),
        # client-side scope keys (auto-injected by pathappPatch in production)
        "scope_event_id": TARGET_EVENT,
        "scope_target_video": ROLE,
    }
    r = requests.post(f"{SERVER}/api/beat/graft", json=body, timeout=30)
    r.raise_for_status()
    return r.json()

def main():
    if not MAP:
        print("ERROR: MAP is empty — Kim's 15-min prep step not done. Halt.")
        return 1
    print(f"[C-9 salvage] {len(MAP)} beats; source={SOURCE_EVENT}/{ROLE}, target={TARGET_EVENT}/{ROLE}")
    for target_pos, source_bid, spk in MAP:
        result = graft_one(target_pos, source_bid, spk)
        print(f"  pos={target_pos:2d} {source_bid} → {result['status']:10s} pre_image={result['pre_image_paths'][-1]}")
    # Orphan stub: Event_2/beat_04 text stays; speaker fix to "Luna" via patch_state
    orph = requests.post(f"{SERVER}/api/v2/patch_state", json={
        "field": "speaker", "value": "Luna",
        "beat_id": "beat_04",
        "scope_event_id": TARGET_EVENT, "scope_target_video": ROLE,
        "expected_version": 0,  # will be re-fetched server-side
    })
    orph.raise_for_status()
    print(f"  orphan stub Event_2/beat_04 speaker=Luna applied")
    print("[C-9 salvage] complete; verify Event_2/intro display_order has 18 entries (17 grafts + beat_04 stub)")

if __name__ == "__main__":
    sys.exit(main() or 0)
```

**Operator procedure:**

1. Stop server: `pkill -f "production_server.py.*Event"`
2. Restart with cross-event flag:
   ```bash
   python3 Production/tools/production_server.py \
     --event-dir Production/Event_2 \
     --source-event Production/Event_1 &
   ```
3. Kim populates `MAP` in the script during prep window (≤ 15 min)
4. Run `python3 Production/scripts/.oneshot/redistribute_event2_beats_<UTC>.py`
5. Verify Event_2/intro display_order has 18 entries
6. Verify speakers canonicalized to "Chipper" for the 3 affected beats (`beat_10/13/17` source)
7. Stop server; restart WITHOUT `--source-event` flag back to default Event_2 pin
8. Smoke test: load v59 client; confirm StoryboardTab renders 18 beats; reload; confirm persistence

**Success criteria:**
- Event_2/production_state.json has `videos.intro.beats` with 18 entries
- Event_2/intro display_order length = 18
- Speakers canonicalized (no `"Guide Bird"` literal remains; `_resolve_beat_speaker` returns `"Chipper"` for the 3 affected beats)
- Event_1/production_state.json has `videos.intro.beats == {}` and `videos.intro.display_order == []`
- Audit JSONL `Production/.recovery_audit.jsonl` has 17 graft rows + 1 patch_state row
- Pre-image backups under both `Event_1/.backups/state/` and `Event_2/.backups/state/`
- Activity log (Directus) mirrored

**Test contract:** manual verification.

**LD pinned:** none (operational; relies on `BEAT_GRAFT_RECOVERY_MECHANISM_V1` from C-7).

**Rollback:** restore Event_1 + Event_2 from pre-image backups (paths logged in audit JSONL); re-run after fix.

---

### C-9b — Salvage SKIP fallback (only if Q2 gate 4 breaches)

If Kim's prep window exceeds 15 min OR she chooses to skip:

**Subject:** `C-9b (authoring-workflow) — Salvage SKIP — clear Event_1/intro and Event_2/intro partitions; Kim re-authors Event 2 from skeleton`

**Procedure:**

1. Stop server
2. One-shot script `Production/scripts/.oneshot/clear_event_1_intro_and_event_2_intro_<UTC>.py`:
   ```python
   # Read pre-image backups (C-0 snapshot)
   # Apply mutate_partition to set partition.beats={} and partition.display_order=[]
   # Write activity log row action="salvage_skipped" with reasoning
   ```
3. Restart server
4. Kim re-authors Event 2 from skeleton dialogue when ready

**Success criteria:**
- Event_1/intro/beats == {}, display_order == []
- Event_2/intro/beats == {}, display_order == []
- Audit row `salvage_skipped` in Directus + JSONL

**Rollback:** restore from C-0 defensive snapshot at `Event_1/.backups/state/preimage_pre_K4_<UTC>.json`.

---

### C-10 — K4 fix (DISPLAY_ORDER_STRICT_V2 defense-in-depth in `mutate_state`)

**Subject:** `C-10 (authoring-workflow) — K4 — DISPLAY_ORDER_STRICT_V2 — defense-in-depth prune in StateManager.mutate_state`

**Scope:**
- `Production/tools/production_server.py` — `StateManager.mutate_state` (lines 1021-1170 vicinity); ADD post-write prune

**Code-diff outline:**

```python
def mutate_state(self, mutator_fn):
    """Existing impl ... add post-write defense-in-depth prune."""
    # ... existing read+mutate+write ...
    # POST-WRITE DEFENSE-IN-DEPTH PRUNE (DISPLAY_ORDER_STRICT_V2)
    # Even if a future handler bypasses mutate_video_state, this catches the bug class.
    state = self._read_state()  # re-read to get post-mutator state
    changed = False
    for role, partition in (state.get("videos") or {}).items():
        if not isinstance(partition, dict):
            continue
        do = partition.get("display_order")
        if not isinstance(do, list):
            continue
        allowed = set(do)
        beats = partition.get("beats")
        if not isinstance(beats, dict):
            continue
        for bid in list(beats.keys()):
            if bid not in allowed:
                del beats[bid]
                changed = True
    if changed:
        self._atomic_write(state)
    # ... return original mutator return value ...
```

**Why C-10 last:** SCR.4 WARNING test documents the destructive pruning. Once C-10 lands, any `mutate_state` call against `Event_1/intro` (or any partition with `len(beats) > len(display_order)`) prunes the orphans. Salvage in C-9 must happen FIRST so Event_1/intro/beats == {} → no orphans to prune.

**Success criteria:**
- TVMC-K4.1 GREEN: state with `display_order=["beat_01"], beats={beat_01,beat_02}` + any `mutate_state` call → post-call beats == `{beat_01}`
- TVMC-K4.2 GREEN: AST grep gate from C-1 still passes
- SCR.4 documents (not asserts) destructive prune behavior

**Test contract:** TVMC-K4.1, TVMC-K4.2 GREEN; SCR.4 WARNING documented.

**LD pinned:** `DISPLAY_ORDER_STRICT_V2` (HARD).

**Rollback:** revert C-10; asymmetric prune returns. C-0 snapshot only matters as rollback if salvage in C-9 also failed AND beats were lost; otherwise C-10 has no destructive effect on already-clean partitions.

---

### C-12 — Ride-along: C6 — Production Map per-role status columns + 5-state glyph

**Subject:** `C-12 (ride-along C6) — Production Map per-role status columns; 5-state glyph rule per post-redeploy v2 §3.3 Part 2`

**Scope:**
- `Production/tools/storyboard-v2/src/components/ProductionMapTab.tsx` — replace single Storyboard column with per-role columns (Intro, Phase A, Phase B, Resolution, Final Concat)
- `Production/tools/production_server.py:_handle_production_map` (~line 8508) — extend on-disk artifact scan per role; preserve picker-spec R3 (no `prod_modules` schema migration)

**Code-diff outline:**

ProductionMapTab.tsx — replace existing `<th>Storyboard</th>` column with 5 columns:
```tsx
<th>Intro</th>
<th>Phase A</th>
<th>Phase B</th>
<th>Resolution</th>
<th>Final</th>
```
Each row renders the 5-state glyph per role per `state.videos.<role>` partition presence:
- Partition absent on disk → `—` (em dash, n/a)
- Partition present + `display_order = []` → `○` (empty)
- Partition present + display_order populated, no completed mp4 → `◐` (in progress)
- Partition present + completed mp4 → `●` (complete)
- Partition present + completed mp4 + final concat → `★` (final)

Server `_handle_production_map` joins existing `prod_modules` row + on-disk artifacts; extend the scan to check per-role artifact files (intro_atomic.mp4, phase_a_stitched.mp4, phase_b_lipsync.mp4, resolution_atomic.mp4, final_atomic.mp4 per filenames-on-disk audit at session start).

**Picker-spec R3 boundary preserved:** NO `prod_modules` schema migration; per-role status DERIVED from on-disk artifacts only.

**Success criteria:**
- New TVMC-C6 Playwright test: load Production Map; verify each row shows 5-glyph state correctly per fixture state
- No `prod_modules` schema migration (verify via Directus schema diff)
- Picker spec R3 still satisfied

**Test contract:** new TVMC-C6 GREEN.

**LD pinned:** none (post-redeploy v2 already has the design; this commit ships it).

**Rollback:** revert C-12; Production Map reverts to single Storyboard column.

---

### C-13 — Ride-along: C7 — CSS for `.mn-video-selector`

**Subject:** `C-13 (ride-along C7) — CSS for .mn-video-selector mirroring .mn-event-selector pattern`

**Scope:**
- `Production/tools/storyboard-v2/src/app.css` — add `.mn-video-selector` rules

**Code-diff outline:** mirror existing `.mn-event-selector` block. Read existing block; copy class name; rename selector. Trivial.

**Success criteria:**
- Visual: scope banner `.mn-video-selector` renders identically to `.mn-event-selector` (Playwright snapshot or manual smoke)

**Test contract:** visual / manual.

**LD pinned:** none.

**Rollback:** revert C-13; CSS class falls back to default.

---

### C-14 — Ride-along: C8 — comprehensive deploy script + LD `STORYBOARD_DEPLOY_PROCESS_V1`

**Subject:** `C-14 (ride-along C8) — Production/scripts/deploy_storyboard_v59.sh — comprehensive rsync mirror with sha256 verify + auto-restart; LD STORYBOARD_DEPLOY_PROCESS_V1`

**Scope:**
- NEW `Production/scripts/deploy_storyboard_v59.sh`
- Directus insert: SOFT LD `STORYBOARD_DEPLOY_PROCESS_V1`

**Script outline (`deploy_storyboard_v59.sh`):**

```bash
#!/usr/bin/env bash
set -euo pipefail

# Sources (canonical CODE per LD-505)
SRC_TOOLING="/Users/kimberlysmith/Projects/mindfulnest-tooling"

# Targets (canonical CONTENT/STATE per LD-505 — Dropbox tree)
DEST_DROPBOX="/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"

UTC_TS=$(date -u +%Y%m%dT%H%M%SZ)

# (a) Pre-deploy snapshot of dest tree subset (timestamped backup)
SNAPSHOT_DIR="$DEST_DROPBOX/.deploy_backups/$UTC_TS"
mkdir -p "$SNAPSHOT_DIR"
for sub in Production/tools Production/lib Production/scripts; do
    if [[ -d "$DEST_DROPBOX/$sub" ]]; then
        rsync -a "$DEST_DROPBOX/$sub/" "$SNAPSHOT_DIR/$sub/"
    fi
done

# (b) Atomic mirror per directory (tooling repo → Dropbox)
for sub in Production/tools Production/lib Production/scripts; do
    rsync -a --delete \
        "$SRC_TOOLING/$sub/" \
        "$DEST_DROPBOX/$sub/" \
        | tee -a "$SNAPSHOT_DIR/rsync_${sub//\//_}.log"
done

# (c) dist/index.html (built artifact) — copy if exists
if [[ -f "$SRC_TOOLING/Production/tools/storyboard-v2/dist/index.html" ]]; then
    cp "$SRC_TOOLING/Production/tools/storyboard-v2/dist/index.html" \
       "$DEST_DROPBOX/Production/tools/storyboard-v2/dist/index.html"
fi

# (d) Per-file sha256 verification (sample critical files)
for sub in \
    "Production/tools/production_server.py" \
    "Production/tools/scope_router.py" \
    "Production/tools/storyboard-v2/src/api/endpoints.ts" \
    "Production/tools/storyboard-v2/src/api/client.ts"
do
    SRC_HASH=$(shasum -a 256 "$SRC_TOOLING/$sub" | awk '{print $1}')
    DST_HASH=$(shasum -a 256 "$DEST_DROPBOX/$sub" | awk '{print $1}')
    if [[ "$SRC_HASH" != "$DST_HASH" ]]; then
        echo "FATAL sha256 mismatch on $sub" >&2
        exit 1
    fi
    echo "[verify] $sub  $SRC_HASH"
done

# (e) Auto-restart production_server.py if mtime changed
SRC_MTIME=$(stat -f %m "$SRC_TOOLING/Production/tools/production_server.py")
DST_MTIME=$(stat -f %m "$DEST_DROPBOX/Production/tools/production_server.py")
if pgrep -f "production_server.py" >/dev/null; then
    echo "[deploy] production_server.py running; restarting..."
    pkill -f "production_server.py" || true
    sleep 1
fi

# (f) Auto-launch (per Kim's earlier authorization in Δ-C5.5-Y)
EVENT_DIR="${MN_EVENT_DIR:-Production/Event_1}"
echo "[deploy] launching production_server.py with --event-dir $EVENT_DIR ..."
cd "$DEST_DROPBOX"
python3 "$DEST_DROPBOX/Production/tools/production_server.py" \
    --event-dir "$EVENT_DIR" \
    > "$DEST_DROPBOX/.deploy_backups/$UTC_TS/server.log" 2>&1 &
sleep 2
if ! pgrep -f "production_server.py.*--event-dir $EVENT_DIR" >/dev/null; then
    echo "FATAL server failed to launch — see log $SNAPSHOT_DIR/server.log" >&2
    exit 1
fi
echo "[deploy] server launched; snapshot at $SNAPSHOT_DIR"
```

**LD `STORYBOARD_DEPLOY_PROCESS_V1` (SOFT):**

```
code: STORYBOARD_DEPLOY_PROCESS_V1
severity: SOFT
scope_domain: production
decision_text: |
  Deploy of v59 storyboard tool from tooling repo to Dropbox runtime tree
  goes through Production/scripts/deploy_storyboard_v59.sh ONLY. Manual partial
  deploys (cp single file, manual rsync of one subdir, etc.) are FORBIDDEN —
  they are how the post-redeploy bug class (C1/C5/C2-bundle scrambles)
  arose. The deploy script:
    (a) timestamps a pre-deploy backup of the dest subset
    (b) atomic-mirrors Production/tools, Production/lib, Production/scripts via rsync
    (c) verifies critical-file sha256 match between source and dest post-mirror
    (d) auto-restarts production_server.py if mtime changed; auto-launches with --event-dir
  Manual deploys may be used for emergency revert (restore from .deploy_backups/<ts>/)
  or for surgical hotfix only with Kim's explicit case-by-case approval.
rationale: |
  Δ-C5.5-Y framing 2026-05-04: post-redeploy bug-triage discovered scrambled
  state across Event_1 + Event_2 caused in part by partial deploys that
  shipped only some of the storyboard files, leaving runtime in inconsistent
  shape. Comprehensive deploy script ensures the full code surface lands
  atomically per LD-505 boundary.
```

**Success criteria:**
- `bash Production/scripts/deploy_storyboard_v59.sh` runs end-to-end without error from a freshly-edited tooling repo
- pre-deploy snapshot present at `$DEST_DROPBOX/.deploy_backups/<UTC>/`
- sha256 verify passes on the 4 critical files
- production_server.py running on `Event_1` after script completes
- Activity log row `action="storyboard_deploy"` with `details={ts, snapshot_dir, files_synced, sha_verified, server_pid}` per DS-8

**Test contract:** manual self-test of deploy script.

**LD pinned:** `STORYBOARD_DEPLOY_PROCESS_V1` (SOFT) — register via `try_post_or_queue` + read-back per DS-8.

**Rollback:** restore from `.deploy_backups/<UTC>/` snapshot via reverse rsync; restart server with old version.

---

### C-15 — Final smoke (run via the new C-14 deploy script as self-validation)

**Subject:** `C-15 (authoring-workflow) — Final smoke — full e2e + LD-519 catalog gate + AST grep gates + sidecar regen + manual smoke on Event_1 (saved video) + Event_2 (post-salvage)`

**Procedure:**

1. **Self-validation: run C-14 deploy script** to ship all C-1..C-14 changes from tooling repo to Dropbox runtime. Exit 0 expected.

2. **CI smoke:**
   ```bash
   cd Production/tools/storyboard-v2
   npx playwright test --project=chromium  # full e2e suite
   # Confirm 91+ existing tests + new K-tests + GR + SCR all GREEN
   ```

3. **LD-519 endpoint catalog gate:**
   ```bash
   bash .github/scripts/verify_mutation_channel_invariant_gate.sh
   # Expects: every server _handle_*mutating route is in MUTATION_ENDPOINTS
   ```

4. **AST grep gates** (from C-1, C-3, C-4):
   ```bash
   # K1+D5: hardcoded videos.intro literal banned
   grep -rn 'state\.setdefault("videos", *{}).setdefault("intro"' Production/tools/production_server.py \
     | grep -v "scope_router.py" | grep -v "lib/state_manager.py" \
     | { ! grep -q .; }
   # K2: top-level state.beats banned outside router
   grep -rn '"beats", *{}' Production/tools/production_server.py \
     | grep -v "scope_router.py" | grep -v "lib/state_manager.py" | grep -v "videos\." \
     | { ! grep -q .; }
   # K3: hardcoded BG segment banned
   grep -rn 'arc_number=1, event_id=2, phase="pre"' Production/tools/production_server.py \
     | { ! grep -q .; }
   ```

5. **Sidecar regen check:** trigger any beat mutation; confirm `<storyboard>.L.json` regenerates per LD-459 UNIVERSAL_AUTOSAVE_V1.

6. **Manual smoke Event_1 (READ-ONLY):** load v59 client; confirm Event_1's saved scene mp4 (`Event_1/intro/scene_intro_*.mp4`) plays via existing stitcher path; confirm StoryboardTab renders empty (per `EVENT_1_SHIPS_VIA_SAVED_VIDEO_V1` SOFT LD); no architectural error.

7. **Manual smoke Event_2 (post-salvage):** load v59 client; confirm StoryboardTab renders 18 beats; reload; persistence intact; confirm BG add-beat with role='intro' lands in correct segment (K3 fix); confirm beat-text edit with role='resolution' lands in `videos.resolution.beats` (K1 fix; smoke against a fresh test beat in resolution role).

8. **Activity log review:**
   - Salvage: 17 graft rows + 1 patch_state row at `Production/.recovery_audit.jsonl` and Directus `prod_activity_log`
   - LDs: 11 rows in `prod_locked_decisions` (10 architecture + 1 deploy)
   - Defensive snapshot row from C-0

**Success criteria:** all 8 steps PASS.

**Test contract:** full TVMC-K + GR + SCR matrix GREEN; new C6 test GREEN; deploy script self-test GREEN.

**LD pinned:** none (verification commit).

**Rollback:** if any step fails, halt and surface to Kim. Per DS-12, fix the underlying issue and re-commit; do NOT bypass the gate.

---

### C-16 — PR open against main with summary

**Subject:** `C-16 (authoring-workflow) — Open PR against main — bundle B (post-redeploy authoring-workflow architecture + ride-alongs C6/C7/C8)`

**Procedure:**

1. Verify branch is at expected head (C-15 complete, all green)
2. Push branch: `git push -u origin claude/post-redeploy-bug-triage`
3. Open PR via `gh pr create` with body containing:

```
## Summary

Authoring-workflow architecture (SR+G v1) per dual-Opus tech-spec
session 2026-05-05/06 (Cursor APPROVE 2026-05-06). Plus ride-along
deferred bundle items C6/C7/C8.

Architecture commits:
- C-0: Defensive pre-snapshot
- C-1: scope_router.py introduced + RED tests pinned
- C-2: K1+D5 — partition resolution from request, not hardcode
- C-3: K2+K7 — Accept-All writes to v3 partition; speaker canonicalized
- C-4: K3 — bg_add_beat derives segment from scope
- C-5: K6 — _assert_event_scope strict defaults
- C-6: K8 — speaker dual-store mirror contract
- C-7: Pillar 7 cornerstone /api/beat/graft (audit + idempotency + pre-image + pre-render-only)
- C-8: 10 architecture LDs filed
- C-9: Salvage — 17 Event-2 beats redistributed via beat_graft (move=true)
- C-10: K4 — DISPLAY_ORDER_STRICT_V2 defense-in-depth prune in mutate_state

Ride-along commits (deferred from post-redeploy bundle):
- C-12: C6 — Production Map per-role status columns + 5-state glyph
- C-13: C7 — CSS for .mn-video-selector
- C-14: C8 — comprehensive deploy script + LD STORYBOARD_DEPLOY_PROCESS_V1

Smoke + PR:
- C-15: Final smoke (run via C-14 deploy script)
- C-16: this PR

## Spec
Production/docs/STORYBOARD_V59_AUTHORING_WORKFLOW_SPEC_v2.md (Cursor APPROVE 2026-05-06)

## Handoff
Production/docs/STORYBOARD_V59_AUTHORING_WORKFLOW_HANDOFF.md

## Test plan
- [x] All 91+ existing Playwright tests GREEN
- [x] TVMC-K1.1, K2.1, K3.1, K4.1, K4.2, K6.1, K7.1, K7.2, K8.1, D5.1 GREEN
- [x] GR.1, GR.2, GR.3, GR.4, GR.5, GR.6 GREEN
- [x] SCR.1, SCR.2, SCR.3 GREEN; SCR.4 documents expected destructive prune
- [x] LD-519 endpoint catalog gate passes
- [x] AST grep gates (K1+D5, K2, K3) pass
- [x] Sidecar regen verified (LD-459)
- [x] Manual smoke Event_1 (saved video) + Event_2 (post-salvage 18 beats render)
- [x] Salvage activity log 17 grafts + 1 patch_state at Production/.recovery_audit.jsonl + Directus prod_activity_log
- [x] 11 LDs registered in prod_locked_decisions

## LDs filed
SCOPE_ROUTER_V1 (HARD), SCOPE_REQUIRED_DEFAULTS_V1 (HARD), DISPLAY_ORDER_STRICT_V2 (HARD), BG_HARDCODED_SCOPE_PURGE_V1 (HARD), SPEAKER_WRITE_BOUNDARY_CANONICALIZATION_V1 (HARD), BEAT_GRAFT_RECOVERY_MECHANISM_V1 (HARD), SPEAKER_DUAL_STORE_DEPRECATION_V1 (SOFT), SPEAKER_CANONICALIZATION_TO_CHIPPER_V1 (SOFT), EVENT_1_SHIPS_VIA_SAVED_VIDEO_V1 (SOFT), STORYBOARD_REORDER_UI_DEFERRED_V1 (SOFT), STORYBOARD_DEPLOY_PROCESS_V1 (SOFT)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

**Success criteria:**
- PR opened; URL surfaced
- CI green on the PR
- Kim assigns reviewer + Cursor handoff per existing convention

---

## 5. Rollback procedures (general)

### Per-commit rollback

For C-1..C-8, C-10, C-12, C-13, C-14: standard `git revert <commit>` against `claude/post-redeploy-bug-triage`. CI must turn red on the reverted state (since K-tests will fail again); fix forward, do not push the revert as a fix.

For C-0 (defensive snapshot): delete the snapshot file; revert the activity-log row.

For C-7 (graft endpoint): if rollback needed AFTER C-9 already ran, the graft data persists; rollback only affects the endpoint code surface.

For C-9 (salvage): restore Event_1 + Event_2 from pre-image backups. Pre-image paths are in:
- `Production/.recovery_audit.jsonl` (file source of truth)
- `prod_activity_log` Directus rows (mirror)

Procedure:
```bash
# stop server
pkill -f "production_server.py.*Event"
# restore from pre-images
cp "$DEST_DROPBOX/Production/Event_1/.backups/state/<UTC>_pre_graft_<mid>.json" \
   "$DEST_DROPBOX/Production/Event_1/production_state.json"
cp "$DEST_DROPBOX/Production/Event_2/.backups/state/<UTC>_pre_graft_<mid>.json" \
   "$DEST_DROPBOX/Production/Event_2/production_state.json"
# restart server with default Event pin
```

For C-9b (salvage SKIP): restore from C-0 defensive snapshot at `Event_1/.backups/state/preimage_pre_K4_<UTC>.json`.

For C-14 (deploy): restore from `.deploy_backups/<UTC>/` via reverse rsync.

### Cross-commit dependency rollback

If C-2..C-7 partially landed and CI is red, do NOT proceed to C-8. Diagnose root cause of the failed test; fix forward; commit; verify CI green; resume sequence.

If C-9 fails partially (e.g., 8 of 17 grafts succeed before failure), use the `mutation_id`s logged in JSONL to identify which beats are at target vs source. The pre-image backups enable full restore. Re-run salvage after fix forward.

If C-10 lands BEFORE C-9 completes (out-of-order accident): the C-0 snapshot is the only safety net. Restore Event_1 from the C-0 snapshot; halt; re-sequence.

---

## 6. Compaction-aware checkpoint authority (DS-12)

Per DS-12 phase boundary commit + push: each C-N commit closes its phase. NEVER mid-phase checkpoint. NEVER cross phase boundary with CI red.

If session context tightens before the natural commit point, checkpoint at the PREVIOUS phase boundary:
- Continuation handoff doc fragment (append to this handoff)
- `prod_activity_log` row `action=CHECKPOINT_AT_PHASE_<N>_DONE`
- Surface to Kim with current state

Mid-phase checkpoints leave the branch in a half-built state and are forbidden.

---

## 7. Risk register reminder (from spec §13)

| ID | Risk | Mitigation |
|---|---|---|
| RR-1 | Audio resolution event-pinning | Graft rejects beats with rendered media (HTTP 400 `graft_pre_render_only`) |
| RR-3 | Salvage prep is Kim-time bound | Q2 gate 4 timebox 15 min; SKIP path C-9b ready |
| RR-4 | K4 prune destroys beats 12-17 | C-0 snapshot + C-10 ordering (K4 LAST after Event_1/intro empty) |
| RR-5 | DV-2 mirror contract requires read-site audit | C-6 commit pins audit |
| RR-6 | Cross-event salvage requires double restart | Salvage script orchestrates restart per DS-7 |
| RR-7 | Future graft of rendered beats blocked | Pre-render-only invariant; follow-on spec for media migration |
| RR-8 | C-1 RED suite blocks CI until K-fixes complete | Acceptable per DS-2 TDD strict ordering |

---

## 8. Post-implementation: tech-spec session terminates

After C-16 PR opens GREEN:

- Tech-spec session 2026-05-05/06 is closed.
- Implementation handoff retired (this doc remains as historical record).
- Next session: PR review + merge per existing convention.
- Follow-on chips (per spec §14):
  - Storyboard reorder/add/delete UI follow-on session
  - `phase_1.speaker` collapse N+1 sprint
  - Tessa's Fall content recreation (Kim discretion)
  - Milestone unification (separate chip)
  - C6 implementation if not bundled here (already absorbed at C-12)
  - Production/scripts/.oneshot/ cleanup

---

**End of handoff.** Self-contained for fresh terminal session execution. Read this + spec + verify K-finding line numbers before any commit. No mid-phase checkpoints. No silent shortcuts. Halt + surface when in doubt.
