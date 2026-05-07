# MindfulNest App Architecture Foundation Spec v1

**Date:** 2026-05-04
**Classification:** FOUNDATION DISCIPLINE — defines the 5 load-bearing pieces that MUST be in place before any MindfulNest consumer-facing app code (iOS / Therapist Dashboard / Parent Dashboard) ships its first feature.
**Predecessors / motivation:**
- Storyboard v59 retroactive coverage program — `Production/docs/STORYBOARD_V59_COMPREHENSIVE_RETROACTIVE_COVERAGE_PLAN_v1.md` (2026-05-04)
- Storyboard v59 architectural fix — `Production/docs/STORYBOARD_V59_ARCHITECTURAL_FIX_SPEC_v1.md` (2026-05-04, Wave 1; introduced `MUTATION_CHANNEL_INVARIANT_V1` + `SERVER_SILENT_FAILURE_FAIL_LOUD_V1` + `PRODUCTION_TOOLING_REQUIREMENTS_TXT_V1`)
- Storyboard v59 retroactive coverage results — `Production/docs/RETROACTIVE_COVERAGE_RESULTS_V1.md` (4 prod_blockers #46-49, 41 e2e tests across 6 surfaces)
- Storyboard v59 proper-fix — `Production/docs/STORYBOARD_V59_S5_5_CE_PROPER_FIX_SPEC_v1.md` (introduced LDs 506-510 incl. `MANDATORY_E2E_GATE_V1`, `CI_PLAYWRIGHT_ON_COMMIT_V1`)

**Authoritative sources synthesized:**
- LD `MINDFULNEST_GIT_REPO` (CRITICAL 2026-04-16) — `kimhyla/mindfulnest-ios` at `~/Projects/MindfulNest` (PRIVATE)
- LD `DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA` (HIGH 2026-04-17) — Therapist + Parent dashboards as separate Lovable/Next.js repos w/ shared `firestore_schema.json` lockfile
- LD `BUILD_AI_COACH_NOT_RENT` (HIGH) — AI Parent Coach BUILDS on Claude API direct
- LD `APP_REPO_SESSION_DIRECTUS_CRED_LOADING_V1` (HIGH 2026-04-20)
- LD `BUNDLE_SIZE_CI_ENFORCEMENT_V1` (HIGH) — CI gate for dist size
- LD `STAGE3_SECURITY_RULES_FIRST` — security rules + `@firebase/rules-unit-testing` are Week 0
- LD-208 — Doppler-first secrets
- LD-124 — Phase 0 mandatory for sessions
- `MINDFULNEST_MASTER_TECHNICAL_SPEC_v6.md` §0.1 (gate register G0–G4), §14.10 (correctness infrastructure tiers), §14.10.1 (Cursor CI Tier A/B/C), §14.13 (architecture contracts pointer index), §19.1 (performance telemetry), §19.2 (release artifact audit). **Canonical filesystem location:** `<DROPBOX_ROOT>/MINDFULNEST_MASTER_TECHNICAL_SPEC_v6.md` — at the Dropbox project root, NOT under `Production/docs/`. All references to this filename in this spec are to that root-level file (per Cursor R2 2026-05-04).
- `Production/docs/STORYBOARD_V59_ARCHITECTURAL_FIX_SPEC_v1.md` (template + structural prototypes)

---

## §1 Why this spec exists

Over the weekend of 2026-05-03/04, the v59 storyboard tool — a production-internal Preact client at `Production/tools/storyboard-v2/` — burned roughly 24-32 hours of focused engineering time on **retroactive structural fixes** that would have cost zero hours had the structural pieces been in place before features shipped. Concretely:

1. The proper-fix session shipped 5 R-bugs + a CI Playwright workflow + the `MANDATORY_E2E_GATE_V1` standard (5 NEW LDs 506-510). Until that point, `npm run build` green + curl 200 + a verifier subagent was being treated as "shipped"; user-visible behavior was broken.
2. The retroactive coverage sprint v1 wrote 41 Playwright tests across 6 surfaces and **immediately surfaced 4 more prod_blockers** (#46-49). The bugs had been there for sessions; the tests just exposed what nobody had been measuring.
3. The architectural-fix session is now mid-flight to address 3 of those 4 + add a mandatory `MUTATION_CHANNEL_INVARIANT_V1` grep gate, because the convention-only mutation channel (pathappPatch as the single mutation entry point) had been silently bypassed in 5 sites — by humans, by AI agents, by handoff prompts. Convention without enforcement got eroded over months.
4. A 6-wave retroactive coverage program was then drafted to systematically chase down the rest of the bug-debt across the whole storyboard tree. That program is the **honest cost** of having shipped features before discipline.

The MindfulNest **app** (iOS at `~/Projects/MindfulNest`, Therapist Dashboard, Parent Dashboard, AI Coach Functions) is a multi-repo consumer-facing product with real children, real parents, real therapists, and real subscription dollars. The blast radius of "ship without discipline" is incomparably larger than a production-internal tool.

This spec defines the 5 load-bearing pieces that, if missing at feature-1, lead to the storyboard's pain at app scale — except instead of 24-32 hours of engineer time, the cost is data corruption affecting paying customers, COPPA violations, App Store rejections, or — most dangerously — silent regressions that don't surface until therapists complain weeks later.

### §1.1 Dual-perspective synthesis (advocate vs counter)

This section names the explicit tradeoff and where the two sides diverge, so the resolution is principled rather than reflexive.

#### Advocate position — minimal foundation, ship features fast

> "Heavy upfront discipline kills velocity for a solo founder. The storyboard's pain came from a TOOL Kim could afford to retrofit — that retrofit took weekends, not months. CI on every commit + a unit-test-when-convenient ethos is enough to start; the rest accumulates as the app matures and as real failure modes surface. Front-loading 5 separate discipline programs before feature 1 means feature 1 ships 4-6 weeks later than it could. For a pre-revenue product chasing app-store launch + therapist beta, that's the wrong tradeoff. Real users + real bug reports teach you which discipline matters more reliably than upfront speculation. Lean foundation = ship → measure → harden the surfaces that actually broke."

Strongest advocate evidence:
- The storyboard retrofit took ~24-32 hours, not months. Retrofit IS feasible.
- Many startups ship without observability + recover; over-engineered foundations have killed more pre-PMF products than they've saved.
- A solo founder has finite working memory; 5 discipline systems concurrently is cognitive load that may compound, not subtract from, error rates.
- Strict TypeScript + Firestore-rules-tested + a "tests for new features" rule already covers 80% of the storyboard pain at a fraction of the upfront cost.

#### Counter position — comprehensive foundation, all 5 pieces before feature 1

> "The storyboard's retrofit was 'only' weekends because it had ONE user (Kim), ONE failure mode (browser smoke surfaces UI bugs), and ZERO compliance surface. The app has children-under-13 (COPPA), payments (Stripe), HIPAA-adjacent therapist data, multi-repo coordination (iOS + Therapist + Parent + Functions + shared schema), App Store review, and TestFlight beta cycles. A single silent regression in COPPA enforcement could end the company. A single Firestore-rules drift could expose child PII. Retrofit at app scale is NOT weekends — it's months of incident response while paying customers churn. The cost of pre-loading discipline is real but bounded (4-6 weeks of foundation work that would happen anyway, just sequenced differently); the cost of skipping it is unbounded. Storyboard's lesson is unambiguous: convention without enforcement WILL erode; discipline AFTER features is always more expensive than discipline BEFORE."

Strongest counter evidence:
- The Master Tech Spec §8.1 already requires Sentry + App Check + Crashlytics + Billing Alerts BEFORE any real child data enters Firebase staging — the company has already locked in "observability before launch." This spec just makes "before launch" mean "before feature 1," which is structurally cheaper than "before launch."
- The 4 prod_blockers found in retroactive coverage v1 were 4 bugs that an e2e test written WITH the feature would have caught. Discipline-after-features = 4× more retroactive work, not less.
- `MANDATORY_E2E_GATE_V1` already exists for the storyboard. Extending it to the app is consistency, not new policy.
- A Firestore schema lockfile + generated TS types is a 1-day setup that eliminates an entire class of multi-repo drift bugs that, post-launch, are 1-week incident-response events.

#### Divergence points

| Question | Advocate | Counter | Resolution |
|---|---|---|---|
| **Should observability (Sentry, structured logs, alerts) be live before feature 1?** | No — wait until features exist to instrument; over-instrumenting greenfield is waste. | Yes — the cost of wiring is fixed (~1 day); the cost of not having it during feature 1 is invisible regressions. | **COUNTER WINS.** Sentry + structured logging + alert rules MUST be live before the first non-greenfield commit lands on `main`. Master spec §8.1 already mandates this for staging; this spec makes "live in staging" a Day-0 requirement, not a Pre-launch requirement. |
| **Schema lockfile generation — manual or auto on Day 1?** | Manual; auto-gen tooling adds CI complexity. | Auto on Day 1; manual sync drifts within 2 weeks. | **COUNTER WINS.** Auto-gen + drift-fails-CI from Day 1. Drift is the highest-confidence bug class to prevent (LD `DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA` already commits to lockfile pattern). |
| **TypeScript strict — at feature 1 or after first refactor?** | After first refactor; strict mode pre-feature-1 slows scaffold velocity. | At feature 1; turning it on later is a multi-day retrofit per repo. | **COUNTER WINS.** Strict on Day 1 in all repos. Cost is hours; retrofit cost is days per repo × 3 repos. |
| **Custom ESLint rules / grep CI gates — pre-built or as-needed?** | As-needed; building rules speculatively is YAGNI. | At least one prototype gate (mutation-channel grep is the storyboard analog) before feature 1, with a documented "how to add a new structural rule" runbook. | **HYBRID.** Ship Day 1 with: (a) standard ESLint config (recommended + react + react-native), (b) the storyboard's mutation-channel grep gate adapted IF/WHEN the app introduces an analogous channel, (c) a documented runbook for adding new structural rules. Don't speculatively build app-specific rules; DO have the wiring + runbook ready. |
| **Test-with-feature in spec template — required clause or recommended?** | Recommended; over-strict gates produce spec-template hacking. | Required clause; storyboard proved that "we'll add tests later" never happens. | **COUNTER WINS.** Required clause in every feature spec template. The spec template itself is the load-bearing artifact. |
| **CI on every commit — at first repo or all repos?** | First repo; replicate when you have evidence others need it. | All repos from Day 1; replication is mechanical and one-time. | **COUNTER WINS.** All repos (iOS, Therapist Dashboard, Parent Dashboard, Functions) Day 1. The cost is the same one-time YAML write per repo; the cost of skipping any one is a discoverability gap that'll bite during an incident. |

#### Synthesis — what this spec actually mandates

The counter wins on 5 of 6 explicit divergences; the hybrid resolution on the 6th is itself a counter-leaning compromise (ship the wiring + the runbook, not speculative app-specific rules). The advocate position survives in two forms:

1. **The 5 pieces are tightly scoped.** Each is "do X mechanism, fail CI on violation, here's the runbook" — not "build a comprehensive program for X." We're locking the **minimum mechanical floor** for each piece, not the maximum.
2. **Out-of-scope (§10) explicitly defends scope.** Performance budgets beyond the existing Master Spec §19.1 mandate, accessibility programs, security-program-beyond-Firestore-rules, visual regression testing, and any Wave-2+ enhancements are deferred to per-stream programs. This spec is foundation, not exhaustive coverage.

This synthesis converts both positions' strongest claims into the spec's mandates below.

---

## §2 Task / scope

Land 5 load-bearing discipline pieces in all MindfulNest app-side repos before feature 1 of any repo ships:

1. **CI from commit 1, no exceptions** — every repo (iOS, Therapist Dashboard, Parent Dashboard, Functions) has GitHub Actions running on every PR + push to main: lint + typecheck + tests + build. CI red blocks merge.
2. **Test-with-feature discipline in the spec template itself** — the canonical app-feature spec template at `Production/docs/APP_FEATURE_SPEC_TEMPLATE_v1.md` lists tests upfront in a mandatory section. No feature ships without its tests in the same PR. No "future" / "phase 2" comments on test coverage. Storyboard's `MANDATORY_E2E_GATE_V1` (LD-507) extended to all app repos.
3. **Structural enforcement of architectural rules (not convention)** — TypeScript strict on Day 1 across all TS repos; ESLint config (recommended + react + react-native) on Day 1; one prototype grep CI gate (`MUTATION_CHANNEL_INVARIANT_V1` adapted, IF/WHEN the app introduces an analog) + documented runbook for adding new structural rules. Firestore security rules tested with `@firebase/rules-unit-testing` (already locked by `STAGE3_SECURITY_RULES_FIRST`).
4. **Schema contracts that verify code matches schema at build time** — `firestore_schema.json` lockfile is the source of truth (per LD `DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA`); generated TS types via auto-gen step that runs on every CI build. Drift between code and schema fails CI. API contracts (CF endpoints) are versioned + Zod-validated. Env vars typed via `zod-env` or equivalent + checked at app boot.
5. **Observability + silent failure detection** — Sentry (or Crashlytics for iOS native + Sentry for JS) live in all environments from Day 1; structured logging via a single logger module (no `console.log` in production code paths — ESLint enforced); alerts on error-rate spikes wired to a Slack channel or email; the storyboard's `SERVER_SILENT_FAILURE_FAIL_LOUD_V1` invariant adapted: any caught exception in CF code that isn't deliberately swallowed-with-rationale (commented + `prod_blockers`-tracked) MUST log + raise.

---

## §3 Governing decisions

### Existing LDs respected

| LD | Reason |
|---|---|
| `MINDFULNEST_GIT_REPO` | Authoritative iOS repo location (`~/Projects/MindfulNest`); CI must wire there |
| `DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA` | Therapist + Parent dashboards as separate repos w/ shared schema; this spec implements the lockfile mechanic |
| `BUILD_AI_COACH_NOT_RENT` | AI Coach is a code path inside Functions repo; CI + observability mandates apply |
| `APP_REPO_SESSION_DIRECTUS_CRED_LOADING_V1` | Sessions targeting these repos use explicit Python cred wiring; this spec doesn't change that |
| `BUNDLE_SIZE_CI_ENFORCEMENT_V1` | Existing CI gate; this spec subsumes it under §2 piece 1 (CI from commit 1) |
| `STAGE3_SECURITY_RULES_FIRST` | Firestore rules + tests are Week 0; this spec re-states as part of piece 3 |
| LD-208 (Doppler-first secrets) | Env vars typed in piece 4; secrets fetched from Doppler in CI |
| LD-124 (Phase 0 mandatory) | Sessions implementing this spec follow Phase 0 |
| LD-507 `MANDATORY_E2E_GATE_V1` | Extended from storyboard to all app repos in piece 2 |
| LD-508 `CI_PLAYWRIGHT_ON_COMMIT_V1` | Pattern adapted: CI-on-every-commit applies to all app repos in piece 1 |
| LD `MUTATION_CHANNEL_INVARIANT_V1` (storyboard arch fix) | Pattern adapted for piece 3; instantiated only IF/WHEN the app introduces an analogous mutation channel |
| LD `SERVER_SILENT_FAILURE_FAIL_LOUD_V1` (storyboard arch fix) | Adapted to CF code in piece 5 |
| LD `PRODUCTION_TOOLING_REQUIREMENTS_TXT_V1` (storyboard arch fix) | Pattern: every repo has a checked-in lockfile (npm `package-lock.json` / iOS `Podfile.lock`) — already standard, restated for completeness |
| Master spec §8.1 (Sentry/App Check/Crashlytics/Billing Alerts before staging child data) | This spec tightens "before staging" to "before feature 1" for the observability piece |
| Master spec §14.10 (correctness infrastructure gate-aligned tiers) | This spec is Tier 0 — required before G0 (architecture write-lock) |
| Master spec §14.13 (architecture contracts pointer index) | This spec is registered there as a pointer |
| Master spec §19.1 (performance telemetry) | Telemetry hooks go in alongside observability (piece 5) so the wiring is one job, not two |
| Master spec §19.2 (release artifact audit) | The audit script is a CI gate; folded under piece 1 (CI from commit 1) |

### NEW LD this spec writes (1)

| Key | Severity | Purpose |
|---|---|---|
| `MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_DISCIPLINE_V1` | HARD | All MindfulNest app-side repos (iOS, Therapist Dashboard, Parent Dashboard, Functions) MUST have the 5 load-bearing pieces in §2 of this spec live and CI-enforced before feature 1 of that repo lands on main. The 5 pieces are non-optional. New app repos created later inherit the requirement. Codifies what the v59 storyboard's retroactive cost (24-32 engineer hours over 2026-05-03/04) demonstrated by negative example. Mechanical enforcement: CI configurations + spec template + lockfile auto-gen step + observability boot-check (the wiring IS the LD). |

---

## §4 Approach (TDD-ordered — discipline first, then features)

### §4.1 Why discipline-first ordering

The storyboard's retroactive program §16 honestly acknowledges that "even with all 6 waves, zero bugs forever is not a state any methodology can guarantee." That's true. What discipline-first ordering DOES guarantee is:

- Every bug surfaced has a test path to write that prevents regression
- Every regression is observable (logged + alerted) within minutes of landing in staging, not weeks of customer reports
- Every schema change visibly breaks the build in the repo that's drifted, not silently in production
- Every architectural pattern that matters is enforced mechanically; convention erosion is impossible without a CI red

The cost of doing each piece before feature 1 is **fixed**. The cost of doing it after is **multiplicative** (the cost per retroactive surface scales with how many features have shipped against the missing discipline).

### §4.2 Ordering rationale

The 5 pieces have dependencies:

1. **CI from commit 1** is foundational. Pieces 2-5 are CI-enforced; CI must exist first.
2. **Spec template (test-with-feature)** is next because it shapes every feature spec written from now on.
3. **Structural enforcement** (TS strict, ESLint, rules tests, prototype grep gate) goes in once CI exists to enforce it.
4. **Schema contracts** (lockfile + auto-gen + Zod) is a single integrated workstream — the lockfile is canon; everything else flows from it.
5. **Observability** (Sentry + structured logger + alerts + fail-loud) is last because it runs in production but can be wired during the build phase; it doesn't gate any other piece.

This is the ordering of the implementation phases below.

---

## §5 Implementation phases

### Phase 0 — Pre-flight

**0.1.** Read this spec + Master Tech Spec §0.1, §8.1, §14.10, §14.13, §19.1, §19.2 + storyboard architectural-fix spec (template) + storyboard retroactive coverage results doc.

**0.2.** `prod_preflight_reviews` row task_id="app-architecture-foundation-discipline-20260504" referencing this spec + the LDs in §3.

**0.3.** Verify working trees:
- `~/Projects/MindfulNest/` (iOS — kimhyla/mindfulnest-ios) exists; `git status` clean
- Therapist Dashboard repo location confirmed (Lovable/Next.js per LD `DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA`)
- Parent Dashboard repo location confirmed
- Functions repo location confirmed (may live inside iOS repo `/functions` or separate — check)
- For each: branch `claude/foundation-discipline-install` created

**0.4.** Confirm the existing scaffolding doesn't already partially install any of the 5 pieces. If a piece is already partially live (e.g., one repo has CI but two don't), document the delta in a `prod_blockers` tracking row. Don't redo work; do close gaps.

**0.5.** Doppler project + service tokens for each repo; CI secret store wiring drafted (not yet committed).

### Phase 1 — Piece 1: CI from commit 1

**1.1.** For each repo, create `.github/workflows/ci.yml` (template — adapt per stack):

```yaml
name: CI
on:
  pull_request:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4    # or setup-python / Xcode runner for iOS
        with: { node-version: '20', cache: 'npm' }
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm run test
      - run: npm run build
      - run: npm run schema:check       # piece 4 — added in Phase 4
      - run: npm run audit:bundle-size  # existing LD BUNDLE_SIZE_CI_ENFORCEMENT_V1
```

iOS-specific: `xcodebuild test` + Swift lint (SwiftLint) + `xcrun simctl` smoke + the existing `eas build` dry-run check.
Functions-specific: Firestore-rules-tests via `@firebase/rules-unit-testing` (per LD `STAGE3_SECURITY_RULES_FIRST`).

**1.2.** Required-status-checks configured in GitHub branch protection: `ci/test` blocking on `main`. No bypass-on-admin.

**1.3.** Verify with a deliberately-failing test in a scratch PR — CI red, merge blocked. Restore. Verify green. Document RED-then-GREEN proof in commit message.

**1.4.** Existing `BUNDLE_SIZE_CI_ENFORCEMENT_V1` integrated as a step inside this workflow (single job, not duplicate workflow).

### Phase 2 — Piece 2: Test-with-feature spec template

**2.1.** Create `Production/docs/APP_FEATURE_SPEC_TEMPLATE_v1.md` with mandatory sections (no skip-clause):

```
## Tests

This section is REQUIRED. A feature without a populated test plan does not ship.
Reviewers (Cursor, Kim, Claude Code) MUST refuse to merge a PR whose linked spec leaves
this section empty or marked "future" / "phase 2" / "later."

### Unit tests
- [ ] <test 1 description; file path; assertion>
- [ ] <test 2 ...>

### Integration tests (CF + Firestore rules)
- [ ] <integration scenario; setup; expected outcome>

### E2E tests (per MANDATORY_E2E_GATE_V1, LD-507)
- [ ] <user-flow scenario; surfaces touched; assertions>

### Negative tests
- [ ] <failure mode that MUST be observable>

### Coverage targets
- New code MUST have ≥80% line coverage on the changed files; CI enforces (piece 1).
```

**2.2.** Adapt the template to each repo's testing stack (Jest + RTL for web, XCTest for iOS, Vitest + supertest for Functions).

**2.3.** Update `Production/CLAUDE.md` and the canonical session-handoff template to reference `APP_FEATURE_SPEC_TEMPLATE_v1.md` as the required template for any app feature spec. Storyboard tooling-side specs continue to use the storyboard template.

**2.4.** Coverage gates:
- `npm run test -- --coverage` produces a JSON coverage report
- CI step `audit:coverage` parses report; if any changed file has <80% line coverage, exits 1
- Existing-but-unchanged files are exempt (don't retroactively block on legacy uncovered code; do block on new uncovered code)

### Phase 3 — Piece 3: Structural enforcement

**3.1. TypeScript strict.** In every TS repo (Therapist Dashboard, Parent Dashboard, Functions, iOS RN if used), `tsconfig.json` has:
```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "exactOptionalPropertyTypes": true
  }
}
```
CI step `typecheck` (already in Phase 1) enforces.

**3.2. ESLint config.** Each repo has `eslint.config.mjs` extending recommended + react (where applicable) + react-native (iOS RN) + `eslint-plugin-functional` or equivalent for invariants. Rules:
- `no-console` (production code paths only — test files exempt)
- `no-any` / `ban-types` for known dangerous types
- Path-based rules: `no-restricted-imports` to prevent direct imports from internal modules that should route through a public surface

**3.3. Firestore rules tests.** Per LD `STAGE3_SECURITY_RULES_FIRST`, every Firestore rule change has a corresponding `firestore.rules.test.ts` covering allow/deny for each role × collection. CI runs the suite against the rules emulator.

**3.4. Prototype grep CI gate (mutation-channel pattern, deferred).** The storyboard's `MUTATION_CHANNEL_INVARIANT_V1` is a grep CI step that **is structurally enforced for declared patterns/signatures** (per Cursor R4 2026-05-04 phrasing) — specifically: it fails CI if raw `fetch()` against any explicitly enumerated mutation endpoint pattern (e.g., `MUTATION_ENDPOINTS.*`, `/api/stitch_editor/{preview,bake,job}`, `/api/video/{set_active,create}`) appears outside the declared channel directories (`src/components/`, `src/state/`, `src/utils/`, excluding `src/api/` where the channel itself lives). It does NOT and cannot guarantee generalized closure of the "no raw mutations anywhere" property — only the patterns/signatures explicitly enumerated in the gate's regex set. New patterns require explicit gate updates.

The app may or may not have an analogous channel — that's a design decision per repo. This spec mandates:
- The runbook `Production/docs/APP_STRUCTURAL_RULE_RUNBOOK_v1.md` exists Day 1, documenting how to add a grep CI gate (template: storyboard arch-fix Phase 3.4 YAML) AND explicitly noting the "structurally enforced for declared patterns" framing — so future implementers don't over-claim what their gate covers.
- IF/WHEN the app introduces a mutation channel (e.g., a single client-side Firestore writer or a single API client wrapping all CF calls), the gate is added per the runbook with explicit pattern enumeration + directory scope + blind-spots documentation.
- No speculative gates Day 1; the runbook is the load-bearing artifact for piece 3's third bullet.

**3.5. Custom ESLint rules.** Same pattern as 3.4: runbook documents how to write one (link to ESLint AST docs + a worked example). No speculative custom rules Day 1.

### Phase 4 — Piece 4: Schema contracts

**4.1. `firestore_schema.json` lockfile** lives in a shared repo or as a git submodule (per LD `DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA`). The lockfile is the source of truth for:
- All Firestore collections + document shapes
- All CF request/response shapes (paired with Zod schemas)
- Required environment variables (paired with `zod-env` schemas)

**4.2. Auto-gen step.** A script (e.g., `scripts/gen_types_from_schema.ts`) reads `firestore_schema.json` + emits TS types into each repo's `src/types/generated/`. The generated file has a header comment: "AUTO-GENERATED — DO NOT EDIT. Regenerate via `npm run schema:gen`."

**4.3. Drift-fails-CI.** CI step `schema:check`:
1. Re-runs the generator
2. Diffs the result against committed types
3. Exits 1 if any diff
This means: editing `firestore_schema.json` requires committing both the lockfile change AND the regenerated types in the same PR. CI enforces.

**4.4. API contracts (CF endpoints).** Each Cloud Function has:
- Zod request schema + response schema co-located in the handler file
- Request/response shapes derived from `firestore_schema.json` where they overlap (single source of truth)
- Endpoint version in URL path (`/v1/`, `/v2/`); breaking changes bump version, parallel-host until clients migrate

**4.5. Env vars typed.** Each repo has `src/env.ts`:
```typescript
import { z } from 'zod';
const envSchema = z.object({
  DOPPLER_TOKEN: z.string(),
  FIREBASE_PROJECT_ID: z.string(),
  // ...
});
export const env = envSchema.parse(process.env);
```
On boot, `env` is parsed; missing/wrong-type vars fail loudly at startup, not at first use.

**4.6. Secrets rotation cadence + ownership (per Cursor R3 2026-05-04 — operational minimum for COPPA/payments context).** Doppler-first secrets storage (LD-208) is the storage mechanism; rotation is a separate operational discipline that must be in place before feature 1 because COPPA + payments + therapist-data risk surfaces make stale-key blast-radius unbounded. Minimum requirements:

- **Cadence:** every API key, OAuth client secret, signing secret, and database credential rotates at least quarterly (90 days). Tighter cadence (30 days) for any key that grants write access to user-facing data (Firebase service account, Stripe secret key, Claude API key for AI Coach, ElevenLabs/Wavespeed/etc.).
- **Owner:** every secret in Doppler has a tag `owner=<github-handle>` (Kim solo for v1, named handoff when team grows). Doppler config audit at quarter-end identifies any secret without an owner tag → immediate ownership assignment.
- **Evidence:** every rotation logged to `prod_activity_log` with action `SECRET_ROTATED_<DOPPLER_PROJECT>_<ENV>_<SECRET_NAME>` + `details: {old_key_last4, new_key_last4, rotation_reason}`. CI workflow `.github/workflows/secrets_rotation_audit.yml` runs monthly on a schedule, queries Doppler config age, and posts a GitHub Issue if any secret exceeds its cadence threshold.
- **Compromised-key procedure:** any suspected leak → immediate rotation + activity_log row with `rotation_reason="suspected_compromise"` + audit of access logs for that key's lifetime + `prod_blockers` row tracking remediation.
- **Out of scope (separate program):** secret scanning in repos (TruffleHog / GitGuardian / GitHub secret scanning) — covered by `SECURITY_AUDIT_PROGRAM` per §10. This sub-piece covers rotation discipline only.

This is NOT a 6th piece — it's an operational minimum bolted onto Piece 4 because Doppler-first only solves storage, not lifecycle.

### Phase 5 — Piece 5: Observability + silent failure detection

**5.1. Sentry.** Each repo has `Sentry.init()` with environment tagged (`development` / `staging` / `production`). DSN from Doppler. Source maps uploaded on production builds (CI step). For iOS, Crashlytics + Sentry RN side-by-side per Master spec §8.1.

**5.2. Structured logger.** Every repo has a single logger module:
```typescript
// src/lib/logger.ts
export function logInfo(event: string, data: Record<string, unknown>) {...}
export function logWarn(event: string, data: Record<string, unknown>) {...}
export function logError(event: string, err: unknown, data?: Record<string, unknown>) {...}
```
ESLint rule `no-console` enforces no `console.log` in production code paths (test files exempt). All production log lines go through the logger; the logger emits to Sentry breadcrumbs + cloud logging.

**5.3. Alerts.** Sentry alert rules wired Day 1:
- Error-rate spike (5× baseline over 10 min) → Slack/email
- New error issue (any unique error not seen in last 30 days) → Slack/email
- CF execution time p95 > SLO (per Master spec §19.1) → Slack/email

**5.4. Fail-loud invariant (`SERVER_SILENT_FAILURE_FAIL_LOUD_V1` adapted).** In CF code, any `try/catch` MUST either:
- Re-raise (default), OR
- Log via `logError` AND record a `prod_blockers`-style row in a CF-side `caughtExceptions` collection (so the silent-by-design swallow becomes a tracked event), AND have an inline comment explaining why this catch is non-fatal-by-design.

ESLint rule (custom) enforces: `try { } catch (e) { /* nothing */ }` is a build-time error. The runbook from Phase 3.5 covers writing this rule.

**5.5. Performance telemetry hooks.** Per Master spec §19.1, the 12 timestamps + p50/p95/p99 reporting wiring is co-located with the logger module so the same code paths emit perf data.

### Phase 6 — Verification

**6.1.** All 4 repos have CI green on a commit that exercises every CI step.

**6.2.** RED-then-GREEN proof per repo for piece 1 (deliberately failing test → CI red → restore → CI green).

**6.3.** Spec template referenced from CLAUDE.md + handoff template; one feature spec drafted against the template (any forthcoming feature) demonstrates non-trivial use.

**6.4.** TypeScript strict + ESLint config landed; `npm run lint && npm run typecheck` clean in all repos.

**6.5.** Firestore rules tests cover all Day-1 collections × roles.

**6.6.** Schema lockfile committed; regenerated types committed; `npm run schema:check` green; deliberate schema-drift PR shows CI red, then restore.

**6.7.** Sentry receiving events from staging in all 4 repos; alert rules visible in Sentry UI; one synthetic error fired confirms Slack/email path.

**6.8.** Structured logger module live; ESLint `no-console` enforced; one PR attempting `console.log` in production code shows CI red.

**6.9.** 1 NEW LD registered (`MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_DISCIPLINE_V1`).

**6.10.** This spec registered in `prod_reference_docs`.

**6.11.** Master Tech Spec §14.13 amended with this spec's pointer.

### Phase 7 — Closeout

**7.1.** `prod_activity_log` row `APP_FOUNDATION_DISCIPLINE_INSTALL_COMPLETE` with full gate summary + per-piece per-repo install state.

**7.2.** PR per repo merged to main.

**7.3.** Master overview / status runbook updated with this session's row.

---

## §6 Files modified / created

### Created (this spec session)
- `Production/docs/MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_SPEC_v1.md` (this file)
- (Master spec §14.13 amended — see §11 Insertion section for blast-radius mitigation)

### To be created by the executing session (Phases 1-7, separate downstream session)
- Per repo (×4): `.github/workflows/ci.yml`
- Per repo (×4): `eslint.config.mjs`
- Per repo (×4 TS repos): `tsconfig.json` (strict-mode amended)
- Per repo (×4): `src/lib/logger.ts`
- Per repo (×4): `src/env.ts`
- Per TS repo: `src/types/generated/firestore.ts` (auto-generated; committed)
- Per TS repo: `scripts/gen_types_from_schema.ts`
- `Production/docs/APP_FEATURE_SPEC_TEMPLATE_v1.md`
- `Production/docs/APP_STRUCTURAL_RULE_RUNBOOK_v1.md`
- Functions repo: `firestore.rules.test.ts` per existing collections
- Functions repo: CF-side custom ESLint rule for `SERVER_SILENT_FAILURE_FAIL_LOUD_V1`
- Shared schema location: `firestore_schema.json` (if not already extant)

### Modified (this spec session — surgical only)
- `MINDFULNEST_MASTER_TECHNICAL_SPEC_v6.md` — single new row in §14.13 table + v6.2 changelog entry

---

## §7 Directus writes

- `prod_locked_decisions`: 1 NEW LD `MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_DISCIPLINE_V1` (severity HARD, scope_domain app-dev, enforcement_type ci_check)
- `prod_reference_docs`: 1 NEW row for this spec doc (doc_category `app_architecture` per live `/fields/prod_reference_docs/doc_category` enum verified 2026-05-04 — `implementation_spec` is NOT a valid live enum value; `app_architecture` is the closest fit; has_locked_decisions true, is_current true)
- `prod_activity_log`: spec-creation row at end of this session
- `prod_preflight_reviews`: 1 row at session start (claude_summary + advocate/counter synthesis)

All writes via `try_post_or_queue` with read-back per Rule 35.

---

## §8 Error cases

| Failure | Handling |
|---|---|
| Master spec §14.13 row insertion alters surrounding heading levels or content | STOP — restore from backup; surface to Kim |
| LD write returns 200 but read-back shows truncated `decision_text` | Bisect via shorter writes; never silently accept partial write |
| `prod_reference_docs` doc_category enum rejection | Re-verify against live schema (`/fields/prod_reference_docs/doc_category`); pick from confirmed list |
| Spec doc fails to write (filesystem) | STOP, surface |
| One of the 4 app repos doesn't exist yet | Document in Phase 0.4 blocker row; note in §10 (the discipline applies WHEN the repo is created — non-existent repos don't block this spec's registration) |
| `try_post_or_queue` timeout / 5xx on Directus | Retry per Rule 35; if 3× failed, write to local queue + surface |
| Cursor R-X review surfaces required edit | Fold per the storyboard arch-fix's R1-R6 fold-log pattern; document in §15 |

**No silent failures.** Per Rule 19.

---

## §9 Verification gates

11 gates (per Phase 6). Plus:

- **G12.** Master Tech Spec §14.13 has exactly one new row (this spec's pointer); diff stats: lines added > 0, lines removed = 0; line count delta = lines added; heading count unchanged; final line of file unchanged.
- **G13.** Backup file `MINDFULNEST_MASTER_TECHNICAL_SPEC_v6.md.pre_app_foundation_insert_<ts>.md` exists before edit.
- **G14.** Multipass diff check: re-read master spec at two distinct offsets post-edit, confirm no surrounding content drift.

---

## §10 Out of scope

- **Performance program beyond Master Spec §19.1.** Detailed perf budgets, load testing, Lighthouse CI, etc. are deferred to a perf-program spec.
- **Accessibility program.** WCAG audit + a11y CI is its own program.
- **Security program beyond Firestore rules tests.** Penetration testing, dependency CVE scanning beyond `npm audit` defaults, secret scanning tooling beyond Doppler — deferred.
- **Visual regression testing.** Percy / Chromatic / similar tools — deferred.
- **Mobile-specific gates beyond CI build.** Detox / Maestro for iOS — deferred.
- **Per-feature spec drafting.** This spec writes the TEMPLATE and the runbooks; it does not draft the actual feature specs.
- **Custom ESLint rule library beyond the one example for fail-loud.** App-specific structural rules go in via the runbook (Phase 3.5) as needed; speculative rule library is YAGNI.
- **Wave 2+ retroactive coverage** (the storyboard pattern). The app's foundation discipline IS the prevention of needing retroactive waves; if waves later prove necessary, that's a per-incident decision.
- **Bolt.new scope rules** (Master spec §8.7). Already locked elsewhere; this spec doesn't restate.
- **Production pipeline tooling** (Production/tools/ + storyboard tooling). Out of scope by definition; this spec is app-side only.
- **Repos that don't exist yet at spec-write time.** The discipline applies WHEN a new repo is created (LD enforcement). This spec's Phase 1-7 only covers existing repos; new ones inherit on creation.

**Incidentally-found gap rule:** if Phase 0-7 work surfaces an additional discipline gap (e.g., a sixth load-bearing piece not covered here), log as a follow-up `prod_blockers` row + do NOT expand this spec's scope. Add a v2 amendment after the install completes if the new piece proves load-bearing.

---

## §11 Dependencies

- LDs in §3 already locked (verify pre-flight)
- Doppler project setup (assumed; if not, Phase 0.5 surfaces)
- Sentry org + projects per repo (assumed; if not, surface)
- GitHub Actions enabled in each repo (free tier sufficient for solo founder)
- 4 app repos exist OR are created on-demand (non-existent repos don't block this spec's registration)
- Firebase project + emulator suite installed (per `STAGE3_SECURITY_RULES_FIRST`)

### Dependencies on the storyboard tree

NONE. Storyboard tooling and the app live in separate trees. This spec borrows PATTERNS from storyboard architectural-fix work, but the app installs them independently.

### Dependencies for the executing session (downstream)

- This spec written + LD registered + reference doc registered + master spec amended (THIS session)
- Cursor cross-review of this spec via `Production/docs/MINDFULNEST_APP_ARCHITECTURE_FOUNDATION_SPEC_v1.md` content paste (separate session)
- Per-repo CI baseline check (Phase 0.4) (executing session, per repo)

---

## §12 Notes for the executing session (downstream)

- **DISCIPLINE-FIRST ORDERING IS LOAD-BEARING.** Phase 1 (CI) → Phase 2 (template) → Phase 3 (structural) → Phase 4 (schema) → Phase 5 (observability) → Phase 6 (verification). Don't ship feature 1 before Phase 6 green.
- **All 5 pieces are mandatory; none are optional.** The advocate position lost on this; revisiting it is not in scope.
- **Per-repo install can parallelize.** 4 repos × 5 pieces = 20 install units; independent units can run in parallel sessions.
- **The runbooks (Phase 3.4 / 3.5) are the load-bearing artifacts for "how do we add new structural rules later."** Don't skip them; they're cheap to write and prevent future "we never added the rule because the path wasn't clear" outcomes.
- **Lockfile auto-gen drift** is the single highest-value piece for multi-repo. Land Phase 4 before any feature touches Firestore in a non-trivial way.
- **Per Rule 35:** every Directus write via `try_post_or_queue` with read-back.
- **Per Rule 19:** no shortcuts. If a repo doesn't have a piece because "it'll be quick later," log a blocker; don't rationalize.
- **Per Rule 29:** server staleness check on any code that affects production_server.py (this spec doesn't, but downstream sessions may).
- **Compaction-aware checkpoints** at the end of each Phase. Don't checkpoint mid-Phase.

---

## §13 Cursor review checklist

For Cursor to verify before terminal handoff:

1. Are the 5 load-bearing pieces the right pieces? Is there a 6th (or could one of the 5 be merged) that storyboard's lessons demonstrate but this spec missed?
2. Is the dual-perspective synthesis (§1.1) honest — are there divergence points the advocate would surface that this spec resolved too quickly?
3. Phase ordering (Phase 1-5) — are the dependencies right? Could any phase parallelize?
4. New LD severity HARD vs SOFT — defensible? (It's HARD; alternative SOFT has no enforcement mechanism, which contradicts the spec's premise.)
5. Scope_domain `app-dev` correct, or should this be `cross-cutting` (since it touches multi-repo + the master spec)?
6. Is the Phase 3.4 mutation-channel-grep deferral right (runbook Day 1, gate IF/WHEN), or should the gate be built speculatively Day 1?
7. Coverage gate at 80% line — defensible, or arbitrary? (Industry standard floor; falsifies "no coverage."  Higher numbers are gameable.)
8. Spec template (Phase 2.1) test sections — are the four (unit / integration / e2e / negative) the right four? Anything missing (e.g., property-based testing, fuzz)?
9. Sentry vs alternative observability stacks — Master spec §8.1 already commits to Sentry; this spec doesn't litigate that, but should it?
10. The "incidentally-found gap rule" in §10 — is this scope discipline correct, or is the right move to expand mid-flight when a sixth piece surfaces?
11. Structured logger module — is it under-specified? Should this spec mandate a specific logger library (Pino / winston / Bunyan), or is "single module per repo, custom or wrapped" enough?
12. Env-vars typed via Zod — is this over-engineering for a small surface? (Counter: type errors at boot vs at first use is an unambiguously better failure mode.)
13. Firestore rules test coverage — is per-role × per-collection sufficient, or should role × collection × document-state matrix be enforced?
14. Master spec §14.13 insertion — the right section, or should this also amend §14.10 tier table (Tier 0 — required before G0)?
15. The 80%/non-trivial-coverage rule for "feature ships with tests" — does this leave room for prototype branches or experimental code, or does it inadvertently block exploration?

Append findings as §14 before terminal execution.

---

**End of App Architecture Foundation Spec v1.**

Awaiting Cursor review per §13 checklist.

---

## §14 Cursor review findings

**Verdict:** **REVISE BEFORE SHIP**

The foundation is strong, appropriately load-bearing, and directionally correct for avoiding a storyboard-style retrofit in app domains. The 5-piece structure is defensible and the dual-perspective synthesis is credible.  
Revision is required for a small set of consistency and scope-precision issues that are mechanical but important.

### §13 checklist answers (Q1-Q15)

1. **Q1 (are the 5 pieces right?):** **Mostly yes.** CI, test-with-feature, structural enforcement, schema contracts, and observability are the correct load-bearing floor.
2. **Q2 (dual-perspective synthesis quality):** **Defensible.** Inline steelman is strong enough for this decision class. Parallel sub-agent debate could add breadth but is not required to proceed.
3. **Q3 (phase ordering):** **Good.** CI -> template -> enforcement -> schema -> observability is rational; per-repo work can parallelize.
4. **Q4 (LD severity HARD vs SOFT):** **HARD is correct** for the umbrella LD since enforcement is CI/mechanical.
5. **Q5 (scope_domain app-dev vs cross-cutting):** **app-dev is acceptable** given target repos are app-facing; no blocker.
6. **Q6 (Phase 3.4 gate deferral):** **Hybrid choice is reasonable.** Runbook/wiring Day 1 + instantiate gate when a real mutation-channel analog exists is a pragmatic minimum.
7. **Q7 (80% coverage gate):** **Defensible baseline.** Good floor for changed files; avoids retroactively blocking legacy untouched code.
8. **Q8 (test template sections):** **Good core 4.** Unit/integration/e2e/negative are sufficient for Day 1.
9. **Q9 (Sentry stack choice):** **No relitigation needed.** Master spec already locks this; this spec correctly inherits.
10. **Q10 (incidentally-found gap rule):** **Correct scope discipline.** Logging follow-up blockers instead of scope ballooning is the right mechanism.
11. **Q11 (logger under-specification):** **Acceptable.** "Single logger module per repo" is enough at foundation phase.
12. **Q12 (typed env via Zod):** **Correct choice.** Boot-time fail-fast is the right failure mode.
13. **Q13 (rules test depth):** **Current requirement is baseline-correct**; row/collection/role matrix expansion can be v2 if needed.
14. **Q14 (also amend master spec §14.10?):** **Not required now.** Adding pointer in §14.13 is sufficient for this spec cycle; §14.10 amendment can be a follow-up only if governance wants explicit tier-table text.
15. **Q15 (80% rule blocks exploration?):** **Manageable.** Exploration should happen on non-merge prototype branches; merge-to-main discipline can remain strict.

### Explicit answers to requested weighting points

- **5-piece grain for COPPA/payments context:** Good minimum floor. The only notable gap is explicit **secrets rotation cadence/ownership**; Doppler-first is referenced but rotation policy is not operationalized in this spec.
- **Inline debate vs parallel sub-agents:** Inline synthesis is materially sufficient; parallel debate is optional sanity-check, not a release blocker.
- **LD severity:** Umbrella HARD is correct. Individual piece LDs can remain deferred until concrete enforcement artifacts are installed.
- **Out-of-scope tightness:** Adequate; correctly prevents performance/visual/a11y/cross-browser program creep into this foundation install.
- **Cost framing:** Directionally right that retrofit is more expensive at app scale than storyboard; this should be phrased as "likely much higher" rather than numerically anchored to storyboard effort.
- **LD conflict check:** No direct conflict found with `DASHBOARD_ARCH_TWO_REPOS_SHARED_SCHEMA`, `BUILD_AI_COACH_NOT_RENT`, `BUNDLE_SIZE_CI_ENFORCEMENT_V1`, `APP_REPO_SESSION_DIRECTUS_CRED_LOADING_V1`.

### Required edits before ship

- **R1 — Fix `doc_category` consistency to live enum mapping.**  
  In §7 Directus writes, change `doc_category implementation_spec` to the confirmed live enum value used for this document (`app_architecture` per session context), and keep the enum-rejection fallback note in §8.

- **R2 — Correct master-spec file path references for reproducibility.**  
  Update path references that currently point to `Production/docs/MINDFULNEST_MASTER_TECHNICAL_SPEC_v6.md` to the actual canonical path in this workspace (`MINDFULNEST_MASTER_TECHNICAL_SPEC_v6.md` at Dropbox root), or explicitly mark it as logical/canonical name independent of filesystem path.

- **R3 — Add explicit secrets-rotation operational minimum (small addition, not a 6th piece).**  
  Under Piece 4 or 5, add one concrete requirement: rotation cadence + owner + CI/ops check (e.g., quarterly token/key rotation evidence in activity log). This closes a real app-domain risk not covered by storyboard-derived lessons.

- **R4 — Tighten "structurally retroactive" phrasing when referring to storyboard-derived gate patterns.**  
  Keep the current hybrid stance, but phrase as "structurally enforced for declared patterns/signatures" to avoid over-claiming generalized closure.

---

## §15 R-fold log (Cursor §14 R1-R4 folded 2026-05-04)

| Cursor required edit | Where it landed |
|---|---|
| R1 — Fix `doc_category` consistency to live enum mapping | §7 — line updated to use `app_architecture` (live enum value) with explicit verification note: `implementation_spec` is NOT a valid live enum value; `app_architecture` is the closest fit per `/fields/prod_reference_docs/doc_category` verified 2026-05-04 |
| R2 — Correct master-spec file path references for reproducibility | §3 (Dependencies) — added explicit "Canonical filesystem location" note clarifying that `MINDFULNEST_MASTER_TECHNICAL_SPEC_v6.md` lives at the Dropbox project root, NOT under `Production/docs/`. All references in this spec use the bare filename to mean that root-level file. |
| R3 — Add explicit secrets-rotation operational minimum | §5 Phase 4 — NEW substep 4.6 added (cadence: quarterly default, 30-day for write-access keys; ownership: per-secret `owner=<github-handle>` Doppler tag with quarterly audit; evidence: `prod_activity_log` action `SECRET_ROTATED_*` per rotation + monthly CI workflow `secrets_rotation_audit.yml` posting GitHub Issue if cadence breached; compromised-key procedure documented; secret scanning tooling explicitly out of scope, owned by `SECURITY_AUDIT_PROGRAM` per §10) |
| R4 — Tighten "structurally retroactive" phrasing | §5 Phase 3 — substep 3.4 rewritten to use Cursor's preferred phrasing: "structurally enforced for declared patterns/signatures." Explicitly enumerates the storyboard gate's actual coverage (specific regexes against specific directories) + acknowledges it does NOT and cannot guarantee generalized closure of "no raw mutations anywhere." Runbook `APP_STRUCTURAL_RULE_RUNBOOK_v1.md` instructed to carry this same framing forward so future implementers don't over-claim. |

All 4 edits are mechanical applications of Cursor's required language. No substantive scope expansion. R3's secrets-rotation addition is operational hygiene (not a new piece) — bolted onto Piece 4 because Doppler-first only solves storage, not lifecycle.

Spec ready for Cursor v2 verification pass.
