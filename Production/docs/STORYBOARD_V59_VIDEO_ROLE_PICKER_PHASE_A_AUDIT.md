# Storyboard v59 — Video Role Picker Phase A Audit (REVISED)

**Date:** 2026-05-05
**Spec:** STORYBOARD_V59_VIDEO_ROLE_PICKER_SPEC_v1.md (Cursor v1 + v2 R1-R5 fold APPROVED 2026-05-05)
**Branch:** `claude/video-role-picker` (cut from `main` @ `d11e573`)
**Status:** **HALT — surface to Kim. Audit revision after browser-level evidence overrules first-pass guess. Real root cause: stale deploy in the Dropbox tree, not a missing component.**

---

## A.0 Pre-flight gates — ALL GREEN (unchanged)

| Gate | Result | Proof |
|---|---|---|
| A.0.1 cd + checkout main + pull | ✅ | `1b40d1b..d11e573` fast-forward (15 files, +3315 / -97) |
| A.0.2 cut `claude/video-role-picker` | ✅ | `git branch --show-current` = `claude/video-role-picker` |
| A.0.3 HEAD includes 5 weekend PRs | ✅ | All ancestors of HEAD: `1d375de`, `724942d`, `82c3fae`, `1b40d1b`, `d11e573` |
| A.0.4 CI on main green | ✅ | Smoke + Playwright e2e `success` for `d11e573` (2026-05-04 22:39 UTC) |
| A.0.5 MUTATION_CHANNEL_INVARIANT_V1 grep gate | ✅ | `bash Production/scripts/verify_mutation_channel_invariant_gate.sh` → `G13 PASS` |

---

## A.1 Browser evidence (Kim, 2026-05-05) overrules first-pass audit

Three pieces of new evidence force a re-read:

1. **`mn-video-selector` returns 0 of 0 in DevTools Elements search on Storyboard, Beat Generator, Stitcher tabs.** The component is not in the live DOM, despite being in source.
2. **`body[data-resolved-scope]="Event_1:global:v1"`.** (Kim parsed this as `target_video=global` but the audit re-read corrects: `scopeKey` returns `${event_id}:${beat_id ?? 'global'}:v${version}` per `src/state/scope.ts:25` — the `'global'` is the **`beat_id`** position, not a target_video sentinel. Kim's hypothesis A about a `target_video !== 'global'` gate doesn't match the code.)
3. **The 409 is by-design** per the on-page diagnostic Kim quoted ("LD-456 + LD-461 helper, server-side scope guard active") — the bug isn't a server contract; it's that the picker's selection of Event_2 doesn't propagate into `activeScope.event_id`.

The first-pass audit assumed the SPA build at `Production/tools/storyboard-v2/dist/index.html` (May 4 18:28, 182,117 bytes — contains `mn-video-selector` + `mn-project-selector`) is what the server serves. **That assumption was wrong.**

## A.2 Real root cause — running server serves a stale build from a different tree

`production_server.py:10890` `_serve_storyboard()` reads `self.app.storyboard_path` (a per-event `storyboard_v<NN>_prod.html` file). The running server (PID 56337):

