# TECH SPEC — Phase B Avatar Pro production wire v1

**Status:** Superseded for Module tab — see `TECH_SPEC_MODULE_LIPSYNC_LEGACY_REINSTATEMENT_v1.md`. Beat Gen Avatar unchanged.  
**Scope:** Replace Phase B `Send for Lipsync` vendor path (Kling base-loop lipsync) with **Kling V2 Avatar Pro** (still + full voice stem + frozen-BG prompt).  
**Proof anchor:** Event_2 chunk-0 job `fbb800405fb54c829e12e6b795f923f7` — $2.93 / 26.07s — operator-approved quality.

---

## Success statement

Kim clicks **Phase B → Send for Lipsync** on Event_2 (or any event with `phase_b_voice_stem_file` set):

1. Server submits **one** Avatar Pro job using canonical Cedric still + trimmed voice stem + `STATIC_BG_PROMPT`.
2. State shows `phase_b_lipsync_status=polling` + `phase_b_lipsync_method=kling_avatar_pro_v1`.
3. Persistent poller downloads MP4 → `finalize_phase_module_lipsync_delivery` → `phase_b_lipsync_status=done`.
4. Preview player shows lipsync; Export to Stitcher unchanged.
5. No base-clip loop, no segmented Kling chunks, no silent failure on restart (poller survives deploy).

---

## Non-goals (v1)

- Multi-chunk Avatar stitching (pause-aligned segments) — full stem only.
- Parallel Kling-lipsync fallback toggle in UI (retired for Phase B; probe scripts remain for experiments).
- Beat-level Avatar (intro/resolution unchanged).

---

## 3×3 agent debate

Three agents × three axes. **Verdict** column is binding for implementation.

### Axis 1 — Where the Avatar route lives

| Agent | Position | Rationale |
|-------|----------|-----------|
| **A — Patch `handle_phase_b_lipsync` inline** | Add `if avatar:` branch with submit code copied from probe | Fastest diff |
| **B — New module + thin handler** | `phase_b_avatar_lipsync.py` owns still resolve, prompt, submit, cost estimate; handler calls one function | Single test surface; probe and server share contract |
| **C — Generic `phase_vendor_lipsync` router** | Pluggable strategies for A/B/C vendors | Over-engineered for one flip |

**Verdict: B** — Category fix: Phase B lipsync vendor is a **module contract**, not inline patches. Retired Kling-base path removed from handler (not left dead behind a flag).

---

### Axis 2 — Submit transport (image + audio)

| Agent | Position | Rationale |
|-------|----------|-----------|
| **A — Public URL hosting (Catbox/Uguu)** | Match existing `LipSyncClient.submit` | Extra failure surface; Avatar probe proved data-URI works |
| **B — Data URI (probe-validated)** | PNG still + MP3 via base64 in POST body | Worked on real job; no third-party host |
| **C — Dropbox signed URLs** | Reuse production file paths | WaveSpeed cannot reach local/Dropbox URLs |

**Verdict: B** — Use data URI via shared `LipSyncClient.submit_avatar_pro()`. Still prep at submit: `ensure_min_dimensions()` then `ensure_avatar_still_dimensions()` → **1920×1080** (`video_delivery.LIPSYNC_INPUT_*`; scale-to-fit + letterbox/pillarbox).

---

### Axis 3 — Async completion / restart durability

| Agent | Position | Rationale |
|-------|----------|-----------|
| **A — Synchronous `submit_and_wait` in HTTP handler** | Simple | 124s Avatar ≈ 30–50 min wall — kills HTTP, dies on tab close |
| **B — Reuse `sweep_phase_module_lipsync_polls`** | Already wired in `LipsyncPollingThread` | Survives restart; proven for Phase B Kling |
| **C — New Avatar-only poller thread** | Separate sweep | Duplicate lifecycle code |

**Verdict: B** — Submit returns 202 + `task_id`; existing poller + `_write_phase_b_lipsync_complete` unchanged except method/spend metadata.

---

### Axis 4 — UI: base clip picker

| Agent | Position | Rationale |
|-------|----------|-----------|
| **A — Keep base clip required** | No UI change | Misleading — Avatar ignores base clip |
| **B — Hide base clip row for Phase B** | Show canonical still chip + enable Send without clip | Matches mental model |
| **C — Keep picker + label “legacy”** | Confusing dual truth |

**Verdict: B** — Phase B: hide base-clip select; show read-only “Cedric still (Avatar Pro)”; Send enabled when voice stem exists.

---

### Axis 5 — Budget / spend tracking

| Agent | Position | Rationale |
|-------|----------|-----------|
| **A — Keep `COST_PER_LIPSYNC = $0.35`** | No server change | Wrong by ~40× for Avatar; budget gate lies |
| **B — Duration-based estimate at submit + complete** | `$0.1122/s × audio_duration` from real bill | Gate matches WaveSpeed; stored on state for audit |
| **C — Post-hoc billing API poll** | Exact cents | Billing API flaky; estimate sufficient for gate |

**Verdict: B** — `estimate_avatar_pro_usd(duration_s)` constant from measured job; budget preflight uses estimate; `add_spend` uses same at complete.

