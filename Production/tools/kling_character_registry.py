"""Kling character + voice registry (Elements + ElevenLabs create-voice).

Loads Production/character_subjects.json.
Beat Gen requires active element_id per dialogue speaker (O3 Pro + bound voice).

Pose / Element model (three stores — keep in sync):
  1. Beat sidecar ``reference_image`` — often Event_*/library/... (user-locked still)
  2. Disk ``Production/<Char>/poses/*.png`` — copies from Add to Element (unbounded)
  3. Registry ``character_subjects.json`` ``refer_images`` — max 3 paths uploaded to Kling

``refer_images`` is the Kling API subset, not a full inventory of poses/. Orphan poses
(files on disk but not in refer_images) caused @Image1 gate failures until reconcile.
Add to Element must always leave the new pose in refer_images after trim.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
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
    "lorelai": "Lorelai",
    "laurel": "Lorelai",
    "loral": "Lorelai",
}

# Kling Element display name "Loral" avoids Laurel/Lorelai naming conflicts and TTS drift.
# Internal registry key, sidecar speaker, and paths stay Lorelai.
_KLING_ELEMENT_DISPLAY_NAME: dict[str, str] = {
    "Lorelai": "Loral",
}


def kling_element_display_name(speaker: str) -> str | None:
    """Name for element_list.element_name and O3 voice/@Image1 lines — not registry keys."""
    entry = get_character_entry(speaker)
    if not entry or entry.get("status") != "active" or not entry.get("element_id"):
        return None
    reg_key = resolve_registry_key(speaker) or (speaker or "").strip()
    if reg_key in _KLING_ELEMENT_DISPLAY_NAME:
        return _KLING_ELEMENT_DISPLAY_NAME[reg_key]
    return entry.get("element_name") or reg_key or speaker


def prod_root() -> Path:
    global _PROD_ROOT
    if _PROD_ROOT is None:
        env = os.environ.get("MN_PROD_ROOT", "").strip()
        if env:
            _PROD_ROOT = Path(env).resolve()
        else:
            here = Path(__file__).resolve()
            _PROD_ROOT = here.parent.parent
    return _PROD_ROOT


def set_prod_root(path: str | Path) -> None:
    """Bind registry paths to runtime Production/ root (Dropbox when server runs)."""
    global _PROD_ROOT
    _PROD_ROOT = Path(path).resolve()


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


def normalize_beat_speaker_for_sidecar(speaker: str) -> str:
    """Canonical sidecar ``speaker`` — registry key, never Kling display name.

    Beat sidecar stores ``Lorelai``; Kling prompts/Elements use ``Loral``.
    Display names must not reach TTS (_resolve_voice_profile) or sidecar rows.
    """
    raw = (speaker or "").strip()
    if not raw:
        return ""
    if raw.startswith("[") and raw.endswith("]"):
        return raw
    reg_key = resolve_registry_key(raw)
    if reg_key:
        return reg_key
    alias = _SPEAKER_REGISTRY_ALIAS.get(raw.lower())
    if alias:
        return alias
    return raw


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


def resolve_proven_o3_bind(entry: dict | None) -> dict[str, str] | None:
    """Return locked Element+voice bind when character carries ``proven_o3_bind``."""
    if not entry or not isinstance(entry, dict):
        return None
    proven = entry.get("proven_o3_bind")
    if not isinstance(proven, dict):
        return None
    element_id = str(proven.get("element_id") or "").strip()
    voice_id = str(proven.get("kling_voice_id") or entry.get("kling_voice_id") or "").strip()
    if not element_id or not voice_id:
        return None
    out: dict[str, str] = {"element_id": element_id, "kling_voice_id": voice_id}
    for key in ("proven_from_beat_id", "proven_element_name"):
        val = str(proven.get(key) or "").strip()
        if val:
            out[key] = val
    return out


def get_proven_element_list_entry(speaker: str) -> dict | None:
    """O3 submit ``element_list`` row from registry ``proven_o3_bind`` contract."""
    entry = get_character_entry(speaker)
    if not entry or entry.get("status") != "active":
        return None
    proven = resolve_proven_o3_bind(entry)
    if not proven:
        return None
    # Single Kling-facing name: display name (registry element_name / _KLING_ELEMENT_DISPLAY_NAME)
    # wins over legacy proven_element_name snapshots so element_list matches @Image1 (Loral).
    element_name = (
        kling_element_display_name(speaker)
        or str(entry.get("element_name") or "").strip()
        or str(proven.get("proven_element_name") or "").strip()
        or speaker
    )
    return {
        "element_id": proven["element_id"],
        "element_name": element_name,
        "voice_id": proven["kling_voice_id"],
    }


def apply_element_id_with_proven_lock(cfg: dict, new_element_id: str, *, source: str) -> dict:
    """Apply Element register result — revert to proven bind when ``lock_element_id`` set."""
    updated = dict(cfg)
    proven = resolve_proven_o3_bind(cfg)
    lock = bool((cfg.get("proven_o3_bind") or {}).get("lock_element_id"))
    if proven and lock and str(new_element_id) != proven["element_id"]:
        if os.environ.get("MN_FORCE_ELEMENT_REREGISTER", "").strip() not in ("1", "true", "yes"):
            updated["element_id"] = proven["element_id"]
            updated["_proven_bind_element_restore"] = {
                "source": source,
                "attempted_element_id": str(new_element_id),
                "restored_element_id": proven["element_id"],
            }
            return updated
    updated["element_id"] = str(new_element_id)
    return updated


def get_element_list_entry(speaker: str) -> dict | None:
    """Return element_list payload entry for O3 Pro, or None."""
    entry = get_character_entry(speaker)
    if not entry:
        return None
    if entry.get("status") != "active":
        return None
    proven = resolve_proven_o3_bind(entry)
    eid = (proven or {}).get("element_id") or entry.get("element_id")
    if not eid:
        return None
    display = kling_element_display_name(speaker) or entry.get("element_name") or speaker
    out: dict[str, str] = {
        "element_id": str(eid),
        "element_name": display,
    }
    vid = (proven or {}).get("kling_voice_id") or entry.get("kling_voice_id")
    if vid:
        out["voice_id"] = str(vid)
    return out


def get_bound_voice_id(speaker: str) -> str | None:
    entry = get_character_entry(speaker)
    if not entry:
        return None
    proven = resolve_proven_o3_bind(entry)
    vid = (proven or {}).get("kling_voice_id") or entry.get("kling_voice_id")
    return str(vid) if vid else None


def kling_image1_speaker_label(speaker: str) -> str:
    """@Image1 header label — Kling display name when Element-bound."""
    display = kling_element_display_name(speaker)
    if display:
        return display
    return (speaker or "Character").strip()


def get_element_name(speaker: str) -> str | None:
    """Kling-facing Element display name (Loral for Lorelai), not registry key."""
    return kling_element_display_name(speaker)


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


def char_ref_aligned_for_intent_commit(char_path: str, speaker: str) -> tuple[bool, str]:
    """Strict alignment for generation-intent commit (no poses-dir false positive)."""
    return char_ref_matches_element_images(
        char_path, speaker, allow_pose_dir_fallback=False,
    )


def char_ref_matches_element_images(
    char_path: str,
    speaker: str,
    *,
    allow_pose_dir_fallback: bool = True,
) -> tuple[bool, str]:
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
    # Library drops often copy bytes into <Char>/poses/ before refer_images catches up.
    if allow_pose_dir_fallback:
        char_key = resolve_registry_key(speaker) or speaker
        if find_pose_rel_by_hash(char_key, char_path):
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


def find_pose_rel_by_hash(char_key: str, char_path: str) -> str | None:
    """Return Production-relative pose path when char ref bytes already exist on disk."""
    root = prod_root()
    char_hash = file_sha256(char_path)
    if not char_hash:
        return None
    poses_dir = root / char_key / "poses"
    if not poses_dir.is_dir():
        return None
    matches: list[str] = []
    for pose in poses_dir.iterdir():
        if not pose.is_file():
            continue
        if file_sha256(pose) == char_hash:
            matches.append(str(pose.relative_to(root)))
    if not matches:
        return None
    matches.sort(key=lambda rel: (len(rel), rel))
    return matches[0]


def reconcile_char_ref_with_element(
    speaker: str,
    char_path: str,
    wavespeed_key: str,
) -> dict[str, Any]:
    """Re-register an on-disk pose onto Element when beat @Image1 bytes match but refer dropped.

    Typical after canonical Element restore: library still matches
    Production/<Char>/poses/<copy>.png but refer_images no longer lists it.
    """
    from tools.kling_element_voice import register_kling_element

    if char_ref_matches_element_images(
        char_path, speaker, allow_pose_dir_fallback=False,
    )[0]:
        entry = get_character_entry(speaker) or {}
        return {
            "ok": True,
            "reconciled": False,
            "element_id": entry.get("element_id"),
        }

    char_key = resolve_registry_key(speaker) or speaker
    if not is_speaker_voice_ready(char_key):
        raise RuntimeError(f"{char_key!r} is not voice-ready")

    rel_pose = find_pose_rel_by_hash(char_key, char_path)
    if not rel_pose:
        raise FileNotFoundError(
            f"No matching pose under {char_key}/poses/ for {Path(char_path).name}"
        )

    data = load_character_subjects()
    chars = data.get("characters") or {}
    cfg = dict(chars[char_key])
    voice_id = cfg.get("kling_voice_id")
    if not voice_id:
        raise RuntimeError(f"{char_key!r} has no kling_voice_id")

    refer = ensure_refer_anchors(
        char_key, [str(r) for r in (cfg.get("refer_images") or [])], cfg,
    )
    if rel_pose not in refer:
        refer.append(rel_pose)
    pin_refs = pinned_refer_paths(cfg, char_key)
    cfg["refer_images"] = trim_refer_images_for_element(
        refer, keep=rel_pose, pin=pin_refs,
    )

    element_id, _prediction_id = register_kling_element(
        char_key, cfg, str(voice_id), wavespeed_key,
    )
    cfg["element_id"] = element_id
    cfg["status"] = "active"
    chars[char_key] = cfg
    data["characters"] = chars
    save_character_subjects(data)

    if not char_ref_matches_element_images(char_path, speaker)[0]:
        raise RuntimeError(
            f"Reconcile failed: {Path(char_path).name} still not in Element set after re-register"
        )

    return {
        "ok": True,
        "reconciled": True,
        "element_id": str(element_id),
        "pose_rel": rel_pose,
        "refer_images": list(cfg.get("refer_images") or []),
    }


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


MAX_ELEMENT_REFER_IMAGES = 3

# Identity anchors that must stay in refer_images when Add to Element trims to 3.
CHARACTER_REFER_ANCHORS: dict[str, tuple[str, ...]] = {
    "Lorelai": (
        "Lorelai/poses/lorelai_explaining.png",
        "Lorelai/poses/lorelai_shocked.png",
    ),
}


def refer_anchor_paths(char_key: str, cfg: dict | None = None) -> list[str]:
    """On-disk canonical refer paths for a character (never evicted on trim)."""
    cfg = cfg or {}
    root = prod_root()
    out: list[str] = []
    seen: set[str] = set()
    for rel in cfg.get("refer_pins") or []:
        rel_s = str(rel)
        if rel_s not in seen and (root / rel_s).is_file():
            seen.add(rel_s)
            out.append(rel_s)
    for rel in CHARACTER_REFER_ANCHORS.get(char_key, ()):
        if rel not in seen and (root / rel).is_file():
            seen.add(rel)
            out.append(rel)
    frontal = str(cfg.get("frontal_image") or "")
    if frontal and frontal not in seen and (root / frontal).is_file():
        out.insert(0, frontal)
    return out


def pinned_refer_paths(cfg: dict, char_key: str = "") -> set[str]:
    """Refer paths that must survive Kling's 3-pose cap (canonical identity anchors)."""
    pins: set[str] = set()
    key = char_key or ""
    for rel in refer_anchor_paths(key, cfg):
        pins.add(rel)
    for rel in cfg.get("refer_images") or []:
        rel_s = str(rel)
        low = rel_s.lower()
        if "canonical" in low or "_explaining" in low or "_shocked" in low:
            pins.add(rel_s)
    return pins


