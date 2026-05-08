# MindfulNest Professional Setup Roadmap v1

**Authored:** 2026-05-07 by Desktop session per Kim directive `[CONFIRMED — this session]`
**Purpose:** Holistic map of macro + micro steps between current state and "production-ready / TestFlight launch / set up like a professional dev team." Every node has either a tracking artifact OR a flag noting the absence.
**Methodology:** Phase 0 classified Tier B (cross-cutting governance doc). Read seven layers, enumerated per-layer scope, cross-referenced live Directus snapshot (LDs ≥ 530 and unresolved blockers, taken 2026-05-07 ~10:00 PT), identified gaps. Confidence tags per CLAUDE.md Rule 24.
**Snapshot bounds:** Live Directus shows max LD id = 560, max blocker id = 66 `[CONFIRMED via get_items 2026-05-07]`. Anything beyond those ids is the next session's concern.

---

## §0 — Reading Order for Future Sessions

A future session opening this doc cold should read in this order:

1. **This roadmap (top to bottom).** Establishes the seven-layer map and current state.
2. `Production/docs/SILENT_DEFERRALS_AUDIT_20260507.md` — 14 audit items, 7 of which became blockers 54-60 and 6 became LDs 546-551 `[CONFIRMED via Directus]`.
3. `Production/docs/V59_GAP_FIX_HANDOFF_20260508.md` — gap-fix sequencing + tracking artifact mapping.
4. `Production/docs/V59_STORYBOARD_SIDEFIX_MORNING_REPORT_20260508.md` — Bug 1 fixed, Bug 2 + Bug 4 deferred (Tier C).
5. `Production/docs/V59_FEATURES_MASTER_INVENTORY_v2.md` — v59 features layer (90 WIRED / 21 WIRED-BUT-BROKEN / 71 UNCLEAR — Cursor v7 forward gate).
6. `Production/docs/V59_LD_505_BOUNDARY_TIGHTENING_SPEC_v1.md` — recently authored two-git-tree migration spec (DRAFT, awaiting Cursor cross-review) `[CONFIRMED present at 45,518 bytes 2026-05-07]`.
7. `Production/docs/STORYBOARD_REAL_FIX_ROADMAP.md` — older operational guide for storyboard tooling; some items folded into v59 work.
8. `CLAUDE.md` Rules 19, 22, 24, 27, 28, 29, 33, 35.

The **gap-fix morning report** referenced in the directive is NOT present at the literal `V59_GAP_FIX_MORNING_REPORT_*` filename `[CONFIRMED via find]`. However, gap-fix Phases A-H all have `_COMPLETE` rows in `prod_activity_log` (rows 1611, 1612, 1613, 1614, 1619, 1623, 1624, 1625) `[CONFIRMED via Directus query]`, and LDs 552-560 cover the 9 phase outputs. So gap-fix HAS executed; the report is either named differently or absent — flag for §4.

---

## §1 — Current State Snapshot (as of 2026-05-07 ~10:00 PT)

