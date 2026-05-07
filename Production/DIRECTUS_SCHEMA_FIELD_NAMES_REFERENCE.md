# Directus Schema Field Names — Reference

**Status:** active reference. Live-schema snapshot taken 2026-04-28 from
`https://directus-production-3460.up.railway.app`. **Enum values for
`prod_locked_decisions` re-verified against live schema 2026-05-04 after
S5.5c+e proper-fix terminal hit deviations.** See "Enum migration note
2026-05-04" below the enum tables in §1.
**Why this doc exists:** the v6 follow-up session (preflight #176, activity_log #1408)
caught 8 distinct mismatches between handoff-prompt field names and live Directus
schema. Each mismatch costs ~10–15 minutes of "halt and surface" friction at
runtime. This doc is the canonical mapping so the next handoff author starts
from the actual schema, not from inferred names.

**How to use:** before writing any Directus task into a handoff prompt, scan
the relevant collection section here. If a field you intend to reference
appears under "common mistakes," fix the prompt before sending. If you need
fresher data than this snapshot, query `/fields/<collection>` directly — that
is always the authoritative source.

**Related artifacts:**
- preflight #176 (`v6-spec-followup-directus-parity-20260428`) — risk register R5/R6/R7 cite these
- activity_log #1408 — `details.schema_mapping_deviations[]` lists all 8 in machine-readable form

---

## Universal rules

1. **Use Python `urllib.request` only.** Curl breaks on the `$` in the Directus
   admin password (Rule 18). The `directus_lib.py` helper at
   `/tmp/mn_v6_followup/directus_lib.py` (or any equivalent) handles JWT refresh
   on a 13-min window inside the 15-min TTL.
2. **Read-before-write on every row.** Capture current text/state, then PATCH
   with the additive change. Never replace `decision_text` wholesale unless the
   handoff explicitly says "replace."
3. **Verify by re-query after every write.** A successful HTTP 200 is necessary
   but not sufficient — re-fetch the row and assert the change landed.
4. **Field names ≠ what feels natural.** Directus collections grew organically;
   field naming is inconsistent across collections. Do NOT assume `title` or
   `version` or `date` exist on a given collection. Always check.

---

## 1. `prod_locked_decisions`

### Live fields (snapshot 2026-04-28)

| field | type | nullable | notes |
|---|---|---|---|
| `id` | integer | no | auto |
| `decision_key` | string | no | unique convention; UPPER_SNAKE_CASE_V<n> |
| `decision_name` | string | no | human-readable title |
| `decision_text` | text | no | the actual decision body |
| `source_document` | string | no | append with ` \| <new doc>` to chain provenance |
| `task_category` | string | no | **enum — see below** |
| `severity` | string | no | **enum — see below** |
| `governance_file` | string | yes | optional path to skill governance file |
| `past_failure_prevented` | text | yes | what mistake this LD prevents |
| `status` | string | no | **enum — see below** |
| `superseded_by_id` | integer | yes | FK to the LD that replaced this one |
| `date_locked` | date | no | YYYY-MM-DD |
| `date_superseded` | date | yes | YYYY-MM-DD when status flipped |
| `notes` | text | yes | append-with-`\| `; never overwrite |
| `related_files` | json | yes | array of file paths |
| `keyword_synonyms` | json | yes | array of search aliases |
| `enforcement_type` | string | yes | usually `awareness_only` |
| `enforcement_artifact_ref` | text | yes | pointer to script/test if mechanically enforced |
| `is_current` | boolean | yes | flip to `false` when superseded |
| `scope_domain` | string | yes | **enum — see below** |
| `supersedable` | boolean | yes | default `true` |
| `schema_version` | integer | no | currently `2` |

### Enum values (re-verified live 2026-05-04 via `/fields/prod_locked_decisions/<field>`)

- **`status`** — `{active, superseded}` only. **`active_conditional` is NOT
  valid.** When a decision is conditional, set `status="active"` and put
  `(CONDITIONAL)` in `decision_name` + describe the condition in
  `decision_text` and `notes`.
- **`severity`** — **`{HARD, SOFT}` per LIVE schema.** Schema migrated
  between 2026-04-28 and 2026-05-04 from `{CRITICAL, HIGH, MEDIUM, LOW}`
  to `{HARD, SOFT}`. **Historical rows still hold the old values** (113
  HIGH / 56 MEDIUM / 14 LOW + lowercase variants observed 2026-05-04);
  write validators do NOT enforce the new enum, so old values appear to
  succeed. **For all NEW writes use HARD or SOFT.** Heuristic: `HARD` =
  behaviorally enforced / can break things if violated (replaces CRITICAL
  + HIGH); `SOFT` = awareness/UX/cosmetic (replaces MEDIUM + LOW). New
  LDs 506-510 (S5.5c+e proper-fix) follow this convention.
- **`scope_domain`** — `{content, production, app-dev, infra, cross-cutting}`
  per LIVE schema. (`content` and `production` were added since the
  2026-04-28 snapshot.) Use `cross-cutting` when the decision touches
  multiple streams.
- **`task_category`** — LIVE schema choice list is now restricted to 11
  values: `audio`, `video`, `storyboard`, `tech_stack`, `api_integration`,
  `phase_b`, `phase_a`, `narrative`, `documents`, `business`, `all`.
  **Historical rows hold many values not in this list** (animation_production,
  app_architecture, architectural, character_design, data_model,
  dev_infrastructure, governance, infrastructure, narrative_production,
  process, process_governance, production_infrastructure,
  production_pipeline_server, production_server_infrastructure,
  production_tool_ui, security, video_production, visual_production,
  audio_production). **For NEW writes use one of the 11 live choices.** If
  none fits, `all` is the safe fallback.
- **`enforcement_type`** — LIVE schema enum is `{structural, db_rule,
  linter, ci_check, test, lockfile, wrapper, code_invariant,
  awareness_only, human_gate}` (10 values). Pick one based on actual
  enforcement mechanism: `ci_check` for CI workflow gates (e.g.,
  CI_PLAYWRIGHT_ON_COMMIT_V1); `test` for behaviors enforced by
  Playwright/unit tests; `awareness_only` only when no mechanical
  enforcement exists (avoid this when something stronger applies);
  `code_invariant` for things like patch-invariants enforced in code;
  `human_gate` for review-required decisions; etc.

### Enum migration note 2026-05-04

The live schema enum for `severity`, `scope_domain`, `task_category`, and
`enforcement_type` was modified after the 2026-04-28 snapshot — likely
between v6 follow-up (preflight #176) and S5.5c+e proper-fix (preflight
#201). The migration was schema-only; row data was not migrated, so:

1. Existing LDs (1-505) still hold the old enum values
2. Write validators do NOT reject old values (they're stored as plain
   strings even though the schema declares an enum)
3. New writes should use the LIVE values from the tables above
4. Mixed-enum coexistence is the steady state until/unless a backfill
   migration runs

This was discovered when proper-fix terminal queried `/fields/.../severity`
and found `[HARD, SOFT]` instead of the expected uppercase tier list. The
5 LDs created in that session (506-510) all use the new convention.

Practical rule for handoff authors: **always re-verify enum choices via
`GET /fields/<collection>/<field>` before locking a handoff that writes
to one of these fields.** Schema migrations are silent.

### Common handoff mistakes → correct mapping

| Handoff says | Reality | Map to |
|---|---|---|
| `supersedes_id: <old_id>` on the new row | **No such field on prod_locked_decisions.** | Express the supersession one-directionally: PATCH the OLD row with `superseded_by_id=<new_id>`, `status=superseded`, `is_current=false`, `date_superseded=YYYY-MM-DD`. Document the inverse pointer in the new row's `notes` for human readability. |
| `last_modified_date` | No such field. | Append `" \| <date>: <change>"` to `notes` and append source to `source_document`. |
| `status: active_conditional` | Not a valid enum value. | `status="active"` + `(CONDITIONAL)` in `decision_name` + condition spelled out in `decision_text` and `notes`. |
| `task_category: app_animation` | Not in enum. | `tech_stack` (closest accurate). |
| `task_category: operations_compliance` | Not in enum. | `operations` (matches existing STREAM_G family). |
| `source_document: <245+ char chain>` | varchar(200) — Directus rejects with a misleading 400 error pointing at `date_locked` instead of source_document. | Put a short summary (`<200 chars`) in `source_document`; full provenance chain goes in `notes` (text, no cap). |

> **Note:** `prod_reference_docs` *does* have a real `supersedes_id` field — but
> `prod_locked_decisions` does not. They look symmetrical from the outside;
> they are not.

### varchar max_length constraints (added 2026-05-02, activity_log id=1445)

The `type` column above lists data type but NOT length. The string fields on
this collection have these caps (queried via `/fields/prod_locked_decisions`):

| field | varchar length |
|---|---|
| `decision_key` | 100 |
| `decision_name` | 200 |
| `source_document` | 200 |
| `task_category` | 50 |
| `severity` | 10 |
| `status` | 20 |
| `governance_file` | 200 |
| `enforcement_type` | 255 |
| `scope_domain` | 255 |

`decision_text`, `past_failure_prevented`, `notes`, `enforcement_artifact_ref`
are `text` and have no length cap.

**Misleading error message:** When ANY of the varchar fields above exceeds its
limit, Directus returns
`Value "<your value>" for field "date_locked" in collection "prod_locked_decisions" is too long.`
— with the WRONG field name. The error mentions `date_locked` regardless of
which field actually overflowed. Bisect via minimal-payload retries to find
the real offender.

**Origin incident:** 2026-05-02 Path C rewrite Session 1 LD registration. The
initial handoff-derived `source_document` was a 245-char provenance chain
("LESSONS_LEARNED... | Session 2 handoff prompt 2026-05-02 | 6-agent
advocate/counter debate... | 2-agent Opus tech-spec... | Cursor cross-review...").
Directus 400'd with the misleading message. Solution: shortened
`source_document` to 148 chars; moved full chain to `notes` (text/unlimited)
under a `[provenance]` heading. Both LDs (id=455 PATH_C_REWRITE_V1, id=456
SCOPE_VALIDATION_V1) then landed cleanly.

---

## 2. `prod_reference_docs`

### Live fields (snapshot 2026-04-28)

| field | type | nullable | notes |
|---|---|---|---|
| `id` | integer | no | auto |
| `doc_title` | string | no | **NOT `title`** |
| `file_path` | string | no | relative to project root |
| `doc_version` | string | yes | **NOT `version`**. Convention: `"v6"`, not `"6"` |
| `doc_category` | string | no | **REQUIRED**, enum (~40 in use — see below) |
| `status` | string | no | `active` / `superseded` |
| `is_current` | boolean | no | **REQUIRED** |
| `has_locked_decisions` | boolean | no | **REQUIRED** — true if the doc *contains* LDs (not just references them) |
| `chain_id` | string | yes | optional grouping for doc lineages |
| `tags` | json | yes | array of strings |
| `notes` | text | yes | |
| `created_at` | timestamp | no | auto |
| `updated_at` | timestamp | no | auto |
| `superseded_by_id` | integer | yes | FK |
| `supersedes_id` | integer | yes | FK — exists here, unlike on prod_locked_decisions |

### `doc_category` values currently in use (2026-04-28)

`External Reference`, `Marketing Resource`, `app_architecture`, `app_config`,
`arc_skeleton`, `architectural`, `architecture`, `autonomous_build_handoff`,
`build_plan`, `business`, `canonical_architecture`, `ci_workflow`, `clinical`,
`clinical_reference`, `data_model`, `gameplay_scope`, `governance`,
`governance_infrastructure`, `handoff`, `implementation_spec`,
`infrastructure`, `lessons_learned`, `narrative_design`, `operations`,
`patch_report`, `patcher_script`, `phase0_report`, `production_artifact`,
`production_process`, `production_script`, `production_tool`,
`proof_of_execution`, `reference`, `runbook`, `scope_handoff`,
`session_checkpoint`, `session_handoff`, `skill`, `strategic_brainstorm`,
`tech_spec`, `technical_spec`, `validation_report`, `visual_asset_folder`.

### Common handoff mistakes → correct mapping

| Handoff says | Reality | Map to |
|---|---|---|
| `title: "..."` | No such field. | `doc_title` |
| `version: "6"` | No such field; convention is the `v` prefix. | `doc_version: "v6"` |
| `date: <today>` | No such field. | Auto via `created_at` |
| (no `doc_category`) | Required field missing — POST will succeed only if you supply one. | Inherit from the predecessor row when version-upping (e.g., v5→v6 → `architecture`) |
| (no `has_locked_decisions`) | Required field missing. | `true` if the doc contains LDs; `false` if it references them |

---

## 3. `prod_preflight_reviews`

### Live fields (snapshot 2026-04-28)

| field | type | nullable | notes |
|---|---|---|---|
| `id` | integer | no | auto |
| `task_id` | string | no | task slug, e.g. `v6-spec-followup-directus-parity-20260428` |
| `task_type` | string | no | classification: `architectural`, `routine`, `trivial` |
| `task_description` | text | no | short description |
| `claude_summary` | text | no | **REQUIRED** — full reasoning, risk register, deviations |
| `agent_advocates` | json | yes | array of advocate objects (any shape) |
| `agent_counters` | json | yes | array of counter objects (any shape) |
| `synthesis` | text | yes | post-debate consensus; append OUTCOME at closeout |
| `approved_to_proceed` | boolean | no | **REQUIRED** — `true` once synthesis is reached |
| `approved_at` | timestamp | yes | set at closeout, not creation |
| `created_at` | timestamp | no | auto |
| `related_activity_log_id` | integer | yes | FK back to the activity_log row that closed this work |

### Common handoff mistakes → correct mapping

| Handoff says | Reality | Map to |
|---|---|---|
| `task_class: "ARCHITECTURAL"` | No such field. | `task_type: "architectural"` (lowercase to match existing rows) |
| `advocates_count: 4` (integer) | No such field. | `agent_advocates: [{...}, {...}, {...}, {...}]` (JSON array; shape is free-form) |
| `counters_count: 3` (integer) | No such field. | `agent_counters: [{...}, {...}, {...}]` (JSON array) |
| `risk_register: "..."` | No such field. | Embed in `claude_summary` as a labeled section (e.g. `Risk register: R1 ...; R2 ...`) |
| `linked_doc: "..."` | No such field. | Embed in `claude_summary` text |
| `session_id: "..."` | No such field. | Embed in `claude_summary` text |
| `status: "in_progress"` / `"completed"` | No such field. | Use `approved_to_proceed` (set at start) and `approved_at` (set at closeout) |
| `completed_at: <ts>` | No such field. | Use `approved_at` |
| `outcome_notes: "..."` | No such field. | Append `"\n\nOUTCOME (closed YYYY-MM-DD): ..."` to `synthesis` at closeout |
| `date: <today>` | No such field. | Auto via `created_at` |

---

## 4. `prod_activity_log`

### Live fields (snapshot 2026-04-28)

| field | type | nullable | notes |
|---|---|---|---|
| `id` | integer | no | auto |
| `module_id` | integer | yes | FK to prod_modules; null for cross-module activity |
| `action` | text | no | **REQUIRED** — short slug, e.g. `directus_registry_sync_v6_followup` |
| `details` | json | yes | free-form; use this for everything that doesn't fit a named field |
| `performed_by` | text | yes | actor identifier, e.g. `claude_code_terminal_session` |
| `created_at` | timestamp | yes | auto |
| `voice_settings` | json | yes | TTS-specific |
| `script_version` | string | yes | TTS/audio-specific |
| `kim_verdict` | string | yes | `approved` / `rejected` / `needs_revision` |
| `kim_feedback` | text | yes | Kim's verbatim words; never paraphrase |
| `asset_id` | integer | yes | FK to prod_assets when relevant |

### Common handoff mistakes → correct mapping

| Handoff says | Reality | Map to |
|---|---|---|
| `activity_type: "..."` | No such field. | `action: "..."` |
| `description: "..."` | No such field. | `details: { "description": "...", ... }` (JSON) |
| `summary: "..."` | No such field (silently drops on POST per S5.5g Phase A 2026-05-04). | `details: { "summary": "...", ... }` (JSON) |
| `linked_doc: "..."` | No such field. | `details: { "linked_doc": "...", ... }` |
| `actor: "..."` | No such field. | `performed_by: "..."` |
| `timestamp: <iso>` | No such field. | Auto via `created_at` (do not provide; let server set it) |

---

## 5. `prod_blockers`

### Live fields (snapshot 2026-04-28)

| field | type | nullable | notes |
|---|---|---|---|
| `id` | integer | no | auto |
| `module_id` | integer | yes | FK; null for cross-module blockers |
| `severity` | unknown | yes | values seen: `low`, `medium`, `high` (lowercase) |
| `title` | text | no | required, short |
| `description` | text | yes | full closure plan, dependencies, criteria |
| `is_resolved` | boolean | yes | filter open with `is_resolved=false` |
| `created_at` | timestamp | yes | auto |
| `resolved_at` | timestamp | yes | set when flipped to resolved |

> **Note:** `prod_blockers.severity` is lowercase (`high`/`medium`/`low`),
> while `prod_locked_decisions.severity` is uppercase (`HIGH`/`MEDIUM`/`LOW`/`CRITICAL`).
> Mind the case.

---

## 6. `prod_session_decisions`

### Live fields (snapshot 2026-04-28)

| field | type | nullable | notes |
|---|---|---|---|
| `id` | integer | no | auto |
| `session_date` | string | yes | `YYYY-MM-DD` |
| `module_id` | integer | yes | FK |
| `decision` | text | no | what was decided |
| `context` | text | yes | why / surrounding context |
| `decided_by` | string | yes | `kim` / `claude` / `claude_phase_0_4plus4` / etc. |
| `created_at` | timestamp | yes | auto |

---

## 7. `coppa_data_flows`

**Created 2026-04-28 by preflight #176 per v6 §16.** This is the G0 gate
artifact that replaced the old static markdown table.

### Schema

| field | type | nullable | notes |
|---|---|---|---|
| `id` | integer | no | auto |
| `data_flow_name` | string | no | unique slug |
| `child_data_involved` | string | no | what child data flows through this path |
| `third_party` | string | yes | external vendor (KWS, Anthropic Managed Agents, firebase ext, etc.); null if first-party only |
| `consent_required` | boolean | no | default `true` |
| `enforcement_point` | string | no | file path or middleware identifier |
| `test_path` | string | yes | relative path to test file |
| `status` | string | no | enum: `built` / `tested` / `deployed` / `audited` / `not_scoped` |
| `launch_blocker_for_gate` | string | no | enum: `G0` / `G1` / `G2` / `G3` / `G4` / `none` |
| `last_audit_date` | date | yes | |
| `notes` | text | yes | |

### Authority for collection creation

The handoff prompt for the v6 follow-up specified the schema explicitly and
gated creation on Kim's approval. Authorization recorded in preflight #176
(claude_summary R2): Kim's session-start grant
("Full autonomous mode, dangerously accept edits, all permissions and
approvals granted") + handoff's verbatim schema spec. Created with exactly the
11 fields listed above; enums implemented via Directus `select-dropdown`
interface with explicit `choices` arrays.

### Initial population (8 V1 rows)

Per handoff Step 6b. See activity_log #1408 `details.rows_touched.coppa_data_flows_rows`
for the full ID list.

---

## 8. Collections that look symmetrical but aren't

| Pair | Asymmetry |
|---|---|
| `prod_reference_docs` vs `prod_locked_decisions` | Both have `superseded_by_id`. Only `prod_reference_docs` also has `supersedes_id`. On `prod_locked_decisions`, the supersession chain is one-directional. |
| `prod_blockers.severity` vs `prod_locked_decisions.severity` | Lowercase vs uppercase. |
| `prod_activity_log.action` vs `prod_session_decisions.decision` | Both are the "what happened" field. Different names. |
| `created_at` vs `date_locked` | `created_at` is auto on every collection. `date_locked` is a manual ISO date on `prod_locked_decisions` only. |

---

## 9. JSON-typed columns — payload format pitfall

When posting to a Directus column of `type: json` (e.g. `prod_preflight_reviews.agent_advocates`, `prod_preflight_reviews.agent_counters`, `prod_activity_log.details`), send the **native Python dict/list**, NOT a JSON-stringified value. Directus accepts strings (it will auto-parse them) but the read-back returns a parsed object, which trips `try_post_or_queue`'s byte-equality check and produces a false-positive `silent_write_failure`. The data IS stored correctly; only the equality check is misled.

**Right:** `payload['agent_advocates'] = [{"model": "haiku", ...}]`
**Wrong (causes false-positive silent_write_failure):** `payload['agent_advocates'] = json.dumps([{"model": "haiku", ...}])`

Affected JSON columns observed so far:
- `prod_preflight_reviews.agent_advocates` (json)
- `prod_preflight_reviews.agent_counters` (json)
- `prod_activity_log.details` (json) — this one works correctly when sent as dict

**Source:** preflight row 181 (2026-05-01, `fixq-dialogue-image-save-visibility-20260501`) — Phase 0 POST sent JSON-stringified arrays, read-back returned parsed lists, mismatch flagged as silent_write_failure but data was correctly stored.

## When to refresh this doc

- Run `python3 -c "from directus_lib import get_collection_fields; print(get_collection_fields('<collection>'))"` if you suspect schema drift.
- If you discover a NEW deviation during a session, add a row to the relevant
  table here AND register the schema-mapping note in `prod_activity_log.details.schema_mapping_deviations`.
- Re-snapshot the `task_category` and `doc_category` enums every ~3 months —
  they grow organically.

---

**Snapshot source:** `directus-production-3460.up.railway.app`, queried
2026-04-28 via Python urllib (`/fields/<collection>` for schema +
200-row sample for enum value extraction).

**Authored by:** claude_code_terminal_session 2026-04-28 as part of
v6-spec-followup-directus-parity preflight #176 follow-up.
