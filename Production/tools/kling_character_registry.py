"""Kling character + voice registry (Elements + ElevenLabs create-voice).

Loads Production/character_subjects.json.
Beat Gen requires active element_id per dialogue speaker (O3 Pro + bound voice).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

_PROD_ROOT: Path | None = None

# Beat Gen speaker aliases → character_subjects.json key
_SPEAKER_REGISTRY_ALIAS: dict[str, str] = {
    "guide bird": "Chipper",
    "chipper": "Chipper",
    "pip": "Chipper",
    "assistant bird": "Chipper",
    "mountain king": "The King",
    "king": "The King",
    "the king": "The King",
    "lady willow": "Willow",
    "grizzle/agent": "Grizzle",
    "agent": "Grizzle",
    "luna": "Lorelai",
}


def prod_root() -> Path:
    global _PROD_ROOT
    if _PROD_ROOT is None:
        here = Path(__file__).resolve()
        _PROD_ROOT = here.parent.parent
    return _PROD_ROOT


def character_subjects_path() -> Path:
    return prod_root() / "character_subjects.json"


def voice_catalog_path() -> Path:
    return prod_root() / "kling_voice_catalog.json"


def audition_dir() -> Path:
    return prod_root() / "kling_voice_audition"


def audition_manifest_path() -> Path:
    return audition_dir() / "manifest.json"


def load_character_subjects() -> dict:
    path = character_subjects_path()
    if not path.is_file():
        return {"characters": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_character_subjects(data: dict) -> None:
    path = character_subjects_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_voice_catalog() -> dict:
    path = voice_catalog_path()
    if not path.is_file():
        return {"voices": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_char_entry(chars: dict, speaker: str) -> dict | None:
    if not speaker:
        return None
    raw = speaker.strip()
    alias = _SPEAKER_REGISTRY_ALIAS.get(raw.lower())
    if alias and alias in chars:
        return chars[alias]
    return (
        chars.get(raw)
        or chars.get(raw.lower())
        or chars.get(raw.title())
        or chars.get(raw.capitalize())
    )


def resolve_registry_key(speaker: str) -> str | None:
    """Return character_subjects.json key for a beat speaker, or None."""
    data = load_character_subjects()
    chars = data.get("characters") or {}
    entry = _resolve_char_entry(chars, speaker)
    if not entry:
        return None
    for key, cfg in chars.items():
        if cfg is entry:
            return key
    return None


def is_speaker_voice_ready(speaker: str) -> bool:
    """True when speaker has active Element + bound Kling voice."""
    return get_element_list_entry(speaker) is not None


def voice_readiness_report() -> dict[str, Any]:
    """Summary for server startup / Beat Gen UI."""
    data = load_character_subjects()
    chars = data.get("characters") or {}
    rows = []
    for name, cfg in chars.items():
        rows.append({
            "character": name,
            "status": cfg.get("status"),
            "element_id": cfg.get("element_id"),
            "kling_voice_id": cfg.get("kling_voice_id"),
            "elevenlabs_voice_name": cfg.get("elevenlabs_voice_name"),
            "ready": cfg.get("status") == "active" and bool(cfg.get("element_id")),
        })
    ready = sum(1 for r in rows if r["ready"])
    return {
        "ready_count": ready,
        "total": len(rows),
        "all_ready": ready == len(rows) and len(rows) > 0,
        "characters": rows,
    }


def get_character_entry(speaker: str) -> dict | None:
    data = load_character_subjects()
    chars = data.get("characters") or {}
    return _resolve_char_entry(chars, speaker)


def get_element_list_entry(speaker: str) -> dict | None:
    """Return element_list payload entry for O3 Pro, or None."""
    entry = get_character_entry(speaker)
    if not entry:
        return None
    if entry.get("status") != "active":
        return None
    eid = entry.get("element_id")
    if not eid:
        return None
    return {
        "element_id": str(eid),
        "element_name": entry.get("element_name") or speaker,
    }


def get_bound_voice_id(speaker: str) -> str | None:
    entry = get_character_entry(speaker)
    if not entry:
        return None
    vid = entry.get("kling_voice_id")
    return str(vid) if vid else None


def get_element_name(speaker: str) -> str | None:
    entry = get_character_entry(speaker)
    if not entry or entry.get("status") != "active" or not entry.get("element_id"):
        return None
    return entry.get("element_name") or speaker


def file_sha256(path: str | Path) -> str | None:
    """Content hash for cross-path Element vs @Image1 alignment checks."""
    p = Path(path)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def element_image_paths(speaker: str) -> list[Path]:
    """Resolved on-disk paths for a character's Element registration images."""
    entry = get_character_entry(speaker)
    if not entry:
        return []
    rels: list[str] = []
    frontal = entry.get("frontal_image")
    if frontal:
        rels.append(str(frontal))
    rels.extend(str(r) for r in (entry.get("refer_images") or []))
    out: list[Path] = []
    root = prod_root()
    for rel in rels:
        candidate = root / rel
        if candidate.is_file():
            out.append(candidate.resolve())
    return out


