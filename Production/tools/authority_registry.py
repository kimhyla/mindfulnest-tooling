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
OPERATOR_EDIT_AUTHORITY_V1 = "OPERATOR_EDIT_AUTHORITY_V1"
AUTHORITY_REGISTRY_DOC = "Production/docs/STORYBOARD_AUTHORITY_REGISTRY_v1.md"
OPERATOR_EDIT_SPEC_DOC = "Production/docs/TECH_SPEC_OPERATOR_EDIT_AUTHORITY_V1.md"

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


@dataclass(frozen=True)
class OperatorEditSurface:
    """Client hydration vs optimistic edit — Tier D operator surfaces (all tabs/events)."""

    id: str
    status: AuthorityStatus
    marker: str
    tab: str
    client_module: str
    client_read: str
    spec_doc: str = OPERATOR_EDIT_SPEC_DOC
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
        id="kling_o3_export_trim",
        status="shipped",
        marker="KLING_O3_EXPORT_TRIM_AUTHORITY_V1",
        question="Which trim window is materialized on Send to Stitcher?",
        authority_shape="disk",
        server_module="beat_generator.py",
        server_read="prepare_beats_for_stitch_export",
        server_write="set_o3_option_trim",
        spec_doc="Production/docs/O3_TRIM_EXPORT_TRUTH_V1.md",
        notes="Option trim must mirror to beat-level before concat; export fails closed on drift.",
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
        marker="O3_GALLERY_OPTION_IDENTITY_V1",
        question="Which delivery clip is the active beat pointer?",
        authority_shape="disk",
        server_module="o3_gallery_option_identity.py",
        server_read="resolve_o3_gallery_option",
        server_write="finalize_kling_delivery_clip",
        spec_doc="Production/docs/TECH_SPEC_OPERATOR_EXPORT_TRUTH_CLOSURE_V1.md",
        notes="Export/select read path via resolve_o3_gallery_option; kling_o3_video_path is active pointer.",
        server_delegation=(
            ("beat_generator.py", "find_active_o3_option"),
            ("server_handlers/kling_o3.py", "assert_beat_export_gallery_authority"),
        ),
    ),
    AuthorityConcept(
        id="o3_gallery_option_identity",
        status="shipped",
        marker="O3_GALLERY_OPTION_IDENTITY_V1",
        question="Which disk file does this gallery option key denote?",
        authority_shape="disk",
        server_module="o3_gallery_option_identity.py",
        server_read="resolve_o3_gallery_option",
        server_write="normalize_o3_gallery_options",
        spec_doc="Production/docs/TECH_SPEC_OPERATOR_EXPORT_TRUTH_CLOSURE_V1.md",
    ),
    AuthorityConcept(
        id="o3_clip_audio_contract",
        status="shipped",
        marker="O3_CLIP_AUDIO_CONTRACT_V1",
        question="What audio shape does this O3/still-insert option promise?",
        authority_shape="disk",
        server_module="o3_gallery_option_identity.py",
        server_read="probe_o3_clip_audio_contract",
        server_write="stamp_o3_option_audio_contract",
        spec_doc="Production/docs/TECH_SPEC_OPERATOR_EXPORT_TRUTH_CLOSURE_V1.md",
    ),
    AuthorityConcept(
        id="stitch_export_timeline_duration",
        status="shipped",
        marker="STITCH_EXPORT_TIMELINE_AUTHORITY_V1",
        question="What duration drives BG export concat and beat boundaries?",
        authority_shape="derived",
        server_module="credentials_lib/ffmpeg_stitch.py",
        server_read="export_clip_timeline_duration_s",
        server_write="normalize_for_concat",
        spec_doc="Production/docs/TECH_SPEC_OPERATOR_EXPORT_TRUTH_CLOSURE_V1.md",
        server_delegation=(
            ("beat_generator.py", "concat_kling_o3_approved_beats"),
        ),
    ),
    AuthorityConcept(
        id="stitch_mux_preview_lineage",
        status="shipped",
        marker="STITCH_EXPORT_ATOMIC_V1",
        question="Which playback artifact hash is authoritative after BG export?",
        authority_shape="disk",
        server_module="server_handlers/stitch_editor.py",
        server_read="stitch_slot_needs_playback_artifact_bake",
        server_write="ensure_stitch_slot_playback_artifacts_on_export",
        spec_doc="Production/docs/TECH_SPEC_OPERATOR_EXPORT_TRUTH_CLOSURE_V1.md",
    ),
    AuthorityConcept(
        id="stitch_slot_playback_mp4",
        status="shipped",
        marker="STITCH_DRY_AUTHORITY_CLIENT_MIX_V1",
        question="Which MP4 is Stitcher dry speech authority per event slot?",
        authority_shape="disk",
        server_module="server_handlers/stitch_slot_playback.py",
        server_read="resolve_slot_playback_path",
        server_write="persist_dry_authority_slot_export",
        client_module="storyboard-v2/src/audio/StitchSlotAudioMixEngine.ts",
        client_read="async attach(",
        spec_doc="Production/docs/TECH_SPEC_STITCH_DRY_AUTHORITY_CLIENT_MIX_V1.md",
    ),
    AuthorityConcept(
        id="stitch_ambient_loop_seam_budget",
        status="shipped",
        marker="STITCH_AMBIENT_FULL_PERIOD_TILE_V2",
        question="How many audible loop seams per ambient bed period?",
        authority_shape="derived",
        server_module="server_handlers/stitch_ambient_loop.py",
        server_read="build_ambient_bed_filter_lane",
        spec_doc="Production/docs/TECH_SPEC_STITCH_AMBIENT_FULL_PERIOD_TILE_V2.md",
    ),
    AuthorityConcept(
        id="stitch_export_truth",
        status="shipped",
        marker="STITCH_EXPORT_TRUTH_JOIN_FADE_V1",
        question="Which concat join fade and waveform source govern intro export quality?",
        authority_shape="disk",
        server_module="beat_generator.py",
        server_read="_kling_export_audio_lane_filter",
        server_write="concat_kling_o3_approved_beats",
        client_module="storyboard-v2/src/utils/stitchJobMediaHydrate.ts",
        client_read="resolveSlotWaveformVideoPath",
        spec_doc="Production/docs/TECH_SPEC_STITCH_INTRO_EXPORT_TRUTH_V1.md",
        notes="Join fade + dry waveform peaks + playback remux; rebake required after deploy.",
    ),
    AuthorityConcept(
        id="stitch_export_truth_v2",
        status="shipped",
        marker="STITCH_EXPORT_TRUTH_STILL_INSERT_VIDEO_FADE_V1",
        question="How do still-insert exits and ambient loops avoid intro seam clicks?",
        authority_shape="disk",
        server_module="beat_generator.py",
        server_read="_still_insert_exit_at_join",
        server_write="concat_kling_o3_approved_beats",
        spec_doc="Production/docs/TECH_SPEC_STITCH_INTRO_EXPORT_TRUTH_V2.md",
        notes="Beat-metadata still-insert fades + tile concat ambient + peaks hash purge on export.",
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
        id="element_visual_canonical_lock",
        status="shipped",
        marker="ELEMENT_VISUAL_CANONICAL_LOCK_V1",
        question="Which PNG bytes define the Element frontal identity?",
        authority_shape="disk",
        server_module="kling_character_registry.py",
        server_read="verify_frontal_sha256",
        server_write="set_element_identity",
        client_module="storyboard-v2/src/api/endpoints.ts",
        client_read="bg_set_element_identity",
        spec_doc="Production/docs/TECH_SPEC_ELEMENT_VISUAL_CANONICAL_LOCK_v1.md",
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
    AuthorityConcept(
        id="phase_watercolor_cue_geometry",
        status="shipped",
        marker="PHASE_WATERCOLOR_CUE_AUTHORITY_V1",
        question="Which cue array drives Phase A/B waveform markers during edit + refresh?",
        authority_shape="disk",
        server_module="production_server.py",
        server_read="_v2_validate_watercolor_cues_json",
        server_write="v2_module_patch phase_*_watercolor_cues_json",
        client_module="storyboard-v2/src/hooks/usePhaseWatercolorCues.ts",
        client_read="mergeWatercolorCuesOnHydrate",
        spec_doc="Production/docs/TIER_D_OPERATOR_EDIT_SURFACES_v1.md",
        notes="Client hook owns optimistic geometry; server JSON is durable store. Hydrate merge preserves local when field omitted or patch in flight.",
    ),
    AuthorityConcept(
        id="phase_stem_cut_geometry",
        status="shipped",
        marker="PHASE_STEM_CUT_AUTHORITY_V1",
        question="Which stem cut handles drive Phase A/B waveform during edit + refresh?",
        authority_shape="disk",
        server_module="production_server.py",
        server_read="phase_a_voice_stem_cut_start_s",
        server_write="v2_module_patch phase_a_voice_stem_cut_start_s",
        client_module="storyboard-v2/src/hooks/usePhaseStemCut.ts",
        client_read="mergeOperatorFieldOnHydrate",
        spec_doc=OPERATOR_EDIT_SPEC_DOC,
        notes="usePhaseStemCut owns cut geometry; mergeOperatorFieldOnHydrate on hydrate omit.",
    ),
    AuthorityConcept(
        id="phase_script_draft",
        status="shipped",
        marker="OPERATOR_EDIT_AUTHORITY_V1",
        question="Which text owns Phase A/B script textarea during poll/focus refresh?",
        authority_shape="disk",
        server_module="production_server.py",
        server_read="phase_a_script",
        server_write="v2_module_patch phase_a_script",
        client_module="storyboard-v2/src/hooks/useProtectedPromptField.ts",
        client_read="useProtectedPromptField",
        spec_doc=OPERATOR_EDIT_SPEC_DOC,
        notes="Uncontrolled textarea + promptEditRegistry; refreshAll must not clobber draft.",
    ),
    AuthorityConcept(
        id="o3_job_truth_stack",
        status="shipped",
        marker="O3_JOB_TRUTH_STACK_V1",
        question="Which resolver owns beat O3 terminal/disk/sidecar read parity?",
        authority_shape="derived",
        server_module="o3_job_truth.py",
        server_read="resolve_beat_o3_truth",
        server_write="close_o3_attempt",
        client_module="storyboard-v2/src/utils/bgSessionBeatMerge.ts",
        client_read="mergeBeatsOnSessionHydrate",
        spec_doc="Production/docs/TECH_SPEC_CROSS_PIPELINE_G1_G8_CLOSURE_v1.md",
    ),
    AuthorityConcept(
        id="o3_failed_redo_heal",
        status="shipped",
        marker="O3_FAILED_REDO_HEAL_V1",
        question="Who restores prior on-disk delivery after failed g4+ regen?",
        authority_shape="disk",
        server_module="o3_generation_intent.py",
        server_read="restore_last_good_o3_delivery_after_failed_attempt",
        server_write="restore_last_good_o3_delivery_after_failed_attempt",
        spec_doc="Production/docs/TECH_SPEC_CROSS_PIPELINE_G1_G8_CLOSURE_v1.md",
    ),
    AuthorityConcept(
        id="o3_subprocess_lifecycle",
        status="shipped",
        marker="O3_SUBPROCESS_LIFECYCLE_V1",
        question="Who finalizes live O3 jobs on shutdown?",
        authority_shape="explicit_approve",
        server_module="o3_generation_intent.py",
        server_read="load_intent_terminal",
        server_write="finalize_live_o3_jobs_before_shutdown",
        client_module="storyboard-v2/src/components/BgPollCoordinator.tsx",
        client_read="beatPatchFromO3PollTerminal",
        spec_doc="Production/docs/TECH_SPEC_CROSS_PIPELINE_G1_G8_CLOSURE_v1.md",
    ),
    AuthorityConcept(
        id="cr_library_milestone_scope",
        status="shipped",
        marker="LIBRARY_SCOPE_ROOT_PARITY_V1",
        question="Which event_dir roots library CR on milestone scope?",
        authority_shape="derived",
        server_module="server_handlers/cropper.py",
        server_read="_resolve_cr_library_scope",
        server_write="assert_production_scope",
        spec_doc="Production/docs/TECH_SPEC_CROSS_PIPELINE_G1_G8_CLOSURE_v1.md",
    ),
    AuthorityConcept(
        id="directus_has_crop_disk_fallback",
        status="shipped",
        marker="DIRECTUS_HAS_CROP_DISK_FALLBACK_V1",
        question="Who sets has_crop when Directus is slow?",
        authority_shape="disk",
        server_module="server_handlers/cropper.py",
        server_read="_enrich_has_crop_from_disk",
        server_write="_enrich_has_crop_from_disk",
        spec_doc="Production/docs/TECH_SPEC_CROSS_PIPELINE_G1_G8_CLOSURE_v1.md",
    ),
    AuthorityConcept(
        id="library_client_cache_coherence",
        status="shipped",
        marker="LIBRARY_CLIENT_CACHE_COHERENCE_V1",
        question="Who busts library sessionStorage after mutations?",
        authority_shape="derived",
        server_module="server_handlers/cropper.py",
        server_read="handle_cr_library",
        client_module="storyboard-v2/src/utils/libraryCachePolicy.ts",
        client_read="invalidateLibrarySessionCache",
        spec_doc="Production/docs/TECH_SPEC_CROSS_PIPELINE_G1_G8_CLOSURE_v1.md",
    ),
    AuthorityConcept(
        id="bg_o3_stitch_export_lineage",
        status="shipped",
        marker="BG_O3_STITCH_EXPORT_LINEAGE_V1",
        question="Who invalidates stitch slot preview when O3 export authority changes?",
        authority_shape="derived",
        server_module="bg_o3_stitch_invalidation.py",
        server_read="compute_bg_segment_o3_export_lineage_sig",
        server_write="invalidate_stitch_slots_for_o3_export_change",
        client_module="storyboard-v2/src/utils/stitchJobMediaHydrate.ts",
        client_read="stitchSlotBgO3ExportLineageMatches",
        spec_doc="Production/docs/TECH_SPEC_CROSS_PIPELINE_G1_G8_CLOSURE_v1.md",
    ),
)


