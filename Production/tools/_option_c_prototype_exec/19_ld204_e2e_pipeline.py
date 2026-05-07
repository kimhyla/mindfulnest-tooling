"""Fourth amendment to LD-204: E2E pipeline Flows wired + smoke-validated.

Tests the full production chain (TTS → Kling §8.3 start-end → §8.4 silcomp →
ByteDance LatentSync) through Directus Flows in the prototype.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import hosted  # type: ignore

LD_ID = 204
AMENDMENT_MARKER = "AMENDMENT 2026-04-18 (E2E pipeline wired + smoke-validated):"

AMENDMENT = f"""

---

{AMENDMENT_MARKER}

Kim directive 2026-04-18: wire and smoke-validate the full production chain
(TTS → Kling §8.3 start-end → §8.4 silcomp → ByteDance LatentSync) through
Directus Flows on beat_03, using the real 4:3 image library imported in
amendment #3 and the production_server.py credentials (WaveSpeed, ElevenLabs,
BFL, LatentSync) — without modifying production_server.py itself.

IMPLEMENTATION (all in Production/tools/_option_c_prototype_exec/):

Schema additions on prod_storyboard_beats:
- tts_audio (file FK → directus_files) — raw ElevenLabs output
- tts_audio_compressed (file FK → directus_files) — §8.4 output, input to Lipsync

Adapter (prototype_kling_adapter.py) now exposes 5 endpoints on localhost:8090,
all bridging Directus Flow webhooks to the same underlying APIs
production_server.py uses. Code imports from tools/kling_startend_pipeline.py
(flux_kontext_generate_end_frame, kling_startend_submit, kling_poll_fresh,
ensure_min_dimensions) and tools/lipsync_sender.py (LipSyncClient) — no
duplication of upstream logic, no modification of production code.

  POST /tts           ElevenLabs Jessica (cgSgspJ2msm6clMCkdW9) / eleven_v3
                      / stability 0.5 / style 0.3 / similarity 0.75
  POST /kling-startend §8.3: Rule-6 upscale + BFL FLUX Kontext end-frame at 4:3
                      + Kling v3.0 Pro start-end submit (cfg_scale 0.5,
                      anti-lipsync negatives, no motion-lock). Writes new
                      prod_video_candidates row (source=kling_startend) and
                      sets selected_option.
  POST /silcomp       §8.4: ffmpeg silencedetect (-32dB/150ms), silences >1.0s
                      compressed to 0.8s via lavfi anullsrc + concat demuxer.
  POST /lipsync       ByteDance LatentSync (bytedance/lipsync/audio-to-video).
                      Uses shell-out curl with -4 (force IPv4) for the submit
                      because Python urllib/http.client hit a 75s connect
                      timeout on the ~9MB base64 payload from this machine
                      (IPv6 happy-eyeballs stall). Poll continues via urllib.

4 manual-trigger Flows created in local Directus (all bound to
prod_storyboard_beats):
  1. Render TTS (Jessica eleven_v3)        -> /tts
  2. Generate Animation (Kling §8.3 start-end) -> /kling-startend
  3. Silence Compress (§8.4)               -> /silcomp
  4. Lipsync (ByteDance LatentSync)        -> /lipsync
Each Flow has requireConfirmation=true with a spend estimate in the prompt.

SMOKE VALIDATION (all on beat_04, so beat_03 stays pristine for Kim):
- TTS: ~5s, tts_audio file id f0171eba-7ded-45c6-94e4-74cc2e8cb6f3
- Kling §8.3: 7 min, task 15... (first attempt failed on missing
  negative_prompt arg — fixed), new candidate b3cbf230-...
- silcomp: ~3s, 0 silences detected on the short line (no-op re-encode),
  tts_audio_compressed id b36ce9fa-...
- LatentSync: 6 min total, task c88f413424d94b69bad3124db39f4111,
  lipsync_output id 55259162-d602-4094-b6e2-6b9232d40051
beat_04 final state: status=approved, lipsync_status=done, lipsync_output set.

DEBUG FINDINGS worth archiving:
- kling_startend_submit requires explicit negative_prompt arg (fixed).
- LipSyncClient.submit path uses subprocess curl, which hit the same
  ~75s connect-timeout as Python urllib on 9MB bodies to api.wavespeed.ai.
  Root cause: happy-eyeballs IPv6 stall on Tencent CLB hostname.
  Fix: shell-out curl with explicit -4 flag.
- WaveSpeed network was unreachable for ~3 min during the session
  (curl exit 28 even from bare shell); recovered on its own.

REAL SPEND this session on smoke validation: ~$0.88 (TTS + BFL + Kling +
2 LatentSync attempts). Kim's full click-through on beat_03 will add ~$0.73.
Projected total ~$1.61 — well under the $12 budget.

BEAT_03 RESET TO PRISTINE CLICK-READY STATE:
- id=9ce11ac2-5caa-496d-8376-d21023294f98
- image_override: None (Kim drops from the real 4:3 gallery — tessa_initial
  upscale recommended for §8.3 compatibility)
- dialogue_text: "Hello there. Take a deep breath with me."
- 3 existing real seed candidates (A/B/C from Event_1 beat_03) preserved for
  the 3-up compare widget; dry_run stub removed
- All generated fields cleared: tts_audio, tts_audio_compressed,
  selected_option, lipsync_output, lipsync_status, status

ROLLBACK: unchanged. `rm -rf ~/directus-prototype` tears down local Directus
+ extensions + SQLite + uploads. Hosted Directus has only audit rows
(preflight 47, 48; activity log entries with task_id=option-c-prototype-exec-20260417)."""

def main():
    c = hosted()
    row = c.get_one("prod_locked_decisions", LD_ID)
    current = row.get("decision_text", "")
    if AMENDMENT_MARKER in current:
        print("E2E pipeline amendment already present on LD-204 — no-op.")
        return
    c.update("prod_locked_decisions", LD_ID, {"decision_text": current + AMENDMENT})
    after = c.get_one("prod_locked_decisions", LD_ID)
    assert AMENDMENT_MARKER in after["decision_text"], "Amendment did not persist"
    print(f"LD-{LD_ID} amended (decision_text now {len(after['decision_text'])} chars).")

if __name__ == "__main__":
    main()
