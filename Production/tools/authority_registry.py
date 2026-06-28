"""STORYBOARD_AUTHORITY_REGISTRY_V1 — machine-readable single-authority index.

Human doc: Production/docs/STORYBOARD_AUTHORITY_REGISTRY_v1.md
Durability: Production/scripts/verify_authority_registry_durability.sh

Each concept declares exactly one read gate (export/UI enable) and one or more
write paths. Duplicate predicates outside the contract module are regressions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

AUTHORITY_REGISTRY_V1 = "STORYBOARD_AUTHORITY_REGISTRY_V1"
AUTHORITY_REGISTRY_DOC = "Production/docs/STORYBOARD_AUTHORITY_REGISTRY_v1.md"

AuthorityStatus = Literal["shipped", "partial", "debt"]


@dataclass(frozen=True)
class ForbiddenClientGate:
    """Client file must not use this regex for export/enable gates (contract owns it)."""

    rel_path: str
    pattern: str
    reason: str


@dataclass(frozen=True)
class AuthorityConcept:
    id: str
    status: AuthorityStatus
    marker: str
    question: str
    authority_shape: str  # disk | derived | explicit_approve
    server_module: str | None = None
    server_read: str | None = None
    server_write: str | None = None
    client_module: str | None = None
    client_read: str | None = None
    spec_doc: str | None = None
    forbidden_client_gates: tuple[ForbiddenClientGate, ...] = field(default_factory=tuple)
    server_delegation: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    notes: str = ""


CONCEPTS: tuple[AuthorityConcept, ...] = (
    AuthorityConcept(
        id="event_scope",
        status="shipped",
        marker="SCOPE_CLIENT_AUTHORITY_V1",
        question="Which event_id is authoritative for mutations on this port?",
        authority_shape="derived",
        server_module="server_handlers/event_video.py",
        server_read="DEDICATED_PORT_PIN_IMMUTABLE",
        client_module="storyboard-v2/src/state/resolveAuthoritativeClientScope.ts",
        client_read="readAuthoritativeEventId",
        spec_doc="Production/docs/SCOPE_CLIENT_AUTHORITY_SPEC_v1.md",
    ),
    AuthorityConcept(
        id="beatgen_scope_partition",
        status="shipped",
        marker="BEATGEN_TRUTH_STACK_V1",
        question="Which SQLite/JSON partition owns this beat write?",
        authority_shape="disk",
        server_module="beatgen_scope.py",
        server_read="scope_from_app",
        server_write="beatgen_scope_ctx",
        spec_doc="Production/docs/TECH_SPEC_BEATGEN_TRUTH_STACK_V1.md",
        notes="HTTP + async export/Kling workers enter beatgen_scope_ctx; O3 subprocess uses scope_from_app.",
    ),
    AuthorityConcept(
        id="kling_stitch_export_ready",
        status="shipped",
        marker="KLING_STITCH_READINESS_V1",
        question="May this beat be included in Send to Stitcher?",
        authority_shape="disk",
        server_module="kling_stitch_readiness.py",
        server_read="beat_kling_stitch_export_ready",
        server_write="finalize_kling_delivery_clip",
        client_module="storyboard-v2/src/utils/klingStitchReadiness.ts",
        client_read="beatKlingStitchExportReady",
        spec_doc="Production/tools/kling_stitch_readiness.py",
        forbidden_client_gates=(
            ForbiddenClientGate(
                "storyboard-v2/src/utils/bgStitchExport.ts",
                r"kling_o3_status\s*===?\s*['\"]approved['\"]",
                "export gate must use beatKlingStitchExportReady only",
            ),
        ),
        server_delegation=(
            ("beat_generator.py", "beat_kling_stitch_export_ready"),
            ("server_handlers/kling_o3.py", "beat_has_stitch_export_clip"),
        ),
    ),
    AuthorityConcept(
        id="still_insert_stitch_approve",
        status="shipped",
        marker="KLING_STITCH_READINESS_V1",
        question="May this still-insert beat export before operator stitch approve?",
        authority_shape="explicit_approve",
        server_module="kling_stitch_readiness.py",
        server_read="beat_kling_stitch_export_ready",
        server_write="kling_o3_still_stitch_approved",
        client_module="storyboard-v2/src/utils/klingStitchReadiness.ts",
        client_read="stillBeatNeedsStitchApprove",
    ),
    AuthorityConcept(
        id="o3_job_busy",
        status="shipped",
        marker="BG_BEAT_JOB_TRUTH_GALLERY",
        question="Is an O3/Kling job in flight blocking operator edits?",
        authority_shape="derived",
        server_module="o3_job_status_contract.py",
        server_read="beat_o3_operator_busy",
        client_module="storyboard-v2/src/o3JobStatusContract.ts",
        client_read="beatO3JobBusy",
        spec_doc="Production/docs/BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1.md",
    ),
    AuthorityConcept(
        id="o3_gallery_active_clip",
        status="shipped",
        marker="BG_BEAT_JOB_TRUTH_GALLERY",
        question="Which delivery clip is the active beat pointer?",
        authority_shape="disk",
        server_module="beat_generator.py",
        server_read="is_user_selectable_o3_video",
        server_write="finalize_kling_delivery_clip",
        notes="Gallery rows are history; kling_o3_video_path is active pointer.",
    ),
    AuthorityConcept(
        id="operator_still_scene",
        status="shipped",
        marker="OPERATOR_WORKBENCH_AUTHORITY",
        question="Which PNG is the still-insert Ken Burns source?",
        authority_shape="disk",
        server_module="operator_workbench_contract.py",
        server_read="resolve_beat_still_scene_abs_path",
        server_write="write_still_scene_source",
        client_module="storyboard-v2/src/types/bgBeat.ts",
        client_read="still_scene_display",
        spec_doc="Production/docs/BG_OPERATOR_WORKBENCH_AUTHORITY_SPEC_v1.md",
    ),
    AuthorityConcept(
        id="operator_display_prompt",
        status="shipped",
        marker="OPERATOR_WORKBENCH_AUTHORITY",
        question="What prompt text does the operator textarea show?",
        authority_shape="derived",
        server_module="operator_workbench_contract.py",
        server_read="active_beat_prompt_for_generation_mode",
        spec_doc="Production/docs/BG_OPERATOR_WORKBENCH_AUTHORITY_SPEC_v1.md",
        notes="GET must never overwrite kling_o3_prompt; display_prompt is _derived only.",
    ),
    AuthorityConcept(
        id="magic_render_visible",
        status="shipped",
        marker="LD-469-VISIBLE-MAGIC-V2",
        question="Does rendered magic pass visible-sparkle contract?",
        authority_shape="disk",
        server_module="magic_render_contract.py",
        server_read="production_magic_compositor_kwargs",
        server_write="write_magic_delivery",
        spec_doc="Production/docs/HOW_TO_MAKE_VISIBLE_MAGIC.md",
        notes="Render via magic_render_contract; writeback via write_magic_delivery (MAGIC_WRITE_AUTHORITY_V1).",
    ),
    AuthorityConcept(
        id="stitch_slot_timeline_dur",
        status="shipped",
        marker="STITCH_SLOT_TIMELINE_ATOMIC_V1",
        question="What duration drives stitch slot rail/SFX geometry?",
        authority_shape="derived",
        server_module="server_handlers/stitch_editor.py",
        server_read="ensure_stitch_slot_timeline_dur_ms",
        client_module="storyboard-v2/src/utils/stitchJobMediaHydrate.ts",
        client_read="stitchSlotTimelineDurMs",
        spec_doc="Production/docs/TECH_SPEC_STITCH_TRUTH_CONTRACT_V2.md",
    ),
    AuthorityConcept(
        id="stitch_playback_url",
        status="shipped",
        marker="STITCH_SFX_PLAYBACK_TRUTH_V1",
        question="Which video URL may the stitch composer play when SFX exist?",
        authority_shape="derived",
        client_module="storyboard-v2/src/utils/stitchJobMediaHydrate.ts",
        client_read="resolveSlotPlaybackPreviewUrl",
        spec_doc="Production/docs/TECH_SPEC_STITCH_SFX_PLAYBACK_TRUTH_V1.md",
    ),
    AuthorityConcept(
        id="stitch_single_owner",
        status="shipped",
        marker="STITCH_SINGLE_OWNER_V1",
        question="Who may mutate stitch slot video after export?",
        authority_shape="disk",
        server_module="server_handlers/stitch_editor.py",
        server_read="STITCH_SINGLE_OWNER_V1",
        spec_doc="Production/docs/TECH_SPEC_STITCH_SINGLE_OWNER_V1.md",
    ),
    AuthorityConcept(
        id="sqlite_sidecar_authority",
        status="shipped",
        marker="BEATGEN_PER_EVENT_SQLITE_V1",
        question="Which store is authoritative for beat sidecar rows?",
        authority_shape="disk",
        server_module="beat_generator.py",
        server_read="sqlite_authority_enabled",
        spec_doc="Production/docs/TECH_SPEC_BEATGEN_PER_EVENT_SQLITE_V1.md",
    ),
    AuthorityConcept(
        id="build_sha_drift",
        status="shipped",
        marker="BUILD_SHA_DRIFT_V1",
        question="Is the loaded storyboard bundle stale vs server?",
        authority_shape="derived",
        client_module="storyboard-v2/src/state/buildShaDrift.ts",
        client_read="checkBuildShaDrift",
        spec_doc="Production/docs/SCOPE_CLIENT_AUTHORITY_SPEC_v1.md",
    ),
    AuthorityConcept(
        id="bg_export_stitcher_job",
        status="shipped",
        marker="BG_EXPORT_TO_STITCHER_ASYNC_V1",
        question="Did async BG→Stitcher export finish and which job owns the slot?",
        authority_shape="disk",
        client_module="storyboard-v2/src/utils/bgExportToStitcherJobTruth.ts",
        client_read="readBgExportBusyLatch",
        notes="Async worker runs inside run_in_beatgen_scope; verify_event_stitch_job_bootstrap durability wired.",
    ),
)


def shipped_concepts() -> tuple[AuthorityConcept, ...]:
    return tuple(c for c in CONCEPTS if c.status == "shipped")


def concept_ids() -> tuple[str, ...]:
    return tuple(c.id for c in CONCEPTS)
