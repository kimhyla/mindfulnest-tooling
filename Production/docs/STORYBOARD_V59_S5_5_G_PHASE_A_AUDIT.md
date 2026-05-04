# Storyboard v59 — S5.5g Phase A Audit

**Date:** 2026-05-04
**Branch:** `claude/s5_5g` (cut from `main@1b40d1b`)
**Preflight row:** Directus `prod_preflight_reviews` id=205, task_id `s5_5g-stitcher-parity-final-20260504`, approved_to_proceed=true
**Spec:** `Production/docs/STORYBOARD_V59_S5_5_G_SPEC_v1.md` (Cursor v8 + v11 §19 + v12 R1-R5 fold approved 2026-05-04)
**This session:** Phase A only (audit + setup). Phase B-I deferred to fresh session per Kim checkpoint authority.

This doc captures the reverse-engineering findings the next session's Phase B-I builds against. **Read this before opening Phase B.**

---

## §1 Phase A.0 verification — gates green

| Gate | Command | Result |
|---|---|---|
| A.0 main pull | `git checkout main && git pull --ff-only` | `724942d..1b40d1b Fast-forward` ✓ |
| A.0.1 branch | `git checkout -b claude/s5_5g` | Switched to new branch ✓ |
| A.0.2 Wave 1 in HEAD | `git merge-base --is-ancestor 1b40d1b HEAD` | `1b40d1b IS in HEAD` ✓ |
| A.0.3 fixture exists | `ls Production/Event_e2e_fixture/` | populated (production_state.json + storyboard_v59_prod.html + .pristine/ + .backups/) ✓ |
| A.0.4 CI on main | `gh run list --branch main --limit 5` | last 4 runs all `completed success` (Smoke + Playwright e2e on 1b40d1b + 82c3fae + 724942d) ✓ |
| A.0.5 grep gate | `bash Production/scripts/verify_mutation_channel_invariant_gate.sh` | `G13 PASS — gate fires on deliberate violation, restores on cleanup` ✓ |

