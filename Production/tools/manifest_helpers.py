# Production/tools/manifest_helpers.py
"""
manifest_helpers.py — Stream B + F shared library for module manifest generation.

Authored: V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md Phase A.
Governing LDs: LD-404 MANIFEST_SCHEMA_V1 (manifest write contract),
               LD-412 PHASE_BOUNDARIES_NAMED_OBJECT_V1 (dual consumer emission).
"""

from typing import Any, TypedDict, Literal, List, Union
from pathlib import Path
import hashlib


# ---------------------------------------------------------------------------
# TypedDict shapes — both forms are LD-412 compliant; manifest emits form A;
# UI/catalog consumes form B.
# ---------------------------------------------------------------------------

class PhaseBoundariesManifestForm(TypedDict):
    """
    Form A — manifest emission shape (single object, 3 ms fields).
    MATCHES: Production/contracts/MANIFEST_SCHEMA_V1.json `phaseBoundaries`.
    USED BY: app `expo-video` manifest fetch path.
    """
    story_start_ms: int
    phase_b_start_ms: int
    phase_b_end_ms: int


PhaseSegmentName = Literal["intro", "phase_a", "phase_b", "resolution"]


class PhaseSegment(TypedDict):
    """
    Form B — segment-array shape (one entry per phase, seconds-precision).
    MATCHES: LD-412 decision_text + STREAM_C_CATALOG_WIRING_SPEC_v1.md.
    USED BY: UI overlays, debugging, Stream C catalog wiring.
    """
    name: PhaseSegmentName
    start_s: float
    end_s: float


# ---------------------------------------------------------------------------
# Canonical input — the label-based timeline assemble_module.py produces.
# ---------------------------------------------------------------------------

class FullModuleSegmentBoundaries(TypedDict):
    """
    Canonical internal timeline. assemble_module.py builds this from per-beat
    manifests (intro: Story Scene start→end, phase_a: Phase A start→end, etc).
    All values in milliseconds. Both Form A and Form B derive from this.
    """
    intro_start_ms: int
    intro_end_ms: int
    phase_a_start_ms: int
    phase_a_end_ms: int
    phase_b_start_ms: int
    phase_b_end_ms: int
    resolution_start_ms: int
    resolution_end_ms: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MANIFEST_FORM_KEYS = ("story_start_ms", "phase_b_start_ms", "phase_b_end_ms")
_LEGACY_FORM_KEYS = ("storyStartMs", "phaseBStartMs", "phaseBEndMs")
_FULL_MODULE_KEYS = (
    "intro_start_ms",
    "intro_end_ms",
    "phase_a_start_ms",
    "phase_a_end_ms",
    "phase_b_start_ms",
    "phase_b_end_ms",
    "resolution_start_ms",
    "resolution_end_ms",
)


def _coerce_int_ms(value: Any, key: str) -> int:
    """Validate that a value is a non-negative integer (ms)."""
    if isinstance(value, bool):  # bool is subclass of int — reject explicitly.
        raise ValueError(
            f"phaseBoundaries[{key}] must be a non-negative integer (got bool {value!r})"
        )
    if not isinstance(value, int):
        raise ValueError(
            f"phaseBoundaries[{key}] must be a non-negative integer (got {type(value).__name__}: {value!r})"
        )
    if value < 0:
        raise ValueError(
            f"phaseBoundaries[{key}] must be >= 0 (got {value})"
        )
    return value


def _detect_input_shape(raw: Any) -> str:
    """
    Return one of: 'manifest', 'legacy', 'full_module'.
    Raises ValueError if no shape matches (missing required keys).
    """
    if not isinstance(raw, dict):
        raise ValueError(
            f"phase_boundaries input must be a dict, got {type(raw).__name__}"
        )
    if all(k in raw for k in _MANIFEST_FORM_KEYS):
        return "manifest"
    if all(k in raw for k in _LEGACY_FORM_KEYS):
        return "legacy"
    if all(k in raw for k in _FULL_MODULE_KEYS):
        return "full_module"
    missing_manifest = [k for k in _MANIFEST_FORM_KEYS if k not in raw]
    raise ValueError(
        "phase_boundaries input does not match any supported shape "
        "(manifest form, legacy camelCase form, or FullModuleSegmentBoundaries label form). "
        f"Missing manifest-form keys: {missing_manifest}; got keys: {sorted(raw.keys())}"
    )


