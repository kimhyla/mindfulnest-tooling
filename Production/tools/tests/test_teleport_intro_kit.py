"""Unit tests for teleport_intro_kit (no API calls)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent))

import teleport_intro_kit as tik  # noqa: E402


class TeleportIntroKitTests(unittest.TestCase):
    def test_build_chipper_voice_prompt_includes_spoken(self):
        spoken = "Ready? Focus on the teleport glass."
        prompt = tik.build_chipper_voice_prompt(tik.CLIP_B_STAGING, spoken)
        self.assertIn(spoken, prompt)
        self.assertIn("warm calm conversational pace", prompt)
        self.assertIn("Only @Image1 is visible", prompt)

    def test_manifest_load_with_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {
                "version": 1,
                "clip_b_locked_line": "Ready?",
                "assets": {
                    "mirror_char": "mirror.png",
                    "studio_bg": "bg.png",
                    "neutral_char": "neutral.png",
                },
                "outputs": {
                    "clip_b_master": "out/clip_b_master.mp4",
                    "clip_b_speak": "out/speak.mp4",
                    "clip_b_glass": "out/glass.mp4",
                    "modules_dir": "out/modules",
                },
            }
            root = Path(tmp)
            (root / "mirror.png").write_bytes(b"x")
            (root / "bg.png").write_bytes(b"x")
            (root / "neutral.png").write_bytes(b"x")
            mpath = root / "manifest.json"
            mpath.write_text(json.dumps(manifest))

            old = os.environ.get("TELEPORT_INTRO_MANIFEST")
            old_drop = os.environ.get("MN_DROPBOX_ROOT")
            try:
                os.environ["TELEPORT_INTRO_MANIFEST"] = str(mpath)
                os.environ["MN_DROPBOX_ROOT"] = str(root)
                m = tik.load_manifest()
                self.assertEqual(m["clip_b_locked_line"], "Ready?")
                p = tik.resolve_asset(m, "mirror_char")
                self.assertTrue(p.is_file())
            finally:
                if old is None:
                    os.environ.pop("TELEPORT_INTRO_MANIFEST", None)
                else:
                    os.environ["TELEPORT_INTRO_MANIFEST"] = old
                if old_drop is None:
                    os.environ.pop("MN_DROPBOX_ROOT", None)
                else:
                    os.environ["MN_DROPBOX_ROOT"] = old_drop


if __name__ == "__main__":
    unittest.main()
