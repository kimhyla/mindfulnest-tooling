"""Pytest config for claude_review tests.

Adds the parent directory (.github/workflows/scripts) to sys.path so the
tests can import claude_review directly without any package installation.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent.parent.resolve()
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
