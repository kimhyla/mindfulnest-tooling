# V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC v1

**Date authored:** 2026-05-07
**Author:** Claude (Opus 4.7, Sonnet sessions to execute)
**Status:** active — execution candidate
**Output of:** Cursor cross-review iteration on Stream B + Stream F gap-fill (5 concerns surfaced; resolutions R1-R5 baked in below)
**Format:** tech-spec skill update 2026-05-06 (§0 Operating Mode + §14 Pre-Execution + §15 Items Missed + §16 Reference Index)
**Owner streams:** B (Single-MP4 assembly pipeline) + F (Content deployment / Cloudflare R2)
**Gate alignment:** G0 contract artifacts → G1 serial milestone (Event 0 → M1 end-to-end)

---

## §0. Mandatory Operating Mode

### §0.1 Pre-Execution Phase 0 — Locked Decision Snapshot (R5)

Before any phase begins, the executing session MUST query Directus `prod_locked_decisions` via `Production/lib/directus.py::try_post_or_queue` (read-back-after-write contract per CLAUDE.md Rule 35 / DS-8) for the decision keys below. Each MUST return `status=active`. Missing or non-active rows = HALT and surface to Kim.

**Required snapshot (cite by `decision_key` — never by integer id, since LD numbers are unstable across schema migrations):**

| # | decision_key | Confirmed-active at spec author time (2026-05-07) | Used by |
|---|---|---|---|
| 1 | `RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1` (id=280) | ACTIVE / HIGH | Phase C concat output contract |
| 2 | `NO_RUNTIME_TTS_PERSONALIZATION_V1` (id=281) | ACTIVE / HIGH | Phase C audio-bake invariant |
| 3 | `CATALOG_DELIVERY_ARC_AT_A_TIME_V1` (id=282) | ACTIVE / HIGH | Phase D R2 publish ordering |
| 4 | `SIZE_BUDGET_PER_MODULE_V1` (id=283) | ACTIVE / HIGH | Phase C Step 11 size+duration gate |
| 5 | `NORMALIZATION_BEFORE_CONCAT_V1` (id=284) | ACTIVE / high | Phase C Step 1 input validation |
| 6 | `PRE_LAUNCH_SERVICES_V1` (id=345) | ACTIVE / HIGH | Phase D R2 must be live before staging child data |
| 7 | `POST_ITEM_VERIFIED_V1` (id=364) | ACTIVE / HIGH | All Directus writes — read-back-after-write |
| 8 | `MANIFEST_SCHEMA_V1` (id=404) | ACTIVE / HIGH — **AMEND target** for `phaseBoundaries` shape | Phase A manifest_helpers.py + Phase D manifest publishing |
| 9 | `SECRETS_MGMT_LOCKED_PRELAUNCH_V1` (id=405) | ACTIVE / HIGH | Phase D r2_upload.py credential handling |
| 10 | `PHASE_BOUNDARIES_NAMED_OBJECT_V1` (id=412) | ACTIVE / HIGH — **OVERLAPS** Kim-listed new LD (see §15) | Phase A reformatter |
| 11 | `ASSET_FINDABILITY_OVERHAUL_V1` (id=421) | ACTIVE / HIGH | All `prod_assets` writes — registered_write.py wrapper |
| 12 | `ASSET_FINDABILITY_BUILD_V1` (id=422) | ACTIVE / HIGH | Wrapper enforcement gate |
| 13 | `CDN_CLOUDFLARE_R2_V1` (id=432) | ACTIVE / high | Phase D Firebase-to-R2 cutover |
| 14 | `SIZE_BUDGET_VIDEO_V1` (id=296) | ACTIVE / HIGH | Phase C Step 1.5 ffprobe HARD STOP at ≤1,900,000 bps |
| 15 | `CONCAT_AUDIO_PARITY_V1` | **NOT FOUND in Directus at author time** (referenced only in `Production/governance/video-producer_governance.md` Lessons Learned April 25-26 2026) — see §15 finding 1 | Phase C Step 1.5 audio-stream parity |

**Snapshot artifact (mandatory output of Phase 0 Step 0.1):** `Production/Event_<N>/.preflight_evidence/<phase>_ld_snapshot.json` with shape `{taken_at: ISO8601, queries: [{q, found, id, key, name, status, sev}]}`. The author's snapshot at spec write time is preserved at `Production/Event_1/.preflight_evidence/V59_STREAM_BF_SPEC_ld_snapshot.json` (created 2026-05-07, 21 raw query rows / **15 unique decision keys** — some keys queried multiple times via different lookup paths; the snapshot records 21 raw query results which dedupe to 15 unique decision keys, of which 14 active and 1 missing was flagged as Finding 1 below). Future Phase 0 snapshots: dedupe by decision_key before reporting count to avoid the raw-vs-unique ambiguity.

**HALT conditions:**
- Any required key returns `found=false` (except `CONCAT_AUDIO_PARITY_V1` which is documented as a known gap in §15 — execution may proceed if Phase 0 includes a pre-step to register it; otherwise HALT).
- Any required key returns `status != active`.
- Snapshot file fails to write or is empty.

### §0.2 Mandatory Operating Mode (per tech-spec skill 2026-05-06)

