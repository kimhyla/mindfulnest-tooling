# Patch Behavioral Parity Audit v1
**Date:** 2026-05-02
**Source:** 24 Path B patches (patch_v38_*.py .. patch_v58_*.py) under Production/tools/
**Purpose:** Fixed behaviors that v59 (Path C) MUST preserve. Each row maps to one Playwright test in Production/tools/storyboard-v2/e2e/behavioral-parity.spec.ts.

## Behavior table

| # | Behavior (user-visible) | Source patch(es) | Category | v59 wiring needed |
|---|---|---|---|---|
| 1 | When dialogue text changes (textarea blur), the per-row save indicator turns yellow ("saving"), then green ("saved") on success and pulses; on 409 it shows "conflict - reload"; on 503 falls back to legacy save and shows "legacy mode"; on network error shows red "network error". | patch_v38_bugs_1_2.py, patch_v38_phase1_5_visibility.py, patch_v38_phase1_5.py, patch_v38_phase1_5_hotfix.py | dialogue | Per-row `<save-ind>` element rendered eagerly on mount; pathappPatch wrapper sets state classes (saving/saved/error) with text labels. |
| 2 | When any save action fires, a fixed top-right toast appears with the same state (saving/saved/error) so the change is unmissable from anywhere on the page. | patch_v38_phase1_5_visibility.py | dialogue | Global toast component subscribed to save-state events; auto-dismiss on success. |
| 3 | When skip_tts_regen is set on a [pause] tag click in lipsynced beats, the dialogue patch POST body includes `skip_tts_regen: true` so the server suppresses TTS regeneration. | patch_v38_bugs_1_2.py | dialogue | pathappPatch options propagation: any `{skip_tts_regen}` flag on the call merges into the POST body. |
| 4 | When the client has no known version for a beat, the dialogue patch POST omits `expected_version` entirely (instead of sending 0) so server-side optimistic concurrency does not 409 unedited beats. | patch_v38_phase1_5_hotfix.py | dialogue | Conditional: only include `expected_version` in payload if locally known; never coerce undefined to 0. |
| 5 | When dragging an image into a beat slot, releasing on the slot persists the image_override server-side and shows the saving indicator (and toast). | patch_v38_phase1_5.py | library | Drop handler routes to pathappPatch(beatId, 'image_override', key); same save-state UX as dialogue. |
| 6 | A/B/C radio selection on a beat's option cards persists `selected_option` server-side and shows the save indicator. | patch_v38_phase1_5.py | preview | Radio onchange → pathappPatch(beatId, 'selected_option', n). |
| 7 | Per-beat Trim Start / Trim End sliders persist `trim_start` / `trim_end` on change, the slider max defaults to 60s and re-clamps to actual video duration once metadata loads (so dragging "to the end" before video preload no longer locks in 10s). | patch_v38_phase1_5.py, patch_v38_trim_max_fix.py | timeline | Per-beat trim sliders bound to L[i].trim_start/end; default max 60; on `loadedmetadata` clamp max + value to actual duration. |
| 8 | A per-beat "Fade after" slider lets Kim override the outgoing-pair fade duration; value `-1` shows "inherit" and persists null (use global default), any other value persists `fade_after_ms` for that beat. | patch_v38_fade_after_override.py | timeline | Per-beat composer fade slider; null on inherit; pathappPatch field `fade_after_ms`. |
| 9 | A per-beat pause slider persists `pause_after_ms` (slider value × 1000), an image dropdown persists `image_override`, a speaker dropdown persists `speaker`, ▲▼ row reorder buttons persist global `display_order`, and "+ Add Line" creates a new blank beat (POST /api/v2/beat/create) inserted after the anchored row. | patch_v38_tier3_widgets.py | timeline | Tier-3 per-row composer widgets all routed through pathappPatch (or v2/beat/create for add-line); display_order is global, not per-beat. |
| 10 | Beats with `speaker_mismatch=true` show a stale-audio badge and a "🔁 Re-send for Lip Sync" link is always available (never disabled by the "done" branch); polling/submitting state shows the in-flight task_id (e.g. "⏳ Processing... (task abc12345)"). | patch_v38_lipsync_ux_and_swap.py, patch_v38_tier3_widgets.py | preview | Lip-sync row state machine: stale badge bound to speaker_mismatch; resend link always rendered; in-flight indicator surfaces task_id. |
| 11 | If the lipsync's `bs.source_option` does not match the currently selected A/B/C option, the lipsync button forces "Re-run" state (rather than showing stale completed file). | patch_v38_lipsync_ux_and_swap.py | preview | Compare current selection vs lipsync's source_option; mismatch → Re-run state. |
| 12 | A "🔒 Move to A" button on Option B / Option C cards POSTs swap_to_a; on success a toast confirms "Option A now contains your preserved pick. B and C are free to regenerate." and the row re-renders; on error a red toast shows the server's hint. | patch_v38_lipsync_ux_and_swap.py | preview | Per-option Move-to-A button on B/C; POST /api/v2/beat/{id}/swap_to_a {from_slot:i+1}; toast + re-render. |
| 13 | A preview-stitched bar at the top of the storyboard supports start/snapshot, plays the current stitched mp4 inline, and includes a "✕ Hide" button; the inline preview video is capped at `max-height: 40vh` so the per-beat composer rows below remain reachable. | patch_v38_preview_stitched.py, patch_v38_preview_hide_button.py | preview | Stitched-preview component with snapshot fetch, mp4 stream playback, hide button, and 40vh height cap. |
| 14 | Module-level patches (no beat context) route to /api/v2/module/patch instead of the beat patch endpoint. | patch_v38_preview_stitched.py | dialogue | pathappPatch(null, field, value) → module-patch endpoint. |
| 15 | The top bar (title, health, preview bar, preview player) stays sticky at the top of the viewport regardless of how tall the Phase B / Phase A panels grow — bulky panels, progress wrap, status line, and export button live in a separate non-sticky lower container. | patch_v38_sticky_header.py | ui_chrome | Layout split: sticky header limited to lightweight controls; everything else in a sibling non-sticky region. |
| 16 | Phase B and Phase A authoring panels are mounted (Cedric meditation panel left @ frame_x=40; Chipper demo panel right @ frame_x=800), with a watercolor timeline widget that loads WaveSurfer.js v7 and gracefully falls back to a plain strip if the CDN fails. | patch_v38_phase_b.py | preview | Phase B / Phase A mount points + watercolor timeline component with offline-fallback. |
| 17 | The Cropper tab sidebar shows "⬆ Add Image" (uploads + auto-loads into canvas) and "📚 Library" buttons; clicking a library item while the Cropper tab is active loads the full-resolution image into the cropper canvas. | patch_v47_cropper_add_image.py | crop | Cropper sidebar buttons; lib-item click router that targets canvas when Cropper is active. |
| 18 | The Cropper sidebar (Save / Back controls) sits to the LEFT of the canvas so the right-side library panel never covers the action buttons when it slides open. | patch_v48_cropper_sidebar_left.py | crop | Cropper layout: sidebar left, canvas right; library panel on right is allowed to overlay canvas only. |
| 19 | Beat Generator stills generation has a "Mode: GPT ✨ / FLUX ⚗️" toggle next to "Generate All Stills"; the active mode determines which batch endpoint is called and the rendered options come from gpt_options when set, otherwise flux_options. | patch_v49_gpt_stills_button.py | bg | BG mode state (gpt|flux) + endpoint routing + option-render fallthrough. |
| 20 | Beat Generator shows a "+ Add Beat" insert affordance between (and after) every beat card; clicking POSTs /api/bg/add-beat with after_beat_id and refreshes BG state. | patch_v49_add_beat_button.py | bg | BG insert-between-rows control wired to add-beat endpoint. |
| 21 | Beat-card delete uses a two-click inline guard: first click swaps the × to red "DELETE? ×" with a 3s timeout; second click within the window deletes; clicking elsewhere cancels. | patch_v49_add_beat_button.py | bg | Two-click delete state machine (no native confirm dialog). |
| 22 | When a library image is dropped onto a beat slot, sibling slot zombie thumbnails are cleared, the accepted thumbnail is injected into the top-right `.bg-accepted-preview` corner, and the Crop button on that slot remains clickable. | patch_v51_libdrop_fixes.py, patch_v53_lib_crop_routing.py, patch_v54_lib_crop_disabled_observer.py | library | Lib-drop handler clears sibling DOM state and updates accepted-preview; Crop button is never disabled on lib-marked slots, including after re-render. |
| 23 | Crop key fallback strips a duplicated `bg_bg_` prefix when beat_id already starts with `bg_` so the Cropper loads the correct still rather than 404. | patch_v51_libdrop_fixes.py | crop | Sanitize crop key before fetch: drop leading "bg_" if next chars are "bg_". |
| 24 | Clicking the Crop button on a library-dropped beat slot fetches the full-res image (GET /api/cr/full?abs_path=...), preloads it into the cropper canvas with a default 4:3 box, sets the active beat target so the saved crop routes back to that slot, and switches to the Cropper tab; if MN_LIB_DATA hasn't loaded yet, it auto-fetches and retries once before erroring. | patch_v53_lib_crop_routing.py, patch_v54_lib_crop_disabled_observer.py | crop | Lib→Cropper routing handler + lib-data preload-and-retry; saved crop returns to originating beat. |
| 25 | When a save POST fails on /api/beat/update_text, /api/v2/beat/*/patch, or /api/assign-image, a full-width red banner appears at the top of the viewport (click-to-dismiss); every dialogue keystroke shadow-writes the value to localStorage with 24h TTL; on beforeunload with dirty fields the browser prompts; on next page load orphan recoveries surface a banner and `window._fixQ_recover()` is exposed. | patch_v52_dialogue_save_visibility.py | dialogue | fetch-error banner + per-textarea localStorage shadow + beforeunload guard + recovery sweep on load. |
| 26 | Library "⬆ Add Image" / "⬆ Upload Image" labels render at a consistent 32px height in both the cropper-sidebar and body locations (no 242×747 giant rectangle). | patch_v55_lib_css_regressions.py, patch_v56_lib_scroll_and_selectors.py | library | structural-eliminated — class-based dimensioning lives once on the upload-button component; no parent-relative selector. |
| 27 | The library sidebar's top edge clears the storyboard nav (so newly-uploaded images at scroll-top are visible, not clipped behind the nav). | patch_v55_lib_css_regressions.py | library | structural-eliminated — library sidebar component positioned with proper offset for the page header. |
| 28 | After a new library upload, the library scroll resets so the new item (which sorts to the top) is actually visible at the top of the panel. | patch_v56_lib_scroll_and_selectors.py | library | After upload completes and list re-renders, scroll the library list container to top. |
| 29 | The library's "sources/" tier sorts by mtime descending so the most recently uploaded image appears first. | patch_v57_lib_delete_ui.py (server-side counterpart) | library | Library list ordering: sources tier sorted by mtime desc on the server response (or client sort if rendering raw). |
| 30 | Each library item in the sources tier shows a 🗑 delete button; clicking confirms then POSTs /api/cr/library/delete; on success the item is removed from the panel; FileNotFoundError is treated as already-gone (idempotent). | patch_v57_lib_delete_ui.py | library | Per-item delete control; confirm → POST → remove on 200 or 404. |
| 31 | On every storyboard load, ~500ms after DOMContentLoaded, a runtime healthcheck runs all registered patch invariants; violations log a console warning and POST to /api/patch_health (server logs to prod_activity_log). | patch_v58_healthcheck_runtime.py | other | structural-eliminated for selector/wrap-chain class — but v59 SHOULD register an equivalent runtime invariant probe (e.g. a self-test that verifies key DOM/data contracts) and POST violations to the same endpoint for continuity of telemetry. |

## Categories
- dialogue
- library
- crop
- preview
- export
- ui_chrome
- bg
- timeline
- other

## Patches reviewed

| Patch | Summary |
|---|---|
| patch_v38_bugs_1_2.py | Late-binding fix on save indicator + skip_tts_regen body forwarding |
| patch_v38_fade_after_override.py | Per-beat "Fade after" slider with -1=inherit |
| patch_v38_lipsync_ux_and_swap.py | Lipsync state mismatch detection, always-on resend link, task_id surfaced; Move-to-A button on B/C |
| patch_v38_phase_b.py | Phase B + Phase A authoring panels mount + watercolor timeline (WaveSurfer.js w/ fallback) |
| patch_v38_phase1_5_hotfix.py | Eagerly inject save-ind spans; omit expected_version when client has no known version |
| patch_v38_phase1_5_visibility.py | Top-right fixed-position toast for every pathappPatch state |
| patch_v38_phase1_5.py | Wire dialogue/drop/radio/trim widgets to window.pathappPatch with save-state UX |
| patch_v38_preview_hide_button.py | ✕ Hide button on inline preview + 40vh height cap |
| patch_v38_preview_stitched.py | Preview-stitched bar with snapshot/playback + module-level patch endpoint routing |
| patch_v38_sticky_header.py | Move bulky panels out of sticky root so top bar stays pinned |
| patch_v38_tier3_widgets.py | Tier-3 per-row composer widgets (pause / image / speaker / reorder / add-line / pause-tag) + speaker_mismatch stale-audio badge |
| patch_v38_trim_max_fix.py | Default trim slider max 60s with metadata-load clamp |
| patch_v47_cropper_add_image.py | Cropper sidebar "⬆ Add Image" + "📚 Library" buttons; lib-click loads into canvas |
| patch_v48_cropper_sidebar_left.py | Move cropper sidebar to left so library panel can't cover it |
| patch_v49_add_beat_button.py | "+ Add Beat" affordance between BG cards + two-click delete guard |
| patch_v49_gpt_stills_button.py | GPT vs FLUX BG-mode toggle + GPT batch poll loop + dual-options render |
| patch_v51_libdrop_fixes.py | Lib-drop: zombie sibling cleanup + accepted-preview thumbnail + bg_bg_ key strip |
| patch_v52_dialogue_save_visibility.py | Loud save-failure banner + localStorage shadow + beforeunload + recovery sweep |
| patch_v53_lib_crop_routing.py | Crop button on lib-dropped slots routes to Cropper with image preloaded |
| patch_v54_lib_crop_disabled_observer.py | Keep Crop button enabled on lib slots through every re-render; pre-resolve MN_LIB_DATA |
| patch_v55_lib_css_regressions.py | Add-image label height fix + library top-offset to clear nav |
| patch_v56_lib_scroll_and_selectors.py | Scroll-reset target fix + broaden upload-button selector |
| patch_v57_lib_delete_ui.py | Per-item 🗑 delete button on sources tier (+ server mtime sort) |
| patch_v58_healthcheck_runtime.py | DOMContentLoaded+500ms invariant healthcheck POSTing to /api/patch_health |

## Notes for tests

- Each row's "v59 wiring needed" column is what the v59 tab/component must implement so a Playwright test can assert it.
- Behaviors that were SELECTOR-FRAGILITY workarounds (Rule 36 origin) — rows 26, 27, and the runtime-class portion of row 31 — are marked **structural-eliminated** in the wiring column. v59's component-scoped CSS removes the parent-relative selector class entirely; the test should still assert the user-visible outcome (e.g., upload button is 32px tall, library panel clears the nav) but does not need to assert the workaround mechanism.
- Behaviors gated on a server-side counterpart (rows 29, 30, 31) require the same backend endpoints in v59; the test should hit them through the UI, not via direct API calls, to confirm wiring.
- Row 31 (Rule 36 healthcheck): in v59 this is partially obsolete because Preact+TS removes the wrap-chain class, but the telemetry contract (POST /api/patch_health on assertion failure) is worth preserving so the prod_activity_log dashboard continues to surface drift.
