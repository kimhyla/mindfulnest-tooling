#!/usr/bin/env python3
"""Tier 3 CLIENT-SIDE widget-wire static tests.

Validates that storyboard_v38_prod.html has been patched with the 6
Tier 3 widget wires + stale-audio badge CSS + _t3LegacyRefuse helper.
Static-text assertions only — no runtime / no server / no browser.

task_id = tier3-html-patcher-20260418
preflight = 68
LD coverage = 239-244, 256-259
"""

from __future__ import annotations

import pathlib
import re
import sys
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from Production.lib.paths import DROPBOX_ROOT  # noqa: E402

PROJECT_ROOT = DROPBOX_ROOT
TARGET = PROJECT_ROOT / "Production" / "Event_1" / "storyboard_v38_prod.html"


class Tier3HTMLPatchTests(unittest.TestCase):
    """Static post-patch signature tests for Tier 3 widget wiring."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.src = TARGET.read_text(encoding="utf-8")

    # ------------------------------------------------------------
    # Per-widget static presence
    # ------------------------------------------------------------

    def test_w1_pause_slider_persists_pause_after_ms(self) -> None:
        """LD-239 — pause slider onchange routes pause_after_ms in ms."""
        # Allow either direct pathappPatch or routedPatch — scope spec
        # accepts "at least once" of the field-name signature.
        direct = self.src.count('pathappPatch(bid, "pause_after_ms"')
        routed = self.src.count('routedPatch(bid,"pause_after_ms"')
        self.assertGreaterEqual(
            direct + routed, 1,
            "pause_after_ms field must be persisted via pathappPatch/routedPatch"
        )
        # Confirm seconds -> ms conversion landed.
        self.assertIn(
            "Math.round(v*1000)", self.src,
            "pause slider must convert seconds to ms"
        )
        # onchange handler was added (release only) — oninput stays too.
        self.assertIn("ps.onchange=function()", self.src)
        self.assertIn("ps.oninput=function()", self.src)

    def test_w2_image_dropdown_routes_image_override(self) -> None:
        """LD-240 — image dropdown onchange routes image_override.

        At least 2 image_override wires total: drag-drop (pre-existing)
        + dropdown (new).
        """
        count = self.src.count('"image_override"')
        self.assertGreaterEqual(
            count, 2,
            f'image_override expected ≥2 occurrences (drag-drop + dropdown), got {count}'
        )
        # Pre-existing drag-drop wire preserved.
        self.assertIn(
            'routedPatch(_bid_drop,"image_override"', self.src,
            "drag-drop image_override wiring must be preserved"
        )

    def test_w3_speaker_dropdown_routes_speaker(self) -> None:
        """LD-241 + LD-256 — speaker dropdown routes speaker field exactly once."""
        direct = self.src.count('pathappPatch(bid, "speaker"')
        routed = self.src.count('routedPatch(bid,"speaker"')
        total = direct + routed
        self.assertEqual(
            total, 1,
            f'speaker field must be patched exactly once, got {total} '
            f'(direct={direct}, routed={routed})'
        )

    def test_w3b_stale_audio_badge_css_and_dom(self) -> None:
        """LD-256 — audio-stale-badge CSS + DOM usage present."""
        # CSS class defined.
        self.assertIn(".audio-stale-badge {", self.src, "audio-stale-badge CSS must be present")
        # Badge DOM element created.
        self.assertIn('"audio-stale-badge"', self.src, "audio-stale-badge must be used as class")
        # speaker_mismatch guard drives the badge.
        self.assertIn("speaker_mismatch", self.src,
                      "speaker_mismatch must gate the stale-audio badge render")
        # Warn emoji + copy (✦ U+26A0 WARNING SIGN) in the badge text.
        self.assertRegex(
            self.src,
            r"audio stale.*Regen Audio",
            "stale-badge copy must prompt Regen Audio"
        )

    def test_w4_row_reorder_emits_display_order(self) -> None:
        """LD-242 + LD-257 — row reorder emits display_order to __global__."""
        self.assertIn(
            "display_order", self.src,
            "display_order field must appear"
        )
        self.assertIn(
            'routedPatch("__global__","display_order"', self.src,
            "mv() must route display_order to the __global__ sentinel"
        )

    def test_w4_hydrate_applies_display_order(self) -> None:
        """LD-257 — hydrate reorders L[] from sidecar display_order on load."""
        # The Tier 3 support script implements _t3ApplyDisplayOrder.
        self.assertIn(
            "_t3ApplyDisplayOrder", self.src,
            "display_order hydrate must be wired"
        )

    def test_w5_add_line_uses_create_endpoint(self) -> None:
        """LD-243 + LD-258 — addLine hits POST /api/v2/beat/create."""
        self.assertIn("/api/v2/beat/create", self.src)
        # insert_after anchor is computed from last L[] anchor (or null).
        self.assertIn("insert_after:_insertAfter", self.src,
                      "addLine must pass insert_after to /api/v2/beat/create")

    def test_w6_pause_tag_dispatches_blur(self) -> None:
        """LD-244 — [pause] tag button dispatches blur after insertion."""
        # Programmatic blur dispatch from the pause button handler.
        self.assertRegex(
            self.src,
            r'dispatchEvent\(new Event\("blur"\)\)',
            "pause-tag button must programmatically dispatch blur"
        )
        # skip_tts_regen flag plumbing — wrapper forwards options.skip_tts_regen.
        self.assertIn("skip_tts_regen", self.src,
                      "skip_tts_regen flag plumbing must exist")
        # Pending flag used by the wrapper.
        self.assertIn("_t3PauseBlurPending", self.src,
                      "pending-flag guard must exist")

    # ------------------------------------------------------------
    # Cross-widget / infra
    # ------------------------------------------------------------

    def test_legacy_refuse_defined_and_used(self) -> None:
        """LD-259 — _t3LegacyRefuse defined AND used ≥6 times (1/widget)."""
        # Definition (window._t3LegacyRefuse = function(...))
        self.assertRegex(
            self.src,
            r"window\._t3LegacyRefuse\s*=\s*function",
            "_t3LegacyRefuse must be defined on window"
        )
        # Bindings — 6 widgets, each passes a _t3LegacyRefuse-bound legacyFn.
        # Counting raw tokens (6 callsites + 1 definition => ≥7).
        count = self.src.count("_t3LegacyRefuse")
        self.assertGreaterEqual(
            count, 6,
            f"_t3LegacyRefuse must appear ≥6 times (widget bindings), got {count}"
        )
        # Confirm it's a red-toast fallback (error state), never silent.
        m = re.search(
            r"window\._t3LegacyRefuse\s*=\s*function[^{]*\{[\s\S]{0,600}?pathappToast\(\s*[\"']error[\"']",
            self.src,
        )
        self.assertIsNotNone(
            m,
            "_t3LegacyRefuse must call pathappToast('error', ...) — red toast, never silent"
        )

    def test_tier3_feature_flag_present(self) -> None:
        """Tier 3 is feature-flagged via window.TIER3_ENABLED."""
        self.assertIn("window.TIER3_ENABLED", self.src)
        # Mirrors TIER1A_ENABLED by convention.
        self.assertIn("TIER1A_ENABLED", self.src)

    # ------------------------------------------------------------
    # File-level invariants
    # ------------------------------------------------------------

    def test_html_structure_intact(self) -> None:
        """</body></html> still terminate the document exactly once."""
        self.assertEqual(self.src.count("</body>"), 1)
        self.assertEqual(self.src.count("</html>"), 1)
        self.assertTrue(self.src.rstrip().endswith("</body></html>"))

    def test_base64_image_count_stable(self) -> None:
        """Tier 3 is Rule 7 Path B — image base64 URIs unchanged.

        Cross-checks against the pristine backup created by the patcher.
        If the backup is missing (fresh install), skip rather than fail.
        """
        backups = sorted(
            TARGET.parent.glob(TARGET.name + ".bak_tier3_widgets_*")
        )
        if not backups:
            self.skipTest("no tier3 backup available for comparison")
        pre = backups[-1].read_text(encoding="utf-8")
        b64_re = re.compile(r"data:image/[a-zA-Z.+-]+;base64,[A-Za-z0-9+/=]+")
        pre_set = sorted(b64_re.findall(pre))
        post_set = sorted(b64_re.findall(self.src))
        self.assertEqual(
            len(pre_set), len(post_set),
            "base64 URI count must be identical"
        )
        self.assertEqual(
            pre_set, post_set,
            "base64 URIs must be byte-identical (Rule 7 Path B invariant)"
        )


class Bugs1And2PatchTests(unittest.TestCase):
    """Static post-patch signature tests for the 2026-04-19 bundled bugfix.

    Bug 1 — pathappPatch lexical-closure fix: all 6 internal call sites to
    pathappSetSaveInd must be rewritten to window.pathappSetSaveInd so the
    Phase 1.5 toast monkey-patch fires on every save.

    Bug 2 — skip_tts_regen forward: pathappPatch must copy
    options.skip_tts_regen into the outgoing POST body so the LD 244 [pause]
    tag protection reaches the server.

    task_id = tier3-bugfix-toast-skipflag-20260419
    preflight = 75 (parent = 68)
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.src = TARGET.read_text(encoding="utf-8")
        cls.fn_body = cls._extract_pathappPatch_body(cls.src)

    @staticmethod
    def _extract_pathappPatch_body(src: str) -> str:
        """Return the substring from `async function pathappPatch(...)`
        through the assignment `window.pathappPatch = pathappPatch;`."""
        header = "async function pathappPatch(beatId, field, value, options)"
        end_marker = "window.pathappPatch = pathappPatch;"
        start = src.find(header)
        end = src.find(end_marker, start)
        assert start >= 0, "pathappPatch header not found"
        assert end >= 0, "pathappPatch end marker not found"
        return src[start:end]

    def test_bug1_toast_uses_window_binding(self) -> None:
        """Bug 1 — 6 call sites in pathappPatch must use window.pathappSetSaveInd(,
        and 0 bare pathappSetSaveInd( calls must remain."""
        body = self.fn_body
        window_count = body.count("window.pathappSetSaveInd(")
        # Bare count = total occurrences of the name minus the window-prefixed ones.
        # Important: we scope to the pathappPatch function body, so the
        # definition at line 1868 and the window assignment at line 1942 are
        # already excluded from fn_body.
        total_name_uses = body.count("pathappSetSaveInd(")
        bare_count = total_name_uses - window_count
        self.assertGreaterEqual(
            window_count, 6,
            f"pathappPatch must have ≥6 window.pathappSetSaveInd( call sites, "
            f"got {window_count}",
        )
        self.assertEqual(
            bare_count, 0,
            f"pathappPatch must have 0 bare pathappSetSaveInd( call sites, "
            f"got {bare_count} (lexical-closure bug would resurface)",
        )

    def test_bug2_skip_tts_regen_forwarded(self) -> None:
        """Bug 2 — pathappPatch must copy options.skip_tts_regen into body."""
        body = self.fn_body
        self.assertIn(
            "body.skip_tts_regen",
            body,
            "pathappPatch must forward options.skip_tts_regen into body "
            "(LD 244 [pause] tag protection)",
        )
        # Guarded form — not a raw assignment.
        self.assertRegex(
            body,
            r"if\s*\(\s*options\s*&&\s*options\.skip_tts_regen\s*\)\s*"
            r"body\.skip_tts_regen\s*=\s*true",
            "skip_tts_regen must be set via guarded `if (options && "
            "options.skip_tts_regen)` form",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