def char_ref_matches_element_images(char_path: str, speaker: str) -> tuple[bool, str]:
    """True when beat @Image1 file matches an Element image (path or sha256)."""
    if not char_path or not os.path.isfile(char_path):
        return False, "character reference file missing"
    element_paths = element_image_paths(speaker)
    if not element_paths:
        key = resolve_registry_key(speaker) or speaker
        return False, f"no Element images registered for {key!r}"
    norm_char = os.path.normpath(os.path.realpath(char_path))
    for ep in element_paths:
        if norm_char == os.path.normpath(str(ep)):
            return True, ""
    char_hash = file_sha256(char_path)
    if not char_hash:
        return False, "could not hash character reference"
    element_hashes = {file_sha256(p) for p in element_paths}
    element_hashes.discard(None)
    if char_hash in element_hashes:
        return True, ""
    key = resolve_registry_key(speaker) or speaker
    rels = ", ".join(
        str(p.relative_to(prod_root())) if p.is_relative_to(prod_root()) else str(p)
        for p in element_paths[:3]
    )
    return False, (
        f"@Image1 ({Path(char_path).name}) does not match Element images for {key!r} "
        f"({rels}). Pick a library still from the Element set or re-register Element."
    )


def assign_voice(character: str, voice_id: str, voice_label: str | None = None) -> dict:
    data = load_character_subjects()
    chars = data.get("characters") or {}
    key = character
    if key not in chars:
        matches = [k for k in chars if k.lower() == character.lower()]
        if not matches:
            raise KeyError(f"Unknown character: {character!r}")
        key = matches[0]
    catalog = {v["voice_id"]: v for v in load_voice_catalog().get("voices", [])}
    if voice_id in catalog:
        label = voice_label or catalog[voice_id].get("label") or voice_id
    else:
        # Custom create-voice IDs (ElevenLabs path) — not in preset catalog
        label = voice_label or f"custom ({voice_id})"
    chars[key]["kling_voice_id"] = voice_id
    chars[key]["kling_voice_label"] = label
    data["characters"] = chars
    save_character_subjects(data)
    return chars[key]


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip())
    return s.strip("_").lower() or "unknown"


def build_audition_manifest() -> dict[str, Any]:
    """Scan audition_dir/samples and merge with character + catalog metadata."""
    data = load_character_subjects()
    catalog = {v["voice_id"]: v for v in load_voice_catalog().get("voices", [])}
    chars = data.get("characters") or {}
    samples_root = audition_dir() / "samples"
    entries: list[dict] = []
    for char_name, cfg in chars.items():
        char_slug = slugify(char_name)
        char_dir = samples_root / char_slug
        voice_samples: list[dict] = []
        if char_dir.is_dir():
            for mp3 in sorted(char_dir.glob("*.mp3")):
                vid = mp3.stem
                meta = catalog.get(vid, {})
                voice_samples.append({
                    "voice_id": vid,
                    "label": meta.get("label", vid),
                    "tags": meta.get("tags", []),
                    "audio_path": f"Production/{mp3.relative_to(prod_root()).as_posix()}",
                })
        entries.append({
            "character": char_name,
            "audition_line": cfg.get("audition_line", ""),
            "audition_speed": cfg.get("audition_speed", 1.0),
            "selected_voice_id": cfg.get("kling_voice_id"),
            "selected_voice_label": cfg.get("kling_voice_label"),
            "element_id": cfg.get("element_id"),
            "element_status": cfg.get("status"),
            "samples": voice_samples,
        })
    return {
        "schema_version": 1,
        "characters": entries,
        "catalog": load_voice_catalog().get("voices", []),
    }
