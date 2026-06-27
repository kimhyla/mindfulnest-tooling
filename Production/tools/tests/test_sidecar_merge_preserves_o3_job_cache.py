"""Category I — SIDECAR_MERGE_PRESERVE_FIELDS includes O3 job cache."""
from __future__ import annotations

import beat_generator as bg
from o3_job_status_contract import O3_JOB_CACHE_FIELDS


def test_sidecar_merge_preserves_all_o3_job_cache_fields() -> None:
    missing = [f for f in O3_JOB_CACHE_FIELDS if f not in bg.SIDECAR_MERGE_PRESERVE_FIELDS]
    assert missing == [], f"missing from SIDECAR_MERGE_PRESERVE_FIELDS: {missing}"


def test_sidecar_merge_preserve_prefix_union() -> None:
    existing = {
        "beat_id": "bg_arc1_event2_pre_beat_01",
        "kling_o3_prompt": "keep",
        "o3_future_field": "future",
        "dialogue_text": "hi",
    }
    incoming = [{"beat_id": "bg_arc1_event2_pre_beat_01", "dialogue_text": "new"}]
    merged = bg.merge_incoming_segment_beats([existing], incoming)
    assert merged[0]["o3_future_field"] == "future"
    assert merged[0]["kling_o3_prompt"] == "keep"
    assert merged[0]["dialogue_text"] == "new"
