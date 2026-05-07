# Storyboard v59 — Authoring Workflow Architecture Spec v2

**Status:** APPROVED — Cursor APPROVE 2026-05-06 (R10 satisfied via shell-based rg+sed verification of disk file; R1-R9 passed substantively in initial review pass; v2 is the canonical implementation spec)
**Date:** 2026-05-05
**Branch:** claude/post-redeploy-bug-triage
**Author:** dual-Opus tech-spec session (Agents A + B, orchestrator synthesis), Kim Smith governance + v2 fold (Cursor REJECT-with-changes, 2026-05-06)
**Supersedes:** `STORYBOARD_V59_AUTHORING_WORKFLOW_SPEC_v1.md` (v1 retained as forensic record; do not delete)
**Implementation:** spec-only this session; atomic-commit terminal sessions follow Cursor approval

### v2 fold (2026-05-06) — 5 must-fix items

1. **§3 line citations** locked to git rev `fafdfed` (`claude/post-redeploy-bug-triage`); table refreshed + verifier ops (§3.0). *Local clones must `git fetch` that branch before running `git show` — see §3.0 if object missing.*
2. **K4 narrative** — prune location verified at locked rev per §3.0 HALT check (prune must exist post-C2-bundle `2a7fd13`).
3. **RR-κ′ severity** aligned with SOFT LD `EVENT_1_SHIPS_VIA_SAVED_VIDEO_V1` (documentation/awareness, not behavioral CI).
4. **§7.4 salvage-SKIP** — discard-via-graft sketch removed; empty-partition path via `scope_router.mutate_partition` only.
5. **§5.1 sibling-handler audit** promoted to in-scope acceptance; corresponding §14 follow-on removed.

---

## 0. Header / Provenance

This spec was produced via the dual-Opus tech-spec protocol codified in `feedback_tech_spec_for_wrong_architecture.md` (Kim Smith, 2026-05-03):

- **Phase 0** pre-flight: 9 inputs verified on disk; DS-1..DS-12 loaded; LD-505 two-tree boundary respected
- **Phase 1** independent investigation: two parallel Opus agents read inputs in isolated contexts; surfaced 9 K-findings (K1-K8 + D5)
- **Phase 2** architecture proposals: two parallel Opus agents proposed independently; substantial convergence on architecture shape, divergence on five operational choices
- **Phase 3** structured debate: three divergences resolved by Kim (DV-1, DV-2, DV-5); two synthesizable (DV-3, DV-4); RR-1 verified by orchestrator
- **Phase 3.5** convergence checkpoint: all non-regression constraints preserved; GREEN
- **Phase 4** synthesis: this document
- **Phase 5** Cursor review: pending
- **Phase 6** Kim sign-off + atomic-commit implementation: pending

All K-finding line citations are locked to **`production_server.py` at git revision `fafdfed`** on branch `claude/post-redeploy-bug-triage` (Δ-architecture-tighten; session HEAD as of 2026-05-05). See **§3.0** for verifier commands and HALT rules. v1 used an imprecise “commit head at session start” wording — v2 replaces that with an explicit SHA lock.

---

## 1. Why this spec exists

The post-redeploy bug-triage session 2026-05-05 surfaced multiple authoring-workflow bugs in a single bundle. Per Kim's `feedback_tech_spec_for_wrong_architecture.md` rule: "When symptom is architectural (multiple unrelated symptoms with shared root, prior spec didn't address the conceptual question), invoke tech-spec rigor. Don't propose a quick fix."

Phase 1 confirmed the architectural root: state mutations on `production_server.py` are scattered across handlers that each re-derive partition resolution by hand, hardcoding `videos.intro` and bypassing the partition-aware mutator wrapper. The result is a class of bugs (K1-K8 + D5) that share one root cause: **no canonical, mandatory partition router**.

Companion finding: the cross-event scramble in `Event_1/intro` (17 Event-2 narrative beats stranded; speakers drifted) was caused by a pre-LD-456 cross-event Accept-All leak (2026-05-01 origin, def at **8936** + LD-456 docstring at **8942-8947** / seed **~8975-9001** @ `fafdfed` per §8) that wrote to top-level legacy `state["beats"]` in the wrong server-pinned event. The leak was structurally closed by LD-456 SCOPE_VALIDATION_V1, but the data damage persisted because K4's asymmetric DISPLAY_ORDER_STRICT prune never ran on the affected partitions.

This spec specifies the architectural change that prevents this bug class from being reintroducible AND the canonical recovery primitive that handles the existing damage.

---

## 2. Scope

### 2.1 In-scope

- Architectural change to `production_server.py` mutation handlers (K1-K8 + D5 prevention)
- New cornerstone endpoint `/api/beat/graft` (canonical beat-recovery primitive)
- Speaker canonicalization at write boundary (K7 + Q3)
- Speaker dual-store collapse path (K8)
- Salvage of the 18 Event 2 beats (executes per bounded-effort gate)
- LDs to file (10 total: 6 HARD, 4 SOFT)
- Test plan: clean fixture + scrambled-state read-only contracts
- Atomic-commit implementation order

### 2.2 Out-of-scope

- **Event_1 / Tessa's Fall content recovery** — Kim ships Event_1 via the existing saved scene mp4 (`Event_1/intro/scene_intro_*.mp4`). Captured by `EVENT_1_SHIPS_VIA_SAVED_VIDEO_V1` SOFT LD.
- **Storyboard tab reorder/add/delete UI** — deferred. Captured by `STORYBOARD_REORDER_UI_DEFERRED_V1` SOFT LD. Per directive: Pillar 5 secondary; UX is its own session.
- **Rendered-beat grafts** (beats with `phase_1.status="completed"` or rendered media) — graft handler rejects these (HTTP 400). Follow-on spec required for media migration.
- **Milestone architecture unification** — separate chip task already spawned.
- **C6 (per-role status columns + 5-state glyph)** — independent; ships either side of this spec.
- **C7 (CSS) and C8 (deploy script)** — independent; can ship anytime.
- **Cleanup of `Production/scripts/.oneshot/`** after session close — separate follow-up chip.

### 2.3 Parked items per directive item 9 framing

- R-κ' (**SOFT**, captured by `EVENT_1_SHIPS_VIA_SAVED_VIDEO_V1`): Event_1 beat-level state intentionally empty — **awareness / policy** via SOFT LD (not a behavioral CI gate). HARD enforcement (e.g. deploy fails if beats non-empty) is **deferred** to a follow-on chip if Kim ever wants it.
- R-κ'' (DEFERRED): Tessa's Fall content recreation — out of scope
- R-σ (SOFT, quantified §11.2): salvage-skip means losing Kim's dialogue authoring + image-gen work; quantified estimate gates the salvage decision

---

## 3. The 9 K-findings (verified, the bugs this spec prevents)

### 3.0 Canonical citation revision `fafdfed` + verifier ops (v2)

**Locked tree:** all **Cite** column ranges in §3.1 refer to `Production/tools/production_server.py` at **`fafdfed`** on **`claude/post-redeploy-bug-triage`** (not an arbitrary working tree). C2-bundle prune behavior is expected on that lineage (`2a7fd13` squash ancestry per post-redeploy session).

**Mandatory verifier (run before Phase 6 implementation):**

```bash
# Fetch the branch if needed (local Dropbox clone may not have the object yet).
git fetch origin claude/post-redeploy-bug-triage
git show fafdfed:Production/tools/production_server.py | nl -ba | sed -n '1165,1255p'   # K4: mutate_video_state + prune block
git show fafdfed:Production/tools/production_server.py | nl -ba | sed -n '4025,4120p'   # D5: patch_state._apply intro_partition
git show fafdfed:Production/tools/production_server.py | nl -ba | sed -n '4705,4840p'   # K6: _assert_event_scope
git show fafdfed:Production/tools/production_server.py | nl -ba | sed -n '8885,9020p'   # K2/K7: _handle_bg_accept_beats
git show fafdfed:Production/tools/production_server.py | nl -ba | sed -n '9235,9305p'   # K3: _handle_bg_add_beat
git show fafdfed:Production/tools/production_server.py | nl -ba | sed -n '11985,12075p' # K1: _handle_beat_update_text
git show fafdfed:Production/tools/production_server.py | nl -ba | sed -n '2425,2475p' # RR-1: _find_beat_audio
```

