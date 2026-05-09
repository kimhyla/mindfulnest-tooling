#!/usr/bin/env python3
"""
MindfulNest Production Pipeline Orchestrator.

Reads all state from Directus, executes production stages by calling
existing Python tools, logs everything automatically, and stops at
hard gates for Kim's approval.

Usage:
    python3 pipeline.py --smoke-test                              # Test all connections
    python3 pipeline.py --list                                    # List all modules + stages
    python3 pipeline.py --module M1 --event 1 --status           # Show current state
    python3 pipeline.py --module M1 --event 1 --run              # Run next pending sub-step
    python3 pipeline.py --module M1 --event 1 --run --step tts   # Run specific sub-step
    python3 pipeline.py --module M1 --event 1 --approve          # Approve current gate
    python3 pipeline.py --module M1 --event 1 --run --skip-validators  # Bypass QA

Architecture decisions (locked April 13, 2026):
    - 5-stage model (sub-steps within existing stages, no DB migration)
    - Phase B skipped (creative work, done in Cowork with skills)
    - Images must exist before storyboard (pipeline refuses without approved assets)
    - QA validators run automatically after each sub-step (April 14, 2026)
"""

import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

# Add the tools directory to path so we can import lib and existing tools
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(TOOLS_DIR))  # Claude Mindfulnest Project Files
sys.path.insert(0, TOOLS_DIR)

from credentials_lib.credentials import load_credentials
from credentials_lib.directus import DirectusClient, DirectusError, parse_module_id

# QA Validators — import from Production/validators/
PRODUCTION_DIR = os.path.join(PROJECT_DIR, "Production")
sys.path.insert(0, PRODUCTION_DIR)
try:
    from validators.runner import validate_artifact, validate_directory, calibration_report
    from validators import ArtifactType
    VALIDATORS_AVAILABLE = True
except ImportError:
    VALIDATORS_AVAILABLE = False

# Global flag set by --skip-validators
SKIP_VALIDATORS = False


def validate_output(file_path, client=None, module_id=None, step_name=None):
    """Post-step QA validation. Returns True if valid, False if blockers found.

    Behavior:
    - If SKIP_VALIDATORS is True: logs bypass, returns True
    - If validators not importable: warns, returns True (graceful degradation)
    - Tier 1 failures: logs to Directus, returns False (blocks pipeline)
    - Tier 2 warnings: logs to Directus, returns True (doesn't block)
    """
    if SKIP_VALIDATORS:
        print(f"  ⚠️  Validators bypassed (--skip-validators)")
        if client and module_id:
            client.log_activity(module_id, f"{step_name}_validators_skipped", {
                "file": os.path.basename(file_path),
                "reason": "kill_switch"
            })
        return True

    if not VALIDATORS_AVAILABLE:
        print(f"  ⚠️  Validators not available (import failed). Skipping QA.")
        return True

    if not os.path.exists(file_path):
        print(f"  ⚠️  Output file not found for validation: {file_path}")
        return True  # Don't block on missing file — step handler should catch this

    result = validate_artifact(file_path)

    if result.skipped:
        print(f"  ℹ️  Validator skipped: {result.skip_reason}")
        return True

    # Log all checks
    if client and module_id:
        try:
            client.log_activity(module_id, f"{step_name}_validated", result.to_directus_log())
        except Exception:
            pass  # Don't fail pipeline on logging errors

    if result.is_valid:
        warnings = result.tier2_warnings
        if warnings:
            print(f"  ✅ QA passed with {len(warnings)} warning(s):")
            for w in warnings:
                print(f"     ⚠️  {w.name}: {w.message}")
        else:
            print(f"  ✅ QA passed — all checks clean")
        return True
    else:
        failures = result.tier1_failures
        print(f"  ❌ QA FAILED — {len(failures)} blocker(s):")
        for f in failures:
            print(f"     ❌ {f.name}: {f.message}")
        if result.retry_count > 0:
            print(f"     (auto-fix attempted {result.retry_count} time(s))")
        return False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The 5 pipeline stages (matches prod_stages in Directus)
STAGE_ORDER = ["intake", "phase_b", "phase_a_json", "audio", "listen_through"]

# Stages that require creative work (pipeline pauses, hands off to Cowork)
CREATIVE_STAGES = {"phase_b"}

# Hard gates (require Kim's explicit approval before advancing)
HARD_GATES = {"phase_b", "listen_through"}

# Sub-steps available within each stage
STAGE_SUBSTEPS = {
    "intake": ["intake_brief"],
    "phase_b": [],  # Creative — no automated sub-steps
    "phase_a_json": ["phase_a_design", "module_json", "narrative_gen", "magic_trail"],
    "audio": ["tts", "storyboard", "voice_stem", "cue_points", "mix"],
    "listen_through": [],  # Kim listens — no automated sub-steps
}

