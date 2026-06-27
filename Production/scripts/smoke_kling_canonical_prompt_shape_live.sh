#!/usr/bin/env bash
# smoke_kling_canonical_prompt_shape_live.sh — post-deploy live proof (KLING_O3_CANONICAL_PROMPT_SHAPE_V2)
#
# Partition path: intro + resolution on the deployed event (legacy full modules).
# Milestone path: KLING_V2_LIVE_SMOKE_MILESTONE_FALLBACK_V1 — when deploy event/load
# pins event scope and intro/resolution sidecars are empty, lint milestone standalone
# beats (production Event_2 + milestone1_arc1 class).
#
# KLING_V2_LIVE_SMOKE_SKIP_STILL_INSERT_V1 — still-insert beats are not O3 motion prompts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
export MN_TOOLING_ROOT="${MN_TOOLING_ROOT:-$REPO_ROOT}"

SERVER_PORT="${MN_SERVER_PORT:-5111}"
BASE="http://localhost:${SERVER_PORT}"
EVENT_ID="${MN_BG_LIVE_SMOKE_EVENT:-Event_2}"
ROLES="${MN_BG_LIVE_SMOKE_ROLES:-intro,resolution}"
DROPBOX_PROD="${MN_DROPBOX_PRODUCTION:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production}"

fail() { echo "[kling-prompt-live-smoke] FAIL: $1" >&2; exit 1; }

curl -sf "${BASE}/api/event/current" >/dev/null 2>&1 || fail "server not reachable on :${SERVER_PORT}"

python3 <<PY
import json, os, sys, urllib.error, urllib.request
from pathlib import Path

tools = Path(os.environ["MN_TOOLING_ROOT"]) / "Production" / "tools"
prod = tools.parent
sys.path.insert(0, str(tools.resolve()))
sys.path.insert(0, str(prod.resolve()))
import beat_generator as bg  # noqa: E402

base = "${BASE}"
event_id = "${EVENT_ID}"
roles = [r.strip() for r in "${ROLES}".split(",") if r.strip()]
if not roles:
    roles = ["intro"]
dropbox_prod = Path("${DROPBOX_PROD}")
pinned_milestone = (os.environ.get("MN_BG_LIVE_SMOKE_MILESTONE") or "").strip()

def post(path, body):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

def get(path):
    with urllib.request.urlopen(base + path, timeout=120) as r:
        return json.loads(r.read().decode())

def count_o3_prompts_in_sidecar(sidecar_path: Path) -> int:
    try:
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    count = 0

    def walk(obj):
        nonlocal count
        if isinstance(obj, dict):
            if obj.get("beat_id") and str(obj.get("kling_o3_prompt") or "").strip():
                count += 1
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return count

def discover_milestone_ids() -> list[str]:
    if pinned_milestone:
        return [pinned_milestone]
    ms_root = dropbox_prod / "Milestones"
    if not ms_root.is_dir():
        return []
    ranked: list[tuple[int, str]] = []
    for entry in ms_root.iterdir():
        if not entry.is_dir():
            continue
        sidecar = entry / "beat_generator_sidecar.json"
        n = count_o3_prompts_in_sidecar(sidecar)
        if n > 0:
            ranked.append((n, entry.name))
    ranked.sort(key=lambda t: (-t[0], t[1]))
    return [mid for _, mid in ranked]

