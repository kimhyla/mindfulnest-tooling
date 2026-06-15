#!/usr/bin/env bash
# verify_kling_canonical_prompt_shape_durability.sh — KLING_O3_CANONICAL_PROMPT_SHAPE_V2
#
# All Element-bound dialogue beats (Tessa, Lorelai/Laurel, Arlo, Chipper, future cast):
#   @Image1 ({Speaker}). Scene from @Image2.
#   {screen direction}
#   {Name} speaks in a {delivery}: [emotion] "dialogue"
#   style + footer locks
# No arc/event/beat labels, no "rooted in place", emotion OUTSIDE quotes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TOOLS="${REPO_ROOT}/Production/tools"
POLICY="${TOOLS}/beat_extract_policy.py"
PROMPT="${TOOLS}/kling_o3_prompt.py"
BG="${TOOLS}/beat_generator.py"
AUTHOR_SKILL="${REPO_ROOT}/Production/.claude/skills/beat-kling-prompt-author/SKILL.md"
SERVER_PORT="${MN_SERVER_PORT:-5111}"

fail() { echo "[kling-canonical-prompt-shape] FAIL: $1" >&2; exit 1; }

[[ -f "$POLICY" ]] || fail "missing beat_extract_policy.py"
[[ -f "$PROMPT" ]] || fail "missing kling_o3_prompt.py"
[[ -f "$BG" ]] || fail "missing beat_generator.py"
[[ -f "$AUTHOR_SKILL" ]] || fail "missing beat-kling-prompt-author SKILL.md"

grep -q 'KLING_O3_CANONICAL_PROMPT_SHAPE_V2' "$PROMPT" \
  || fail "kling_o3_prompt.py missing KLING_O3_CANONICAL_PROMPT_SHAPE_V2"
grep -q 'KLING_O3_CANONICAL_PROMPT_SHAPE_V2' "$BG" \
  || fail "beat_generator.py missing KLING_O3_CANONICAL_PROMPT_SHAPE_V2 marker"
grep -q 'screen_direction_paragraph' "$POLICY" \
  || fail "beat_extract_policy.py missing screen_direction_paragraph"
grep -q 'strip_rooted_in_place' "$PROMPT" \
  || fail "kling_o3_prompt.py missing strip_rooted_in_place"
grep -q 'KLING O3 CANONICAL PROMPT SHAPE V2' "$POLICY" \
  || fail "kling_staging_policy_block missing V2 law"
grep -q 'Emotion OUTSIDE quotes' "$AUTHOR_SKILL" \
  || fail "author SKILL missing emotion-outside-quotes rule"

cd "$TOOLS"
python3 -m pytest \
  tests/test_kling_author_enrichment.py::test_canonical_prompt_shape_v2_tessa \
  tests/test_kling_author_enrichment.py::test_canonical_prompt_shape_v2_all_element_speakers \
  tests/test_element_voice_alignment.py \
  tests/test_kling_o3_duration_extraction.py \
  -q

python3 <<PY
import sys
from pathlib import Path

sys.path.insert(0, str(Path("${TOOLS}").resolve()))
sys.path.insert(0, str(Path("${REPO_ROOT}/Production").resolve()))
import beat_generator as bg

CASES = [
    ("Tessa", "Tessa", "curious", "stands near the MindfulNest", "Oh, hello."),
    ("Lorelai", "Laurel", "awe, breathless", "holds her rolled map up", "Oh my goodness!"),
    ("Arlo", "Arlo", "warm, to camera", "faces the camera with a gentle nod", "Ready, Kiddo?"),
]

def check(speaker, header_label, emotion, scene, dialogue):
    beat = {
        "speaker": speaker,
        "dialogue_text": dialogue,
        "emotion": emotion,
        "scene_notes": scene,
        "kling_o3_prompt": (
            f"@Image1 ({speaker}) {speaker} — arc 99 event 9 pre, beat 01. Scene from @Image2.\\n\\n"
            f'{speaker} speaks: "[{emotion}] {dialogue}"'
        ),
    }
    out = bg.normalize_o3_element_bound_prompt(beat, beat["kling_o3_prompt"])
    assert out.startswith(f"@Image1 ({header_label}). Scene from @Image2."), (speaker, out[:120])
    assert "arc 99" not in out.lower(), speaker
    assert "rooted in place" not in out.lower(), speaker
    assert scene.split(",")[0].strip().lower() in out.lower(), (speaker, scene, out)
    assert f'[{emotion}] "' in out or f"[{emotion}] \"" in out, (speaker, out)
    assert f'"[{emotion}]' not in out, (speaker, out)

for args in CASES:
    check(*args)
print("  offline: Tessa + Lorelai + Arlo normalize_o3_element_bound_prompt OK")
PY

if curl -sf "http://localhost:${SERVER_PORT}/api/event/current" >/dev/null 2>&1; then
  python3 <<PY
import json, urllib.request

base = "http://localhost:${SERVER_PORT}"

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
qs = (
    "scope_event_id=Event_2&scope_video_role=intro"
    "&scope_arc_number=1&scope_phase=pre"
)
state = get(f"/api/bg/session-state?{qs}")
beats = state.get("beats") or []
checked = 0
for b in beats:
    sp = (b.get("speaker") or "").strip()
    prompt = (b.get("kling_o3_prompt") or "").strip()
    if not prompt or sp in ("[Stage Direction]", "Character", ""):
        continue
    if "arc 1 event" in prompt.lower() and "beat " in prompt.lower():
        raise SystemExit(f"legacy arc/beat header on {b.get('beat_id')}: {prompt[:80]!r}")
    if "rooted in place" in prompt.lower():
        raise SystemExit(f"rooted in place on {b.get('beat_id')}")
    if prompt.count("@Image1") >= 1 and "Scene from @Image2" in prompt:
        checked += 1
if checked < 1:
    raise SystemExit("no dialogue beats with kling_o3_prompt on Event_2 session-state")
print(f"  live API: Event_2 session-state {checked} dialogue beat prompt(s) pass shape lint")
PY
  echo "[kling-canonical-prompt-shape] OK — source guards + pytest + offline/live smoke passed"
else
  echo "[kling-canonical-prompt-shape] OK — source guards + pytest + offline smoke (server down)"
fi
