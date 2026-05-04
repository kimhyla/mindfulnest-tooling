# Tier 3 Browser E2E Report — 20260418_154211

- Total: **13** — Passed: **11** — Failed: **2**
- Total runtime: **71.65s**
- Snapshot: `production_state.pre_browser_test_20260418_154211.json`
- Pre-test SHA256:  `017090fe6adf9f16afd5d12f717b9ad234e73824a18dbb8bbc3cdfe579593ea4`
- Post-restore SHA: `017090fe6adf9f16afd5d12f717b9ad234e73824a18dbb8bbc3cdfe579593ea4` (MATCH)
- Test-created beats: ['beat_12']

## Summary Table

| # | Tier | Name | Result | Duration | Screenshot |
|---|------|------|--------|----------|------------|
| 1 | P0 | `page_load_hydration` | PASS | 0.77s | `page_load_hydration.png` |
| 2 | P0 | `toast_appears_on_pathappPatch` | FAIL | 4.74s | `toast_appears_on_pathappPatch.png` |
| 3 | P0 | `pause_slider_persists_on_release` | PASS | 4.49s | `pause_slider_persists_on_release.png` |
| 4 | P0 | `image_dropdown_persists` | PASS | 4.51s | `image_dropdown_persists.png` |
| 5 | P0 | `speaker_dropdown_stale_badge` | PASS | 7.69s | `speaker_dropdown_stale_badge.png` |
| 6 | P0 | `row_reorder_display_order` | PASS | 6.86s | `row_reorder_display_order.png` |
| 7 | P0 | `add_line_creates_beat` | PASS | 2.46s | `add_line_creates_beat.png` |
| 8 | P0 | `pause_tag_button_no_tts_regen` | FAIL | 11.25s | `pause_tag_button_no_tts_regen.png` |
| 9 | P1 | `dialogue_edit_debounce` | PASS | 12.65s | `dialogue_edit_debounce.png` |
| 10 | P1 | `drag_drop_image` | PASS | 4.49s | `drag_drop_image.png` |
| 11 | P1 | `ab_c_pick_button` | PASS | 4.43s | `ab_c_pick_button.png` |
| 12 | P1 | `reload_persistence` | PASS | 4.98s | `reload_persistence.png` |
| 13 | OPT | `error_fallback_red_toast` | PASS | 1.11s | `error_fallback_red_toast.png` |

## Test Details

### 1. `page_load_hydration` [P0] — PASS

**Evidence:**
- hydrated_log=True seeded_log=True toast_log=True
- globals={'pathappPatch': True, 'routedPatch': True, 'pathappToast': True}

**Console (filtered):**
```
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
```

**Network (/api/v2/ only):**
```
GET http://localhost:5111/api/v2/storyboard/L.json
```

**Screenshot:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/tests/browser_screenshots/page_load_hydration.png`

### 2. `toast_appears_on_pathappPatch` [P0] — FAIL

**Error:**
```
PRODUCTION BUG SURFACED: pathappPatch uses a lexical closure reference to pathappSetSaveInd (line 1896 in storyboard_v38_prod.html), so the monkey-patched window.pathappSetSaveInd toast-wrapper is bypassed. The success toast never fires for user-visible save events. Fix: pathappPatch should call window.pathappSetSaveInd (attribute lookup), not the local reference.
```

**Evidence:**
- patch_result={"status": "applied", "new_version": 20, "beat": {"text": "test-probe-delme", "text_last_updated_at": "2026-04-18T19:34:06.485840+00:00", "_version": 20, "phase_1": {"selected_option": 1, "trim_start": 1234, "trim_end": 
- window.pathappSetSaveInd_invocations_via_pathappPatch=0
- pathappToast_direct={"text": "\u2713 Saved", "cls": "pathapp-toast saved visible"}
- beat_99_test.phase_1.trim_start=1234.0

**Console (filtered):**
```
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
```

**Network (/api/v2/ only):**
```
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
GET http://localhost:5111/api/v2/storyboard/L.json
```

**Screenshot:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/tests/browser_screenshots/toast_appears_on_pathappPatch.png`

