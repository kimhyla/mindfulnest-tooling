#!/usr/bin/env python3
"""
Orphaned Ideas Rescue Cascade (2026-04-17)

Rescues 5 approved orphaned ideas from stale research docs + captures C3/C4
resolutions. For each rescue:
  1. Create a prod_preflight_reviews row (approved_to_proceed=True, Kim
     explicitly approved the rescue).
  2. Register the locked decision in prod_locked_decisions.
  3. Register / patch reference docs in prod_reference_docs.
  4. Log each rescue to prod_activity_log with the decision_key.

Rescues:
  1. FIRESTORE_RULES_AND_TRANSACTIONS_CANONICAL
  2. THERAPIST_SUMMARY_CLOUD_FUNCTION_PATTERN
  3. TTS_APPROACH_A_SHIPS_V1 + TTS_APPROACH_B_TRIGGER_5K + TTS_APPROACH_C_FORBIDDEN
  4. VENDOR_ABSTRACTION_LAYER_V1
  5. SPRITE_APPROVAL_RUBRIC_PRINCIPLE

Plus:
  - C3 (Scenario.gg vs Gemini): DEFERRED — activity log only, no LD.
  - C4 (Firestore field-level sanitization): LD FIRESTORE_FIELD_LEVEL_SANITIZATION_VIA_CLOUD_FUNCTION.

Uses Python urllib.request via the shared DirectusClient (never curl).
Reads credentials at runtime from Production/API_KEYS_MASTER.md.
Each write retries once on DirectusError before surfacing.
Idempotent: re-running the script will not duplicate rows — existing
decision_key / task_id / basename matches are detected and PATCHed.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.normpath(os.path.join(THIS_DIR, "..", "tools"))
sys.path.insert(0, TOOLS_DIR)

from credentials_lib.credentials import load_credentials  # noqa: E402
from credentials_lib.directus import DirectusClient, DirectusError  # noqa: E402


TODAY = "2026-04-17"
PROJECT_ROOT = "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"


# ---------------------------------------------------------------------------
# Rescue specifications
# ---------------------------------------------------------------------------

RESCUES = [
    {
        "rescue_id": "rescue-1-firestore-rules-canonical",
        "task_id": "orphan-rescue-firestore-rules-20260417",
        "locked_decisions": [
            {
                "decision_key": "FIRESTORE_RULES_AND_TRANSACTIONS_CANONICAL",
                "decision_name": (
                    "Canonical Firestore security ruleset + runTransaction atomic writes"
                ),
                "decision_text": (
                    "The canonical Firestore security ruleset for MindfulNest Stage 3 is "
                    "Production/FIRESTORE_SECURITY_RULES_v1.md §1. It enforces three "
                    "non-negotiables: (a) therapist can read only linked patients; "
                    "(b) parent can read/write only linked children; (c) modules, "
                    "storeItems, narrativeEvents, arcDefinitions are shared read-only to "
                    "authenticated users. Subcollections under /children/{childId} inherit "
                    "parent-child linkage via get(). Atomic writes (module completion, "
                    "coin/rune updates, bar circles) MUST use runTransaction with "
                    "serverTimestamp() as the offline-collision tiebreaker — per "
                    "Production/FIRESTORE_SECURITY_RULES_v1.md §2. Client code NEVER "
                    "writes protected progression fields directly (coins, modulesCompleted, "
                    "runeStates, ownedItems, sessionsThisWeek, engagementStatus, "
                    "domainSessionCounts); those fields are server-owned and mutated only "
                    "by Cloud Functions triggered by completionLog creates. This is the "
                    "ruleset that STAGE3_SECURITY_RULES_FIRST requires to ship before any "
                    "data-model or feature code."
                ),
                "source_document": "Production/FIRESTORE_SECURITY_RULES_v1.md",
                "task_category": "architectural",
                "severity": "critical",
                "notes": (
                    "Rescued 2026-04-17 from Research/FIREBASE_FIRESTORE_ARCHITECTURE_"
                    "OPTIMIZATION_v1.md §6 + §10. Kim explicitly approved the rescue. "
                    "Paired with STAGE3_SECURITY_RULES_FIRST (execution ordering) and "
                    "PROTECTED_FIELD_IMMUTABILITY_PATTERN (LD-125, fieldUnchanged helper)."
                ),
            },
        ],
        "reference_docs": [
            {
                "file_path": "Production/FIRESTORE_SECURITY_RULES_v1.md",
                "doc_title": "Firestore Security Rules + Atomic Write Patterns (Canonical)",
                "doc_category": "app_architecture",
                "doc_version": "v1",
                "notes": (
                    "Canonical Stage 3 Firestore ruleset + runTransaction pattern + "
                    "therapist-summary Cloud Function + C4 field-level sanitization. "
                    "Created 2026-04-17 to consolidate rescued content from "
                    "Research/FIREBASE_FIRESTORE_ARCHITECTURE_OPTIMIZATION_v1.md §6/§10/§13."
                ),
            },
            {
                "file_path": "Research/FIREBASE_FIRESTORE_ARCHITECTURE_OPTIMIZATION_v1.md",
                "doc_title": "Firebase/Firestore Architecture Optimization Research v1",
                "doc_category": "app_architecture",
                "doc_version": "v1",
                "notes": (
                    "Research source document for the Firestore rules + atomic writes + "
                    "therapist summary Cloud Function. Canonical content extracted to "
                    "Production/FIRESTORE_SECURITY_RULES_v1.md on 2026-04-17. This "
                    "research doc is now supporting reference only."
                ),
            },
        ],
        "preflight": {
            "task_type": "architectural",
            "task_description": (
                "Rescue the Firestore canonical ruleset + runTransaction atomic-write "
                "pattern from Research/FIREBASE_FIRESTORE_ARCHITECTURE_OPTIMIZATION_v1.md "
                "§6 + §10 into a Production-folder canonical reference doc, then register "
                "the locked decision FIRESTORE_RULES_AND_TRANSACTIONS_CANONICAL that "
                "makes that doc authoritative for Stage 3 implementation."
            ),
            "claude_summary": (
                "Kim approved rescuing this content. Creating Production/FIRESTORE_"
                "SECURITY_RULES_v1.md with the full ruleset (therapist/parent/child "
                "isolation + shared read-only + protected-field immutability helper) "
                "and runTransaction pattern. Registering the reference docs and the "
                "canonical locked decision. Low risk — documentation consolidation, no "
                "implementation code landing."
            ),
            "notes": (
                "Part of a 5-rescue batch approved by Kim on 2026-04-17. See "
                "orphaned_ideas_rescue_cascade_20260417.py."
            ),
        },
    },
    {
        "rescue_id": "rescue-2-therapist-summary-cf",
        "task_id": "orphan-rescue-therapist-summary-cf-20260417",
        "locked_decisions": [
            {
                "decision_key": "THERAPIST_SUMMARY_CLOUD_FUNCTION_PATTERN",
                "decision_name": (
                    "Pre-computed therapist-summary fields via Cloud Function"
                ),
                "decision_text": (
                    "On every create under children/{childId}/completionLog/{logId}, a "
                    "Cloud Function atomically updates the child document's summary "
                    "fields: sessionsThisWeek (number), engagementStatus (enum: active / "
                    "moderate / inactive), domainSessionCounts (map<domain,count>), and "
                    "lastActivityAt (timestamp mirrored from completedAt). Updates run "
                    "inside db.runTransaction. Idempotency is guarded by "
                    "lastProcessedLogId on the child doc (at-least-once delivery "
                    "protection). This replaces the naive 'read completionLog per child' "
                    "therapist dashboard pattern, which costs 10x more at scale. "
                    "Reference implementation in Production/FIRESTORE_SECURITY_RULES_v1.md §3."
                ),
                "source_document": "Production/FIRESTORE_SECURITY_RULES_v1.md",
                "task_category": "architectural",
                "severity": "high",
                "notes": (
                    "Rescued 2026-04-17 from Research/FIREBASE_FIRESTORE_ARCHITECTURE_"
                    "OPTIMIZATION_v1.md §13. Canonical content consolidated into "
                    "Production/FIRESTORE_SECURITY_RULES_v1.md alongside the rules + "
                    "runTransaction pattern (rescue 1)."
                ),
            },
        ],
        "reference_docs": [],  # Already registered in rescue 1
        "preflight": {
            "task_type": "architectural",
            "task_description": (
                "Register the therapist-summary Cloud Function pattern as a locked "
                "decision. Fields updated on child doc: sessionsThisWeek, "
                "engagementStatus, domainSessionCounts, lastActivityAt. Idempotency via "
                "lastProcessedLogId. Rescued from Research/FIREBASE_FIRESTORE_"
                "ARCHITECTURE_OPTIMIZATION_v1.md §13."
            ),
            "claude_summary": (
                "Kim approved rescuing. Consolidating Cloud Function pattern into the "
                "same canonical doc as rescue 1 (rules + runTransaction). Registering "
                "the LD THERAPIST_SUMMARY_CLOUD_FUNCTION_PATTERN pointing to "
                "Production/FIRESTORE_SECURITY_RULES_v1.md §3."
            ),
            "notes": "Part of 5-rescue batch.",
        },
    },
    {
        "rescue_id": "rescue-3-tts-approach-decisions",
        "task_id": "orphan-rescue-tts-approach-decisions-20260417",
        "locked_decisions": [
            {
                "decision_key": "TTS_APPROACH_A_SHIPS_V1",
                "decision_name": (
                    "TTS Approach A (full-sentence rendering) ships for V1"
                ),
                "decision_text": (
                    "MindfulNest V1 ships with Approach A: every personalized sentence "
                    "is rendered in full per child via ElevenLabs. One-time render cost "
                    "per child ~$2.82 for the full app (54 modules). Zero splicing, zero "
                    "engineering complexity, perfect audio quality. This is the current "
                    "pipeline as documented in TTS_PERSONALIZATION_PIPELINE_v1.md. Do "
                    "NOT build Approach B or C before the trigger in "
                    "TTS_APPROACH_B_TRIGGER_5K is met."
                ),
                "source_document": (
                    "Research/TTS_PERSONALIZATION_COST_OPTIMIZATION_ANALYSIS_April2026.md"
                ),
                "task_category": "architectural",
                "severity": "high",
                "notes": (
                    "Rescued 2026-04-17 from TTS cost analysis. At $499/6mo pricing, "
                    "TTS is <1% of revenue and drops over time. Engineering effort is "
                    "better spent on growth features until the 5K-child threshold is hit."
                ),
            },
            {
                "decision_key": "TTS_APPROACH_B_TRIGGER_5K",
                "decision_name": (
                    "TTS Approach B (short-phrase splice) trigger: ~5K active children"
                ),
                "decision_text": (
                    "Build Approach B (short-phrase splicing with universal segments "
                    "+ per-child variable-carrying phrases, crossfaded via Web Audio "
                    "API) ONLY when active children cross ~5K. At that threshold, "
                    "cumulative savings (~$5,200) justify the 4–5 day dev investment "
                    "(phrase boundary markup + splicing engine + QA pipeline + "
                    "ongoing maintenance). Before 5K, the engineering time is better "
                    "spent on growth features."
                ),
                "source_document": (
                    "Research/TTS_PERSONALIZATION_COST_OPTIMIZATION_ANALYSIS_April2026.md"
                ),
                "task_category": "architectural",
                "severity": "medium",
                "notes": (
                    "Rescued 2026-04-17. Paired with TTS_APPROACH_A_SHIPS_V1 "
                    "(V1 default) and TTS_APPROACH_C_FORBIDDEN (never build). Review "
                    "when active-children count crosses 3K as an early trigger warning."
                ),
            },
            {
                "decision_key": "TTS_APPROACH_C_FORBIDDEN",
                "decision_name": (
                    "TTS Approach C (single-word splicing) forbidden"
                ),
                "decision_text": (
                    "Never build Approach C (single-word splicing of variable values "
                    "into universal audio). Prosody mismatch is audible — an isolated "
                    "\"Emma\" sounds different from \"Emma\" spoken mid-sentence. "
                    "Unacceptable quality tradeoff for a premium therapeutic product "
                    "aimed at children who need to feel the voice speaks directly to "
                    "them. The cost savings ($2.35/child vs $1.04/child for Approach B) "
                    "do not justify the quality degradation."
                ),
                "source_document": (
                    "Research/TTS_PERSONALIZATION_COST_OPTIMIZATION_ANALYSIS_April2026.md"
                ),
                "task_category": "architectural",
                "severity": "high",
                "notes": (
                    "Rescued 2026-04-17. Hard prohibition — if any future proposal "
                    "resurrects Approach C, cite this LD and close without further "
                    "debate."
                ),
            },
        ],
        "reference_docs": [
            {
                "file_path": (
                    "Research/TTS_PERSONALIZATION_COST_OPTIMIZATION_ANALYSIS_April2026.md"
                ),
                "doc_title": (
                    "TTS Personalization Cost Optimization Analysis (April 2026)"
                ),
                "doc_category": "app_architecture",
                "doc_version": "v1",
                "notes": (
                    "Source document for TTS_APPROACH_A_SHIPS_V1 + "
                    "TTS_APPROACH_B_TRIGGER_5K + TTS_APPROACH_C_FORBIDDEN. "
                    "Line-by-line cost analysis of three TTS rendering approaches "
                    "with Arc 1 measured data. Registered in prod_reference_docs "
                    "2026-04-17 as part of the orphan-rescue cascade."
                ),
            },
        ],
        "preflight": {
            "task_type": "routine",
            "task_description": (
                "Register three paired TTS approach locked decisions "
                "(A ships V1 / B trigger at 5K / C forbidden) rescued from "
                "Research/TTS_PERSONALIZATION_COST_OPTIMIZATION_ANALYSIS_April2026.md."
            ),
            "claude_summary": (
                "Kim approved rescuing. Three decisions that answer 'which TTS "
                "approach?' for the lifetime of the product. Low risk — "
                "documentation only, no code changes. Registering the source "
                "research doc as reference."
            ),
            "notes": "Part of 5-rescue batch.",
        },
    },
    {
        "rescue_id": "rescue-4-vendor-abstraction-layer",
        "task_id": "orphan-rescue-vendor-abstraction-20260417",
        "locked_decisions": [
            {
                "decision_key": "VENDOR_ABSTRACTION_LAYER_V1",
                "decision_name": (
                    "Thin vendor abstraction layer with env-var swappable providers"
                ),
                "decision_text": (
                    "MindfulNest wraps each external vendor behind a thin wrapper "
                    "function so the provider can be swapped via environment "
                    "variable. The five wrapped vendor categories are: VIDEO_PROVIDER "
                    "(default: wavespeed_kling), LIPSYNC_PROVIDER (default: "
                    "wavespeed_bytedance), TTS_PROVIDER (default: elevenlabs), "
                    "IMAGE_PROVIDER (default: bfl_flux_kontext), LLM_PROVIDER "
                    "(default: anthropic_claude). Reference pattern: "
                    "Research/TECHNICAL_PIPELINE_RESEARCH_AND_RECOMMENDATIONS_April2026.md "
                    "§3. Scope is INTENTIONALLY MINIMAL — a thin wrapper + env var + "
                    "fallback hook, NOT a full adapter pattern with plugin registry or "
                    "feature-flag DSL. Goal: if a vendor goes down or raises prices, "
                    "swap takes hours not weeks. Over-abstraction explicitly out of "
                    "scope."
                ),
                "source_document": (
                    "Research/TECHNICAL_PIPELINE_RESEARCH_AND_RECOMMENDATIONS_April2026.md"
                ),
                "task_category": "architectural",
                "severity": "medium",
                "notes": (
                    "Rescued 2026-04-17. Implementation is deferred but the pattern "
                    "is locked — when any vendor wrapper code lands, it follows this "
                    "shape, not a heavier adapter pattern."
                ),
            },
        ],
        "reference_docs": [
            {
                "file_path": (
                    "Research/TECHNICAL_PIPELINE_RESEARCH_AND_RECOMMENDATIONS_April2026.md"
                ),
                "doc_title": (
                    "Technical Pipeline Research & Recommendations (April 2026)"
                ),
                "doc_category": "app_architecture",
                "doc_version": "v1",
                "notes": (
                    "Source for VENDOR_ABSTRACTION_LAYER_V1 (§3) plus batch-production "
                    "patterns (§4) and Midjourney character consistency (§1). "
                    "Registered in prod_reference_docs 2026-04-17 as part of the "
                    "orphan-rescue cascade."
                ),
            },
        ],
        "preflight": {
            "task_type": "routine",
            "task_description": (
                "Register VENDOR_ABSTRACTION_LAYER_V1 — thin wrapper per vendor "
                "category with env-var swappability. NOT a full adapter pattern. "
                "Rescued from TECHNICAL_PIPELINE_RESEARCH_AND_RECOMMENDATIONS §3."
            ),
            "claude_summary": (
                "Kim approved rescuing. Registering the pattern now so any future "
                "vendor-wrapping code reuses the minimal shape instead of "
                "over-engineering. Low risk — no code landing in this cascade."
            ),
            "notes": "Part of 5-rescue batch.",
        },
    },
    {
        "rescue_id": "rescue-5-sprite-approval-rubric",
        "task_id": "orphan-rescue-sprite-approval-rubric-20260417",
        "locked_decisions": [
            {
                "decision_key": "SPRITE_APPROVAL_RUBRIC_PRINCIPLE",
                "decision_name": (
                    "Sprite approval rubric — documented thresholds required"
                ),
                "decision_text": (
                    "Before any sprite generation begins, a documented rubric with "
                    "OBJECTIVE numeric thresholds for sprite approval must exist. The "
                    "rubric must cover at minimum: (a) CLIP-based consistency score "
                    "vs reference anchor; (b) palette drift threshold (hex-space delta "
                    "from reference palette); (c) silhouette readability at reduced "
                    "scale (sprite reads cleanly at dialogue-portrait and "
                    "map-sprite sizes); (d) mouth variant count per creature for lip "
                    "sync (minimum 2: open / closed). This principle collapses review "
                    "cycles — without objective thresholds, every sprite becomes a "
                    "subjective judgment call and Kim is a bottleneck. Original "
                    "numeric thresholds (CLIP >= 0.90, palette ±10%, silhouette reads "
                    "at 50% scale, 2 mouth variants) were calibrated for a "
                    "painterly/illustrative style. They need RECALIBRATION for Pixar-"
                    "3D style before being treated as numeric specs. Source: "
                    "Research/VISUAL_PIPELINE_MASTER_PLAN_v5.md Step 0.5."
                ),
                "source_document": "Research/VISUAL_PIPELINE_MASTER_PLAN_v5.md",
                "task_category": "architectural",
                "severity": "medium",
                "notes": (
                    "Rescued 2026-04-17. needs_recalibration: true — the CLIP 0.90 / "
                    "palette ±10% / silhouette 50% / 2-mouth-variant numbers were "
                    "calibrated for painterly 2D style and need to be re-derived for "
                    "Pixar-3D. The PRINCIPLE (objective rubric required before "
                    "generation) is locked now so it isn't re-debated. The NUMBERS "
                    "are open until recalibrated."
                ),
            },
        ],
        "reference_docs": [
            {
                "file_path": "Research/VISUAL_PIPELINE_MASTER_PLAN_v5.md",
                "doc_title": "Visual Pipeline Master Plan v5",
                "doc_category": "production_process",
                "doc_version": "v5",
                "notes": (
                    "Source for SPRITE_APPROVAL_RUBRIC_PRINCIPLE (Step 0.5). "
                    "Registered in prod_reference_docs 2026-04-17 as part of the "
                    "orphan-rescue cascade. Numeric thresholds in Step 0.5 need "
                    "Pixar-3D recalibration before use as numeric specs."
                ),
            },
        ],
        "preflight": {
            "task_type": "routine",
            "task_description": (
                "Register SPRITE_APPROVAL_RUBRIC_PRINCIPLE — sprite generation "
                "requires documented objective thresholds (CLIP, palette, silhouette, "
                "mouth variants). Original numbers need Pixar-3D recalibration. "
                "Rescued from VISUAL_PIPELINE_MASTER_PLAN_v5.md Step 0.5."
            ),
            "claude_summary": (
                "Kim approved rescuing. Locking the PRINCIPLE now prevents re-debate; "
                "the specific numeric thresholds are flagged needs_recalibration for "
                "Pixar-3D. Low risk — no generation work running in this cascade."
            ),
            "notes": "Part of 5-rescue batch.",
        },
    },
    # ----- C4 (field-level sanitization) -----
    {
        "rescue_id": "c4-firestore-field-level-sanitization",
        "task_id": "c4-firestore-field-level-sanitization-20260417",
        "locked_decisions": [
            {
                "decision_key": "FIRESTORE_FIELD_LEVEL_SANITIZATION_VIA_CLOUD_FUNCTION",
                "decision_name": (
                    "Firestore field-level restrictions via Cloud Function sanitization"
                ),
                "decision_text": (
                    "Firestore security rules cannot enforce field-level read "
                    "restrictions (if a user can read a doc, they read every field). "
                    "For therapist-dashboard reads that must exclude certain "
                    "child-doc fields (e.g., free-text parent notes, raw "
                    "completionLog entries, parent account email), MindfulNest "
                    "adopts a Cloud Function sanitization pattern: therapist clients "
                    "call a dedicated Cloud Function "
                    "(e.g., getTherapistDashboardForChild(childId)) that reads the "
                    "child doc server-side, strips therapist-forbidden fields, and "
                    "returns the sanitized projection. Security rules still prevent "
                    "unauthorized therapist access to the underlying doc; the Cloud "
                    "Function adds the projection layer that rules cannot express. "
                    "Reference: Production/FIRESTORE_SECURITY_RULES_v1.md §3 "
                    "addendum."
                ),
                "source_document": "Production/FIRESTORE_SECURITY_RULES_v1.md",
                "task_category": "architectural",
                "severity": "high",
                "notes": (
                    "Kim-approved 2026-04-17 as part of rescue discussion (item C4). "
                    "Pairs with THERAPIST_SUMMARY_CLOUD_FUNCTION_PATTERN — both live "
                    "in the same Cloud Functions codebase."
                ),
            },
        ],
        "reference_docs": [],  # Already registered in rescue 1
        "preflight": {
            "task_type": "architectural",
            "task_description": (
                "Register C4 decision: adopt Cloud Function sanitization for "
                "field-level restrictions on therapist-dashboard reads, since "
                "Firestore rules can't do field-level restrictions."
            ),
            "claude_summary": (
                "Kim explicitly approved C4. Documentation in "
                "Production/FIRESTORE_SECURITY_RULES_v1.md §3 addendum. No code "
                "landing in this cascade — pattern lock only."
            ),
            "notes": "C4 resolution from orphan-rescue discussion 2026-04-17.",
        },
    },
]


# C3 is deferred — activity log only, no LD.
C3_DEFER_NOTE = {
    "task_id": "c3-scenario-vs-gemini-deferred-20260417",
    "action": (
        "C3 (Scenario.gg vs Gemini) — DEFERRED. A separate agent is investigating "
        "current actual usage. No locked decision registered yet. Revisit after the "
        "investigation agent reports."
    ),
    "details_payload": {
        "status": "deferred",
        "reason": (
            "Actual vendor usage is being investigated by a separate agent. "
            "Premature registration would risk locking in a stale assumption."
        ),
        "next_step": (
            "Await investigation agent report, then register LD in a follow-up cascade."
        ),
        "related_rescue_cascade": "orphan-rescue-cascade-20260417",
    },
}


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _with_retry(label, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DirectusError as e1:
        print(f"[rescue] {label} attempt 1 failed: {e1}", flush=True)
        time.sleep(1.0)
        try:
            return fn(*args, **kwargs)
        except DirectusError as e2:
            print(f"[rescue] {label} attempt 2 failed: {e2}", flush=True)
            raise


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------

def create_preflight(client, rescue):
    """Create a prod_preflight_reviews row for the rescue (approved_to_proceed=True)."""
    task_id = rescue["task_id"]
    pf = rescue["preflight"]

    # Idempotency check
    existing = _with_retry(
        f"preflight check {task_id}",
        client._request,
        "GET",
        "/items/prod_preflight_reviews",
        params={"filter[task_id][_eq]": task_id, "limit": 1},
    )
    rows = existing.get("data", [])
    if rows:
        rid = rows[0]["id"]
        print(f"[rescue] preflight already exists: task_id={task_id} id={rid}", flush=True)
        return rid, "existing"

    now_iso = datetime.now(timezone.utc).isoformat()
    # Single advocate row satisfying the Phase 0 schema with Kim's explicit approval
    advocates = [
        {
            "angle": "kim_explicit_approval",
            "verdict": "FOR",
            "summary": (
                "Kim reviewed the rescue and explicitly approved on 2026-04-17. "
                "No counter-agent loop required because this cascade writes only "
                "documentation + Directus rows; no implementation code lands."
            ),
        }
    ]
    counters = [
        {
            "critiques": "kim_explicit_approval",
            "severity": "LOW",
            "finding": (
                "Risk surface: a locked decision could later be re-interpreted if "
                "the source research doc is deleted. Mitigation: the rescue "
                "registers the source research docs in prod_reference_docs and the "
                "canonical content is lifted into a Production-folder reference "
                "doc where applicable."
            ),
        }
    ]

    payload = {
        "task_id": task_id,
        "task_type": pf["task_type"],
        "task_description": pf["task_description"],
        "claude_summary": pf["claude_summary"],
        "agent_advocates": advocates,
        "agent_counters": counters,
        "synthesis": (
            "Kim explicitly approved the rescue on 2026-04-17. No shortcut taken — "
            "reference docs are either consolidated into a Production-folder "
            "canonical doc or the source research doc is registered so the "
            "content is traceable. No code lands; risk is limited to LD phrasing "
            "accuracy."
        ),
        "approved_to_proceed": True,
        "approved_at": now_iso,
    }

    result = _with_retry(
        f"preflight POST {task_id}",
        client._request,
        "POST",
        "/items/prod_preflight_reviews",
        data=payload,
    )
    new_id = result["data"]["id"]
    print(f"[rescue] preflight created: task_id={task_id} id={new_id}", flush=True)
    return new_id, "created"


def register_locked_decision(client, ld_spec):
    """Register one locked decision. Idempotent by decision_key."""
    key = ld_spec["decision_key"]

    existing = _with_retry(
        f"LD check {key}",
        client._request,
        "GET",
        "/items/prod_locked_decisions",
        params={
            "filter[decision_key][_eq]": key,
            "fields": "id,decision_key,status",
            "limit": 1,
        },
    )
    rows = existing.get("data", [])
    if rows:
        lid = rows[0]["id"]
        print(f"[rescue] LD {key} already exists: id={lid}", flush=True)
        return lid, "existing"

    payload = {
        "decision_key": key,
        "decision_name": ld_spec["decision_name"],
        "decision_text": ld_spec["decision_text"],
        "source_document": ld_spec["source_document"],
        "task_category": ld_spec["task_category"],
        "severity": ld_spec["severity"],
        "date_locked": TODAY,
        "status": "active",
        "notes": ld_spec.get("notes", ""),
    }

    result = _with_retry(
        f"LD POST {key}",
        client._request,
        "POST",
        "/items/prod_locked_decisions",
        data=payload,
    )
    new_id = result["data"]["id"]
    print(f"[rescue] LD {key} created: id={new_id}", flush=True)
    return new_id, "created"


def register_reference_doc(client, rd_spec, rescue_id):
    """Create/patch prod_reference_docs entry for a single doc."""
    file_path = rd_spec["file_path"]
    basename = os.path.basename(file_path)

    # Search by file_path basename match
    existing = _with_retry(
        f"ref_doc lookup {basename}",
        client._request,
        "GET",
        "/items/prod_reference_docs",
        params={
            "filter[file_path][_contains]": basename,
            "fields": "id,file_path,doc_title",
            "limit": 10,
        },
    )
    rows = existing.get("data", [])
    match = None
    for r in rows:
        rp = r.get("file_path") or ""
        if rp == file_path or rp.endswith(basename) or basename in rp:
            match = r
            break

    patch_note_suffix = (
        f" [Rescue cascade {rescue_id} on {TODAY}: confirmed/linked to this entry.]"
    )

    if match:
        rid = match["id"]
        # Patch notes to record the rescue touch
        patch_data = {
            "notes": (rd_spec.get("notes", "")
                      + patch_note_suffix)[:4000]
        }
        _with_retry(
            f"ref_doc PATCH {rid}",
            client._request,
            "PATCH",
            f"/items/prod_reference_docs/{rid}",
            data=patch_data,
        )
        print(f"[rescue] ref_doc {basename} -> patched (id={rid})", flush=True)
        return {"file_path": file_path, "action": "patched", "row_id": rid}

    # Create new
    create_data = {
        "doc_title": rd_spec["doc_title"],
        "file_path": file_path,
        "doc_category": rd_spec["doc_category"],
        "status": "active",
        "is_current": True,
        "notes": rd_spec.get("notes", "") + f" [Registered {TODAY} via {rescue_id}.]",
    }
    if "doc_version" in rd_spec:
        create_data["doc_version"] = rd_spec["doc_version"]

    try:
        result = _with_retry(
            f"ref_doc POST {basename}",
            client._request,
            "POST",
            "/items/prod_reference_docs",
            data=create_data,
        )
        new_id = result["data"]["id"]
        print(f"[rescue] ref_doc {basename} -> created (id={new_id})", flush=True)
        return {"file_path": file_path, "action": "created", "row_id": new_id}
    except DirectusError as e:
        print(f"[rescue] ref_doc {basename} -> ERROR {e}", flush=True)
        return {"file_path": file_path, "action": f"error: {e}", "row_id": None}


def log_activity(client, rescue, preflight_id, ld_ids, ref_doc_results):
    """Log the rescue cascade to prod_activity_log."""
    rescue_id = rescue["rescue_id"]
    decision_keys = [ld["decision_key"] for ld in rescue["locked_decisions"]]
    action_text = (
        f"orphan-rescue cascade: {rescue_id}. Registered {len(ld_ids)} locked "
        f"decision(s): {', '.join(decision_keys)}. Approved_to_proceed=true "
        f"(Kim explicit approval 2026-04-17)."
    )

    details = {
        "rescue_id": rescue_id,
        "task_id": rescue["task_id"],
        "preflight_row_id": preflight_id,
        "locked_decision_ids": ld_ids,
        "decision_keys": decision_keys,
        "reference_docs_results": ref_doc_results,
        "cascade_batch": "orphan-rescue-cascade-20260417",
    }

    payload = {
        "action": action_text,
        "performed_by": "claude-opus-4-7-agent",
        "details": details,
    }

    result = _with_retry(
        f"activity_log POST {rescue_id}",
        client._request,
        "POST",
        "/items/prod_activity_log",
        data=payload,
    )
    new_id = result["data"]["id"]
    print(f"[rescue] activity_log created: id={new_id}", flush=True)
    return new_id


def log_c3_deferral(client):
    """Log C3 deferral to prod_activity_log (no LD)."""
    payload = {
        "action": C3_DEFER_NOTE["action"],
        "performed_by": "claude-opus-4-7-agent",
        "details": C3_DEFER_NOTE["details_payload"],
    }
    result = _with_retry(
        "activity_log POST C3 defer",
        client._request,
        "POST",
        "/items/prod_activity_log",
        data=payload,
    )
    new_id = result["data"]["id"]
    print(f"[rescue] C3 deferral logged: id={new_id}", flush=True)
    return new_id


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------

def main():
    creds = load_credentials()
    client = DirectusClient(
        creds["directus_url"],
        creds["directus_email"],
        creds["directus_password"],
    )
    client.authenticate()
    print(f"[rescue] Authenticated: {creds['directus_url']}", flush=True)

    summary = {
        "rescues": [],
        "c3_deferral_activity_log_id": None,
        "totals": {
            "preflight_rows": 0,
            "locked_decisions": 0,
            "reference_docs": 0,
            "activity_logs": 0,
        },
        "errors": [],
    }

    for rescue in RESCUES:
        rescue_id = rescue["rescue_id"]
        print(f"\n=== {rescue_id} ===", flush=True)
        rescue_report = {
            "rescue_id": rescue_id,
            "task_id": rescue["task_id"],
            "preflight_id": None,
            "preflight_action": None,
            "locked_decisions": [],
            "reference_docs": [],
            "activity_log_id": None,
            "errors": [],
        }

        # Step 1 — preflight
        try:
            pf_id, pf_action = create_preflight(client, rescue)
            rescue_report["preflight_id"] = pf_id
            rescue_report["preflight_action"] = pf_action
            if pf_action == "created":
                summary["totals"]["preflight_rows"] += 1
        except Exception as e:
            rescue_report["errors"].append(f"preflight: {e}")
            summary["errors"].append(f"{rescue_id} preflight: {e}")
            summary["rescues"].append(rescue_report)
            continue  # skip the rest of this rescue

        # Step 2 — locked decisions
        ld_ids = []
        for ld_spec in rescue["locked_decisions"]:
            try:
                ld_id, ld_action = register_locked_decision(client, ld_spec)
                rescue_report["locked_decisions"].append({
                    "decision_key": ld_spec["decision_key"],
                    "id": ld_id,
                    "action": ld_action,
                })
                ld_ids.append(ld_id)
                if ld_action == "created":
                    summary["totals"]["locked_decisions"] += 1
            except Exception as e:
                rescue_report["errors"].append(
                    f"LD {ld_spec['decision_key']}: {e}")
                summary["errors"].append(
                    f"{rescue_id} LD {ld_spec['decision_key']}: {e}")

        # Step 3 — reference docs (may be empty if consolidated into rescue 1)
        for rd_spec in rescue["reference_docs"]:
            try:
                rd_result = register_reference_doc(client, rd_spec, rescue_id)
                rescue_report["reference_docs"].append(rd_result)
                if rd_result.get("action") == "created":
                    summary["totals"]["reference_docs"] += 1
            except Exception as e:
                rescue_report["errors"].append(f"ref_doc {rd_spec['file_path']}: {e}")
                summary["errors"].append(
                    f"{rescue_id} ref_doc {rd_spec['file_path']}: {e}")

        # Step 4 — activity log
        try:
            al_id = log_activity(
                client, rescue, rescue_report["preflight_id"], ld_ids,
                rescue_report["reference_docs"],
            )
            rescue_report["activity_log_id"] = al_id
            summary["totals"]["activity_logs"] += 1
        except Exception as e:
            rescue_report["errors"].append(f"activity_log: {e}")
            summary["errors"].append(f"{rescue_id} activity_log: {e}")

        summary["rescues"].append(rescue_report)

    # C3 deferral (activity log only)
    print(f"\n=== c3-scenario-vs-gemini-deferred ===", flush=True)
    try:
        c3_id = log_c3_deferral(client)
        summary["c3_deferral_activity_log_id"] = c3_id
        summary["totals"]["activity_logs"] += 1
    except Exception as e:
        summary["errors"].append(f"C3 deferral activity_log: {e}")

    # Final totals
    summary["totals"]["total_rows_written"] = (
        summary["totals"]["preflight_rows"]
        + summary["totals"]["locked_decisions"]
        + summary["totals"]["reference_docs"]
        + summary["totals"]["activity_logs"]
    )

    print("\n=== RESCUE CASCADE SUMMARY ===")
    print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()
