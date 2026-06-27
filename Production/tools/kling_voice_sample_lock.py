"""Durable lock: speed-audition lines → Element create-voice sample text.

Prevents setup_all_kling_character_voices.py from baking a different MP3 than
Kim heard in the speed ladder (audition_line in JSON vs --line mismatch).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kling_element_voice import ELEVENLABS_VOICE_ROSTER, MIN_SAMPLE_S, MAX_SAMPLE_S

# eleven_v3 emotion tags use comma-separated descriptors: [warm, gentle]
_ELEVEN_V3_EMOTION_TAG_RE = re.compile(r"\[[^\]]+,\s*[^\]]+\]")

# Representative Beat Gen lines for create-voice (5–30s target). Not calm intros.
# New characters: every line SHOULD include eleven_v3 emotion tags ([warm, gentle]).
DEFAULT_ELEMENT_SAMPLE_LINES: dict[str, list[str]] = {
    "Chipper": [
        "[warm, calm] Ready? Just focus on the Teleport Glass. Here we go!",
        "[encouraging, steady] Alright Kiddo. Let's teleport to the Wizarding School and see.",
        "[confident, warm] Well, I know some super smart people who have lots of faith in this kid.",
    ],
    "Arlo": [
        "[warm, helpful] Well maybe we can help. I'm Arlo, assistant to the Great Wizard.",
        "[upbeat, reassuring] Alright Kiddo. I bet the Great Wizard can teach you a magic spell to help Tessa.",
        "[steady, inviting] We just have to teleport to the Wizarding School for your first lesson.",
    ],
    "Tessa": [
        "[shy, gentle] Oh ... hi. I'm Tessa.",
        "[soft, amazed] ....that's awesome",
        "[wary, hopeful] Well.... Do you think she can really help?",
    ],
    "Lorelai": [
        "[excited, scholarly] Fascinating! The patterns match exactly!",
        "[delighted, breathless] Wait — look at this! The nest stones are glowing!",
        "[confident, warm] I think I know what the Great Wizard meant!",
    ],
    "Luna": [
        "[excited, scholarly] Fascinating! The patterns match exactly!",
        "[curious, bright] Wait — look at this inscription!",
        "[warm, eager] I think I know what the Great Wizard meant!",
    ],
    "Ember": [
        "[warm, gentle] Come here — you don't have to do this alone.",
        "[curious, friendly] Hello there.",
        "[wonder-struck, breathless] I'm Ember — I'm from Foxhollow, down in the valley. [pause] What are you guys doing?",
    ],
    "Bramble": [
        "[steady, reassuring] Steady now — I've got you.",
        "[warm, calm] Easy does it — we'll figure this out together.",
        "[gentle, grounded] You're safe here with us now.",
    ],
    "Benson": [
        "[warm, gentle] It's going to be all right, little one.",
        "[soft, nurturing] You're safe here with us now.",
        "[calm, reassuring] Take a deep breath — we'll figure this out together.",
    ],
    "Bork": [
        "[formal, authoritative] By order of the King, this matter is closed.",
        "[stern, clear] The King's decree stands — there will be no further debate.",
        "[measured, official] Proceed as instructed and keep the peace.",
    ],
    "Oliver": [
        "[warm, gentle] Something wonderful is waiting for us.",
        "[soft, welcoming] The forest has been waiting for someone like you.",
        "[reverent, warm] This wand chooses its keeper — and it chose you.",
    ],
    "Grizzle": [
        "[guarded, cool] Nothing to see here. Move along.",
        "[measured, sly] This area is restricted by order of the King.",
        "[firm, dismissive] Keep walking and don't ask questions.",
    ],
    "Willow": [
        "[serene, warm] The forest remembers what you forget.",
        "[soft, prophetic] Listen closely, child.",
        "[mystical, gentle] The old magic still flows through these trees.",
    ],
    "The King": [
        "[regal, warm] Everdale has need of you.",
        "[commanding, kind] The forest calls to those who listen.",
        "[measured, inviting] Will you answer when the kingdom asks?",
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


def sample_lines_have_emotion_tags(lines: list[str]) -> bool:
    """True when at least one line has an eleven_v3 emotion tag (comma inside brackets)."""
    return any(_ELEVEN_V3_EMOTION_TAG_RE.search(str(line)) for line in lines)


def validate_o3_delivery_lock(char_name: str) -> list[str]:
    """Layer 1: Beat Gen O3 delivery phrase must exist before WaveSpeed spend."""
    from kling_o3_prompt import delivery_for_speaker

    if delivery_for_speaker(char_name):
        return []
    slug = re.sub(r"[^A-Za-z0-9]+", "_", char_name.strip()).strip("_").upper()
    return [
        f"{char_name}: no O3 delivery lock — add KLING_O3_{slug}_VOICE_DELIVERY and "
        f"'_DELIVERY_BY_SPEAKER[\"{char_name}\"]' in Production/tools/kling_o3_prompt.py "
        "(see BEAT_GEN_CHARACTER_ONBOARDING_v1.md step 4a)."
    ]


def has_voice_onboarding_waiver(cfg: dict) -> bool:
    """Explicit opt-out for emotion-tag gate (narrator-only / non-Element edge cases)."""
    waiver = cfg.get("voice_onboarding_waiver")
    if waiver is True:
        return True
    return bool(str(waiver or "").strip())


def validate_emotion_tags_in_sample_lines(char_name: str, cfg: dict) -> list[str]:
    """Layer 2: create-voice sample lines need eleven_v3 emotional direction tags."""
    if has_voice_onboarding_waiver(cfg):
        return []
    lines = resolve_element_sample_lines(char_name, cfg)
    if sample_lines_have_emotion_tags(lines):
        return []
    return [
        f"{char_name}: element_sample_lines need eleven_v3 emotion tags like [warm, gentle] "
        "on at least one line (see VOICE_ROSTER_LOCKED_v2.md and onboarding step 4b), "
        "or set voice_onboarding_waiver on the character entry."
    ]


def is_first_voice_registration(cfg: dict) -> bool:
    """True when character has never completed Element + create-voice registration."""
    return not cfg.get("element_id") or (cfg.get("status") or "").strip().lower() != "active"


def validate_voice_onboarding_before_spend(
    char_name: str,
    cfg: dict,
    *,
    require_emotion_tags: bool = True,
) -> list[str]:
    """All gates that must pass before setup_all_kling_character_voices spends credits."""
    errors = list(validate_lock_before_register(char_name, cfg))
    errors.extend(validate_o3_delivery_lock(char_name))
    if require_emotion_tags:
        errors.extend(validate_emotion_tags_in_sample_lines(char_name, cfg))
    return errors


def validate_roster_voice_onboarding_contract() -> list[str]:
    """CI/deploy: every ElevenLabs roster character has Layer 1 + tagged Layer 2 defaults."""
    from kling_o3_prompt import delivery_for_speaker

    errors: list[str] = []
    for char_name in sorted(ELEVENLABS_VOICE_ROSTER):
        if not delivery_for_speaker(char_name):
            errors.append(
                f"{char_name}: missing O3 delivery lock in kling_o3_prompt.py "
                "(BEAT_GEN_CHARACTER_ONBOARDING_v1.md step 4a)"
            )
        defaults = DEFAULT_ELEMENT_SAMPLE_LINES.get(char_name) or []
        if not defaults:
            errors.append(
                f"{char_name}: missing DEFAULT_ELEMENT_SAMPLE_LINES in kling_voice_sample_lock.py "
                "(step 4b)"
            )
        elif not sample_lines_have_emotion_tags(defaults):
            errors.append(
                f"{char_name}: DEFAULT_ELEMENT_SAMPLE_LINES lack eleven_v3 emotion tags "
                "(step 4b)"
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