OPERATOR_EDIT_SURFACES: tuple[OperatorEditSurface, ...] = (
    OperatorEditSurface(
        id="phase_watercolor_cue_geometry",
        status="shipped",
        marker="PHASE_WATERCOLOR_CUE_AUTHORITY_V1",
        tab="phase_a|phase_b",
        client_module="storyboard-v2/src/hooks/usePhaseWatercolorCues.ts",
        client_read="mergeWatercolorCuesOnHydrate",
    ),
    OperatorEditSurface(
        id="phase_stem_cut_geometry",
        status="shipped",
        marker="PHASE_STEM_CUT_AUTHORITY_V1",
        tab="phase_a|phase_b",
        client_module="storyboard-v2/src/hooks/usePhaseStemCut.ts",
        client_read="mergeOperatorFieldOnHydrate",
    ),
    OperatorEditSurface(
        id="phase_script_draft",
        status="shipped",
        marker="OPERATOR_EDIT_AUTHORITY_V1",
        tab="phase_a|phase_b",
        client_module="storyboard-v2/src/hooks/useProtectedPromptField.ts",
        client_read="useProtectedPromptField",
        notes="PhaseProducer script textarea — all events via scope.event_id fieldId.",
    ),
    OperatorEditSurface(
        id="stitch_sfx_cue_geometry",
        status="shipped",
        marker="STITCH_SAVE_REFRESH_LOCAL_CUES_V1",
        tab="stitcher",
        client_module="storyboard-v2/src/utils/stitchSlotDurableMerge.ts",
        client_read="mergeStitchJobSlotsClientPatch",
    ),
    OperatorEditSurface(
        id="stitch_slot_durable_fields",
        status="shipped",
        marker="STITCH_SAVE_SLOT_DURABLE_MERGE_V1",
        tab="stitcher",
        client_module="storyboard-v2/src/utils/stitchSlotDurableMerge.ts",
        client_read="mergeStitchSlotClientPatch",
    ),
    OperatorEditSurface(
        id="bg_beat_prompt_field",
        status="shipped",
        marker="OPERATOR_EDIT_AUTHORITY_V1",
        tab="beat_gen",
        client_module="storyboard-v2/src/hooks/useProtectedPromptField.ts",
        client_read="useProtectedPromptField",
        notes="Per beat_id across all milestone partitions.",
    ),
    OperatorEditSurface(
        id="bg_beat_ref_boxes",
        status="shipped",
        marker="OPERATOR_EDIT_AUTHORITY_V1",
        tab="beat_gen",
        client_module="storyboard-v2/src/state/promptEditRegistry.ts",
        client_read="preserveRefBoxesOnServerBeatMerge",
    ),
    OperatorEditSurface(
        id="phase_ambient_preset",
        status="shipped",
        marker="OPERATOR_EDIT_AUTHORITY_V1",
        tab="phase_b",
        client_module="storyboard-v2/src/hooks/usePhaseAmbientPreset.ts",
        client_read="mergeOperatorFieldOnHydrate",
    ),
    OperatorEditSurface(
        id="stitch_ambient_bed_selection",
        status="shipped",
        marker="STITCH_AMBIENT_BED_MERGE_V1",
        tab="stitcher",
        client_module="storyboard-v2/src/utils/stitchSlotDurableMerge.ts",
        client_read="mergeStitchAmbientBedOnHydrate",
    ),
    OperatorEditSurface(
        id="storyboard_dialogue_cell",
        status="shipped",
        marker="STORYBOARD_DIALOGUE_FIELD_V1",
        tab="storyboard",
        client_module="storyboard-v2/src/hooks/useStoryboardDialogueField.ts",
        client_read="useStoryboardDialogueField",
    ),
    OperatorEditSurface(
        id="storyboard_beat_trim",
        status="shipped",
        marker="STORYBOARD_TRIM_FIELDS_V1",
        tab="storyboard",
        client_module="storyboard-v2/src/hooks/useStoryboardTrimFields.ts",
        client_read="mergeOperatorFieldOnHydrate",
    ),
    OperatorEditSurface(
        id="bg_beat_o3_cut_overlay",
        status="shipped",
        marker="BG_O3_CUT_SESSION_V1",
        tab="beat_gen",
        client_module="storyboard-v2/src/hooks/useBgO3CutSession.ts",
        client_read="useBgO3CutSession",
    ),
    OperatorEditSurface(
        id="bg_beat_o3_trim_numeric",
        status="shipped",
        marker="BG_O3_TRIM_NUMERIC_DRAFT_V1",
        tab="beat_gen",
        client_module="storyboard-v2/src/hooks/useBgO3TrimNumericDraft.ts",
        client_read="mergeOperatorFieldOnHydrate",
    ),
    OperatorEditSurface(
        id="bg_beat_o3_gallery_session",
        status="shipped",
        marker="BG_SESSION_BEAT_MERGE_V1",
        tab="beat_gen",
        client_module="storyboard-v2/src/utils/bgSessionBeatMerge.ts",
        client_read="mergeBeatsOnSessionHydrate",
    ),
    OperatorEditSurface(
        id="phase_base_clip_picker",
        status="shipped",
        marker="OPERATOR_EDIT_AUTHORITY_V1",
        tab="phase_a|phase_b",
        client_module="storyboard-v2/src/hooks/usePhaseBaseClipPicker.ts",
        client_read="mergeOperatorFieldOnHydrate",
    ),
)


def shipped_concepts() -> tuple[AuthorityConcept, ...]:
    return tuple(c for c in CONCEPTS if c.status == "shipped")


def concept_ids() -> tuple[str, ...]:
    return tuple(c.id for c in CONCEPTS)


def operator_edit_surface_ids() -> tuple[str, ...]:
    return tuple(s.id for s in OPERATOR_EDIT_SURFACES)
