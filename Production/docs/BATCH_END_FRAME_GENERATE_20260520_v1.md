# Batch End-Frame Generate — Implementation Plan v1.1
Date: 2026-05-20
Branch: `feature/magic-and-endframe-20260520`
Marker: `BATCH_END_FRAME_GEN_20260520_8C72FE91A0B3`
Cursor review: round 1 converged with 4 changes folded.

## §1 Task

Add a single-click batch end-frame generator: walks every beat in the
**currently-selected video role** (e.g. resolution) that has:
1. `phase_1.selected_option != null` (an animation option exists to lipsync against)
2. NO `end_frame_path` already set (or `end_frame_path_exists === false`)
3. **`image_path` set AND `image_path_exists !== false`** (cursor R1: filter
   out beats with no start image; would fail with `START_IMAGE_REQUIRED` and
   waste a toast)

…and calls `/api/beat/preview_end_frame` for each one sequentially. Kim
hits the button once, **leaves this tab open**, comes back to a row of
populated thumbnails. Cursor R1 clarified: client-only loop stops if the
tab is closed/navigated/sleeped — UI copy must say "keep tab open"
(NOT "walk away") to match reality.

## §2 Approach

### Client-only loop, sequential

**Decision: client-only loop. NO new server endpoint.**

- Reuses existing `/api/beat/preview_end_frame` per-beat work
- Partial progress survives connection drops (each beat's state mutation
  is independent)
- No new DS-22 verify path or new test surface
- Sequential keeps OpenAI rate limits + server RAM happy (cursor R1: parallel
  raises 429s, not wall-clock reliability)

### UI placement + locking

- Single button above `<ol class="mn-beat-list">` (between pane header
  and list). Not per-row. One instance per `activeTargetVideo`.
- Label: `✏ Batch end frames (N beats)` where N = filter-matching count
  in current partition only. Disabled when N=0.
- **Lock UI while batch in-flight** (cursor R1): disable VideoSelector,
  EventSelector, and the batch button itself. Prevents scope drift
  mid-loop. video_role is FROZEN at batch start (read `activeTargetVideo.value`
  once, capture in closure, use for all iterations) — defense in depth.
- While running: label switches to `… M of N end frames (Cancel)`. Cancel
  stops further submissions; in-flight OpenAI request cannot be aborted.

### Per-iteration freshness

Each iteration:
1. Re-read `/api/v2/event/{eventId}/state` for FRESHEST state
2. Re-check that beat's end_frame_path is still missing (someone could
   have generated it in another tab between batch start + this iteration)
3. If now present → SKIP (log "already done")
4. Otherwise POST `/api/beat/preview_end_frame` with FROZEN video_role +
   `scope_event_id` from activeScope. NO pathappPatch (cursor R1: body
   shape must match per-beat preview, not a partition mutation).
5. Per-beat `onMutated()` after each success → live thumbnail refresh

### Per-beat error handling

- Each beat's POST in `try/catch`. Failure → toast for that beat, continue.
- Final summary toast: `✓ M succeeded · ✗ K failed · ⏭ S skipped`
- No halt-on-first-error.

### Cost guardrail

- Confirm dialog when N > 5: shows `$0.04 × N = $X.XX` estimated cost +
  **"Keep this tab open until the batch completes"** notice.
- Below 5: just go (no confirm).

## §3 Files to be modified

- `Production/tools/storyboard-v2/src/components/StoryboardTab.tsx` —
  new state hooks for batch progress; new button + lock logic at top of
  beat list
- (No server changes. No state schema changes. No new endpoint.)

## §4 Integration Contract — 12 observables (extended per cursor R1)

| # | User action | Observable | Probe |
|---|---|---|---|
| B-1 | Open Storyboard on resolution where some beats have selected_option+image, no end_frame_path | Button shows `✏ Batch end frames (N beats)` where N counts ONLY active partition (resolution), filter excludes beats missing image_path | curl /api/v2/event/Event_1/state; jq filter to count; assert label |
| B-2 | All beats already have end_frame_path | Button disabled, tooltip `All beats already have an end frame.` | UI state check |
| B-3 | Click button when N ≤ 5 | Loop starts immediately; first beat POSTs to preview_end_frame | server log shows `[preview_end_frame]` lines |
| B-4 | Click button when N > 5 | Confirm dialog shows estimated cost + "Keep tab open" message | click-then-cancel test |
| B-5 | Mid-batch, button shows progress | Label `… 3 of 19 end frames (Cancel)` updates after each completion | UI smoke |
| B-6 | One beat's preview returns 4xx/5xx | Toast for that beat; loop continues to next | manually fail one beat (e.g. unset image_path); assert |
| B-7 | After batch completes | All filtered beats now have `end_frame_path_exists === true`; pruning kept last 3 per beat | curl + ls end_frames/ |
| B-8 | Click Cancel mid-batch | No new POSTs after cancel click; in-flight call completes (1 more may finalize) | server log: no new `[preview_end_frame]` lines after T_cancel |
| B-9 | Inspect POST body for any iteration | `scope_video_role === activeTargetVideo.value at batch start`; `scope_event_id === activeScope.value.event_id` | DevTools Network tab; server log |
| B-10 | N pre-flight calculation | N excludes any beat without image_path OR with image_path_exists === false | jq filter compared to N |
| B-11 | After each successful POST | Thumbnail appears in the beat row live (not after batch completion) | UI smoke; per-iteration onMutated() fires |
| B-12 | Double-click batch button while running | Second click is no-op (button disabled). Re-entry blocked. | UI state check |

## §5 Out of scope

- Server-side batch endpoint
- Parallel concurrent OpenAI calls
- Resume after browser close (idempotence handles re-click; no resume token)
- Cancel of in-flight OpenAI call
- Per-beat custom addendums in batch (uses canonical only; iterate after)
- Beat Gen tab integration (decided earlier — end frames are per-beat)
- Background server worker (would change "tab must stay open" — future enhancement)

## §6 Cursor cross-review prompt (final diff review)

```
Review the diff implementing BATCH_END_FRAME_GENERATE_20260520_v1.md.

Check that each of the 12 observables in §4 is delivered by specific
file:line code paths. Specifically:
1. N filter excludes beats missing image_path (B-10)
2. video_role + scope_event_id frozen at batch start, NOT read fresh from
   stale React closure (B-9)
3. VideoSelector + EventSelector + button disabled during in-flight (B-12)
4. Per-iteration state re-read (B-11)
5. No use of pathappPatch — raw fetch with correct JSON body (BUG-3 risk)
6. Cancel button stops loop but doesn't abort in-flight (B-8)
7. Cost dialog copy includes "Keep tab open" (B-4)

Output: per-observable PASS/FAIL/NEEDS-PROBE + one-line justification.
Max 400 words.
```
