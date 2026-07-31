"""Lock Arlo green Path A Send assets + topology-safe Kling idle outline choke."""
from __future__ import annotations

import numpy as np
from scipy.ndimage import label

from arlo_green_path_a_assets import (
    IDLE_CHOKE_BODY_PX,
    IDLE_CHOKE_TAIL_PX,
    IDLE_FROM_TRIMMED_REL,
    KEY_RGB,
    TRIMMED_STILL_REL,
    choke_kling_idle_outline,
)


def test_idle_choke_constants_tail_heavier_than_body() -> None:
    assert IDLE_CHOKE_TAIL_PX > IDLE_CHOKE_BODY_PX
    assert IDLE_CHOKE_BODY_PX == 3
    assert IDLE_CHOKE_TAIL_PX == 8
    assert "choke_tail6_v4" in IDLE_FROM_TRIMMED_REL
    assert "trimmed" in TRIMMED_STILL_REL
    assert KEY_RGB == (3, 241, 5)


def test_choke_kling_idle_outline_eats_dark_tail_ring() -> None:
    """Synthetic: dark outline on right (tail) must become key green."""
    h, w = 120, 200
    key = np.array(KEY_RGB, dtype=np.uint8)
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = key
    # Character blob with black outline on the right side
    frame[20:100, 40:160] = (180, 120, 70)  # fur
    frame[20:100, 157:163] = (20, 20, 20)  # dark trim on right edge
    out = choke_kling_idle_outline(frame, body_px=2, tail_px=5, tail_x_frac=0.5)
    right = out[40:80, 157:163]
    lum = right.mean(axis=2)
    assert (lum < 40).sum() == 0, f"dark trim remains: {right.reshape(-1, 3)[:8]}"
    assert np.allclose(out[50, 161], KEY_RGB, atol=1)


def test_choke_eats_dark_green_kling_stroke_not_vest() -> None:
    """Dark-green key stroke on outer edge → key; olive vest interior stays."""
    h, w = 100, 160
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = KEY_RGB
    frame[20:80, 30:120] = (180, 120, 70)  # fur
    frame[35:70, 45:75] = (40, 90, 45)  # olive vest (costume green)
    # Kling dark-green stroke on right outer edge
    frame[20:80, 118:122] = (27, 153, 4)
    out = choke_kling_idle_outline(frame, body_px=2, tail_px=5, tail_x_frac=0.5)
    # Outer stroke columns should be key
    assert np.allclose(out[50, 120], KEY_RGB, atol=2)
    # Vest interior must survive (not keyed out)
    vest = out[50, 55]
    assert vest[1] > vest[0], f"vest destroyed: {vest}"
    assert not np.allclose(vest, KEY_RGB, atol=5)


def test_choke_preserves_body_tail_bridge() -> None:
    """Rectangular right-half erode used to sever body↔tail; outer-face must not."""
    h, w = 120, 200
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = KEY_RGB
    # Body (left) + bushy tail (right) joined by a thin bridge
    frame[30:90, 40:100] = (180, 120, 70)  # body
    frame[40:70, 100:112] = (180, 120, 70)  # bridge ~12px
    frame[25:95, 112:170] = (180, 120, 70)  # tail
    # dark-green trim on outer tail
    frame[25:95, 166:170] = (27, 153, 4)
    out = choke_kling_idle_outline(frame, body_px=2, tail_px=6, tail_x_frac=0.5)
    key = np.array(KEY_RGB, dtype=np.float32)
    fg = np.linalg.norm(out.astype(np.float32) - key, axis=2) > 50
    _lab, n = label(fg)
    sizes = sorted(int((_lab == i).sum()) for i in range(1, n + 1))
    assert sizes[-1] > 5000, f"character eaten/split: components={n} sizes={sizes[-3:]}"
    # Outer trim gone
    assert np.allclose(out[50, 168], KEY_RGB, atol=2)


def test_assert_send_assets_doc_contract() -> None:
    """Source contract: refuse raw still name; require choke_tail6_v4 idle name."""
    import arlo_green_path_a_assets as m

    src = open(m.__file__, encoding="utf-8").read()
    assert 'still.name == "arlo still green background.png"' in src
    assert "choke_tail6_v4" in src
    assert "def choke_kling_idle_outline" in src
    assert "def assert_send_assets" in src
    assert "right_face" in src
    assert "for i in range(tail_px)" in src or "Iteratively peels" in src
