# Storyboard “Real Fix” — Touchpoint A (Kim)

**Full program:** See **`STORYBOARD_REAL_FIX_ROADMAP.md`** (Phases 0–5, start → stop).

**Purpose:** Lock the minimum inputs so automation (Playwright + refactors) optimizes the **right** system.  
**Time budget:** ~30–45 minutes once.  
**Rule:** This file is the contract until you explicitly revise it.

---

## Before you start

1. **Golden backup exists** — `storyboard_v58_prod.html` stays **untouched** as reference; all refactors happen on a **copy** or **git branch** (see `Production/e2e/README.md` and `scripts/backup_golden_storyboard.sh`).
2. **Server command** you actually use is recorded in §3 (one line).

---

## 1) Must-pass flows (check ✅ or edit)

Automation will mirror these. **Strike** what you never use; **add** one line per missing habit.

| # | Flow | Your ✅ |
|---|------|--------|
| 1 | Open storyboard from **localhost** (not `file://`) — page loads, nav bar visible | |
| 2 | **Beat Generator** tab: pick arc → segment → beats render in panel | |
| 3 | **Accept All to Storyboard** — lines appear in main storyboard; scope feels correct for **this** event/segment | |
| 4 | **Library** — open, refresh, at least one image visible or empty state is sane | |
| 5 | **Library → slot** (or your usual assign path) — still lands on correct beat | |
| 6 | **Crop** — open cropper, save; beat card shows accepted / preview path still works | |
| 7 | **Dialogue save** — at least one line saves; indicator or network shows success | |
| 8 | **Image / patch save** — dropdown or drag-drop still persists (how you actually work) | |
| 9 | **Tab switch** — Storyboard ↔ Beat Generator without blank screen | |
| 10 | **Optional:** export / batch / restart — only if you use it **weekly+** | |

---

## 2) URLs & filenames (fill in)

| Item | Your value |
|------|------------|
| Storyboard URL | `http://localhost:5111/` or `http://localhost:5111/storyboard` |
| Active storyboard file today | e.g. `storyboard_v58_prod.html` |
| Event dir | e.g. `Production/Event_1` |
| `event-id` CLI flag | e.g. `Event_1` |

---

## 3) Exact server start (one command)

Paste the command you use (or from your `.command` launcher):

```
python3 Production/tools/production_server.py --event-dir Production/Event_1 --storyboard storyboard_v58_prod.html --event-id Event_1
```

(Adjust paths if your cwd differs.)

---

## 4) “Done” for Touchpoint A

- [ ] Table in §1 filled or edited  
- [ ] §2 completed  
- [ ] §3 matches how you really start the server  
- [ ] You ran **`npm install` + `npx playwright test`** once from `Production/e2e` (see README) — **green** with server up, or noted failures for Claude to fix  

**After this:** Touchpoint B — **short hands-on pass** through the same flows (see roadmap). Required per release candidate; Playwright green alone is not your gate.

---

## 5) What you do *not* need to do here

- Invent selectors or test code  
- Merge patches or read the 9k-line file  
- Stay online while overnight jobs run  

---

**Version:** 1 — created for the storyboard real-fix program.

---

## 6) Proposed v59 must-pass flows (Claude draft 2026-05-02, Kim edits Session 2)

Split into two sub-sections per Kim 2026-05-02:

- **§6A — Session 1 read-only verification flows** (testable now; smoke passes today)
- **§6B — v59 production workflow contract** (testable after Session 1.5; this is the **cutover gate**)

§6A is the sanity check that Session 1's preview shell works. §6B is the
contract the rewrite must satisfy before v59 replaces v58. The Playwright
suite Session 2 builds (~45 tests) covers §6A in full and stub-tests §6B
where the server endpoint exists; the rest of §6B turns green as Session 1.5
ships server-side scope guards + persistence + snapshot endpoint.

### §6A — Session 1 read-only verification flows