No escape-hatch trigger fired. Untracked working-tree files (`.claude/`, `Production/Event_e2e_fixture/storyboard_v59_prod.L.json`) confirmed by Kim as unrelated to S5.5g (sidecar test side-effect from Wave 1's AF.3.1 + IDE state) — left untracked, not committed, not deleted.

---

## §2 Spec line-number drift (READ FIRST when opening Phase B)

Spec §3 references several `server.py:NNNN` line numbers. Code has shifted since the spec was written (Wave 1 added scope guards + pin checks). **Use these current line numbers, not the spec's.**

| Spec reference | Spec said | **Actual current line** | Symbol / handler |
|---|---|---|---|
| Production Map endpoint | `server.py:8434` | **`server.py:8507`** | `_handle_production_map` |
| `slot.sfx_cues` consumer | `server.py:14659` | **`server.py:14897`** | `_stitch_build_pipeline` per-slot SFX validation |
| Transition cue synthesis | `server.py:14824` | **`server.py:14920-14938`** | `_stitch_build_pipeline` `trans_<after_slot>` synthesis |
| Stitch save job upsert | (not specced) | `server.py:14486-14520` | `_handle_stitch_save_job` |
| Stitch preview + bake | (not specced) | `server.py:14960` (preview), `server.py:14990` (bake) | `_handle_stitch_preview`, `_handle_stitch_bake` |
| Timeline cue upsert | `/api/timeline/cues` | `server.py:14054-14101` | `_handle_timeline_cue_upsert` |
| Timeline cue delete | `/api/timeline/cues/<id>` | `server.py:14103-14124` | `_handle_timeline_delete_cue` |

---

## §3 /stitch_editor job JSON — server contract (snake_case canonical)

The server-side stitch contract is **all snake_case**. The legacy HTML editor uses camelCase internally and converts at the POST boundary (legacy `stitch_editor.html:999-1009`).

### Slot shape (sent to `POST /api/stitch_editor/job` and consumed by `_stitch_build_pipeline`)

```jsonc
{
  "id": "intro" | "phase_a" | "phase_b" | "resolution" | "<custom>",   // legacy uses int id; v59 server keys by slot key
  "video_path": "abs/path/to/slot.mp4",                                  // required
  "video_dur_ms": 30000,                                                 // optional, used for UI duration
  "ambient_bed_path": "abs/path/to/ambient.mp3" | null,                  // optional
  "ambient_vol": 0.4,                                                    // optional, 0.0-1.0
  "sfx_cues": [
    {
      "id": "cue_001",
      "source_path": "abs/path/to/sfx.mp3",
      "name": "soft_chime.mp3",                                          // display only
      "offset_ms": 5200,                                                 // slot-relative
      "volume": 0.45,                                                    // server default 0.45 (line 14085)
      "fadein_ms": 300,                                                  // server default 300 (line 14086)
      "fadeout_ms": 1200                                                 // server default 1200 (line 14087)
    }
  ]
  // §6 below — ADD trim_in_ms / trim_out_ms (NEW fields for S5.5g)
}
```

### Transition shape

```jsonc
{
  "after_slot": 0,                              // index of slot the transition fires after
  "source_path": "abs/path/to/transition.mp3",  // empty = "cut" (no transition audio)
  "audio_name": "swoosh.mp3",                   // display only
  "fade_ms": 500                                // default 500ms (server.py:14929 + legacy line 503)
}
```

Server pipeline at `_stitch_build_pipeline:14920-14938` synthesizes a `trans_<after_slot>` SFX cue from each transition entry:
- `offset_ms = max(0, slot_dur - fade_ms)` — places the transition at the slot boundary
- Hardcoded volume **0.7**, fadein **300ms**, fadeout **300ms** (line 14933-14934)
- Re-mixes the slot via `_stitch_mix_slot_audio` injecting the transition as an SFX cue

### Module-level cues (separate from slot.sfx_cues)

`POST /api/timeline/cues` writes into `state["module_sfx_cues"]` at `_handle_timeline_cue_upsert:14090-14098` — NOT into the stitch_editor job. The two systems coexist:

- **Per-slot cues** (`slot.sfx_cues[]`) → live in `app.stitch_state.jobs[<name>].slots[i].sfx_cues` → consumed by `_stitch_build_pipeline` for stitched bake
- **Module-level cues** (`state["module_sfx_cues"]`) → live in `app.state` (production_state.json) → consumed by `_handle_timeline_preview_with_sfx:14151+` for full-module previews

Spec §3.2 says the v59 UI must distinguish: drop on slot waveform → per-slot cue; drop on module timeline (below slots) → module-level cue. That requires two different POST paths (`/api/stitch_editor/job` vs `/api/timeline/cues`) and Phase B-C must wire both.

### camelCase ↔ snake_case map (legacy `stitch_editor.html:999-1009` POST converter)

| Legacy JS (camelCase, internal) | Server / v59 client (snake_case, wire) |
|---|---|
| `videoPath` | `video_path` |
| `videoDurMs` | `video_dur_ms` |
| `ambientPath` | `ambient_bed_path` |
| `ambientVol` | `ambient_vol` |
| `sfxCues[].path` | `sfx_cues[].source_path` |
| `sfxCues[].offsetMs` | `sfx_cues[].offset_ms` |
| `transitions[].afterSlotIndex` | `transitions[].after_slot` |
| `transitions[].audioPath` | `transitions[].source_path` |
| `transitions[].audioName` | `transitions[].audio_name` |
| `transitions[].fadeDurMs` | `transitions[].fade_ms` |

**Decision for v59 client: use snake_case throughout.** Mirrors all other v59 mutation endpoints. Phase 3.5 cross-model boundary diff in Phase B/C should compare the JS POST body keys against `_handle_stitch_save_job:14486` + `_stitch_build_pipeline:14867` argument extraction.

---

## §4 Transition defaults audit (A.2)

| Field | Default | Source |
|---|---|---|
| Crossfade duration | **500 ms** | server.py:14929 (`fade_ms = int(t.get("fade_ms", 500))`) AND legacy stitch_editor.html:503 (`fadeDurMs: 500`) — **consistent** |
| Crossfade transition cue volume | **0.7** | server.py:14933 (hardcoded in `trans_slot` synthesis) |
| Crossfade transition cue fadein/fadeout | **300/300 ms** | server.py:14934 (hardcoded in `trans_slot` synthesis) |
| Per-slot SFX volume default | **0.45** | server.py:14085 (`_handle_timeline_cue_upsert`) |
| Per-slot SFX fadein default | **300 ms** | server.py:14086 |
| Per-slot SFX fadeout default | **1200 ms** | server.py:14087 |

### Transition-type scope

Spec §3.3 names three transition types. Implementation status:

| Type | Status | Phase B-C work |
|---|---|---|
| `crossfade` | ✓ Backend exists; legacy supports | Wire UI selector → POST `transitions[].fade_ms = <selected>` and `source_path = <selected transition audio>` |
| `cut` | ✓ Backend supports trivially | UI selector value "cut" → omit transition entry OR send `fade_ms: 0` + empty `source_path`. Server already skips empty paths (line 14927) |
| `dissolve` | ✗ **NOT in server pipeline. NOT in legacy editor.** | **NEW Phase B-C work.** Spec §3.3 references "LD-376 fadeblack pattern from Phase A". Requires extending `_stitch_build_pipeline` to apply video fadeblack (ffmpeg `fade=t=out:st=…:d=…` + `fade=t=in:st=0:d=…` on adjacent slots) when `transition.kind == "dissolve"`. **Open question: should `kind` be a new field on the transition shape, or inferred from `source_path` being empty + non-zero `fade_ms`?** Phase B-C must decide. |

**Recommendation for Phase B-C:** add explicit `kind: "crossfade" | "cut" | "dissolve"` field on transition. Server stays backward-compat (defaults `kind="crossfade"` if absent). `dissolve` triggers fadeblack pre-concat step.

---

## §5 Per-slot trim backend pattern decision (A.3) — **LOCKED**

### Decision

**Extend `POST /api/stitch_editor/job` body with per-slot `trim_in_ms` and `trim_out_ms` fields.** Do NOT add a new endpoint.

### Rationale

- `_handle_stitch_save_job:14486-14520` already passes `slots[]` verbatim into `app.stitch_state` — adding two fields is purely additive
- `_stitch_build_pipeline:14867` consumes the same `slots[]` shape — pipeline extension goes in `_stitch_normalize_slot` (called at line 14908) via ffmpeg `-ss <trim_in_s>` and `-to <trim_out_s>` (or `-t <duration>`)
- Mirrors how `ambient_bed_path` and `sfx_cues` were originally added — same incremental pattern
- A separate `POST /api/stitch_editor/slot/trim` endpoint would need its own scope guard (LD-456), event pin check (LD-460), state lock, and mutation surface — all redundant given stitch_save_job already has them
- Per-slot trim is a property of the slot, not an independent operation — domain modeling matches the storage choice

### Alternative considered & rejected

`POST /api/beat/trim` (`server.py:12450`) is a per-beat trim that writes into `state["videos"][role]["beats"][beat_id]["phase_1"]["trim_start"]`. **Rejected for this use case** — it's a per-beat (storyboard) trim, not a per-slot (stitcher) trim. Different state collection, different consumer. Reusing `/api/beat/trim` would conflate two concerns.

### Field shape (Phase B-D contract — locked here)

```jsonc
{
  "video_path": "...",
  "trim_in_ms":  0,            // default 0 (start of clip); inclusive
  "trim_out_ms": null,         // null = end of clip (full length); else exclusive cutoff in ms
  // ...
}
```

**Server-side validation:**
- `trim_in_ms >= 0` (else 400)
- `trim_out_ms is null OR trim_out_ms > trim_in_ms` (else 400)
- `trim_out_ms <= video_dur_ms + 50ms tolerance` (else 400 — guards against UI drift)

**Pipeline implementation sketch (Phase B-D):**

In `_stitch_normalize_slot` (currently called at line 14908), pre-trim before normalization:

```python
def _stitch_normalize_slot(self, video_path: Path, cache_dir: Path,
                           trim_in_ms: int = 0, trim_out_ms: int | None = None) -> Path:
    # Build cache key including trim fingerprint
    trim_sig = f"{trim_in_ms}-{trim_out_ms or 'end'}"
    # ffmpeg: -ss <trim_in_s> -i <input> -to <trim_out_s>  (or -t <dur>)
    # Output cached as norm_<orig_hash>_<trim_sig>.mp4
```

Cache key MUST include trim fingerprint or the LRU cache (line 14955) collides between different trim windows of the same source.

---

## §6 Production Map multi-event mapping bug (§3.6) — **LOCATED**

Bug at `Production/tools/production_server.py:8537-8544` in `_handle_production_map`:

```python
production_root = self.app.event_dir.parent
rows: list[dict] = []
for m in modules or []:
    event_dirs = sorted(
        p for p in production_root.iterdir()
        if p.is_dir() and p.name.startswith("Event_") and "_" not in p.name[len("Event_"):]
    )
    # Take the first event dir (Event_1) as the canonical for now;
    # multi-event would map M-number → event in S4.
    edir = event_dirs[0] if event_dirs else None      # ← BUG: same edir for every module
```

**Every iteration reads the same sorted list and picks `[0]`.** Result: every module row reports `event_dir = "Event_1"` (or whichever sorts first).

### Fix approach (Phase E — locked here)

Map `m_number → event_dir` deterministically. Two viable paths:

1. **Convention-based:** `f"Event_{m_number}"` if it exists, else fallback to existence-check in sort order. Matches Kim's existing event naming.
2. **Directus-driven:** Add `event_dir_path` column to `prod_modules` and read it during the join. More flexible but requires schema migration.

**Recommend path 1** for S5.5g (minimal surface, no schema migration). The current code already has `production_root.iterdir()` — just match by name:

```python
for m in modules or []:
    m_num = m.get("m_number")
    candidate = production_root / f"Event_{m_num}"
    edir = candidate if (candidate.is_dir() and m_num) else None
    # ... segments lookup unchanged but operates on per-module edir
```

**Out of scope for S5.5g:** the Sprint D / Wave 3 deferred ProductionMapTab.tsx:128 `event_load` raw-fetch migration (#53). Per `verify_mutation_channel_invariant_gate.sh` allowlist, ProductionMapTab.tsx event_load remains a sanctioned raw fetch until then.

### Test for §3.6 fix (Phase E)

Phase E TDD red→green needs at least 2 distinct `Event_N` directories in fixture so the test can assert different `event_dir` values per row. **Current fixture has only one event dir (`Event_e2e_fixture`).** Phase E must either:
- Add `Production/Event_e2e_fixture_2/` (per spec §7 escape hatch — fixture additions allowed in S5.5g), OR
- Add `Event_3/`, `Event_5/` minimal stubs

Either is fine. Fixture mutation is allowed; mutation of `Event_1` / `Event_2` is forbidden (§7).

---

## §7 Wave 1 raw-fetch migration verification (§19.10 amendment)

Per spec §19.10 amendment, Phase F is verification only — Wave 1 has already migrated StitcherTab.

### StitcherTab.tsx audit (current Wave 1 state)

| Line | Call | Classification |
|---|---|---|
| 70 | `fetch(\`${SERVER_BASE}/api/stitch_editor/jobs\`)` | GET (READ) — not a mutation, **OK** |
| 88 | `fetch(\`${SERVER_BASE}/api/stitch_editor/job/${name}\`)` | GET (READ) — not a mutation, **OK** |
| 125 | `pathappPatch(activeScope.value, 'stitch_preview', {…})` | MUTATION via pathappPatch ✓ |
| 146 | `pathappPatch<{bake_path?:string}>(activeScope.value, 'stitch_bake', {…})` | MUTATION via pathappPatch ✓ |
| 166 | `pathappPatch(activeScope.value, 'stitch_loudnorm', {…})` | MUTATION via pathappPatch ✓ |
| 183 | `pathappPatch(activeScope.value, 'stitch_save_job', {…})` | MUTATION via pathappPatch ✓ |

**StitcherTab.tsx is 100% pathappPatch-clean for mutations.** No Phase F migration work required. Phase F-as-verification = G14 grep-gate green check + this table.

### MUTATION_CHANNEL_INVARIANT_V1 grep-gate allowlist (`verify_mutation_channel_invariant_gate.sh`)

```bash
grep -vE "(ProjectSelector\.tsx|EventSelector\.tsx|ProductionMapTab\.tsx).*MUTATION_ENDPOINTS\.event_load"
```

**Three sanctioned raw-fetch sites** (deferred to Sprint D / Wave 3):
- `ProjectSelector.tsx` × `MUTATION_ENDPOINTS.event_load`
- `EventSelector.tsx` × `MUTATION_ENDPOINTS.event_load`
- `ProductionMapTab.tsx:128` × `MUTATION_ENDPOINTS.event_load`

These map to deferred prod_blockers #50-53 and are OUT OF SCOPE for S5.5g.

### Re-classification of `STITCHER_RAW_FETCH_MIGRATED_V1`

Spec §3.5 originally listed StitcherTab raw-fetch migration as required work. Wave 1 (commit 1b40d1b) already did this. Per §19.10, the LD becomes a **verification LD** — confirming the gate stays green with current StitcherTab. Phase H still writes the LD (HARD severity per §19.4) but its decision_text shifts to "verified-clean post Wave 1" rather than "migrated in S5.5g".

---

## §8 Schema findings — `prod_preflight_reviews`

When writing the preflight row this Phase A (id=205), four fields were sent and dropped silently by Directus:

- `classification`
- `advocates_count`
- `counters_count`
- `date_reviewed`

Substantive fields persisted correctly: `task_id`, `task_type`, `task_description`, `claude_summary`, `approved_to_proceed`. **Future Phase 0 writes for downstream sessions: omit these four fields.** The `task_type` field carries the classification string ("architectural") — that's the canonical classification field in this schema.

The DirectusAdminClient `post_item_verified` flagged this as `silent_write_failure`, but the row exists and is correct — it's a verification false positive caused by schema/payload divergence. Treat `silent_write_failure` with `mismatches.field` ∈ {missing-from-schema} as PASS for these specific fields.

---

## §9 Phase A — outputs delivered

| Output | Location | Status |
|---|---|---|
| Branch | `claude/s5_5g` (local) | Created, push pending in §A.commit |
| Preflight row | Directus `prod_preflight_reviews` id=205 | Written + read-back ✓ |
| Audit doc | This file (`Production/docs/STORYBOARD_V59_S5_5_G_PHASE_A_AUDIT.md`) | Written |
| Continuation handoff | `Production/docs/STORYBOARD_V59_S5_5_G_CONTINUATION_HANDOFF.md` | Written |
| Preflight script | `Production/scripts/s5_5g_phase_a_preflight.py` | Committed |
| Phase A commit | Single commit pushed to `origin/claude/s5_5g` | pending |

No PR opened. No implementation code. No master overview update (closeout doc updates are Phase I).

---

## §10 Phase B-I scope — **deferred to fresh session**

See `STORYBOARD_V59_S5_5_G_CONTINUATION_HANDOFF.md` for the next-session pickup brief.

In summary, Phase B-I work remaining (per spec §4 + §19 amendments):

- Phase B — per-slot SFX cue placement (G3-G6) — extend StitcherTab with per-slot WaveformTimeline + drag-drop + CuePopover wiring
- Phase C — per-boundary transitions (G7-G8) — add transition selectors between slot pairs; wire crossfade + cut + **dissolve (NEW; needs LD-376 fadeblack pipeline extension)**
- Phase D — per-slot trims (G9-G10) — UI handles + extend stitch_save_job + extend `_stitch_normalize_slot` per §5 above
- Phase E — Production Map multi-event fix (G12-G13) — server.py:8537-8544 fix per §6 above + 2-event fixture
- Phase F — Wave 1 raw-fetch verification only (G14) — grep gate already green; this is a no-op verification per §19.10
- Phase G — cross-cutting verification (G1, G2, G11, G15, G16) — bake-with-everything integration test, full Playwright suite, retirement-decision protocol logging
- Phase H — register 5 NEW LDs (HARD/SOFT per §19.4) + V59_CLIENT_FEATURE_COMPLETE_V1 (HARD)
- Phase I — closeout: master overview status table update (Dropbox tree), STORYBOARD_V59_FEATURE_PARITY_COMPLETE_HANDOFF.md, single commit, push, `gh pr create` with retirement metric protocol

Total estimate: 6-8 hr / ~1500-2000 LOC / 16 gates.
