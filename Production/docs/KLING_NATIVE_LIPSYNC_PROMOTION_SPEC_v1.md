# Kling Native LipSync Promotion Spec v1 (draft)

Status: **draft — Kim visual review required before any production swap**

Depends on: `KLING_NATIVE_LIPSYNC_WRAPPER_REPLACEMENT_SPEC_v2.md`

## 1. Summary

Live QA proved native Developer API `POST /v1/videos/lip-sync` can replace WaveSpeed **for humanoid-faced characters** with raw output at or above the 720 gate.

**Arlo (squirrel-humanoid O3 silent base) is the exception:** WaveSpeed still lipsyncs him; native Developer API rejects the same clip with `The model did not detect a human`. That is a **provider parity gap**, not proof Arlo cannot be lipsynced.

## 2. Gate evidence (verified)

| Case | Character | Route | Input | Raw output | Gate |
| --- | --- | --- | --- | --- | --- |
| DD-04 | Tessa | native `/v1/videos/lip-sync` | 1280×720 | 1280×720 + audio | **PASS** |
| AP-06 | Chipper | native `/v1/videos/lip-sync` | 1920×1080 | 1920×1072 + audio | **PASS** |
| DD-01 / AP-03 | Arlo | WaveSpeed | 1080p / 720p | 832×464 + audio | FAIL (resolution) |
| AP-01 / AP-02 | Arlo | native | 1080p / 720p | rejected | FAIL (human detection) |

Artifacts:

```text
Event_1/kling_native_lipsync_experiments/_due_diligence_20260610T221617Z/
Event_1/kling_native_lipsync_experiments/_arlo_parity_20260610T222429Z/
```

## 3. Phased promotion (recommended)

### Phase A — Native sender for gate-passing characters (safe to implement)

Swap `lipsync_sender.py` production submit/poll to native JWT when:

1. Route = `native_kling_lip_sync_a2v`
2. Character/speaker class is **not** in Arlo blocked set (initially: block `speaker == "Arlo"` on O3 voice-fix path until parity)
3. Raw output passes existing `_assert_lipsync_quality` gate before any approval

Characters with live gate pass today: **Tessa, Chipper** (extend list only after live proof per character).

### Phase B — Arlo parity (blocked on engineering alone)

Required before native Arlo:

1. Kling Developer support ticket: WaveSpeed `kwaivgi/kling-lipsync` accepts hosted URL; Developer `/v1/videos/lip-sync` returns human-detection failure on identical Arlo bytes (see AP-01/AP-02 manifests).
2. **Do not** redesign Arlo to be “more human” as a workaround — WaveSpeed already lipsyncs current design.
3. Until Kling resolves: keep WaveSpeed on Arlo O3 voice-fix path **but still enforce raw ≥720 gate** (current behavior — refuse soft upscale).

### Phase C — Retire WaveSpeed lipsync globally

Only when **all** production characters pass native gate on representative beats.

## 4. Implementation checklist (Phase A only)

- [ ] Add `NativeKlingLipSyncClient` parallel to `LipSyncClient` in `lipsync_sender.py` (or adapter switch behind env `KLING_LIPSYNC_TRANSPORT=native|wavespeed`)
- [ ] JWT from `KLING_ACCESS_KEY` / `KLING_SECRET_KEY` (same as experiment adapters)
- [ ] Poll `GET /v1/videos/lip-sync/{task_id}` until `task_status=succeed`
- [ ] Download raw MP4; run existing ffprobe gate unchanged
- [ ] Character router: native default; Arlo → WaveSpeed fallback until Phase B
- [ ] Log provider, task_id, raw profile on every job (existing contract fields)
- [ ] No auto-approval; Kim playback on first native swap per character

## 5. Explicit non-goals

- Do not promote experiment outputs from Beat Gen card automatically
- Do not lower the 720 gate for WaveSpeed 832×464 output
- Do not switch Arlo to identify-face/advanced-lip-sync as production (wrong shape; Tessa advanced failed on audio duration mismatch — fixed in adapters for future experiments only)

## 6. Open questions for Kim

1. OK to ship **Phase A** (Chipper/Tessa native, Arlo stays WaveSpeed+gate) while Kling support works Phase B?
2. Visual review clips: DD-04 raw, AP-06 raw — approve lip quality before Phase A code lands?
