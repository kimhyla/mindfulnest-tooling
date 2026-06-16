from pathlib import Path
SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"

def test_deploy_allows_e2e_fixture_dirty_paths():
    text = (SCRIPTS / "deploy_storyboard_v59.sh").read_text(encoding="utf-8")
    assert "DEPLOY_DIRTY_IGNORE_PATTERNS" in text
    assert "Event_e2e_fixture" in text
