#!/usr/bin/env bash
# smoke_kling_canonical_prompt_shape_live.sh — post-deploy live proof (KLING_O3_CANONICAL_PROMPT_SHAPE_V2)
# Checks Event_2 intro + resolution (MN_BG_LIVE_SMOKE_ROLES override: comma-separated roles).
set -euo pipefail

SERVER_PORT="${MN_SERVER_PORT:-5111}"
BASE="http://localhost:${SERVER_PORT}"
EVENT_ID="${MN_BG_LIVE_SMOKE_EVENT:-Event_2}"
ROLES="${MN_BG_LIVE_SMOKE_ROLES:-intro,resolution}"

fail() { echo "[kling-prompt-live-smoke] FAIL: $1" >&2; exit 1; }

curl -sf "${BASE}/api/event/current" >/dev/null 2>&1 || fail "server not reachable on :${SERVER_PORT}"

python3 <<PY
import json, os, urllib.error, urllib.request

base = "${BASE}"
event_id = "${EVENT_ID}"
roles = [r.strip() for r in "${ROLES}".split(",") if r.strip()]
if not roles:
    roles = ["intro"]

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

post("/api/event/load", {"event_id": event_id})
role_phase = {"intro": "pre", "resolution": "post"}
total_checked = 0
for role in roles:
    phase = role_phase.get(role, "pre")
    qs = f"scope_event_id={event_id}&scope_video_role={role}&scope_arc_number=1&scope_phase={phase}"
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
            raise SystemExit(f"legacy arc/beat header on {bid} ({role}): {prompt[:100]!r}")
        if "rooted in place" in prompt.lower():
            raise SystemExit(f"rooted in place on {bid} ({role})")
        if "no locomotion" in prompt.lower():
            raise SystemExit(f"no locomotion on {bid} ({role})")
        if not prompt.startswith("@Image1 ("):
            raise SystemExit(f"missing V2 header on {bid} ({role}): {prompt[:80]!r}")
        if "Scene from @Image2" not in prompt:
            raise SystemExit(f"missing @Image2 scene ref on {bid} ({role})")
        if '"[' in prompt and "speaks in a" in prompt:
            raise SystemExit(f"emotion inside quotes on {bid} ({role}): {prompt[:120]!r}")
        checked += 1
        if len(samples) < 2:
            samples.append((bid, sp, prompt.split("\\n\\n")[0]))
    if checked < 1 and role in ("intro", "resolution"):
        raise SystemExit(f"no dialogue beats with kling_o3_prompt on {event_id}/{role} after migrate heal")
    total_checked += checked
    print(f"  live: {event_id}/{role} {checked} beat(s) pass V2 lint")
    for bid, sp, head in samples:
        print(f"    {bid} ({sp}): {head}")
if total_checked < 1:
    raise SystemExit(f"no dialogue beats checked across roles {roles!r}")
PY

echo "[kling-prompt-live-smoke] OK — ${EVENT_ID} roles (${ROLES}) pass V2 lint"
