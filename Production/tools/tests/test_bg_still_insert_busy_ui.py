"""Still+TTS beats must not inherit O3 job-busy UI or client latch bleed."""
from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
BGTAB = TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
NAV = TOOLS / "storyboard-v2" / "src" / "utils" / "bgBeatNavStatus.ts"
BACKGROUND = TOOLS / "server_handlers" / "background.py"


def test_still_insert_nav_busy_ignores_o3_submit_pending() -> None:
    nav = NAV.read_text(encoding="utf-8")
    block = nav.split("export function beatHasActiveNavJob", 1)[1].split("\nexport ", 1)[0]
    assert "isStillInsertNavBeat(beat)" in block
    assert "activeStillRenderJobs[id]" in block
    assert block.index("isStillInsertNavBeat") < block.index("beatO3JobBusy")


def test_still_insert_generate_skips_o3_submit_pending_latch() -> None:
    src = BGTAB.read_text(encoding="utf-8")
    gen = src.split("const onGenerateBatch = async", 1)[1].split("\n  const handleO3SubmitResult", 1)[0]
    assert "if (isStillInsertBeat(beat))" in gen
    still_branch = gen.split("if (isStillInsertBeat(beat))", 1)[1].split("return;", 1)[0]
    assert "onRenderStillClip" in still_branch
    assert "setO3SubmitPending" not in still_branch
    assert gen.index("onRenderStillClip") < gen.index("setO3SubmitPending")


def test_still_render_client_latch_has_finally_and_clears_o3_audit() -> None:
    src = BGTAB.read_text(encoding="utf-8")
    fn = src.split("const onRenderStillClip = async", 1)[1].split("\n  const handleO3SubmitResult", 1)[0]
    assert "try {" in fn
    assert "} finally {" in fn
    assert "setActiveStillRenderJobs" in fn.split("} finally {", 1)[1]
    assert "setO3SubmitAuditByBeat" in fn
    assert "delete next[beatId]" in fn


def test_refresh_state_prunes_still_render_and_o3_audit_for_still_insert() -> None:
    src = BGTAB.read_text(encoding="utf-8")
    block = src.split("const refreshState = async", 1)[1].split("\n  useEffect(() => {", 1)[0]
    assert "pruneActiveStillRenderJobs" in block
    assert "setO3SubmitAuditByBeat" in block
    assert "isStillInsertNavBeat(beat)" in block


def test_beat_gen_card_hides_o3_audit_for_still_insert() -> None:
    src = BGTAB.read_text(encoding="utf-8")
    assert "busy && !stillInsert && (o3SubmitAudit || o3IntentSnapshot)" in src
    assert "Building still clip (+ TTS)" in src


def test_still_clip_response_beat_snapshot_job_busy_false() -> None:
    src = BACKGROUND.read_text(encoding="utf-8")
    fn = src.split("def handle_bg_render_still_clip", 1)[1].split("\ndef handle_bg_accept_option", 1)[0]
    assert 'snap["job_busy"] = False' in fn
    assert "STILL_RENDER_IN_PROGRESS" in fn
    assert "if beat_id in _STILL_RENDER_BUSY" in fn
    assert fn.index("if beat_id in _STILL_RENDER_BUSY") < fn.index("_STILL_RENDER_BUSY.add")


def test_shared_session_job_busy_includes_still_render_set() -> None:
    src = BACKGROUND.read_text(encoding="utf-8")
    assert "def _resolve_beat_job_busy_for_session" in src
    helper = src.split("def _resolve_beat_job_busy_for_session", 1)[1].split("\ndef ", 1)[0]
    assert "beat_is_still_insert" in helper
    assert "_STILL_RENDER_BUSY" in helper
    enrich = src.split("def _enrich_beats_job_busy", 1)[1].split("\ndef ", 1)[0]
    assert "_resolve_beat_job_busy_for_session" in enrich


def test_o3_poll_snapshot_clears_stale_pointer_before_job_busy() -> None:
    src = BACKGROUND.read_text(encoding="utf-8")
    fn = src.split("def _enriched_beat_snapshot_for_o3_poll", 1)[1].split("\ndef ", 1)[0]
    assert "clear_o3_pointer_if_terminal" in fn
    assert "_resolve_beat_job_busy_for_session" in fn


def test_apply_o3_gallery_poll_ignores_o3_job_fields_on_still_insert() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "state" / "promptEditRegistry.ts").read_text(encoding="utf-8")
    fn = src.split("export function applyO3GalleryFieldsFromPoll", 1)[1].split("\nexport ", 1)[0]
    assert "stillInsert" in fn
    assert "delete gallery.job_busy" in fn
    assert "delete gallery.o3_current_job_id" in fn
    assert "'kling_o3_still_stitch_approved'" in fn
    assert "'kling_o3_still_stitch_approved_at'" in fn


def test_nav_module_purges_o3_client_latches_for_still_insert() -> None:
    nav = NAV.read_text(encoding="utf-8")
    assert "export function purgeO3ClientJobStateForStillInsertBeats" in nav
    assert "export function purgeO3ClientJobStateForBeatIds" in nav
    assert "export function stillInsertBeatIdsFromBeats" in nav


def test_refresh_state_reconciles_gpt_batch_job_from_server_not_sticky() -> None:
    src = BGTAB.read_text(encoding="utf-8")
    block = src.split("const refreshState = async", 1)[1].split("\n  useEffect(() => {", 1)[0]
    assert "collectActiveGptBatchJobFromBeats(nextBeats)" in block
    assert "setActiveJobId(nextGptJob)" in block
    assert "prev ?? collectActiveStillJobFromBeats" not in block
    assert "stillInsertBeatIdsFromBeats(nextBeats)" in block
    assert "pruneGptBatchSubmitPending" in block


def test_pipeline_switch_to_still_insert_purges_o3_client_latches() -> None:
    src = BGTAB.read_text(encoding="utf-8")
    fn = src.split("const onSetBeatGenerationMode = async", 1)[1].split("\n  const onAlignElementRef", 1)[0]
    assert "if (mode === 'still_insert')" in fn
    assert "purgeO3ClientLatchesForBeatIds([beatId])" in fn


def test_gpt_batch_submit_uses_pending_latch_with_finally() -> None:
    src = BGTAB.read_text(encoding="utf-8")
    gen = src.split("const onGenerateBatch = async", 1)[1].split("\n  const onSubmitNativeLipSyncExperiment", 1)[0]
    gpt = gen.split("setGptBatchSubmitPending", 1)[1]
    assert "try {" in gpt
    assert "} finally {" in gpt
    assert "delete next[beatId]" in gpt.split("setGptBatchSubmitPending", 1)[1]


def test_beat_nav_context_includes_gpt_batch_submit_pending() -> None:
    src = BGTAB.read_text(encoding="utf-8")
    assert "gptBatchSubmitPending" in src
    nav = NAV.read_text(encoding="utf-8")
    still_block = nav.split("export function beatHasActiveNavJob", 1)[1].split("\nexport ", 1)[0]
    assert "gptBatchSubmitPending" in still_block
