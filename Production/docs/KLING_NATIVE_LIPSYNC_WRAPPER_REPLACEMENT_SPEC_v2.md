# Kling Native LipSync Wrapper Replacement Spec v2

Status: **active** — supersedes v1 sections 4–5 route selection; v1 invariants still apply.

Parent doc: `KLING_NATIVE_LIPSYNC_WRAPPER_REPLACEMENT_SPEC_v1.md` (non-negotiables, gate, experiment fields).

## 1. What changed in v2

v1 incorrectly treated **identify-face → advanced-lip-sync** as the primary native target. Live QA proved:

| Route | Beat Gen parity | Arlo beat_10 | Tessa g0 |
| --- | --- | --- | --- |
| WaveSpeed `kwaivgi/kling-lipsync/audio-to-video` | **Yes (production today)** | Lipsync OK, raw 832×464 | not primary test |
| Native `POST /v1/videos/lip-sync` (`audio2video`) | **Yes (documented Kling API)** | Failed: human detection | live QA required |
| Native identify-face → advanced-lip-sync | No (different API family) | Failed: human detection | identify OK; advanced blocked on billing pre-purchase |

**Canonical native replacement target:** Developer API `POST /v1/videos/lip-sync` with:

```json
{
  "input": {
    "video_url": "...",
    "mode": "audio2video",
    "audio_type": "url",
    "audio_url": "..."
  }
}
```

Alternate transport for QA: `audio_type: "file"` + base64 `audio_file` (route `native_kling_lip_sync_a2v_b64`).

identify-face → advanced-lip-sync remains a **secondary experiment route only**, not production parity.

## 2. Product truth (non-negotiable)

1. **Kling lipsyncs Arlo** — Beat Gen has done this repeatedly via WaveSpeed; beat_10 job log + control manifest prove completion on identical delivery input.
2. **We are replacing the WaveSpeed wrapper**, not switching away from Kling or ElevenLabs.
3. If native Developer API fails on Arlo while WaveSpeed succeeds on the same bytes, that is a **parity bug to resolve** — not evidence that Arlo cannot be lipsynced.
4. **Promotion remains blocked** until raw provider output passes `min(width,height) >= 720` with audio. No auto-approval.

## 3. Billing wallets (confirmed 2026-06-10)

| Wallet | Pays for | Notes |
| --- | --- | --- |
| Kling web membership credits | kling.ai app generation | Does **not** fund Developer API |
| Kling Developer resource packages | `api-singapore.klingai.com` | Purchased; 1102 resolved; failed jobs may deduct 0 units |
| WaveSpeed balance | `api.wavespeed.ai` production lipsync today | Separate wallet |
| Fal balance | Fal wrapper experiments only | Not production target |

## 4. Live evidence index

```text
Event_1/kling_native_lipsync_experiments/
  bg_arc1_event1_pre_beat_10/control_wavespeed_20260610t2042z/     # DD-01 control
  bg_arc1_event1_pre_beat_10/native_kling_arlo_post_purchase_20260610t2300z/  # DD-02
  _due_diligence_<stamp>/qa_report.json                            # full matrix
```

WaveSpeed control (DD-01): same input sha256 as native attempts; **completed** lipsync; raw **832×464** → `PROVIDER_RAW_GATE_FAILED`.

Native URL (DD-02): task submitted; poll `task_status=failed`, `task_status_msg=The model did not detect a human`; **0 units deducted**.

## 5. QA matrix (due diligence)

Run:

```bash
python3 Production/tools/kling_native_lipsync_due_diligence.py --event-dir "$EVENT_1" --run-live
```

| Case | Route | Input | Purpose |
| --- | --- | --- | --- |
| DD-01 | wavespeed_kling_lipsync_baseline | beat_10 | Control: lipsync works, gate fails |
| DD-02 | native_kling_lip_sync_a2v | beat_10 | Primary native parity |
| DD-03 | native_kling_lip_sync_a2v_b64 | beat_10 | Native audio file transport |
| DD-04 | native_kling_lip_sync_a2v | Tessa g0 + beat_10 audio | Humanoid gate proof |
| DD-05 | native_kling_identify_face_advanced_lipsync | Tessa g0 + beat_10 audio | Secondary route |

Classification buckets: `GATE_PASS`, `PROVIDER_OK_GATE_FAIL`, `PROVIDER_REJECT`, `BILLING_AUTH`, `FAILED`.

**Promotion spec (Phase 2)** is written only after any case hits `GATE_PASS`.

## 6. Open parity work (Phase 1)

### 6.1 Arlo — Developer API vs WaveSpeed (confirmed 2026-06-10)

| Input | WaveSpeed | Native `/v1/videos/lip-sync` |
| --- | --- | --- |
| beat_10 Arlo delivery 1920×1080 | Lipsync OK → raw 832×464 | `The model did not detect a human` |
| Same clip re-encoded 1280×720 | Lipsync OK → raw 832×464 | Same rejection |
| identify-face on Arlo 720p | n/a | code 1201 human detection |
| Chipper g5 1920×1080 + same audio | not tested | **GATE PASS → raw 1920×1072** (AP-06) |

**Conclusion:** Native Developer API face gate accepts humanoid bird/turtle faces (Chipper, Tessa) at full resolution. Arlo requires WaveSpeed partner tier today OR Kling support fix. Resolution and `model_name` tweaks do not unblock Arlo on native.

### 6.2 Next actions

1. Kling support ticket with AP-01/AP-02 manifests + WaveSpeed DD-01 manifest (same hosted URL semantics).
2. **Phase A promotion** per `KLING_NATIVE_LIPSYNC_PROMOTION_SPEC_v1.md` — native for Chipper/Tessa; Arlo stays on WaveSpeed until parity.
3. Do **not** swap `lipsync_sender.py` globally until Kim approves promotion spec + visual review of DD-04 / AP-06 raw outputs.

## 7. Implementation map

| Component | Path |
| --- | --- |
| Adapters | `Production/tools/kling_native_lipsync_adapters.py` |
| Experiment runner | `Production/tools/kling_native_lipsync_experiment.py` |
| Due diligence QA | `Production/tools/kling_native_lipsync_due_diligence.py` |
| Tests | `Production/tools/tests/test_kling_native_lipsync_experiment.py` |
| Beat Gen UI experiment | `storyboard-v2` BgTab + server handlers (unchanged contract) |
| Production lipsync (protected) | `Production/tools/lipsync_sender.py` |

Deploy rule: copy changed tools to Dropbox `Production/tools/` before server UI experiments.

## 8. Do we need this spec?

**Yes — v2 is required.** v1 remains valid for invariants and WaveSpeed downscale evidence, but v2 corrects the native route target and records billing/parity findings so we do not chase the wrong API shape again.
