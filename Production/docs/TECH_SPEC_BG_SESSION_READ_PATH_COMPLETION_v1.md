# TECH_SPEC — Beat Gen Session Read Path Completion V1

**Status:** Implemented  
**Branch:** `fix/bg-session-read-path-v1`  
**Amends:** `BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1.md` §6, `TECH_SPEC_BG_SCOPE_ACTIVATION_COLD_BOOT_ONLY_V1.md`, `BEATGEN_SIDECAR_SQLITE_AUTHORITY_SPEC_v1.md`  
**Precedes:** `TECH_SPEC_BEATGEN_SOLE_AUTHORITY_v1.md` (Track B)

---

## 1. Category-unlocker

- **Bug category:** Read/write split violation — default `GET /api/bg/session-state` persisted terminal/orphan merges via `mutate_sidecar_locked`, convoying all workers during active O3/WaveSpeed writes.
- **Category fix:** Session GET is **read-only for sidecar persistence** — terminal + disk truth merged **in-memory** into the response; startup reconcile plans on disk **outside** lock then short commit.
- **Fix type:** CATEGORY

---

## 2. Invariants (I-GET / I-START)

### I-GET-1 — Default session GET never persists

`handle_bg_session_state` (without `force_reconcile_o3=1`) must not call:

- `mutate_sidecar_locked`
- `update_beat_locked`
- `write_sidecar`

### I-GET-2 — Read-time terminal compose

`compose_session_terminal_view()` merges `{job_id}_terminal.json`, disk deliveries, and orphan preview **into response beats only** via `preview_orphan_o3_delivery_on_beat()`.

Kim-visible UX preserved: one hard refresh shows latest terminal clip **without** sidecar write.

### I-GET-3 — Explicit persist entry points only

| Trigger | May persist |
|---------|-------------|
| `force_reconcile_o3=1` on GET | Yes (operator) |
| Finalize / checkpoint / submit | Yes |
| Startup gallery/admin repair threads | Yes (background) |
| Post-deploy scripts | Yes |
| Default refresh / tab load | **No** |

### I-START-1 — Startup event reconcile off hot lock hold

`reconcile_event_sidecar_after_milestone_exit()`:

1. Brief read snapshot (`read_sidecar_for_poll_snapshot`)
2. Disk-heavy `_run_event_sidecar_reconcile_on_sidecar()` on **deep copy** (no lock)
3. Short `mutate_sidecar_locked(_commit, timeout_s=30)` — replace from draft only

---

## 3. Files

| File | Change |
|------|--------|
| `Production/tools/o3_session_terminal_reconcile.py` | `compose_session_terminal_view`, `orphan_preview` |
| `Production/tools/beat_generator.py` | `preview_orphan_o3_delivery_on_beat`, startup plan/commit split |
| `Production/tools/server_handlers/background.py` | `_compose_o3_session_terminal_view` on default GET |
| `Production/tools/tests/test_bg_session_read_path_completion.py` | Behavioral contract |
| `Production/scripts/verify_bg_session_read_path_durability.sh` | Deploy grep gate |

---

## 4. Acceptance

- [ ] Repro script: `_apply_o3_session_terminal_reconcile` → 0 `mutate_sidecar_locked` on default compose path
- [ ] pytest `test_bg_session_read_path_completion.py` green
- [ ] Event_3 `:5113` session-state < 2s under parallel GETs while mock writer holds lock
- [ ] Hard refresh Beat Gen during idle — loads; no convoy
- [ ] Terminal done + delivery on disk visible in response without GET persist

---

## 5. Residual (Track B)

- JSON mirror union on cold boot (startup only — warm GET unchanged)
- Federated repair worker queue
- Sole authority spec (`TECH_SPEC_BEATGEN_SOLE_AUTHORITY_v1`)