def ensure_refer_anchors(char_key: str, refer: list[str], cfg: dict) -> list[str]:
    """Re-insert canonical emotion refer poses before trim (Add to Element safety)."""
    out = [str(r) for r in refer if r]
    for rel in refer_anchor_paths(char_key, cfg):
        if rel not in out:
            out.insert(0, rel)
    return out


def trim_refer_images_for_element(
    refer: list[str],
    *,
    keep: str | None = None,
    max_count: int = MAX_ELEMENT_REFER_IMAGES,
    pin: set[str] | frozenset[str] | None = None,
) -> list[str]:
    """Kling elements API accepts at most 3 refer_images (frontal is separate).

    Eviction order when over cap: unpinned first, then heuristic pins, then explicit
    refer_pins/anchors. ``keep`` (the pose just added) is never evicted.
    """
    strict_pins = frozenset(pin or ())
    pin_set = set(strict_pins)
    if keep:
        pin_set.add(keep)
    ordered: list[str] = []
    seen: set[str] = set()
    for rel in refer:
        rel_s = str(rel)
        if rel_s and rel_s not in seen:
            seen.add(rel_s)
            ordered.append(rel_s)

    result = list(ordered)
    while len(result) > max_count:
        evict: str | None = None
        for rel in result:
            if keep and rel == keep:
                continue
            if rel not in pin_set:
                evict = rel
                break
        if evict is None:
            for rel in result:
                if keep and rel == keep:
                    continue
                if rel not in strict_pins:
                    evict = rel
                    break
        if evict is None:
            for rel in result:
                if keep and rel == keep:
                    continue
                evict = rel
                break
        if evict is None:
            break
        result.remove(evict)
    return result