### 3. `pause_slider_persists_on_release` [P0] — PASS

**Evidence:**
- baseline pause_after_ms=None
- routedPatch_poll={"timeout": true}
- post pause_after_ms=1700
- v2_patch_posts_count=1

**Console (filtered):**
```
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
```

**Network (/api/v2/ only):**
```
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
GET http://localhost:5111/api/v2/storyboard/L.json
```

**Screenshot:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/tests/browser_screenshots/pause_slider_persists_on_release.png`

### 4. `image_dropdown_persists` [P0] — PASS

**Evidence:**
- routedPatch_poll={"timeout": true}
- image_override=tessa_closeup_4x3

**Console (filtered):**
```
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
```

**Network (/api/v2/ only):**
```
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
GET http://localhost:5111/api/v2/storyboard/L.json
```

**Screenshot:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/tests/browser_screenshots/image_dropdown_persists.png`

### 5. `speaker_dropdown_stale_badge` [P0] — PASS

**Evidence:**
- pre_beat={"beat_id": "beat_99_test", "beat": {"text": "test-probe-delme", "text_last_updated_at": "2026-04-18T19:34:06.485840+00:00", "_version": 22, "phase_1": {"selected_option": 1, "trim_start": 1234.0, "trim_end": 5.5, "audio_delay": 0.5, "pause
- speaker_change_result={"status": "applied", "new_version": 24, "beat": {"text": "test-probe-delme", "text_last_updated_at": "2026-04-18T19:34:06.485840+00:00", "_version": 24, "phase_1": {"selected_option": 1, "trim_start"
- speaker='Tessa' speaker_mismatch=True
- audio_stale_badge_css_rule_present=True
- badge_paints={"present": true, "text": "\u26a0 audio stale (click Regen Audio)"}

**Console (filtered):**
```
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
```

**Network (/api/v2/ only):**
```
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
```

**Screenshot:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/tests/browser_screenshots/speaker_dropdown_stale_badge.png`

### 6. `row_reorder_display_order` [P0] — PASS

**Evidence:**
- baseline display_order len=11
- reorder_result={"timeout": true}
- post display_order[:3]=['beat_02', 'beat_01', 'beat_03']
- restore_call=True
- restore_ok=True

**Console (filtered):**
```
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
```

**Network (/api/v2/ only):**
```
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/__global__/patch
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/__global__/patch
```

**Screenshot:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/tests/browser_screenshots/row_reorder_display_order.png`

### 7. `add_line_creates_beat` [P0] — PASS

**Evidence:**
- pre_rows_in_dom=11 pre_display_order_len=11
- create_response={"status": "created", "beat_id": "beat_12", "inserted_after": null, "display_order_len": 12}
- post_rows_in_dom=12 post_display_order_len=12
- new_beat_id=beat_12

**Console (filtered):**
```
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
```

**Network (/api/v2/ only):**
```
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/create
GET http://localhost:5111/api/v2/storyboard/L.json
```

**Screenshot:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/tests/browser_screenshots/add_line_creates_beat.png`

### 8. `pause_tag_button_no_tts_regen` [P0] — FAIL

**Error:**
```
PRODUCTION BUG SURFACED (LD 244 violated): Tier 3 [pause] button wrapper sets options.skip_tts_regen=true when _t3PauseBlurPending is true, but pathappPatch() (line 1883 of storyboard_v38_prod.html) builds `body` from {field,value,mutation_id} only and NEVER copies options.skip_tts_regen. As a result the server receives no skip flag and the [pause] tag insertion would trigger a TTS regen on any beat that has existing audio. Fix: in pathappPatch, add `if (options.skip_tts_regen) body.skip_tts_regen = true;` after the body is built. Evidence: [pause]_in_value=True, body_has_flag=False, fetch_intercept=[{'field': 'dialogue', 'value': 'fetch-probe 1776541370348', 'mutation_id': 'fa842f26-f381-4f55-a1e4-6b900d6e2065', 'expected_version': 25}]
```

**Evidence:**
- pathappPatch_result={"status": "applied", "new_version": 25, "beat": {"text": "test dialogue with [pause] inserted by test 1776541364624", "_version": 25}, "legacy": {"ok": true, "beat": "beat_99_test", "saved_at": "2026-04-18T19:42:45.230515+00:00", "html_pat
- captured_dialogue_posts=1
- skip_tts_flag_in_POST_body=False [pause]_in_value=True
- legacy.tts_regen.ok=None legacy.tts_regen.skipped=None
- fetch_intercepted_bodies=[{"field": "dialogue", "value": "fetch-probe 1776541370348", "mutation_id": "fa842f26-f381-4f55-a1e4-6b900d6e2065", "expected_version": 25}]
- wrapper_forwarded_skip_tts_to_body=False

**Console (filtered):**
```
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
```

**Network (/api/v2/ only):**
```
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
```

**Screenshot:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/tests/browser_screenshots/pause_tag_button_no_tts_regen.png`

### 9. `dialogue_edit_debounce` [P1] — PASS

**Evidence:**
- num_results=3
- v2_patch_posts_for_beat_99_test=3
- tts_fired=0 tts_skipped=0

**Console (filtered):**
```
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
```

**Network (/api/v2/ only):**
```
GET http://localhost:5111/api/v2/storyboard/L.json
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
```

**Screenshot:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/tests/browser_screenshots/dialogue_edit_debounce.png`

### 10. `drag_drop_image` [P1] — PASS

**Evidence:**
- drop_sim_result={"timeout": true}
- image_override=beat02_guidebird_closeup

**Console (filtered):**
```
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
```

**Network (/api/v2/ only):**
```
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
GET http://localhost:5111/api/v2/storyboard/L.json
```

**Screenshot:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/tests/browser_screenshots/drag_drop_image.png`

### 11. `ab_c_pick_button` [P1] — PASS

**Evidence:**
- pre_selected_option=1
- pick_result={"timeout": true}
- post_selected_option=2

**Console (filtered):**
```
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
```

**Network (/api/v2/ only):**
```
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
GET http://localhost:5111/api/v2/storyboard/L.json
```

**Screenshot:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/tests/browser_screenshots/ab_c_pick_button.png`

### 12. `reload_persistence` [P1] — PASS

**Evidence:**
- server trim_end=7.75 client_ver=None

**Console (filtered):**
```
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[warning] [pathapp] hydrate failed, using embedded L[]: TypeError: Failed to fetch
    at window.fetch (http://localhost:5111/storyboard:1667:27)
    at pathappHydrate (http://localhost:5111/storyboard:1818:24)
    at HTMLDocument.pathappHydrateAndSeedIndicators (http://localhost:5111/storyboard:1949:17)
[log] [hotfix] seeded 11 save-ind spans
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
```

**Network (/api/v2/ only):**
```
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
GET http://localhost:5111/api/v2/storyboard/L.json
GET http://localhost:5111/api/v2/storyboard/L.json
GET http://localhost:5111/api/v2/storyboard/L.json
GET http://localhost:5111/api/v2/storyboard/L.json
```

**Screenshot:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/tests/browser_screenshots/reload_persistence.png`

### 13. `error_fallback_red_toast` [OPT] — PASS

**Evidence:**
- error_toast_text='⚠ Save failed for beat_99_test trim_start: offline. Refresh to retry.'

**Console (filtered):**
```
[log] [phase1.5-viz] toast installed
[log] [T3] Tier 3 widget support loaded. TIER3_ENABLED= true
[log] [pathapp] hydrated 10 beats from sidecar
[log] [hotfix] seeded 11 save-ind spans
[warning] [T3] save failed, no legacy fallback: test beat_99_test trim_start offline
```

**Network (/api/v2/ only):**
```
GET http://localhost:5111/api/v2/storyboard/L.json
POST http://localhost:5111/api/v2/beat/beat_99_test/patch
GET http://localhost:5111/api/v2/storyboard/L.json
```

**Screenshot:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/tools/tests/browser_screenshots/error_fallback_red_toast.png`