# ---------------------------------------------------------------------------
# Emitters — explicit, named, non-overloaded.
# ---------------------------------------------------------------------------

def phase_boundaries_to_manifest_form(
    raw: Union[dict, FullModuleSegmentBoundaries]
) -> PhaseBoundariesManifestForm:
    """
    Reformat ANY caller-supplied phaseBoundaries source into the locked
    manifest-form per LD-404 + MANIFEST_SCHEMA_V1.json.

    Accepts THREE input shapes (R1 amended 2026-05-08):
      1. Already-correct manifest form: {story_start_ms, phase_b_start_ms, phase_b_end_ms}
         (passes through with validation).
      2. Legacy key spellings: storyStartMs / phaseBStartMs / phaseBEndMs
         (snake_cased on read).
      3. FullModuleSegmentBoundaries label-based form
         (story_start_ms = intro_start_ms; phase_b_start_ms = phase_b_start_ms;
          phase_b_end_ms = phase_b_end_ms — note resolution period is OUTSIDE
          phase_boundaries per the manifest contract).

    Args:
        raw: dict in any of the three shapes above.

    Returns:
        Validated PhaseBoundariesManifestForm with snake_case keys.

    Raises:
        ValueError if any required key is missing OR if values do not satisfy
        story_start_ms <= phase_b_start_ms <= phase_b_end_ms.
    """
    shape = _detect_input_shape(raw)

    if shape == "manifest":
        story_start_ms = _coerce_int_ms(raw["story_start_ms"], "story_start_ms")
        phase_b_start_ms = _coerce_int_ms(raw["phase_b_start_ms"], "phase_b_start_ms")
        phase_b_end_ms = _coerce_int_ms(raw["phase_b_end_ms"], "phase_b_end_ms")
    elif shape == "legacy":
        story_start_ms = _coerce_int_ms(raw["storyStartMs"], "storyStartMs")
        phase_b_start_ms = _coerce_int_ms(raw["phaseBStartMs"], "phaseBStartMs")
        phase_b_end_ms = _coerce_int_ms(raw["phaseBEndMs"], "phaseBEndMs")
    else:  # full_module
        # Per spec: story_start_ms = intro_start_ms; phase_b boundaries pass through.
        # Resolution period is INTENTIONALLY excluded from manifest form.
        story_start_ms = _coerce_int_ms(raw["intro_start_ms"], "intro_start_ms")
        phase_b_start_ms = _coerce_int_ms(raw["phase_b_start_ms"], "phase_b_start_ms")
        phase_b_end_ms = _coerce_int_ms(raw["phase_b_end_ms"], "phase_b_end_ms")

    if not (story_start_ms <= phase_b_start_ms <= phase_b_end_ms):
        raise ValueError(
            "phase_boundaries violates ordering invariant "
            "story_start_ms <= phase_b_start_ms <= phase_b_end_ms "
            f"(got story_start_ms={story_start_ms}, "
            f"phase_b_start_ms={phase_b_start_ms}, "
            f"phase_b_end_ms={phase_b_end_ms})"
        )

    return PhaseBoundariesManifestForm(
        story_start_ms=story_start_ms,
        phase_b_start_ms=phase_b_start_ms,
        phase_b_end_ms=phase_b_end_ms,
    )