| # | Flow | Why it must pass | Kim's ✅ / edit |
|---|------|------------------|----------------|
| 1 | Page loads at `http://localhost:5111/` after `production_server.py --event-dir Production/Event_1 --storyboard storyboard_v59_prod.html --event-id Event_1`; you see header "Storyboard v2", 4 tabs, library side rail. | Smoke: app actually runs. | |
| 2 | Scope chip in the header reads `Event_1:global:v1` (or current event's name); body has `data-resolved-scope` attribute set. | Confirms ScopeBoundary resolves at boot — client-side half of LD SCOPE_VALIDATION_V1. | |
| 3 | Click each of the 4 tabs (Storyboard / Beat Generator / Cropper / Stitcher); each pane renders without console errors. | All tabs reachable; no blank screens. | |
| 4 | Cropper opens **as a modal overlay** (not a separate page) when invoked from a Storyboard or BG slot. Close button works; clicking the backdrop closes it. | Eliminates v58 double-crop detour (BG → Cropper → Library → BG drag-back → "Use This"). | |
| 5 | Library panel renders Event_1's actual library items (mtime-sorted per LD-452 / Fix-V) with thumbnails; counter in header shows `N items`. | Library is real data, not a placeholder. | |
| 6 | If `/api/cr/library` returns an error (server stopped, network blip), library shows a "Could not reach" banner with the error string — never a silent blank panel. | Visible failure (Fix-Q LD-447 anti-pattern from v58 carried forward). | |
| 7 | Storyboard tab fetches `/api/v2/event-state` and renders the L[] array as numbered beat cards with speaker + text; if the endpoint isn't there (Session 1.5 work), a clear "Could not reach" banner appears, not a blank screen. | Same visibility principle. | |
| 8 | BG tab shows the Cross-Event Accept-All Banner (warning copy stating: scope.event_id will accompany every Accept All POST; server returns HTTP 409 on mismatch). | Communicates that the cross-event leak class is structurally addressed (LD SCOPE_VALIDATION_V1). | |
| 9 | Switch tabs Storyboard ↔ BG ↔ Stitcher ↔ Storyboard rapidly; the active-tab indicator stays in sync; no leak of one tab's state into another. | Catches the wrap-chain class of bugs (Rule 36 origin) at the structural level — components are independent. | |
| 10 | Open DevTools network tab, do all of #1-#9; observe **ZERO POST/PATCH requests** to any `/api/...` endpoint. Only GETs (library, event-state, etc). | Session 1 done-state guarantee: ZERO state writes ship. Mutation channel `pathappPatch()` exists but has no callers until Session 1.5. | |

### §6B — v59 production workflow contract (cutover gate, testable after Session 1.5)

Each row is a real-workflow flow that v59 must satisfy before v59 replaces
v58 in production use. **This is the cutover gate** — until every row here
passes, v58 stays available as the flag fallback (M2 parallel-run gate).

| # | Flow | Why it must pass | Kim's ✅ / edit |
|---|------|------------------|----------------|
| 1 | Drag a library image onto a beat slot → lands on the correct beat → persists across page reload. | Core Storyboard workflow. Persistence verified across reload kills any "browser-memory only" regression class. | |
| 2 | Open the Cropper from a beat row → save the crop → the crop becomes that beat's still. | The double-crop detour is gone (Cropper-as-modal); save round-trip works end-to-end. | |
| 3 | Edit dialogue inline on a beat → save indicator goes green → reload page → the edit persists. | Fix-Q LD-447 invariant carried forward (visible save state) plus persistence. | |
| 4 | Trim a beat (set start/end) → save → reload → trim persists. | Per-beat metadata round-trip. | |
| 5 | Accept All from BG while on Event 1 succeeds. The same `/api/bg/accept-beats` POST with body `event_id=Event_2` returns **HTTP 409**. | Direct end-to-end test of LD-456 SCOPE_VALIDATION_V1. The cross-event Accept-All leak class is structurally impossible. | |
| 6 | Run Kling generation on a beat → option appears in the beat's options array → select it. | Animation pipeline integration (WaveSpeed/Kling) still wires through v59's mutation channel. | |
| 7 | Run lipsync on a beat → the lipsync output becomes the primary clip for that beat. | ByteDance LipSync round-trip still works through v59. | |
| 8 | Add a beat / delete a beat → persists across reload. | Beat-list mutation endpoints round-trip correctly through pathappPatch. | |
| 9 | v59 writes dialogue → flag-flip to v58 (`--storyboard storyboard_v58_prod.html`) → v58 reads back **the same dialogue**. | **Persistence contract verified across the v58↔v59 boundary.** This is M2's literal precondition — without it, parallel-run is unsafe. | |
| 10 | The `/api/state/snapshot` endpoint fires before every mutation; verify a fresh JSON file appears in `Production/Event_1/.backups/state/YYYY-MM-DD_HHMMSSZ.json` for each mutation in #1-#8. | M1 mitigation verified end-to-end. Every v59 write is rollback-able. | |

**Cutover gate logic:** v58 stays the live storyboard until ALL §6B rows
pass. Promote v59 only after Kim has personally verified one complete
module (M2 parallel-run gate) using the v59 app in real production work,
with v58 still callable as the flag fallback for the same module.

**Replace these proposals with §1 form once edited:** copy the rows you keep
into §1, mark ✅, then this §6 can be deleted (or retained as the cutover-
gate checklist).

---

