# TECH SPEC — Phase A Avatar Pro production wire v1

**Status:** Approved for implementation  
**Scope:** Replace Phase A `Send for Lipsync` ByteDance-on-base-clip path with **Kling V2 Avatar Pro** (Arlo wizard-desk still + full voice stem + frozen-BG prompt). Parity with Phase B module contract.  
**Proof anchor:** Event_2 probe `phase_a_avatar_pro_probe/phase_a_arlo_avatar_pro_10s_20260624-154539.mp4` — operator-approved quality vs ByteDance middle.

---

## Success statement

Kim clicks **Phase A → Send for Avatar Pro** on Event_2 (voice stem set):

1. Server submits **one** Avatar Pro job using canonical Arlo still + trimmed voice stem + `ARLO_WIZARD_DESK_PROMPT`.
2. State shows `phase_a_lipsync_status=polling` + `phase_a_lipsync_method=kling_avatar_pro_v1`.
3. `sweep_phase_module_lipsync_polls` downloads MP4 → `finalize_phase_module_lipsync_delivery` → `phase_a_lipsync_status=done`.
4. Preview player + Export to Stitcher unchanged.
5. No ByteDance worker thread, no base-clip loop, no segmented chunks.

---

## Category fix (not patch)

| Old class | Patch symptom | Category fix |
|-----------|---------------|--------------|
| Phase A vendor = ByteDance on base clip | UI says Avatar Pro but server runs ByteDance | Single module Avatar contract shared with Phase B: submit → poll → delivery encode |
| Poller phase-hardcoded `"b"` | Phase A would orphan on restart | Poller sweeps **both** `phase_a` and `phase_b` polling rows |
| UI requires base clip for Phase A Send | Blocks Avatar path (still-based) | Phase A UI matches Phase B: canonical still chip + voice stem gate |

---

## Non-goals

- Removing ByteDance library code (scripts / experiments remain on disk).
- Beat Gen routing (already Avatar Pro default for speak beats).
- Phase A fly-in/fly-out (already retired).

---

## 3×3 debate summary (binding)

| Axis | Verdict |
|------|---------|
| Where route lives | `phase_a_avatar_lipsync.py` + thin `handle_phase_a_lipsync` |
| Transport | Data URI via `LipSyncClient.submit_avatar_pro()` (probe-validated) |
| Async completion | Reuse `sweep_phase_module_lipsync_polls` for phase `a` |
| UI base clip | Hide picker; show read-only Arlo still chip |
| Budget | `estimate_avatar_pro_usd(duration)` at submit + complete |
| Delivery | `finalize_phase_module_lipsync_delivery` on terminal write |
| Still source | `resolve_phase_a_arlo_idle_still()` from `phase_a_arlo_contract.py` |
| Still prep | `ensure_min_dimensions()` + `ensure_avatar_still_dimensions()` → **1920×1080** in `submit_avatar_pro()` (shared with Beat Gen / Phase B) |

---

## Verification matrix

| Gate | Command / proof |
|------|-----------------|
| Unit | `pytest tests/test_phase_a_avatar_lipsync.py tests/test_phase_a_avatar_wire.py tests/test_phase_b_avatar_lipsync.py -v` |
| Handler grep | `handle_phase_a_lipsync` contains `submit_avatar_pro`, not `run_phase_a_base_clip_bytedance_lipsync` |
| Deploy | Mirror tooling → Dropbox, storyboard build, restart `:5112` |
| Browser | Phase A tab: Arlo still chip, Send for Avatar Pro enabled with stem |
| User path | POST `/api/phase_a/lipsync` → 202 + `task_id` + `kling_avatar_pro_v1` |
