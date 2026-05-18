"""Shared base for extracted handler modules. V59 Phase 4.

Handler modules import `BaseHandlerMixin` and inherit from it. The mixin
exposes `self.app`, `self.app.state`, `self._send_json`, `self._send_error`,
`self._read_body`, etc. — all the helpers currently on ProductionHandler
that handlers depend on.

The actual ProductionHandler in production_server.py also inherits from
BaseHandlerMixin so the dispatch chain works after handlers are extracted.
"""
from __future__ import annotations
# Import nothing — this file is a marker for the extraction phase
