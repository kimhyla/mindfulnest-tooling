# Schema Vocab Migration — Dry-Run Report (20260509)

- Spec authority: v7 sha256 `dc7db3e3953b65d1bd71d76b02f5fe73e9a5789412f83180b3172f35ed5e58c3`
- Handoff: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md`
- Snapshot: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_20260509.jsonl`
- Snapshot hash: `46f42e45f4e3de8b28e66ad457105673065709b440c269aa4ae993220d4a138f`
- Total touched rows (union): 365

## §1 — Drift evaluation (mechanical halt #2 threshold)

| Rule | Expected | Actual | Delta | %drift | <=25%? |
|---|---|---|---|---|---|
| rule_1_severity_high_critical_to_hard | 320 | 306 | -14 | 4.38% | OK |
| rule_2_severity_lowercase_to_upper | 37 | 38 | +1 | 2.7% | OK |
| rule_3b_task_category_remap | 56 | 56 | +0 | 0.0% | OK |
| rule_4_scope_domain_remap | 29 | 35 | +6 | 20.69% | OK |

All rules within 25% drift threshold. No halt fires.

## §2 — Sample of 5 ids per rule (deterministic seed=42)

### rule_1
| id | decision_key | severity | scope_domain | task_category |
|---|---|---|---|---|
| 60 | arc1_benson_inscription_full | CRITICAL | cross-cutting | narrative |
| 15 | html_forbidden_direct_edit | CRITICAL | cross-cutting | storyboard |
| 165 | THERAPIST_SUMMARY_CLOUD_FUNCTION_PATTERN | HIGH | cross-cutting | architectural |
| 144 | ANIMATION_DURATION_MATCHES_AUDIO | HIGH | cross-cutting | production_server_infrastructure |
| 126 | HARDENED_SESSION_PROTOCOL_TERMINAL_CLI | CRITICAL | cross-cutting | governance |

### rule_2
| id | decision_key | severity | scope_domain | task_category |
|---|---|---|---|---|
| 236 | FIREBASE_PROJECT_ID_MINDFULNESTKIDS | high | app | infrastructure |
| 228 | SHORTCUT_CF_INIT_NO_REAL_DEPLOY_VALIDATION | medium | app | infrastructure |
| 265 | TIER3_SERVER_WHITELIST_EXTENSIONS_PAUSE_SPEAKER_DISPLAY_ORDER | high | infra | infrastructure |
| 263 | CLAUDE_MD_PRUNING_DEFERRED_POST_STAGE_3 | low | cross-cutting | architectural |
| 262 | CLASSIFICATION_INSIDE_PHASE_0_STEP_1 | medium | cross-cutting | architectural |

### rule_3b
| id | decision_key | severity | scope_domain | task_category |
|---|---|---|---|---|
| 299 | BUNDLE_SIZE_CI_ENFORCEMENT_V1 | HIGH | ci_pipeline | architectural |
| 153 | LIPSYNC_UI_MUST_SUPPORT_RERUN | HIGH | cross-cutting | production_server_infrastructure |
| 145 | AUDIT_BEAT_DURATIONS_TOOL | MEDIUM | cross-cutting | production_server_infrastructure |
| 402 | DISPLAY_ARTIFACTS_REDERIVED_FROM_DISK_V1 | HIGH | cross-cutting | architectural |
| 204 | OPTION_C_DIRECTUS_AS_UI_PROTOTYPE_SCOPE_v2 | CRITICAL | cross-cutting | architectural |

### rule_4
| id | decision_key | severity | scope_domain | task_category |
|---|---|---|---|---|
| 246 | LOG_HYGIENE_SUPPRESS_CLIENT_CANCEL_TRACEBACKS | LOW | production-server | infrastructure |
| 228 | SHORTCUT_CF_INIT_NO_REAL_DEPLOY_VALIDATION | medium | app | infrastructure |
| 278 | SHORTCUT_AUTH_IN_MEMORY_PERSISTENCE_20260418 | medium | app | infrastructure |
| 273 | SHORTCUT_RN_COMPONENT_TEST_INFRA_DEFERRED_20260418 | medium | app | infrastructure |
| 270 | SHORTCUT_AUDIT_BEST_EFFORT_WRITES_20260418 | medium | app | infrastructure |

## §3 — Rule-3b INVESTIGATE-class triage queue

These task_category values are present live but require per-row Kim triage per spec §3.3 verdict — NOT auto-PATCHed:
- `feature`: 1 row(s)
- `production_infrastructure`: 35 row(s)
- `production_pipeline`: 26 row(s)
- `tools`: 6 row(s)

## §4 — Computed target-value mappings

### Rule 4 (scope_domain remap)

| Old | New | Live count touched | Origin |
|---|---|---|---|
| app | app-dev | 13 | spec §3.4 |
| audio_pipeline | production | 1 | spec §3.4 |
| audio_production | production | 1 | spec-extension (Kim 2026-05-09) |
| beat_generator | production | 1 | spec §3.4 |
| ci_pipeline | infra | 1 | spec §3.4 |
| claude_session_behavior | cross-cutting | 1 | spec §3.4 |
| governance | cross-cutting | 2 | spec §3.4 |
| image_pipeline | production | 1 | spec §3.4 |
| infrastructure | infra | 6 | spec §3.4 |
| payments | app-dev | 1 | spec §3.4 |
| production-server | infra | 3 | spec-extension (Kim 2026-05-09) |
| production_pipeline | production | 1 | spec-extension (Kim 2026-05-09) |
| stillgen | production | 2 | spec §3.4 |
| video_pipeline | production | 1 | spec §3.4 |

### Rule 2 (severity lowercase -> UPPER)

| Old | New | Live count touched |
|---|---|---|
| MED | MEDIUM | 2 |
| critical | CRITICAL | 2 |
| high | HIGH | 15 |
| low | LOW | 3 |
| medium | MEDIUM | 16 |

### Rule 3b (task_category synonym remap)

| Old | New | Live count touched |
|---|---|---|
| architectural | app_architecture | 33 |
| audio_production | audio | 4 |
| production_server | infrastructure | 2 |
| production_server_infrastructure | infrastructure | 14 |
| video_production | video | 3 |

### Rule 1 (severity HIGH/CRITICAL -> HARD)

(Phase 5 deferred this session per spec §3.1; no PATCHes.)

| Old | New | Live count touched |
|---|---|---|
| CRITICAL | HARD | 132 |
| HIGH | HARD | 174 |

