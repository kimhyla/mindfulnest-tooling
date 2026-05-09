# Fixture — v2 handoff with two HALT gates

## What you're doing

Test fixture for DS-26 handoff parser.

## HALT gates

> **Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.
>
> Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

### Gates (must all be MET before Phase 2)

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|------------------|-----------------|-------------|
| 1 | Gate one | `Production/docs/example.md` | Met | HALT |
| 2 | Gate two | `Production/docs/example.md` | Met | HALT |

## Pre-flight

N/A for fixture.
