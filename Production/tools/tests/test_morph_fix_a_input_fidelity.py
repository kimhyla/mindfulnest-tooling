#!/usr/bin/env python3
"""Fix A v2 regression tests — input_fidelity:high must be present in
the OpenAI /v1/images/edits multipart body sent by
``openai_image_edit_generate_end_frame``.

task_id = morph-fix-a-v2-input-fidelity-20260518
preflight = (spawned task, parent session 1fe4b973)
LD coverage = LD-439 carryover (input_fidelity:high precedent),
               LD-730 (OpenAI vendor end-frame gen), LD-745 + LD-781
               (prompt-layer fixes that did NOT address the morph regression).
Reference doc = prod_reference_docs id=231
                Production/docs/V59_BACKGROUND_MORPH_REGRESSION_DIAGNOSIS_v1.md

Diagnosis verdict (from id=231 §6):
  Root cause = hybrid H2 + H1.5. Specifically: the LD-439 amendment
  (``input_fidelity: "high"``) was NOT carried over from the still-gen
  path (beat_generator.py:1176) to the end-frame path
  (kling_startend_pipeline.py openai_image_edit_generate_end_frame).

Fix A v2 = add ``_field("input_fidelity", "high")`` to ``body_parts``
within ``openai_image_edit_generate_end_frame`` so every OpenAI
end-frame call sends the parameter.

Test approach:
  - Monkey-patch ``http.client.HTTPSConnection`` inside the target
    module's namespace, intercept ``conn.request(method, path, body,
    headers)`` to capture the raw multipart bytes.
  - Stub a minimal OpenAI-like JSON response (containing a 1x1 PNG
    encoded as base64 in ``data[0].b64_json``) so the function returns
    without raising.
  - Assert on the captured bytes:
      * field name ``input_fidelity`` appears in body
      * value ``high`` appears in body adjacent to the field name
      * field appears in the multipart body alongside ``model`` /
        ``prompt`` / ``quality`` (proves no accidental relocation
        outside the body)

NO network calls. Fully offline. Deterministic.
"""

from __future__ import annotations

import base64
import io
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


# Minimal 1x1 transparent PNG bytes (for the response payload).
_MIN_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBg"
    "AAAABQABh6FO1AAAAABJRU5ErkJggg=="
)


class _FakeResponse:
    """Mimics http.client.HTTPResponse just enough for the function."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body


class _CapturingHTTPSConnection:
    """Replacement for http.client.HTTPSConnection that records the
    multipart body so the test can assert on its contents.

    All instances of this class write to the class-level
    ``last_request`` dict so the test can read it after the function
    returns.
    """

    last_request: dict = {}

    def __init__(self, host: str, timeout: int = 60, context=None) -> None:
        self.host = host
        self.timeout = timeout

    def request(self, method: str, path: str, body: bytes, headers: dict) -> None:
        type(self).last_request = {
            "method": method,
            "path": path,
            "body": body,
            "headers": headers,
        }

    def getresponse(self) -> _FakeResponse:
        # Build a minimal OpenAI-like JSON response containing a valid PNG.
        import json as _json
        resp_body = _json.dumps(
            {"data": [{"b64_json": _MIN_PNG_B64}]}
        ).encode("utf-8")
        return _FakeResponse(200, resp_body)

    def close(self) -> None:
        pass


class FixAInputFidelityMultipartTests(unittest.TestCase):
    """Assert input_fidelity:high is present in the multipart body
    sent to /v1/images/edits."""

    def _invoke(self) -> bytes:
        """Run openai_image_edit_generate_end_frame with HTTPS conn
        monkey-patched. Returns the captured multipart body bytes."""
        import kling_startend_pipeline as mod
        import http.client as _hc

        # Patch http.client.HTTPSConnection inside the module's namespace
        # (the function does `import http.client as _http`, so we have
        # to patch http.client.HTTPSConnection at module global scope
        # since _http is just an alias).
        original = _hc.HTTPSConnection
        _hc.HTTPSConnection = _CapturingHTTPSConnection
        _CapturingHTTPSConnection.last_request = {}
        try:
            # Call with tiny inputs; the fake conn returns a valid PNG so
            # the function should return without raising.
            png_out = mod.openai_image_edit_generate_end_frame(
                start_image_bytes=b"\x89PNG\r\n\x1a\nFAKE",
                end_prompt="test prompt — does not matter for body capture",
                api_key="sk-test-fake-key-not-used",
                aspect_ratio="4:3",
                timeout_s=30,
            )
            self.assertIsInstance(png_out, bytes)
            self.assertGreater(len(png_out), 0)
        finally:
            _hc.HTTPSConnection = original

        captured = _CapturingHTTPSConnection.last_request
        self.assertIn("body", captured, "HTTPS request not captured")
        return captured["body"]

    def test_input_fidelity_field_present_in_body(self) -> None:
        """The multipart body MUST contain a form field named input_fidelity."""
        body = self._invoke()
        self.assertIn(
            b'name="input_fidelity"',
            body,
            "input_fidelity form field absent from multipart body",
        )

    def test_input_fidelity_value_is_high(self) -> None:
        """The input_fidelity field MUST have value 'high'."""
        body = self._invoke()
        # Multipart field format:
        # ----<boundary>\r\nContent-Disposition: form-data; name="input_fidelity"\r\n\r\nhigh\r\n
        body_str = body.decode("utf-8", "replace")
        marker = 'name="input_fidelity"\r\n\r\nhigh\r\n'
        self.assertIn(
            marker,
            body_str,
            f"input_fidelity value is not 'high' — body excerpt around field:\n"
            f"{body_str[max(0, body_str.find('input_fidelity') - 40):body_str.find('input_fidelity') + 200]!r}",
        )

    def test_input_fidelity_alongside_other_required_fields(self) -> None:
        """Sanity check that input_fidelity is in the multipart body
        alongside the other required form fields (model, prompt,
        quality, size, n) and not e.g. accidentally added to the URL
        path or headers."""
        body = self._invoke()
        for required in (
            b'name="model"',
            b'name="prompt"',
            b'name="quality"',
            b'name="size"',
            b'name="n"',
            b'name="input_fidelity"',
            b'name="image"',  # the PNG attachment
        ):
            self.assertIn(
                required,
                body,
                f"Required multipart field {required!r} absent from body",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