def refer_images_contain_path_or_hash(
    refer_rel_paths: list[str],
    char_path: str,
    *,
    frontal_rel: str | None = None,
) -> bool:
    """True when char_path matches any Production-relative refer path by path or sha256."""
    root = prod_root()
    check_paths: list[Path] = []
    for rel in ([frontal_rel] if frontal_rel else []) + list(refer_rel_paths):
        if not rel:
            continue
        p = root / str(rel)
        if p.is_file():
            check_paths.append(p.resolve())
    if not check_paths:
        return False
    norm_char = os.path.normpath(os.path.realpath(char_path))
    for ep in check_paths:
        if norm_char == os.path.normpath(str(ep)):
            return True
    char_hash = file_sha256(char_path)
    if not char_hash:
        return False
    return char_hash in {file_sha256(p) for p in check_paths}


def assert_pose_in_refer_images(
    char_key: str,
    rel_pose: str,
    refer_images: list[str],
    source_abs_path: str | Path,
    *,
    frontal_rel: str | None = None,
) -> None:
    """Raise when Add to Element copied a pose but trim dropped it from Kling refer set."""
    if refer_images_contain_path_or_hash(
        refer_images, str(source_abs_path), frontal_rel=frontal_rel,
    ):
        return
    raise RuntimeError(
        f"Add to Element failed invariant: {Path(source_abs_path).name} was copied to "
        f"{rel_pose} but is not in refer_images after trim ({refer_images!r}). "
        f"Kling Element would reject @Image1 — try removing unused poses or refer_pins."
    )


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip())
    return s.strip("_").lower() or "unknown"


