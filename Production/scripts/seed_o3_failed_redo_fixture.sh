#!/usr/bin/env bash
# Seed O3-FAILED-REDO-1 hermetic state on Event_e2e_fixture (beatgen + disk).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TOOLS="$ROOT/Production/tools"
LIB="$ROOT/Production/lib"
FIXTURE="$ROOT/Production/Event_e2e_fixture"
BEAT_ID="${O3_FIXTURE_BEAT_ID:-bg_arc1_event2_pre_beat_o3fr1}"
JOB_ID="${O3_FIXTURE_JOB_ID:-o3fr1-failed-g4}"
DB="${MN_BEATGEN_DB_PATH:-$HOME/.mindfulnest/state/beatgen_evente2efixture.db}"

mkdir -p "$FIXTURE/arlo_o3_jobs" "$FIXTURE/kling_o3_clips"
G3="$FIXTURE/kling_o3_clips/${BEAT_ID}_g3_element_o3_master_delivery.mp4"
printf 'g3-fixture-bytes' >"$G3"

export BEAT_ID JOB_ID FIXTURE="$FIXTURE" DB LIB="$LIB"
python3 - <<PY
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(os.environ["LIB"]).parent))
from lib.beatgen_store import BeatgenStore

beat_id = os.environ["BEAT_ID"]
job_id = os.environ["JOB_ID"]
fixture = Path(os.environ["FIXTURE"])
g3 = fixture / "kling_o3_clips" / f"{beat_id}_g3_element_o3_master_delivery.mp4"

terminal = {
    "schema_version": 1,
    "job_id": job_id,
    "beat_id": beat_id,
    "status": "failed",
    "failure": {"message": "O3 job ended without terminal record"},
    "intent": {"generation_slot": "g4"},
}
term_path = fixture / "arlo_o3_jobs" / f"{job_id}_terminal.json"
term_path.write_text(json.dumps(terminal), encoding="utf-8")

intent = {
    "schema_version": 1,
    "job_id": job_id,
    "beat_id": beat_id,
    "generation_slot": "g4",
}
intent_path = fixture / "arlo_o3_jobs" / f"{job_id}_intent.json"
intent_path.write_text(json.dumps(intent), encoding="utf-8")

db = Path(os.environ["DB"])
store = BeatgenStore(db)
sidecar = {
    "schema_version": 3,
    "active_context": {"arc_number": 1, "event_id": "e2e_fixture", "phase": "pre"},
    "arcs": {
        "arc_1": {
            "segments": {
                "event_e2e_fixture_pre": {
                    "name": "E2E O3 failed redo",
                    "beats": [{
                        "beat_id": beat_id,
                        "speaker": "Arlo",
                        "status": "o3_element_running",
                        "kling_o3_status": "submitted",
                        "kling_o3_voice_fix_status": "o3_element_running",
                        "kling_o3_generation": 4,
                        "o3_current_job_id": job_id,
                        "kling_o3_options": [{
                            "key": "g3",
                            "video_path": str(g3),
                            "generation": 3,
                        }],
                    }],
                }
            }
        }
    },
}
store.import_from_dict(sidecar)
print(f"seeded {beat_id} job={job_id} db={db}")
PY
