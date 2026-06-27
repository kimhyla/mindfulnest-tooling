"""Shared Phase A/B module lipsync job contract — server + PhaseProducer UI.

Truth model: ``phase_{a|b}_lipsync_status`` + ``phase_{a|b}_lipsync_task_id`` on
``production_state.json``. UI busy state is derived only from these fields —
no parallel client-side job flags.
"""
from __future__ import annotations

PHASE_LIPSYNC_IN_FLIGHT_STATUSES = frozenset({
    "running",      # Phase A local worker
    "polling",      # Phase B Kling — persistent poller owns terminal writes
    "submitting",
    "submitted",
})

PHASE_LIPSYNC_TERMINAL_SUCCESS = frozenset({
    "done",
    "needs_manual_visual_review",
})

PHASE_LIPSYNC_TERMINAL_CLEARED = frozenset({
    "rejected",
    "idle",
})

PHASE_LIPSYNC_TERMINAL_FAILURE_PREFIX = "error:"
PHASE_LIPSYNC_QA_FAILED = "qa_failed"

# Statuses that require a vendor task_id before UI shows in-flight (Kling path).
_PHASE_LIPSYNC_TASK_BOUND = frozenset({"polling", "submitting", "submitted"})


def phase_lipsync_job_busy(
    status: str | None,
    task_id: str | None = None,
) -> bool:
    """Server-owned in-flight — sole authority for PhaseProducer busy UI."""
    s = str(status or "").strip().lower()
    if s not in PHASE_LIPSYNC_IN_FLIGHT_STATUSES:
        return False
    if s in _PHASE_LIPSYNC_TASK_BOUND:
        return bool(str(task_id or "").strip())
    # Phase A ``running`` — worker thread is authoritative; task_id optional.
    return s == "running"


def phase_lipsync_is_terminal(status: str | None) -> bool:
    s = str(status or "").strip().lower()
    if not s:
        return True
    if s in PHASE_LIPSYNC_TERMINAL_SUCCESS:
        return True
    if s in PHASE_LIPSYNC_TERMINAL_CLEARED:
        return True
    if s == PHASE_LIPSYNC_QA_FAILED:
        return True
    return s.startswith(PHASE_LIPSYNC_TERMINAL_FAILURE_PREFIX)


def phase_lipsync_progress_message(phase: str) -> str:
    p = (phase or "b").strip().lower()
    if p == "a":
        return (
            "⏳ Lipsync processing (~5–20 min). "
            "Safe to switch tabs — will auto-update when done."
        )
    return (
        "⏳ Avatar Pro lipsync in progress (~10–50 min for full meditation). "
        "Safe to switch tabs — will auto-update when done."
    )


def phase_lipsync_terminal_banner(status: str | None, phase: str) -> str | None:
    """User-facing line when job is terminal (not in-flight)."""
    s = str(status or "").strip()
    if not s or phase_lipsync_job_busy(s):
        return None
    low = s.lower()
    if low in PHASE_LIPSYNC_TERMINAL_CLEARED:
        return "✓ Lipsync cleared — waveform shows voice stem; trim or resend when ready."
    if low in PHASE_LIPSYNC_TERMINAL_SUCCESS:
        return "✓ Lipsync complete — preview ready."
    if low == PHASE_LIPSYNC_QA_FAILED:
        return "✗ Lipsync QA failed — review frames or regenerate."
    if low.startswith(PHASE_LIPSYNC_TERMINAL_FAILURE_PREFIX):
        detail = s.split(":", 1)[-1].strip() or "unknown error"
        return f"✗ Lipsync failed: {detail}"
    return None
