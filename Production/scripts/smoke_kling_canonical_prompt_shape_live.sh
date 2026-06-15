#!/usr/bin/env bash
# smoke_kling_canonical_prompt_shape_live.sh — post-deploy live proof (KLING_O3_CANONICAL_PROMPT_SHAPE_V2)
set -euo pipefail

SERVER_PORT="${MN_SERVER_PORT:-5111}"
BASE="http://localhost:${SERVER_PORT}"

fail() { echo "[kling-prompt-live-smoke] FAIL: $1" >&2; exit 1; }

curl -sf "${BASE}/api/event/current" >/dev/null 2>&1 || fail "server not reachable on :${SERVER_PORT}"

python3 <<PY
import json, urllib.error, urllib.request

base = "${BASE}"

def post(path, body):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

def get(path):
    with urllib.request.urlopen(base + path, timeout=60) as r:
        return json.loads(r.read().decode())

post("/api/event/load", {"event_id": "Event_2"})
qs = "scope_event_id=Event_2&scope_video_role=intro&scope_arc_number=1&scope_phase=pre"
state = get(f"/api/bg/session-state?{qs}")
beats = state.get("beats") or []
checked = 0
samples = []
for b in beats:
    sp = (b.get("speaker") or "").strip()
    prompt = (b.get("kling_o3_prompt") or "").strip()
    if not prompt or sp in ("[Stage Direction]", "Character", ""):
        continue
    bid = b.get("beat_id") or "?"
    if " — arc " in prompt.lower() and "beat " in prompt.lower():
        raise SystemExit(f"legacy arc/beat header on {bid}: {prompt[:100]!r}")
    if "rooted in place" in prompt.lower():
        raise SystemExit(f"rooted in place on {bid}")
    if not prompt.startswith(f"@Image1 ("):
        raise SystemExit(f"missing V2 header on {bid}: {prompt[:80]!r}")
    if "Scene from @Image2" not in prompt:
        raise SystemExit(f"missing @Image2 scene ref on {bid}")
    if '"[' in prompt and 'speaks in a' in prompt:
        raise SystemExit(f"emotion inside quotes on {bid}: {prompt[:120]!r}")
    checked += 1
    if len(samples) < 2:
        samples.append((bid, sp, prompt.split("\\n\\n")[0], prompt.split("speaks in a")[0][-40:] if "speaks in a" in prompt else ""))
if checked < 1:
    raise SystemExit("no dialogue beats with kling_o3_prompt on Event_2 after migrate heal")
print(f"  live: Event_2 {checked} beat(s) pass V2 lint")
for bid, sp, head, _ in samples:
    print(f"    {bid} ({sp}): {head}")
PY

echo "[kling-prompt-live-smoke] OK — Event_2 session-state prompts healed to V2"
