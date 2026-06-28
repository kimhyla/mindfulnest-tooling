"""Beat Gen speak beats — Kling V2 Avatar Pro contract (still + ElevenLabs audio).

Shared by ``arlo_avatar_beat_pipeline.py`` and budget preflight in ``background.py``.
"""
from __future__ import annotations

import re
from pathlib import Path

from phase_b_avatar_lipsync import AVATAR_PRO_PROHIBIT, AVATAR_USD_PER_SEC, estimate_avatar_pro_usd

KLING_O3_MODE_AVATAR = "o3_avatar_pro_v1"
O3_OPTION_SOURCE_AVATAR = "kling_o3_avatar_pro"

_CONTINUITY_PARA = re.compile(r"^\s*Continuity:", re.IGNORECASE)
_CONTINUITY_BODY = re.compile(
    r"\bhas just heard\b|\bBefore speaking\b|\bdelivers the line\b|\bhas just witnessed\b",
    re.IGNORECASE,
)
_SPEAKS_CLAUSE = re.compile(r"\bspeaks(?:\s+in|\s*:|\s+warmly)?\b", re.IGNORECASE)

_SKIP_STAGING_LINE = re.compile(
    r"^(?:"
    r"match the natural lighting"
    r"|match .+ character appearance"
    r"|only .+ is visible"
    r"|children's illustrated"
    r"|audio:"
    r")",
    re.IGNORECASE,
)


def _ref_path(value) -> Path:
    if isinstance(value, dict):
        return Path(value.get("abs_path") or value.get("path") or value.get("local_path") or "")
    return Path(value or "")


def resolve_beat_avatar_still(beat: dict) -> Path:
    """Portrait still from beat ``reference_image`` (operator-locked char ref)."""
    still = _ref_path(beat.get("reference_image")).expanduser().resolve()
    if not still.is_file():
        raise FileNotFoundError(f"character reference_image missing: {still}")
    return still


def prepare_avatar_pro_audio(audio_path: Path) -> tuple[Path, float, float]:
    """Pad Beat Gen Avatar Pro audio (+0.5s lead, +2.5s tail) before WaveSpeed submit.

    Returns ``(path_for_submit, spoken_duration_s, padded_duration_s)``. When padding
    applies, ``path_for_submit`` is a temp file the caller must delete after submit.
    """
    from lipsync_sender import LIPSYNC_PAD_END, LIPSYNC_PAD_START, pad_audio_for_lipsync  # noqa: WPS433

    audio_path = Path(audio_path).expanduser().resolve()
    spoken_duration_s = _probe_audio_duration_s(audio_path)
    padded_path = pad_audio_for_lipsync(audio_path)
    if padded_path.resolve() == audio_path.resolve():
        padded_duration_s = spoken_duration_s
    else:
        padded_duration_s = _probe_audio_duration_s(padded_path)
    return padded_path, spoken_duration_s, padded_duration_s


def _probe_audio_duration_s(path: Path) -> float:
    import subprocess

    try:
        raw = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            text=True,
            timeout=30,
        ).strip()
        return round(float(raw or 0), 3)
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0.0


def avatar_pro_padding_metadata(*, spoken_duration_s: float, padded_duration_s: float) -> dict:
    """Sidecar fields documenting Avatar Pro lipsync padding applied before submit."""
    from lipsync_sender import LIPSYNC_PAD_END, LIPSYNC_PAD_START  # noqa: WPS433

    return {
        "kling_o3_voice_fix_audio_padding_start_s": LIPSYNC_PAD_START,
        "kling_o3_voice_fix_audio_padding_end_s": LIPSYNC_PAD_END,
        "kling_o3_voice_fix_audio_spoken_duration_s": round(spoken_duration_s, 3),
        "kling_o3_voice_fix_audio_padded_duration_s": round(padded_duration_s, 3),
        "kling_o3_voice_fix_audio_padding_applied": padded_duration_s > spoken_duration_s + 0.05,
    }


def _rewrite_image_refs(text: str, character_label: str) -> str:
    return (
        text.replace("@Image1", character_label)
        .replace("@Image2", "the background scene")
    )


def _strip_o3_avatar_source(prompt: str, *, display: str, speaker: str) -> str:
    """Remove dialogue/audio/header lines; rewrite @Image refs — never strip mid-line."""
    text = (prompt or "").strip()
    text = re.sub(r"^@Image1[^\n]*\n?", "", text, flags=re.MULTILINE)
    kept_lines: list[str] = []
    for line in text.splitlines():
        if _CONTINUITY_PARA.match(line.strip()):
            continue
        kept_lines.append(line)
    text = "\n".join(kept_lines)
    for label in (display, (speaker or "").strip()):
        if not label:
            continue
        text = re.sub(
            rf"{re.escape(label)} speaks[^\n]*",
            "",
            text,
            flags=re.IGNORECASE,
        )
    text = re.sub(r"Audio:.*", "", text, flags=re.DOTALL)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _rewrite_image_refs(text, display).strip()


