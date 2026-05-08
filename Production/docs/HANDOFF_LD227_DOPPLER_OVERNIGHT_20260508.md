# Handoff — LD 227 Doppler Cutover (Overnight Autonomous Session)

**For:** Terminal Claude Code CLI session, autonomous mode
**From:** worktree `gallant-bouman-804b4f` session, 2026-05-08
**LD:** 227 `SHORTCUT_CREDSTORE_MD_FALLBACK_20260418`
**Estimated time:** 4–6 hours autonomous (Phase 1 + monitoring setup); Phase 4 needs separate session 14 days later

---

## Why this is split, not single-session

The closure plan has 4 phases. Phases 1, 2, 4 are mechanical; Phase 3 is calendar time. **You CANNOT compress Phase 3** — it requires 14 days of zero MD-fallback warnings to confirm Doppler is fully load-bearing.

Phase 2 also needs Kim's hands (System Settings UI for Full Disk Access grant) — not autonomous.

So the realistic execution shape:
- **THIS session (autonomous, overnight):** Phase 1 + monitoring instrumentation
- **Kim manual (15 min):** Phase 2 (FDA grant) — see G5 in session handoff
- **Calendar wait:** 14 days post-instrumentation
- **Future session:** Phase 4 (remove MD fallback)

---

## Pre-flight (MUST do before starting)

1. **Read LD 227 verbatim** from Directus — confirm `notes` field still contains the 4-phase closure plan written 2026-05-08 by prior agent. If drifted, HALT.

2. **Read these reference files:**
   - `Production/tools/lib/credentials.py` — current MD-FIRST priority + 26 callers
   - `Production/lib/directus_admin_client.py` lines 55-56 — env var name mismatch (DIRECTUS_EMAIL vs DIRECTUS_ADMIN_EMAIL)
   - `Production/lib/credential_store.py` — reference correct pattern (env-FIRST, MD fallback)
   - `Production/scripts/daily_backup.sh` — references SUPABASE_DB_HOST not in Doppler
   - `Production/scripts/_weekly_snapshot_wrapper.sh` — no `doppler run --` prefix
   - `Production/API_KEYS_MASTER.md` — current state (DO NOT EDIT in Phase 1)

3. **Verify Doppler is configured:** `doppler whoami` and `doppler secrets` show expected secret names.

4. **Inventory the 26 callers** of `tools/lib/credentials.py::load_credentials`. Run `grep -rn "from.*credentials import\|import credentials\b\|tools/lib/credentials" Production/ | head -50`. Build a complete list before any edits.

---

## Phase 1 — CODE (autonomous-doable)

### Phase 1.A — Flip `tools/lib/credentials.py` to env-first
- Current: MD-FIRST, falls back to env only if file missing
- Target: env-FIRST, falls back to MD only if env missing AND emit `_CREDSTORE_FALLBACK_WARNED` warning to stderr (mirror `lib/credential_store.py:75-79` pattern)

### Phase 1.B — Align env var names
Two name mismatches:
- `DIRECTUS_EMAIL` / `DIRECTUS_PASSWORD` vs Doppler's `DIRECTUS_ADMIN_EMAIL` / `DIRECTUS_ADMIN_PASSWORD`
- `SUPABASE_REF` / `SUPABASE_PASSWORD` / `RAILWAY_TOKEN` vs Doppler's `SUPABASE_PROJECT_REF` / `SUPABASE_DB_PASSWORD` / `RAILWAY_API_TOKEN`

Decision options:
- **(a) Update code to read Doppler's canonical names** — preferred (single source of truth)
- **(b) Add Doppler aliases** — adds `DIRECTUS_EMAIL: ${DIRECTUS_ADMIN_EMAIL}` etc. — preserves backwards compat but grows secret count

Recommended: (a). Update code in:
- `lib/directus_admin_client.py:55-56`
- `tools/lib/credentials.py:165-166`

### Phase 1.C — Add `SUPABASE_DB_HOST` to Doppler
- Find current value (probably in `daily_backup.sh` or a config file)
- `doppler secrets set SUPABASE_DB_HOST=<value>`
- Verify with `doppler secrets get SUPABASE_DB_HOST`

