"""Full E2E pipeline smoke test on beat_04.

Assigns a gallery image, sets clean dialogue, then fires all 4 endpoints
sequentially via direct POST (simulating what the Flow buttons would do).
Polls for completion at each stage.

Expected real-money spend: ~$0.73
  TTS ~$0.05 | Kling start-end (BFL + Kling) ~$0.53 | LatentSync ~$0.15
"""
from __future__ import annotations
import sys, time, json, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import local  # type: ignore

ADAPTER = "http://127.0.0.1:8090"
SMOKE_BEAT = 4
SMOKE_DIALOGUE = "Hello there. Take a deep breath with me."


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{ADAPTER}{path}", data=json.dumps(body).encode(),
        method="POST", headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read())


def poll_until(c, beat_id: str, kind: str, expected_field: str, timeout_s: int):
    """Poll until beat[expected_field] changes OR kind job fails."""
    start = time.time()
    last_stage = None
    last_err = None
    while time.time() - start < timeout_s:
        time.sleep(5)
        try:
            with urllib.request.urlopen(f"{ADAPTER}/", timeout=5) as r:
                st = json.loads(r.read())
            job = st.get("active_jobs", {}).get(f"{beat_id}:{kind}", {})
            stage = job.get("stage", "—")
            err = job.get("error")
        except Exception as e:
            stage, err = "(adapter poll)", str(e)
        b = c.get_one("prod_storyboard_beats", beat_id)
        field_set = bool(b.get(expected_field))
        elapsed = int(time.time() - start)
        if stage != last_stage or err != last_err:
            print(f"    [t+{elapsed}s] stage={stage}  err={err}  {expected_field}={'set' if field_set else '—'}  status={b.get('status')}")
            last_stage, last_err = stage, err
        if field_set:
            return True, b
        if err:
            return False, b
    return False, c.get_one("prod_storyboard_beats", beat_id)


def main():
    c = local()
    beat = c.get("prod_storyboard_beats", filters={"beat_number": SMOKE_BEAT}, limit=1)[0]
    beat_id = beat["id"]
    print(f"=== smoke test on beat_{SMOKE_BEAT} (id={beat_id}) ===\n")

    # Pick a gallery image (prefer Rule 6 compliant upscale).
    # Directus boolean filter needs string "true" via query params.
    r = c._request("GET", "/items/prod_visual_assets", params={
        "filter[rule6_compliant][_eq]": "true",
        "fields": "id,filename,file,asset_type,width,height",
        "sort": "asset_type",
        "limit": 10,
    })
    rows = r.get("data", [])
    if not rows:
        # Fall back to any image if no rule6-compliant one is registered
        r = c._request("GET", "/items/prod_visual_assets", params={
            "fields": "id,filename,file,asset_type,width,height", "limit": 10,
        })
        rows = r.get("data", [])
    if not rows:
        raise SystemExit("no gallery images at all")
    chosen = rows[0]
    print(f"gallery pick: {chosen['filename']} (asset_type={chosen['asset_type']}, file={chosen['file'][:8]}…)")

    # Reset + prep beat_04
    c.update("prod_storyboard_beats", beat_id, {
        "image_override": chosen["file"],
        "dialogue_text": SMOKE_DIALOGUE,
        "status": "pending",
        "lipsync_status": "none",
        "selected_option": None,
        "tts_audio": None,
        "tts_audio_compressed": None,
        "lipsync_output": None,
        "kim_feedback": None,
    })
    print(f"prepped beat_{SMOKE_BEAT}: image={chosen['file'][:8]}…, dialogue='{SMOKE_DIALOGUE}'\n")

    # --- Step 1: TTS ---
    print("STEP 1: POST /tts")
    s, r = post("/tts", {"beat_id": beat_id})
    print(f"  -> {s} {r}")
    ok, b = poll_until(c, beat_id, "tts", "tts_audio", 120)
    print(f"  TTS {'OK' if ok else 'FAILED'}  tts_audio={b.get('tts_audio')}\n")
    if not ok: return

    # --- Step 2: Kling §8.3 ---
    print("STEP 2: POST /kling-startend (real ~$0.53, ~3-5 min)")
    s, r = post("/kling-startend", {"beat_id": beat_id, "duration": 5})
    print(f"  -> {s} {r}")
    ok, b = poll_until(c, beat_id, "kling-startend", "selected_option", 9 * 60)
    print(f"  Kling §8.3 {'OK' if ok else 'FAILED'}  selected_option={b.get('selected_option')}\n")
    if not ok: return

    # --- Step 3: silcomp ---
    print("STEP 3: POST /silcomp")
    s, r = post("/silcomp", {"beat_id": beat_id})
    print(f"  -> {s} {r}")
    ok, b = poll_until(c, beat_id, "silcomp", "tts_audio_compressed", 60)
    print(f"  silcomp {'OK' if ok else 'FAILED'}  tts_audio_compressed={b.get('tts_audio_compressed')}\n")
    if not ok: return

    # --- Step 4: lipsync ---
    print("STEP 4: POST /lipsync (real ~$0.15, ~2-5 min)")
    s, r = post("/lipsync", {"beat_id": beat_id})
    print(f"  -> {s} {r}")
    ok, b = poll_until(c, beat_id, "lipsync", "lipsync_output", 9 * 60)
    print(f"  Lipsync {'OK' if ok else 'FAILED'}  lipsync_output={b.get('lipsync_output')}  status={b.get('status')}\n")

    # Final
    print("=== FINAL STATE beat_04 ===")
    b = c.get_one("prod_storyboard_beats", beat_id)
    for f in ["status","lipsync_status","image_override","tts_audio",
              "tts_audio_compressed","selected_option","lipsync_output","kim_feedback"]:
        print(f"  {f}: {b.get(f)}")


if __name__ == "__main__":
    main()