1. **Six-Layer Verification Contract (DS-13).** Every behavior added in Phase A-D MUST pass all 6 layers before phase COMPLETE: UI/CLI element exists → input wiring → backend processing → state propagation → UI/output re-render → end-to-end smoke. Server-side gates (py_compile, curl, ffprobe) verify Layers 1-4. Layer 5+6 require live execution against a real test event (Event 0 or Event 1).
2. **Eight Risk Classes for Silent Failure (DS-14).** Per-class smoke tests required where applicable — for this spec the load-bearing classes are: (a) Multi-stage pipelines (10-step assemble_module pipeline; per-stage logging mandatory); (b) Side-effect captures (registered_write, iteration_notes, cdn_url, manifest_published_at — grep all write paths and assert find_asset returns row); (c) Async / fire-and-forget (R2 upload + verify HEAD); (d) Conditional rendering (size-budget threshold branch behavior).
3. **DS-16 Memory Mantra:** Do NOT rely on memory or guess. Read every contract file, governance file, and `prod_assets` schema row before authoring an execution payload. Re-read at phase boundaries.
4. **DS-19 Standing Escape Hatches:** STOP and surface to Kim if any of: schema drift (live `/fields/prod_assets` ≠ this spec's expected fields); LD-404 amend wording uncertain; py_compile breaks on `assemble_module.py`; Layer 6 smoke fails (Event 0 produced output that did not pass all hard-fail gates); Rule 26 Opus escalation triggered.
5. **Tier B classification.** This spec governs an architectural change (new schema fields + new LDs + LD AMEND + Firebase-to-R2 cutover). Phase 6.5 live boundary probe + Phase 6.7 mobile E2E (R2 catalog fetch) + Phase 6.8 media golden probe (Event 0 atomic MP4) all REQUIRED at execution time.
6. **Confidence annotation per CLAUDE.md Rule 24** required throughout the executing session — tag every numeric threshold / LD citation / interpretation as `[CONFIRMED against <source>]`, `[INFERRED — verify]`, or `[GUESSED]`.

---

## §1. Task

Build Stream B (Single-MP4 assembly pipeline) and Stream F (Cloudflare R2 deployment) to the level required for the G1 serial milestone (Event 0 mandatory spike per v6 §2 → M1 end-to-end on physical iPad 9). Specifically:

- **Phase A** — Author `Production/tools/manifest_helpers.py` (currently does NOT exist on disk, confirmed via `ls` 2026-05-07): a small library exposing `phase_boundaries_to_manifest_form()`, `validate_phase_boundaries()`, and `compute_app_compat_content_hash()` used by both Phase C (assemble_module) and Phase D (r2_atomic_publish) to keep manifest emission consistent.
- **Phase B** — Add 3 fields to `prod_assets` (`cdn_url`, `manifest_published_at`, `codec_recipe_hash`) and update `Production/tools/registered_write.py::register_asset` signature to accept and persist them. Drops the dual content_hash representation per R3 — see §3.3.
- **Phase C** — Author `Production/tools/assemble_module.py` (currently does NOT exist on disk, confirmed): the canonical 10-step pipeline followed by 3 finalization steps (R2). Produces all 7 declared output artifacts per `ASSEMBLE_MODULE_CONTRACT.md`. Gates on size+duration (LD-283), bitrate (LD-296), audio parity (CONCAT_AUDIO_PARITY_V1).
- **Phase D** — Author `Production/scripts/r2_upload.py` and `Production/scripts/r2_atomic_publish.py` per `R2_DEPLOYMENT_CONTRACT.md`. Amend LD-404 `MANIFEST_SCHEMA_V1` to align `phaseBoundaries` with the named-object shape per LD-412 (or close LD-412 if redundant — see §15). Execute Firebase-to-R2 cutover per LD-432.

**Goal-level success criteria:**
- Event 0 successfully assembles via Phase C + uploads via Phase D and is fetchable from `https://cdn.mindfulnest.app/modules/E0.<sha-12>.mp4` with all R2 cache headers present and HEAD/range probes green.
- LD-404 manifest schema AMEND merged so app-side schema validator accepts new shape.
- 6 new LDs registered in `prod_locked_decisions` (was 7; `MANIFEST_PHASEBOUNDARIES_NAMED_OBJECT_LOCK_V1` dropped per LOCKED Decision 5 in favor of LD-412); LD-404 PATCHED with `decision_text` updated in place per LOCKED Decision 1 (Phase D AMEND, in-place path).

**Goal-level non-success conditions (Rule 19 / DS-19):**
- Any silent failure in Directus writes (skip read-back-after-write).
- Any output MP4 above the 80 MB / 7 minute / 1,900,000 bps gates without a `SHORTCUT_MODULE_<id>_CEILING_V1` Kim-approved decision.
- Any `prod_assets` write outside `registered_write.py`.
- Any Phase D upload that bypasses the 5-step atomic publish order (upload → verify hash → verify range → publish manifest → smoke test).

---

## §2. Governing Decisions

All §0.1 LDs are governing. The load-bearing decisions and **the precise constraint each one imposes on this spec** are enumerated below — citation alone is insufficient per CLAUDE.md Rule 16.

| LD key | Constraint imposed on this spec | Where enforced |
|---|---|---|
| `RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1` (LD-280) | Phase C output is ONE MP4 with all video+audio+animations baked. No separate audio track, no overlay file, no multi-file deliverable. | Phase C Step 3 (+faststart re-mux) + Step 4 (MOOV-at-front validation) + Step 6 (1-frame decode) + Step 7 (full-duration smoke) |
| `NO_RUNTIME_TTS_PERSONALIZATION_V1` (LD-281) | The audio mix MP3 fed to Phase C must contain ZERO `{childName}` / `{therapistName}` / `{parentTitle}` / `{parentName}` / `{chosenGuideName}` / pronoun placeholders. All universal phrasing is resolved at production-pipeline authoring time, not at concat time. | Phase C Step 0 input validation (grep audio mix metadata sidecar for placeholder tokens; HARD STOP if any present) |
| `CATALOG_DELIVERY_ARC_AT_A_TIME_V1` (LD-282) | Phase D publishes per-module assets to immutable hash-named URLs; manifest is the single mutable cache key. Versioned manifests (`manifest_v_<catalogVersion>.json`) are immutable for rollback. | Phase D r2_atomic_publish.py 5-step sequence |
| `SIZE_BUDGET_PER_MODULE_V1` (LD-283) | Phase C Step 11 HARD-FAILS if `bytes > 80 MB` (83,886,080) or `durationMs > 420,000` (7 min). Override = `SHORTCUT_MODULE_<id>_CEILING_V1` with Kim approval per Rule 19. | Phase C Step 11 finalization |
| `NORMALIZATION_BEFORE_CONCAT_V1` (LD-284) | Phase C Step 1 ffprobes EVERY input; HARD-FAILS if any input deviates from canonical codec spec (H.264 High / yuv420p / 1280×720 / 24 fps / AAC 128 kbps mono 44.1 kHz / +faststart). Concat is `-c copy`; no transcode at concat time. | Phase C Step 1 ffprobe gate + Step 2 codec-copy concat |
| `MANIFEST_SCHEMA_V1` (LD-404) | The manifest entries Phase A reformats and Phase D publishes MUST validate against `Production/contracts/MANIFEST_SCHEMA_V1.json`. The `phaseBoundaries` field is the AMEND target — current locked schema accepts the shape `{story_start_ms, phase_b_start_ms, phase_b_end_ms}` (named-object form already), which means LD-412 may already be satisfied by LD-404 — see §15 finding 2. | Phase A `phase_boundaries_to_manifest_form()` + Phase D atomic publish |
| `PHASE_BOUNDARIES_NAMED_OBJECT_V1` (LD-412) | phaseBoundaries shape is named-object only; positional/array form is forbidden. **Already locked**; the Kim-listed new LD `MANIFEST_PHASEBOUNDARIES_NAMED_OBJECT_LOCK_V1` may be redundant — surfaced in §13. | Phase A `validate_phase_boundaries()` |
| `ASSET_FINDABILITY_OVERHAUL_V1` (LD-421) + `ASSET_FINDABILITY_BUILD_V1` (LD-422) | All media writes go through `Production/tools/registered_write.py`. Phase B extends the wrapper signature; Phase C calls it for every artifact; Phase D calls it for the published asset. | Phase B signature update + Phase C Step 12 + Phase D Step 4 |
| `CDN_CLOUDFLARE_R2_V1` (LD-432) | Cloudflare R2 is the CDN. Firebase Storage is superseded. Phase D r2_atomic_publish.py is the only sanctioned upload path post-cutover. | Phase D entire scope |
| `SIZE_BUDGET_VIDEO_V1` (id=296) | ffprobe stream `bit_rate` ≤ 1,900,000 bps for any normalized input AND for the assembled output. 5% guard band under the 2.0 Mbps hard ceiling. | Phase C Step 1.5 (per-input gate) + Step 5 (output gate) |
| `CONCAT_AUDIO_PARITY_V1` (governance only — see §15) | Every Phase C input must have BOTH `codec_type=video` AND `codec_type=audio`. If audio missing, inject `anullsrc=r=44100:cl=mono,atrim=duration=<seg_dur_s>` BEFORE concat. Concat demuxer silently drops ALL audio if any input lacks it. | Phase C Step 1.5 |
| `POST_ITEM_VERIFIED_V1` (LD-364) | Every Directus write performs read-back-after-write. Use `try_post_or_queue` from `Production/lib/directus.py`. Schema deviations per CLAUDE.md Rule 35 / `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`. | All Directus writes in Phase B / C / D |
| `SECRETS_MGMT_LOCKED_PRELAUNCH_V1` (LD-405) | R2 credentials (account ID, access key ID, secret access key) loaded from environment / Doppler — never hardcoded. r2_upload.py reads `os.environ['R2_ACCESS_KEY_ID']` etc. | Phase D r2_upload.py |

---

## §3. Approach

### §3.1 R1 — manifest_helpers.py (NEW file, no ambiguity)

**Pre-execution check at Phase A Step 0:** `ls Production/tools/manifest_helpers.py` MUST return "No such file or directory". Confirmed at spec author time 2026-05-07. If the file appears between spec authoring and execution, HALT and surface — someone built it concurrently and the signatures may diverge.

**The file is CREATED in Phase A** with these documented signatures.

**LD-412 dual-emission contract (R1 amended 2026-05-08):** LD-412 `PHASE_BOUNDARIES_NAMED_OBJECT_V1` is interpreted as "manifest timeline object + validator with dual consumer emission." Two consumer shapes coexist:

1. **Manifest shape** — single object with 3 ms fields (`story_start_ms`, `phase_b_start_ms`, `phase_b_end_ms`). Matches `Production/contracts/MANIFEST_SCHEMA_V1.json` exactly. This is what the app's `expo-video` player consumes via the manifest fetch path.
2. **Segment-array shape** — `[{name, start_s, end_s}]` with names `intro / phase_a / phase_b / resolution`. Matches the LD-412 decision_text and the `STREAM_C_CATALOG_WIRING_SPEC_v1.md` description. This is what UI / debugging / Stream C catalog wiring consumes.

`manifest_helpers.py` MUST emit BOTH shapes from a single canonical input. The canonical input is the label-based timeline (`full_module_segment_boundaries`) that `assemble_module.py` already produces from beat manifests. No silent translation — both shapes are explicit named functions.

```python
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
```

**File listed under §5 Created (NEW). No ambiguity at execution time:** the executing session writes this file from scratch. If `ls` returns a file at this path, HALT.

### §3.2 R2 — Canonical 10-step pipeline + Steps 11-13 finalization

Per Cursor concern: prior drafts conflated assembly with finalization. The canonical pipeline is **exactly 10 steps**, with **Steps 11-13** explicitly labeled as Post-Pipeline Finalization. This eliminates the off-by-one (some drafts called the size+duration gate "Step 9", others "Step 11").

**Canonical 10 steps (Phase C):**

1. **Validate inputs.** ffprobe every per-beat normalized clip (H.264 High / yuv420p / 1280×720 / 24 fps / AAC 128 kbps mono 44.1 kHz / +faststart). HARD STOP on any deviation per LD-284.
2. **Build concat-list.** Emit `beat_list.txt` with `file '<absolute path>'` lines (single-quote escape for paths containing spaces — see Open Question in `ASSEMBLE_MODULE_CONTRACT.md`).
3. **Concat with `-c copy`.** `ffmpeg -f concat -safe 0 -i beat_list.txt -c copy out_raw.mp4`. Codec-copy only since inputs match canonical spec.
4. **+faststart remux.** Re-mux with `-movflags +faststart` so MOOV atom is at file head. Output: `out.mp4`.
5. **MOOV validate.** Parse MP4 atom structure; assert MOOV appears before MDAT. Use `mp4dump` (Bento4) or python `pymp4` library — pick one in execution.
6. **Codec assert.** Run `ffprobe -v error -show_streams -show_format -of json out.mp4`. Assert all codec/resolution/audio/duration values match canonical spec. HARD STOP on any mismatch.
7. **1-frame decode test.** `ffmpeg -i out.mp4 -frames:v 1 -f null -`. Exit code MUST be 0.
8. **Full-duration smoke test.** `ffmpeg -i out.mp4 -f null -`. Exit code MUST be 0. Catches mid-stream corruption that 1-frame test misses.
9. **Compute hashes.** `source_hash` = SHA-256(canonicalized JSON of {per-beat hashes + audio mix hash + metadata}). `output_hash` = SHA-256 of `out.mp4` raw bytes via `compute_app_compat_content_hash()` from R1. Both written as 64-char lowercase hex per MANIFEST_SCHEMA_V1 patterns.
10. **Emit 7 artifacts.** Per `ASSEMBLE_MODULE_CONTRACT.md`: M001.mp4, M001.manifest.json, M001.ffprobe.json, M001.decode_test.log, M001.size_report.json, M001.sha256, M001.listen_through.mp4.

**Steps 11-13 (Post-Pipeline Finalization — explicitly labeled, NOT part of the canonical pipeline):**

11. **Size + duration gate.** Read `out.mp4` size in bytes; assert `bytes <= 83,886,080` (80 MB per LD-283). Read `durationMs` from ffprobe; assert `durationMs <= 420,000` (7 min per LD-283 amended cap). HARD STOP on either breach without an active `SHORTCUT_MODULE_<id>_CEILING_V1` row in `prod_locked_decisions`.
12. **register_asset.** Call `Production/tools/registered_write.py::register_asset()` with new R2-aware signature (per Phase B) once per artifact. Persists `cdn_url=None` (set in Phase D after upload), `manifest_published_at=None` (set at publish time), `codec_recipe_hash=<sha256 of canonical codec spec string>`. Read-back-after-write per LD-364.
13. **Emit phaseBoundaries.** Call `manifest_helpers.phase_boundaries_to_manifest_form(raw)` and write the named-object form into `M001.manifest.json` per LD-412.

**Cache key — canonical 5-tuple discriminator (R2):**

```
cache_key = sha256_first16_hex(
    canonical_json({
        "source_path":               <absolute path>,
        "source_mtime":              <int unix seconds>,
        "source_sha256_first_1mb":   <64-char hex>,
        "selected_option":           <str — beat option label>,
        "codec_spec_hash":           <64-char hex of LD-284 canonical spec string>,
    })
)
```

These 5 fields ARE the cache key. Two metadata fields (`created_at`, `normalizer_version`) are written into the sidecar `beat_NN_normalized.meta.json` for audit / debugging but are EXPLICITLY NOT part of the cache HIT key. A cache HIT requires all 5 of the discriminator fields to match. Stating this once explicitly here is the canonical form — Phase A / C / D reference this section rather than restating.

### §3.3 R3 — Single hex hash form (drop dual representation)

Per Cursor concern: the prior plan carried both a `content_hash` and a `sha256` field on `prod_assets`, creating two parallel sources of truth and two opportunities for them to drift. **Resolution: drop `content_hash`. The existing `prod_assets.sha256` field (raw-byte hex per LD-421 `prod_assets` schema) IS the manifest's `output_hash` IS the app-compat target.**

**Rationale (verified at upload_module.py:155-165 read 2026-05-07):** the legacy `sha256_file()` function uses `hashlib.sha256(base64(file_bytes))` — base64-encoded. That form was added 2026-04-25 (Stream C preflight 156) to match `expo-crypto.digestStringAsync` behavior **as it was being called at the time** (with `EncodingType.Base64`). Per R3 Cursor analysis: expo-crypto's documented default for `digestStringAsync` is HEX (`Encoding.HEX`), NOT base64. The legacy base64 path is therefore an OBSOLETE workaround for a non-default encoding choice that the app should not be making.

**Phase B execution-time gate:**
1. Compute `compute_app_compat_content_hash(<known asset>)` from R1 → 64-char hex.
2. Read the app's expo-crypto call site (current file path: TBD — execution session must grep `digestStringAsync` in the MindfulNest app repo).
3. If the app calls `digestStringAsync(content, Encoding.HEX)` (or default-encoding overload) → R3 stands; mark `upload_module.py:155-165 sha256_file()` as OBSOLETE post-R2 cutover.
4. If the app calls `digestStringAsync(content, Encoding.Base64)` → escalate as RELEASE-BLOCKER. Either change the app to HEX (preferred — aligns with MANIFEST_SCHEMA_V1 pattern `^[a-f0-9]{64}$`) OR fall back to dual-form (write both `prod_assets.sha256_hex` and `prod_assets.sha256_base64`, decision deferred to §13 Open Kim Decision 3).

**Phase B adds 3 NEW fields to `prod_assets`** (existing `sha256` field unchanged):
- `cdn_url` (string, nullable until publish) — the hash-named R2 URL `https://cdn.mindfulnest.app/modules/<moduleId>.<sha256-first-12>.mp4` per `R2_DEPLOYMENT_CONTRACT.md`.
- `manifest_published_at` (timestamp, nullable until publish) — wall-clock UTC of when the asset was included in a published `manifest.json`.
- `codec_recipe_hash` (string, nullable) — SHA-256 of the canonical codec recipe string used to produce the asset (LD-284 spec for normalized clips; assemble_module's recipe for atomic MP4s). Allows future fast detection of "encoder-only changed" assets per v6 §5.4.

**OBSOLETE marker on legacy base64:** `Production/tools/upload_module.py:155-165` `sha256_file()` function is EXPLICITLY MARKED OBSOLETE at execution time via inline docstring update + a `# DEPRECATED — replaced by manifest_helpers.compute_app_compat_content_hash() per V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md R3. Do not call from new code.` comment immediately above the function. Removal of the function itself is OUT OF SCOPE for this spec (§10) — there may be uncommitted callers. Removal happens in a follow-up audit task.

### §3.4 R4 — Concat audio parity + ffprobe HARD STOP at Phase C Step 1.5

Per Cursor concern: Phase C must catch both bitrate violations AND audio-stream-missing scenarios BEFORE concat, because both fail silently on output (bitrate looks fine until iPad 9 streaming stalls; audio-missing produces an output with no audio AT ALL).

**Phase C Step 1.5 (NEW STEP — sits between Step 1 input validate and Step 2 concat-list build):**

```python
# Phase C Step 1.5 — per-input ffprobe parity + bitrate gate (R4 amended 2026-05-08)
# CRITICAL: ffprobe -show_streams -show_format JSON has format at the JSON ROOT,
# not per-stream. Use root["format"]["bit_rate"] / root["format"]["duration"].
# Handle bit_rate: "N/A" by deriving from size_bytes / duration_seconds * 8.
import os, json, subprocess

def ffprobe_full(path: str) -> dict:
    """Return full ffprobe -show_streams -show_format JSON (parsed)."""
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path),
    ])
    return json.loads(out)

def derive_bitrate_bps(root: dict, file_path: str) -> int:
    """Derive overall bitrate from root.format. Handles 'N/A' fallback to size/duration."""
    fmt = root.get("format", {})
    raw = fmt.get("bit_rate")
    if raw is not None and str(raw).upper() not in ("N/A", "0", ""):
        return int(raw)
    # Fallback: size_bytes / duration_seconds * 8
    size = int(fmt.get("size", 0)) or os.path.getsize(file_path)
    dur = float(fmt.get("duration", 0))
    if dur <= 0:
        HARD_STOP(f"{file_path}: cannot derive bitrate (no duration in format)")
    return int(size * 8 / dur)

def video_duration_s(root: dict) -> float:
    """Prefer video stream duration; fall back to root.format.duration."""
    for s in root.get("streams", []):
        if s.get("codec_type") == "video" and s.get("duration"):
            try: return float(s["duration"])
            except (TypeError, ValueError): pass
    fmt_dur = root.get("format", {}).get("duration")
    if fmt_dur:
        return float(fmt_dur)
    HARD_STOP("ffprobe returned no usable duration")

for beat_path in normalized_beat_paths:
    root = ffprobe_full(beat_path)         # full JSON (root has streams[] AND format{})
    streams = root.get("streams", [])

    # (a) Video stream assert
    video_streams = [s for s in streams if s["codec_type"] == "video"]
    if len(video_streams) != 1:
        HARD_STOP(f"{beat_path}: expected exactly 1 video stream, got {len(video_streams)}")
    v = video_streams[0]
    assert v["codec_name"] == "h264" and v["profile"] == "High", \
        f"{beat_path}: video codec must be h264 High, got {v['codec_name']}/{v['profile']}"
    assert v["pix_fmt"] == "yuv420p", f"{beat_path}: pix_fmt must be yuv420p, got {v['pix_fmt']}"
    assert int(v["width"]) == 1280 and int(v["height"]) == 720, \
        f"{beat_path}: resolution must be 1280x720, got {v['width']}x{v['height']}"
    fps_ok = v.get("r_frame_rate") == "24/1" or v.get("avg_frame_rate") == "24/1"
    assert fps_ok, f"{beat_path}: fps must be 24/1, got r_frame_rate={v.get('r_frame_rate')} avg={v.get('avg_frame_rate')}"

    # (b) Audio stream assert — CONCAT_AUDIO_PARITY_V1
    audio_streams = [s for s in streams if s["codec_type"] == "audio"]
    if len(audio_streams) == 0:
        # CONCAT_AUDIO_PARITY_V1 — inject silence rather than HARD STOP.
        # Concat demuxer silently DROPS ALL AUDIO from the output if any input
        # lacks an audio stream.
        # Use video stream duration (NOT streams[0]["duration"] — that's a bug if
        # streams[0] is non-video; format.duration via fallback is also safe).
        beat_path = inject_silence_track(
            beat_path,
            duration_s=video_duration_s(root),
            sample_rate=44100,
            channels=1,
        )
        # Re-ffprobe to confirm audio now present, then continue
        audio_streams = [s for s in ffprobe_full(beat_path).get("streams", []) if s["codec_type"] == "audio"]
        if len(audio_streams) != 1:
            HARD_STOP(f"{beat_path}: silence injection failed; concat would drop audio")
    elif len(audio_streams) != 1:
        HARD_STOP(f"{beat_path}: expected exactly 1 audio stream, got {len(audio_streams)}")
    a = audio_streams[0]
    assert a["codec_name"] == "aac", f"{beat_path}: audio codec must be aac, got {a['codec_name']}"
    audio_br_raw = a.get("bit_rate")
    if audio_br_raw is None or str(audio_br_raw).upper() in ("N/A", "0", ""):
        # Audio stream lacks declared bitrate. Acceptable if normalized via LD-284 ffmpeg
        # which always sets explicit bitrate; fall through with WARN — most likely a
        # pre-normalization input that should have been rejected at Step 1.
        WARN(f"{beat_path}: audio bit_rate not declared in stream metadata; skipping bitrate assert")
    else:
        assert int(audio_br_raw) == 128000 or abs(int(audio_br_raw) - 128000) < 5000, \
            f"{beat_path}: audio bitrate must be 128k, got {audio_br_raw}"
    assert int(a["sample_rate"]) == 44100, f"{beat_path}: sample_rate must be 44100, got {a['sample_rate']}"
    assert int(a["channels"]) == 1, f"{beat_path}: channels must be 1 (mono), got {a['channels']}"

    # (c) Overall bitrate gate — SIZE_BUDGET_VIDEO_V1 1.9 Mbps with 5% guard band
    # FIX: format is at JSON ROOT not per-stream. Use derive_bitrate_bps() to handle N/A.
    overall_bitrate = derive_bitrate_bps(root, beat_path)
    if overall_bitrate > 1_900_000:
        HARD_STOP(
            f"{beat_path}: bit_rate {overall_bitrate} bps > 1,900,000 bps ceiling "
            f"per SIZE_BUDGET_VIDEO_V1. Either re-encode source or open "
            f"SHORTCUT_MODULE_<id>_BITRATE_OVERRIDE_V1 with Kim approval (uses existing "
            f"SHORTCUT_MODULE_* governance pattern, NOT new SHORTCUT_BEAT_* language)."
        )
```

**Citations on the gate:** `SIZE_BUDGET_VIDEO_V1` decision_key (id=296, ACTIVE / HIGH per §0.1 snapshot) for the 1,900,000 bps ceiling. `Production/governance/video-producer_governance.md` §7 for the canonical ffmpeg command + ffprobe assertion code block. `CONCAT_AUDIO_PARITY_V1` decision_key (per §15 finding 1, MUST be registered before Phase C executes if not already — see §6 Directus Writes).

**`inject_silence_track()` helper** uses ffmpeg per the governance Lessons Learned April 25-26 2026 LD: `anullsrc=r=44100:cl=mono,atrim=duration=<seg_dur_s>` — the `atrim` is mandatory (without it `anullsrc` generates infinite silence and the encode hangs). Helper lives in `Production/tools/audio_helpers.py` (TO WRITE in Phase C; or inlined in `assemble_module.py` if simpler).

### §3.5 R5 — Directus LD verification snapshot at Phase 0

Per Cursor concern: prior plans assumed LD references would be valid at execution time. They might not be — schema migrates, statuses change, decision keys get superseded. **Resolution: §0.1 above mandates the snapshot. The 21-key snapshot taken at spec author time is preserved at `Production/Event_1/.preflight_evidence/V59_STREAM_BF_SPEC_ld_snapshot.json` as a baseline.** The executing session re-runs the snapshot at Phase 0 and compares — any drift since spec authoring time is surfaced before any phase begins.

---

## §4. Implementation Phases

Each phase is a discrete unit of work executable in one Sonnet session (with Opus escalation per CLAUDE.md Rule 26 if a 2nd patch fails or cross-system architectural decision surfaces). Phases run **sequentially** — Phase A unblocks B, B unblocks C, C unblocks D.

### §4.1 Phase A — manifest_helpers.py (Tier A, ~1-2h)

**Goal:** Create `Production/tools/manifest_helpers.py` per R1.

**Steps:**
1. Phase 0 LD snapshot per §0.1.
2. `ls Production/tools/manifest_helpers.py` MUST return error. HALT if file exists.
3. Read `Production/contracts/MANIFEST_SCHEMA_V1.json` `definitions.ModuleEntry.properties.phaseBoundaries` to confirm exact named-object key spelling (`story_start_ms` / `phase_b_start_ms` / `phase_b_end_ms` — confirmed at author time but executing session re-confirms).
4. Write `Production/tools/manifest_helpers.py` with the three signatures from R1 implemented. Type annotations per Python 3.9+ (the system Python on Kim's Mac).
5. Write `Production/tools/tests/test_manifest_helpers.py` covering: (a) named-object output for each of the 3 historical key-spellings; (b) ValueError on out-of-order boundaries; (c) ValueError on missing keys; (d) hex-string output of compute_app_compat_content_hash; (e) FileNotFoundError on missing file.
6. `python3 -m py_compile Production/tools/manifest_helpers.py` (Phase 2.5 gate).
7. `python3 -m pytest Production/tools/tests/test_manifest_helpers.py -v`.
8. Register Asset / log: append `prod_activity_log` row `MANIFEST_HELPERS_PY_CREATED` with details JSON `{file_path, lines, sha256, task_id}` via `try_post_or_queue`.
9. Phase 7 proof: paste pytest stdout + py_compile stdout into Phase 7 verification table.

**Done when:** All R1 signatures implemented, tests pass, file registered, prod_activity_log row landed (read-back confirmed).

### §4.2 Phase B — prod_assets schema fields + register_asset signature (Tier B, ~2-3h)

**Goal:** Add `cdn_url`, `manifest_published_at`, `codec_recipe_hash` to `prod_assets`. Update `register_asset` to accept and persist them.

**Steps:**
1. Phase 0 LD snapshot.
2. Live schema query: `GET /fields/prod_assets` to confirm current shape. HALT if any of the 3 fields ALREADY exist with different types — surfaces another session created them.
3. Add the 3 fields via Directus Admin UI OR via `lib/directus.py::create_field` (depending on Kim preference — see §13 Open Kim Decision 4). Suggested types: `cdn_url=string(2048, nullable)`, `manifest_published_at=timestamp(nullable)`, `codec_recipe_hash=string(64, nullable)`.
4. Update `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` AND `.auto-memory/feedback_directus_schema_canonical.md` with the 3 new field names per CLAUDE.md Rule 35 Write-Time Enforcement.
5. Read `Production/tools/registered_write.py` to find current `register_asset()` signature. Update signature to add `cdn_url=None, manifest_published_at=None, codec_recipe_hash=None` keyword args. Persist via the existing payload assembly path. Read-back-after-write per LD-364.
6. Add Phase B execution-time R3 gate: function `verify_app_hash_encoding()` that grepps the MindfulNest app repo for `digestStringAsync` calls. If any call uses `Encoding.Base64`, raises `ReleaseBlockerError` with structured message. Called from Phase D r2_atomic_publish.py before any upload.
7. Update `Production/tools/find_asset.py` `--fields` enum (or equivalent) to include the 3 new fields so Kim can query them.
8. Smoke: write a fresh `prod_assets` row using all new fields populated; read back; assert all 3 fields present with submitted values.
9. `python3 -m py_compile Production/tools/registered_write.py` (Phase 2.5).
10. Register: `prod_activity_log` row `PROD_ASSETS_R2_FIELDS_ADDED` with details JSON `{fields_added, schema_query_evidence_path, smoke_row_id}`.

**Done when:** 3 fields exist on `prod_assets`, register_asset persists them, schema reference doc updated, find_asset can query them, smoke row created and read back.

### §4.3 Phase C — assemble_module.py 10-step pipeline + Steps 11-13 (Tier B, ~6-10h)

**Goal:** Create `Production/tools/assemble_module.py` per R2 + R4.

**Steps:**
1. Phase 0 LD snapshot.
2. `ls Production/tools/assemble_module.py` MUST return error. HALT if file exists. (Confirmed empty at author time.)
3. Read `Production/contracts/ASSEMBLE_MODULE_CONTRACT.md` END-TO-END (already done at author time; executing session re-reads).
4. Read `Production/PIPELINE_BRAIN_v1.md` §Normalization for canonical codec spec.
5. Implement Steps 1-10 + Steps 11-13 per §3.2.
6. Implement Step 1.5 per §3.4 (CONCAT_AUDIO_PARITY_V1 + SIZE_BUDGET_VIDEO_V1 gate).
7. Implement `inject_silence_track()` helper.
8. Per-stage logging (DS-14 Multi-stage pipeline risk class): every step emits a structured log line `{step, status, duration_s, output_path}` to `prod_activity_log` action `ASSEMBLE_MODULE_STEP_<N>` for audit. Compose into a single `prod_activity_log` action `ASSEMBLE_MODULE_RUN` with details JSON containing all per-step logs + final 7 artifact paths.
9. CLI: `python3 Production/tools/assemble_module.py --module <id> --beats <dir> --audio <mp3> --metadata <json> --out <dir>` reads inputs, executes 10+3 steps, writes 7 artifacts.
10. Layer 6 smoke test (DS-13): assemble Event 0 (per v6 §2 Stream B Mandatory Spike). HARD-FAIL if any of the 10 canonical steps fails. Output: 7 artifacts at `Production/Event_0/output/`.
11. Phase 6.8 media golden probe (per zero-error-qa skill) on Event 0 output: duration ≤±50ms, 24fps exactly, A/V sync <100ms, B-frames=0, decode errors=0.
12. `python3 -m py_compile Production/tools/assemble_module.py` (Phase 2.5).
13. Register the Event 0 output artifacts in `prod_assets` via `register_asset` (with `codec_recipe_hash` populated; `cdn_url=None` until Phase D upload; `manifest_published_at=None` until Phase D publish).

**Done when:** Event 0 produces all 7 artifacts, all 10+3 steps pass, golden probe green, all 7 artifacts registered.

### §4.4 Phase D — r2_upload.py + r2_atomic_publish.py + LD-404 AMEND + Firebase-to-R2 cutover (Tier C, ~8-12h)

**Goal:** Build the Stream F deployment pipeline.

**Steps:**
1. Phase 0 LD snapshot. Confirm CDN_CLOUDFLARE_R2_V1 (LD-432) still active.
2. Read `Production/contracts/R2_DEPLOYMENT_CONTRACT.md` end-to-end.
3. **Sub-decision boto3 vs urllib (§13 Open Kim Decision 3):** decide and stick. Recommended: boto3 (R2 S3-compatible API works with boto3 client out-of-box; saves implementing AWS Sig V4 by hand). Trade-off: boto3 dep weight (~50 MB) acceptable for Kim-side production tooling.
4. Author `Production/scripts/r2_upload.py`:
   - Reads `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID`, `R2_BUCKET_NAME` from env (LD-405 secrets management).
   - `upload(local_path, key, content_type, cache_control)` puts the object with the supplied Cache-Control header.
   - `head(key)` returns `{ETag, Content-Length, Content-Type, Cache-Control}`.
   - `range_get(key, byte_range)` issues `Range: bytes=X-Y` and returns response bytes + status.
   - Logs to `prod_activity_log` action `R2_UPLOAD_<key>` per call.
5. Author `Production/scripts/r2_atomic_publish.py`:
   - Implements 5-step atomic publish from `R2_DEPLOYMENT_CONTRACT.md` §Atomic publish order.
   - Calls Phase B `verify_app_hash_encoding()` BEFORE step 1 — RELEASE BLOCKS if app uses base64 encoding.
   - Step 4 publishes BOTH `manifest.json` (current) AND `manifest_v_<catalogVersion>.json` (immutable).
   - Step 5 smoke test: synthetic client fetches manifest + first asset + verifies SHA-256.
   - Atomic abort on any failure: prior `manifest.json` remains live.
6. **Amend LD-404** (§13 Open Kim Decision 1: Phase A vs Phase D timing). Two paths:
   - **In-place amend (preferred — preserves LD number, simpler audit):** PATCH `prod_locked_decisions[id=404]` `decision_text` field to add a note that `phaseBoundaries` MUST be the named-object form per LD-412. `notes` field appended with reference to this spec.
   - **Replace (only if in-place amend is rejected by Kim):** POST new LD `MANIFEST_SCHEMA_V1_PHASE_BOUNDARIES_NAMED_V1`; PATCH LD-404 `superseded_by_id` to point at new LD; mark LD-404 status=superseded.
7. **Firebase-to-R2 cutover per LD-432:**
   - `Production/scripts/migrate_firebase_to_r2.py` (separate script — execution time: probably 30-60 min for all currently-uploaded assets, depending on count).
   - For each `prod_assets` row currently pointing at a Firebase Storage URL: download → re-upload to R2 → PATCH row with new `cdn_url` → verify HEAD.
   - At cutover moment: `manifest.json` overwritten with R2-only URLs in single atomic operation.
   - Firebase Storage bucket retained read-only for 30 days as rollback path; deletion follow-up task at day 31.
8. Layer 6 smoke (DS-13): real iPad 9 device fetch of Event 0 from R2 URL. First-byte latency ≤ 5s on simulated 3G per `R2_DEPLOYMENT_CONTRACT.md` §First-byte / first-frame test. Phase 6.7 mobile E2E.
9. Phase 6.5 live boundary probe per `r2-range-cache-probe.mjs` if it exists, else implement inline: 10 random `Range: bytes=X-Y` probes, all must return 206 + correct bytes + `Cache-Control: public, max-age=31536000, immutable` + `ETag` matching expected hash.
10. Register all 6 new LDs (per §6 Directus Writes; row 7 `MANIFEST_PHASEBOUNDARIES_NAMED_OBJECT_LOCK_V1` dropped per LOCKED Decision 5).

**Done when:** Event 0 hash-named URL is live on R2; HEAD/range probes green; iPad 9 first-frame ≤5s on 3G; manifest.json published; all 6 LDs registered + LD-404 amended.

---

## §5. Files Created / Modified

### §5.1 Created (NEW)

| Path | Phase | Purpose |
|---|---|---|
| `Production/tools/manifest_helpers.py` | A | R1 — phase_boundaries reformatter + LD-412 validator + app-compat hash helper |
| `Production/tools/tests/test_manifest_helpers.py` | A | Unit tests for the 3 functions |
| `Production/tools/assemble_module.py` | C | R2 — canonical 10-step pipeline + Steps 11-13 finalization |
| `Production/tools/audio_helpers.py` | C | `inject_silence_track()` helper for CONCAT_AUDIO_PARITY_V1 (or inlined in assemble_module.py — execution session decides) |
| `Production/scripts/r2_upload.py` | D | R2 S3-compatible upload + HEAD + range_get |
| `Production/scripts/r2_atomic_publish.py` | D | 5-step atomic publish per R2_DEPLOYMENT_CONTRACT.md |
| `Production/scripts/migrate_firebase_to_r2.py` | D | One-shot Firebase Storage → R2 migration script (LD-432 cutover) |
| `Production/Event_1/.preflight_evidence/<phase>_ld_snapshot.json` | 0 | R5 — LD snapshot artifact, one per phase |

### §5.2 Modified

| Path | Phase | Change |
|---|---|---|
| `Production/tools/registered_write.py` | B | `register_asset()` signature adds `cdn_url`, `manifest_published_at`, `codec_recipe_hash` kwargs |
| `Production/tools/find_asset.py` | B | `--fields` enum adds the 3 new fields (or equivalent query interface) |
| `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` | B | New section documenting the 3 new `prod_assets` fields per Rule 35 Write-Time Enforcement |
| `.auto-memory/feedback_directus_schema_canonical.md` | B | Mirror of the above |
| `Production/tools/upload_module.py` | C/B (annotation) | Add `# DEPRECATED — replaced by manifest_helpers.compute_app_compat_content_hash() per V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md R3.` immediately above `sha256_file()` (lines ~155-165). Removal OUT OF SCOPE. |
| `Production/contracts/MANIFEST_SCHEMA_V1.json` | D | If LD-404 AMEND chooses replace path, schema $id banner updated to v2; if in-place, no schema file change required. |

### §5.3 Out of repository (Directus / cloud-side)

| Resource | Phase | Change |
|---|---|---|
| `prod_assets` collection schema | B | 3 new fields added |
| `prod_locked_decisions` rows | A-D | 7 new LD rows + 1 LD AMEND (per §6) |
| `prod_activity_log` rows | A-D | One row per phase milestone + per assemble_module step |
| Cloudflare R2 bucket `mindfulnest-cdn` | D | New bucket OR existing bucket re-keyed; assets uploaded with hash-named keys; manifest.json published |
| Firebase Storage bucket | D | Retained read-only for 30 days post-cutover; deletion follow-up |

---

## §6. Directus Writes

All writes go through `Production/lib/directus.py::try_post_or_queue` per LD-364 + CLAUDE.md Rule 35. Read-back-after-write contract enforced by helper.

### §6.1 Locked decisions to register

Per Kim directive: 7 new + 1 AMEND (LD-404). Each row is `{decision_key, decision_name, decision_text, source_document, task_category, severity, scope_domain, status, date_locked, notes}`. Severity is HARD/SOFT (per DS-9 schema migration 2026-05-04 — old enums still accepted but use HARD/SOFT for new writes).

| # | decision_key | severity | scope_domain | task_category | What it locks |
|---|---|---|---|---|---|
| 1 | `STREAM_B_PHASE_BOUNDARIES_REFORMATTER_V1` | HARD | production | tech_stack | manifest_helpers.py exists; `phase_boundaries_to_manifest_form()` is the only sanctioned reformatter; positional/array form input rejected; output ALWAYS named-object per LD-412. |
| 2 | `STREAM_B_HASH_HEX_CANONICAL_V1` | HARD | production | tech_stack | Single hex hash form per R3. `prod_assets.sha256` is canonical. Manifest `output_hash` matches expo-crypto digestStringAsync HEX default. base64 form OBSOLETE post-R2 cutover. RELEASE-BLOCKER fallback to dual-form if app uses non-default encoding. |
| 3 | `STREAM_B_ASSEMBLE_MODULE_CLI_V1` | HARD | production | tech_stack | assemble_module.py is the canonical 10-step pipeline + Steps 11-13 finalization. CLI signature locked. All 7 declared output artifacts required. Cache key is the 5-tuple discriminator from §3.2. |
| 4 | `STREAM_F_R2_UPLOAD_V1` | HARD | production | infra | r2_upload.py is the canonical upload entry point. Reads R2_* secrets from env per LD-405. Logs every call to prod_activity_log. |
| 5 | `STREAM_F_R2_ATOMIC_PUBLISH_V1` | HARD | production | infra | r2_atomic_publish.py implements the 5-step atomic publish from R2_DEPLOYMENT_CONTRACT.md. Pre-publish gate: verify_app_hash_encoding() per R3. Atomic abort on any step failure. |
| 6 | `STREAM_F_FIREBASE_TO_R2_CUTOVER_V1` | HARD | infra | infra | Firebase Storage is superseded by R2 per LD-432. Cutover executed via migrate_firebase_to_r2.py. Firebase bucket retained 30 days read-only post-cutover. |
| ~~7~~ | ~~`MANIFEST_PHASEBOUNDARIES_NAMED_OBJECT_LOCK_V1`~~ | **DROPPED PER LOCKED DECISION 5 (2026-05-08)** — LD-412 `PHASE_BOUNDARIES_NAMED_OBJECT_V1` already covers this scope. Cite LD-412 in all places this LD was previously referenced. Row removed; total new LDs = 6. |

### §6.2 LD AMEND — LD-404 MANIFEST_SCHEMA_V1

**Decision Kim must make at execution time (§13 Open Kim Decision 1):** in-place vs replace.

**In-place amend (recommended):**
```
PATCH /items/prod_locked_decisions/404
{
  "decision_text": "<existing decision_text>\n\nAMENDED 2026-XX-XX per V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md: phaseBoundaries field MUST conform to LD-412 PHASE_BOUNDARIES_NAMED_OBJECT_V1 named-object form ({story_start_ms, phase_b_start_ms, phase_b_end_ms}). Positional/array form is forbidden. Manifest entries that fail validate_phase_boundaries() are rejected by r2_atomic_publish.py.",
  "notes": "<existing notes>; amended via STREAM_BF_SPEC_v1 Phase D"
}
```
Read-back: confirm `decision_text` contains "AMENDED" substring AND `phaseBoundaries` reference.

**Replace path (only if in-place rejected):**
```
POST /items/prod_locked_decisions
{
  "decision_key": "MANIFEST_SCHEMA_V1_NAMED_PHASE_BOUNDARIES_V2",
  "decision_text": "...",
  ...
}
PATCH /items/prod_locked_decisions/404
{
  "superseded_by_id": <new id>,
  "status": "superseded"
}
```

### §6.3 Activity-log writes

| action | Phase | When |
|---|---|---|
| `MANIFEST_HELPERS_PY_CREATED` | A | After Phase A Step 8 |
| `PROD_ASSETS_R2_FIELDS_ADDED` | B | After Phase B Step 8 |
| `ASSEMBLE_MODULE_PY_CREATED` | C | After Phase C Step 12 |
| `ASSEMBLE_MODULE_STEP_<N>` | C | One per step during a run (debug detail in `details.step_log`) |
| `ASSEMBLE_MODULE_RUN` | C | After every CLI invocation, success or fail |
| `R2_UPLOAD_<key>` | D | One per upload |
| `R2_ATOMIC_PUBLISH_<catalogVersion>` | D | One per atomic publish |
| `FIREBASE_TO_R2_CUTOVER_COMPLETE` | D | Once at cutover |
| `KIM_BROWSER_SMOKE_PASSED` | D | After Kim's verbatim confirmation per DS-21 (mechanically required for any `<phase>_COMPLETE` write per LD `BROWSER_SMOKE_MECHANICAL_GATE_V1`) |
| `<phase>_COMPLETE` | A/B/C/D | Each phase boundary, gated by DS-21 |

### §6.4 Schema deviations to consult before writing

Per CLAUDE.md Rule 35: BEFORE composing any of the above payloads:
- Re-read `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md`.
- For `prod_locked_decisions`: severity is HARD/SOFT for new writes (not CRITICAL/HIGH); status enum is `{active, superseded}` only; `superseded_by_id` is one-directional (PATCH the OLD row, not the new one); `task_category` enum does NOT include `app_animation` — use `tech_stack` for app-dev or `infra` for infra. `scope_domain` enum is `{content, production, app-dev, infra, cross-cutting}`.
- For `prod_activity_log`: uses `action` (not activity_type), `details(JSON)` (not notes), `performed_by`, `created_at(auto)`. Bare `summary` field is dropped silently — use `details.summary`.
- For uncatalogued field changes (the 3 new prod_assets fields): query `GET /fields/prod_assets` first.

---

## §7. Error Cases

### §7.1 Phase A error cases

| Error | Detection | Handling |
|---|---|---|
| `manifest_helpers.py` already exists at execution time | Phase A Step 2 `ls` returns success | HALT. Surface to Kim — concurrent build. |
| `MANIFEST_SCHEMA_V1.json` `phaseBoundaries` definition has changed since spec authoring | Phase A Step 3 schema diff | HALT. Re-spec is required because R1 signatures encode the schema. |
| Tests fail | Phase A Step 7 pytest non-zero exit | Fix code; do NOT relax tests. |

### §7.2 Phase B error cases

| Error | Detection | Handling |
|---|---|---|
| 3 new fields already exist with different types | Phase B Step 2 `/fields/prod_assets` query | HALT. Surface — another session created them with possibly-different types. |
| `register_asset()` payload assembly drops new fields silently | Phase B Step 8 smoke + read-back | Per CLAUDE.md Rule 35: this IS the silent_write_failure class — HARD STOP and append the deviation to `DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` before continuing. |
| App uses `Encoding.Base64` in expo-crypto | Phase B Step 6 `verify_app_hash_encoding()` | RELEASE-BLOCKER. Either change app to HEX (preferred) OR fall back to dual-form per §13. |

### §7.3 Phase C error cases

| Error | Detection | Handling |
|---|---|---|
| Per-beat clip not normalized | Step 1 ffprobe codec mismatch | HARD STOP per LD-284. Trigger normalization pass + retry. |
| Audio stream missing on input | Step 1.5 audio_streams==0 | Inject silence per CONCAT_AUDIO_PARITY_V1; retry parity check; HARD STOP if injection fails. |
| Bitrate > 1.9 Mbps on input | Step 1.5 overall_bitrate > 1_900_000 | HARD STOP per SIZE_BUDGET_VIDEO_V1. Re-encode source OR open SHORTCUT_BEAT_<id>_BITRATE_OVERRIDE_V1. |
| Concat output > 80 MB | Step 11 size gate | HARD STOP per LD-283. Compress further OR open SHORTCUT_MODULE_<id>_CEILING_V1 with Kim approval. |
| Duration > 7 minutes | Step 11 duration gate | HARD STOP per LD-283. Cut content OR open SHORTCUT_MODULE_<id>_CEILING_V1. |
| MOOV after MDAT | Step 5 mp4 atom parse | HARD STOP. Re-mux with `+faststart`; if persists, source has structural issue — escalate. |
| 1-frame decode fails | Step 7 ffmpeg exit non-zero | HARD STOP. Source has corruption; re-render upstream. |
| Full-duration smoke fails | Step 8 ffmpeg exit non-zero | HARD STOP. Mid-stream corruption; ffmpeg concat edge case — escalate. |
| `output_hash` collision with prior module | Step 9 catalog sanity check | HARD STOP. Either two modules really are byte-identical (suspicious) or hash compute is broken. Investigate. |
| Listen-through file generation fails | Step 11 (if Phase B audio missing) | Soft fail — log warning; assemble_module continues; Kim review file unavailable for this run. |
| Directus write fails (silent_write_failure) | Step 12 read-back | HALT per Rule 35. Surface mismatch + append deviation to schema reference doc. |

### §7.4 Phase D error cases

| Error | Detection | Handling |
|---|---|---|
| R2 credentials missing in env | Phase D r2_upload.py init | HARD STOP. Surface to Kim with env var names. |
| HEAD ETag mismatch post-upload | Atomic publish step 2 | Abort publish; prior manifest stays live. Re-upload. |
| Range-request returns 200 instead of 206 | Atomic publish step 3 | Abort publish. R2 misconfiguration — investigate worker config. |
| Smoke test fails | Atomic publish step 5 | Abort publish; prior manifest stays live. SHA-256 mismatch likely — recompute hash and retry. |
| LD-404 AMEND fails to read back | Phase D Step 6 | HALT. Schema migration may have changed `decision_text` field to read-only. Investigate. |
| Firebase migration leaves stale `cdn_url` pointing at Firebase | Phase D Step 7 | Per-row PATCH guarantees atomic per-asset cutover; if a row is missed, find_asset reports it; manual PATCH recovery. |
| iPad 9 first-frame > 5s on 3G | Phase D Step 8 mobile E2E | Investigate +faststart application + R2 worker config. Block G1 until passing. |

### §7.5 Cross-phase error cases

| Error | Detection | Handling |
|---|---|---|
| LD snapshot drift between Phase 0 and execution | Phase 0 §0.1 re-run | Surface diff to Kim; do not auto-resolve. Spec may need re-author. |
| Schema reference doc out of sync with live `/fields` | Rule 35 silent_write_failure | Append deviation; re-author the schema reference section. |
| Phase A produces a file with signatures that don't match the ones in §3.1 | Phase B import or call site type error | Backtrack to Phase A; re-author. Do not patch downstream. |

---

## §8. Verification

### §8.1 Per-phase verification gates

Each phase emits a Phase 7 verification table per `zero-error-qa` skill. Required cells:

| Phase | Critical checks (all PASS for phase COMPLETE) |
|---|---|
| A | py_compile clean; pytest all green; all 3 functions invocable; activity log row read back |
| B | `/fields/prod_assets` returns 3 new fields with correct types; `register_asset()` smoke row read back with all 3 fields populated; schema reference doc updated; py_compile clean |
| C | Event 0 produces all 7 declared artifacts; ffprobe + 1-frame + full-duration all green; size ≤ 80 MB; duration ≤ 7 min; bitrate ≤ 1.9 Mbps; hash matches `compute_app_compat_content_hash()`; 7 prod_assets rows registered |
| D | r2_upload.py + r2_atomic_publish.py py_compile clean; Event 0 fetchable from `cdn.mindfulnest.app/modules/E0.<sha-12>.mp4`; HEAD shows `Cache-Control: public, max-age=31536000, immutable` + ETag; 10 random range probes all 206; first-byte ≤ 5s on simulated 3G; LD-404 amended (read back showing AMENDED substring); 6 new LDs registered (read back showing status=active) |

### §8.2 Layer 6 smoke per DS-13

For each phase boundary, require KIM_BROWSER_SMOKE_PASSED row OR (if no UI surface in phase) `BROWSER_SMOKE_DEFERRED` audit row + env var override per DS-21. Phase A + B may legitimately defer (no UI). Phase C may defer if Kim is not in the loop (but assemble_module CLI run at terminal is itself a smoke). Phase D requires KIM_BROWSER_SMOKE_PASSED for the cutover (Kim verifies fetch URL works in browser; Kim verifies a real iPad 9 plays Event 0 from R2).

### §8.3 Tail-end independent verifier (DS-17)

After Phase D Step 10, spawn an Explore agent with prompt: "Verify the executed Stream B+F build per V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md. Independent end-to-end check: (1) `find_asset.py --module E0` returns the registered asset with cdn_url populated; (2) `curl -I <cdn_url>` returns expected headers; (3) `prod_locked_decisions` query for the 7 new LD keys returns all active; (4) LD-404 decision_text contains AMENDED substring. Spot-check 5 of the 10 assemble_module log rows for completeness. Report PASS or FAIL with evidence."

---

## §9. Rollback

### §9.1 Phase A rollback

`rm Production/tools/manifest_helpers.py Production/tools/tests/test_manifest_helpers.py`. Mark `prod_activity_log` row `MANIFEST_HELPERS_PY_CREATED` with action `MANIFEST_HELPERS_PY_REMOVED`. No downstream cleanup needed (Phase A ships an isolated library).

### §9.2 Phase B rollback

The 3 new `prod_assets` fields can be dropped via Directus Admin OR `lib/directus.py::delete_field`. `register_asset()` signature reverted via git. Existing rows that were written with the new fields are NOT auto-cleaned — Phase B rollback is partial-data-loss; surface to Kim. **Recommendation: do NOT roll back Phase B if any rows have been written with the new fields. Roll forward by fixing the issue.**

### §9.3 Phase C rollback

`rm Production/tools/assemble_module.py Production/tools/audio_helpers.py`. Revert `prod_activity_log` rows via PATCH `action='ROLLED_BACK'` (do NOT delete — audit trail). Existing Event 0 output artifacts at `Production/Event_0/output/` are git-untracked and can be deleted. `prod_assets` rows registered in Step 12 PATCHed with `status=superseded`.

### §9.4 Phase D rollback

R2 cutover rollback per `R2_DEPLOYMENT_CONTRACT.md` §Rollback procedure:
1. Identify last-known-good `catalogVersion` from versioned manifest snapshots.
2. Copy that versioned manifest to `manifest.json` (overwriting current).
3. Confirm via HEAD + smoke test.
4. Set Remote Config `force_manifest_version` flag to pin app to rolled-back manifest.

Firebase-to-R2 cutover rollback (within 30-day retention window): repoint `cdn_url` field on affected `prod_assets` rows back to Firebase Storage URL; republish manifest pointing at Firebase URLs; flip Remote Config flag.

LD-404 AMEND rollback:
- In-place path: PATCH `decision_text` to remove the AMENDED block.
- Replace path: PATCH new LD `status=superseded`; PATCH LD-404 `superseded_by_id=null` and `status=active`.

The 6 new LDs can be PATCHed `status=superseded` rather than deleted (audit trail).

---

## §10. Out of Scope

The following are NOT covered by this spec — explicitly listed to prevent scope creep:

1. **Removal of `upload_module.py:155-165 sha256_file()`.** The function is marked OBSOLETE in Phase C/B but NOT removed. There may be uncommitted callers; removal happens in a follow-up audit task.
2. **Per-arc R2 publish orchestration.** This spec covers Event 0 + per-module publish. Per-arc bundling (10 arcs × 6 modules) requires a separate orchestration script that calls r2_atomic_publish.py per module — out of this spec, follow-up.
3. **CDN edge cache flush procedure.** Cloudflare R2 has its own cache layer; manifest.json `no-cache, must-revalidate` should bypass, but production verification + automation of edge flushes is out of scope.
4. **Backup R2 bucket region.** `R2_DEPLOYMENT_CONTRACT.md` open question; out of this spec, follow-up.
5. **Synthetic smoke test client implementation choice.** `R2_DEPLOYMENT_CONTRACT.md` open question (dedicated CI runner vs piggybacked on Maestro); out of this spec, decision deferred.
6. **`manifest.json` schema migration support in app code.** App-side validator that accepts new shape per LD-404 AMEND is a Stream C task; out of this spec.
7. **EAS Build / TestFlight integration.** Stream B+F output feeds Stream C; the Stream C catalog wiring is a separate spec.
8. **Refactor of `Production/lib/directus.py` `try_post_or_queue` for batched writes.** Current per-row write is sufficient for this spec's volume; batching is a perf optimization, not in scope.
9. **Cost monitoring / R2 spend dashboard.** Tracked in GOV-19 elsewhere; out of this spec.
10. **`.cursor/rules/` updates** referencing the new LDs. Stream G governance task; out of this spec.

---

## §11. Dependencies

### §11.1 Phase A depends on

- `Production/contracts/MANIFEST_SCHEMA_V1.json` exists (CONFIRMED 2026-05-07).
- LD-412 `PHASE_BOUNDARIES_NAMED_OBJECT_V1` active (CONFIRMED via §0.1 snapshot).
- LD-404 `MANIFEST_SCHEMA_V1` active (CONFIRMED).
- Python 3.9+ on the executing machine (Kim's Mac default).

### §11.2 Phase B depends on

- Phase A complete (`compute_app_compat_content_hash()` exists for the verify_app_hash_encoding step).
- Live `prod_assets` schema queryable via `/fields/prod_assets`.
- LD-421 `ASSET_FINDABILITY_OVERHAUL_V1` + LD-422 `ASSET_FINDABILITY_BUILD_V1` active (CONFIRMED — `register_asset()` exists in `Production/tools/registered_write.py`).
- MindfulNest app repo accessible (for `verify_app_hash_encoding()` grep).

### §11.3 Phase C depends on

- Phase A + Phase B complete.
- Event 0 inputs prepared: per-beat normalized clips per LD-284 + Phase B audio mix MP3 per LD-281 + module metadata JSON.
- ffmpeg + ffprobe in PATH (`which ffmpeg && which ffprobe`).
- Optional: `mp4dump` (Bento4) OR Python `pymp4` library for MOOV-at-front parsing.

### §11.4 Phase D depends on

- Phase A + B + C complete.
- Cloudflare R2 bucket provisioned + access keys generated.
- R2_* env vars set: `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID`, `R2_BUCKET_NAME`.
- Domain `cdn.mindfulnest.app` DNS pointing at R2 (CNAME or worker route).
- LD-432 `CDN_CLOUDFLARE_R2_V1` active (CONFIRMED).
- LD-405 `SECRETS_MGMT_LOCKED_PRELAUNCH_V1` active (CONFIRMED).
- iPad 9 device available for first-byte / first-frame test.

### §11.5 Cross-phase dependencies

- `Production/lib/directus.py::try_post_or_queue` importable at session start (existence check per Rule 35). HALT if not.
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` readable + writable.

---

## §12. Cursor Cross-Review Prompt

For Tier B execution where Kim wants a second pair of eyes (per Phase 3 of zero-error-qa skill — optional), paste this spec into Cursor and ask:

> Cross-review V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md against:
>
> 1. ASSEMBLE_MODULE_CONTRACT.md — does §3.2 R2 canonical 10-step pipeline correctly capture all 12 declared processing steps and 7 declared output artifacts? Flag drift.
> 2. R2_DEPLOYMENT_CONTRACT.md — does §3.4 R4 / §4.4 Phase D Step 5 correctly replicate the 5-step atomic publish order? Flag drift.
> 3. MANIFEST_SCHEMA_V1.json — does §3.1 R1 `phase_boundaries_to_manifest_form()` return shape match the JSON schema's `phaseBoundaries` definition? Flag drift.
> 4. CLAUDE.md Rule 19 (no error paths) + Rule 26 (Opus escalation) + Rule 35 (Directus schema) + Rule 8.5 (LipSync 10s — irrelevant here, but check for accidental wires) — does this spec leave any silent-failure path open?
> 5. video-producer_governance.md §7 — does §3.4 Step 1.5 ffprobe HARD STOP gate use the same 1,900,000 bps threshold + 5% guard band stated in the governance file?
> 6. expo-crypto npm docs — confirm digestStringAsync default encoding is HEX (R3 hangs on this — if base64, the entire R3 strategy inverts).
> 7. boto3 R2 S3-compat docs — confirm S3-compatible API works with boto3 client out-of-box for Cloudflare R2 (§13 Open Decision 3 informs this).
> 8. LD-412 PHASE_BOUNDARIES_NAMED_OBJECT_V1 vs the Kim-listed new LD MANIFEST_PHASEBOUNDARIES_NAMED_OBJECT_LOCK_V1 — surface whether they overlap (§15 finding 2). Recommend close vs keep both.
>
> Return findings in `[CRITICAL|HIGH|MED] — <weakness> — <proposed mitigation>` format. Also flag any over-engineering (anything in this spec that goes beyond the 5 R-resolutions Kim asked for).

---

## §13. Notes for Executing Sessions + Open Kim Decisions

### §13.1 Open Kim Decisions (3 — collapsed from 4 because R3 absorbed dual-hash)

#### Open Decision 1 — phaseBoundaries shape AMEND timing (Phase A vs Phase D)

**Question:** When does the LD-404 AMEND land?
- **Option A (Phase A):** Amend LD-404 in Phase A, BEFORE writing manifest_helpers.py. Manifest_helpers.py asserts the amended state at import time. Pro: clean dependency graph. Con: spec gets gated on Kim's amend approval before any code work begins.
- **Option B (Phase D, recommended):** Manifest_helpers.py is authored against the CURRENT LD-404 wording (which already accepts named-object form per the schema JSON file's `phaseBoundaries` definition). The AMEND in Phase D is a clarifying note that the named-object form is REQUIRED (closing positional/array form). Pro: A/B/C unblocked immediately. Con: brief window where `MANIFEST_SCHEMA_V1.json` wording is more permissive than executing intent.

**Recommendation:** Option B (Phase D AMEND). The schema JSON is already named-object-only — the AMEND is closing a wording ambiguity, not changing structure.

**LOCKED PER KIM 2026-05-08:** Option B — Phase D. Manifest_helpers.py authored against current LD-404 wording; AMEND lands in Phase D as a clarifying note that named-object form is REQUIRED.

#### Open Decision 2 — R2 cutover timing (now vs V1.1)

**Question:** Does the Firebase-to-R2 cutover (LD-432, Phase D Step 7) execute now (this spec) or later (V1.1)?
- **Option A (now):** Execute migrate_firebase_to_r2.py during Phase D. All currently-uploaded assets relocated to R2. Firebase retained read-only for 30 days.
- **Option B (V1.1):** Phase D builds the upload + atomic publish infrastructure; new uploads go to R2; existing Firebase URLs grandfathered. Cutover script runs as a follow-up.

**Recommendation:** Option A (now), for two reasons. (a) LD-432 `CDN_CLOUDFLARE_R2_V1` is locked HIGH; deferring violates Rule 19's "no shortcuts." (b) The 30-day Firebase retention provides a clean rollback window; longer-lived dual-source state risks drift. The cost is ~30-60 min of compute on the cutover script.

**LOCKED PER KIM 2026-05-08:** Option B — V1.1. Phase D builds upload + atomic publish infrastructure; new uploads go to R2; existing Firebase URLs grandfathered. Cutover script runs as a follow-up post-V1. Rationale: Phase D scope already substantial; cutover is a separable migration that can land independently without blocking G1 serial milestone. The Rule 19 framing in my recommendation was overstated — locked LD-432 binds the destination (R2) but doesn't bind the timing of legacy migration.

#### Open Decision 3 — boto3 vs urllib for r2_upload.py

**Question:** Does r2_upload.py use boto3 (S3-compatible client) or hand-rolled urllib + AWS Sig V4?
- **Option A (boto3, recommended):** Adds boto3 dep (~50 MB). Out-of-box S3-compat with Cloudflare R2. Multipart upload + retry logic for free. ~200 LOC for r2_upload.py.
- **Option B (urllib):** Zero new deps. Hand-roll AWS Signature V4. ~600+ LOC. Higher bug surface.

**Recommendation:** Option A (boto3). Production-side tooling weight is acceptable; correctness > dep size. Also: boto3 already a transitive dep elsewhere in Kim-side tooling (verify at execution time).

**LOCKED PER KIM 2026-05-08:** Option B — urllib + AWS Sig V4 hand-rolled. Rationale: avoids Rule 26 first-integration-with-new-vendor Opus escalation triggering mid-execution (boto3 is not in `Production/API_KEYS_MASTER.md`). Higher LOC + bug surface accepted in exchange for execution stability. If hand-rolled implementation surfaces correctness bugs during Phase D, escalate to Kim for boto3 reconsideration with `SHORTCUT_BOTO3_FIRST_INTEGRATION_V1` LD path.

### §13.2 Notes for executing sessions

1. **Read all 5 source contracts AGAIN at execution time.** Do not rely on this spec's paraphrases. The contract files are authoritative; if they have changed since 2026-05-07, surface drift before proceeding.
2. **Phase 0 LD snapshot is MANDATORY at every phase, not just session-start.** Phases run sequentially with possibly-different sessions. Each session re-snapshots.
3. **Confidence annotation per Rule 24 throughout.** Tag every numeric threshold + LD citation. Future-you (or Kim) can challenge `[INFERRED]` claims in one reply.
4. **DS-21 mechanical gate.** Each `<phase>_COMPLETE` row in `prod_activity_log` is rejected by `try_post_or_queue` unless a matching `KIM_BROWSER_SMOKE_PASSED` row exists. For Phase A + B (no UI surface), use the `BROWSER_SMOKE_DEFERRED` audit row + `MN_SKIP_BROWSER_SMOKE_GATE=1` env var override path. Phase D MUST get a real KIM_BROWSER_SMOKE_PASSED.
5. **Rule 26 Opus escalation triggers.** Any of: 2nd failed py_compile patch on `assemble_module.py`; cross-system architectural surfaces (e.g., turns out `expo-crypto` default encoding has changed); apparent LD conflict between LD-412 and LD-404 AMEND wording; first integration with Cloudflare R2 (vendor not in `Production/API_KEYS_MASTER.md` yet — verify at execution); 3+ frustration phrases from Kim. On trigger: pause, state escalation aloud, spawn Opus agent (or 3+3 advocate/counter for second-failed-patch cases) before continuing.
6. **DS-19 standing escape hatches.** STOP and surface to Kim if any fire — listed in §0.2 and re-state in each phase preamble.
7. **Cache write-through pattern for R2 assets.** When `register_asset` persists `cdn_url`, immediately HEAD-check the URL — if 404 (race condition between R2 upload completion and find_asset), the row's `cdn_url` is stamped with status `pending_propagation` and a follow-up job verifies + clears.
8. **Don't refactor while building.** If `Production/tools/registered_write.py` looks like it could be cleaner during Phase B Step 5 — leave it. This spec adds 3 fields. A refactor is a different spec.

---

## §14. Pre-Execution Discipline Checklist

Run this checklist at the start of EVERY phase. If any line cannot be checked, halt + surface.

```
[ ] zero-error-qa skill loaded; Phase 0 classification stated aloud.
[ ] §0.1 LD snapshot taken THIS SESSION; all 15 unique decision keys returned active (or known-missing keys per §15 acknowledged). Note: snapshot may include duplicate raw rows per multi-path lookup — dedupe by `decision_key` for the active-count check.
[ ] Snapshot saved to Production/Event_<N>/.preflight_evidence/<phase>_ld_snapshot.json.
[ ] `try_post_or_queue` importable from Production/lib/directus.py (existence check per Rule 35).
[ ] Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md re-read; no schema drift since prior phase.
[ ] All 5 source contracts re-read or confirmed unchanged via mtime comparison.
[ ] Working tree git-clean OR all dirty paths belong to this phase (Step 1.6).
[ ] Branch is feature branch, not main (Step 1.6).
[ ] Last gh fetch within 24h (Step 1.6).
[ ] py_compile + pytest baseline run on the file(s) about to be modified (no pre-existing errors that would make this phase's introduced errors invisible).
[ ] Phase output target paths confirmed empty (e.g., `ls Production/tools/manifest_helpers.py` returns "No such file or directory" before Phase A; same for assemble_module.py before Phase C; r2_*.py before Phase D).
[ ] DS-13 Six-Layer Verification plan drafted for this phase (which 6 layers will be smoked, in which order, against which test inputs).
[ ] DS-19 escape hatches reviewed; the ones likely to fire this phase named.
[ ] Rule 26 Opus escalation criteria reviewed; the criteria likely to fire this phase named.
[ ] If Phase B/C/D: any new third-party library proposed has its npm/PyPI URL + README capability claim cited.
[ ] If Phase B: live `/fields/prod_assets` queried and current shape recorded.
[ ] If Phase C: ffmpeg + ffprobe in PATH.
[ ] If Phase D: R2_* env vars set; iPad 9 reachable.
[ ] Confidence annotation per Rule 24 active for this phase.
[ ] No proposed action from this spec is a Rule 19 shortcut (defer / placeholder / "we'll add later"); if any is, escape hatch protocol invoked.
```

---

## §15. Items I May Have Missed

### §15.1 Finding 1 — `CONCAT_AUDIO_PARITY_V1` is NOT registered in `prod_locked_decisions`

**Evidence:** §0.1 LD snapshot taken 2026-05-07 returned `found=False` for `CONCAT_AUDIO_PARITY_V1`. The decision is referenced in `Production/governance/video-producer_governance.md` "Lessons Learned April 25–26, 2026" section as a documented LD key, but no row was ever written to `prod_locked_decisions`. This is a Rule 18 violation (Locked Decision Auto-Registration) — when Kim (or governance) marks something as a locked LD key, it should land in Directus immediately.

**Impact on this spec:** R4 / §3.4 / §4.3 Phase C cite `CONCAT_AUDIO_PARITY_V1` as the governing LD for the audio-stream parity check + silence injection logic. Until the row exists, the citation has nothing to read.

**Resolution at execution time:** Phase C Step 0 (or before) writes the LD row:

```
POST /items/prod_locked_decisions
{
  "decision_key": "CONCAT_AUDIO_PARITY_V1",
  "decision_name": "Concat audio-stream parity check (silence injection before ffmpeg concat)",
  "decision_text": "Before ANY ffmpeg concat demuxer operation, run ffprobe -show_streams on EVERY input segment and confirm each has both codec_type=video AND codec_type=audio. If any segment lacks audio, inject a synthesized silent stream: anullsrc=r=44100:cl=mono,atrim=duration=<segment_duration_s> (the atrim is mandatory — without it, anullsrc generates infinite silence). Concat demuxer silently drops ALL audio from the entire output when even one input lacks an audio stream. Failure is silent; the output looks correct until playback. Origin: Production/governance/video-producer_governance.md Lessons Learned April 25-26 2026.",
  "source_document": "video-producer_governance.md + V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md §3.4",
  "task_category": "production",
  "scope_domain": "production",
  "severity": "HARD",
  "status": "active",
  "date_locked": "2026-04-25"
}
```

This LD is registered AS PART OF Phase C, not as a separate spec — the silent gap is closed by the executing session.

### §15.2 Finding 2 — `MANIFEST_PHASEBOUNDARIES_NAMED_OBJECT_LOCK_V1` overlaps existing LD-412 `PHASE_BOUNDARIES_NAMED_OBJECT_V1`

**Evidence:** §0.1 LD snapshot returned LD-412 active with name "phaseBoundaries Schema — Named Objects". Kim's directive lists `MANIFEST_PHASEBOUNDARIES_NAMED_OBJECT_LOCK_V1` as a NEW LD to write.

**Impact on this spec:** §6.1 row 7 lists this as a new LD. If Kim closes the redundancy, the new LD is either (a) not written, with LD-412 cited everywhere instead, OR (b) written as a more-narrowly-scoped lock for the manifest-emission use case specifically (LD-412 is broader; the new LD locks the manifest write path).

**Open Kim Decision 5** (added 2026-05-07): keep both, or just LD-412?
- **Option A (just LD-412):** §6.1 row 7 NOT written. All citations in this spec refer to LD-412.
- **Option B (both):** Write `MANIFEST_PHASEBOUNDARIES_NAMED_OBJECT_LOCK_V1` as a narrow scope-lock specific to manifest emission. Reference LD-412 as parent in the `notes` field. The narrow LD makes the manifest-pipeline citation cleaner.

**Recommendation:** Option A (just LD-412). LD-412 already locks the named-object form — restating it as a narrower LD adds audit-trail noise. Drop the new LD; cite LD-412 everywhere.

**LOCKED PER KIM 2026-05-08:** Option A — DROP `MANIFEST_PHASEBOUNDARIES_NAMED_OBJECT_LOCK_V1`. Cite LD-412 `PHASE_BOUNDARIES_NAMED_OBJECT_V1` everywhere instead. §6.1 row 7 removed. §16 reference index updated. LD count adjusted: "7 new LDs" → "6 new LDs (+ LD-404 AMEND)" throughout.

### §15.3 Finding 3 — `Production/contracts/MANIFEST_SCHEMA_V1.json` $id banner already states v7 PR is needed

**Evidence:** Line 5 of MANIFEST_SCHEMA_V1.json reads: "Governing LDs: ... LD-404 MANIFEST_SCHEMA_V1 (currently locked at narrower schema; v7 update PR needed to align LD-404 with this expanded schema)."

**Impact:** the file itself acknowledges that LD-404's locked decision_text is narrower than the JSON schema. The AMEND in Phase D is therefore not optional — it's already documented as required. Open Decision 1 (amend timing) becomes the only live question.

### §15.4 Finding 4 — `Production/tools/upload_module.py:160-165` references that the user gave do NOT match the actual line numbers in the file

**Evidence:** Read of upload_module.py 2026-05-07 found `sha256_file()` at lines ~155-165, NOT 160-165. The function uses `hashlib.sha256(_base64.b64encode(raw).decode("ascii").encode("utf-8"))` per the on-disk content.

**Impact on this spec:** §3.3 R3 cites both the user-given line range (160-165) AND the actually-observed range (155-165). If the file is patched between spec authoring and execution, the line numbers may shift. Executing session greps for the function name `sha256_file` rather than relying on line numbers.

### §15.5 Finding 5 — assemble_module.py audio mix integration is an ASSEMBLE_MODULE_CONTRACT.md open question

**Evidence:** Line 73 of ASSEMBLE_MODULE_CONTRACT.md: "[TBD pending implementation] Audio mix integration order — does Phase B audio mix get layered at concat time, or is each beat's per-beat audio bed already mixed in?"

**Impact:** The 10-step pipeline in §3.2 implicitly assumes audio is already baked into per-beat normalized clips. If audio is layered at concat time, Step 2 needs `-map` flags + a separate audio input, AND Step 1.5 audio parity check changes shape (input clips might legitimately have no audio because audio comes from the mix MP3).

**Resolution at execution time:** Phase C Step 0 reads one of the existing per-beat normalized clips (e.g., from a recent Event 1 production) and runs ffprobe to confirm audio is already present. If yes — pipeline runs as specced. If no — escalate to Open Kim Decision 6 (added at execution time): "audio at concat or audio at per-beat?"

### §15.6 Finding 6 — `boto3` is NOT yet registered in `Production/API_KEYS_MASTER.md`

**Evidence:** Per Rule 26 escalation trigger 4 ("First integration with a new vendor"): structural check is "vendor's endpoint absent from Production/API_KEYS_MASTER.md". boto3 talking to Cloudflare R2 is a new vendor integration. This triggers Opus escalation at Phase D Step 4.

**Impact:** Phase D Step 4 author should pause, state escalation aloud, spawn Opus agent. Spec author has flagged this in §13 Note 5 already.

### §15.7 Finding 7 — Phase B `verify_app_hash_encoding()` requires app repo access

**Evidence:** R3 Phase B execution-time gate greps the MindfulNest app repo (separate codebase) for `digestStringAsync` calls. Kim's project files repo is at `Claude Mindfulnest Project Files/`; the app repo is `/Users/kimberlysmith/Projects/MindfulNest` per §2 Stream C row.

**Impact:** Phase B execution session must have access to BOTH repos. If running headless, needs both paths configured. Add to §11.2 Phase B dependencies.

### §15.8 Finding 8 — DS-21 `BROWSER_SMOKE_MECHANICAL_GATE_V1` may not be deployed yet

**Evidence:** The mechanical gate in `Production/lib/directus.py::try_post_or_queue` is referenced in DS-21 (added 2026-05-07 per V59 gap-fix Phase F). Spec author has not confirmed whether the code is actually deployed; DS-21 was added to the skill on 2026-05-07 — same day as this spec.

**Impact:** If the mechanical gate is NOT yet wired, the executing session relies on Claude self-discipline to honor DS-21. Surface to Kim at execution time: "Has BROWSER_SMOKE_MECHANICAL_GATE_V1 been wired in try_post_or_queue?" If no, request that V59 gap-fix Phase F lands BEFORE Phase D execution.

### §15.9 Finding 9 — No explicit listen-through file format

**Evidence:** ASSEMBLE_MODULE_CONTRACT.md open question line 74: "Listen-through file format — does Kim want Phase B audio + slate frames, or a side-by-side preview?"

**Impact:** Phase C Step 11 emits `M001.listen_through.mp4` but the format is undefined. Default (per `audio-producer` skill — flat MP3 already used for review) probably suffices, but should be confirmed at execution. Add to §13 as Open Kim Decision 7 if not auto-resolved.

### §15.10 Finding 10 — R2 manifest atomic publish step 4 publishes BOTH manifest.json + manifest_v_<catalogVersion>.json — order matters for rollback

**Evidence:** R2_DEPLOYMENT_CONTRACT.md §Atomic publish order step 4: "Upload new manifest.json (overwriting current) AND a versioned snapshot manifest_v_<catalogVersion>.json (immutable)."

**Impact:** If versioned snapshot is published AFTER manifest.json, there is a window where the rollback target doesn't yet exist. Recommended order: publish versioned snapshot FIRST (immutable, safe to upload), then publish current manifest.json (the cutover moment). r2_atomic_publish.py implementation must respect this ordering — Phase D Step 5 author MUST get this right.

---

## §16. Reference Index

### §16.1 Files cited (read at spec author time 2026-05-07)

- `Production/contracts/ASSEMBLE_MODULE_CONTRACT.md` (read in full)
- `Production/contracts/R2_DEPLOYMENT_CONTRACT.md` (read in full)
- `Production/contracts/MANIFEST_SCHEMA_V1.json` (read in full)
- `MINDFULNEST_MASTER_TECHNICAL_SPEC_v6.md` §2, §5.4, §14.6, §14.13, §15, §16, §17.3, §19 (targeted reads — file is 77k+ tokens, full read exceeds context budget)
- `Production/PIPELINE_BRAIN_v1.md` (referenced; not re-read here — execution session reads §Normalization)
- `Production/governance/video-producer_governance.md` (read in full — §7 Delivery Encoding + §CONCAT_AUDIO_PARITY_V1 Lessons Learned)
- `Production/tools/upload_module.py:155-165` (read for R3 base64 evidence)
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` (referenced; execution session re-reads)
- CLAUDE.md (project instructions — Rules 6, 7, 8 §8.5, 12, 15, 16, 17, 18, 19, 22, 23, 24, 25, 26, 32, 33, 34, 35)
- `.claude/skills/zero-error-qa/SKILL.md` (loaded for Phase 0 classification + DS-1 through DS-21)

### §16.2 LD snapshot evidence

- `Production/Event_1/.preflight_evidence/V59_STREAM_BF_SPEC_ld_snapshot.json` — 21-key snapshot taken 2026-05-07 by spec author. Each executing session takes a fresh snapshot at Phase 0.

### §16.3 Locked decisions cited

LD-280, LD-281, LD-282, LD-283, LD-284, LD-345, LD-364, LD-404, LD-405, LD-412, LD-421, LD-422, LD-432, SIZE_BUDGET_VIDEO_V1 (id=296), CONCAT_AUDIO_PARITY_V1 (governance only — see §15 finding 1).

### §16.4 New LDs to register (§6.1)

`STREAM_B_PHASE_BOUNDARIES_REFORMATTER_V1`, `STREAM_B_HASH_HEX_CANONICAL_V1`, `STREAM_B_ASSEMBLE_MODULE_CLI_V1`, `STREAM_F_R2_UPLOAD_V1`, `STREAM_F_R2_ATOMIC_PUBLISH_V1`, `STREAM_F_FIREBASE_TO_R2_CUTOVER_V1`. (`MANIFEST_PHASEBOUNDARIES_NAMED_OBJECT_LOCK_V1` DROPPED per LOCKED Decision 5 — cite LD-412 instead.) Plus LD-404 AMEND.

### §16.5 Skills referenced

- zero-error-qa (loaded; Phase 0-7.5 + DS-1 through DS-21)
- tech-spec (this spec's authoring format)
- dashboard-ops + dashboard-gate (Phase B prod_assets schema work)
- video-producer (governance for Phase C codec gates)

### §16.6 Cross-spec cross-references

- `V59_CICD_GAP_FIX_SPEC_v1.md` — sibling spec covering CI/CD gaps (Phase F browser-smoke hook + Phase H CodeQL/Dependabot). DS-21 + DS-20 mechanical gates referenced here originate from that spec's Phase F.
- `Production/contracts/CACHE_DOWNLOAD_STATE_MACHINE.md` — Stream C catalog wiring (referenced; out of scope per §10).
- `Production/contracts/PLAYER_LIFECYCLE_CONTRACT.md` — Stream C app playback (referenced; out of scope).
- `MINDFULNEST_PROFESSIONAL_SETUP_ROADMAP_v1.md` — 7-layer master roadmap (this spec lives in Layer 3 Production pipeline).

---

**End of V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md**
