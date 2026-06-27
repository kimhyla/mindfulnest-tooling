---
name: durable-if-appropriate
description: >-
  Decide whether a fix needs real durability work, then apply the minimum correct
  layer (code vs runtime data vs one-off). Use when Kim says "make this durable
  if appropriate", "durable if appropriate", "should this be durable?", or
  asks how to balance durability vs complexity.
---

# Durable If Appropriate

Kim does **not** run terminal. The agent decides **and executes** the right layer.

## Trigger phrases

- "make this durable if appropriate"
- "durable if appropriate"
- "should this be durable?"
- "is a durability fix needed here?"

## Step 1 — Classify the incident (mandatory)

Use **three categories** from Beat Gen invariants (`.cursor/rules/beatgen-durability-invariants.mdc`):

| Cat | What | Ship as |
|-----|------|---------|
| **1 — Code** | Handler/UI/heal/submit bug | Commit + deploy + pytest + `build-sha` |
| **2 — Runtime data** | Wrong sidecar row, registry, per-event bind | Disk fix + optional guard in cat-1 |
| **3 — One-off ops** | Manual redo during triage | **Not shipped alone** — extract cat-1 if recurring |

**Output first** (before coding):

```markdown
## Durability decision
- **Category:** 1 / 2 / 3
- **Appropriate to durable?** yes / no / partial
- **Why:** …
- **If yes — layer:** code | runtime heal | invariant | skip
```

## Step 2 — Is durability appropriate? (decision tree)

Answer **yes** (full durability path) when **any** of:

1. Bug can recur on **refresh, redo, new Event_N, or deploy restart** without operator memory
2. Touches **parser, gate, sidecar field, O3 submit, multi-store sync** (disk vs intent vs UI poll map)
3. Prior "fix" was **chat-only, grep-only, or cat-3 only**
4. User saw **wrong UX after correct server state** (stuck Generating, phantom busy, stale slot)

Answer **no** (minimal fix only) when **all** of:

1. Pure **cat-2** wrong data on one beat and root cause is known operator error
2. **Docs/copy** only
3. **One-time** migration already has cat-1 guard and this is cleanup
4. **Cosmetic** UI with no state contract

Answer **partial** when:

- Needs **cat-2 recovery now** + **small cat-1 guard** so it does not recur
- Example: move g12 to slot 2 on disk **and** add wake-refresh so UI matches sidecar

## Step 3 — Pick the durability approach (prefer simpler)

**Do not default to more heals.** Pick the **lowest layer** that satisfies Step 2:

| Approach | When | Avoid |
|----------|------|-------|
| **Invariant** | One rule prevents a class of bugs | Patching symptoms in 3 places |
| **Authoritative store** | Intent/terminal owns job lifecycle; sidecar is gallery | Log-path → job-id inference |
| **Read/write split** | GET heals response; debounced delta persist | Full sidecar re-scan under lock |
| **Client wake sync** | Tab sleep / throttled timers | Infinite poll TTL |
| **Golden contract test** | Behavior Kim would notice | `assert "fn" in file` alone |

**Red flags — durability made things worse:**

- Same heal runs **in-memory and again under sidecar lock**
- **Second source of truth** (log path revives `ui_job_id` after terminal)
- **grep-only** tests without behavior fixture
- **Cat-3** "works now" without commit

If you see these, **simplify** (remove redundant path) rather than add another heal.

## Step 4 — Execute by category

### If cat-1 (code) + durability appropriate

1. Read `~/.cursor/skills/real-durability/SKILL.md` — failure inventory + golden fixtures
2. Minimal invariant-first diff
3. Behavior pytest (not grep-only)
4. If server-side: `~/.cursor/skills/full-qa/SKILL.md` — deploy, `build-sha`, commit

### If cat-2 (runtime data) only

1. Fix on-disk with evidence (path + field before/after)
2. Say whether **redo** is required for other beats
3. If recurrence likely → add cat-1 guard + test

### If cat-3 only

1. Do the op for Kim
2. **Must** end with: "extracted cat-1?" yes/no
3. If yes → open code task; do not call incident "fixed"

## Step 5 — Beat Gen conflict review (when appropriate)

Run a **light conflict review** when:

- Adding a new heal, busy detector, or session-state persist path
- UI still lies after server truth is correct
- Lock waits appear in O3 logs during Beat Gen refresh

**Review checklist** (grep + read, not Find Issues):

| Conflict type | Look for |
|---------------|----------|
| **Truth** | Two stores both claim "job running" (sidecar vs intent vs `activeO3Jobs`) |
| **Lock** | Heavy work under `sidecar_file_lock` during session GET |
| **Client/server** | TS `beatO3JobLooksRunning` ≠ Python `beat_o3_voice_job_running` |
| **Heal cascade** | heal A clears field heal B rehydrates |
| **Display** | `buildFixedO3OptionSlots` order ≠ `assign_kling_o3_option_to_slot` target |

Report conflicts found + which tier fix applies (truth / lock / client sync).

## Report template

```markdown
## Durable if appropriate — [title]

**Category:** 1 / 2 / 3
**Appropriate?** yes / no / partial — …

**Approach chosen:** invariant | authoritative store | wake sync | runtime only | skip

**What we did not do (and why):** …

**Proof:** pytest / curl / sidecar field / build-sha

**Commit:** `<sha>` or "cat-2 only — no commit"
```

## Related

- Cat 1/2/3 + proof block: `.cursor/rules/beatgen-durability-invariants.mdc`
- Test design: `~/.cursor/skills/real-durability/SKILL.md`
- Deploy proof: `~/.cursor/skills/full-qa/SKILL.md`
