"""Milestone Send-to-Stitcher export jobs live under Milestones/<id>/, not Event_N/."""

from __future__ import annotations

from pathlib import Path

from bg_export_stitcher_job_store import (
    create_job,
    export_job_store_roots,
    find_export_job,
    job_poll_payload,
    new_job_id,
)


def test_find_export_job_in_milestone_root_not_event_dir(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_2"
    milestone_dir = tmp_path / "Milestones" / "milestone1_arc1"
    event_dir.mkdir(parents=True)
    milestone_dir.mkdir(parents=True)

    job_id = new_job_id()
    create_job(
        milestone_dir,
        job_id=job_id,
        scope_key="1|3b|full|standalone",
        scope_event_id="milestone1_arc1",
        arc_number=1,
        bg_event_id="3b",
        phase="full",
        slot_key="standalone",
        beat_ids=["bg_arc1_event3b_full_beat_01"],
        pin={"pinned_generation": 1, "pinned_event_dir": str(event_dir), "pinned_video_role": "standalone"},
    )

    roots = export_job_store_roots(event_dir, app_milestone_dir=None)
    found = find_export_job(roots, job_id)
    assert found is not None
    store_dir, job = found
    assert store_dir.resolve() == milestone_dir.resolve()
    payload = job_poll_payload(job)
    assert payload["job_id"] == job_id
    assert payload["slot_key"] == "standalone"
    assert job.get("job_store_dir") == str(milestone_dir.resolve())
