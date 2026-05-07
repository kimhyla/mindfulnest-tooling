# Storyboard Real Fix — Full Roadmap (Start → Stop)

**Purpose:** One checklist from **first setup** through **cutover** and **steady state**. Use with:

- `STORYBOARD_REAL_FIX_TOUCHPOINT_A.md` — Kim’s must-pass flows + URLs (Touchpoint A)
- `Production/e2e/README.md` — Playwright install + run
- `Production/scripts/backup_golden_storyboard.sh` — golden backup

**Rule:** `storyboard_v58_prod.html` (or your chosen golden file) stays **untouched** until an explicit **cutover** step; work on a **copy** or **git branch**.

### Kim involvement (locked policy — 2026)

| Step | Time (typ.) | What you do |
|------|-------------|-------------|
| **Touchpoint A** | ~30–45 min, **once** | Fill Touchpoint A doc: flows that must never break, exact URL, server start command. *Required — without this, automation optimizes the wrong thing.* |
| **Touchpoint B** | ~20–40 min **per release candidate** | **Short hands-on pass** through those same flows on the branch/candidate. *This is the chosen gate — not “trust green only.”* Something must certify “this is still my tool.” |
| **Cutover** | ~10–20 min | Approve loading the new storyboard path/bundle on the server (or pre-approve “merge when tests green” **after** B is done). |
| **Emergency** | ~5 min | Restore golden backup or revert branch — not days of co-debugging. |

**Rough total your time:** ~**1–2 hours** across **2–4 short sessions** (not weeks of daily work), assuming Phases 1–2 stay machine-driven and tests stay green.

---

## Phase 0 — Safety net + contract (foundation)

- [ ] **Golden backup** — Run `backup_golden_storyboard.sh` at least once; know restore command (`cp` from `*_GOLDEN_BACKUP_*` back to prod filename).
- [ ] **Git branch** (recommended) — e.g. `storyboard-real-fix`; all work lands here until cutover.
- [ ] **Touchpoint A complete** — Fill `STORYBOARD_REAL_FIX_TOUCHPOINT_A.md` §1–§3 (flows, URLs, server command).
- [ ] **E2E folder bootstrapped** — `Production/e2e`: `npm install`, `npx playwright install chromium` (or `PLAYWRIGHT_USE_SYSTEM_CHROME=1`), `npm test` **green**.
- [ ] **Baseline smoke** — Current tests pass against **golden** storyboard + your normal server flags.

---

## Phase 1 — Playwright = contract (before big refactors)

Expand automation so refactors are **proven**, not guessed.

- [ ] **Map every Touchpoint A row** to a test (or explicit “manual only” with reason).
- [ ] **Beat Generator** — load arc/segment; beats render (selectors stable).
- [ ] **Accept All to Storyboard** — `L[]` / tab / network assertion (as feasible headless).
- [ ] **Library** — open, refresh, at least one assertion on panel state.
- [ ] **Crop path** — save + preview / card state (may need API mocks or server fixtures).
- [ ] **Saves** — dialogue + image/patch path you actually use.
- [ ] **Scope sanity** — scenario for “wrong event” class if applicable (segment A vs B).
- [ ] **CI or nightly** (optional) — same `npm test` on a schedule or on push.

**Stop gate:** Touchpoint A flows are **either** automated **or** explicitly deferred with a ticket.

---

## Phase 2 — Architecture (the “real fix” body)

Mostly **Claude + terminal**; Kim **not** in the loop except async review.

- [ ] **Scope model** — Single object or convention for `(event, storyboard file/stem, segment)`; no silent aliasing between `BG_*` and `L[]`.
- [ ] **Server validation** — Dangerous endpoints (e.g. `/api/bg/accept-beats`) reject illegal cross-scope payloads; log clearly.
- [ ] **Collapse wrap chains** — For each hot path (`_mnLibFetch`, `_bgRenderBeats`, `_bgAcceptToStoryboardV3`, `fetch`, etc.): one composed implementation; remove obsolete Path B layers per **Rule 27** after merge.
- [ ] **Module + build** — JS in modules; bundle emitted via Path A script or deterministic build step; stop editing 9k-line monolith as the default workflow.
- [ ] **`patch_invariant_audit.py`** — Clean or justify on each Path B touch (**Rule 36**).

**Stop gate:** Playwright **green** on branch; no known regression vs Phase 1 suite.

---

## Phase 3 — Touchpoint B (Kim, one session per candidate)

**Policy:** **Short hands-on pass required** — walk the Touchpoint A flows on the **branch/candidate** (20–40 min). Playwright green is **necessary** but **not sufficient** for your gate.

- [ ] **Hands-on pass** — Same flows as Touchpoint A table; note anything off before cutover.
- [ ] **If red** — Revert to golden or reset branch; fix forward with **failing test first** (add test that would have caught it).

---

## Phase 4 — Cutover (promote new artifact)

- [ ] **Server CLI / launcher** updated to load **new** storyboard filename or bundled output (document exact flag line).
- [ ] **Smoke + Playwright** on the **promoted** path (not only dev copy).
- [ ] **Golden v58 retained** as archive until you **explicitly** delete or archive it.

**Stop gate:** Kim **cutover approval** after Touchpoint B hands-on pass (and Playwright green on promoted path).

---

## Phase 5 — Steady state (stop repeating the patch spiral)

- [ ] **Path B rare** — Hotfixes only; each change runs **audit + tests**.
- [ ] **Rule 36** — INVARIANTS + `patch_invariant_audit` + `__patchHealthcheck` where applicable.
- [ ] **Periodic** — Re-run Touchpoint A flows quarterly or after major pipeline changes.

---

## One-page “start → stop” summary

| Stage | Owner | What |
|-------|--------|------|
| **0** | Kim + setup | Backup, branch, Touchpoint A, E2E green |
| **1** | Claude + tests | Full Playwright coverage of A |
| **2** | Claude + terminal | Scope, server, unwrap, modules, build |
| **3** | Kim | Touchpoint B — **hands-on pass** per candidate |
| **4** | Kim + Claude | Cutover, promote, final smoke |
| **5** | Ongoing | Discipline: tests + audit, not stack patches |

---

**Version:** 2 — Touchpoint B locked to **short hands-on pass** (not trust-green-only).