# Module creature names (for display)
CREATURE_NAMES = {
    1: "Tessa (Turtle)",
    2: "Luna (Owl)",
    3: "Benson (Bear)",
    4: "Ember (Fox)",
    5: "Bork (Porcupine)",
    6: "Bramble (Tree Creature)",
}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_smoke_test(client, creds):
    """Test all API connections."""
    print("=" * 60)
    print("  MindfulNest Pipeline — Smoke Test")
    print("=" * 60)
    print()

    # 1. Directus
    print("Directus Dashboard:")
    result = client.smoke_test()
    print(f"  Auth:   {'✅ OK' if result['auth'] else '❌ FAIL'}")
    print(f"  Query:  {'✅ OK' if result['query'] else '❌ FAIL'}")
    print(f"  Schema: {'✅ OK' if result['schema'] else '❌ FAIL'}")
    for err in result.get("errors", []):
        print(f"  ⚠️  {err}")
    print()

    # 2. ElevenLabs (check key exists)
    el_key = creds.get("elevenlabs_key", "")
    print("ElevenLabs TTS:")
    if el_key and len(el_key) > 10:
        print(f"  API Key: ✅ Present ({el_key[:8]}...)")
    else:
        print(f"  API Key: ❌ Missing or too short")
    print()

    # 3. BFL FLUX Kontext
    bfl_key = creds.get("bfl_key", "")
    print("FLUX Kontext (BFL):")
    if bfl_key and len(bfl_key) > 5:
        print(f"  API Key: ✅ Present ({bfl_key[:8]}...)")
    else:
        print(f"  API Key: ❌ Missing")
    print()

    # 4. WaveSpeed (Seedance + ByteDance)
    ws_key = creds.get("wavespeed_key", "")
    print("WaveSpeed (Seedance + ByteDance):")
    if ws_key and len(ws_key) > 10:
        print(f"  API Key: ✅ Present ({ws_key[:8]}...)")
    else:
        print(f"  API Key: ❌ Missing")
    print()

    # Summary
    all_ok = result["auth"] and result["query"] and result["schema"]
    print("=" * 60)
    if all_ok:
        print("  ✅ All critical systems operational.")
    else:
        print("  ❌ Some systems failed. Fix errors above before production.")
    print("=" * 60)

    return 0 if all_ok else 1


def cmd_list(client):
    """List all modules with their current stage and status."""
    print("=" * 60)
    print("  MindfulNest Production Pipeline — Module Status")
    print("=" * 60)
    print()

    modules = client.get_all_modules()

    if not modules:
        print("  No modules found in prod_modules.")
        print("  Run dashboard-ops skill to initialize module data.")
        return 1

    print(f"  {'M#':<4} {'Creature':<22} {'Stage':<16} {'Status':<14}")
    print(f"  {'─'*4} {'─'*22} {'─'*16} {'─'*14}")

    for m in modules:
        m_num = m.get("m_number", "?")
        creature = CREATURE_NAMES.get(m_num, f"Module {m_num}")
        stage = m.get("current_stage", "unknown")
        status = m.get("stage_status", "unknown")

        # Status indicators
        status_icon = {
            "not_started": "⬜",
            "in_progress": "🔵",
            "blocked": "🔴",
            "completed": "✅",
            "waiting_approval": "⏸️",
        }.get(status, "❓")

        print(f"  M{m_num:<3} {creature:<22} {stage:<16} {status_icon} {status}")

    print()

    # Show stage legend
    print("  Pipeline stages: ", end="")
    for i, stage in enumerate(STAGE_ORDER):
        marker = "🔒" if stage in HARD_GATES else "→"
        if i > 0:
            print(f" {marker} ", end="")
        print(stage, end="")
    print()
    print("  🔒 = Hard gate (requires Kim's approval)")
    print()

    return 0