def _paragraphs(text: str) -> list[str]:
    out: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        para = " ".join(line.strip() for line in block.splitlines() if line.strip())
        if para:
            out.append(para)
    return out


def _normalize_scene_phrase(para: str, *, display: str) -> str:
    """Pose/staging words only — drop dialogue and continuity narration."""
    scene = re.sub(rf"^{re.escape(display)}\s+", "", para, flags=re.IGNORECASE)
    scene = re.sub(r'"[^"]*"', "", scene)
    scene = re.sub(r"'[^']*'", "", scene)
    scene = _SPEAKS_CLAUSE.split(scene, maxsplit=1)[0]
    scene = re.sub(r"^(?:She|He)\s+", "", scene, flags=re.IGNORECASE)
    scene = re.sub(r"\s+", " ", scene).strip(" ,.;")
    return scene


def _extract_scene_staging(cleaned: str, *, display: str) -> str:
    """Pose/setting paragraph from the O3 box — not continuity, identity, or style locks."""
    for para in _paragraphs(cleaned):
        if _CONTINUITY_PARA.search(para) or _CONTINUITY_BODY.search(para):
            continue
        if _SKIP_STAGING_LINE.search(para):
            continue
        scene = _normalize_scene_phrase(para, display=display)
        if len(scene) >= 12:
            return scene
    return "speaks warmly in the storybook scene"


def _extract_style_clause(cleaned: str) -> str:
    for para in _paragraphs(cleaned):
        low = para.lower()
        if low.startswith("children's illustrated") or "storybook style" in low:
            return para
    return ""


def _avatar_tripod_lock(display: str) -> str:
    """Phase-B parity: named character motion + frozen background (same API contract)."""
    return (
        "TRIPOD LOCK — absolutely static camera: zero pan, zero zoom, zero dolly, zero tilt, "
        "zero Ken Burns. The ENTIRE background is frozen and unmoving for the full clip — "
        "no rippling, warping, or morphing. "
        f"Only {display} moves: natural lip sync to the audio, soft blinks, subtle breathing, "
        "small hand gestures. No new objects appear. No pop-in props. No background hallucinations."
    )


def _avatar_single_image_lighting_lock(display: str) -> str:
    """Portrait Avatar Pro — lighting from the one input still (no @Image2 dual-ref lock)."""
    return (
        f"Preserve the exact lighting, warm golden color temperature, and soft shadow depth "
        f"from the input portrait of {display}. The character must look naturally present in the "
        f"frozen backdrop, not pasted on or separately relit. No rim-light mismatch."
    )


def build_avatar_beat_prompt(beat: dict, *, speaker: str) -> str:
    """Avatar Pro prompt — Phase-B-shaped contract with O3 pose/style + full fidelity locks."""
    import kling_character_registry as reg  # noqa: WPS433
    from beat_generator import KLING_O3_IDENTITY_LOCK  # noqa: WPS433

    display = reg.kling_image1_speaker_label(speaker)
    raw = (beat.get("kling_o3_prompt") or "").strip()
    cleaned = _strip_o3_avatar_source(raw, display=display, speaker=speaker)
    scene = _extract_scene_staging(cleaned, display=display)
    style = _extract_style_clause(cleaned)
    identity = _rewrite_image_refs(KLING_O3_IDENTITY_LOCK, display)

    parts = [
        f"{display} {scene}, speaking warmly to camera.",
        _avatar_tripod_lock(display),
    ]
    if style:
        parts.append(style)
    parts.extend([identity, _avatar_single_image_lighting_lock(display), AVATAR_PRO_PROHIBIT])
    return " ".join(parts)


def encode_avatar_pro_delivery(src: Path, dst: Path | None = None) -> tuple[Path, dict]:
    """Kid-facing delivery — same choke point as Phase A/B module lipsync (TECH_SPEC §4.2).

    Beat Gen Avatar Pro must not fork delivery encode; ``finalize_phase_module_lipsync_delivery``
    is the single ``voice_first_upscale`` + sharpen contract for all Avatar Pro outputs.
    """
    import shutil

    from phase_module_lipsync_delivery import finalize_phase_module_lipsync_delivery

    src = Path(src).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"avatar raw missing: {src}")
    out = Path(dst).expanduser().resolve() if dst else src.with_name(f"{src.stem}_delivery.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.resolve() != src.resolve():
        shutil.copy2(src, out)
    meta = finalize_phase_module_lipsync_delivery(out, sharpen=True)
    return out, meta


__all__ = [
    "AVATAR_PRO_PROHIBIT",
    "AVATAR_USD_PER_SEC",
    "KLING_O3_MODE_AVATAR",
    "O3_OPTION_SOURCE_AVATAR",
    "avatar_pro_padding_metadata",
    "build_avatar_beat_prompt",
    "encode_avatar_pro_delivery",
    "estimate_avatar_pro_usd",
    "prepare_avatar_pro_audio",
    "resolve_beat_avatar_still",
]