def _unique_pose_dest(char_key: str, source: Path) -> tuple[Path, str]:
    """Return (absolute dest, rel path under Production/) for a new pose PNG."""
    poses_dir = prod_root() / char_key / "poses"
    poses_dir.mkdir(parents=True, exist_ok=True)
    stem = slugify(source.stem) or "pose"
    rel = f"{char_key}/poses/{stem}.png"
    dest = prod_root() / rel
    if dest.is_file():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rel = f"{char_key}/poses/{stem}_{ts}.png"
        dest = prod_root() / rel
    return dest.resolve(), rel


def add_element_pose(
    character: str,
    source_abs_path: str | Path,
    wavespeed_key: str,
) -> dict[str, Any]:
    """Copy a pose PNG into Production/<Char>/poses and re-register Element.

    Preserves the locked kling_voice_id (ElevenLabs clone) but re-uploads Element
    with canonical refer anchors pinned so identity + voice bind stay intact.
    """
    from tools.kling_element_voice import register_kling_element

    source = Path(source_abs_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Pose source missing: {source}")
    if source.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError(f"Pose source must be an image file: {source.name}")

    data = load_character_subjects()
    chars = data.get("characters") or {}
    char_key = character
    if char_key not in chars:
        matches = [k for k in chars if k.lower() == character.lower()]
        if not matches:
            raise KeyError(f"Unknown character: {character!r}")
        char_key = matches[0]
    cfg = dict(chars[char_key])

    if not is_speaker_voice_ready(char_key):
        raise RuntimeError(
            f"{char_key!r} is not voice-ready — run setup_character_voice first."
        )
    voice_id = cfg.get("kling_voice_id")
    if not voice_id:
        raise RuntimeError(f"{char_key!r} has no kling_voice_id — cannot re-register Element.")

    dest, rel_pose = _unique_pose_dest(char_key, source)
    from beat_generator import copy_file_durable

    copy_file_durable(source, dest)

    refer = ensure_refer_anchors(char_key, [str(r) for r in (cfg.get("refer_images") or [])], cfg)
    if rel_pose not in refer:
        refer.append(rel_pose)
    pin_refs = pinned_refer_paths(cfg, char_key)
    cfg["refer_images"] = trim_refer_images_for_element(
        refer, keep=rel_pose, pin=pin_refs,
    )
    assert_pose_in_refer_images(
        char_key,
        rel_pose,
        list(cfg["refer_images"] or []),
        source,
        frontal_rel=str(cfg.get("frontal_image") or "") or None,
    )
    if not cfg.get("frontal_image"):
        cfg["frontal_image"] = rel_pose

    element_id, _prediction_id = register_kling_element(
        char_key, cfg, str(voice_id), wavespeed_key,
    )
    cfg["element_id"] = element_id
    cfg["status"] = "active"
    element_id = str(element_id)
    chars[char_key] = cfg
    data["characters"] = chars
    save_character_subjects(data)

    return {
        "ok": True,
        "pose_rel": rel_pose,
        "pose_abs_path": str(dest),
        "element_id": element_id,
        "kling_voice_id": cfg.get("kling_voice_id"),
        "character": char_key,
        "refer_images": list(cfg.get("refer_images") or []),
    }


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
