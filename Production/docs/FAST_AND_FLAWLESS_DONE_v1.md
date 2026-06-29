# Fast and Flawless — Definition of Done v1

**Marker:** `FAST_AND_FLAWLESS_DONE_V1`  
**Gate:** `Production/scripts/verify_fast_and_flawless_done.sh` (exit 0 required before "done")

Machine-enforced closure for operator UX. An agent must **not** declare fast/flawless complete until this gate passes.

## Acceptance checklist

| ID | Requirement | Proof |
|----|-------------|-------|
| FF-001 | Operator session merge (Tier D D-008..D-021) | `verify_operator_edit_surfaces_durability.sh` |
| FF-002 | O3 prompt lineage (O3-004..006) | `verify_o3_prompt_lineage_durability.sh` |
| FF-003 | Waveform time authority (WTA-017, GAP-001..003) | `verify_waveform_time_authority.sh` + REMOUNT-1 e2e |
| FF-004 | Watercolor drop timing (WTA-018) | DROP-WC-1 / F7 e2e |
| FF-005 | Behavioral parity executable suite (SB-009) | `behavioral-parity.spec.ts` non-fixme tests green |
| FF-006 | Event switch zero-touch | `verify_event_switch_automation_durability.sh` |
| FF-007 | Operator session perf | `verify_operator_session_perf.sh` |
| FF-008 | Named hydrate e2e markers present + green | `phase_e_operator_hydrate.spec.ts` |
| FF-009 | Edit-during-poll across tabs | `phase_e_edit_during_poll.spec.ts` |
| FF-010 | Live Event fleet hydrate | `phase_e_hydrate_live.spec.ts` on :5111 |
| FF-011 | Symptom matrix zero in-scope partial/spec-only | grep gate in meta script |
| FF-012 | Deploy build-sha = git HEAD on :5111–5113 | curl proof in meta script |

## Out of scope (explicit — not blocking FF done)

- `behavioral-parity.spec.ts` **test.fixme** rows (S3 polish backlog per audit v1)
- WTA-0 full `waveformSeekController.ts` extract (future refactor)
- Infra rows (RC10) — parallel ops gates only

## Maintenance

When adding operator edit surfaces, extend FF-001/008/009 and re-run meta gate.