def phase_boundaries_to_segment_array_form(
    raw: Union[dict, FullModuleSegmentBoundaries]
) -> List[PhaseSegment]:
    """
    Reformat ANY caller-supplied phaseBoundaries source into the segment-array
    form per LD-412 decision_text. Always emits exactly 4 segments in order:
    intro, phase_a, phase_b, resolution (any can be zero-duration if absent
    from input, except phase_b which MUST have positive duration).

    Args:
        raw: dict in any input shape (manifest form, legacy keys, or
             FullModuleSegmentBoundaries label form).

    Returns:
        Length-4 list of PhaseSegment dicts. start_s / end_s are floats
        (millisecond input divided by 1000.0).

    Raises:
        ValueError if phase_b duration is zero or negative.
    """
    shape = _detect_input_shape(raw)

    if shape == "full_module":
        intro_start_ms = _coerce_int_ms(raw["intro_start_ms"], "intro_start_ms")
        intro_end_ms = _coerce_int_ms(raw["intro_end_ms"], "intro_end_ms")
        phase_a_start_ms = _coerce_int_ms(raw["phase_a_start_ms"], "phase_a_start_ms")
        phase_a_end_ms = _coerce_int_ms(raw["phase_a_end_ms"], "phase_a_end_ms")
        phase_b_start_ms = _coerce_int_ms(raw["phase_b_start_ms"], "phase_b_start_ms")
        phase_b_end_ms = _coerce_int_ms(raw["phase_b_end_ms"], "phase_b_end_ms")
        resolution_start_ms = _coerce_int_ms(
            raw["resolution_start_ms"], "resolution_start_ms"
        )
        resolution_end_ms = _coerce_int_ms(
            raw["resolution_end_ms"], "resolution_end_ms"
        )
    else:
        # Manifest or legacy form: only 3 boundary points are known.
        # Per spec, intro and phase_a collapse to zero-duration segments at
        # story_start_ms; resolution collapses to zero-duration at phase_b_end_ms.
        manifest = phase_boundaries_to_manifest_form(raw)
        intro_start_ms = manifest["story_start_ms"]
        intro_end_ms = manifest["story_start_ms"]
        phase_a_start_ms = manifest["story_start_ms"]
        phase_a_end_ms = manifest["phase_b_start_ms"]
        phase_b_start_ms = manifest["phase_b_start_ms"]
        phase_b_end_ms = manifest["phase_b_end_ms"]
        resolution_start_ms = manifest["phase_b_end_ms"]
        resolution_end_ms = manifest["phase_b_end_ms"]

    if phase_b_end_ms - phase_b_start_ms <= 0:
        raise ValueError(
            "phase_b segment must have positive duration "
            f"(got start={phase_b_start_ms}ms, end={phase_b_end_ms}ms)"
        )

    return [
        PhaseSegment(
            name="intro",
            start_s=intro_start_ms / 1000.0,
            end_s=intro_end_ms / 1000.0,
        ),
        PhaseSegment(
            name="phase_a",
            start_s=phase_a_start_ms / 1000.0,
            end_s=phase_a_end_ms / 1000.0,
        ),
        PhaseSegment(
            name="phase_b",
            start_s=phase_b_start_ms / 1000.0,
            end_s=phase_b_end_ms / 1000.0,
        ),
        PhaseSegment(
            name="resolution",
            start_s=resolution_start_ms / 1000.0,
            end_s=resolution_end_ms / 1000.0,
        ),
    ]