def cmd_status(client, module_id, event):
    """Show detailed status for a specific module."""
    print("=" * 60)
    creature = CREATURE_NAMES.get(module_id, f"Module {module_id}")
    print(f"  M{module_id} — {creature} — Event {event}")
    print("=" * 60)
    print()

    state = client.bootstrap(module_id)
    module = state["module"]

    if module.get("_error"):
        print(f"  ❌ {module['_error']}")
        return 1

    # Current stage
    stage = module.get("current_stage", "unknown")
    status = module.get("stage_status", "unknown")
    print(f"  Stage:  {stage}")
    print(f"  Status: {status}")

    # Stage progress bar
    print()
    print("  Progress: ", end="")
    stage_idx = STAGE_ORDER.index(stage) if stage in STAGE_ORDER else -1
    for i, s in enumerate(STAGE_ORDER):
        if i < stage_idx:
            print(f"[✅ {s}] ", end="")
        elif i == stage_idx:
            icon = "🔵" if status == "in_progress" else "⏸️" if status in ("waiting_approval", "blocked") else "⬜"
            print(f"[{icon} {s}] ", end="")
        else:
            print(f"[⬜ {s}] ", end="")
    print()

    # Locked decisions
    locked = state.get("locked_decisions", [])
    if locked:
        print(f"\n  Locked Decisions: {len(locked)}")
        for d in locked[:5]:
            key = d.get("decision_key", "?")
            val = d.get("decision_value", "?")
            print(f"    • {key}: {val}")
        if len(locked) > 5:
            print(f"    ... and {len(locked) - 5} more")

    # Blockers
    blockers = state.get("blockers", [])
    if blockers:
        print(f"\n  ⚠️  Unresolved Blockers: {len(blockers)}")
        for b in blockers:
            severity = b.get("severity", "?")
            title = b.get("title", "?")
            icon = "🔴" if severity in ("critical", "high") else "🟡"
            print(f"    {icon} [{severity}] {title}")
    else:
        print(f"\n  ✅ No unresolved blockers")

    # Recent activity
    activity = state.get("activity", [])
    if activity:
        print(f"\n  Recent Activity (last {min(5, len(activity))}):")
        for a in activity[:5]:
            action = a.get("action", "?")
            when = a.get("created_at", "?")
            verdict = a.get("kim_verdict", "")
            verdict_str = f" → Kim: {verdict}" if verdict else ""
            # Truncate timestamp to date+time
            if isinstance(when, str) and len(when) > 16:
                when = when[:16]
            print(f"    {when}  {action}{verdict_str}")

    # Audio assets
    audio = state.get("audio_assets", [])
    if audio:
        print(f"\n  Audio Assets: {len(audio)}")
        for a in audio:
            # Try multiple possible field names
            name = (a.get("file_name") or a.get("filename")
                    or a.get("asset_name") or a.get("file_path", "?"))
            # Shorten long paths to just filename
            if "/" in str(name):
                name = name.rsplit("/", 1)[-1]
            status_a = a.get("status", "?")
            ftype = a.get("file_type", "")
            type_str = f" ({ftype})" if ftype else ""
            print(f"    • {name}{type_str} [{status_a}]")

    # Visual assets
    visual = state.get("visual_assets", [])
    if visual:
        approved = sum(1 for v in visual if v.get("status") == "approved")
        print(f"\n  Visual Assets: {len(visual)} ({approved} approved)")

    # Voice profiles
    voices = state.get("voice_profiles", [])
    if voices:
        print(f"\n  Voice Profiles: {len(voices)}")
        for v in voices:
            name = v.get("character_name", "?")
            vid = v.get("elevenlabs_voice_id", "?")
            stab = v.get("stability", "?")
            print(f"    • {name}: {vid[:12]}... (stability: {stab})")

    # Session state
    notes = module.get("session_resumption_notes")
    if notes:
        print(f"\n  Resumption Notes:")
        print(f"    {notes}")

    checklist = module.get("session_checklist")
    if checklist and isinstance(checklist, list):
        # Checklist items may be dicts {"description": str, "done": bool}
        # or plain strings (legacy format). Handle both.
        done = 0
        total = len(checklist)
        print(f"\n  Session Checklist:")
        for item in checklist:
            if isinstance(item, dict):
                is_done = item.get("done", False)
                desc = item.get("description", "?")
            else:
                # Legacy: treat string as description, not done
                is_done = False
                desc = str(item)
            if is_done:
                done += 1
            icon = "✅" if is_done else "⬜"
            print(f"    {icon} {desc}")
        print(f"    ({done}/{total} complete)")

    # Next action recommendation
    print()
    print("─" * 60)
    if stage in CREATIVE_STAGES:
        print(f"  ⏸️  '{stage}' requires creative work.")
        print(f"     Use the appropriate skill in Cowork.")
        print(f"     When approved, run: pipeline.py --module M{module_id} --event {event} --approve")
    elif status == "blocked":
        print(f"  🔴 Module is blocked. Resolve blockers before continuing.")
    elif status == "completed" and stage in HARD_GATES:
        print(f"  ⏸️  '{stage}' gate completed. Awaiting approval.")
        print(f"     Run: pipeline.py --module M{module_id} --event {event} --approve")
    elif status in ("not_started", "in_progress"):
        substeps = STAGE_SUBSTEPS.get(stage, [])
        if substeps:
            print(f"  ▶️  Ready to run. Available sub-steps for '{stage}':")
            for ss in substeps:
                print(f"       pipeline.py --module M{module_id} --event {event} --run --step {ss}")
            print(f"     Or run all: pipeline.py --module M{module_id} --event {event} --run")
        else:
            print(f"  ▶️  Ready to advance.")
    print("─" * 60)

    return 0


def cmd_run(client, module_id, event, step=None):
    """Execute the next (or specified) pipeline sub-step."""
    state = client.bootstrap(module_id)
    module = state["module"]

    if module.get("_error"):
        print(f"❌ {module['_error']}")
        return 1

    stage = module.get("current_stage", "unknown")
    status = module.get("stage_status", "unknown")

    # Check for blockers
    blockers = state.get("blockers", [])
    critical_blockers = [b for b in blockers
                         if b.get("severity") in ("critical", "high")]
    if critical_blockers:
        print(f"🔴 Module M{module_id} has {len(critical_blockers)} critical/high blockers:")
        for b in critical_blockers:
            print(f"   • [{b.get('severity')}] {b.get('title')}")
        print(f"   Resolve blockers before running pipeline.")
        return 1

    # Check if at a creative stage
    if stage in CREATIVE_STAGES:
        print(f"⏸️  M{module_id} is at '{stage}' — this requires creative work.")
        print(f"   Use the appropriate skill in Cowork to do this work.")
        print(f"   When Kim approves, run:")
        print(f"     pipeline.py --module M{module_id} --event {event} --approve")
        return 0

    # Check if waiting for approval
    if stage in HARD_GATES and status == "completed":
        print(f"⏸️  M{module_id} has completed '{stage}' and is waiting for approval.")
        print(f"   Run: pipeline.py --module M{module_id} --event {event} --approve")
        return 0

    # Dispatch to stage handler
    available_steps = STAGE_SUBSTEPS.get(stage, [])

    if step:
        if step not in available_steps:
            print(f"❌ Sub-step '{step}' is not available at stage '{stage}'.")
            print(f"   Available: {', '.join(available_steps) if available_steps else 'none (creative stage)'}")
            return 1
        return _run_substep(client, state, module_id, event, stage, step)
    else:
        # Run all sub-steps in order
        if not available_steps:
            print(f"⏸️  Stage '{stage}' has no automated sub-steps.")
            return 0

        for ss in available_steps:
            print(f"\n{'='*40}")
            print(f"  Sub-step: {ss}")
            print(f"{'='*40}")
            result = _run_substep(client, state, module_id, event, stage, ss)
            if result != 0:
                print(f"\n❌ Sub-step '{ss}' failed. Stopping pipeline.")
                return result
            # Re-read state after each sub-step
            state = client.bootstrap(module_id)

        print(f"\n✅ All sub-steps for '{stage}' complete.")

        # If this stage is a hard gate, mark waiting for approval
        if stage in HARD_GATES:
            client.update("prod_modules", module["id"], {
                "stage_status": "completed"
            })
            print(f"⏸️  Awaiting Kim's approval at '{stage}' gate.")
            print(f"   Run: pipeline.py --module M{module_id} --event {event} --approve")
        else:
            # Auto-advance to next stage
            next_stage = _get_next_stage(stage)
            if next_stage:
                client.advance_stage(module["id"], next_stage)
                client.log_activity(module_id, f"stage_advanced",
                                    {"from": stage, "to": next_stage})
                print(f"▶️  Advanced to stage: {next_stage}")
            else:
                client.update("prod_modules", module["id"], {
                    "stage_status": "completed"
                })
                print(f"🎉 Module M{module_id} pipeline complete!")

        return 0


