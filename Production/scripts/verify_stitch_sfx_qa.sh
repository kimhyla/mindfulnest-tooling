#!/usr/bin/env bash
# verify_stitch_sfx_qa.sh — Stitcher SFX timeline + library preview durability gate.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EDITOR="$ROOT/Production/tools/server_handlers/stitch_editor.py"
SERVER="$ROOT/Production/tools/production_server.py"
WAVEFORM="$ROOT/Production/tools/storyboard-v2/src/components/StitcherSlotWaveform.tsx"
TIMELINE="$ROOT/Production/tools/storyboard-v2/src/components/phase/WaveformTimeline.tsx"

fail() { echo "[stitch-sfx-qa] FAIL — $*" >&2; exit 1; }

grep -q 'def hydrate_stitch_slot_video_dur_ms' "$EDITOR" || fail "missing hydrate_stitch_slot_video_dur_ms"
grep -q 'STITCH_SLOT_VIDEO_DUR_V1' "$WAVEFORM" || fail "missing STITCH_SLOT_VIDEO_DUR_V1 marker"
grep -q 'mixExtracting' "$WAVEFORM" || fail "missing mixExtracting gating in StitcherSlotWaveform"
grep -q 'mixExtracting' "$TIMELINE" || fail "missing mixExtracting gating in WaveformTimeline"
grep -q 'project_root / safe' "$SERVER" || fail "missing legacy project_root audio serve path"
grep -q 'STITCH_WAVEFORM_MIX_MONO_V1' "$EDITOR" || fail "missing mono mix cache bust marker"
grep -q 'aformat=channel_layouts=mono' "$EDITOR" || fail "missing mono normalize in stitch mix"
grep -q 'sync_stitch_slot_video_dur_ms' "$EDITOR" || fail "missing video_dur drift sync"
grep -q 'ensure_stitch_intro_default_whoosh_cue' "$EDITOR" || fail "missing intro default whoosh"
grep -q 'collect_stitch_job_slot_warnings' "$EDITOR" || fail "missing slot duration warnings"
grep -q 'STITCH_VIDEO_DUR_DRIFT_TOLERANCE_MS' "$EDITOR" || fail "missing duration drift tolerance"

python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_sfx_qa.py" -q
python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_video_dur_sync.py" -q
python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_audio_file_serve.py" -q

echo "[stitch-sfx-qa] OK — markers + pytest passed"