---

### Axis 6 — Delivery encode

| Agent | Position | Rationale |
|-------|----------|-----------|
| **A — Save raw Avatar bytes** | Skip encode | Regresses kid-facing bitrate/shape gates |
| **B — `finalize_phase_module_lipsync_delivery` on terminal write** | Existing category choke point | Parity with Phase A/B delivery spec |
| **C — Separate Avatar delivery profile** | New ffmpeg recipe | Unnecessary — voice_first_upscale works on probe output |

**Verdict: B** — Unchanged delivery module at `_write_phase_b_lipsync_complete`.

---

### Axis 7 — Still source of truth

| Agent | Position | Rationale |
|-------|----------|-----------|
| **A — Per-event upload only** | Operator picks each time | No canonical; drift across events |
| **B — `phase_b_cedric_contract` canonical still path** | Jun 21 PNG under `NEW STYLE CHARACTERS/CEDRIC/` | Matches probe winner |
| **C — Base clip first frame extract** | Reuses idle base | Reintroduces loop artifact class |

**Verdict: B** — `resolve_phase_b_cedric_still(production_root)` in contract module; state records `phase_b_avatar_still_file` basename on complete.

---

### Axis 8 — Failure visibility

| Agent | Position | Rationale |
|-------|----------|-----------|
| **A — Generic `error: unknown`** | Minimal | Operator cannot act |
| **B — Vendor status + truncated message in `phase_b_lipsync_status`** | Existing poller pattern | UI banner via `phase_lipsync_terminal_banner` |
| **C — Silent retry forever on poll transport error** | Already done for transport | Keep; only vendor `failed` marks terminal error |

**Verdict: B + C** — No new failure class; extend messages for Avatar ETA in progress banner.

---

### Axis 9 — Test strategy

| Agent | Position | Rationale |
|-------|----------|-----------|
| **A — Manual Event_2 only** | One happy path | No regression harness |
| **B — pytest with mocked `submit_avatar_pro` + handler integration** | Proves state writes, budget gate, no base clip required | CI-safe |
| **C — Live $14 full stem in CI** | Real proof | Forbidden — cost + flake |

**Verdict: B** — Unit tests for contract + handler; full QA adds manual/browser proof on Event_2 submit (mock or dry-run curl) + deploy build-sha.

---

## Architecture

```
PhaseProducer (Phase B)
  POST /api/phase_b/lipsync { phase: "b" }   // base_clip_id optional/ignored
       ↓
handle_phase_b_lipsync (phases.py)
  audio trim → phase_b_avatar_lipsync.submit_phase_b_avatar_job(...)
       ↓
LipSyncClient.submit_avatar_pro(still, audio, prompt) → task_id
       ↓
state: polling + method + estimated_cost + pending_out + still
       ↓
LipsyncPollingThread → sweep_phase_module_lipsync_polls
       ↓
_write_phase_b_lipsync_complete → finalize_phase_module_lipsync_delivery
```

---

## State fields (Phase B)

| Field | Set when | Purpose |
|-------|----------|---------|
| `phase_b_lipsync_status` | submit / complete / fail | UI busy + banners |
| `phase_b_lipsync_task_id` | submit | Poller |
| `phase_b_lipsync_pending_out` | submit | Output filename |
| `phase_b_lipsync_method` | submit | `kling_avatar_pro_v1` |
| `phase_b_lipsync_estimated_cost_usd` | submit | Budget audit |
| `phase_b_avatar_still_file` | submit | Which still was used |
| `phase_b_lipsync_audio_duration_s` | submit | Spend + debug |
| `phase_b_lipsync_file` / `_mtime` | complete | Preview + stitch |

Retired for new submits: dependency on `phase_b_cedric_base_clip_id` for lipsync (field may remain in state for legacy exports).

---

## Constants

| Constant | Value | Source |
|----------|-------|--------|
| Endpoint | `kwaivgi/kling-v2-ai-avatar-pro` | Probe + WaveSpeed bill |
| `AVATAR_USD_PER_SEC` | `0.1122` | $2.9257 / 26.074467s |
| Prompt | `STATIC_BG_PROMPT` in probe | Operator-locked |
| Still | `NEW STYLE CHARACTERS/CEDRIC/ChatGPT Image Jun 21, 2026, 10_45_20 PM.png` | Canonical |

---

## Integration checklist (must pass before ship)

- [ ] `handle_phase_b_lipsync` does not call `prep_phase_b_kling_base_video` or `LipSyncClient.submit(video, audio)` for Phase B
- [ ] Phase B budget gate uses duration estimate, not `$0.35`
- [ ] Poller completes Avatar task → delivery encode → `done`
- [ ] UI Send works without base clip (Phase B only)
- [ ] `pytest` new + updated panel tests green
- [ ] Deploy: tooling → Dropbox, storyboard build-sha, server restart, Event_2 Phase B tab smoke

---

## Rollback

Re-enable Kling path only via git revert of this spec’s handler swap — probe scripts and segmented tools remain on disk for experiments, not wired to UI.