def cmd_approve(client, module_id, event):
    """Approve a hard gate and advance to the next stage."""
    state = client.bootstrap(module_id)
    module = state["module"]

    if module.get("_error"):
        print(f"❌ {module['_error']}")
        return 1

    stage = module.get("current_stage", "unknown")

    if stage not in HARD_GATES:
        print(f"❌ Stage '{stage}' is not a hard gate. Nothing to approve.")
        print(f"   Hard gates: {', '.join(HARD_GATES)}")
        return 1

    # Record approval in prod_approvals
    try:
        client.create("prod_approvals", {
            "module_id": module_id,
            "gate_type": stage,
            "status": "approved",
            "approved_by": "kim",
            "approval_date": datetime.now(timezone.utc).isoformat()
        })
    except DirectusError as e:
        print(f"⚠️  Could not record approval: {e}")
        print(f"   Continuing with stage advance...")

    # Log activity
    client.log_activity(module_id, f"{stage}_approved", {
        "gate": stage,
        "approved_by": "kim",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    # Advance to next stage
    next_stage = _get_next_stage(stage)
    if next_stage:
        client.advance_stage(module["id"], next_stage)
        client.log_activity(module_id, "stage_advanced",
                            {"from": stage, "to": next_stage})
        creature = CREATURE_NAMES.get(module_id, f"M{module_id}")
        print(f"✅ '{stage}' approved for {creature}.")
        print(f"▶️  Advanced to: {next_stage}")
    else:
        client.update("prod_modules", module["id"], {
            "stage_status": "completed"
        })
        print(f"🎉 Module M{module_id} is complete!")

    return 0


# ---------------------------------------------------------------------------
# Sub-step dispatch
# ---------------------------------------------------------------------------

def _run_substep(client, state, module_id, event, stage, step):
    """Dispatch to a specific sub-step handler.

    Returns 0 on success, non-zero on failure.
    """
    # Mark module as in_progress
    module = state["module"]
    if module.get("id"):
        client.update("prod_modules", module["id"], {
            "stage_status": "in_progress"
        })

    handlers = {
        # intake sub-steps
        "intake_brief": _step_intake_brief,
        # phase_a_json sub-steps
        "phase_a_design": _step_phase_a_design,
        "module_json": _step_module_json,
        "narrative_gen": _step_narrative_gen,
        # magic trail compositor (phase_a_json)
        "magic_trail": _step_magic_trail,
        # audio sub-steps
        "tts": _step_tts,
        "storyboard": _step_storyboard,
        "voice_stem": _step_voice_stem,
        "cue_points": _step_cue_points,
        "mix": _step_mix,
    }

    handler = handlers.get(step)
    if not handler:
        print(f"❌ No handler for sub-step '{step}'. Not yet implemented.")
        return 1

    try:
        result = handler(client, state, module_id, event)
        if result != 0:
            return result

        # --- QA Validation Gate ---
        # After a successful sub-step, validate any output artifacts.
        # The handler may set state["_output_file"] to tell us what to validate.
        output_file = state.get("_output_file")
        if output_file and os.path.exists(output_file):
            if not validate_output(output_file, client, module_id, step):
                print(f"  🔴 Pipeline paused: QA validation failed for {os.path.basename(output_file)}")
                print(f"     Fix the issue and re-run, or use --skip-validators to bypass.")
                return 1

        return 0
    except DirectusError as e:
        print(f"❌ Directus error in '{step}': {e}")
        client.log_activity(module_id, f"{step}_failed", {
            "error": str(e),
            "stage": stage
        })
        return 1
    except Exception as e:
        print(f"❌ Error in '{step}': {e}")
        client.log_activity(module_id, f"{step}_failed", {
            "error": str(e),
            "stage": stage
        })
        return 1


# ---------------------------------------------------------------------------
# Sub-step implementations (Phase 1: stubs with clear messages)
# ---------------------------------------------------------------------------

def _step_intake_brief(client, state, module_id, event):
    """Generate intake brief from arc skeleton."""
    print("  📋 Intake Brief — Not yet implemented.")
    print("     Use the intake-briefer skill in Cowork for now.")
    return 0


def _step_phase_a_design(client, state, module_id, event):
    """Generate Phase A beat sheet."""
    print("  🎨 Phase A Design — Not yet implemented.")
    print("     Use the phase-a-designer skill in Cowork for now.")
    return 0


def _step_module_json(client, state, module_id, event):
    """Generate module JSON configuration."""
    print("  📦 Module JSON — Not yet implemented.")
    print("     Use the module-json-builder skill in Cowork for now.")
    return 0


def _step_narrative_gen(client, state, module_id, event):
    """Generate narrative cache."""
    print("  📖 Narrative Generation — Not yet implemented.")
    print("     Use the narrative-generator skill in Cowork for now.")
    return 0


def _step_magic_trail(client, state, module_id, event):
    """
    Render the resolution-scene magic trail for this event using MagicCompositor.

    Approved style: tessa_ori (LD MAGIC_STYLE_TESSA_ORI_V1 / Directus id=398).
    Approved approach: sparkle river v6 — pre-placed particles, additive blend,
    floor-flat anisotropic scatter. Kim approved 2026-04-22.

    Outputs: preview PNG + full MP4 in Production/Event_{N}/kling_clips/
    Usage: pipeline.py --module M1 --event 1 --run --step magic_trail
    """
    import sys
    sys.path.insert(0, TOOLS_DIR)
    from magic_compositor import MagicCompositor

    # Per-event scene config: background still + bezier path control points.
    # Add a new entry here when a new resolution scene background is ready.
    # Path geometry rule: endpoint must be at the STEP EDGE of the altar/focal
    # point, NOT floating above it (LD MAGIC_STYLE_TESSA_ORI_V1).
    EVENT_CONFIGS = {
        1: {
            "background": os.path.join(
                PROJECT_DIR, "Production", "Event_1", "resolution_stills",
                "heartwood_3q_left_1456.png"
            ),
            # Locked geometry: altar step edge at y=0.670 (NOT altar top 0.60)
            "path_pts": [
                (0.01, 0.745),
                (0.18, 0.755),
                (0.35, 0.735),
                (0.47, 0.670),
            ],
        },
        # Future events: add entries as backgrounds are produced and geometry locked.
        # e.g. 2: {"background": "...", "path_pts": [...]}
    }

    cfg = EVENT_CONFIGS.get(int(event))
    if cfg is None:
        print(f"  ⚠️  No magic trail config for Event {event} yet.")
        print(f"     Add an entry to EVENT_CONFIGS in _step_magic_trail().")
        print(f"     Skipping — not a blocking error.")
        return 0

    if not os.path.exists(cfg["background"]):
        print(f"  ❌ Background image not found: {cfg['background']}")
        print(f"     Generate the resolution still first.")
        return 1

    out_dir = os.path.join(PROJECT_DIR, "Production", f"Event_{event}", "kling_clips")
    os.makedirs(out_dir, exist_ok=True)
    label = f"event{event}_resolution"

    print(f"  ✨ Magic Trail Compositor — Event {event} (style: tessa_ori)", flush=True)
    print(f"     LD: MAGIC_STYLE_TESSA_ORI_V1 (Directus id=398)", flush=True)

    mc = MagicCompositor(
        background_path=cfg["background"],
        path_pts=cfg["path_pts"],
        style="tessa_ori",
        duration=3.5,
        fps=24,
        output_dir=out_dir,
        label=label,
    )
    preview_path = mc.render_preview()
    video_path   = mc.render_video()

    # Register output in activity log
    client.log_activity(module_id, "magic_trail_rendered", {
        "event": event,
        "style": "tessa_ori",
        "ld_key": "MAGIC_STYLE_TESSA_ORI_V1",
        "preview": os.path.basename(preview_path),
        "video": os.path.basename(video_path),
        "video_bytes": os.path.getsize(video_path),
    })

    state["_output_file"] = video_path
    print(f"  ✅ Magic trail rendered: {os.path.basename(video_path)}", flush=True)
    return 0


def _step_tts(client, state, module_id, event):
    """Generate TTS for dialogue lines."""
    print("  🎙️  TTS Generation — Not yet implemented (Phase 3).")
    print("     Use the audio-producer skill in Cowork for now.")
    return 0


def _step_storyboard(client, state, module_id, event):
    """Build storyboard from registry.

    Full pipeline:
    1. Check for approved visual assets (HARD REQUIREMENT — images first)
    2. Find the locked lines JSON (Kim's exported sequence or canonical file)
    3. Find the latest existing storyboard HTML (for regression audit)
    4. Determine next version number
    5. Call build_storyboard.py --registry with all arguments
    6. Parse output for regression failures (image scrambling = FAIL)
    7. Update Directus dashboard (storyboard_status, version, built_at)
    8. Log activity
    """

    event_dir = os.path.join(PROJECT_DIR, "Production", f"Event_{event}")

    # ------------------------------------------------------------------
    # 1. Check for approved visual assets (locked decision: images first)
    # ------------------------------------------------------------------
    approved = client.get_approved_visual_assets(module_id, event)
    if not approved:
        print("  ❌ No approved visual assets in registry for "
              f"M{module_id} Event {event}.")
        print("     Register and approve images before building storyboard.")
        print("     Use dashboard-ops skill or FLUX Kontext to create images,")
        print("     then register them in prod_visual_assets.")
        return 1

    print(f"  📸 Found {len(approved)} approved visual assets.")

    # ------------------------------------------------------------------
    # 2. Find the locked lines JSON
    # ------------------------------------------------------------------
    lines_path = _find_lines_json(event_dir, module_id, event)
    if not lines_path:
        print(f"  ❌ No lines JSON found for M{module_id} Event {event}.")
        print(f"     Expected one of:")
        print(f"       - M{module_id}E{event}_locked_lines_v*.json")
        print(f"       - storyboard_sequence_*.json")
        print(f"     In: {event_dir}")
        print(f"     Export from the storyboard ('Download as JSON for builder')")
        print(f"     or create one from the arc skeleton dialogue.")
        return 1

    # Validate the lines JSON
    try:
        with open(lines_path) as f:
            lines_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ❌ Cannot read lines JSON: {e}")
        # If this was an export and it's corrupt, fall back to locked file
        if "storyboard_sequence" in os.path.basename(lines_path):
            print(f"     Corrupt export detected. Checking for locked lines fallback...")
            locked_pattern = os.path.join(event_dir,
                                          f"M{module_id}E{event}_locked_lines_v*.json")
            locked_files = sorted(glob.glob(locked_pattern))
            if locked_files:
                lines_path = locked_files[-1]
                print(f"     Falling back to: {os.path.basename(lines_path)}")
                try:
                    with open(lines_path) as f:
                        lines_data = json.load(f)
                except Exception:
                    print(f"  ❌ Fallback also failed. Cannot proceed.")
                    return 1
            else:
                return 1
        else:
            return 1

    if not isinstance(lines_data, list) or len(lines_data) == 0:
        print(f"  ❌ Lines JSON is empty or not an array: {os.path.basename(lines_path)}")
        return 1

    # Check that lines have the required 'image' field (scramble prevention)
    lines_missing_image = [i for i, ln in enumerate(lines_data)
                           if not ln.get("image")]
    if lines_missing_image:
        print(f"  ⚠️  {len(lines_missing_image)} line(s) missing 'image' field "
              f"in {os.path.basename(lines_path)}.")
        print(f"     Lines: {lines_missing_image}")
        print(f"     The builder will fall back to speaker-based assignment")
        print(f"     for those lines (risk of scrambling).")

    # Sanity check: does this export look like it belongs to this module/event?
    # (Fix: adversarial audit — wrong-module export in same folder)
    if lines_data:
        # Check if any lines reference speakers/images that are wildly different
        # from what we'd expect. We can't know the "right" speakers without
        # reading the skeleton, but we CAN check if the file has the basic
        # structure: speaker, text, image fields on every line.
        malformed = [i for i, ln in enumerate(lines_data)
                     if not isinstance(ln, dict)
                     or "speaker" not in ln
                     or "text" not in ln]
        if malformed:
            print(f"  ❌ Lines JSON has {len(malformed)} malformed line(s) "
                  f"(missing speaker/text fields).")
            print(f"     This file may not be a valid storyboard export.")
            print(f"     Lines: {malformed}")
            return 1

    # Record mtime for race condition detection (Fix: adversarial audit #3)
    lines_mtime = os.path.getmtime(lines_path)

    # Identify source type for logging
    lines_basename = os.path.basename(lines_path)
    if "locked_lines" in lines_basename:
        source_label = "locked"
    elif "storyboard_sequence" in lines_basename:
        source_label = "export"
    else:
        source_label = "unknown"

    # If using an export over a locked file, warn — the export may be stale
    if source_label == "export":
        locked_pattern = os.path.join(event_dir,
                                      f"M{module_id}E{event}_locked_lines_v*.json")
        locked_files = sorted(glob.glob(locked_pattern))
        if locked_files:
            locked_basename = os.path.basename(locked_files[-1])
            print(f"  📋 Using browser export (newer than {locked_basename})")
            print(f"     If this is wrong, delete the export or re-save the locked file.")

    print(f"  📝 Lines JSON: {lines_basename} "
          f"({len(lines_data)} lines, source: {source_label})")

    # ------------------------------------------------------------------
    # 3. Find latest existing storyboard HTML (for regression audit)
    # ------------------------------------------------------------------
    previous_html, current_version = _find_latest_storyboard(event_dir)
    next_version = current_version + 1

    if previous_html:
        print(f"  📊 Previous version: {os.path.basename(previous_html)} "
              f"(will audit for regressions)")
    else:
        print(f"  📊 No previous storyboard found — first build.")

    # ------------------------------------------------------------------
    # 4. Determine output path
    # ------------------------------------------------------------------
    output_path = os.path.join(event_dir, f"storyboard_v{next_version}.html")
    print(f"  📄 Output: storyboard_v{next_version}.html")

    # ------------------------------------------------------------------
    # 5. Call build_storyboard.py --registry
    # ------------------------------------------------------------------
    builder_script = os.path.join(TOOLS_DIR, "build_storyboard.py")
    if not os.path.exists(builder_script):
        print(f"  ❌ Builder not found: {builder_script}")
        return 1

    cmd = [
        sys.executable, builder_script,
        "--registry",
        "--module", f"M{module_id}",
        "--event", str(event),
        "--lines", lines_path,
        "--output", output_path,
        "--title", f"Event {event}: M{module_id} "
                   f"{CREATURE_NAMES.get(module_id, '')}",
        "--subtitle", f"Built by pipeline v{next_version}",
    ]

    # Add image-base path — registry stores paths relative to PROJECT root
    # (e.g., "Cropper/file.png", "Production/Event_1/gemini_stills/file.png")
    cmd.extend(["--image-base", PROJECT_DIR])

    # Add audit-previous if a prior version exists
    if previous_html:
        cmd.extend(["--audit-previous", previous_html])

    # Race condition check: verify lines JSON hasn't changed since we read it
    if os.path.getmtime(lines_path) != lines_mtime:
        print(f"  ❌ Lines JSON was modified while preparing build. Aborting.")
        print(f"     File: {os.path.basename(lines_path)}")
        print(f"     Re-run this step to use the updated file.")
        return 1

    print(f"\n  🔨 Running builder...")
    print(f"     {' '.join(os.path.basename(c) for c in cmd[:3])} "
          f"--registry --module M{module_id} --event {event} ...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_DIR,
        )
    except subprocess.TimeoutExpired:
        print(f"  ❌ Builder timed out after 120 seconds.")
        return 1
    except OSError as e:
        print(f"  ❌ Failed to launch builder: {e}")
        return 1

    # Print builder output (indented)
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            print(f"     {line}")
    if result.stderr:
        for line in result.stderr.strip().split("\n"):
            print(f"     [stderr] {line}")

    # ------------------------------------------------------------------
    # 6. Check for regression failures
    # ------------------------------------------------------------------
    build_output = (result.stdout or "") + (result.stderr or "")

    if result.returncode != 0:
        print(f"\n  ❌ Builder exited with code {result.returncode}.")
        print(f"     Storyboard NOT built. Check errors above.")
        return 1

    # Check if the output file was actually created
    if not os.path.exists(output_path):
        print(f"\n  ❌ Builder reported success but output file not found:")
        print(f"     {output_path}")
        return 1

    # Check for regression warnings in builder output.
    # IMPORTANT: Match the EXACT builder output format to avoid false positives.
    # The builder prints "FEATURE REGRESSIONS DETECTED" on failure and
    # "no regressions detected" on success — naive substring "REGRESSION"
    # would match BOTH. (Fix: adversarial audit #1)
    has_regressions = ("FEATURE REGRESSIONS DETECTED" in build_output
                       or "IMAGE ASSIGNMENTS CHANGED" in build_output)

    if has_regressions:
        print(f"\n  🔴 REGRESSION DETECTED in builder output!")
        print(f"     The rebuilt storyboard may have scrambled images or")
        print(f"     lost features compared to v{current_version}.")
        print(f"     Output saved as v{next_version} but NOT marked approved.")
        print(f"     Review the output above, then either:")
        print(f"       - Fix and re-run this step")
        print(f"       - Or manually approve if the change was intentional")

        # Log the regression but don't update dashboard status to approved
        try:
            client.log_activity(module_id, "storyboard_build_regression", {
                "version": next_version,
                "previous_version": current_version,
                "output_file": os.path.basename(output_path),
                "lines_source": os.path.basename(lines_path),
                "approved_images": len(approved),
            })
        except Exception as e:
            print(f"  ⚠️  Failed to log regression activity: {e}")

        # Still update tracking fields — but status is needs_review, not approved
        try:
            module = state["module"]
            if module.get("id"):
                client.update("prod_modules", module["id"], {
                    "storyboard_status": "needs_review",
                    "storyboard_version": next_version,
                    "storyboard_built_at": datetime.now(timezone.utc).isoformat(),
                    "storyboard_build_mode": "registry",
                })
        except Exception as e:
            print(f"  ⚠️  Failed to update dashboard: {e}")
            print(f"     Storyboard file exists on disk but metadata is out of sync.")

        return 1  # Fail the step — regressions must be resolved

    # ------------------------------------------------------------------
    # 7. Success — update Directus dashboard
    # ------------------------------------------------------------------
    output_size = os.path.getsize(output_path)
    print(f"\n  ✅ Storyboard v{next_version} built successfully "
          f"({output_size:,} bytes)")

    # Wrap dashboard updates in try/except to prevent silent desync
    # (Fix: adversarial audit #2 — file exists but metadata fails)
    try:
        module = state["module"]
        if module.get("id"):
            client.update("prod_modules", module["id"], {
                "storyboard_status": "built",
                "storyboard_version": next_version,
                "storyboard_built_at": datetime.now(timezone.utc).isoformat(),
                "storyboard_build_mode": "registry",
            })
    except Exception as e:
        print(f"  ⚠️  Dashboard update failed: {e}")
        print(f"     Storyboard v{next_version} exists on disk but metadata is out of sync.")
        print(f"     Re-run this step or manually update prod_modules.")
        return 1

    # ------------------------------------------------------------------
    # 8. Log activity
    # ------------------------------------------------------------------
    try:
        client.log_activity(module_id, "storyboard_built", {
            "version": next_version,
            "previous_version": current_version if previous_html else None,
            "output_file": os.path.basename(output_path),
            "lines_source": os.path.basename(lines_path),
            "lines_count": len(lines_data),
            "approved_images": len(approved),
            "file_size_bytes": output_size,
            "regressions": "none",
            "build_mode": "registry",
        })
    except Exception as e:
        print(f"  ⚠️  Activity log failed: {e}")
        print(f"     Build succeeded and dashboard updated, but activity not logged.")

    print(f"  📋 Dashboard updated: storyboard_status=built, version={next_version}")

    # Signal output file for QA validation gate
    state["_output_file"] = output_path
    return 0


def _find_lines_json(event_dir, module_id, event):
    """Find the best available lines JSON for a module/event.

    Uses NEWEST-WINS logic: compares the most recent locked lines file
    against the most recent browser-exported sequence file. Whichever
    was modified more recently is used. This means Kim can edit in the
    browser, export, and the pipeline automatically picks up her changes
    without anyone needing to manually copy/rename the export.

    Candidates:
    - M{m}E{e}_locked_lines_v*.json (canonical locked exports)
    - storyboard_sequence_*.json (Kim's browser exports)

    Returns (path, source_type) tuple or (None, None) if nothing found.
    source_type is "locked" or "export" for logging purposes.
    """
    if not os.path.isdir(event_dir):
        return None

    # Find best candidate from each type
    best_locked = None
    best_export = None

    # Locked lines: highest version number
    locked_pattern = os.path.join(event_dir,
                                  f"M{module_id}E{event}_locked_lines_v*.json")
    locked_files = sorted(glob.glob(locked_pattern))
    if locked_files:
        best_locked = locked_files[-1]

    # Browser exports: most recent by mtime
    seq_pattern = os.path.join(event_dir, "storyboard_sequence_*.json")
    seq_files = glob.glob(seq_pattern)
    if seq_files:
        seq_files.sort(key=os.path.getmtime, reverse=True)
        best_export = seq_files[0]

    # Newest-wins: compare mtimes
    if best_locked and best_export:
        locked_mtime = os.path.getmtime(best_locked)
        export_mtime = os.path.getmtime(best_export)
        if export_mtime > locked_mtime:
            # Kim exported something newer than the locked file
            return best_export
        else:
            return best_locked
    elif best_locked:
        return best_locked
    elif best_export:
        return best_export

    return None


def _find_latest_storyboard(event_dir):
    """Find the latest storyboard HTML and its version number.

    Returns (path, version_number) or (None, 0) if none found.
    """
    if not os.path.isdir(event_dir):
        return None, 0

    pattern = os.path.join(event_dir, "storyboard_v*.html")
    matches = glob.glob(pattern)

    if not matches:
        return None, 0

    # Extract version numbers — handle storyboard_v10.html, storyboard_v2.html, etc.
    versioned = []
    for path in matches:
        basename = os.path.basename(path)
        # Skip variants like storyboard_v6_base.html
        if "_base" in basename or "_backup" in basename:
            continue
        # Extract version number from storyboard_vN.html
        try:
            v_part = basename.replace("storyboard_v", "").replace(".html", "")
            version = int(v_part)
            versioned.append((version, path))
        except ValueError:
            continue

    if not versioned:
        return None, 0

    versioned.sort(key=lambda x: x[0])
    highest_version, highest_path = versioned[-1]
    return highest_path, highest_version


def _step_voice_stem(client, state, module_id, event):
    """Generate Phase B voice stem."""
    print("  🎤 Voice Stem — Not yet implemented (Phase 3).")
    print("     Use the audio-producer skill in Cowork for now.")
    return 0


def _step_cue_points(client, state, module_id, event):
    """Extract cue points via Vosk STT."""
    print("  📍 Cue Point Extraction — Not yet implemented (Phase 4).")
    print("     Use the audio-producer skill in Cowork for now.")
    return 0


def _step_mix(client, state, module_id, event):
    """Mix Phase B audio via ffmpeg."""
    print("  🎵 Audio Mixing — Not yet implemented (Phase 4).")
    print("     Use the audio-producer skill in Cowork for now.")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_next_stage(current):
    """Get the next stage after current, or None if at end."""
    try:
        idx = STAGE_ORDER.index(current)
        return STAGE_ORDER[idx + 1] if idx + 1 < len(STAGE_ORDER) else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="MindfulNest Production Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pipeline.py --smoke-test                           Test all API connections
  pipeline.py --list                                 Show all modules
  pipeline.py --module M1 --event 1 --status         Detailed module status
  pipeline.py --module M1 --event 1 --run            Run next automated step
  pipeline.py --module M1 --event 1 --run --step tts Run specific sub-step
  pipeline.py --module M1 --event 1 --approve        Approve hard gate
        """
    )

    parser.add_argument("--module", type=str, help="Module ID (M1, M2, ...)")
    parser.add_argument("--event", type=int, help="Event number (1, 2, ...)")
    parser.add_argument("--status", action="store_true", help="Show detailed module status")
    parser.add_argument("--run", action="store_true", help="Run next automated stage")
    parser.add_argument("--step", type=str, help="Specific sub-step to run (with --run)")
    parser.add_argument("--approve", action="store_true", help="Approve current hard gate")
    parser.add_argument("--smoke-test", action="store_true", help="Test all API connections")
    parser.add_argument("--list", action="store_true", help="List all modules and stages")
    parser.add_argument("--skip-validators", action="store_true",
                        help="Emergency bypass: skip QA validators after sub-steps")
    parser.add_argument("--validate", type=str,
                        help="Run validators on a specific file or directory")

    args = parser.parse_args()

    # Load credentials
    try:
        creds = load_credentials()
    except ValueError as e:
        print(f"❌ {e}")
        return 1

    # Create Directus client
    client = DirectusClient(
        creds["directus_url"],
        creds["directus_email"],
        creds["directus_password"]
    )

    # Set global validator bypass flag
    global SKIP_VALIDATORS
    SKIP_VALIDATORS = args.skip_validators

    # Standalone validate command (no Directus needed)
    if args.validate:
        if not VALIDATORS_AVAILABLE:
            print("❌ Validators not available (import error)")
            return 1
        target = args.validate
        if os.path.isdir(target):
            results = validate_directory(target)
            print(calibration_report(results))
        else:
            result = validate_artifact(target)
            print(result.summary())
        return 0

    # Dispatch commands
    if args.smoke_test:
        return cmd_smoke_test(client, creds)

    if args.list:
        return cmd_list(client)

    # All other commands require --module
    if not args.module:
        parser.print_help()
        return 1

    module_id = parse_module_id(args.module)
    if module_id is None:
        print(f"❌ Cannot parse module ID: '{args.module}'")
        print(f"   Expected format: M1, M2, m3, arc1_m4, or just 1")
        return 1

    event = args.event or 1  # Default to event 1

    if args.status:
        return cmd_status(client, module_id, event)
    elif args.approve:
        return cmd_approve(client, module_id, event)
    elif args.run:
        return cmd_run(client, module_id, event, args.step)
    else:
        # Default: show status
        return cmd_status(client, module_id, event)


if __name__ == "__main__":
    sys.exit(main())
