# Hook Lifecycle Cost Report — 2026-05-08

**Author:** Claude Opus 4.7 (session a5a61aac, housekeeping pass).
**Source of truth:** `~/.claude/settings.json` (read 2026-05-08T12:31Z).
**Scope:** Inventory every hook entry across all five lifecycles (PreToolUse, PostToolUse, SessionStart, PreCompact, Stop), measure empirical latency, compute cumulative per-turn impact, recommend retirements.

---

## 1. Per-hook inventory and latency

Latency = mean of 5 cold runs, `/usr/bin/python3 <script>` with `{}` JSON on stdin (matches harness invocation pattern). All times in seconds.

| Lifecycle | Matcher | Command | Mean (s) | Max (s) | I/O profile |
|---|---|---|---|---|---|
| PreToolUse | Write\|Edit | inline `jq` + `grep` Rule 19 reminder | ~0.020 (est., shell-only) | ~0.030 | local string match, no network |
| PreToolUse | Write\|Edit | `Production/scripts/preflight_hook.py` | 0.046 | 0.056 | local file read (locked_decisions.cache.json), no network |
| PreToolUse | Write\|Edit | `Production/scripts/docx_confirmation_hook.py` | 0.037 | 0.038 | local file read, no network |
| PreToolUse | Bash | `Production/scripts/deny_bash_governed_write.py` | 0.030 | 0.038 | local regex match, no network |
| PostToolUse | Write\|Edit\|Bash | `Production/scripts/session_event_logger.py` | 0.028 | 0.029 | local append-only log, no network |
| SessionStart | (none) | inline shell + `weekly_preflight_audit.py --hours 12` (BACKGROUNDED with `&`, timeout 30) | ~0 (foreground) | ~0 | runs in bg; does not block turn |
| SessionStart | (none) | inline shell — copy CLAUDE.md to ~/.claude/mindfulnest-context (timeout 15) | ~0.05 (file copy + sentinel grep) | ~0.10 | local cp, no network |
| SessionStart | (none) | inline shell — write canary timestamp to last_session_start.txt (timeout 5) | ~0.005 | ~0.01 | local write |
| SessionStart | (none) | `Production/scripts/lock_decision.py rebuild-cache` (BACKGROUNDED with `&`, timeout 30) | ~0 (foreground) | ~0 | runs in bg; does not block turn |
| PreCompact | (none) | `Production/scripts/precompact_save_trigger.py` | not measured (rare-fire path) | est. <0.1 | local write |
| Stop | (none) | `~/.claude/hooks/stop_state_claim_scan.py` | 0.026 | 0.027 | reads transcript JSONL, regex scan, no network |

Note: weekly_preflight_audit.py is 999 lines / 46 KB and DOES make Directus calls (`urllib.request` × 4 occurrences). It is intentionally backgrounded with `&` at SessionStart so it cannot block the foreground session.

---

## 2. Worst-case cumulative impact per assistant turn

A typical turn that issues a mix of Bash + Edit + Write tools triggers PreToolUse + PostToolUse for each tool. The cumulative budget per turn is:

| Phase | Hooks fired | Worst-case sum (s) |
|---|---|---|
| PreToolUse on Write/Edit (3 hooks) | jq-grep + preflight_hook.py + docx_confirmation_hook.py | 0.030 + 0.056 + 0.038 = **0.124** |
| PreToolUse on Bash (1 hook) | deny_bash_governed_write.py | **0.038** |
| PostToolUse on any tool (1 hook) | session_event_logger.py | **0.029** |
| Stop (1 hook, fires once per turn end) | stop_state_claim_scan.py | **0.027** |

**Per-tool overhead worst case:**
- For a Write/Edit tool call: 0.124 (Pre) + 0.029 (Post) = **0.153 s ≈ 153 ms**.
- For a Bash tool call: 0.038 (Pre) + 0.029 (Post) = **0.067 s ≈ 67 ms**.

**Per-turn overhead worst case (10 tool calls — half Write/Edit, half Bash):**
5 × 0.153 + 5 × 0.067 + 1 × 0.027 (Stop) = 0.765 + 0.335 + 0.027 = **~1.1 seconds per heavy turn.**

**Per-session worst case (SessionStart, fires once):**
- Foreground hooks (cp + canary write): ~0.06 s.
- Background hooks (weekly_preflight_audit + lock_decision rebuild-cache): non-blocking.
- **SessionStart foreground budget: ~0.06 s.**

**PreCompact (fires only on auto-compact event):** estimate <0.1 s, infrequent.

