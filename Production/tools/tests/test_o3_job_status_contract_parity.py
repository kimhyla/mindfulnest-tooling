from pathlib import Path
from o3_job_status_contract import O3_BEAT_STATUS_PREFIXES, O3_VOICE_FIX_RUNNING_PHASES, O3_VOICE_FIX_RUNNING_STATUSES, beat_o3_voice_job_running
TOOLS = Path(__file__).resolve().parent.parent
TS = TOOLS / "storyboard-v2" / "src" / "o3JobStatusContract.ts"

def test_subprocess_is_phase_not_running_status():
    assert "subprocess" not in O3_VOICE_FIX_RUNNING_STATUSES
    assert "subprocess" in O3_VOICE_FIX_RUNNING_PHASES
    assert beat_o3_voice_job_running({"kling_o3_voice_fix_ui_job_id": "abc", "kling_o3_voice_fix_phase": "subprocess", "kling_o3_voice_fix_status": "approved", "kling_o3_status": "completed"}) is True

def test_ts_contract_contains_all_python_running_statuses():
    src = TS.read_text(encoding="utf-8")
    for status in sorted(O3_VOICE_FIX_RUNNING_STATUSES):
        assert f"'{status}'" in src
    for prefix in O3_BEAT_STATUS_PREFIXES:
        assert prefix in src