### Phase 1.D — Add `doppler run --` prefix to weekly snapshot wrapper
- `Production/scripts/_weekly_snapshot_wrapper.sh` — prepend `doppler run --` to the python3 invocation
- Same for `Production/scripts/weekly_preflight_audit.py` if it's invoked by launchd

### Phase 1.E — Multipass verify all 26 callers
For each of the 26 callers identified pre-flight:
- Confirm they still load credentials correctly post-edit (env-first works)
- Run any callable smoke test if available
- Document any caller that breaks

### Phase 1.F — Smoke test
Run a representative caller end-to-end. Confirm:
- Doppler env values are picked up (not MD)
- Operations succeed
- No `_CREDSTORE_FALLBACK_WARNED` warnings on stderr (because Doppler IS providing the values)

### Phase 1.G — Activity log
POST a `prod_activity_log` row documenting Phase 1 completion: file diff summary, callers touched, smoke-test result. Per Rule 35 read-back.

### Phase 1.H — Update LD 227 notes
PATCH LD 227 notes to mark Phase 1 complete with date + commit SHA. Status remains `active`.

---

## Phase 2 (NOT autonomous — Kim manual)

This phase grants Full Disk Access to launchd jobs in System Settings. Cannot be done by an agent. See main session's G5 handoff for steps.

After Phase 2: launchd jobs run successfully → Phase 3 clock starts.

---

## Phase 3 (calendar time, ~14 days)

After Phase 1 + 2 land:
- Set up monitoring: ensure `_CREDSTORE_FALLBACK_WARNED` warnings (if any) write to a log file, not just stderr
- 14 days of zero warnings = Doppler-only is proven
- If even one warning fires → investigate, fix, restart clock

You CANNOT compress this. Don't try.

---

## Phase 4 (separate future session, after Phase 3 completes)

- Delete MD fallback in 4 sites: `tools/lib/credentials.py`, `lib/directus_admin_client.py`, `lib/credential_store.py`, `tools/production_server.py::parse_api_keys`
- Replace key VALUES in `Production/API_KEYS_MASTER.md` with `<REDACTED>` (retain metadata for grep)
- DS-13 Layer 6 verify each: pre-fix exploit (provide bogus env, observe fallback to MD); post-fix exploit (provide bogus env, observe correct failure with no MD fallback)
- PATCH LD 227 status='closed', date_superseded=<today>, closure note
- Activity log

---

## Hard rules for this session

- Per Rule 35: read-back-after-write for every Directus write
- Multipass: re-Read every file after edit
- Rule 24: confidence tags throughout
- DS-13 Layer 6 for any credential-loading code change: pre-fix and post-fix smoke test with bogus env
- HALT if any caller breaks during Phase 1.E (don't auto-fix; surface to Kim)
- Do NOT proceed to Phase 2/3/4 in this session — those are out of scope
- Do NOT remove MD fallback in this session — that's Phase 4

---

## Final report

`Production/docs/LD227_PHASE1_REPORT_<DATE>.md`:
1. Pre-flight inventory (26 callers list verbatim)
2. Per-step diff
3. Per-caller verification (pass/fail)
4. Smoke test verbatim
5. Doppler secrets verbatim (sanitized)
6. Activity log row id
7. LD 227 notes diff
8. Phase 2/3/4 dependencies clearly listed
9. Confidence tags per Rule 24
10. Self-classification

---

## What NOT to do

- Do NOT remove MD fallback (Phase 4)
- Do NOT touch `API_KEYS_MASTER.md` values (Phase 4)
- Do NOT grant FDA (Phase 2 — Kim only)
- Do NOT compress 14-day calendar wait (Phase 3)
- Do NOT modify any `prod_locked_decisions` row other than LD 227

---

## Context for the agent

LD 227 was created 2026-04-18 documenting the dual-credential-source state during Doppler migration. Prior 2026-05-08 agent did inventory + gap analysis but made NO code changes (per Hard Rule). Your job: execute Phase 1 + instrument for Phase 3. The system MUST continue to work post-Phase-1 (env-first with MD fallback safety net) — this is not a "remove MD" session.
