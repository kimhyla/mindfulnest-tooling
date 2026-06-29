# Fast and Flawless — Definition of Done v2 (perfect storyboard)

**Marker:** `FAST_AND_FLAWLESS_DONE_V2`  
**Gate:** `Production/scripts/verify_fast_and_flawless_done.sh` (exit 0 required before "done")

No carve-outs. **Perfect** = every in-scope storyboard surface green + auto speech loudnorm shipped.

## Acceptance checklist

| ID | Requirement | Proof |
|----|-------------|-------|
| FF-001 | Operator session merge (Tier D D-008..D-021) | `verify_operator_edit_surfaces_durability.sh` |
| FF-002 | O3 prompt lineage (O3-004..006) | `verify_o3_prompt_lineage_durability.sh` |
| FF-003 | Waveform time authority (WTA-017, GAP-001..003) | `verify_waveform_time_authority.sh` + REMOUNT-1 e2e |
| FF-004 | Watercolor drop timing (WTA-018) | DROP-WC-1 / F7 e2e |
| FF-005 | **Full** behavioral parity (SB-009) | `behavioral-parity.spec.ts` **zero test.fixme**, all tests green |
| FF-006 | Touchpoint A parity | `touchpoint-a.spec.ts` **zero test.fixme**, all tests green |
| FF-007 | Event switch zero-touch | `verify_event_switch_automation_durability.sh` |
| FF-008 | Operator session perf | `verify_operator_session_perf.sh` |
| FF-009 | Named hydrate e2e markers present + green | `phase_e_operator_hydrate.spec.ts` |
| FF-010 | Edit-during-poll across tabs | `phase_e_edit_during_poll.spec.ts` |
| FF-011 | Live Event fleet hydrate | `phase_e_hydrate_live.spec.ts` on :5111 |
| FF-012 | Symptom matrix zero in-scope partial/spec-only | grep gate in meta script |
| FF-013 | Auto speech loudnorm (Layer A + B) | `verify_speech_loudnorm_durability.sh` + `TECH_SPEC_AUTO_LOUDNORM_V1.md` |
| FF-014 | Deploy build-sha = git HEAD on :5111–5113 | curl proof in meta script |

## Non-blocking (explicit)

- WTA-0 full `waveformSeekController.ts` extract (future refactor only)
- Infra rows (RC10) — parallel ops gates only

## Maintenance

When adding operator edit surfaces or audio pipeline stages, extend FF-001/009/010/013 and re-run meta gate.
