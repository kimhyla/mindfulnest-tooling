"""Contract tests for BG beat jump-nav status badges (read-only indicators)."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BG_TAB = REPO_ROOT / "tools" / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
NAV_STATUS = REPO_ROOT / "tools" / "storyboard-v2" / "src" / "utils" / "bgBeatNavStatus.ts"
APP_CSS = REPO_ROOT / "tools" / "storyboard-v2" / "src" / "app.css"


def test_nav_status_helpers_are_pure_readonly_module() -> None:
    src = NAV_STATUS.read_text(encoding="utf-8")
    assert "export function beatHasActiveNavJob" in src
    assert "export function beatIsStitchApproved" in src
    assert "export function computeBeatNavItemStatuses" in src
    assert "beatHasActiveStillBatchJob" in src
    # Nav badges must not call APIs or mutate state.
    assert "pathappPatch" not in src
    assert "apiGet" not in src
    assert "setActive" not in src


def test_bgtab_wires_nav_status_without_side_effects() -> None:
    src = BG_TAB.read_text(encoding="utf-8")
    assert "computeBeatNavItemStatuses" in src
    assert "itemStatuses={beatNavItemStatuses}" in src
    assert "bg-beat-nav-dot" in src
    assert "bg-beat-nav-check" in src
    assert "beatHasActiveNavJob(b, beatNavJobContext)" in src
    # Old global still-job bleed removed from card busy.
    assert "activeJobId !== null\n                ||" not in src


def test_nav_badge_css_present() -> None:
    css = APP_CSS.read_text(encoding="utf-8")
    assert ".mn-bg-beat-nav-dot" in css
    assert ".mn-bg-beat-nav-check" in css
    assert "prefers-reduced-motion" in css
