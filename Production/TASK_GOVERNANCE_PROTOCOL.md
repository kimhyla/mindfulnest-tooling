# Task Governance Protocol v1.0

**Created:** April 15, 2026
**Purpose:** Maps every task category to its governing documents and locked decisions. Claude reads this at the start of any non-trivial task (CLAUDE.md Rule 16) to prevent the class of failures where locked decisions are contradicted because the relevant doc wasn't checked.

**Location of skill governance files:** `Production/governance/<skill-name>_governance.md`

---

## How to Use This Protocol

1. **Identify the task category** from the taxonomy below
2. **Apply cross-cutting inheritance** (see next section) — some categories are *transverse* and attach to any task meeting a condition, even if you already picked a primary category
3. **Read the governing docs** listed for every category you've pulled in (locked decision sections at minimum)
4. **Confirm compliance** before proceeding: "I have read [docs] and understand locked decisions [list]"
5. **If the task spans multiple categories**, read ALL governing docs for all applicable categories

This is a BLOCKING gate — do not skip it to save time. The 5 past failures this prevents each cost hours of rework.

---

## Cross-Cutting Category Inheritance

Some categories are **transverse** — they attach to a task in addition to the primary category whenever a condition holds. Check these conditions every time, even after you think you've categorized the task. A task can (and often will) inherit multiple transverse categories.