- CWD: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files`
- Launched: `python production_server.py --event-dir Production/Event_1 --storyboard storyboard_v59_prod.html --event-id Event_1`
- Currently pinned to: `Event_2` (Kim switched it via the dropdown)

So the file actually being served on `localhost:5111/` is:
**`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/Event_2/storyboard_v59_prod.html`**

Not `~/Projects/mindfulnest-tooling/Production/tools/storyboard-v2/dist/index.html`.

### A.2.1 Tree comparison

| Path | mtime | Size | `mn-event-selector`? | `mn-project-selector`? | `mn-video-selector`? |
|---|---|---|---|---|---|
| Dropbox `Production/Event_1/storyboard_v59_prod.html` | May 3 00:05 | 71,702 B | ✅ | ❌ | ❌ |
| Dropbox `Production/Event_2/storyboard_v59_prod.html` | May 3 00:05 | 71,702 B | ✅ | ❌ | ❌ |
| Dropbox `Production/tools/storyboard-v2/dist/index.html` | May 3 18:02 | 113,885 B | (newer build, never copied to Event_X) | | |
| Local `Production/tools/storyboard-v2/dist/index.html` | May 4 18:28 | 182,117 B | ✅ | ✅ | ✅ |
| Local `Production/Event_e2e_fixture/storyboard_v59_prod.html` | May 4 10:59 | 173,237 B | ✅ | ✅ | ✅ |

**Per `Production/tools/storyboard-v2/scripts/copy-to-event.sh`,** the deploy step is `cp dist/index.html Production/Event_<N>/storyboard_v<NN>_prod.html`. This was last run on the Dropbox tree on **May 3 00:05** — predating both the May 3 18:02 Dropbox-side rebuild and all subsequent local-tree work (S5.5e ProjectSelector, S5.5g Stitcher SFX/transitions/trims, etc.).

### A.2.2 What this means for each of Kim's symptoms

1. **"No Video Role picker"** — Correct: the served Dropbox HTML predates VideoSelector landing. The component file exists in source but it isn't in the served bundle. Symptom is **deploy-induced, not code-induced**.

2. **"Production Map shows 'intro' in every row"** — Correct: same stale-deploy reason; the served bundle predates whatever rendering changes have landed since May 3.

3. **"Event picker change → 409 Conflict + scope chip stays Event_1"** — The May 3 deployed bundle uses legacy `EventSelector` (`mn-event-selector`). Looking at the current source `EventSelector.tsx:49-89`, after `/api/event/load` it does `setCurrent(data.event_id) → activeScope.value = makeScope(data.event_id, ...) → window.location.reload()`. **But the May 3 bundle is older than the current source** — its EventSelector may not include the `activeScope.value = makeScope(...)` line, may not include the URL-update, or may handle the reload differently. Without diffing against May 3 source we can't know precisely; we only know the served code is older than current.

   The 409 itself is correct LD-456 SCOPE_VALIDATION_V1 behavior — the bug is that the stale client never updates `activeScope` before the next mutation fires. This is a **stale-bundle artifact, not a contract defect.**

## A.3 What the spec misdiagnoses

Spec §1 attributes all three symptoms to "an architectural UI gap … picker is not visible in the current layout." That framing assumed the served HTML was the current source. With evidence in hand, the correct diagnosis is:

| Spec assumption | Reality |
|---|---|
| "Picker not visible — needs to be surfaced" | Picker is in current source + current local dist; just never deployed to the Dropbox tree the running server serves |
| "Wire picker → activeTargetVideo signal" | Already wired in current source (`VideoSelector.tsx:96-98`) |
| "StoryboardTab + BgTab subscribe to activeTargetVideo" | Already done (`StoryboardTab.tsx:770-775`, `BgTab.tsx:163,185`) |
| "Production Map needs per-role columns" | ProductionMap already has 4 segment columns; only `intro_or_resolution` conflation may need splitting (smaller change than spec assumed) |
| "/api/v2/event-state needs full-scope contract LD" | Endpoint already correctly validates URL `<event_id>` per LD-456. No contract change needed. |
| "3 NEW HARD LDs" | None of the 3 has its premise intact after the deploy reality check |

## A.4 Revised hypotheses for what (if anything) is a code bug

To separate "code bug" from "deploy gap" we need to confirm by **redeploying the current local build to the Dropbox tree's `Production/Event_1/` and `Production/Event_2/`** (via `copy-to-event.sh` adapted, or manual `cp`) and re-testing in Kim's browser. After redeploy:

- **If all three symptoms vanish:** the issue was 100% deploy-induced. No spec, no LDs, no tests needed beyond what's already merged. (But: write a small CSS rule for `.mn-video-selector` to ensure the picker is visually distinguishable from siblings — currently has no style rules in `app.css`.)
- **If picker now visible but still feels invisible:** add `.mn-video-selector { display: inline-flex; align-items: center; gap: 6px; margin-left: 12px; }` mirroring `.mn-event-selector` (lines 266-287 in `app.css`). Small, single-LD change.
- **If event-picker → scope propagation still broken after redeploy:** that's a real client-side bug worth a HARD LD `EVENT_PICKER_PROPAGATES_TO_ACTIVE_SCOPE_V1` per Kim's note. Most likely culprit is in `ProjectSelector.onChange` or `EventSelector.onChange` — a real fix is small (ensure activeScope.value assignment + reload). Audit at that point.
- **If Production Map per-role columns still conflate intro+resolution:** small split. Single test, single LD.

## A.5 Recommended path — option-driven, not pre-prescribed

Per spec §7 escape hatch governance: HALT and surface to Kim with the deploy-gap finding. Three options, ranked:

### Option 1 — Redeploy first, then audit again (RECOMMENDED)

1. Build local SPA: `cd Production/tools/storyboard-v2 && npm run build`
2. Copy to Dropbox `Production/Event_1/storyboard_v59_prod.html` AND `Production/Event_2/storyboard_v59_prod.html` (manual `cp` since `copy-to-event.sh` resolves to the local tree which has no `Event_1/` or `Event_2/` directories — the Dropbox tree is where they live)
3. Restart server pinned to `Event_1`
4. Kim re-tests in browser
5. Audit anything that's STILL broken after redeploy
6. **Then** scope tests + LDs to whatever's actually a code bug

This avoids over-shipping LDs/tests for symptoms that vanish on redeploy.

### Option 2 — Write the LDs Kim outlined now, regardless

Per Kim's revised root-cause framing in the latest message:

- DROP `EVENT_STATE_FULL_SCOPE_CONTRACT_V1` (premise wrong). ✅
- ADD `EVENT_PICKER_PROPAGATES_TO_ACTIVE_SCOPE_V1` (HARD).
- Keep `VIDEO_ROLE_PICKER_UI_V1` (HARD) — render unconditionally OR default `target_video='intro'` on event load (audit picks).
- Keep/Adjust `PRODUCTION_MAP_PER_ROLE_COLUMNS_V1` (HARD) — downstream of picker.

This commits LDs before we know which symptoms were stale-deploy artifacts. Risk: 1-2 of the 3 LDs may be no-ops on redeploy, leaving HARD invariants for behavior the codebase already guarantees.

### Option 3 — Ignore the deploy gap, write the spec's original 3 LDs verbatim

Disrecommended. Would commit `EVENT_STATE_FULL_SCOPE_CONTRACT_V1` despite its premise being wrong, and over-ship picker/map LDs that mostly already hold in the code we just haven't deployed.

## A.6 Action requested

Per CLAUDE Rule 26 (escalate when audit reveals material spec/reality divergence) + spec §7 escape hatch governance: HALT pending Kim's choice.

**Three concrete asks:**

1. **Pick Option 1, 2, or 3 above.** I default to Option 1 unless overridden.
2. **For Option 1:** confirm I should run the build + manual `cp` to `Dropbox/Production/Event_1/` and `Dropbox/Production/Event_2/`. This writes to the Dropbox tree (shared state) so I want explicit go-ahead, not assumed.
3. **Confirm `target_video='global'` parsing correction.** Kim's hypothesis A presumed a `target_video !== 'global'` render gate. The codebase `scopeKey` formats as `${event_id}:${beat_id ?? 'global'}:v${version}` — `'global'` is `beat_id`, not `target_video`. Audit recommends dropping hypothesis A.

Holding all Directus writes (no `prod_preflight_reviews` row yet, no LDs), all code edits, and all commits until Kim picks. Branch `claude/video-role-picker` is cut and clean.

---

**End of Phase A audit (revised after browser evidence).**
