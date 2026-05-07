# PHASE B ARCHITECTURE — ZOOM-OUT REVIEW v2

**Date:** 2026-04-17
**Supersedes:** v1 (preliminary synthesis; this doc incorporates full 4+4 adversarial review)
**Audit trail:** Phase 0 preflight row id=46 (task_id=`phaseb-zoomout-b4b7a84d`) + id=44 (other thread's Phase B v2 review). Research agents: B1 (v1 spec extraction), B2 (v2 review-of-review), B3 (existing-stack map), B4 (off-the-shelf survey). Advocacy agents: 4 advocates + 4 counter-agents against Options A/B/C/D.
**Status:** Recommendation = **Option E (hybrid: minimal extraction + measure + defer unification)**. Option E itself has NOT been through its own 4+4 yet — if Kim approves the framing, that 4+4 happens before commit.

---

## 1. KIM'S QUESTION (verbatim)

*"how many layers out do we need to zoom before we see that early decisions may have been wrong? Is there simpler software out there? Could we stitch existing tools? Is our bespoke approach actually right for us? Or should storyboard + Phase B merge into ONE unified Module Producer that handles all 7 screens?"*

---

## 2. THE FOUR OPTIONS EVALUATED

| Option | Position |
|---|---|
| **A** | Build spec-v1 Phase B Producer as specified (4-layer Flask tool at localhost:5112; apply 20 amendments; resolve 5 pending Kim decisions) |
| **B** | Delete Layer 4 from v1; keep Layers 0-3 as Python libraries; use AE + aerender OR Resolve + Python for visual compositing |
| **C** | Ship M2-M5 manually on POC v8 scripts as-is; build nothing new; decide after M5 |
| **D** | Build unified Module Producer covering all 7 screens (map → intro → phase_a → phase_b → resolution → win → decoration) |

---

## 3. COUNTER-AGENT VERDICTS

### Option A — REJECTED (3 CRITICAL + 4 HIGH)

- **CRIT-W1:** "20 amendments = stress-tested" inverts the evidence. Stress-testing produces convergence; this spec produced *contradictions that survived review* (R2 rejects what G5 accepts; D4 is simultaneously accepted AND pending K3; A3/G2 conflict). That's under-specification, not settled design.
- **CRIT-W2:** Rule 19 INVERTED. Advocate A cites Rule 19 to *prevent* revisiting; but Rule 19 explicitly forbids *open error paths*, and the unresolved contradictions ARE open error paths. Invoking Rule 19 to justify not fixing them is a material misapplication.
- **CRIT-W3:** Time-estimate violation is load-bearing. "~2-3 weeks realistic" anchors the ROI framing. Kim's memory explicitly flags flat-number estimates as unreliable. Remove the estimate, the argument collapses.
- HIGH: ExtendScript-deprecation is strawman (AE UXP is migration path; Resolve sidesteps Adobe entirely); v1 adds UX not coverage (POC v8 already covers 54); two-server "cognitive modes" is unevidenced rationalization; original 4+4 did not consider off-the-shelf (procedural sufficiency ≠ substantive sufficiency).

### Option B — REJECTED (3 CRITICAL + 6 HIGH)

- **CRIT-1:** Learning-curve cliff contradicts Kim's operating profile. AE is moderate-to-steep; Resolve is steep industry-grade. Kim is solo + non-engineer. "Kim builds the template ONCE" assumes she becomes competent enough in Adobe/Blackmagic to debug template failures mid-production. Same pattern Rule 19 forbids ("it'll be fine once Kim learns it" = error path left open).
- **CRIT-2:** Pause-timing fidelity unverified. v1 spec captures per-sentence pauses at 0.5s / 1.5s / 2s granularity. `{{PAUSE:Xs}}` Markdown markers through TTS concatenation can drift 50-200ms per marker due to TTS tail decay + silence padding. Across a 40-sentence Phase B = multi-second aggregate drift = invalidates therapeutic timing.
- **CRIT-3:** Resolve API audio-cue gap is a plan-killer on that path. If Resolve can't programmatically place per-sentence audio cues, plan collapses to AE-only, inheriting ExtendScript deprecation risk. Advocate B presented "AE or Resolve" as a choice; it's actually forced to AE.
- HIGH: Two-toolchain maintenance (Python + Adobe); "template once" false across arcs (Wisdom Stone / different creature framings will force rebuilds); ExtendScript deprecates Sept 2026 ≈ 5 months from launch; 20 amendments don't fully evaporate (D1-D6 data model, A1-A5 audio constants apply regardless); Layer 1 UI punt = "we'll add it later" pattern Rule 19 forbids; non-engineer + aerender CLI + template nesting = silent failure risk.

### Option C — REJECTED (3 CRITICAL + 3 HIGH)

- **CRIT-1:** "Sample size of one" defense inverts evidence. Kim's zoom-out question at M1 IS a second data point. A solo founder with finite capacity and 53 modules ahead asking "should I build a tool?" = felt need. Dismissing it requires assuming Kim's friction-sense is wrong.
- **CRIT-2:** "POC v8 IS the tool" = category error. A collection of Python scripts Kim runs sequentially while fixing ffmpeg glitches is a workbench, not a tool. Tools have idempotent entry points, state recovery, don't require per-invocation parameter re-tuning. Advocate C defines away the problem.
- **CRIT-3:** Exit criteria have no sensor. "After M5 retrospective" + ">6hrs/module triggers build" require Kim to measure and remember per-module labor. Kim's memory explicitly unreliable for time. Trigger without telemetry = trigger that never fires = default is manual-forever.
- HIGH: Opportunity cost ignored (49 modules × saved-hours is unmodeled); "tooling doesn't ship" false at second order (Phase B output IS shipped, bad tool → bad output); YAGNI misapplied (YAGNI forbids speculative abstractions, not extractions of felt need).

### Option D — REJECTED (3 CRITICAL + 4 HIGH)

- **CRIT-1:** N=1 induction fallacy. Generalizing a unified abstraction from exactly ONE complete module (M1). Schema will encode M1's quirks as universal invariants; M2 (Luna — excitable/physical/dramatic) and M5 (Bork loudspeaker) will expose content shapes M1 didn't have.
- **CRIT-2:** Category error — production vs app-side. Map + decoration (Wishing Garden) are React Native runtime-rendered per APP-22/APP-23, NOT pre-produced video assets. "378 screen productions" figure inflated — 108 of those are app code, not production-pipeline outputs. The "7-screen unified producer" is 5-screen at most; the pitch rests on a miscount.
- **CRIT-3:** Ships-M2-never = Rule 19 violation in disguise. Option D delays every downstream module to build a tool. M1's value only compounds when M2-M6 ship. No closure plan, no SHORTCUT_ entry, no `app_blockers` deadline. Gold-plating-as-blocker is an error path in disguise.
- HIGH: "Subsume as stages" understates refactor of 4 skills + 5 tools, re-opens locked §8.2/§8.3/§8.4 lipsync decisions; composition shares NO code path across screens (only the English word); Kim's zoom-out ≠ Option D mandate (design question ≠ implementation commitment); Option D strictly larger than v1's 20-amendment pile → amendment rate projected to 40+.

---

## 4. WHAT SURVIVES ALL 4 COUNTER-ATTACKS

Distilled from counter findings:

| Constraint | Source |
|---|---|
| Don't build v1 as specified — unresolved contradictions are open error paths | Counter-A W1, W2 |
| Don't rely on prior 4+4 — it didn't consider off-the-shelf | Counter-A W7 |
| Don't flat-estimate weeks — Kim's explicit feedback | Counter-A W3 |
| Don't put AE/Resolve on Kim's critical path — learning cliff | Counter-B CRIT-1 |
| Don't use Markdown-only pause markers at therapeutic precision — verify first | Counter-B CRIT-2 |
| Don't default to manual-forever — triggers must have sensors | Counter-C CRIT-3 |
| Don't treat POC v8 as "the tool" — it's a workbench | Counter-C CRIT-2 |
| Don't ignore Kim's felt need — she asked the question for a reason | Counter-C CRIT-1 |
| Don't unify at N=1 — need 3+ data points | Counter-D CRIT-1 |
| Don't include app-side in production tool — category error | Counter-D CRIT-2 |
| Don't delay M2 for tool build — ships-never pattern | Counter-D CRIT-3 |
| Don't defer decisions as "we'll add later" — Rule 19 | Counter-B HIGH |

---

## 5. RECOMMENDATION — OPTION E

**A hybrid that respects every surviving constraint:**

### 5.1 What Option E is

1. **Ship M2 now on POC v8 scripts.** Do not block M2 on tool-build. This addresses Counter-D CRIT-3 (ships-M2-never) and Counter-C's valid framing that M2 can't wait.

2. **In parallel with M2, do a bounded extraction:**
   - Promote POC v8 scripts into `Production/lib/phase_b/` as a coherent module set. Reduce copy-paste only. Do NOT introduce a new Flask server. Do NOT build a timeline editor. Do NOT refactor existing skills.
   - The extraction target: any script or command that appeared verbatim in M1 production and will appear again in M2. Clear wins only. Speculative abstractions are out of scope.

3. **Build ONE narrow UI addition:** a pause-annotation route on the EXISTING `localhost:5111` production server (NOT a new localhost:5112 server, NOT a drag-drop timeline editor). This route lets Kim input per-sentence pause durations into Directus → `prod_script_pauses` collection (per v2 review D1 amendment). Generated audio script reads this collection.
   - Rationale: addresses Counter-B CRIT-2 (Markdown precision risk) by making pause data structured, not free-text markers. Addresses Counter-A's "v1 adds UX" argument by providing the single UX element that genuinely adds value vs POC v8.

4. **DO NOT build Layer 4 (drag-drop timeline editor).** ffmpeg compose pattern from POC v8 is correct for consistent-framing meditation videos. If per-module visual variation emerges across M2-M5, revisit THEN.

5. **DO NOT choose between AE and Resolve.** Don't put either on Kim's critical path. If a future module demands visual-compositing complexity POC v8 ffmpeg can't handle, that's when we evaluate AE vs Resolve — with evidence from M2-M5, not speculation.

6. **Add a telemetry sensor.** Kim logs a one-line Directus row per module after production: `prod_module_production_log` with `module_id`, `hours_spent_rough` (no precise counting — band: "quick / medium / painful"), `friction_areas` (free text), `tooling_ideas` (free text). This creates the sensor Counter-C said was missing. Not a clock; a post-hoc friction-capture.

7. **Defer the unification decision (Option D) until after M5.** At M5, we have 5 data points. The data determines whether unification is real or lexical illusion (per Counter-D HIGH-5). Explicit gate: after M5 production log is written, run a fresh 4+4 on "build Unified Module Producer yes/no" with 5 modules of real data.

### 5.2 What Option E explicitly rejects

- ❌ Building any new Flask server (localhost:5112)
- ❌ Building a drag-drop timeline editor
- ❌ Putting AE or Resolve on Kim's critical path
- ❌ Refactoring existing production skills
- ❌ Forcing Kim to become an Adobe/Blackmagic operator
- ❌ Unifying all 7 screens into one tool now
- ❌ Manual-forever with no measurement
- ❌ Pre-solving the 20 amendments from the v1 spec (most become irrelevant)

### 5.3 Why Option E survives the counter-attacks

| Counter constraint | How E addresses it |
|---|---|
| Don't build v1 as spec'd | No v1 build |
| Don't flat-estimate weeks | No flat estimate given |
| Don't put AE/Resolve on critical path | Explicitly out |
| Markdown-only pause precision risk | Structured `prod_script_pauses` via narrow UI route |
| Manual-forever default | Telemetry sensor on every module + explicit M5 revisit gate |
| Unification at N=1 | Unification explicitly deferred to N=5 |
| App-side in production tool | Option E scope is phase_b + intro screens only; map/decoration stay app-side |
| Ships-M2-never | M2 ships now on POC v8 |
| "We'll add later" Rule 19 violation | Every "later" is specified (M5 revisit, friction-driven extraction) |
| Kim's felt need ignored | Bounded extraction addresses it proportionally |
| POC v8 is not a tool | Extraction to `Production/lib/phase_b/` upgrades workbench to minimal tool |

### 5.4 Honest weaknesses of Option E

- (a) "Bounded extraction" is subjective — Kim/Claude must judge what to extract. Risk: over-extracting into Option B territory, or under-extracting so nothing changes.
- (b) Telemetry sensor depends on Kim filling in a Directus row per module. If she skips it, the M5 revisit has no data. Mitigation: a session-start prompt after any Phase B module ships reminds Kim to log.
- (c) Defers the real architectural question (unification?) rather than answering it. Some people prefer the big bet.
- (d) The pause-annotation UI route IS a small build — not zero. It's the only net-new UX in Option E.
- (e) If M2-M5 ship uneventfully, the M5 revisit may find "just keep doing this" which looks like procrastination but may be correct. Distinguishing "still discovering" from "avoiding the decision" requires honesty at M5.

### 5.5 What happens next if Kim approves Option E

1. **This review + Option E recommendation** → gets its own 4+4 in the other thread before commit. The 4+4 here was on the 4 options, not on E specifically.
2. **On Option E commit:** promote POC v8 scripts → `Production/lib/phase_b/`. Add `prod_script_pauses` collection. Add `prod_module_production_log` collection. Add pause-annotation route to existing `production_server.py` on localhost:5111. No new Flask server.
3. **M2 ships** using the lightly-extracted pipeline. Kim logs friction.
4. **After M5:** fresh 4+4 on "Unified Module Producer yes/no" with real data.

---

## 6. CONNECTION TO STAGE 3 EXECUTION PLAN (this thread)

**No changes required to the Stage 3 execution plan.** Option E touches production-pipeline tooling (PROD section + C10 governance files), not app-code architecture (APP-* rows). Wave A through Stage 3 proceed as planned.

**Minor notes that stay true regardless of Option E:**
- APP-22 (animation stack) and APP-23 (scene composer) continue to consume pre-rendered MP4 outputs from whatever production pipeline exists
- Kim's §12 Q1 answer already included adding phase-b-writer + storyboard-producer governance files (they become the Option E governance files for the extracted library and pause-annotation route)

---

## 7. OPEN QUESTIONS FOR KIM

1. **Approve Option E framing?** If yes, run its own 4+4 before commit. If no, which of the four pure options survives your judgment despite the counter-findings?
2. **Telemetry method:** Directus row per module OR simpler (Markdown append to a file)? Recommend Directus so weekly audit cron can aggregate.
3. **M5 revisit timing:** what's the concrete trigger? (Proposed: "after M5 production log written and approved listen-through completes.")
4. **pause-annotation UI scope:** per-sentence pause durations is the minimum. Also include cue markers (`{{INHALE_CUE}}`, `{{BELL_CUE}}`)? Recommend YES — cue markers share the precision concern.
5. **Who owns the `Production/lib/phase_b/` extraction:** Claude in the other thread, Claude in this thread, or back-and-forth?

---

## 8. WHAT THIS REVIEW v2 IS NOT

- Not a commit-to-build for Option E (needs its own 4+4 first).
- Not a rejection of every point in spec-v1 or the v2 review synthesis. Data-model cleanups (D1-D6), error-handling taxonomies (E1-E6), governance (G1-G5) mostly generalize to Option E — they applied to Layers 0-3 regardless.
- Not a replacement for the other thread's decision authority.
- Not a full architectural spec of Option E. A directional recommendation with survival-under-counter-attack evidence.

---

**End of review v2.**

**Next in other thread:** run 4+4 specifically on Option E vs status-quo-POC-v8 before commit. Get Kim's answers to §7. Then execute.