| Condition on the task | Also inherits | Why |
|---|---|---|
| **Calls an external API (any service, any endpoint)** | Category 5 (API Integration) | The curl→Python rule (lesson T-2) is scoped to *any* credential passing through bash, not just Directus. Naive Claudes miss this because they look up the task's primary domain (e.g. "video production") and never ask "am I also making an HTTP call with a secret?" |
| **Edits a file Kim may have touched** (any `.docx` narrative doc, any `.md` reference doc she's known to edit, anything in an active skeleton) | Category 9 (Document Editing / Cross-Document Updates) — which enforces CLAUDE.md Rules 2–3 (version-up, read-before-write, Kim-confirmation gate) | Kim's edits between sessions are the single largest data-loss risk. Rule 3's confirmation gate must fire for *any* file Kim touches, not only files the primary category knows about. |
| **Writes to ANY Directus collection** (assets, activity, modules, reference docs, session decisions, etc.) | Two-Write Rule from `Production/DIRECTUS_REGISTRATION_COMPLIANCE_GATE_v1.md` | Every Directus write to a production artifact must be paired with an activity-log write. This is enforced at the registration compliance gate level, not at the domain skill level, so it's easy to miss if you only read the primary category's docs. |

**How to apply:** after you've named your primary category, run through these three conditions in order. For each one that fires, append the inherited category's governing docs to your reading list *before* Step 3 of the procedure above.

**Worked example:** Task = "Generate a Kling clip for Tessa via WaveSpeed, then register the MP4 in `prod_visual_assets`."
- Primary: Category 2 (Video/Animation Production)
- Inherits Category 5 (makes an external API call to WaveSpeed)
- Inherits Two-Write Rule (writes to `prod_visual_assets`)
- Final reading list: CLAUDE.md Rule 8, PIPELINE_BRAIN video section, `video-producer_governance.md`, `API_KEYS_MASTER.md`, lesson T-2, `DIRECTUS_REGISTRATION_COMPLIANCE_GATE_v1.md`

---

## Task Category Taxonomy

### 1. Audio Production
**Governing docs:**
- `Production/PIPELINE_BRAIN_v1.md` (audio section)
- `TTS_PERSONALIZATION_PIPELINE_v1.md`
- `CLAUDE.md` Rule 8 (lip-sync prevention)
- `Production/governance/audio-producer_governance.md`

**Key locked decisions:**
- Myrrhin voice: stability 0.70, speed 0.50 (query `prod_voice_profiles`)
- Model: `eleven_v3` for all characters
- Delivery: QuickTime Player via Finder (never `computer://` links)
- Sequential execution at audio stage (no parallelization)
- Voice stem is timing master (never estimate from word counts)
- Vosk STT for cue points (never manual timing)

**Past failure prevented:** Re-trying voice settings Kim already rejected (April 11, 2026)

---

### 2. Video / Animation Production
**Governing docs:**
- `CLAUDE.md` Rule 8 (motion prompt lip-sync prevention — CRITICAL)
- `Production/PIPELINE_BRAIN_v1.md` (video section)
- `Production/governance/video-producer_governance.md`

**Key locked decisions:**
- Default model: Kling v3.0 Pro (NOT Seedance unless Kim requests)
- Seedance = experimental, requires Lip-Sync Review Gate for EVERY clip
- Banned words in ALL motion prompts: `speaking`, `speech`, `dialogue`, `lip sync`, `lip movement`, `mouth movement`, `beak movement`, `talking`, `singing`, `vocal`
- Required API params: `sound: false`, negative_prompt with lip-sync terms, `cfg_scale: 0.5`
- Style: Pixar 3D (NOT painterly — superseded April 10, 2026)
- Never cross-paste between AI generators
- Single-master-crop approach for character consistency

**Past failures prevented:**
- Seedance producing Chinese lip-sync on cartoon characters (April 14, 2026)
- Per-character stills destroying visual consistency

---

### 3. Storyboard Rebuild / HTML Production Tools
**Governing docs:**
- `CLAUDE.md` Rule 7 (Two-Path Protocol — CRITICAL)
- `Production/PIPELINE_BRAIN_v1.md` (storyboard section)
- `Production/governance/storyboard-producer_governance.md`

**Key locked decisions:**
- Two permitted methods only: Path A (Python builder) or Path B (JS-only patch)
- FORBIDDEN: Direct HTML editing, base64 injection, hand-writing HTML
- Pre-rebuild browser-edit gate: ask Kim if she has unsaved drag-drop edits
- Export-first rebuild protocol: Kim's exported JSON is MANDATORY primary source
- Never guess at disk file paths — extract from current HTML
- Always run `--audit` before and `--audit-previous` after rebuild

**Past failure prevented:** 5 production failures on April 13, 2026 (scrambled images, lost drag-drop, wrong base64)

---

### 4. Tech Stack / Architecture Decisions
**Governing docs:**
- `APP_DEV_AUTOMATION_ARCHITECTURE_v1.md` (locked tech stack)
- `AI_PARENT_COACH_DECISIONS_EXTRACTED.md` (Architecture A decisions)
- `CLAUDE.md` Rule 13 (read existing docs before generating analysis)

**Key locked decisions:**
- React Native + Expo (NEVER Next.js, NEVER Flutter)
- AI Parent Coach: Architecture A (COPPA-only, template-based, no HIPAA)
- Claude API backend with smart routing (60% Haiku, 30% Sonnet, 10% Opus)
- SMS/WhatsApp for coaching delivery (not push notifications)

**Past failure prevented:** Recommending Next.js instead of locked React Native stack

---

### 5. API Integration / External Service Calls
**Governing docs:**
- `Production/API_KEYS_MASTER.md`
- Lessons learned documents (curl vs. Python rule)

**Key locked decisions:**
- ALWAYS use Python `urllib.request` (or Node) for any external API call carrying credentials — NEVER curl. Root cause: bash `$` interpolation + credential inline exposure. See lesson T-2.
- JWT tokens expire in 15 minutes — re-authenticate for long operations
- ElevenLabs API key from API_KEYS_MASTER.md (never hardcode)
- WaveSpeed API key shared between Kling (default) and Seedance (experimental/alt)

**Past failure prevented:** curl silently truncating Directus password at `$` character, causing auth failures (April 15, 2026, lesson T-2). The rule generalizes beyond Directus to any service whose credentials pass through bash.

---

### 6. Phase B Script Writing
**Governing docs:**
- `ARC_PRODUCTION_BIBLE_v2_10.md`
- `UNIFIED_TECHNIQUE_INVENTORY_v1_14.md`
- Active creature skeleton (check which version is current)
- `CLAUDE.md` Rule 11 (Source Fidelity Protocol)

**Key locked decisions:**
- 7-section template (Opening Bell → Grounding → Instruction → Deepening → Integration → Landing → Closing)
- Myrrhin is narrator for ALL Phase B meditations
- Sensation language belongs to Phase B only (not Phase A)
- Cue markers placed on line BEFORE narration they accompany
- Kim-authored dialogue preserved VERBATIM

---

### 7. Phase A Design
**Governing docs:**
- `ARC_PRODUCTION_BIBLE_v2_10.md`
- `CLAUDE.md` Phase A rules
- Active creature skeleton

**Key locked decisions:**
- Phase A shows WHAT (ingredients + outcome), NOT HOW
- No vocabulary cards, no sensation language, no elaborate mechanics
- Guide Bird ALWAYS narrates (never silent)
- Child's character performs the action (not Guide Bird)
- One demo cycle only
- Runtime duration under 30 seconds

---

### 8. Arc Skeleton / Narrative Work
**Governing docs:**
- `CLAUDE_Everdale_World_Design_Bible_v13_10.md` (Bible)
- `NARRATIVE_DECISIONS_UNIFIED_v2_8.md` (NDU — often more current than Bible)
- `ArcBuilder_v2_3.md`
- `CLAUDE.md` Rules 11-12 (Source Fidelity, M-Number Convention)

**Key locked decisions:**
- M-numbers FIXED to creatures (M1=Tessa, M2=Luna, M3=Benson, M4=Ember, M5=Bork, M6=Bramble)
- Play order ≠ M-number order
- Three Questions Gate before any Phase A/B work
- Kim-authored dialogue preserved VERBATIM
- Screen direction is binding (not suggestions)

---

### 9. Document Editing / Cross-Document Updates
**Governing docs:**
- `CLAUDE.md` Rules 2-3 (version-up, read-before-write, Kim-confirmation gate)
- `Production/governance/verified-edit_governance.md`
- `Production/governance/cross-document-update_governance.md`

**Key locked decisions:**
- Version-up, never overwrite (create new filename)
- Single-format workflow (.docx for working docs, .md for reference docs)
- Kim-confirmation gate before ANY file write (BLOCKING, with full filename)
- Read current file from disk immediately before writing
- Detailed change report: filename, line number, old text, new text

---

### 10. Business / Pricing / Strategy Analysis
**Governing docs:**
- `MindfulNest_CRI_Parent_System_Business_Model_v1.md`
- `MINDFULNEST_PRICING_STRATEGY_ANALYSIS.md`
- `PRICING_RESEARCH_UPDATE_March2026.md`
- `CLAUDE.md` Rule 13 (MANDATORY — read existing docs first)

**Key locked decisions:**
- B2C model with therapist distribution (NOT B2B)
- $499 one-time for 6-month program (supersedes $89/month)
- Tiered lump-sum commissions ($200-$275/family)
- Near-zero cost structure (Kim + AI tools, no engineering team)

---

## Governance File Locations

Each production skill's governance constraints are documented in `Production/governance/`:

| Skill | Governance File | Priority |
|-------|----------------|----------|
| video-producer | `video-producer_governance.md` | HIGH (lip-sync gate) |
| audio-producer | `audio-producer_governance.md` | HIGH (voice settings) |
| storyboard-producer | `storyboard-producer_governance.md` | HIGH (Two-Path Protocol) |
| dashboard-gate | `dashboard-gate_governance.md` | MEDIUM |
| dashboard-ops | `dashboard-ops_governance.md` | MEDIUM |
| arcbuilder | `arcbuilder_governance.md` | MEDIUM |
| video-expander | `video-expander_governance.md` | MEDIUM |
| cross-document-update | `cross-document-update_governance.md` | LOW |
| verified-edit | `verified-edit_governance.md` | LOW |

**Phase 1 (April 15, 2026):** video-producer and audio-producer governance files created with full content.
**Phase 2 COMPLETE (April 15, 2026):** All 9 governance files fully expanded with validation checklists, pseudocode, failure handling, and past failure references. Verified by verification agent + counter-agent adversarial review.
**Phase 3 COMPLETE (April 15, 2026):** Directus `prod_locked_decisions` collection created (14 fields, 99 decisions). Queryable by task_category, severity, governance_file, status. All 11 categories covered. 12 entries cross-reference past failures.

---

## Quick Reference: The 5 Past Failures This System Prevents

| # | Failure | Root Cause | Governing Doc That Would Have Prevented It |
|---|---------|------------|---------------------------------------------|
| 1 | Next.js instead of React Native | Didn't read locked tech stack | APP_DEV_AUTOMATION_ARCHITECTURE_v1.md |
| 2 | Per-character stills instead of single-master-crop | Didn't read CLAUDE.md Rule 6 | CLAUDE.md Rule 6 (now Rule 7) |
| 3 | Seedance without lip-sync review gate | Didn't read CLAUDE.md Rule 8 | CLAUDE.md Rule 8 |
| 4 | Skipped PIPELINE_BRAIN before production | Didn't read governing doc | Production/PIPELINE_BRAIN_v1.md |
| 5 | Used curl instead of Python for API calls | Didn't read lessons learned | API_KEYS_MASTER.md + lessons learned |
| 6 | urllib stuck-state poll-hang for hours in long-running server | Used module-level urllib opener + cached SSL context | `prod_locked_decisions` 137 POLL_CLIENT_ROOT_CAUSE_HTTP_CLIENT; `production_server.py` `_wavespeed_request` |
| 7 | Silent "Submitting…" revert on Generate B+C | `/api/beat/add_options` returned 200 with `new_submitted:0`; `/api/animate/status` filtered out polling options | Tier 1 fixes; `prod_locked_decisions` 129 EXP_BACKOFF_POLL_RETRY |
| 8 | Cross-machine race on production_state.json | fcntl.lockf is local-only on Dropbox-synced volume | `prod_locked_decisions` 132 CROSS_MACHINE_DIRECTUS_LOCK; this file "dev_infrastructure_cross_machine" category |

---

## Task Categories Added April 16 2026

Three new task categories surfaced during Tier 1 + Tier 3 + blind-spot remediation. Each maps to specific governing docs + locked decisions.

### Category: `production_server_infrastructure`
Changes to `Production/tools/production_server.py`, the long-running Python HTTP server. High blast radius — affects animation, lipsync, drag-drop, recovery, cross-machine coordination.

**Governing docs:** CLAUDE.md Rule 19 (no shortcuts), Rule 7 (HTML Two-Path), `Production/PIPELINE_BRAIN_v1.md` §19, this file.

**Locked decisions to verify against before editing:**
- `POLL_CLIENT_ROOT_CAUSE_HTTP_CLIENT` (id=137) — all WaveSpeed HTTP must use the fresh-connection helper, not raw urllib.
- `EXP_BACKOFF_POLL_RETRY` (id=129) — `MAX_RETRIES` + `RETRY_BACKOFF_EXTRA_SEC` must stay length-aligned (enforced by assert).
- `PRE_FAIL_CDN_RECHECK` (id=130) — retry behavior includes async CDN re-check; do not remove.
- `CROSS_MACHINE_DIRECTUS_LOCK` (id=132) — all `StateManager.mutate_state` / `add_spend` / `override_budget` paths MUST acquire the Directus lock.
- `ATOMIC_DOWNLOAD_TMP_RENAME` (id=134) — `WaveSpeedClient.download` must write through tmp.
- `WAVESPEED_STARTUP_SMOKE_TEST` (id=133) — server startup must run the 5s smoke test.
- `ANIMATION_DURATION_MATCHES_AUDIO` (id=144) — both `_handle_add_options` and `_handle_animate` MUST infer duration from `_find_beat_audio` + `_infer_animation_duration`. Explicit `duration` in body must be 5 or 10 only. Audio > 10s raises, never truncates.
- `AUDIT_BEAT_DURATIONS_TOOL` (id=145) — `Production/scripts/audit_beat_durations.py` must stay in sync with server's `_find_beat_audio` priority ladder (duplicated for tool isolation; drift = silent bugs).

**Pre-flight rigor:** architectural (4+4 agents per Phase 0) for any change that touches retry logic, lock logic, HTTP client behavior, or state-persistence paths.

### Category: `task_recovery`
Changes to the manual recovery CLI tool `Production/tools/recover_stuck_tasks.py` or the runbook at `Production/RUNBOOKS/recover_stuck_wavespeed_task.md`.

**Governing docs:** `prod_locked_decisions` id=131 (CDN_RECOVERY_TOOL_PRIMARY), `prod_reference_docs` id=44 (runbook), CLAUDE.md Rule 18 (Two-Write), Rule 19 (no shortcuts).

**Invariants the tool MUST preserve:**
1. Idempotency via `recovered_from_cdn_at` marker — already-recovered rows are skipped.
2. Winner-lock — only `--force-beat` overrides beats that have `selected_option` or any completed option.
3. Spend-ledger deduplication — `StateManager.add_spend(..., task_id=X)` is a no-op if task_id already in `spend_ledger.jsonl`.
4. Primitives imported from `production_server`, never duplicated.

**Pre-flight rigor:** architectural for any change to the 3 safeguards; routine for CLI ergonomics.

### Category: `dev_infrastructure_cross_machine`
Changes that affect Kim's ability to work from her Mac AND her Windows machine. Covers Claude Code install, Directus auth, Dropbox sync expectations, `PRODUCTION_SERVER_SINGLE_MACHINE` escape hatch.

**Governing docs:** CLAUDE.md Rule 5 (Dropbox-synced workflow), `prod_locked_decisions` id=142 (WINDOWS_WORK_MACHINE_SECONDARY_DEV_ENV), id=132 (CROSS_MACHINE_DIRECTUS_LOCK).

**Invariants:**
1. Single-writer guarantee via Directus `prod_locks` — second machine must refuse to start if first machine holds the lock.
2. Fail-closed on Directus unreachable (env escape hatch documented).
3. State-file writes are atomic (tmp+rename) so Dropbox can't sync a half-written JSON.

**Pre-flight rigor:** architectural for any change to the lock protocol; routine for docs/setup updates.

### Category: `stitch_pipeline` (future — Tier 4)
Changes to the scene-assembly pipeline when built. See `Production/governance/storyboard-producer_governance.md` "Stitch Pipeline Decisions" section for the full invariants (`STITCH_ARCHITECTURE_MULTI_STAGE` id=139, `STITCH_WORKFLOW_PREVIEW_THEN_COMMIT` id=140, `STITCH_BUTTON_LOCATION_STORYBOARD_OVERLAY` id=141).