def lint_beats(beats: list, label: str) -> tuple[int, int, list]:
    checked = 0
    skipped_still = 0
    samples: list[tuple[str, str, str]] = []
    for b in beats:
        sp = (b.get("speaker") or "").strip()
        prompt = (b.get("kling_o3_prompt") or "").strip()
        if not prompt or sp in ("[Stage Direction]", "Character", ""):
            continue
        bid = b.get("beat_id") or "?"
        if bg.beat_is_still_insert(b) or bg.is_still_insert_prompt_text(prompt):
            skipped_still += 1
            continue
        if " — arc " in prompt.lower() and "beat " in prompt.lower():
            raise SystemExit(f"legacy arc/beat header on {bid} ({label}): {prompt[:100]!r}")
        if "rooted in place" in prompt.lower():
            raise SystemExit(f"rooted in place on {bid} ({label})")
        if "no locomotion" in prompt.lower():
            raise SystemExit(f"no locomotion on {bid} ({label})")
        if not prompt.startswith("@Image1 ("):
            raise SystemExit(f"missing V2 header on {bid} ({label}): {prompt[:80]!r}")
        if "Scene from @Image2" not in prompt:
            raise SystemExit(f"missing @Image2 scene ref on {bid} ({label})")
        if '"[' in prompt and "speaks in a" in prompt:
            raise SystemExit(f"emotion inside quotes on {bid} ({label}): {prompt[:120]!r}")
        checked += 1
        if len(samples) < 2:
            samples.append((bid, sp, prompt.split("\\n\\n")[0]))
    return checked, skipped_still, samples

post("/api/event/load", {"event_id": event_id})
role_phase = {"intro": "pre", "resolution": "post"}
total_checked = 0
total_skipped_still = 0
scope_label = f"{event_id} partition"
for role in roles:
    phase = role_phase.get(role, "pre")
    qs = f"scope_event_id={event_id}&scope_video_role={role}&scope_arc_number=1&scope_phase={phase}"
    state = get(f"/api/bg/session-state?{qs}")
    beats = state.get("beats") or []
    checked, skipped_still, samples = lint_beats(beats, f"{event_id}/{role}")
    if checked < 1:
        print(f"  live: {event_id}/{role} — no O3 beats to lint (partition empty)")
    else:
        print(
            f"  live: {event_id}/{role} {checked} O3 beat(s) pass V2 lint"
            + (f" ({skipped_still} still-insert skipped)" if skipped_still else "")
        )
        for bid, sp, head in samples:
            print(f"    {bid} ({sp}): {head}")
    total_checked += checked
    total_skipped_still += skipped_still

if total_checked < 1:
    # KLING_V2_LIVE_SMOKE_MILESTONE_FALLBACK_V1
    milestone_ids = discover_milestone_ids()
    if not milestone_ids:
        raise SystemExit(
            f"no O3 dialogue beats on {event_id} partitions {roles!r} and no milestone sidecars with prompts"
        )
    for mid in milestone_ids:
        post("/api/milestones/load", {"milestone_id": mid})
        qs = (
            f"scope_event_id={event_id}&scope_milestone_id={mid}"
            f"&scope_video_role=standalone&scope_target_video=standalone&scope_arc_number=1"
        )
        state = get(f"/api/bg/session-state?{qs}")
        beats = state.get("beats") or []
        checked, skipped_still, samples = lint_beats(beats, f"milestone/{mid}/standalone")
        if checked < 1:
            print(f"  live: milestone/{mid}/standalone — no O3 beats to lint")
            continue
        total_checked += checked
        total_skipped_still += skipped_still
        scope_label = f"milestone/{mid}/standalone"
        print(
            f"  live: milestone/{mid}/standalone {checked} O3 beat(s) pass V2 lint"
            + (f" ({skipped_still} still-insert skipped)" if skipped_still else "")
        )
        for bid, sp, head in samples:
            print(f"    {bid} ({sp}): {head}")
        break

if total_checked < 1 and total_skipped_still < 1:
    raise SystemExit(f"no O3 dialogue beats checked across {event_id} partitions or milestones")
print(f"  KLING_V2_LIVE_SMOKE_SKIP_STILL_INSERT_V1: skipped {total_skipped_still} still-insert beat(s)")
print(f"  KLING_V2_LIVE_SMOKE_MILESTONE_FALLBACK_V1: scope={scope_label}")
PY

echo "[kling-prompt-live-smoke] OK — ${EVENT_ID} V2 lint passed (partition and/or milestone fallback)"
