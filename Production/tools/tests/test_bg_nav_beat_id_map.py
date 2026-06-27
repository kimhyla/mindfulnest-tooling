"""Category C — Event_2 resolution nav order vs beat_id (frozen map)."""
from __future__ import annotations

EVENT_2_RESOLUTION_NAV_MAP: list[tuple[int, str]] = [
    (1, "bg_arc1_event2_post_beat_01"),
    (2, "bg_arc1_event2_post_beat_02"),
    (3, "bg_arc1_event2_post_beat_07"),
    (4, "bg_arc1_event2_post_beat_03"),
    (5, "bg_arc1_event2_post_beat_04"),
    (6, "bg_arc1_event2_post_beat_05"),
    (7, "bg_arc1_event2_post_beat_06"),
]


def test_event_2_resolution_nav_map_frozen() -> None:
    """Nav Beat 4 must remain post_beat_03 — incident class guard."""
    nav4 = next(bid for nav, bid in EVENT_2_RESOLUTION_NAV_MAP if nav == 4)
    assert nav4 == "bg_arc1_event2_post_beat_03"
    assert nav4 != "bg_arc1_event2_post_beat_04"