def validate_phase_boundaries(
    pb: Union[PhaseBoundariesManifestForm, List[PhaseSegment]],
    total_duration_ms: int
) -> None:
    """
    Enforce LD-412 invariants on EITHER form.

    For manifest form (PhaseBoundariesManifestForm dict):
        - story_start_ms < 0 → ValueError
        - phase_b_start_ms < story_start_ms → ValueError
        - phase_b_end_ms < phase_b_start_ms → ValueError
        - phase_b_end_ms > total_duration_ms → ValueError

    For segment-array form (List[PhaseSegment]):
        - len != 4 → ValueError
        - names not in order [intro, phase_a, phase_b, resolution] → ValueError
        - any segment start > end → ValueError
        - segment[N].end != segment[N+1].start (no gaps, no overlaps) → ValueError
        - phase_b duration <= 0 → ValueError
        - resolution.end > total_duration_ms / 1000.0 → ValueError
    """
    if isinstance(total_duration_ms, bool) or not isinstance(total_duration_ms, int):
        raise ValueError(
            f"total_duration_ms must be an int (got {type(total_duration_ms).__name__})"
        )
    if total_duration_ms < 0:
        raise ValueError(
            f"total_duration_ms must be >= 0 (got {total_duration_ms})"
        )

    if isinstance(pb, dict):
        # Manifest form path
        for k in _MANIFEST_FORM_KEYS:
            if k not in pb:
                raise ValueError(
                    f"phase_boundaries manifest form missing required key: {k}"
                )
        story_start_ms = _coerce_int_ms(pb["story_start_ms"], "story_start_ms")
        phase_b_start_ms = _coerce_int_ms(pb["phase_b_start_ms"], "phase_b_start_ms")
        phase_b_end_ms = _coerce_int_ms(pb["phase_b_end_ms"], "phase_b_end_ms")

        if story_start_ms < 0:
            raise ValueError(
                f"story_start_ms must be >= 0 (got {story_start_ms})"
            )
        if phase_b_start_ms < story_start_ms:
            raise ValueError(
                "phase_b_start_ms must be >= story_start_ms "
                f"(got phase_b_start_ms={phase_b_start_ms}, story_start_ms={story_start_ms})"
            )
        if phase_b_end_ms < phase_b_start_ms:
            raise ValueError(
                "phase_b_end_ms must be >= phase_b_start_ms "
                f"(got phase_b_end_ms={phase_b_end_ms}, phase_b_start_ms={phase_b_start_ms})"
            )
        if phase_b_end_ms > total_duration_ms:
            raise ValueError(
                "phase_b_end_ms must be <= total_duration_ms "
                f"(got phase_b_end_ms={phase_b_end_ms}, total_duration_ms={total_duration_ms})"
            )
        return

    if isinstance(pb, list):
        # Segment-array form path
        if len(pb) != 4:
            raise ValueError(
                f"segment-array phase_boundaries must have exactly 4 entries (got {len(pb)})"
            )
        expected_names: List[PhaseSegmentName] = [
            "intro",
            "phase_a",
            "phase_b",
            "resolution",
        ]
        for idx, seg in enumerate(pb):
            if not isinstance(seg, dict):
                raise ValueError(
                    f"segment-array entry {idx} must be a dict (got {type(seg).__name__})"
                )
            for required in ("name", "start_s", "end_s"):
                if required not in seg:
                    raise ValueError(
                        f"segment-array entry {idx} missing required key: {required}"
                    )
            if seg["name"] != expected_names[idx]:
                raise ValueError(
                    "segment-array names must be in order "
                    f"{expected_names} (got {[s.get('name') for s in pb]})"
                )
            if not isinstance(seg["start_s"], (int, float)) or isinstance(
                seg["start_s"], bool
            ):
                raise ValueError(
                    f"segment-array entry {idx} start_s must be numeric"
                )
            if not isinstance(seg["end_s"], (int, float)) or isinstance(
                seg["end_s"], bool
            ):
                raise ValueError(
                    f"segment-array entry {idx} end_s must be numeric"
                )
            if seg["start_s"] > seg["end_s"]:
                raise ValueError(
                    f"segment-array entry {idx} ({seg['name']}) has start_s > end_s "
                    f"(start={seg['start_s']}, end={seg['end_s']})"
                )

        # No gaps, no overlaps.
        for idx in range(len(pb) - 1):
            if pb[idx]["end_s"] != pb[idx + 1]["start_s"]:
                raise ValueError(
                    "segment-array must have no gaps/overlaps: "
                    f"segment[{idx}].end_s={pb[idx]['end_s']} != "
                    f"segment[{idx + 1}].start_s={pb[idx + 1]['start_s']}"
                )

        # phase_b positive duration.
        phase_b = pb[2]
        if phase_b["end_s"] - phase_b["start_s"] <= 0:
            raise ValueError(
                "phase_b segment must have positive duration "
                f"(got start={phase_b['start_s']}, end={phase_b['end_s']})"
            )

        resolution = pb[3]
        if resolution["end_s"] > total_duration_ms / 1000.0:
            raise ValueError(
                "resolution.end_s must be <= total_duration_ms / 1000.0 "
                f"(got resolution.end_s={resolution['end_s']}, "
                f"total_duration_ms/1000.0={total_duration_ms / 1000.0})"
            )
        return

    raise ValueError(
        "validate_phase_boundaries: pb must be a manifest-form dict or "
        f"segment-array list (got {type(pb).__name__})"
    )


def compute_app_compat_content_hash(file_path: Path) -> str:
    """
    Compute SHA-256 over the file's RAW bytes and return as 64-char lowercase hex.

    This is the canonical app-compat hash form per R3 (single hex hash) — matches
    expo-crypto digestStringAsync() default `encoding=Encoding.HEX` behavior.

    Phase D execution-time gate verifies the app's actual encoding by either reading
    the app's expo-crypto call site OR running a Phase B smoke test that hashes a
    known asset client-side and compares to the value this function produces. If
    the app uses a non-default encoding (e.g., the legacy base64 form per
    upload_module.py:155-165 which is OBSOLETE post-R2 cutover), escalate as
    RELEASE-BLOCKER per §7 and fall back to dual-form per §13 Open Kim Decision 3.

    Args:
        file_path: absolute Path to the file to hash.

    Returns:
        64-character lowercase hex string matching `^[a-f0-9]{64}$` per MANIFEST_SCHEMA_V1.json.

    Raises:
        FileNotFoundError if file_path does not exist or is not a regular file.
    """
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(
            f"compute_app_compat_content_hash: file not found or not a regular file: {path}"
        )

    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
