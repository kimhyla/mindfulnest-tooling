"""Lock Arlo green Path A Gate0 still trim + topology-safe idle choke."""
from __future__ import annotations

import numpy as np
from scipy.ndimage import label

from arlo_green_path_a_assets import (
    IDLE_CHOKE_BODY_PX,
    IDLE_CHOKE_TAIL_PX,
    IDLE_FROM_TRIMMED_REL,
    IDLE_PROMPT,
    KEY_RGB,
    TRIMMED_STILL_REL,
    choke_kling_idle_outline,
    composite_trimmed_rgb_on_plate,
    measure_key_rgb,
    spillkill_warm_edge_vj,
    trim_green_character_frame,
)


def test_idle_choke_constants_tail_heavier_than_body() -> None:
    assert IDLE_CHOKE_TAIL_PX > IDLE_CHOKE_BODY_PX
    assert IDLE_CHOKE_BODY_PX == 3
    assert IDLE_CHOKE_TAIL_PX == 8
    assert "openmouth" in IDLE_FROM_TRIMMED_REL
    assert "openmouth" in TRIMMED_STILL_REL
    assert "Mouth relaxed" in IDLE_PROMPT
    assert "MOUTH LOCK" not in IDLE_PROMPT


def test_spillkill_preserves_interior_bandana_teal() -> None:
    """Aggressive G-crush must not run on costume interior (Kim bandana note)."""
    h, w = 80, 120
    key = (2, 234, 8)
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = key
    frame[20:60, 30:90] = (180, 120, 70)
    # Interior teal-blue bandana (raw open-mouth was ~27,82,120)
    frame[35:50, 45:75] = (27, 82, 120)
    out, _ = spillkill_warm_edge_vj(frame, key_rgb=key)
    g = int(out[42, 60, 1])
    assert g >= 70, f"bandana G crushed to {g} — interior spillkill too aggressive"


def test_spillkill_warm_edge_vj_pins_screen_and_kills_neon_edge() -> None:
    """Synthetic: neon green fringe on fur edge → key; screen stays key."""
    h, w = 80, 120
    key = (3, 234, 8)
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = key
    frame[20:60, 30:90] = (180, 120, 70)  # fur
    # Neon baked into fur tip (fg, not near-key screen): high G, mid R
    frame[20:60, 82:88] = (100, 220, 40)
    out, used = spillkill_warm_edge_vj(frame, key_rgb=key)
    assert used == key
    assert np.allclose(out[5, 5], key, atol=1)
    # G-clamp: G := min(G, max(R,B)) → ≤100 (not raw 220)
    assert int(out[40, 85, 1]) <= 105


def test_choke_kling_idle_outline_eats_dark_tail_ring() -> None:
    h, w = 120, 200
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = KEY_RGB
    frame[20:100, 40:160] = (180, 120, 70)
    frame[20:100, 157:163] = (20, 20, 20)
    out = choke_kling_idle_outline(frame, body_px=2, tail_px=5, tail_x_frac=0.5)
    right = out[40:80, 157:163]
    lum = right.mean(axis=2)
    assert (lum < 40).sum() == 0, f"dark trim remains: {right.reshape(-1, 3)[:8]}"
    assert np.allclose(out[50, 161], KEY_RGB, atol=1)


def test_choke_eats_dark_green_kling_stroke_not_vest() -> None:
    h, w = 100, 160
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = KEY_RGB
    frame[20:80, 30:120] = (180, 120, 70)
    frame[35:70, 45:75] = (40, 90, 45)
    frame[20:80, 118:122] = (27, 153, 4)
    out = choke_kling_idle_outline(frame, body_px=2, tail_px=5, tail_x_frac=0.5)
    assert np.allclose(out[50, 120], KEY_RGB, atol=2)
    vest = out[50, 55]
    assert vest[1] > vest[0], f"vest destroyed: {vest}"
    assert not np.allclose(vest, KEY_RGB, atol=5)


def test_choke_preserves_body_tail_bridge() -> None:
    h, w = 120, 200
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = KEY_RGB
    frame[30:90, 40:100] = (180, 120, 70)
    frame[40:70, 100:112] = (180, 120, 70)
    frame[25:95, 112:170] = (180, 120, 70)
    frame[25:95, 166:170] = (27, 153, 4)
    out = choke_kling_idle_outline(frame, body_px=2, tail_px=6, tail_x_frac=0.5)
    key = np.array(KEY_RGB, dtype=np.float32)
    fg = np.linalg.norm(out.astype(np.float32) - key, axis=2) > 50
    _lab, n = label(fg)
    sizes = sorted(int((_lab == i).sum()) for i in range(1, n + 1))
    assert sizes[-1] > 5000, f"character eaten/split: components={n} sizes={sizes[-3:]}"
    assert np.allclose(out[50, 168], KEY_RGB, atol=2)


def test_trim_green_character_frame_then_plate_kills_neon_edge() -> None:
    """Idle/video frames must use Gate0 stack — not ffmpeg chromakey alone."""
    h, w = 80, 120
    key = (3, 234, 8)
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = key
    frame[20:60, 30:90] = (180, 120, 70)
    frame[20:60, 82:88] = (40, 220, 20)  # neon fringe
    plate = np.full((h, w, 3), 40, dtype=np.uint8)
    trimmed, used = trim_green_character_frame(frame, apply_idle_choke=True)
    assert used == key
    comp = composite_trimmed_rgb_on_plate(trimmed, plate)
    # Fringe band should not remain neon on plate composite
    edge = comp[20:60, 82:88]
    assert int((edge[:, :, 1].astype(int) - edge[:, :, 0].astype(int)).max()) <= 25


def test_assert_send_assets_doc_contract() -> None:
    import arlo_green_path_a_assets as m

    src = open(m.__file__, encoding="utf-8").read()
    assert "def spillkill_warm_edge_vj" in src
    assert "def trim_green_character_frame" in src
    assert "def composite_trimmed_rgb_on_plate" in src
    assert "openmouth" in m.TRIMMED_STILL_REL
    assert "inner_scrub" in src or "COMPOSITE_INNER_SCRUB" in src
    assert "def choke_kling_idle_outline" in src
    assert measure_key_rgb(np.zeros((40, 40, 3), dtype=np.uint8) + np.array(KEY_RGB)) == KEY_RGB
