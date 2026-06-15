"""Durable lock: speed-audition lines → Element create-voice sample text.

Prevents setup_all_kling_character_voices.py from baking a different MP3 than
Kim heard in the speed ladder (audition_line in JSON vs --line mismatch).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kling_element_voice import ELEVENLABS_VOICE_ROSTER, MIN_SAMPLE_S, MAX_SAMPLE_S

# Representative Beat Gen lines for create-voice (5–30s target). Not calm intros.
DEFAULT_ELEMENT_SAMPLE_LINES: dict[str, list[str]] = {
    "Chipper": [
        "Ready? Just focus on the Teleport Glass. Here we go!",
        "Alright Kiddo. Let's teleport to the Wizarding School and see.",
        "Well, I know some super smart people who have lots of faith in this kid.",
    ],
    "Arlo": [
        "Well maybe we can help. I'm Arlo, assistant to the Great Wizard.",
        "Alright Kiddo. I bet the Great Wizard can teach you a magic spell to help Tessa.",
        "We just have to teleport to the Wizarding School for your first lesson.",
    ],
    "Tessa": [
        "Oh ... hi. I'm Tessa.",
        "....that's awesome",
        "Well.... Do you think she can really help?",
    ],
    "Lorelai": [
        "Fascinating! The patterns match exactly!",
        "Wait — look at this! The nest stones are glowing!",
        "I think I know what the Great Wizard meant!",
    ],
}

SESSION_FILENAME = "session.json"


def default_element_sample_lines(char_name: str, audition_line: str) -> list[str]:
    """Lines for create-voice MP3: char defaults, else single audition line."""
    defaults = DEFAULT_ELEMENT_SAMPLE_LINES.get(char_name)
    if defaults:
        return list(defaults)
    line = (audition_line or "").strip()
    return [line] if line else []


def join_element_sample_lines(lines: list[str]) -> str:
    parts = [str(x).strip() for x in lines if str(x).strip()]
    if not parts:
        return ""
    return " ... ".join(parts)


def resolve_element_sample_lines(char_name: str, cfg: dict) -> list[str]:
    """Authoritative lines for create-voice — lock wins over legacy audition_line."""
    direct = cfg.get("element_sample_lines")
    if isinstance(direct, list):
        parts = [str(x).strip() for x in direct if str(x).strip()]
        if parts:
            return parts

    lock = cfg.get("voice_sample_lock") or {}
    locked = lock.get("element_sample_lines")
    if isinstance(locked, list):
        parts = [str(x).strip() for x in locked if str(x).strip()]
        if parts:
            return parts

    locked_text = (lock.get("element_sample_text") or cfg.get("element_sample_text") or "").strip()
    if locked_text:
        return [locked_text]

    audition = (cfg.get("audition_line") or "").strip()
    if audition:
        return default_element_sample_lines(char_name, audition)

    return default_element_sample_lines(char_name, "")


def resolve_element_sample_text(char_name: str, cfg: dict) -> str:
    text = join_element_sample_lines(resolve_element_sample_lines(char_name, cfg))
    if len(text) < 20:
        text = f"{text} [pause] This is how I sound when I speak in Everdale."
    return text


def sample_text_fingerprint(char_name: str, sample_text: str) -> str:
    roster = ELEVENLABS_VOICE_ROSTER.get(char_name) or {}
    speed = float(roster.get("speed") or 1.0)
    payload = f"{char_name}|{speed:.4f}|{sample_text.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def write_audition_session(
    out_dir: Path,
    *,
    char_name: str,
    audition_line: str,
    element_sample_lines: list[str],
    speeds: list[float],
    roster_speed: float,
) -> Path:
    """Persist session.json beside speed ladder MP3s."""
    out_dir.mkdir(parents=True, exist_ok=True)
    element_text = resolve_element_sample_text(char_name, {
        "element_sample_lines": element_sample_lines,
    })
    session = {
        "schema_version": 1,
        "character": char_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "session_id": out_dir.name,
        "audition_line": audition_line,
        "element_sample_lines": element_sample_lines,
        "element_sample_text": element_text,
        "speeds": speeds,
        "roster_speed_at_session": roster_speed,
        "sample_text_fingerprint": sample_text_fingerprint(char_name, element_text),
    }
    path = out_dir / SESSION_FILENAME
    path.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_audition_session(session_dir: Path) -> dict:
    path = session_dir / SESSION_FILENAME
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing {SESSION_FILENAME} in {session_dir} — re-run speed audition first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def apply_voice_sample_lock(
    char_name: str,
    cfg: dict,
    *,
    locked_speed: float,
    audition_line: str,
    element_sample_lines: list[str],
    session_id: str,
) -> dict:
    """Write lock fields onto character cfg (caller saves character_subjects.json)."""
    element_text = join_element_sample_lines(element_sample_lines)
    if len(element_text) < 20:
        raise ValueError(
            f"element_sample_lines for {char_name} too short ({len(element_text)} chars) — "
            "need ≥20 for create-voice."
        )
    fp = sample_text_fingerprint(char_name, resolve_element_sample_text(char_name, {
        "element_sample_lines": element_sample_lines,
    }))
    updated = dict(cfg)
    updated["audition_line"] = audition_line
    updated["audition_speed"] = locked_speed
    updated["element_sample_lines"] = list(element_sample_lines)
    updated["element_sample_text"] = element_text
    updated["voice_sample_lock"] = {
        "schema_version": 1,
        "session_id": session_id,
        "audition_line": audition_line,
        "element_sample_lines": list(element_sample_lines),
        "element_sample_text": element_text,
        "locked_speed": locked_speed,
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "sample_text_fingerprint": fp,
    }
    return updated


def lock_from_session(
    char_name: str,
    cfg: dict,
    session: dict,
    locked_speed: float,
) -> dict:
    return apply_voice_sample_lock(
        char_name,
        cfg,
        locked_speed=locked_speed,
        audition_line=str(session.get("audition_line") or "").strip(),
        element_sample_lines=list(session.get("element_sample_lines") or []),
        session_id=str(session.get("session_id") or session.get("created_at") or "unknown"),
    )


def validate_lock_before_register(char_name: str, cfg: dict) -> list[str]:
    """Return human-readable errors; empty = OK to spend WaveSpeed on --force."""
    errors: list[str] = []
    lock = cfg.get("voice_sample_lock") or {}
    if not lock:
        errors.append(
            f"{char_name}: no voice_sample_lock — run audition, pick speed, then "
            f"audition_character_voice_speed.py --char {char_name} --lock-speed <speed> "
            f"--from-dir <speed_compare_dir>"
        )
        return errors

    roster = ELEVENLABS_VOICE_ROSTER.get(char_name) or {}
    roster_speed = float(roster.get("speed") or 0)
    locked_speed = float(lock.get("locked_speed") or cfg.get("audition_speed") or 0)
    if abs(roster_speed - locked_speed) > 0.005:
        errors.append(
            f"{char_name}: roster speed {roster_speed} ≠ locked speed {locked_speed} — "
            "update kling_element_voice.py ELEVENLABS_VOICE_ROSTER then re-lock."
        )

    expected_text = resolve_element_sample_text(char_name, cfg)
    expected_fp = sample_text_fingerprint(char_name, expected_text)
    stored_fp = lock.get("sample_text_fingerprint")
    if stored_fp and stored_fp != expected_fp:
        errors.append(
            f"{char_name}: sample_text_fingerprint mismatch — element_sample_lines or "
            "roster speed changed since lock; re-run --lock-speed from latest session."
        )

    audition_line = (lock.get("audition_line") or "").strip()
    element_lines = lock.get("element_sample_lines") or []
    if not element_lines:
        errors.append(f"{char_name}: voice_sample_lock missing element_sample_lines.")

    # Audition line must appear in element mix OR be the sole line (other chars).
    if audition_line and element_lines and audition_line not in element_lines:
        joined = join_element_sample_lines(element_lines)
        if audition_line not in joined:
            errors.append(
                f"{char_name}: speed audition line is not represented in "
                "element_sample_lines — Kim's pick may not match create-voice MP3."
            )

    return errors


def stored_sample_matches_lock(char_name: str, cfg: dict, sample_path: Path, duration_s: float) -> bool:
    lock = cfg.get("voice_sample_lock") or {}
    if not lock:
        return True
    expected_fp = lock.get("sample_text_fingerprint")
    if not expected_fp:
        return True
    current_fp = sample_text_fingerprint(char_name, resolve_element_sample_text(char_name, cfg))
    if expected_fp != current_fp:
        return False
    return MIN_SAMPLE_S <= duration_s <= MAX_SAMPLE_S