---

## 3. Findings — which hooks are paying their freight?

| Hook | Value | Cost | Verdict |
|---|---|---|---|
| jq-grep Rule 19 reminder (PreToolUse) | Reminder banner only — surfaces governed-file edits to Claude. No enforcement. | ~30 ms | **Keep** — cheap and surfaces real signal. |
| preflight_hook.py (PreToolUse) | C5 content scan against locked decisions cache; shadow/enforce mode toggle. | 46 ms | **Keep** — core LD enforcement primitive. |
| docx_confirmation_hook.py (PreToolUse) | DOCX edit guard. | 37 ms | **Audit candidate** — verify it still has unique role distinct from preflight_hook.py; if redundant for DOCX paths, candidate for retirement. NOT retiring in this pass per HALT rule. |
| deny_bash_governed_write.py (PreToolUse) | Blocks Bash from writing to governed paths (settings.json, SKILL.md, etc.) — bypass-prevention. | 30 ms | **Keep** — security-relevant guard. |
| session_event_logger.py (PostToolUse) | Activity log emission for tool use. | 28 ms | **Keep** — feeds weekly_preflight_audit. |
| SessionStart inline-shell suite | Audit log seed, CLAUDE.md staging, canary, cache rebuild. | <100 ms foreground; rest backgrounded | **Keep** — well-architected (foreground minimal, heavy work in `&`). |
| precompact_save_trigger.py (PreCompact) | Rare-fire save trigger ahead of compact. | rare | **Keep** — fires only on compact, low ambient cost. |
| stop_state_claim_scan.py (Stop) | Q1 Part 1 turn-end state-claim scan. | 26 ms | **Keep** — net-new today, value-prop validated by spec §10. |

---

## 4. Recommendation

**No retirement candidate is unsafe today.** Per the HALT rule in the housekeeping mission, no hook surfaced a security concern. The single audit candidate (`docx_confirmation_hook.py`) is **flagged for review** — it overlaps in concern-area with `preflight_hook.py` for DOCX file paths and may be redundant. A 30-minute side-by-side diff would clarify; not retiring in this pass.

**Cumulative budget verdict:** ~1 second of latency on heavy 10-tool turns is well within acceptable for a discipline-enforcement layer. No hook was found to perform network calls in the foreground (all Directus traffic is either backgrounded or absent). No prod_blocker filed — findings do not warrant action right now.

---

## 5. References

- `~/.claude/settings.json` — hook wiring (read 2026-05-08T12:31Z).
- `Production/scripts/preflight_hook.py` — C5 content scan (Wave C WB-C5).
- `Production/scripts/docx_confirmation_hook.py` — DOCX edit guard.
- `Production/scripts/deny_bash_governed_write.py` — governed-path Bash bypass guard.
- `Production/scripts/session_event_logger.py` — activity log emitter.
- `Production/scripts/weekly_preflight_audit.py` — backgrounded SessionStart audit (999 lines / 46 KB).
- `Production/scripts/precompact_save_trigger.py` — pre-compact save trigger.
- `Production/scripts/lock_decision.py rebuild-cache` — backgrounded SessionStart cache rebuild.
- `~/.claude/hooks/stop_state_claim_scan.py` — Q1 Part 1 state-claim scanner.
- Spec: `Production/docs/Q1_PART1_STOP_HOOK_SPEC_v1.md`.

---

## 6. Confidence tags (Rule 24)

- [CONFIRMED via `/usr/bin/python3 <script>` × 5 runs each, 2026-05-08]: Per-hook latency for preflight_hook.py / docx_confirmation_hook.py / deny_bash_governed_write.py / session_event_logger.py / stop_state_claim_scan.py.
- [CONFIRMED via Read of ~/.claude/settings.json, 2026-05-08]: Hook inventory (5 lifecycles, 9 hook entries).
- [CONFIRMED via grep — `grep -E 'DirectusAdminClient|urlopen|urllib.request' <script>`]: Only weekly_preflight_audit.py contains urllib.request tokens (4 hits); all others zero — so foreground hooks make no network calls.
- [INFERRED from `&` shell operator in settings.json]: weekly_preflight_audit and lock_decision rebuild-cache run non-blocking; their wall-clock cost does not gate the foreground session.
- [GUESSED — not measured]: jq-grep inline reminder timing (~30 ms estimate) and PreCompact precompact_save_trigger timing (<0.1 s estimate). Did not run an empirical probe; values are heuristic ceilings based on shell warmup + script size.

---

*End of report.*