**HALT — K4 / prune:** On `git show fafdfed:...`, inside `mutate_video_state`, if there is **no** post-mutator **DISPLAY_ORDER_STRICT** prune (or equivalent symmetric beat-set reconciliation), **stop**. That would mean C2-bundle integration differs from session assumptions — resolve genealogy before writing code, not just line numbers.

**Cursor v2 fold note:** the machine that produced this fold could not resolve `fafdfed` in the local clone (`unknown revision`). The §3.1 table listed **provisional** ranges aligned to the session’s intended `fafdfed` tree.

**VERIFIER RUN 2026-05-06 (Kim's desktop clone, tooling repo @ `fafdfed54644225fbc2d7ad1fcf5367b17491185`):** the §3.0 verifier blocks were executed against actual `fafdfed`. **§3.1 Cite anchors corrected accordingly** (v2 fold's provisional numbers had drifted because Cursor's earlier R10 read targeted a non-`fafdfed` tree). **HALT condition resolved:** the K4 DISPLAY_ORDER_STRICT prune is **CONFIRMED present at lines 1198-1217** in `mutate_video_state` on `fafdfed` (C2-bundle integration intact; prune block reads `# DISPLAY_ORDER_STRICT_V1 prune (C2b)` per disk truth).

### 3.1 K-table (bugs prevented)

| # | Finding | Severity | Cite @ `fafdfed` |
|---|---|---|---|
| K1 | `_handle_beat_update_text` HARDCODES `videos.intro` (`setdefault` chain). Edits intended for other roles silently land in `intro`. | HARD | **12048-12054** (`# Step 2` comment + `def update(state)` mutator + `state.setdefault("videos", {}).setdefault("intro", ...)` chain) |
| K2 | `_handle_bg_accept_beats` seeds legacy top-level `state["beats"]` via `mutate_state`; bypasses v3 partitions + `display_order`. | HARD | **8975-9001** (`_seed_bg_beats` / `mutate_state` block); fallback **8990** (`"speaker": beat.get("speaker") or "Guide Bird",`) |
| K3 | `_handle_bg_add_beat` HARDCODES BG segment **`get_seg_entry(..., arc_number=1, event_id=2, phase="pre")`** — wrong event for scoped work. | HARD | **9279** (hardcoded segment lookup) |
| K4 | DISPLAY_ORDER_STRICT asymmetric: prune runs on **`mutate_video_state`** path at **1198-1217** (CONFIRMED present @ fafdfed per §3.0 verifier); **`mutate_state`** handlers bypass. Bypass examples: `_handle_beat_update_text` (**12061** mutate_state call), `patch_state._apply` (**4079** mutator), Accept-All seed (**9001** mutate_state call). | HARD | **1198-1217** (prune block) vs **12061, 4079, 9001** (bypass call sites) |
| K5 | No cross-event move in client; no Storyboard reorder UI. | HARD (move) / SOFT (UI) | `grep` **MUTATION_ENDPOINTS** / StoryboardTab.tsx **725–880** |
| K6 | `_assert_event_scope` defaults **`allow_missing=True, allow_missing_video_role=True`** — missing `event_id` passes. | HARD | **4734-4827** (`_assert_event_scope`); `_scope_body` helper follows |
| K7 | Accept-All speaker fallback **`"Guide Bird"`** when sidecar empty. | SOFT | **8990** (`or "Guide Bird"` literal) |
| K8 | Speaker dual-store: TTS reads `beat_state.get("speaker")` (top-level path); `patch_state` writes **`phase_1.speaker`**. | SOFT | **4170-4175** (patch_state phase_1.speaker target) vs **8990** (Accept-All top-level write) |
| D5 | `patch_state._apply` routes partition writes through **`intro_partition` = `videos.intro`** for global + beat fields. Same class as K1, **`patch_state` layer**. | HARD | **4083** (`intro_partition = state.setdefault("videos", {}).setdefault("intro", ...)`) |

---

## 4. Architecture: SCOPE-ROUTER + GRAFT (SR+G v1)

### 4.1 Tagline

One mutation router consumes the scope keys the client already injects (per LD-461), proves them against state, and routes every partition write into the named `(event_id, video_role)` partition. The DISPLAY_ORDER_STRICT prune runs symmetrically on every write. Beat recovery is a single endpoint (`/api/beat/graft`) that uses the same router.

### 4.2 Three structural shifts

**Shift 1 — Mandatory partition router.** A new module `Production/tools/scope_router.py` exposes:

- `scope_router.resolve(body) -> ResolvedScope` — frozen dataclass `(event_id, video_role, beat_id?, mutation_id?)`. Validates `scope_event_id` against `self.app.event_dir.name` (HTTP 409 on mismatch); validates `scope_target_video` (or `scope_video_role` alias) against `_VALID_VIDEO_ROLES` (HTTP 400 on missing/invalid).
- `scope_router.mutate_partition(scope, mutator_fn)` — wraps `StateManager.mutate_video_state(scope.video_role, mutator_fn)`. The mutator receives the partition dict (already correct partition), never the full state. The DISPLAY_ORDER_STRICT prune runs inside.
- `scope_router.graft(source_ref, target_scope, target_position, options)` — the cornerstone (§7).

All beat-touching mutation handlers MUST call `scope_router.mutate_partition`. An AST grep CI gate (sibling of LD-519's MUTATION_ENDPOINTS gate) bans:
- `state.setdefault("videos", {}).setdefault("intro"` outside `scope_router.py` and `StateManager`
- direct `state.setdefault("beats"` (top-level legacy write) outside `scope_router.py` and `StateManager`
- literal `arc_number=1, event_id=2, phase="pre"` in handlers (K3 specific)

**Shift 2 — Scope-strict defaults.** `_assert_event_scope` defaults flip from `allow_missing=True / allow_missing_video_role=True` to `allow_missing=False / allow_missing_video_role=False` for **all mutating handlers**. Read-only probes (`state_snapshot`, `event_load`) keep the permissive default. Client `pathappPatch` already auto-injects scope keys per LD-461; the flip just turns on the receiver.

**Shift 3 — Speaker write-boundary canonicalization.** Every write site that lands a `speaker` field flows through `_canonicalize_speaker(raw)` first. The literal `or "Guide Bird"` fallback at line **8990** (`_handle_bg_accept_beats` seed) is dropped — empty stays empty (LD-520 fail-loud applies at TTS time). The existing `_SPEAKER_ALIAS` table (line 3257-3271) already maps `"guide bird" → "Chipper"`; this just enforces it at write time, not just TTS read time.

### 4.3 Two new abstractions; zero schema changes

- `scope_router.py` — new module; ~150 lines. Houses `ResolvedScope`, `resolve`, `mutate_partition`, `graft`.
- `/api/beat/graft` — new endpoint registered in `MUTATION_ENDPOINTS` (LD-519 compliant).

No changes to `state.json` schema. No changes to Directus `prod_*` collection schemas (preserves picker-spec R3 boundary).

---

## 5. Per-pillar design (locked)

### 5.1 Pillar 1 — Beat lifecycle

**Current state.** Lifecycle handlers scattered: **K1** (`_handle_beat_update_text` — cite §3.1), **K3** (`_handle_bg_add_beat` — cite §3.1), **D5** (`patch_state._apply` — cite §3.1). The **K1/D5** bug class is structural: any handler that touches `videos.<role>.beats` without the partition router can re-hardcode `intro` or bypass prune.

**In-scope acceptance (v2 — promoted from former §14 follow-on):** commits **C-2..C-7** **MUST** audit the following **sibling handlers** and route partition writes through **`scope_router.mutate_partition`** (or equivalent single entrypoint) wherever they touch beat or partition fields:

`_handle_beat_finalize`, `_handle_beat_use_as_final`, `_handle_beat_delay`, `_handle_beat_trim`, `_handle_select`, `_handle_assign_image`, `_handle_animate`, `_handle_lipsync`

Each handler’s audit is a **sub-deliverable** of the parent **C-N** commit that touches it. **Acceptance (post-C-7):** repository grep for **`state.setdefault("videos", {}).setdefault(`** outside `scope_router.py` (and the small allowlist in **`StateManager`**, if any) returns **ZERO** hits in `production_server.py` and other server mutation surfaces covered by the LD-519 catalog.

**Locked design.** Every lifecycle handler:
1. `scope = self._scope_router_resolve(body)` — raises 409/400 on missing/invalid
2. `def _mutator(partition, ...): partition.beats[scope.beat_id]["text"] = ...; ...`
3. `self.app.state.mutate_partition(scope, _mutator)` — partition prune runs

`_handle_bg_add_beat` derives `(arc_number, event_id, phase)` from `scope.event_id` + `scope.video_role` via mapping `intro→pre, resolution→post, standalone→main` (codified). Hardcoded **`get_seg_entry(..., arc_number=1, event_id=2, phase="pre")`** at line **9279** removed.

**K-findings addressed:** K1, K3, K4 (via channel switch), D5.

**Non-regression touchpoints:** LD-461 client-side scope injection unchanged; C1 BG_TAB_SCOPE_SYNC_V1 strengthened (scope still validated, default flips stricter).

### 5.2 Pillar 2 — Cross-event semantics

**Current state.** Server is single-event-pinned at startup (`--event-dir Production/Event_1`). `_assert_event_scope:4769` checks body event_id against `self.app.event_dir.name`. Default `allow_missing=True` is the K6 leak.

**Locked design.** `allow_missing=False` becomes the default for ALL mutation handlers. `_assert_event_scope` becomes a thin wrapper around `scope_router.resolve` (single source of truth for scope validation).

**Cross-event MOVE is supported only via `/api/beat/graft`** (Pillar 7) with explicit `--source-event Production/<event>` CLI flag at server startup. NO in-band cross-event mutation endpoint is exposed to the v59 client. Per Kim's DV-1 resolution: the 2-restart operational ceremony is the fair trade for permanent architectural cleanliness — the invariant "one server = one event always" is preserved.

**K-findings addressed:** K1, K2, K5 (move via graft), K6, D5.

**Non-regression touchpoints:** LD-456 SCOPE_VALIDATION_V1 STRENGTHENED (defaults flip; cross-event leak class structurally closed). LD-461 unchanged.

### 5.3 Pillar 3 — "Accept all beats"

**Current state.** `_handle_bg_accept_beats` calls `mutate_state` via `_seed_bg_beats` (**~8975-9001**) with `state.setdefault("beats", {})` — top-level legacy. Bypasses partition + prune. Speaker fallback `"Guide Bird"` at **8990**.

**Locked design.** Rewrite handler:
1. `scope = self._scope_router_resolve(body)`
2. Read BG sidecar; build list of `(beat_id, speaker, text)` tuples positionally
3. Canonicalize each speaker via `_canonicalize_speaker(raw)`; **drop the `or "Guide Bird"` literal** — empty stays empty
4. `def _seed(partition): for bid, fields: partition.beats[bid] = {speaker, text}; partition.display_order.extend(...)` (idempotent: skip if bid already in display_order)
5. `self.app.state.mutate_partition(scope, _seed)` — prune runs

**K-findings addressed:** K2 (write to correct partition), K4 (prune runs), K7 (no Guide Bird literal), K8 (single-store write — partition.beats[bid].speaker).

**Non-regression touchpoints:** BG sidecar shape unchanged; LD-460 pin checks unchanged.

### 5.4 Pillar 4 — display_order canonicalization

**Current state.** Prune at `mutate_video_state:1198-1217`. Symmetric with renderer ONLY for callers that go through `mutate_video_state`. Three handlers bypass via `mutate_state` (K4 asymmetry).

**Locked design — belt-and-suspenders (DV-3 synthesis pick):**

1. **Structural fix:** all partition writes route through `scope_router.mutate_partition` (Pillars 1+3). Grep CI gate forbids direct `mutate_state` calls touching partition fields outside `scope_router.py` and `StateManager`.

2. **Defense-in-depth:** add a post-write invariant check in `StateManager.mutate_state` itself. After the mutator runs, walk `state.get("videos", {})` and for each role with a `display_order: list`, prune `partition.beats` to be a subset. ~10 lines; idempotent; runs after every `mutate_state` call. Catches any future handler that bypasses `mutate_partition` for top-level fields and accidentally touches a partition.

3. **CI gate:** as in (1) above.

**K-findings addressed:** K4.

**Non-regression touchpoints:** C2-bundle DISPLAY_ORDER_STRICT_V1 STRENGTHENED, not weakened. The renderer's strict gate is unchanged.

**LD upgrade:** the existing LD-530 DISPLAY_ORDER_STRICT_V1 PATCHes to v2 (or new sibling LD `DISPLAY_ORDER_STRICT_V2` filed; implementation chooses).

### 5.5 Pillar 5 — Storyboard tab UX (deferred)

**Locked design (DV-5 resolution):** **defer entirely.** No reorder UI; no add/delete UI. Pillar 7's `/api/beat/graft` exists as the move primitive — used via terminal-session calls only this sprint. SOFT LD `STORYBOARD_REORDER_UI_DEFERRED_V1` documents the deferral with explicit "move primitive exists at /api/beat/graft; UI follow-on tracked separately."

**K-findings addressed:** K5 SOFT half (UI gap acknowledged). K5 HARD half (no move endpoint) closed by Pillar 7.

**Non-regression touchpoints:** none.

### 5.6 Pillar 6 — Speaker drift

**Current state.** Two stores: `beat_state.get("speaker")` (TTS read **3366**) AND `phase_1.speaker` (`patch_state` branch **4170-4175**). `_canonicalize_speaker:745` + `_SPEAKER_ALIAS:3257-3271` already map `"guide bird" → "Chipper"`. Drift is at WRITE-time fallback (K7) and dual-store divergence latent (K8).

**Locked design — two contracts:**

1. **Write-boundary canonicalization (HARD).** Every speaker write site flows through `_canonicalize_speaker(raw)` first. Sites: BG accept-all seed (line **8990**), patch_state speaker case (**4170-4175**), graft handler (Pillar 7). The literal `or "Guide Bird"` at line **8990** is dropped.

2. **Single-store contract (DV-2 resolution: top-level canonical).** `partition.beats[bid].speaker` is the canonical write target — it matches the existing TTS reader at **3366** (fewest downstream code changes) and the conceptual model "speaker is a beat-level property." `phase_1.speaker` becomes a **write-time mirror** for one release as a read-compat shim, then deprecated. Read sites are audited during implementation:
   - TTS read **3366**: continues to read beat-level `speaker` (no change)
   - any `phase_1.speaker` reader (audit needed): wrapped in `_resolve_beat_speaker(beat)` helper that reads top-level first, falls back to phase_1 mirror

   Future sprint (post-deprecation): collapse `phase_1.speaker` writes; remove the mirror.

**Q3 plumbing:** no `_SPEAKER_ALIAS` change needed (already maps Guide Bird → Chipper). The change is enforcing canonicalization at WRITE boundary, not just READ. Default fallback flips from `"Guide Bird"` (line **8990**) to **empty** (no literal default; raises at TTS time if absent — fail-loud per LD-520).

**K-findings addressed:** K7, K8.

**Non-regression touchpoints:** TTS voice resolution unaffected (already alias-aware). Sidecar L.json gets the canonical name.

---

## 6. Pillar 7 — `/api/beat/graft` cornerstone (deepest design)

This is permanent infrastructure regardless of whether Pillar 8's salvage executes.

### 6.1 Endpoint shape

```
POST /api/beat/graft
Body: {
  source: {
    event_id: str,            // e.g., "Event_1"
    video_role: str,           // e.g., "intro"
    beat_id: str               // e.g., "beat_03"
  },
  target: {
    event_id: str,             // MUST equal self.app.event_dir.name (HTTP 409 otherwise)
    video_role: str,
    position: int              // 0-indexed insert into target display_order; -1 = append; >len clamps to append
  },
  speaker_override: str|null,  // optional canonicalized server-side
  move: bool = false,          // false (default) = COPY semantics; true = COPY-then-DELETE source
  mutation_id: str             // mandatory uuid4 from caller; idempotency key
}

Returns: {
  ok: bool,
  status: "moved" | "copied" | "dedup" | "already_present",
  pre_image_path: str,         // absolute path; same-event case = single path; cross-event = source + target paths
  audit_log_path: str,         // JSONL row pointer
  audit_log_id: str,           // Directus prod_activity_log row id (best-effort)
  target_display_order: [...], // post-mutation
  beat_id: str                 // target beat_id (= source.beat_id since KEEP-IDS per Q2)
}
```

Registered in `Production/tools/storyboard-v2/src/api/endpoints.ts::MUTATION_ENDPOINTS` as `beat_graft` (LD-519 compliant). Routes through `pathappPatch`.

### 6.2 COPY default + `move=true` flag (DV-1 resolution)

- **Default (move=false): COPY.** Source partition unchanged. Target partition gains a new beat at `target.position` with the same beat_id (KEEP-IDS per Q2). The source remains addressable in its original event/role.
- **`move=true`: COPY-then-DELETE.** After successful target write, source beat is deleted from its partition (and from `display_order`) in a same-thread atomic mutation. Cross-event move is structurally identical to cross-event copy + same-event delete — but the COPY-then-DELETE sequence within one handler call is the contract.
- **Same-event move:** allowed; `target.event_id == source.event_id`.
- **Cross-event move:** requires server started with `--source-event Production/<source_event>` CLI flag (per DV-1 resolution; pin invariant preserved). Otherwise HTTP 409 with `code: cross_event_requires_explicit_source`.

### 6.3 Pre-render-only invariant (RR-1 mitigation)

**HARD invariant:** the graft handler REJECTS (HTTP 400) any source beat where:
- `phase_1.status == "completed"`, OR
- any `phase_1.options[*].file` is non-empty, OR
- any `phase_1.options[*].lipsync_task_id` is non-zero/non-null

Rejection reason in body: `code: "graft_pre_render_only"`. This prevents grafting beats whose rendered media files are event-pinned (see RR-1 verification: `_find_beat_audio` at **`production_server.py:2459`** @ `fafdfed` looks up TTS under `event_dir / story_scene_tts_v2` — moving a rendered beat across events would silently break audio playback).

**Rationale:** Kim's specific salvage (18 beats, all pre-render with `lipsync.task_id=None` and `audio_path=0`) does not hit this. A follow-on spec is required if rendered-beat grafts ever become a use case (would need either media-file copy logic or namespaced filename rewriting).

### 6.4 Audit-log shape (DV-4 synthesis pick: file-first JSONL + Directus mirror)

Every successful graft writes:

**(a) Local JSONL row** at `Production/.recovery_audit.jsonl` (created if absent). Atomic append. Shape:
```json
{
  "schema_version": 1,
  "action": "beat_graft",
  "ts": "2026-05-05T14:32:18Z",
  "mutation_id": "<uuid4>",
  "source": {"event_id":"Event_1","video_role":"intro","beat_id":"beat_03","pre_image_version":47},
  "target": {"event_id":"Event_2","video_role":"intro","beat_id":"beat_03","position":2,"post_image_version":12},
  "move": true,
  "speaker_resolved": "Chipper",
  "speaker_source": "alias:guide bird->Chipper" | "override" | "untouched" | "empty",
  "actor": "production_server_v59",
  "pre_image_paths": [
    "Production/Event_1/.backups/state/20260505T143218Z_pre_graft_<mutation_id>.json",
    "Production/Event_2/.backups/state/20260505T143218Z_pre_graft_<mutation_id>.json"
  ],
  "ok": true,
  "elapsed_ms": 423
}
```
Same-event grafts: single `pre_image_paths` entry. Cross-event grafts: two entries (source + target).

**(b) Directus `prod_activity_log` mirror** via `lib/directus.try_post_or_queue` per DS-8. Same payload, with `details` field carrying the JSONL row content. Best-effort mirror — if Directus write fails, JSONL on disk is the durable source of truth.

### 6.5 Idempotency contract

`mutation_id` is required (HTTP 400 if missing). Server-side dedup cache `_GRAFT_DEDUP` (LRU, bounded; same shape as `_PATCH_STATE_DEDUP:4072`). Cache hit returns the original result with `status: "dedup"` and no state change. Cache size: 256 entries; TTL: process lifetime.

Restart-safe semantics: clients SHOULD use a fresh `mutation_id` if uncertain after a restart. The handler also performs a **content fingerprint check**: if a beat with the same `(target.event_id, target.video_role, target.beat_id)` and matching `text + speaker` already exists in target.beats, returns `status: "already_present"` without re-mutating. This catches replay after partial-failure even when dedup cache is cold.

### 6.6 Pre-image backup contract

Before any mutation:
1. Atomic copy of source event's `production_state.json` to `Production/Event_<source>/.backups/state/<UTC>_pre_graft_<mutation_id>.json`
2. Same for target event (if cross-event; else same path as source)
3. Both paths recorded in audit log; returned in response

If snapshot fails → HTTP 503 (do not proceed). If post-mutation read-back doesn't match expected shape → restore from pre-image and return HTTP 500 with both pre_image_paths in body.

Pattern matches existing `Production/lib/atomic_json_write` + the migration script's pre-image convention at `migrate_state_to_videos_partition.py:360-362`.

### 6.7 Scope-validation per LD-456 (mandatory)

- `_assert_event_scope` runs with `allow_missing=False`
- `body.target.event_id` MUST equal `self.app.event_dir.name` (HTTP 409 otherwise)
- `body.target.video_role` MUST be in `_VALID_VIDEO_ROLES` (HTTP 400 otherwise)
- `body.source.video_role` MUST be in `_VALID_VIDEO_ROLES` (HTTP 400 otherwise)
- When `body.source.event_id != body.target.event_id`: `body.source.event_id` MUST equal the `--source-event` startup flag value (HTTP 409 with `cross_event_requires_explicit_source` otherwise)
- `body.source.beat_id` MUST exist in `<source_event_state>.videos[source.video_role].beats` (HTTP 404 otherwise)

### 6.8 Failure modes table

| Mode | Detection | Recovery |
|---|---|---|
| Source beat not found | KeyError on source partition.beats lookup | HTTP 404; audit row with `ok:false, reason:"source_not_found"`; no state change |
| Source beat has rendered media | `phase_1.status=="completed"` or `options[*].file` non-empty | HTTP 400 `code:"graft_pre_render_only"`; no state change |
| Target partition missing | `videos[target.video_role]` absent | HTTP 400 `code:"target_role_not_in_state"`; client should call partition-create first |
| Position out of range | `position > len(target.display_order)` | clamp to append; logged but not failure |
| Cross-event without --source-event flag | startup flag missing | HTTP 409 `code:"cross_event_requires_explicit_source"`; no state change |
| Snapshot fails | `atomic_json_write` exception during snapshot | HTTP 503; no state change |
| Source delete succeeded, target insert failed | post-mutation read-back mismatch on target | restore both events from pre-image; HTTP 500 with `pre_image_paths` |
| Concurrent mutation on source mid-call | version check on source beat | HTTP 409 conflict; no state change |
| Concurrent mutation on target mid-call | version check on target.display_order | HTTP 409 conflict; no state change |
| Server pin changes mid-call (LD-460) | generation check at terminal write | HTTP 423; no state change |
| Caller retries with same mutation_id | dedup cache hit | replay original result with `status:"dedup"` |
| Content already at target (different mutation_id, same content) | content fingerprint check | `status:"already_present"`; no state change |

---

## 7. Pillar 8 — Salvage decision (EXECUTE → fold to SKIP per disk-truth disposition 2026-05-06)

**Disposition note (2026-05-06):** EXECUTE path was attempted at C-9 and
non-viable due to RR-1 invariant on Event_1/intro beats 1-11 (rendered
Kling .mp4 files in event-pinned `clips_dir/`; spec §7.2 anticipated only
lipsync_task_id=0 absence, not animation-file absence). C-9b normative
SKIP (§7.4) executed instead. Pre-skip transcript at
`Production/docs/.archive/EVENT_2_BEAT_DIALOGUE_RECOVERED_<UTC>.md`
(Dropbox tree) preserves dialogue + canonical-speaker content for Kim's
manual re-author. Activity log rows: 1541 (Event_1/intro) + 1542
(Event_2/intro).

### 7.1 Bounded-effort gate per Q2 (1)-(4)

| Gate | Result | Reasoning |
|---|---|---|
| (1) NO new endpoint required beyond Pillar 7's mechanism | **PASS** | `/api/beat/graft` IS the canonical mechanism. Salvage is N invocations of it. |
| (2) NO per-beat conditional branching | **PASS** | All 17 source beats homogeneous: `(Event_1, intro, beat_NN)` → `(Event_2, intro, position_M)` with `speaker_override=null`. Same call shape every iteration. The orphan stub at Event_2/beat_04 is a separate one-line `patch_state` field=`text` update; not part of the 17-beat batch. |
| (3) NO custom mapping beyond canonical inputs | **PASS** | Mapping is a flat list of `(target_position, source_beat_id)` tuples consumed in order. `target_position` and (optional) `speaker_override` ARE the canonical inputs. The mapping table is data, not code branching. |
| (4) Salvage prep + execution + verification ≤ 30 min | **PASS** (conditional) | Estimate: prep (Kim hand-orders the 17 beats) ~10-15 min; execution (17 sequential graft calls + 1 patch_state for orphan stub, ~1s each) ~5 min; verification (read back Event_2 state; spot-check; load v59 client) ~5-10 min. Total ~20-30 min. **Conditional on Kim's prep window — if hand-ordering exceeds 15 min, gate breaches and salvage SKIPS.** |

**Final salvage decision: EXECUTE.** All four gates pass.

### 7.2 Cost-of-skip estimate (per directive item 4)

Disk truth from both agents' independent reads of `Event_1/intro/` and `production_state.json`:

- `Event_1/intro/`: 2 stitched scene mp4s only (`scene_intro_*.mp4`, ~10MB each, May 3). NO per-beat lipsync/animate mp4s.
- `videos.intro.beats[*].lipsync.task_id`: **None** across all 17 beats.
- `phase_1.options[*]`: 31 total options across 17 beats; `lipsync_task_id=0` and `audio_path=0` on every option.

**Salvage value preserved (if EXECUTE):** dialogue text + speaker + selected_option choices + image_overrides for 17 beats. ~30 min Kim re-typing if SKIP; ~$0-15 image-regen + ~$1 TTS regen if SKIP and Kim later wants to re-render Event 2.

**No lipsync/audio media work to lose** (none generated yet for these beats). The salvage avoids ~30 minutes of Kim's content re-entry; arithmetic of the gate is "is the architecture's natural mechanism cheap enough to use" — gates pass — so execute.

### 7.3 Salvage execution plan (post-spec)

After K1-K3, K5, K6, K7, K8, D5 fixes land + Pillar 7 endpoint deploys (per §10 atomic-commit order), Kim runs a script `Production/scripts/.oneshot/redistribute_event2_beats_<UTC>.py` that:

1. Restarts production_server with `--event-dir Production/Event_2 --source-event Production/Event_1`
2. Loops 17 beats with hand-ordered `target_position` map; calls `pathappPatch(beat_graft, {source: ..., target: {event_id:"Event_2", video_role:"intro", position:M}, move:true, mutation_id:<uuid>})` for each
3. Calls `pathappPatch(patch_state, {field:"text", value:"...", scope_event_id:"Event_2", scope_target_video:"intro", beat_id:"beat_04"})` for the orphan stub (corrected text + speaker)
4. Reads back Event_2 state; assertion: 18 beats present in display_order; speaker canonicalized to "Chipper" for the 3 Guide-Bird-aliased beats
5. Restarts production_server back to default pin (no `--source-event` flag)
6. Smoke test: load v59 client on Event_2; confirm StoryboardTab renders 18 beats; reload; confirm persistence

If any step fails, pre-image backups in `.backups/state/` enable rollback.

### 7.4 Salvage SKIP fallback (if gate (4) breaches at execution time)

If Kim's prep exceeds the 15-minute timebox, salvage **SKIPS** (no graft batch).

**Salvage-SKIP path (normative):** use **`scope_router.mutate_partition`** with a mutator that sets **`partition.beats = {}`** and **`partition.display_order = []`** for **both** `Event_1/intro` and **`Event_2/intro`** partitions (appropriate scoped calls per event pin — typically one **server pin per event** + snapshot, or a one-shot script that invokes the same mutator contract twice). **Do not** use `/api/beat/graft` or `move=true` to a “discard” target for this cleanup; graft is for intentional beat moves, not partition nukes.

**Pre-image backups** are still written per **`mutate_partition` / state-write contract** before emptying. A **`prod_activity_log`** row records the skip + Kim's reasoning.

After SKIP, Kim re-authors Event_2 from skeleton dialogue when ready.

---

## 8. Forensic finding (Q4 closure)

**`migrate_state_to_videos_partition.py` EXONERATED.** Both Phase 2 agents read the script independently. Cite:

- `discover_state_files()` (line 229-236) globs each event independently
- `build_v2_state(v1_state)` (line 144-221) operates on a single file's content; mutates a NEW `v2: dict = {}`
- `INTRO_LIFT` rules (line **81–86** on current `main`; verify @ `fafdfed` if lineage differs) only relabel WITHIN a state dict
- `atomic_json_write(str(path), v2_state)` (line 365) writes back to the SAME path that was read

No code path opens two state files or carries a beat dict from one event into another's lift output.

**Forensic root cause locked:** pre-LD-456 cross-event Accept-All leak (2026-05-01 origin, def at **8936** + LD-456 docstring **8942-8947**, seed **~8975-9001** @ `fafdfed` (verifier-confirmed 2026-05-06)). Server pinned Event_1; client BG context Event_2; `allow_missing=True` let the request through; the seed wrote to top-level legacy `state["beats"]` of the server-pinned event (Event_1). The leak was structurally closed by LD-456 SCOPE_VALIDATION_V1 (C5 ratified). The data damage persisted because:
1. K2 wrote to legacy top-level `state["beats"]`, not v3 partition
2. Subsequent migration (`migrate_state_to_videos_partition.py`) faithfully lifted the corrupted top-level `beats` into `videos.intro.beats`
3. K4's asymmetric prune meant subsequent `mutate_state` callers never re-pruned to drop the orphan beats 12-17

This spec's K2/K4/K6 fixes prevent recurrence. Pillar 7's `/api/beat/graft` is the recovery mechanism for the existing damage.

---

## 9. LDs to file (10 total: 6 HARD, 4 SOFT)

Per DS-9: HARD = behaviorally enforced (CI gate, code invariant, structural rule); SOFT = awareness/UX/cosmetic.

| LD codename | Severity | Scope domain | Description |
|---|---|---|---|
| `SCOPE_ROUTER_V1` | **HARD** | server + client | All beat-touching mutations route through `scope_router.resolve` + `scope_router.mutate_partition`. Direct `state.setdefault("videos",{}).setdefault("intro"...)` and direct `state.setdefault("beats"...)` banned outside `scope_router.py` and `StateManager`. AST grep CI gate enforces. Subsumes K1, K2, K3, D5 prevention. |
| `SCOPE_REQUIRED_DEFAULTS_V1` | **HARD** | server | `_assert_event_scope` defaults flip to `allow_missing=False, allow_missing_video_role=False` for all mutating handlers. Read-only probes keep permissive default. Subsumes K6 prevention. |
| `DISPLAY_ORDER_STRICT_V2` | **HARD** | server | Strengthens C2-bundle DISPLAY_ORDER_STRICT_V1 (LD #530). Post-write prune runs in BOTH `mutate_state` AND `mutate_video_state` (defense-in-depth). Renderer's strict gate unchanged. Subsumes K4 prevention. |
| `BG_HARDCODED_SCOPE_PURGE_V1` | **HARD** | server | `_handle_bg_add_beat` and any handler that resolves a BG sidecar segment MUST derive `(arc_number, event_id, phase)` from `(scope.event_id, scope.video_role)` via codified mapping. Literal `arc_number=1, event_id=2, phase="pre"` banned by grep CI gate. Subsumes K3 prevention. |
| `SPEAKER_WRITE_BOUNDARY_CANONICALIZATION_V1` | **HARD** | server | Every `speaker` write site flows through `_canonicalize_speaker(raw)` first. Literal `or "Guide Bird"` fallback banned. Empty stays empty (LD-520 fail-loud at TTS time applies). Subsumes K7 prevention. |
| `BEAT_GRAFT_RECOVERY_MECHANISM_V1` | **HARD** | server + client | `/api/beat/graft` endpoint shape, COPY default, `move=true` flag, `--source-event` cross-event semantics, audit log shape (file JSONL + Directus mirror), idempotency (mutation_id + content fingerprint), pre-image backup contract, scope-validation per LD-456, pre-render-only invariant (RR-1 mitigation). Permanent infrastructure. Subsumes K5 HARD half. |
| `SPEAKER_DUAL_STORE_DEPRECATION_V1` | SOFT | server | `partition.beats[bid].speaker` is canonical write target; `phase_1.speaker` is write-time mirror for one release as read-compat shim, then collapsed in N+1 sprint. Read-side helper `_resolve_beat_speaker` reads top-level first, falls back to phase_1 mirror. Subsumes K8 path. |
| `SPEAKER_CANONICALIZATION_TO_CHIPPER_V1` | SOFT | server | Per Q3: `_SPEAKER_ALIAS` already maps `"guide bird"→"Chipper"` and `"pip"→"Chipper"`; this LD documents the canonicalization-at-write-boundary policy and the read-side fallback for legacy on-disk values. |
| `EVENT_1_SHIPS_VIA_SAVED_VIDEO_V1` | SOFT | content/architecture | Event_1 ships via the existing saved scene mp4s (`Event_1/intro/scene_intro_*.mp4`), not via beat-level production state. `Event_1/intro/beats{}` is intentionally empty post-salvage. Future Claude sessions MUST NOT "fix" empty Event_1/intro by re-authoring beats unless Kim explicitly requests. Documented in Architecture Overview v1. |
| `STORYBOARD_REORDER_UI_DEFERRED_V1` | SOFT | UX | Storyboard tab reorder/add/delete UI deferred. Move primitive exists at `/api/beat/graft`; UI follow-on tracked separately. Per directive Pillar 5 secondary. |

Note on existing LDs:
- LD #530 DISPLAY_ORDER_STRICT_V1 (C2-bundle) — superseded/upgraded by DISPLAY_ORDER_STRICT_V2; NOT unwound, the C2-bundle commit ratified.
- LD #529 BG_TAB_SCOPE_SYNC_V1 (C1) — preserved unchanged; the SCOPE_REQUIRED_DEFAULTS_V1 flip only strengthens.
- LD #527 PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1 (C5) — preserved unchanged; this spec doesn't touch Production Map.
- LD-456 SCOPE_VALIDATION_V1 — preserved + strengthened by SCOPE_REQUIRED_DEFAULTS_V1.
- LD-461 SCOPE_BODY_HELPER_V1 — preserved unchanged.
- LD-519 MUTATION_CHANNEL_INVARIANT_V1 — preserved + extended (new endpoint registered).
- LD-505 TOOLING_REPO_CREATED_V1 — preserved (all code in tooling repo).

---

## 10. Atomic-commit implementation plan (Kim's refined order)

Per directive item 8 + Kim's RR-4 refinement: bug fixes → cornerstone → salvage decision → K4 fix LAST → final smoke.

| # | Subject | Scope (files) | Test contract | LD pinned |
|---|---|---|---|---|
| C-0 | **Pre-snapshot Event_1/intro state** to `Production/Event_1/.backups/state/preimage_pre_K4_<UTC>.json` (defensive — protects beats 12-17 from K4 prune in case salvage fails or skips) | one-shot bash + `lib/atomic_json_write` | manual: snapshot file present | none (operational step) |
| C-1 | **`scope_router.py` introduced** — ResolvedScope + resolve + mutate_partition; AST grep CI gate added; RED tests for K-fixes pinned | NEW `Production/tools/scope_router.py`; NEW `e2e/scope_router_red.spec.ts` | RED suite; CI red on K1/K2/K3/K6/D5 expected | SCOPE_ROUTER_V1 |
| C-2 | **K1+D5 fix** — `_handle_beat_update_text` + `patch_state._apply` route through `scope_router.mutate_partition`. Hardcoded `videos.intro` literals removed. | `production_server.py` **K1 12048-12054** + **`patch_state._apply` intro partition 4083** (and subsequent _apply branches) (see **§3.1** @ `fafdfed`) | TVMC-K1.1, TVMC-D5.1 GREEN | SCOPE_ROUTER_V1 |
| C-3 | **K2+K7 fix** — `_handle_bg_accept_beats` routes through `scope_router.mutate_partition`; partition.beats target; `_canonicalize_speaker` at write boundary; drop `or "Guide Bird"` literal | **`8990`** (fallback) + **`8975-9001`** (mutate_state seed block) (see **§3.1** @ `fafdfed`) | TVMC-K2.1, TVMC-K7.1, TVMC-K7.2 GREEN | SCOPE_ROUTER_V1, SPEAKER_WRITE_BOUNDARY_CANONICALIZATION_V1 |
| C-4 | **K3 fix** — `_handle_bg_add_beat` derives BG sidecar segment from `(scope.event_id, scope.video_role)`; literal `arc_number=1, event_id=2, phase="pre"` removed; grep CI gate adds the literal-ban | **`9279`** + grep gate config (see **§3.1** @ `fafdfed`) | TVMC-K3.1 GREEN | BG_HARDCODED_SCOPE_PURGE_V1 |
| C-5 | **K6 fix** — `_assert_event_scope` defaults flip; ~30 caller-site audit; startup assertion lists scope-strict handlers | **`4734-4827`** (`_assert_event_scope`) + **`_scope_body` @ 4830** + caller sites (see **§3.1** @ `fafdfed`) | TVMC-K6.1 GREEN; existing pathappPatch flow still passes | SCOPE_REQUIRED_DEFAULTS_V1 |
| C-6 | **K8 fix** — speaker dual-store mirror contract; `partition.beats[bid].speaker` canonical; `phase_1.speaker` mirrored on write; `_resolve_beat_speaker` read helper | **`4170-4175`** + read-site audit (**3366**) (see **§3.1** @ `fafdfed`) | TVMC-K8.1 GREEN | SPEAKER_DUAL_STORE_DEPRECATION_V1 |
| C-7 | **Pillar 7 cornerstone** — `/api/beat/graft` endpoint + `scope_router.graft` + audit JSONL + Directus mirror + dedup cache + content-fingerprint check + pre-image snapshots + pre-render-only HTTP 400 + scope-validation | NEW `_handle_beat_graft` in production_server.py; NEW `MUTATION_ENDPOINTS.beat_graft` in endpoints.ts; NEW `e2e/beat_graft.spec.ts`; NEW `Production/.recovery_audit.jsonl` (gitignored) | TVMC-GR.1..GR.6 GREEN; TVMC-S3 dry-run on fixture mirror GREEN | BEAT_GRAFT_RECOVERY_MECHANISM_V1 |
| C-8 | **LDs file** — register all 10 LDs via `try_post_or_queue` + read-back per DS-8 | Directus prod_locked_decisions inserts | `mn-lds list` shows all 10 entries | (all LDs) |
| C-9 | **Salvage decision execution** (per §7) — runs ONLY because gates 1-4 passed. One-shot `Production/scripts/.oneshot/redistribute_event2_beats_<UTC>.py` invokes `/api/beat/graft` 17× with `move=true` + `patch_state` for orphan stub | NEW one-shot script; runs against Event_1+Event_2 with `--source-event` restart | manual: 18 beats land in Event_2/intro display_order; speakers canonicalized to "Chipper" for 3 affected beats; Event_1/intro/beats={} post-move | (none — operation, not contract) |
| C-10 | **K4 fix lands** — `mutate_state` defense-in-depth prune; `DISPLAY_ORDER_STRICT_V2`. **Now safe** because Event_1/intro/beats={} either via salvage (C-9) or via SKIP fallback (C-9b). C-0 snapshot is the rollback safety net. | `production_server.py` `StateManager.mutate_state` ~**1021** (defense-in-depth prune to add); `mutate_video_state` prune already at **1198-1217** unchanged | TVMC-K4.1, TVMC-K4.2 GREEN | DISPLAY_ORDER_STRICT_V2 |
| C-11 | **Final smoke** — full Playwright e2e green; LD-519 endpoint catalog gate; AST grep gates; sidecar regen check; manual smoke on Event_1 (READ-ONLY, render saved video) and Event_2 (post-salvage, full beat-level UI) | full e2e suite | All tests GREEN; new K-tests GREEN | (none — verification) |

**Atomic boundaries** per LD-518 + DS-12: each commit independently verifiable; CI green between commits 1-8 + 10. Commits C-9 and C-9b (skip variant) are operational + feature-flagged. Commit C-10 is gated by C-9 outcome (must run AFTER salvage decision executes).

**Why C-10 (K4) deferred to last (Kim's RR-4 refinement):** if K4 lands BEFORE the salvage decision, the first `mutate_state` call against Event_1/intro after C-10 would prune beats 12-17 (since `display_order=[beat_01..beat_11]`). The defensive C-0 snapshot is the rollback safety net, but ordering eliminates the need to use it.

---

## 11. Test plan

### 11.1 Clean fixture tests (Event_e2e_fixture/) — DS-3

| Test ID | Surface | Pillar | Description |
|---|---|---|---|
| TVMC-K1.1 | Playwright e2e | 1, 4 | StoryboardTab role='resolution' active → click beat → edit text → reload → assert text persists in `videos.resolution.beats` AND `videos.intro.beats` UNCHANGED |
| TVMC-K2.1 | Playwright e2e | 3 | BgTab → generate beats → Accept All in role='intro' → reload → assert beats present in `videos.intro.beats` AND `state.beats` (top-level legacy) absent |
| TVMC-K3.1 | Playwright e2e | 1 | BgTab role='resolution' → "+ Add empty beat" → server-side assertion: BG sidecar segment matches `(arc_number, event_id from scope, phase from role mapping)` |
| TVMC-K4.1 | Pytest | 4 | State has `display_order=["beat_01"]` + `beats={beat_01:{}, beat_02:{}}`; call `/api/beat/update_text` for beat_02; assert post-call `beats={beat_01:{...}}` (beat_02 pruned by defense-in-depth) |
| TVMC-K4.2 | CI grep | 4 | Grep test: `state.setdefault("videos",{}).setdefault("intro"` returns ZERO hits in handlers outside `scope_router.py` |
| TVMC-K5.1 | (n/a — UI deferred) | 5 | covered by GR.1 instead |
| TVMC-K6.1 | Pytest | 2, 6 | curl POST to `/api/beat/update_text` WITHOUT `event_id` → HTTP 400 `code:"scope_required"` |
| TVMC-K7.1 | Pytest | 6 | Accept-All on sidecar beat with `speaker=""` → state lands `speaker=""` (not "Guide Bird"); subsequent TTS resolution fails-loud per LD-520 |
| TVMC-K7.2 | Pytest | 6 | Accept-All on sidecar beat with `speaker="Guide Bird"` → state lands `speaker="Chipper"` (canonicalized at write boundary) |
| TVMC-K8.1 | Pytest | 6 | patch_state speaker case → assert `partition.beats[bid].speaker = "Chipper"` AND `partition.beats[bid].phase_1.speaker = "Chipper"` (mirror) |
| TVMC-D5.1 | Playwright e2e | 1 | StoryboardTab role='resolution' active → adjust trim → assert write lands in `videos.resolution.beats[bid].phase_1.trim_start`, NOT `videos.intro` |
| GR.1 | Playwright e2e | 7 | Same-event same-role graft via `/api/beat/graft` → verify pre-image backup written, audit JSONL row + Directus mirror, idempotent replay returns dedup |
| GR.2 | Pytest | 7 | mutation_id missing → HTTP 400 |
| GR.3 | Pytest | 7 | Source beat missing → HTTP 404 + audit row `beat_graft_failed` |
| GR.4 | Pytest | 7 | Source beat with `phase_1.status=="completed"` → HTTP 400 `code:"graft_pre_render_only"` |
| GR.5 | Pytest | 7 | Cross-event graft without `--source-event` flag → HTTP 409 `code:"cross_event_requires_explicit_source"` |
| GR.6 | Pytest | 7 | `move=true` graft within same event → source beat removed from source partition; target partition gains beat at position; both display_orders updated |

### 11.2 Scrambled-state tests (READ-ONLY against Event_1's actual state)

Per directive item 6. Tests confirm fixes don't crash on existing damage AND Pillar 7 mechanism handles existing state correctly.

| Test ID | Description |
|---|---|
| SCR.1 | Pytest: load Event_1 state (17 beats, display_order=11 entries) → call `scope_router.resolve(body={event_id:"Event_1", scope_target_video:"intro"})` → returns ResolvedScope without raising |
| SCR.2 | Pytest: with Event_1 state loaded, attempt `_handle_beat_update_text` on `beat_05` (whose speaker is "Guide Bird") → write succeeds → speaker_canonical=`"Chipper"` post-write; partition.beats[beat_05].speaker == "Chipper"; partition.beats[beat_05].phase_1.speaker == "Chipper" (mirror) |
| SCR.3 | Pytest: with Event_1 + Event_2 states loaded under `--source-event Production/Event_1`, perform graft of `beat_03` from Event_1/intro to Event_2/intro position 1 with `move=true` → success; pre-image of both events written; Event_1/intro.beats no longer contains beat_03; Event_2/intro.beats contains beat_03 with canonicalized speaker; both display_orders updated; audit log + Directus mirror records `move:true` |
| SCR.4 | **WARNING test** — Pytest: with Event_1 state loaded, perform any `mutate_video_state` call → confirm DISPLAY_ORDER_STRICT_V1 prune drops beats 12-17 (already orphaned). DOCUMENT THIS as expected destructive behavior post-prune. **Pillar 7 graft used BEFORE any other mutation preserves the 6 beats.** This test enforces the C-0 → C-9 → C-10 implementation order. |

### 11.3 DS coverage

- DS-1 (Playwright e2e per functional gate): TVMC-K1.1, K2.1, K3.1, D5.1, GR.1
- DS-2 (TDD strict ordering RED → GREEN): C-1 commit pins RED suite; C-2..C-7 commits GREEN
- DS-3 (fixture pinning): all clean tests use `Production/Event_e2e_fixture/`; SCR tests use READ-ONLY copies
- DS-4 (critical-path tests never quarantined): all TVMC-K and GR tests are critical-path
- DS-5 (mutation channel discipline): new `/api/beat/graft` registered in MUTATION_ENDPOINTS; LD-519 grep gate covers
- DS-6 (server fail-loud): empty speaker raises at TTS time; no silent print
- DS-7 (server staleness): salvage script restarts server before C-9 + after; CI workflow handles
- DS-8 (Directus writes via try_post_or_queue + read-back): C-8 LD inserts; audit JSONL mirror
- DS-9 (HARD/SOFT severity): all 10 new LDs classified (6 HARD + 4 SOFT)
- DS-10 (CI workflow APPEND not replace): Playwright workflow appends new `e2e/scope_router_red.spec.ts` + `e2e/beat_graft.spec.ts`
- DS-11 (no future comments): no `// TODO` or `// FIXME` in shipped commits
- DS-12 (phase boundary commit + push): each C-N commit closes its phase; CI green between

---

## 12. Compatibility statement

| Constraint | Status | How preserved |
|---|---|---|
| C1 affb887 (BG_TAB_SCOPE_SYNC_V1, LD #529) | **Ratified, strengthened** | Picker scope sync still drives `scope_event_id` + `scope_video_role` injection in BG endpoints; SCOPE_REQUIRED_DEFAULTS_V1 flip closes the silent-default leak |
| C5 ea04c24 (PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1, LD #527) | **Ratified, untouched** | Production Map handler is read-only; no mutation surface touched by this spec; Picker-spec R3 boundary preserved (no `prod_modules` schema migration) |
| C2-bundle 2a7fd13 (DISPLAY_ORDER_STRICT_V1, LD #530) | **Strengthened (V2)** | K4 fix adds defense-in-depth prune in `mutate_state`; renderer's strict gate unchanged; CI grep gate ensures no future handler bypasses partition wrapper |
| Δ-architecture-tighten fafdfed | **Ratified** | No new cleanup scripts proposed; halt-bundle pattern honored (this spec IS that tech-spec) |
| LD-505 TOOLING_REPO_CREATED_V1 | **Preserved** | All code changes in tooling repo (`Production/tools/`); content/state recovery via canonical endpoint; no Dropbox-side scripts |
| LD-519 MUTATION_CHANNEL_INVARIANT_V1 | **Preserved + extended** | `/api/beat/graft` registered in MUTATION_ENDPOINTS catalog; AST grep gate extended for partition-write bans |
| LD-456 SCOPE_VALIDATION_V1 | **Preserved + strengthened** | `allow_missing=False` flip is strictly within LD-456 spirit ("reject cross-event mutations at the door") |
| LD-461 SCOPE_BODY_HELPER_V1 | **Preserved unchanged** | `_scope_body` continues to coalesce `event_id` / `scope_event_id`; `scope_router.resolve` calls it under the hood |
| Picker-spec R3 boundary | **Preserved** | Per-role status DERIVED from on-disk artifacts; this spec touches state mutation handlers only; Production Map's on-disk artifact scan unchanged; NO `prod_modules` schema expansion |
| Post-redeploy v2 §3.3 Part 2 5-state glyph rule | **Preserved** | `state.videos.<role>` partition presence still drives `—` glyph for C6 derivation; `mutate_partition` auto-creates partitions on first write (matches existing `mutate_video_state:1186-1196`) |

---

## 13. Risk register (final, DS-9 classified)

| ID | Risk | Sev | Mitigation |
|---|---|---|---|
| RR-1 | Audio resolution event-pinning could break grafted beats | HARD | Graft handler rejects beats with rendered media (HTTP 400 `graft_pre_render_only`). **Disposition 2026-05-06:** RR-1 fired at C-9 attempt — Event_1/intro beats 1-11 carried rendered Kling .mp4 files; spec §7.2 had only quantified lipsync_task_id=0 (true) but missed `phase_1.options[].file` presence. EXECUTE path folded to C-9b SKIP per §7.4 with pre-skip transcript dump preserving dialogue value. Follow-on spec for media migration deferred to post-merge chip. |
| RR-2 | Pin-bypass cornerstone exception (Agent A's variant) | (n/a) | DV-1 resolved by Kim against this design; not in spec |
| RR-3 | Salvage prep time is Kim-availability bound | SOFT | Q2 gate (4) timebox 15 min for prep; if exceeded, salvage SKIPS (§7.4) |
| RR-4 | K4 prune after-K4-lands destroys beats 12-17 | HARD | C-0 defensive snapshot + C-10 ordering (K4 lands LAST, after Event_1/intro is empty post-salvage or post-skip) |
| RR-5 | DV-2 mirror contract requires read-site audit | SOFT | C-6 commit pins read-site audit; SPEAKER_DUAL_STORE_DEPRECATION_V1 documents collapse path |
| RR-6 | Cross-event salvage requires double server restart | SOFT | Salvage script orchestrates restart; DS-7 server-staleness check applies; one-time operational ceremony per Kim's DV-1 trade |
| RR-κ' | Event_1 contains zero Event_1 narrative beats (post-salvage / intentional empty intro) | **SOFT** | Awareness/policy: **`EVENT_1_SHIPS_VIA_SAVED_VIDEO_V1`** SOFT LD. Not a behavioral CI gate. HARD deploy-blocking enforcement deferred unless Kim requests a follow-on chip. |
| RR-κ'' | Tessa's Fall content recreation | DEFERRED | Out of scope; future Kim decision |
| RR-σ | Salvage skip lipsync/audio loss | SOFT | Quantified §7.2: $0-15 image-regen + ~30 min Kim re-author. Bounded-effort gate explicitly evaluable. |
| RR-7 | Future graft of rendered beats blocked | SOFT | Pre-render-only invariant (§6.3); follow-on spec for media migration if needed |
| RR-8 | C-1 RED suite blocks CI until K-fixes complete | SOFT | Acceptable per DS-2 TDD strict ordering; expected RED→GREEN progression |

---

## 14. Out-of-scope follow-ons

These items are explicitly out of scope for this spec but tracked for future sessions:

1. **Storyboard tab UX** (reorder/add/delete) — `STORYBOARD_REORDER_UI_DEFERRED_V1` SOFT LD captures
2. **Rendered-beat graft media-migration spec** — follow-on if cross-event move of rendered beats ever needed
3. **`phase_1.speaker` collapse** — N+1 sprint per `SPEAKER_DUAL_STORE_DEPRECATION_V1` SOFT LD
4. **Tessa's Fall content recreation** — Kim discretion; deferred
5. **Milestone architecture unification** — separate chip task already spawned
6. **C6 (per-role status columns + 5-state glyph)** — independent; ships either side of this spec
7. **Production/scripts/.oneshot/ cleanup** — separate follow-up chip after spec implementation

*(Sibling-handler audit for K1-class coverage is **in-scope** under **§5.1** and C-2..C-7 — it is no longer listed here as a follow-on.)*

---

## 15. Acceptance criteria for Cursor (Phase 5) review

A Cursor review of this spec is APPROVE if:

1. **Prevention claims for K1-K8 + D5 are credible** — each K-finding has a structural prevention mechanism; no cosmetic-only fixes.
2. **Pillar 7 cornerstone is robust** — endpoint shape, audit log, idempotency, pre-image, scope-validation, pre-render-only invariant all present and consistent.
3. **Bounded-effort gate (Q2 1-4) is honored** — salvage decision is explicit (EXECUTE) with reasoning per each gate.
4. **Cost-of-skip estimate is grounded in disk truth** — agents' independent reads cited.
5. **Atomic-commit order respects RR-4** — K4 lands after salvage decision; C-0 snapshot is defensive.
6. **Non-regression compatibility statement is complete** — all 10 prior constraints (C1/C5/C2-bundle/tighten + LD-505/519/456/461 + Picker-spec R3 + 5-state glyph rule) addressed.
7. **LDs are correctly classified per DS-9** — HARD entries are behaviorally enforced; SOFT entries are documentation/UX.
8. **Test plan covers both fixture sets** — clean (Event_e2e_fixture/) + scrambled (READ-ONLY against Event_1's actual state) per directive item 6.
9. **Out-of-scope items are explicitly tracked** — no silent scope creep.
10. **Forensic finding (Q4) is closed** — migration script EXONERATED with code citations; root cause locked; **§3.0 `fafdfed` line-lock** satisfied (or verifier ops run with no HALT on K4 prune).

If Cursor flags any K-class regression risk, REJECT and revise.

---

## 16. Implementation handoff

After Phase 5 Cursor approval + Phase 6 Kim sign-off, the implementation handoff doc `Production/docs/STORYBOARD_V59_AUTHORING_WORKFLOW_HANDOFF.md` is generated, following the post-redeploy-bug-triage handoff pattern (`Production/docs/STORYBOARD_V59_POST_REDEPLOY_TERMINAL_HANDOFF.md`, prod_reference_docs id=199).

The handoff doc will contain:
- Summary of this spec (1-page)
- C-0 → C-11 atomic-commit instructions (one section per commit; explicit code diff scope)
- Test contract per commit (which TVMC/GR/SCR test must GREEN)
- Pre-image snapshot procedure (C-0)
- Salvage execution script template (C-9)
- Rollback procedure if any commit fails CI

The handoff is generated AT THAT TIME — it does not yet exist.

---

## 17. Sign-off

This document **`STORYBOARD_V59_AUTHORING_WORKFLOW_SPEC_v2.md`** is the Phase 4 synthesis output of the dual-Opus tech-spec session 2026-05-05, **folded to v2 on 2026-05-06** (Cursor REJECT-with-changes). **`STORYBOARD_V59_AUTHORING_WORKFLOW_SPEC_v1.md`** remains the unmodified Phase 4 drop for forensic comparison. For authoring-workflow architecture, **v2 supersedes v1**; v1 supersedes the Δ-architecture-tighten halt-bundle narrative only for historical traceability.

**Next step:** Phase 5 Cursor review (R-row format per post-redeploy spec pattern) **of v2**. Phase 6 Kim sign-off + atomic-commit handoff doc generation. Implementation in subsequent terminal sessions.

**This session: SPEC ONLY. NO CODE OR DATA MUTATIONS.**
