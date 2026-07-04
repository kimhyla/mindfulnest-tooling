"""O3_GALLERY_OPTION_IDENTITY_V1 — canonical gallery key ↔ path ↔ export authority.

Human spec: Production/docs/TECH_SPEC_OPERATOR_EXPORT_TRUTH_CLOSURE_V1.md (FF-022, FF-023)
Sibling: o3_gallery_closure.py (terminal done ⟺ row exists — lifecycle only)
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

O3_GALLERY_OPTION_IDENTITY_V1 = "O3_GALLERY_OPTION_IDENTITY_V1"
O3_CLIP_AUDIO_CONTRACT_V1 = "O3_CLIP_AUDIO_CONTRACT_V1"
O3_GALLERY_KEY_COLLISION_HEAL = "O3_GALLERY_KEY_COLLISION_HEAL"
O3_STILL_INSERT_SILENT_SIBLING_PRUNE = "O3_STILL_INSERT_SILENT_SIBLING_PRUNE"

AUDIO_CONTRACT_VIDEO_ONLY = "video_only"
AUDIO_CONTRACT_EMBEDDED_VOICE = "embedded_voice"
AUDIO_CONTRACT_TTS_MUXED = "tts_muxed"

_EXPORT_VOICE_RMS_THRESHOLD = 0.002


class O3GalleryOptionAmbiguousError(ValueError):
    """Duplicate keys remain after normalize — fail closed."""


class O3GalleryExportAuthorityError(ValueError):
    """Active pointer / selected key / export path disagree."""


class O3ClipAudioContractError(ValueError):
    """Export clip violates operator audio contract."""


def canonical_o3_option_key(beat_id: str, video_path: str) -> str:
    digest = hashlib.sha1(str(video_path).encode("utf-8")).hexdigest()[:10]
    return f"{beat_id}_o3_video_{digest}"


def is_still_insert_gallery_option(beat_id: str, option: dict, *, video_path: str | None = None) -> bool:
    """Still-insert rows use stable stem keys — not sha1 canonical keys."""
    vp = str(video_path or option.get("video_path") or "").strip()
    key = str(option.get("key") or "")
    source = str(option.get("source") or "").lower()
    if source.startswith("still_insert") or "_still_insert_" in vp.lower():
        return True
    return bool(beat_id and key.startswith(beat_id) and "_still_insert_" in key)


def is_still_insert_silent_ken_burns_preview(video_path: str) -> bool:
    """True for ken-burns preview clips (``*_still_insert_<ts>.mp4``) without real TTS audio.

    Ken-burns builds mux a near-silent AAC track onto the preview file; the audible clip is
    the ``*_tts.mp4`` sibling. Disk reconcile must not fill UI slots with these when TTS exists.
    """
    path = Path(str(video_path or "").strip())
    name = path.name.lower()
    if "_still_insert_" not in name or not name.endswith(".mp4"):
        return False
    if "_tts" in name or "_trimmed" in name or "_kling_idle" in name:
        return False
    if not path.is_file():
        return False
    if clip_has_embedded_voice(path):
        return False
    parent = path.parent
    tts = parent / f"{path.stem}_tts.mp4"
    return tts.is_file()


def still_insert_audible_sibling_path(video_path: str | Path) -> Path | None:
    """Return ``*_tts.mp4`` sibling when ``video_path`` is a silent ken-burns preview."""
    path = Path(str(video_path or "").strip())
    if not is_still_insert_silent_ken_burns_preview(str(path)):
        return None
    tts = path.parent / f"{path.stem}_tts.mp4"
    return tts if tts.is_file() else None


def filter_still_insert_disk_paths_for_gallery(paths: list[Path]) -> list[Path]:
    """Drop silent ken-burns previews when an audible ``*_tts`` sibling is in the batch."""
    resolved = {str(p.resolve()) for p in paths if p.is_file()}
    kept: list[Path] = []
    for path in paths:
        if not path.is_file():
            continue
        sibling = still_insert_audible_sibling_path(path)
        if sibling is not None and str(sibling.resolve()) in resolved:
            continue
        kept.append(path)
    return kept


def prune_still_insert_silent_sibling_options(beat: dict) -> list[str]:
    """Remove silent ken-burns rows from ``kling_o3_options`` when ``*_tts`` sibling is listed."""
    options = [o for o in (beat.get("kling_o3_options") or []) if isinstance(o, dict)]
    if not options:
        return []
    paths = {
        str(o.get("video_path") or "").strip()
        for o in options
        if str(o.get("video_path") or "").strip()
    }
    logs: list[str] = []
    kept: list[dict] = []
    active_vp = str(beat.get("kling_o3_video_path") or "").strip()
    for opt in options:
        vp = str(opt.get("video_path") or "").strip()
        if not vp:
            kept.append(opt)
            continue
        if not is_still_insert_silent_ken_burns_preview(vp):
            kept.append(opt)
            continue
        sibling = still_insert_audible_sibling_path(vp)
        if sibling is None:
            kept.append(opt)
            continue
        sib_str = str(sibling.resolve())
        if sib_str not in paths and sib_str != active_vp:
            kept.append(opt)
            continue
        logs.append(
            f"{O3_STILL_INSERT_SILENT_SIBLING_PRUNE}: dropped silent preview "
            f"{Path(vp).name} (audible sibling on gallery)",
        )
    if len(kept) != len(options):
        beat["kling_o3_options"] = kept
        if active_vp and is_still_insert_silent_ken_burns_preview(active_vp):
            rep = still_insert_audible_sibling_path(active_vp)
            if rep is not None:
                beat["kling_o3_video_path"] = str(rep.resolve())
                logs.append(
                    f"{O3_STILL_INSERT_SILENT_SIBLING_PRUNE}: active pointer "
                    f"→ {rep.name}",
                )
    return logs


def still_insert_gallery_option_key(beat_id: str, video_path: str) -> str:
    """Stable gallery key for still-insert clips — one key per distinct file stem.

    Ken-burns still builds produce silent (``*.mp4``) and TTS (``*_tts.mp4``)
    siblings on disk. Collapsing ``_tts`` into the silent stem caused duplicate
    gallery keys, ``_dup*`` demotion, and select-o3 ``key/path mismatch`` failures.
    """
    return Path(str(video_path).strip()).stem


def gallery_option_key_for_path(beat_id: str, video_path: str, option: dict | None = None) -> str:
    opt = option or {}
    if is_still_insert_gallery_option(beat_id, opt, video_path=video_path):
        return still_insert_gallery_option_key(beat_id, video_path)
    return canonical_o3_option_key(beat_id, video_path)


def option_key_matches_path(beat_id: str, option: dict) -> bool:
    vp = str(option.get("video_path") or "").strip()
    if not vp:
        return False
    expected = gallery_option_key_for_path(beat_id, vp, option)
    return str(option.get("key") or "") == expected


def stamp_o3_option_audio_contract(opt_row: dict, *, path: str | None = None) -> str:
    """Set ``audio_contract`` on an option row from ffprobe + sidecar hints."""
    contract = probe_o3_clip_audio_contract(path or str(opt_row.get("video_path") or ""), opt_row)
    opt_row["audio_contract"] = contract
    return contract


def probe_o3_clip_audio_contract(
    video_path: str,
    opt_row: dict | None = None,
) -> str:
    """Classify clip audio shape: video_only | embedded_voice | tts_muxed."""
    path = Path(str(video_path or "").strip())
    if not path.is_file():
        return AUDIO_CONTRACT_EMBEDDED_VOICE
    opt = opt_row or {}
    source = str(opt.get("source") or "").lower()
    binding = opt.get("o3_voice_binding")
    if binding and isinstance(binding, dict):
        return AUDIO_CONTRACT_TTS_MUXED
    if "tts" in source or "_tts" in path.name.lower():
        if _has_audio_stream(path):
            return AUDIO_CONTRACT_TTS_MUXED
    if not _has_audio_stream(path):
        return AUDIO_CONTRACT_VIDEO_ONLY
    if "_still_insert_" in path.name.lower() and "_kling_idle_tts" in path.name.lower():
        return AUDIO_CONTRACT_VIDEO_ONLY
    if is_still_insert_silent_ken_burns_preview(str(path)):
        return AUDIO_CONTRACT_VIDEO_ONLY
    if "_still_insert_" in path.name.lower() and not clip_has_embedded_voice(path):
        return AUDIO_CONTRACT_VIDEO_ONLY
    return AUDIO_CONTRACT_EMBEDDED_VOICE


def _has_audio_stream(path: Path) -> bool:
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                str(path.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return "audio" in (out.stdout or "")


def clip_has_embedded_voice(path: str | Path, *, start_s: float = 0.0, dur_s: float = 2.0) -> bool:
    """True when audio stream has non-silent energy (Kling/EL speech), not padding AAC."""
    p = Path(path)
    if not p.is_file() or not _has_audio_stream(p):
        return False
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-ss", f"{max(0.0, start_s):.3f}",
                "-t", f"{max(0.05, dur_s):.3f}",
                "-i", str(p.resolve()),
                "-af", "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
                "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return _has_audio_stream(p)
    log = (proc.stderr or "") + (proc.stdout or "")
    for line in log.splitlines():
        if "RMS_level" not in line:
            continue
        try:
            db = float(line.split("=")[-1].strip())
            # -inf or very low dB → silent padding
            if db <= -60.0:
                return False
            import math
            rms = math.pow(10.0, db / 20.0)
            return rms > _EXPORT_VOICE_RMS_THRESHOLD
        except (TypeError, ValueError):
            continue
    return False


def normalize_o3_gallery_options(beat: dict) -> list[str]:
    """Heal corrupt gallery rows in-place. Returns audit log lines."""
    beat_id = str(beat.get("beat_id") or "").strip()
    if not beat_id:
        return []
    options = [o for o in (beat.get("kling_o3_options") or []) if isinstance(o, dict)]
    if not options:
        return []
    logs: list[str] = []
    by_key: dict[str, list[dict]] = {}
    for opt in options:
        vp = str(opt.get("video_path") or "").strip()
        if vp and Path(vp).is_file():
            canon = gallery_option_key_for_path(beat_id, vp, opt)
            if opt.get("key") != canon:
                logs.append(
                    f"{O3_GALLERY_KEY_COLLISION_HEAL}: re-key {opt.get('key')!r} → {canon!r} "
                    f"for {Path(vp).name}",
                )
                opt["key"] = canon
            stamp_o3_option_audio_contract(opt, path=vp)
        key = str(opt.get("key") or "")
        if key:
            by_key.setdefault(key, []).append(opt)

    for key, rows in by_key.items():
        if len(rows) <= 1:
            continue
        active_vp = str(beat.get("kling_o3_video_path") or "").strip()
        active_rows = [
            r for r in rows
            if active_vp and str(r.get("video_path") or "").strip() == active_vp
        ]
        canonical_rows = [r for r in rows if option_key_matches_path(beat_id, r)]
        if active_rows:
            keep = active_rows[0]
        elif canonical_rows:
            keep = canonical_rows[0]
        else:
            keep = rows[0]
        used_keys = {str(r.get("key") or "") for r in options if isinstance(r, dict)}
        for row in rows:
            if row is keep:
                continue
            vp = str(row.get("video_path") or "").strip()
            if not vp:
                continue
            new_key = gallery_option_key_for_path(beat_id, vp, row)
            if new_key == key or new_key in used_keys:
                suffix = hashlib.sha1(vp.encode()).hexdigest()[:6]
                new_key = f"{key}_dup{suffix}"
                n = 2
                while new_key in used_keys:
                    new_key = f"{key}_dup{suffix}_{n}"
                    n += 1
            logs.append(
                f"{O3_GALLERY_KEY_COLLISION_HEAL}: duplicate key {key!r} — "
                f"demoted {Path(vp).name} → {new_key!r}",
            )
            row["key"] = new_key
            used_keys.add(new_key)

    seen_paths: dict[str, dict] = {}
    collapsed: list[dict] = []
    for opt in options:
        vp = str(opt.get("video_path") or "").strip()
        if not vp:
            collapsed.append(opt)
            continue
        try:
            resolved = str(Path(vp).resolve())
        except OSError:
            resolved = vp
        if resolved in seen_paths:
            logs.append(
                f"{O3_GALLERY_KEY_COLLISION_HEAL}: collapsed duplicate row "
                f"for {Path(vp).name}",
            )
            continue
        seen_paths[resolved] = opt
        collapsed.append(opt)
    options = collapsed

    beat["kling_o3_options"] = options
    logs.extend(prune_still_insert_silent_sibling_options(beat))
    _sync_selected_option_key_from_active_path(beat)
    return logs


def _sync_selected_option_key_from_active_path(beat: dict) -> None:
    """After normalize, align selected key with the row that owns kling_o3_video_path."""
    beat_id = str(beat.get("beat_id") or "").strip()
    active_vp = str(beat.get("kling_o3_video_path") or "").strip()
    if not beat_id or not active_vp:
        return
    options = [o for o in (beat.get("kling_o3_options") or []) if isinstance(o, dict)]
    for opt in options:
        vp = str(opt.get("video_path") or "").strip()
        if vp != active_vp:
            continue
        key = str(opt.get("key") or "").strip()
        if key:
            beat["kling_o3_selected_option_key"] = key
        return
    selected = str(beat.get("kling_o3_selected_option_key") or "").strip()
    if selected:
        try:
            opt = resolve_o3_gallery_option(beat, selected)
            if str(opt.get("video_path") or "").strip() == active_vp:
                return
        except O3GalleryOptionAmbiguousError:
            pass
        beat.pop("kling_o3_selected_option_key", None)


def _duplicate_keys_after_normalize(beat: dict) -> list[str]:
    seen: dict[str, int] = {}
    for opt in beat.get("kling_o3_options") or []:
        if not isinstance(opt, dict):
            continue
        key = str(opt.get("key") or "")
        if not key:
            continue
        seen[key] = seen.get(key, 0) + 1
    return [k for k, n in seen.items() if n > 1]


def resolve_o3_gallery_option(beat: dict, option_key: str) -> dict:
    """Single read gate for gallery option lookup — fail closed on ambiguity."""
    beat_id = str(beat.get("beat_id") or "").strip()
    key = str(option_key or "").strip()
    if not beat_id or not key:
        raise O3GalleryOptionAmbiguousError("missing beat_id or option_key")
    dupes = _duplicate_keys_after_normalize(beat)
    if dupes:
        raise O3GalleryOptionAmbiguousError(
            f"duplicate gallery keys after normalize: {', '.join(dupes)}",
        )
    matches = [
        o for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict) and str(o.get("key") or "") == key
    ]
    if len(matches) > 1:
        raise O3GalleryOptionAmbiguousError(f"ambiguous gallery key {key!r}")
    if len(matches) == 1:
        opt = matches[0]
        vp = str(opt.get("video_path") or "").strip()
        if vp and not option_key_matches_path(beat_id, opt):
            raise O3GalleryOptionAmbiguousError(
                f"key/path mismatch for {key!r} → {Path(vp).name}",
            )
        return opt
    raise O3GalleryOptionAmbiguousError(f"unknown gallery key {key!r}")


def resolve_o3_gallery_option_or_path(
    beat: dict,
    option_key: str,
) -> tuple[dict | None, str | None]:
    """Resolve option + video_path; stem/path fallback only when key is unique."""
    beat_id = str(beat.get("beat_id") or "").strip()
    try:
        opt = resolve_o3_gallery_option(beat, option_key)
        return opt, str(opt.get("video_path") or "") or None
    except O3GalleryOptionAmbiguousError:
        raise
    except ValueError:
        pass
    options = [o for o in (beat.get("kling_o3_options") or []) if isinstance(o, dict)]
    for o in options:
        vp = str(o.get("video_path") or "")
        stem = Path(vp).stem if vp else ""
        if stem and (stem == option_key or vp.endswith(f"/{option_key}.mp4")):
            if vp and option_key_matches_path(beat_id, o):
                return o, vp
    if option_key == f"{beat_id}_approved_o3_video" and beat.get("kling_o3_video_path"):
        vp = str(beat.get("kling_o3_video_path"))
        return {
            "key": option_key,
            "label": "approved O3 video",
            "video_path": vp,
            "source": "approved_kling_o3_video",
        }, vp
    return None, None


def assert_beat_export_gallery_authority(beat: dict) -> None:
    """Export gate — active pointer must match selected option identity."""
    beat_id = str(beat.get("beat_id") or "beat")
    path = str(beat.get("kling_o3_video_path") or "").strip()
    if not path:
        raise O3GalleryExportAuthorityError(f"{beat_id}: missing kling_o3_video_path")
    selected = str(beat.get("kling_o3_selected_option_key") or "").strip()
    if selected:
        opt = resolve_o3_gallery_option(beat, selected)
        opt_path = str(opt.get("video_path") or "").strip()
        if opt_path != path:
            raise O3GalleryExportAuthorityError(
                f"{beat_id}: selected key {selected!r} → {Path(opt_path).name} "
                f"!= export path {Path(path).name}",
            )
        return
    active_opts = [
        o for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict) and o.get("active")
    ]
    if len(active_opts) == 1:
        opt_path = str(active_opts[0].get("video_path") or "").strip()
        if opt_path and opt_path != path:
            raise O3GalleryExportAuthorityError(
                f"{beat_id}: active option path != kling_o3_video_path",
            )


def assert_beat_export_audio_contract(beat: dict, clip_path: str | Path) -> None:
    """Fail closed when still-insert video_only selection exports embedded voice."""
    selected = str(beat.get("kling_o3_selected_option_key") or "").strip()
    if not selected:
        return
    try:
        opt = resolve_o3_gallery_option(beat, selected)
    except O3GalleryOptionAmbiguousError:
        return
    contract = str(opt.get("audio_contract") or probe_o3_clip_audio_contract(
        str(opt.get("video_path") or ""), opt,
    ))
    if contract != AUDIO_CONTRACT_VIDEO_ONLY:
        return
    if clip_has_embedded_voice(clip_path):
        raise O3ClipAudioContractError(
            f"{beat.get('beat_id')}: video_only contract but export clip has embedded voice",
        )