**Done (mechanical infrastructure live):**
- Tooling repo CI/CD gap-fix (Phases A-H) `[CONFIRMED — 8 phase COMPLETE rows + 9 LDs 552-560]`.
- v59 storyboard tool's Wave 0-4 architectural fix (mutation channel discipline LD-519, scope router LD-531, server fail-loud LD-520) `[CONFIRMED — LDs 519-538 active]`.
- Bug 1 server-side validation fix (PR #7 → commit 5733b21 on `claude/post-redeploy-bug-triage`); not yet on main `[CONFIRMED — side-fix morning report 2026-05-08]`.
- Silent-deferrals audit: 7 blockers (54-60) + 6 LDs (546-551) registered `[CONFIRMED via Directus 2026-05-07]`.

**In flight:**
- LD-505 boundary tightening spec authored (two-Opus-debate draft, awaiting Cursor cross-review before lock) `[CONFIRMED via file mtime 2026-05-07 19:13]`.
- Stream B + F production pipeline tech spec authored by other Desktop session — `Production/docs/V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md` (~78 KB, 16 sections, Phases A-D) `[CONFIRMED via ls 2026-05-07]`. Awaits execution per §5 Week 2 onward.
- LD-505 boundary tightening migration spec — `Production/docs/V59_LD_505_BOUNDARY_TIGHTENING_SPEC_v1.md` (~45 KB) authored by other Desktop session; eliminates Dropbox-resident `.git/`; supersedes LD-264 (`PRODUCTION_TOOLS_STAYS_IN_DROPBOX`). DRAFT awaiting Cursor cross-review before lock. `[CONFIRMED via ls + content read 2026-05-07]`

**Pending Kim's input as of 2026-05-07 ~10:00 PT (4 decisions):**
1. Code Scanning enable on tooling repo (CodeQL surfaced via LD-559) — needs Kim toggle.
2. Branch protection model on main — covered by LD-553 but Kim must activate GitHub Pro `[CONFIRMED — V59_GAP_FIX_HANDOFF §3 Q3]`.
3. Typecheck fix authorization — pending; specific scope unknown to this session `[INFERRED — directive references it]`.
4. META amendment authorization — pending; specific scope unknown to this session `[INFERRED — directive references it]`.

**Untouched / Untracked at this snapshot:**
- 6 of 7 v59 storyboard tabs unsmoked for Bug 2/4 architectural class `[CONFIRMED — blocker 56]`.
- 22-file Dropbox/tooling code divergence (substantive in-progress engineering, preserved on `claude/preserve-uncommitted-divergence-20260507`) `[CONFIRMED — blocker 54]`.
- Two-git-tree structural problem `[CONFIRMED — blocker 55]`.
- 30+ app-feature blockers (3, 4, 12, 13, 15-42, 44, etc.) untouched `[CONFIRMED via Directus]`.
- Watch list mechanical enforcement (LD-560) — registered but the workflows it requires (Phase G + H of gap-fix) shipped without §8.4 forbidden-vendor SDK scan + §9 anti-pattern detection `[INFERRED — directive flagged this; requires verification]`.

---

## §1.5 — User-Facing Categorization Cross-Reference

The seven technical layers in §2 don't map cleanly to Kim's mental model. Per Kim 2026-05-07: *"the actual app includes everything except the MP4 content coming out of the stitcher tool — dashboard, gameplay, rewards, fidget zones, server, database, back end tools."*

This section bridges between Kim's mental model and the technical layers so future sessions can reason in either frame.

### Kim's mental categories

| Kim's category | What it includes | Maps to technical layers |
|---|---|---|
| **MP4 production** | The pipeline that creates the .mp4 files children watch (storyboard authoring tool + assemble_module.py + R2 deploy) | Layer B (Storyboard v59 tool) + Layer C (Stream B+F production pipeline) |
| **The app** ("everything else not-MP4") | Dashboard, gameplay, rewards, fidget zones, server, database, backend tools, AI Parent Coach, Stripe integration, COPPA gating, account systems | Layer D (Main RN app CI/CD) + Layer F (App backend + features) |
| **Behind the scenes** (you don't touch directly) | CI/CD plumbing, governance discipline, post-launch concerns, audit trail mechanics | Layer A (gap-fix CI/CD) + Layer E (Governance hygiene) + Layer G (Future post-launch) |

### Layer F clarification

The original Layer F label ("App-level features") under-described it. **Layer F includes server, database, backend tools, AND user-facing features** — it's "everything except CI/CD discipline (Layer A) and pure-MP4 production (Layers B+C)."

### Why both framings matter

- **Kim's framing** is the right lens for "what does the user/child experience" + "what produces revenue" decisions.
- **Technical-layer framing** is the right lens for "what depends on what" + "what session executes when" decisions.
- Both are correct; neither is more authoritative. When discussing scope or sequencing, name which frame you're using.

`[CONFIRMED via Kim 2026-05-07 — explicit framing in chat]`

---

## §1.6 — Active SHORTCUT LDs with Closure Caps

**Why this section exists:** SHORTCUT_*_V1 LDs represent Rule 19 escape hatches — temporary deviations from the "no shortcuts" principle, justified for a bounded window. They MUST close. Without mechanical surfacing they silently age past their caps. This section enumerates active SHORTCUT LDs so dashboard-gate Phase 0.7 (LD 561) reads them as IN-FLIGHT items and surfaces approaching closure 30 days before cap.

**Cap policy (LOCKED 2026-05-07, Kim directive — replaces uniform 120-day proxy):**

- `RARE_NEVER` LDs auto-halt at **14 days from `date_locked`**. These have no scheduled triggering event ("if/when we happen to refactor", "if/when an upstream tool changes"). The 14-day cap forces an explicit reckoning before they age silently. Mechanically enforced by `weekly_preflight_audit.py::check_shortcut_ld_closure_dates()` via `SHORTCUT_LD_CLASSIFICATION` dict (see `Production/scripts/weekly_preflight_audit.py`).
- `EVENT_DRIVEN` LDs gate on the named event (PR merge, repo cutover, infra change). The LD itself sets the hard date backstop where applicable. The audit retains a 120-day backstop only as a safety surface so these don't silently age forever if the event never lands.
- New SHORTCUT LDs: classification is REQUIRED at creation time. `SHORTCUT_LD_CLASSIFICATION` raises an UNCLASSIFIED warning for any active SHORTCUT_*_V1 row missing from the dict.
- **Prospective-only cap (meta-fix B + C, 2026-05-07):** the 14-day RARE_NEVER cap applies ONLY to LDs locked on/after 2026-05-07 (`SHORTCUT_CAP_POLICY_LOCK_DATE` constant in audit script). RARE_NEVER LDs locked BEFORE that date are GRANDFATHERED — they emit a softer `GRANDFATHER_REVIEW` finding once for one-time triage (CLOSE / AMEND / re-classify). Once triaged in Directus the finding never re-fires. The four April-locked RARE_NEVER LDs (199, 200, 201, 249) were triaged 2026-05-07 in this same pass.

**Active SHORTCUT LDs (as of 2026-05-08; +15 prior-Apr/early-May LDs classified, LD 573 removed after closure):**

| LD id | decision_key | Class | Cap | Closure triggers | Surfacing |
|---|---|---|---|---|---|
| ~~199~~ | ~~`SHORTCUT_ARCH_WEIGHT_PCT_COLLAPSED_TO_ENUM`~~ | ~~RARE_NEVER~~ | **CLOSED 2026-05-07** (status=closed; v2 inventory closure trigger met — see notes on LD 199) | n/a | Removed from active SHORTCUT_LD_CLASSIFICATION dict |
| 200 | `SHORTCUT_LD_LINKAGE_SNAPSHOT_ONLY` | EVENT_DRIVEN (re-classified 2026-05-07 from RARE_NEVER) | 120-day backstop = 2026-08-15 | (a) Stage 4 kickoff OR (b) second contributor added to `prod_locked_decisions` writes → add `linked_inventory_rows` json field + cascade script that backfills from inventory_v2 row→LD citations. Quarterly audit (next 2026-08-07) confirms triggers; if both still unfired by 2026-11-07, re-evaluate relevance. | Phase 0.7 + weekly_preflight_audit |
| ~~201~~ | ~~`SHORTCUT_PARTIAL_STATUS_NO_PCT_FIELD`~~ | ~~RARE_NEVER~~ | **CLOSED 2026-05-07** (status=closed; v2 inventory closure trigger met — see notes on LD 201) | n/a | Removed from active SHORTCUT_LD_CLASSIFICATION dict |
| 227 | `SHORTCUT_CREDSTORE_MD_FALLBACK_20260418` | EVENT_DRIVEN | 120-day backstop = 2026-08-16 | Doppler-only cutover: "all launch scripts / cron jobs / CLI sites verified running under `doppler run --` for one full production cycle" → remove MD fallback in `credentials.py` + redact `Production/API_KEYS_MASTER.md` to `<REDACTED>` | Phase 0.7 + weekly_preflight_audit |
| 237 | `SHORTCUT_STAGING_PITR_WINDOW_20260418` | EVENT_DRIVEN | 120-day backstop = 2026-08-16 | (a) S3-POLISH-retention CF (purges staging docs >24h), (b) Firestore TTL GA on child-data collections, (c) PITR per-collection config when Google ships control | Phase 0.7 + weekly_preflight_audit |
| 247 | `SHORTCUT_EMAIL_VERIFICATION_DEFERRED_20260418` | EVENT_DRIVEN | 120-day backstop = 2026-08-16 | S3-AUTH-consent ship + verify no new attack surface; consider emailVerified as defense-in-depth | Phase 0.7 + weekly_preflight_audit |
| 248 | `SHORTCUT_FORGOT_PASSWORD_DEFERRED_20260418` | EVENT_DRIVEN | 120-day backstop = 2026-08-16 | S3-AUTH-recovery row ships before first external beta user (must precede S3-AUTH-consent + KWS go-live) | Phase 0.7 + weekly_preflight_audit |
| 249 | `SHORTCUT_IDENTITY_PLATFORM_EVALUATION_20260418` | EVENT_DRIVEN (re-classified 2026-05-07 from RARE_NEVER → PERIODIC+EVENT_DRIVEN; INTERIM mapping to EVENT_DRIVEN until PERIODIC class lands) | 120-day backstop = 2026-08-16 | Quarterly review (next 2026-07-18, then 2026-10-18, 2027-01-18); event triggers (a) MAU > 10K, (b) MFA becomes COPPA/therapist requirement, (c) SAML for B2B therapist orgs, (d) abuse attempts → register UPGRADE_IDENTITY_PLATFORM_* LD if triggered. APP-09 currently NOT-SCOPED → MAU=0; first substantive review fires on/after 2026-07-18 OR S3-AUTH-firebase ship + first MAU snapshot. | Phase 0.7 + weekly_preflight_audit |
| 269 | `SHORTCUT_COIN_REWARDS_HARDCODED_ARC1_20260418` | EVENT_DRIVEN | 120-day backstop = 2026-08-16 | Migrate `functions/src/config/moduleRewards.ts` constants to Firestore `/config/module_rewards/{moduleId}` when (a) Kim tunes 3+ times, (b) Arc 2 begins, (c) A/B testing on rewards becomes scope | Phase 0.7 + weekly_preflight_audit |
| 270 | `SHORTCUT_AUDIT_BEST_EFFORT_WRITES_20260418` | EVENT_DRIVEN | 120-day backstop = 2026-08-16 | S3-POLISH-audit-retry follow-up row (Firestore-backed outbox + scheduled CF drainer + DLQ) ships before first external beta user onboarding | Phase 0.7 + weekly_preflight_audit |
| 273 | `SHORTCUT_RN_COMPONENT_TEST_INFRA_DEFERRED_20260418` | EVENT_DRIVEN | 120-day backstop = 2026-08-16 | S3-TEST-rn-component-setup row adds jest-expo + @testing-library/react-native + jest.config + setup; backfills VideoLoopPlayer tests; must close before first external beta user | Phase 0.7 + weekly_preflight_audit |
| 277 | `SHORTCUT_APP_CHECK_SDK_DEFERRED_20260418` | EVENT_DRIVEN | 120-day backstop = 2026-08-16 | S3-POLISH-appcheck row: (a) decide JS-SDK-compatible App Check provider, (b) install SDK, (c) wire token attestation, (d) flip `enforceAppCheck:true` on onCall CFs per LD-229, (e) DeviceCheck/Play Integrity console provisioning | Phase 0.7 + weekly_preflight_audit |
| 278 | `SHORTCUT_AUTH_IN_MEMORY_PERSISTENCE_20260418` | EVENT_DRIVEN | 120-day backstop = 2026-08-16 | S3-AUTH-persistence follow-up row picks one of (A) `@react-native-firebase/auth` migration, (B) custom AsyncStorage persistence adapter, (C) pin firebase ≤10.6 — must close before external beta | Phase 0.7 + weekly_preflight_audit |
| 408 | `SHORTCUT_THERAPIST_DASHBOARD_V1_1` | EVENT_DRIVEN | 120-day backstop = 2026-08-23 | Therapist dashboard codebase begins immediately post-launch when D2-MVP is stable + has production traffic; LD must register before App Store submission per SHIP_READINESS_PARALLEL_TRACKS_v2.md | Phase 0.7 + weekly_preflight_audit |
| 416 | `SHORTCUT_PHASE_BOUNDARIES_CACHE_HIT_CF_V1` | EVENT_DRIVEN | 120-day backstop = 2026-08-23 | V1.1 cutover: store `phaseBoundaries` in `CacheEntry` (eliminates ~200ms warm-latency per play + O(plays) Firestore reads on cache HIT) | Phase 0.7 + weekly_preflight_audit |
| 545 | `SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1` | EVENT_DRIVEN | When V59_CICD_GAP_FIX PR merges to main (event); 120-day backstop = 2026-09-04 | Option B PR merge to main (Bug 2 + Bug 4 architectural fix) | Phase 0.7 + dashboard-gate |
| 565 | `SHORTCUT_TOOLING_REPO_PUBLIC_FOR_CODESCAN_V1` | EVENT_DRIVEN | 2026-09-07 hard cap (literal in LD); 120-day audit backstop coincides | (a) tooling private flip, (b) GitHub Enterprise tier purchased, (c) 2026-09-07 cap reached | Phase 0.7 + weekly_preflight_audit |
| 567 | `SHORTCUT_RN_REPO_PUBLIC_FOR_CODESCAN_V1` | EVENT_DRIVEN | 2026-09-07 hard cap (literal in LD); plus earlier triggers (TestFlight upload, COPPA content commit, real user data, Sentry/Crashlytics wired) | (a) RN private flip, (b) Enterprise tier purchased, (c) any earlier event trigger, (d) 2026-09-07 cap reached | Phase 0.7 + weekly_preflight_audit |
| 569 | `SHORTCUT_CODEQL_LOCK_FILE_0644_ACCEPT_V1` | RARE_NEVER | **date_locked + 14 days = 2026-05-21** | "If/when" lock-file open() calls refactored to 0o600, OR CodeQL `py/overly-permissive-file` rule updated to exempt empty advisory locks | Phase 0.7 + weekly_preflight_audit |
| 570 | `SHORTCUT_CODEQL_REDOS_BOUNDED_INPUT_ACCEPT_V1` | RARE_NEVER | **date_locked + 14 days = 2026-05-21** | "If/when" regex patterns rewritten with possessive quantifiers / length guards, OR CodeQL ReDoS rule gains bounded-length modeling | Phase 0.7 + weekly_preflight_audit |
| 571 | `SHORTCUT_CODEQL_FILES_EXISTENCE_TEST_ACCEPT_V1` | RARE_NEVER | **date_locked + 14 days = 2026-05-21** | "If/when" endpoints (production_server.py:2598, :9944) refactored to validate paths against project-root allowlist before existence test | Phase 0.7 + weekly_preflight_audit |
| 572 | `SHORTCUT_CODEQL_LOCALHOST_FFMPEG_LIST_FORM_ACCEPT_V1` | RARE_NEVER | **date_locked + 14 days = 2026-05-21** | "If/when" all ffmpeg subprocess input paths validated against project-root allowlist upstream, OR CodeQL `py/command-line-injection` rule distinguishes list-form from `shell=True` | Phase 0.7 + weekly_preflight_audit |
| 574 | `SHORTCUT_CODEQL_REALPATH_SINK_INSIDE_CHECK_V1` | RARE_NEVER | **date_locked + 14 days = 2026-05-21** | "If/when" CodeQL `py/path-injection` rule gains sanitizer-recognition for `Path.resolve()`/`os.path.realpath()` inside immediate-following containment-check guard idiom, OR code refactored to a helper that returns resolved path inline | Phase 0.7 + weekly_preflight_audit |
| 575 | `SHORTCUT_CODEQL_HTTP_RESPONSE_SPLITTING_TYPED_REBUILD_V1` | RARE_NEVER | **date_locked + 14 days = 2026-05-21** | "If/when" CodeQL `py/http-response-splitting` rule gains recognition for typed-component rebuild from `urllib.parse` (scheme + hostname + int port), OR CORS response uses entirely server-controlled origin with no user input in echo | Phase 0.7 + weekly_preflight_audit |

**Status:** 22 active SHORTCUT LDs in flight (after 2026-05-07 triage of LDs 199 + 201 to status=closed and re-classification of LDs 200 + 249 to EVENT_DRIVEN). 16 EVENT_DRIVEN (200, 227, 237, 247, 248, 249, 269, 270, 273, 277, 278, 408, 416, 545, 565, 567); 6 RARE_NEVER (569, 570, 571, 572, 574, 575). 16 + 6 = 22. Dashboard-gate Phase 0.7 reads this section + cross-references Directus to surface "closure approaching" 30 days before cap OR when triggers fire. Weekly preflight audit cron scans SHORTCUT_*_V1 LDs by classification (`SHORTCUT_LD_CLASSIFICATION` dict in `weekly_preflight_audit.py`) — RARE_NEVER caps at 14 days from date_locked (prospective-only, on/after 2026-05-07), EVENT_DRIVEN caps at 120-day backstop.

**RARE_NEVER cap-expired alerts (April-locked LDs):** TRIAGED 2026-05-07 in combined LD-PATCH + meta-fix pass — LDs 199 + 201 closed (status=closed; closure triggers met by v2 inventory supersession of v1); LDs 200 + 249 re-classified RARE_NEVER → EVENT_DRIVEN (LD 200 with Stage 4 / second-contributor triggers; LD 249 with quarterly review cadence interim-mapped to EVENT_DRIVEN until PERIODIC class lands). Audit script `SHORTCUT_LD_CLASSIFICATION` dict updated to match. Prospective-only cap (`SHORTCUT_CAP_POLICY_LOCK_DATE = 2026-05-07`) means no future April-locked LDs get retroactively dinged.

**RARE_NEVER cap-imminent alerts (May-locked LDs):** LDs 569-572, 574-575 (all date_locked 2026-05-07) hit their 14-day cap on **2026-05-21**. On 2026-05-08 audit runs they sit at days_until_cap=13, inside the 30-day warn window (CRITICAL fires when days_until_cap ≤ 7, i.e. 2026-05-14 onward). After 2026-05-14 the audit creates CRITICAL `prod_blockers` rows. Action required: close/refactor each by 2026-05-21 or amend classification.

**EVENT_DRIVEN backstops:** 14 LDs gate on named events; primary closure path is the event itself. The 120-day backstop is a safety surface so these don't silently age forever if the event never lands. Backstops cluster around 2026-08-16 (April-locked LDs), 2026-08-23 (late-April), 2026-09-04 (early-May), and 2026-09-07 (literal hard cap in LD-565/567).

**Recently closed (2026-05-08 cleanup pass — see activity log):**
- LD 234 `SHORTCUT_AUTONOMOUS_LIVE_BUILD_PHASE1_20260418` → status=superseded; one-shot Rule 19 grant fulfilled; build SHIPPED 2026-04-18 per `MORNING_REPORT_PHASE1_LIVE_20260418.md`. (Was never in `SHORTCUT_LD_CLASSIFICATION` dict.)
- LD 573 `SHORTCUT_CODEQL_VITE_BUILD_ARTIFACT_POSTMESSAGE_V1` → status=superseded; closure event fired in PR #8 commits f2b8eb7 (StoryboardTab.tsx + PhaseProducer.tsx origin-allowlist) + b4c199f (Vite bundle rebuild). Removed from this table + `SHORTCUT_LD_CLASSIFICATION` dict.

**Recently closed (2026-05-07 RARE_NEVER LDs triage + meta-fix pass — see activity log):**
- LD 199 `SHORTCUT_ARCH_WEIGHT_PCT_COLLAPSED_TO_ENUM` → status=closed (date_superseded=2026-05-07); closure trigger met by Stage 3 retrospective (v2 inventory 2026-04-18) which preserved qualitative HYBRID flag and did not surface margin-flagging pain. v1 source doc itself superseded by v2. Removed from active SHORTCUT_LD_CLASSIFICATION dict (kept as comment for traceability).
- LD 201 `SHORTCUT_PARTIAL_STATUS_NO_PCT_FIELD` → status=closed (date_superseded=2026-05-07); closure trigger met by v2 inventory (text-only next_action approach preserved; PARTIAL row count dropped 5→2; no pct field needed). Removed from active SHORTCUT_LD_CLASSIFICATION dict (kept as comment for traceability).

**Closure protocol:** when an LD closes, PATCH its row to `status='superseded'`, add closure rationale to `notes`, and remove from this table. Self-amend protocol per LD 561. **PR-merge-keyed closure events are now auto-closed by the weekly audit per §1.7 + LD 576** (manual PATCH still applies for non-PR-merge closures, e.g. doppler cutovers, V1.1 ships).

---

## §1.7 — PR-Merge Auto-Close (LD 576)

**Why this section exists:** SHORTCUT LDs whose closure event is a specific PR merging to main (e.g. LD 545 keyed on V59 CI/CD gap-fix PR #8 in `kimhyla/mindfulnest-tooling`) historically required someone to manually PATCH `status='superseded'` once the PR landed. Without a process-based reminder this cleanup got forgotten. LD 576 `MERGE_CLEANUP_AUTO_CLOSE_PROTOCOL_V1` formalizes the auto-close as a weekly audit sub-check.

**Mechanism:**
- Implementation: `Production/scripts/weekly_preflight_audit.py::check_pr_merge_closure_events` (added 2026-05-08).
- Schedule: weekly Monday 00:00 UTC (rides existing `weekly_preflight_audit.py` cron — same trigger as `check_shortcut_ld_closure_dates`).
- Scope: active EVENT_DRIVEN SHORTCUT_*_V1 LDs whose `notes` or `decision_text` contains a PR-merge phrase (regex: `\bPR\s+#?\d+\b`, `PR\s+merges?\s+to\s+main`, `gap[-\s]?fix\s+PR`, `merges?\s+to\s+main`).
- Repo resolution: explicit `<owner>/<repo>` in notes → repo-hint patterns (e.g. `V59_CICD_GAP_FIX` → tooling) → `decision_key` heuristic (TOOLING / RN / MAIN_APP) → else WARN.
- Detection: `gh pr list --state merged --limit 30 --json …` per resolved repo; match PR title/body/branch against COMPOUND `UPPER_SNAKE` identifiers extracted from the LD (regex requires at least one underscore — single uppercase words like `CRITICAL` or `STAGE` are excluded to prevent false positives).
- Action: PATCH `status='superseded'`, set `date_superseded`, append closure paragraph to `notes` with PR number + merge SHA + mergedAt + matched signal. POST `app_activity_log` row.
- Idempotency: re-reads LD status before PATCH; skips if already non-active.
- Failure-mode handling: multiple PR matches → take most recent + WARN; no match → no action; gh CLI / network errors → record in summary, never crash main audit.

**Scope limits (NOT handled by this sub-check):**
- Non-PR-merge closure events: doppler cutover (LD 227), post-launch traffic (LD 408), V1.1 cutover (LD 416), repo-public-flip OR enterprise-tier OR hard-cap-date triggers (LDs 565/567). Those need separate detectors.
- These remain MANUAL until each gets its own audit sub-check.

**Verification (2026-05-08):**
- Dry-run against live Directus + GitHub: 22 active SHORTCUT LDs scanned, 3 PR-merge-eligible (LDs 545, 565, 567), 0 matched (correct: PR #8 still OPEN as of authorship), 0 false positives after token-extraction tightening.
- Mock-test (PR #8 simulated as merged): LD 545 detected, matched via `body:V59_CICD_GAP_FIX_SPEC_v1`, would PATCH `status='superseded'` with merge_sha captured.

**Future-state (when to upgrade):** post tooling-repo public flip (LD 565 closure) AND if ≤7-day audit-cron latency proves too slow for governance hygiene, replace this sub-check with a GitHub Actions hook (`on: pull_request, types: [closed]`, `if merged == true`) — supersedes LD 576 with `MERGE_CLEANUP_AUTO_CLOSE_CI_HOOK_V1`. Until then the weekly cron is the canonical mechanism.

---

## §2 — The Seven Layers

### §2.A Layer A: Tooling repo CI/CD (gap-fix)

**Status:** DONE (mechanical) — pending merge of `feature/v59-gap-fix-2026-05-08` to main, pending Kim's GitHub Pro activation for branch protection enforcement.

**Tracking artifacts:**
- LDs 552 (`DEPLOY_VERIFICATION_GATE_V1` HARD), 553 (`BRANCH_PROTECTION_V1` HARD), 554 (`AI_REVIEW_AUTOMATION_V1` SOFT), 555 (`RN_WORKFLOW_ACTIVATION_V1` HARD), 556 (`PLAYWRIGHT_E2E_SPEC_WIRING_V1` SOFT), 557 (`BROWSER_SMOKE_MECHANICAL_GATE_V1` HARD), 558 (`PRE_COMMIT_DROPBOX_EDIT_GATE_V1` HARD), 559 (`CODEQL_DEPENDABOT_SECURITY_SCAN_V1` HARD), 560 (`WATCH_LIST_MECHANICAL_ENFORCEMENT_V1` HARD) `[ALL CONFIRMED via Directus]`.
- Activity log: rows 1611-1625 (Phases A-H) `[CONFIRMED via prod_activity_log query]`.
- Spec doc: `Production/docs/V59_CICD_GAP_FIX_SPEC_v1.md` (84,093 bytes) `[CONFIRMED via ls]`.

**Macro steps:**
1. (DONE) Phase A — Deploy verification gates (sha256 / mtime / curl probe) — LD-552.
2. (DONE) Phase B — Branch protection on main — LD-553. Pending Kim GitHub Pro.
3. (DONE) Phase C — AI review automation (Claude API custom) — LD-554.
4. (DONE) Phase D — RN-side workflow activation — LD-555.
5. (DONE) Phase E — 2 of 6 deferred Playwright specs wired — LD-556.
6. (DONE) Phase F — Browser smoke as HARD prereq for COMPLETE (mechanically enforced in `try_post_or_queue`) — LD-557.
7. (DONE) Phase G — Pre-commit hook blocking direct Dropbox edits — LD-558.
8. (DONE) Phase H — CodeQL + Dependabot — LD-559.

**Micro steps within current macro (post-Phase-H closeout):**
- Self-review the diff via `git diff main...HEAD --stat` + `git log --stat`.
- Squash-merge `feature/v59-gap-fix-2026-05-08` to main.
- Confirm CI green on main post-merge.
- Run `deploy_storyboard_v59.sh` to verify the new mechanical assertions work end-to-end.
- PATCH LD-545 (`SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1`) to `status='superseded'` post-merge `[CONFIRMED requirement — handoff §"Notes for Kim"]`.

**Dependencies (other layers that gate this):** none for completion of mechanical work; Layer D (main RN app) depends on Layer A patterns being validated end-to-end.

**Closure criteria:** PR merged to main, CI green on main, branch protection active (Kim GitHub Pro on), LD-545 superseded, 4 remaining of 6 deferred Playwright specs wired (currently only 2 of 6 — see LD-556 `[CONFIRMED]`).

---

### §2.B Layer B: Storyboard v59 tool stability

**Status:** IN-FLIGHT — Bug 1 fixed; Bug 2 + Bug 4 deferred (Tier C, Option B locked); 6 tabs unsmoked.

**Tracking artifacts:**
- LD-545 `SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1` (HARD, active until Option B lands) `[CONFIRMED]`.
- Blockers: 54 (22-file divergence), 55 (two-git-tree), 56 (6 tabs untested), 57 (27 pre-existing mods), 59 (manual-drop-on-options regression), 60 (Beat_22 corruption) `[ALL CONFIRMED via Directus]`.
- Plus 4 medium F-S2-* blockers (50, 51, 52, 53) for `event_load` raw fetch conversions `[CONFIRMED]`.
- LD-540 (`STORYBOARD_REORDER_UI_DEFERRED_V1` SOFT) — reorder/add/delete UI deferred `[CONFIRMED]`.

**Macro steps:**
1. (DONE) Bug 1 server-side fix — PR #7 → 5733b21 `[CONFIRMED]`.
2. (PLANNED) Cherry-pick 22 remaining divergence files from Dropbox into tooling — closes blockers 54 + 57 — handoff §sequencing #2 (~2-3 hr).
3. (PLANNED) Option B fix session — `bg_session_state` derives segment from `scope_event_id`; closes Bug 2 + Bug 4 — closes LD-545 (supersede) — (~2-4 hr).
4. (PLANNED) Manual-drop-on-options regression port — closes blocker 59 (~1-2 hr).
5. (PLANNED) 6-tab smoke pass (Cropper / Storyboard / Phase B / Phase A / Stitcher / Library) — closes blocker 56 (~2-3 hr).
6. (PLANNED) Resolve 4 F-S2-* event_load fetch conversions (Wave 3) — closes blockers 50-53.
7. (PLANNED) Convert 71 UNCLEAR features in v2 inventory via Cursor v7 symbol-level tracing — gating release decision `[CONFIRMED — V59_FEATURES_MASTER_INVENTORY_v2.md §forward gate]`.

**Micro steps within current macro (post-gap-fix #2 — divergence cherry-pick):**
- Open preserve branch `claude/preserve-uncommitted-divergence-20260507` at commit `95e4462`.
- Per-file classification: keep / reconcile / discard for each of 22 code files.
- Reconstruct BG-37 audit-trail + BG-22+C-9 registered_write refactor branches in tooling.
- Verify against blocker 54's scope-list.
- **Mark beat_22 corrupted in prod_assets BEFORE regen.** Per lessons doc 2026-05-08 (id=203) lesson 3.6 + `prod_blockers id=60`: beat_22's `speaker` + `accepted_image_key` were overwritten with empty strings during 2026-05-07 overnight smoke. Without a corruption marker in prod_assets, future regen sessions may not know which beat needs full re-author vs partial repair. Closure prerequisite: register `prod_assets` row OR add `corrupted=true` field on the existing row before any regen attempt. Cross-references blocker 78 (test fixture isolation) — same root cause class.

**Dependencies:** Layer A completion (gap-fix CI/CD must be live so PRs run through new gates). Layer C blocked behind Layer B's Option B.

**Closure criteria:** All 7 v59 tabs smoke six-layer-clean for Kim's actual workflow; 0 unresolved high-severity blockers in Layer B scope; v2 inventory 71 UNCLEAR resolved to WIRED or scope-cut.

---

### §2.C Layer C: Production pipeline (Stream B + F)

**Status:** UNSCOPED in this session — tech spec authored by other Desktop session — `Production/docs/V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md` (~78 KB, 16 sections, Phases A-D defined). Awaits execution per §5 Week 2 onward. `[CONFIRMED via ls 2026-05-07]`

**Tracking artifacts:**
- Blocker 62 (high) — Stream B production pipeline NOT STARTED — `assemble_module.py` + content_hash + phase_boundaries `[CONFIRMED]`.
- Blocker 63 (high) — Stream F content deployment NOT STARTED — Cloudflare R2 upload pipeline + manifest atomic publish `[CONFIRMED]`.
- LD context: master tech spec v6 §2 is the source-of-truth for the work `[INFERRED — referenced in blocker descriptions]`.

**Macro steps (placeholder — to be fleshed out by the side spec):**
1. (PLANNED) Receive Stream B+F tech spec from side conversation.
2. (PLANNED) Build `assemble_module.py` orchestrator.
3. (PLANNED) Implement SHA-256 content_hash + Directus registration.
4. (PLANNED) Build phase_boundaries manifest emission.
5. (PLANNED) Cloudflare R2 upload pipeline (per LD `CDN_CLOUDFLARE_R2_V1` 2026-04-27).
6. (PLANNED) Manifest atomic publish + rollback.

**Micro steps:** to be authored by side spec; this roadmap intentionally does NOT duplicate that work per directive.

**Dependencies:** Layer B's Option B should land before Stream B begins (BG/Storyboard write paths must be canonical). Layer A's deploy verification gates (LD-552) gate Stream F's CDN deploys.

**Closure criteria:** Stream B+F ship a module end-to-end; assembled MP4 + manifest live on R2; module CDN-served + downloadable in main RN app.

**Stream B+F Production Pipeline Phases (per V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md):**

Phase A → Phase B → Phase C → Phase D (sequential, in this order):
- Phase A — `Production/tools/manifest_helpers.py` creation (~1-2h, Tier A)
- Phase B — `prod_assets` schema fields + `register_asset` signature changes (~2-3h, Tier B)
- Phase C — `assemble_module.py` 10-step pipeline + Steps 11-13 finalization
  + `CONCAT_AUDIO_PARITY_V1` LD registration + `STREAM_B_*` LD registrations (~6-10h, Tier B)
- Phase D — `r2_upload.py` + `r2_atomic_publish.py` + LD-404 AMEND
  + `STREAM_F_*` LD registrations (~8-12h, Tier C)

Each phase writes its own governance updates and Directus LD registrations
INLINE per §6 of the spec. Not a separate "governance phase."

Sequence dependencies:
- All four phases run AFTER gap-fix lands + 22-file divergence reconciliation
  + Option B fix + manual-drop port + tab smoke (per V59_GAP_FIX_HANDOFF_20260508.md
  decision sequencing locked).
- Phases run sequentially: A unblocks B, B unblocks C, C unblocks D.
- Spec authored 2026-05-07; locked + amended 2026-05-08 with R1-R5 Cursor concerns
  resolved + 4 open Kim decisions LOCKED.

**Status:** SPEC LOCKED. Phase A unblocked but waiting on gap-fix per sequencing.

---

### §2.D Layer D: Main RN app CI/CD (greenfield)

**Status:** PLANNED — LD-544 `MAIN_APP_CICD_GREENFIELD_DESIGN_V1` (HARD, active) locks the design constraint; actual implementation is a future scope `[CONFIRMED via Directus]`.

**Tracking artifacts:**
- LD-544 — locks "design greenfield from scratch; never inherit/copy/patch from tooling repo CI/CD" `[CONFIRMED]`.
- LD-555 — `RN_WORKFLOW_ACTIVATION_V1` (HARD) — RN-side workflow drafts copied from tooling, but per LD-544 these are TEMPLATES NOT ROOTSTOCK — needs verification `[INFERRED — verify before main app session]`.
- Memory: `project_main_app_cicd_greenfield_lock.md`.
- Blocker 61 (high) — `dependency-audit.yml` PostCSS XSS (5 vulns) failing every nightly since 2026-05-01; fix needs Expo SDK breaking change `[CONFIRMED]`.

**Macro steps:**
1. (PLANNED) Resolve blocker 61 (PostCSS XSS) — Expo SDK upgrade.
2. (PLANNED) Greenfield CI/CD design session for `MindfulNest/.github/workflows/` (separate from tooling).
3. (PLANNED) EAS Build + TestFlight setup (per blocker 41, medium — pre-launch recommended services).
4. (PLANNED) Maestro Tier-1 follow-up (blocker 9 — medium; PR #16 manual open + comments).
5. (PLANNED) Sentry + Firebase App Check + Crashlytics + Billing Alerts adoption (blocker 40, high).
6. (PLANNED) iPad 9 floor-device performance validation (blocker 65, high; LD-287).

**Micro steps within current macro (greenfield design):**
- Tech-spec dual-Opus debate session (4+4 advocate/counter agents per Rule 19).
- Define each workflow file from scratch: `zero-error-qa.yml`, `rn-expo-gate.yml`, `dependency-audit.yml` (already exists).
- Apply tooling-repo workflows as "what to AVOID" reference only.

**Dependencies:** Layer A patterns must be validated end-to-end first (so we know which patterns NOT to reuse). Layer F (app features) blocks: cannot ship app without features.

**Closure criteria:** TestFlight build green; CI green on `main` of `kimhyla/mindfulnest-ios`; Maestro tier-1 + tier-2 + tier-3 specs all green; Sentry + Firebase App Check enforcement live.

---

### §2.E Layer E: Documentation + governance hygiene

**Status:** IN-FLIGHT — silent-deferrals pattern caught + corrected; cascade work pending.

**Tracking artifacts:**
- LD-551 `VERBAL_DEFERRAL_TRACKING_REQUIRED_V1` (HARD) — operationalized via dashboard-gate skill + weekly_preflight_audit `[CONFIRMED]`.
- LDs 546, 547, 548, 549, 550 (all SOFT, deferred-* keys) — Items 7, 8, 9, 11, 12 from audit `[CONFIRMED]`.
- Blocker 58 (high) — 66 lessons in LESSONS_LEARNED_May06_2026 incorporation status unverified `[CONFIRMED]`.
- Blocker 64 (medium) — Governance doc cascade pending from 2026-04-18 — 4 SKILL.md files + Bible reference obsolete architecture `[CONFIRMED]`.

**Macro steps:**
1. (DONE) Audit silent deferrals → 7 blockers + 6 LDs registered.
2. (PLANNED) Inline-fix schema doc inconsistency (LD-546).
3. (PLANNED) Cross-link `feedback_browser_smoke_required.md` to `feedback_storyboard_url_serves_at_root.md` (LD-547).
4. (PLANNED) Inventory branch reconciliation decision (LD-548).
5. (PLANNED) 66-lesson incorporation audit (blocker 58) — read each lesson, check whether each has a corresponding LD/skill/memory entry.
6. (PLANNED) 2026-04-18 governance cascade (blocker 64) — LDs 280/281/282 (single-MP4 atomic, no runtime TTS, arc-at-a-time) need cascade across 4 SKILL.md files + Bible.
7. (PLANNED) Doppler secret manager migration (blocker 66, medium) — replaces `Production/API_KEYS_MASTER.md`.

**Micro steps within current macro (66-lesson audit):**
- Read `prod_reference_docs id=202` (LESSONS_LEARNED_May06_2026 file).
- For each of 66 lessons, grep `prod_locked_decisions` + `.claude/skills/*/SKILL.md` + memory dir for incorporation evidence.
- File a `prod_blockers` row for any lesson with no incorporation evidence.

**Dependencies:** Layer F (app features) blocked behind some governance items (e.g., Doppler before launch).

**Closure criteria:** All SOFT deferred-LDs (546-550) closed via supersession or natural decay; blocker 64 + 58 + 66 resolved; governance docs cite no obsolete architecture.

**Governance Doc Cascade (blocker id=64, MEDIUM severity):**

SEPARATE session from Stream B+F Phase execution. The cascade is the pending
update for LDs 280/281/282 (single-MP4 atomic, no runtime TTS, arc-at-a-time)
that was queued 2026-04-18 but never executed.

Files needing update (verified stale 2026-05-08):
- 4 SKILL.md files: `phase-b-writer`, `video-expander`, `scene-to-production`,
  `video-producer` (all reference obsolete multi-file / runtime TTS patterns)
- `Canon/CLAUDE_Everdale_World_Design_Bible_v13_13.md` (latest Bible — 0 references
  to new architecture as of 2026-05-08 grep)
- NDU + ArcBuilder + 11 `Production/governance/` files

CLAUDE.md was already updated (verified 6 references to new architecture).

Risk if deferred: future Phase B + arc skeleton authoring sessions follow
obsolete patterns; risk of producing content that violates LD-281 (no runtime
TTS) and LD-280 (single-MP4 atomic).

Estimated effort: ~2-3 hours.
Sequence: ANY time post-gap-fix. Independent of Stream B+F. Run alongside or
between the Stream B+F phases as bandwidth allows.

**Status:** registered as `prod_blockers id=64`, unresolved.

---

### §2.F Layer F: App backend + features (everything not-MP4 not-CI/CD)

**Status:** UNSCOPED execution — 30+ blockers tracked, none in flight at this snapshot.

**Scope clarification (per §1.5 cross-reference):** Includes server, database, backend tools, dashboard, AI Parent Coach, Stripe + COPPA gating, account systems — NOT just user-facing features. Per Kim's mental model, this and Layer D together = "the app" (everything except MP4 production).

**Tracking artifacts (grouped by category):**

| Category | Blocker IDs | Severity profile |
|---|---|---|
| Stripe / payments / COPPA | 12, 13, 15, 16, 17, 18 | high (12, 13, 17), medium (15, 18), low (16) |
| Rewards / progression | 19, 20, 21, 22, 23, 33, 34 | high (19, 33), medium (20, 21, 22, 23, 34) |
| Therapist entitlement | 24 | high |
| Bubble Hop / fidget | 25, 26, 35, 36 | medium (25, 26, 35, 36), low (26) |
| Content production (Phase B drafts) | 3, 4, 28, 39, 42 | high (3, 4, 42), medium (28, 39) |
| RN architecture cascade | 30 | medium |
| Pre-launch services | 40, 41, 65 | high (40, 65), medium (41) |
| Retention / Today card / streaks | 37, 38 | medium |
| Asset sourcing | 31, 32 | medium (31), low (32) |
| Tech debt | 5, 6, 7, 8, 45 | low |

`[ALL CONFIRMED via Directus blocker query 2026-05-07]`

**Macro steps (high-level — order driven by blocker severity + dependency):**
1. (PLANNED) COPPA / KWS gate before any Stripe flow (blocker 17 — high).
2. (PLANNED) Stripe webhook business logic + purchase schema (blockers 12, 13, 18).
3. (PLANNED) Therapist entitlement bypass (blocker 24 — high).
4. (PLANNED) Reward UI + backpack reveal + magic tap probabilistic drop (blockers 33, 34, 35).
5. (PLANNED) Bubble Hop kid validation (blocker 25 — medium; gate for Path A primitive).
6. (PLANNED) Phase B script drafts for M5 (Bork) + M6 (Bramble) + M3 design (blockers 3, 4, 42).
7. (PLANNED) Pre-launch services adoption (blocker 40 — Sentry / App Check / Crashlytics / Billing Alerts).
8. (PLANNED) Retention layer (blockers 28, 37, 38, 39).
9. (PLANNED) Tech debt sweep (blockers 5, 6, 7, 8, 45 — all low).

**Micro steps:** out of scope for this roadmap; each macro item warrants its own session-level breakdown when scoped.

**Dependencies:** Layer D must be live (CI/CD green) before app-feature work merges. Layer C must ship at least one module end-to-end so payment flow has product to gate. Layer B's Option B not strictly blocking but desirable.

**Closure criteria:** All HIGH blockers in Layer F resolved; Stripe live in production; COPPA gate enforcing; pre-launch services adopted; 6+ modules content-complete; Bubble Hop + 1 other fidget validated with kids.

---

### §2.G Layer G: Future post-launch concerns (CURRENTLY UNTRACKED)

**Status:** UNSCOPED — these items have NO Directus tracking artifact yet and are surfaced for the first time by this audit.

**Tracking artifacts:** NONE EXIST. See §4 for proposed.

**Macro steps (proposed — none have artifacts):**
1. **Staging environment** — separate Firestore + Stripe sandbox + R2 bucket from production. Currently both share `production` config `[INFERRED — no staging-* keys in Directus]`.
2. **Test coverage thresholds** — enforce minimum coverage on RN app + tooling repo via CI gate. Currently: no threshold `[INFERRED — gap-fix Phase E only added 2 of 6 specs]`.
3. **Performance budgets** — bundle size + cold-start time + frame-rate targets per LD-287 floor device.
4. **Observability** — Sentry adoption (blocker 40 covers crash side); add structured logging + metrics beyond what Sentry provides.
5. **Multi-dev workflow** — current setup is solo-dev (LD-558 PRE_COMMIT_DROPBOX_EDIT_GATE_V1 says "local-only per spec §3 solo-dev scope"). When 2nd dev joins, gate semantics break.
6. **Disaster recovery** — backup + restore drill for Directus, Firestore, R2, prod_assets, beat_generator_state.json. No drill ever performed `[INFERRED — no DR-related LDs]`.
7. **Compliance audit pre-launch** — COPPA verification trail; HIPAA-adjacent posture (clinical claims); App Store review prep (kids category).
8. **Customer support tooling** — refunds, account deletion (COPPA right-to-erasure), parent-account-recovery flow.

**Micro steps:** none — these are tier-C architectural decisions awaiting trigger.

**Dependencies:** Most are gated behind launch (Layer F + D + C cohesion). Staging environment ideally lands before pre-launch services (Layer F item 7).

**Closure criteria:** Each item gets a tracking artifact. Then tracked through to landing as part of normal session work.

---

## §3 — Cross-Layer Dependency Graph

Text-based graph (→ means "gates"):

```
Layer A (gap-fix CI/CD) ──→ Layer D (main RN CI/CD)
                       ──→ Layer F (app features merge through CI)
                       ──→ Layer C (Stream F deploy gates)

Layer B (storyboard) ──→ Layer C (Stream B uses canonical BG/Storyboard write paths)
                    ──→ Layer F (content production needs storyboard tool stable)

Layer C (Stream B+F) ──→ Layer F (payments need product)
                    ──→ Layer D (TestFlight needs at least 1 shippable module)

Layer E (governance) ──→ all layers (silent deferrals + 66 lessons + cascade
                          inform every other layer's quality)

Layer G (future)     ──→ blocked behind launch decision
```

**Key invariants:**
- Layer D cannot ship before Layer A patterns are validated (LD-544 requirement).
- Layer C cannot ship Stream F before Layer A's deploy verification gate (LD-552) is on main.
- Layer F (Stripe) cannot ship before Layer F (COPPA gate, blocker 17).
- Layer F (Stripe webhook business logic) cannot ship before Layer F (purchase schema, blocker 13) — internal Layer F dependency.

**No contradictions detected** between layer dependencies as enumerated.

---

## §4 — Untracked Items Surfaced by This Audit

For each: proposed collection, proposed severity, proposed key/title.

1. **Watch list mechanical enforcement may be stale on shipped gap-fix branch.**
   - Proposed: `prod_blockers`, severity=`high`, title=`Verify LD-560 watch-list mechanical enforcement actually shipped in Phase G + H workflows OR amend on follow-up branch`.
   - Rationale: directive flagged Phase G + H shipped without §8.4 + §9 checks; LD-560 was registered after the workflows. Either an amendment or a separate watch-list-only PR is needed.

2. **Gap-fix morning report missing at expected filename.**
   - Proposed: `prod_blockers`, severity=`low`, title=`Locate or rename gap-fix morning report — directive expects V59_GAP_FIX_MORNING_REPORT_*.md but file not found at that pattern`.
   - Rationale: `find` returned 0 hits; activity log shows Phases A-H complete; report may be at a different filename or absent.

3. **Staging environment for Firestore / Stripe / R2.**
   - Proposed: `prod_locked_decisions`, severity=`SOFT`, key=`STAGING_ENVIRONMENT_DESIGN_V1`.
   - Rationale: no separation between dev + prod data plane.

4. **Test coverage thresholds.**
   - Proposed: `prod_locked_decisions`, severity=`SOFT`, key=`COVERAGE_THRESHOLD_GATE_V1`.
   - Rationale: gap-fix Phase E wired only 2 of 6 deferred specs; no threshold gate exists.

5. **Performance budget targets per floor device.**
   - Proposed: `prod_locked_decisions`, severity=`SOFT`, key=`PERFORMANCE_BUDGET_FLOOR_DEVICE_V1`.
   - Rationale: LD-287 names iPad 9 as floor; no numeric budget locked.

6. **Multi-dev workflow plan for when solo-dev assumption breaks.**
   - Proposed: `prod_blockers`, severity=`low`, title=`Plan for multi-dev workflow — current LD-558 pre-commit gate is local-only per solo-dev scope`.
   - Rationale: LD-558 explicitly scopes to solo-dev; no plan for the transition.

7. **Disaster-recovery drill for Directus + Firestore + R2 + state files.**
   - Proposed: `prod_blockers`, severity=`medium`, title=`Run DR drill — backup + restore for Directus, Firestore, R2, prod_assets, beat_generator_state.json`.
   - Rationale: zero DR drills performed.

8. **App Store review prep (kids category).**
   - Proposed: `prod_blockers`, severity=`high`, title=`App Store review prep — kids category requirements + screenshots + description + privacy nutrition label`.
   - Rationale: required for TestFlight → App Store transition.

9. **Customer support tooling — refunds, COPPA right-to-erasure, account recovery.**
   - Proposed: `prod_blockers`, severity=`medium`, title=`Customer support tooling — refunds + account deletion (COPPA) + recovery flows`.
   - Rationale: required pre-launch; no row exists.

10. **Master roadmap living-doc enforcement mechanism (anti-slip for THIS doc).**
    - Proposed: `prod_locked_decisions`, severity=`HARD`, key=`MASTER_ROADMAP_LIVING_DOC_V1`.
    - Rationale: see §6.

11. **2 of 6 Cursor v7 symbol-level traces actually performed (4 still pending).**
    - Proposed: `prod_blockers`, severity=`medium`, title=`v59 features inventory v2 — 71 UNCLEAR items still need Cursor v7 symbol-level tracing`.
    - Rationale: master inventory v2 §forward-gate cites Cursor v7 as gating release; not yet executed.

12. ~~**Stream B + F spec hand-off mechanism between this thread and the side conversation.** — RESOLVED 2026-05-07: Stream B+F spec received at `Production/docs/V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md`. Closure mechanism never registered as a tracking artifact (transient hand-off concern, not a long-term item).~~

13. **pathappPatch single-write continuous verification.**
    - Tracked at `prod_blockers id=77`, severity=medium, is_resolved=false.
    - Origin: V59 Storyboard Foundation Sprint lessons doc 2026-05-08 (id=203) lesson 2.10.
    - Gap: LD-456 SCOPE_VALIDATION_V1 enforces scope token in handlers, but no CI gate prevents future PRs from adding non-pathappPatch mutation sites. Without continuous verification, the 13-coupled-handler bug class (cross-event Accept-All) can silently re-enter.
    - Closure: add CI workflow grep gate. Estimated 1-2 hours.

14. **Test fixture isolation for production_state.json.**
    - Tracked at `prod_blockers id=78`, severity=medium, is_resolved=false.
    - Origin: V59 Storyboard Foundation Sprint lessons doc 2026-05-08 (id=203) lessons 3.8 + 3.6.
    - Gap: smoke tests write to canonical Production/Event_*/production_state.json with no rollback. Caused 2 production-state incidents in 5 days (clear-test pollution 2026-05-03 + beat_22 corruption 2026-05-07).
    - Closure: snapshot-before-smoke + auto-restore OR extend Production/Event_e2e_fixture/ pattern (DS-3) to all smoke tests. Estimated 3-4 hours.

15. **Side-conversation write verification pattern.**
    - Tracked at `prod_blockers id=79`, severity=low, is_resolved=false.
    - Origin: V59 Storyboard Foundation Sprint lessons doc 2026-05-08 (id=203) lesson 6.6.
    - Gap: when offloading work to side conv, "I wrote X" claims can be false (V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md announced-not-written incident 2026-05-07; Cursor caught via FILE NOT FOUND).
    - Closure: add memory file `feedback_side_conv_write_verification.md` documenting mtime-check pattern, OR amend mn-context skill with cross-conv write verification step. Estimated 30-60 min.

---

## §5 — Sequencing Plan (next 30 days, micro-step level)

Calibrated against handoff §sequencing + audit's effort estimates + gap-fix done state.

### Week 1 (2026-05-07 → 2026-05-13)
**Theme:** close the gap-fix loop + LD-505 boundary tightening + start the divergence reconciliation.

| Day | Macro item | Micro outcome | Layer |
|---|---|---|---|
| Mon (today) | Roadmap authored + Kim review | This doc written; Kim's 4 pending decisions resolved | E |
| Tue | Gap-fix PR self-review + squash-merge to main | Layer A closes mechanical phase | A |
| Wed (after gap-fix merge) | **LD-505 boundary tightening migration** (locked earlier per Kim 2026-05-07 directive): eliminate Dropbox-resident `.git/`; tooling repo becomes sole git tree | Two-git-tree problem mechanically gone (closes blocker 55); all subsequent sessions operate on unified tree | A, B |
| Wed | LD-545 supersede + post-merge `deploy_storyboard_v59.sh` smoke | LD-545 → superseded | A, B |
| Thu | Begin 22-file divergence cherry-pick (handoff seq #3, now operating on unified tree) | 5-10 of 22 files reconciled | B |
| Fri | Finish 22-file cherry-pick + close blocker 54 + 57 | All 22 files in tooling | B |

*Note 2026-05-07 (original): LD-505 boundary tightening spec authored at `Production/docs/V59_LD_505_BOUNDARY_TIGHTENING_SPEC_v1.md` (45 KB) — DRAFT, awaiting Cursor cross-review before lock.* `[CONFIRMED via ls 2026-05-07]`

**Sequencing change 2026-05-07 (Kim directive):** LD-505 was promoted from
"eventual / after 6-tab smoke" to "immediately after gap-fix lands" in the
handoff doc sequencing. The 22-file cherry-pick (formerly handoff seq #2) is
now handoff seq #3 and MUST NOT begin until LD-505 migration completes.
Rationale: the path-mismatch failure class (Dropbox-tree vs tooling-repo
divergence) has caused agent halts and rework twice in the same session. LD-505
eliminates the dual-tree state; subsequent sessions then operate on a single
canonical tree. If Cursor cross-review of the LD-505 spec surfaces a
release-blocker, surface to Kim before proceeding — do NOT skip LD-505 and
proceed to the 22-file cherry-pick, as that would reintroduce the same
dual-tree hazard into the reconciliation session.

### Week 2 (2026-05-14 → 2026-05-20)
**Theme:** Option B fix + 6-tab smoke + Stream B+F spec receive.

| Day | Macro item | Micro outcome | Layer |
|---|---|---|---|
| Mon | Stream B+F spec already received (V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md, ~78 KB, on disk); execute Phase A (manifest_helpers.py) | Phase A skeleton + tests | C |
| Tue | Option B fix session (handoff seq #4) | Bug 2 + Bug 4 closed; LD-545 superseded | B |
| Wed | Manual-drop-on-options regression port (handoff seq #5) | Blocker 59 closed | B |
| Thu-Fri | 6-tab smoke pass (handoff seq #6) | Blocker 56 closed; new bugs filed as discovered | B |

### Week 3 (2026-05-21 → 2026-05-27)
**Theme:** governance hygiene + Cursor v7 + Stream B begin.

| Day | Macro item | Micro outcome | Layer |
|---|---|---|---|
| Mon | Watch list verification + amendment if stale (untracked #1) | LD-560 either confirmed-shipped OR amended | A, E |
| Tue-Wed | Cursor v7 symbol-level pass on 71 UNCLEAR (untracked #11) | v59 inventory v3 — 0 UNCLEAR | B |
| Thu | 66-lesson incorporation audit (blocker 58) | Each lesson tagged WITH-INCORPORATION or NEEDS-INCORPORATION | E |
| Fri | Stream B (assemble_module.py) implementation begins | Skeleton + test harness | C |

### Week 4 (2026-05-28 → 2026-06-03)
**Theme:** Stream B finish + governance cascade + main RN CI/CD design.

| Day | Macro item | Micro outcome | Layer |
|---|---|---|---|
| Mon-Tue | Stream B SHA-256 content_hash + Directus registration + phase_boundaries | Blocker 62 closed | C |
| Wed | 2026-04-18 governance cascade (blocker 64) | 4 SKILL.md + Bible updated for LDs 280/281/282 | E |
| Thu | Doppler migration begin (blocker 66) | Doppler workspace created; first secret migrated | E |
| Fri | Main RN CI/CD greenfield tech-spec session (LD-544) | 4+4 advocate-counter spec produced | D |

**Honest calibration:** 4 weeks gets us from "gap-fix landed" to "Stream B underway + 2-of-7 layers visible-progress." Stream F + Layer F + Layer D are 6+ additional weeks. TestFlight remains a Q3 target, not a Q2 target. Layer G items remain unscoped throughout.

---

## §6 — Anti-Slip Mechanism (mechanical, not admonition)

**The risk:** this doc itself becomes a verbal deferral if no mechanical check fires. Per Kim's 2026-05-07 directive (the entire reason for this roadmap), every "we'll get to it later" must have mechanical enforcement.

**Proposed mechanism (registers as untracked item §4 #10 → LD `MASTER_ROADMAP_LIVING_DOC_V1`):**

1. **Add to MEMORY.md** at top of index: `[Master Setup Roadmap (LIVING DOC)](project_master_roadmap_living_doc.md) — every session-start dashboard-gate checks roadmap §1 current-state snapshot age. If age > 7 days, halt + surface to Kim with diff prompt.`

2. **Extend `dashboard-gate` skill** with a Phase 0 sub-step:

   ```
   STEP 0.7 — Roadmap freshness check
   Read Production/docs/MINDFULNEST_PROFESSIONAL_SETUP_ROADMAP_v1.md §1.
   Check the "as of" timestamp.
   If older than 7 days: halt; surface to Kim:
     "Roadmap §1 current-state is N days old. Update before proceeding,
      or override with rationale."
   ```

3. **Extend `weekly_preflight_audit`** (the existing weekly audit referenced in LD-551) with a roadmap-drift check:
   - For every `prod_blockers` row created or resolved since last audit, verify it appears in §2 layer enumeration.
   - For every LD created or amended since last audit, verify it's referenced in §2.
   - File `prod_blockers` row if drift found.

4. **Self-amend protocol:** when an executing session lands work that closes a blocker or LD listed in §2, the same session amends §1 + §2 inline + commits the doc edit alongside the work commit. Mechanical rule: "if your PR closes a Layer A-G item, it must also touch this doc."

**Why mechanical:** §6 is a script (the `dashboard-gate` Phase 0.7 step) + a contract (LD `MASTER_ROADMAP_LIVING_DOC_V1`), not just a "remember to update." Future sessions hit the gate; gate halts; halt forces update.

**Skill-level discipline cross-reference:** zero-error-qa skill DS-13 through DS-19 (Six-Layer Verification, Eight Risk Classes, Authoring Discipline, Don't Rely on Memory, Tail-End Verifier, Deviation Logging, Standing Escape Hatches) + Phase 0 retroactive remediation pattern apply on every session via skill auto-load. Future readers of this roadmap who do NOT also load zero-error-qa will miss these protections. Recommend reading roadmap alongside `.claude/skills/zero-error-qa/SKILL.md` for full context. Origin: V59 Storyboard Foundation Sprint lessons doc 2026-05-08 (id=203) lessons 1.1 + 1.5 + 1.6 + 1.10 (GAP-MINOR class).

---

## §7 — Confidence Annotations Sweep

Per Rule 24, every numeric / artifact-id / "tracked at X" claim is tagged.

**Highest-confidence claims (cross-checked via Directus get_item 2026-05-07):**
- LDs 530-560 inclusive — 31 active rows `[CONFIRMED via get_items filter status=active id>=530]`.
- Blockers 1-66 — 54 unresolved `[CONFIRMED via get_items filter is_resolved=false]`.
- LDs 544, 545, 551, 552, 557, 560 — round-tripped individually `[CONFIRMED via get_item]`.
- Blockers 12, 17, 24, 40, 54, 55, 56, 59, 60, 62, 63, 64, 65, 66 — round-tripped individually `[CONFIRMED via get_item]`.
- Phase A-H _COMPLETE rows in `prod_activity_log` (rows 1611, 1612, 1613, 1614, 1619, 1623, 1624, 1625) `[CONFIRMED via get_items _iends_with _COMPLETE]`.

**Now CONFIRMED (upgraded from INFERRED 2026-05-08):**
- Stream B+F spec authored, locked, and amended at `Production/docs/V59_PRODUCTION_PIPELINE_STREAM_BF_SPEC_v1.md` (1067 lines, 17 sections, R1-R5 Cursor concerns resolved + 4 amendments applied) `[CONFIRMED via ls + grep verification 2026-05-08]`.
- 4 pending Kim decisions all LOCKED 2026-05-08: Decision 1 (LD-404 timing) = Phase D; Decision 2 (Firebase→R2 cutover) = V1.1; Decision 3 (boto3 vs urllib) = urllib; Decision 5 (drop duplicate LD) = DROP MANIFEST_PHASEBOUNDARIES_NAMED_OBJECT_LOCK_V1 `[CONFIRMED via grep "LOCKED PER KIM 2026-05-08" returns 4 markers in spec]`.

**Inferred (not directly verified in this session):**
- LD-264 → LD-505 supersede chain context `[INFERRED — V59_LD_505_BOUNDARY_TIGHTENING_SPEC_v1.md preamble]`.
- 30-day sequencing effort estimates `[INFERRED — handoff §sequencing + audit estimates, not measured]`.

**Guessed (low confidence — flagged for follow-up):**
- Layer G items (staging, coverage thresholds, perf budgets, observability, multi-dev, DR, compliance, support tooling) — assembled from general knowledge of "production-ready" practice; no MindfulNest-specific evidence reviewed `[GUESSED — needs Kim review]`.
- Whether LD-560 watch list checks actually shipped in Phase G + H `[INFERRED — directive sent to gap-fix terminal session 2026-05-08; LD-560 status=active confirmed via Directus query but Phase G + H code-side validation pending gap-fix completion]`.

---

## §8 — Authorship + Review Trail

| Date | Action | Actor | Evidence |
|---|---|---|---|
| 2026-05-07 ~10:00 PT | Initial authorship per Kim directive | Desktop session (this) | `[CONFIRMED — file written]` |
| 2026-05-08 ~20:30 PT | Surgical insertions: §2.C Stream B+F line item + §2.E Governance cascade line item; §7 confidence upgrade Stream B+F spec INFERRED→CONFIRMED + 4 Kim decisions INFERRED→CONFIRMED + LD-560 GUESSED→INFERRED; §8 trail entry added | Desktop session (this) | `[CONFIRMED via Edit tool diff + multipass grep verification]` |
| 2026-05-07 (Kim directive) | §5 Week 1 table + note updated: LD-505 position locked as handoff seq #2 (immediately after gap-fix); 22-file cherry-pick renumbered to seq #3; sequencing-change rationale block added. Companion edit to V59_GAP_FIX_HANDOFF_20260508.md §"Decision sequencing locked." | Terminal CLI session per Kim 2026-05-07 directive | `[CONFIRMED — edits applied + multipass verified]` |
| TBD | Kim cross-review against gap-fix morning report (when found) | Kim | pending |
| TBD | Cursor cross-review for blind spots | Cursor | pending |
| TBD | Amend §1 current-state snapshot post LD-545 supersede | next session | pending |

**Amendment policy:** §1 + §2 update inline whenever a session lands work that closes a tracked artifact. §6 mechanical gate enforces. §3 dependency graph updates only when a NEW layer is added or a layer's dependency relationship inverts.

---

`[CONFIRMED — roadmap authored 2026-05-07 by Desktop session per Kim directive. All Directus artifact references round-trip-verified via get_item or get_items filter queries against live snapshot. Confidence annotations applied per Rule 24. No fabricated tracking artifacts. Untracked items in §4 are flagged with proposed collection + severity + key + rationale rather than left as prose deferrals (per LD-551 VERBAL_DEFERRAL_TRACKING_REQUIRED_V1).]`
