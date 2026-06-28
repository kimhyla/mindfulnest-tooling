# Tech Spec — BG ref drop stale misreport v1

**Date:** 2026-06-25  
**Branch:** `fix/build-sha-drift-banner`  
**Problem:** Char/BG ref library drops show `"Char ref drop failed: Storyboard updated…"` when `CLIENT_BUNDLE_STALE` blocks `pathappPatch` client-side — request never reaches server.

## Root cause (proven)

| Layer | Evidence |
|-------|----------|
| Error text | Exact match `CLIENT_BUNDLE_STALE_MESSAGE` in `buildShaDrift.ts` |
| Client gate | `pathappPatch` returns before fetch when `isClientBundleStale()` |
| Misreport | `BgRefSlot` toasts `${label} drop failed: ${err}` — not wired like save/replace-slot in `73d3b3c` |
| Server OK | curl `POST /api/bg/update-beat` → 200, `written: ["reference_image"]` |

## Category fix

1. **Single stale UX surface** — all Beat Gen mutation handlers including `BgRefSlot` must treat `CLIENT_BUNDLE_STALE` like save/replace-slot: revert optimistic UI, **no action toast**, rely on `BuildShaDriftBanner`.
2. **Contract test** — grep gate that `bg-ref-drop-error` path checks `isClientBundleStaleError` before `pushToast`.
3. **Deploy** — rebuild bundle, fanout to `Event_*/storyboard_v59_prod.html`, `build-sha` = git HEAD.

## Out of scope

- Removing build-sha drift gate (correct safety behavior).
- Server char-ref / milestone sidecar changes (already working).

## Proof

- `test_build_sha_drift_banner.py` extended
- Browser: drag library image → char ref on `:5112/?video=intro&milestone=milestone1_arc1`
- `verify_beatgen_deploy_smoke.sh 5112`
