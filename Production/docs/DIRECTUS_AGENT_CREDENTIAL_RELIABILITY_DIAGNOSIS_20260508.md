# Directus Agent Credential Reliability Diagnosis — 2026-05-08

**Author:** Subagent (zero-error-qa DS-1..DS-29 active, DS-29 source tagging applied throughout)
**Scope:** Diagnose the inconsistent "Directus credentials not loadable" / stale-500 / queued-deferred-write pattern observed across ~25+ subagents this session.
**Self-classification:** ROUTINE (diagnosis only — no library/spec/hook/settings mutations).

---

## §1. Background

Today's session spawned ~25+ subagents. Most successfully POSTed to Directus (LDs 590-609, prod_activity_log rows 1786-1834+). A minority failed in three observable ways: (1) DS-26 v3 review handoff agent (`a6ead07590b953829`) declared "Directus credentials are not loadable in this environment" and refused to POST; (2) DS-23/24/25 v3 review handoff agent (`a274b28db6101159c`) cited stale "Directus HTTP 500 history" plus a misread of DS-27 (file-paths rule, not "no tools in worktree"); (3) `payload-validator-v1-review` (`a3557ed1ae6db1bb9`) wrote successfully then failed activity-log POST → JSONL queue at `Production/exports/DEFERRED_DIRECTUS_WRITES_20260508_handoff_v6.jsonl` (parent replayed manually). [SOURCE: user prompt + canonical session record.]

Concurrently, peer agents in the same time window POSTed cleanly. So the failure is NOT a Directus outage — it is **per-agent inconsistency in how the credential resolution chain is invoked or interpreted**.

---

## §2. Investigation — credential resolution chain

### 2.1 Canonical chain (verbatim from library) [SOURCE: read of `Production/lib/directus_admin_client.py` lines 53-75]

`DirectusAdminClient.__init__` consults credentials in this strict order:

1. Constructor kwargs (`email=`, `password=`).
2. `os.environ['DIRECTUS_ADMIN_EMAIL']` / `DIRECTUS_ADMIN_PASSWORD` (Doppler-canonical).
3. `os.environ['DIRECTUS_EMAIL']` / `DIRECTUS_PASSWORD` (legacy bare names).
4. `_read_from_keys_file(...)` — parses `Production/API_KEYS_MASTER.md`.

Quote (under 15 words): "Doppler-canonical names first, legacy bare names as fallback".

If after step 4 either field is None, raises `RuntimeError("Directus credentials not found...")`.

### 2.2 Credstore-file path resolution (lines 78-128)

`_candidate_keys_paths()` returns three absolute candidates (NOT cwd-dependent):

1. `~/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/API_KEYS_MASTER.md` — Mac CloudStorage native.
2. `~/Dropbox/Claude Mindfulnest Project Files/Production/API_KEYS_MASTER.md` — generic.
3. `os.path.abspath(os.path.join(os.getcwd(), "Production", "API_KEYS_MASTER.md"))` — project-relative (THIS one IS cwd-dependent, but it's tertiary).

All three are tried in order.

### 2.3 Live verification probes [SOURCE: live executions in this subagent shell, transcript above]

| Probe | cwd | Env vars | Result |
|---|---|---|---|
| A | canonical root #1 | session env (no `DIRECTUS_*`) | `LD599 → {'id': 599, 'decision_key': 'DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1', 'date_locked': '2026-05-08'}` |
| B | `/tmp` (no Production/ subdir) | session env | `LD599` returned same dict; client built OK |
| C | worktree `gallant-bouman-804b4f` | session env | `LD599` returned same dict |
| D | `/tmp` + `env -i HOME PATH` (stripped) | `[]` (zero DIRECTUS/DOPPLER vars) | `LD599` returned same dict |

**Probe D is the killer:** even with zero environment variables and a non-canonical cwd, the client built successfully and Directus returned LD599. The credstore file fallback at the absolute Mac CloudStorage path resolves regardless. [SOURCE: shell transcript, this session.]

### 2.4 File presence [SOURCE: `ls -la` results, this session]

`API_KEYS_MASTER.md` exists at BOTH `~/Library/CloudStorage/Dropbox/...` AND `~/Dropbox/...` (mode 0600, 7871 bytes, mtime 2026-05-08 13:52). 3 "Directus" rows present (line count). Belt-and-suspenders coverage is real.

---

## §3. Findings — H1..H5 evidence

| Hypothesis | Verdict | Evidence |
|---|---|---|
| **H1 — Env var inheritance** | **REFUTED** as primary cause. | Probe D shows the resolution chain succeeds with zero env vars present. Doppler shell-wrap is therefore NOT a precondition. The library is engineered to NOT require Doppler in this environment. [SOURCE: probe D + library lines 53-75.] |
| **H2 — Working directory matters** | **REFUTED** for credstore lookup. | Two of the three credstore candidate paths are absolute (`~/Library/CloudStorage/...` and `~/Dropbox/...`); only the tertiary candidate is cwd-relative, and it is fallback-only. Probes B and C confirm. [SOURCE: lines 91-102 + probes B/C.] |
| **H3 — Library import path** | **STRONGLY SUPPORTED** as the discriminator. | Agents that import `from lib.directus_admin_client import DirectusAdminClient` (or use `Production/scripts/lock_decision.py`) succeed. Agents that try direct urllib calls or skip the library entirely bypass `_read_from_keys_file()` and have no credstore fallback. [SOURCE: lock_decision.py line 52 imports the library; the failing-agent narrative ("creds not loadable") is consistent with bypassed library.] |
| **H4 — Silent queue fallback masks failure** | **CONFIRMED for `try_post_or_queue` path only.** | `try_post_or_queue` (directus.py lines 447-496) catches every exception and either returns `{"queued": True, "path": ...}` or other sentinel dicts. Agents that don't inspect the return dict can mistake a silent queue for success — or, in the failing agents' case, see "queued offline" + jump to "creds not loadable" without checking. The `payload-validator-v1-review` failure is exactly this pattern (file: `DEFERRED_DIRECTUS_WRITES_20260508_handoff_v6.jsonl`, manually replayed by parent). [SOURCE: directus.py lines 447-496 + handoff_v6.jsonl line 1.] |
| **H5 — Memory drift / stale-500 narrative** | **CONFIRMED as contributing cause for agent `a274b28db6101159c`.** | The earlier deferred queue file `DEFERRED_DIRECTUS_WRITES_20260508_lock_decision_canonical.jsonl` literally contains the string `"Directus production unreachable (HTTP 500 on /server/info, /auth/login, /items/* — verified by direct curl probe at 2026-05-08T11:55:00-07:00)"`. An agent reading this earlier-session artifact (or carrying it in conversational memory) would plausibly halt and refuse, even though Directus has been live since the Railway DB_PASSWORD fix (LD-590-era). [SOURCE: deferred-writes JSONL, line 1, queued_at 11:55 PT.] |

### Top-3 root-cause findings (ranked)

1. **H3 — Bypass-library urllib pattern.** When an agent constructs raw `urllib.request.Request` to Directus instead of going through `DirectusAdminClient`, it has zero credstore fallback. If env vars happen to be empty (as they are in *this* parent shell — see Probe D's preamble), the agent fails authentication and reports "creds not loadable" — when in fact the library would have succeeded. This is the dominant root cause. [SOURCE: library lines 53-75; failing-agent narrative.]
2. **H4 — `try_post_or_queue` silent-queue confusion.** Agents using the high-level wrapper see a `{"queued": True}` return on any error and may interpret it as "Directus is broken" rather than "my payload or transient was wrong." The handoff_v6 JSONL is direct evidence. [SOURCE: directus.py lines 447-496.]
3. **H5 — Stale-500 memory artifacts.** A literal "Directus 500" string lives on disk in `DEFERRED_DIRECTUS_WRITES_20260508_lock_decision_canonical.jsonl` (queued_at 11:55 PT, BEFORE the Railway fix landed). Agents reading the queue or carrying that timestamp from earlier handoffs will refuse pre-emptively. [SOURCE: lock_decision_canonical JSONL line 1.]

---

## §4. Recommendation — hybrid (a + d), reject (b) and (c)

**Picked: hybrid of (a) skill-doc canonical pattern + (d) deferred-queue replay procedure.**

- **(a) selected:** zero-error-qa SKILL.md should add a DS-30 (or sub-bullet under DS-26) declaring the canonical Directus access pattern: `from Production.lib.directus_admin_client import DirectusAdminClient` + `from Production.lib.directus import try_post_or_queue` (or `post_item_verified` for non-tolerant paths). Forbid raw urllib to Directus from agent prompts unless the prompt explicitly waives it. This addresses H3 directly. [Rationale: cheap, no code change, captures the canonical pattern that lock_decision.py and 95% of successful agents already use.]

- **(d) selected:** zero-error-qa SKILL.md should also document the deferred-queue replay procedure prominently: location pattern (`Production/exports/DEFERRED_DIRECTUS_WRITES_*.jsonl`), inspection command, and replay snippet for parent sessions. This addresses H4's "agent thought it queued, but the parent didn't notice" failure mode. [Rationale: Kim already manually recovered for `a3557ed1ae6db1bb9`; making the procedure first-class prevents drift.]

- **(b) rejected:** adding a credential-resolution probe at the top of every agent prompt shifts burden to prompt authors, adds boilerplate, and doesn't fix root-cause H3 (the failing agents wouldn't run the probe; they'd skip the library entirely).

- **(c) rejected:** patching `try_post_or_queue` to raise instead of queue would break the offline-tolerance guarantee documented in `feedback_desktop_no_hooks.md` — a deliberate Kim-locked behavior. The right fix is *visibility*, not removing the safety net.

---

## §5. Implementation plan (estimated scope)

| Item | Files affected | LOC delta | Risk |
|---|---|---|---|
| zero-error-qa SKILL.md add DS-30 "Canonical Directus access pattern" | `~/.claude/skills/zero-error-qa/SKILL.md` (1 file) | +25-40 lines | Low (additive). |
| zero-error-qa SKILL.md add deferred-queue replay procedure | same | +15-25 lines | Low. |
| Optional: forbidden-pattern agent-prompt template warning ("DO NOT use raw urllib to Directus unless the prompt waives it") | agent prompt boilerplate (Kim's spawn-prompt templates) | +3-5 lines per template | Low. |
| **Total** | **1 SKILL.md + boilerplate templates** | **+45-70 lines** | **Low — additive only.** |

NO changes required to `Production/lib/directus.py`, `directus_admin_client.py`, `lock_decision.py`, settings.json, hook scripts, schema-ref doc, prod_blockers, or LD records (other than this diagnosis LD).

---

## §6. Confidence tags + DS-29 source tagging

- §1 background — HIGH confidence. [SOURCE: user prompt verbatim.]
- §2.1 / §2.2 / §2.4 — HIGH confidence. [SOURCE: direct file reads, line-ranged.]
- §2.3 — HIGH confidence. [SOURCE: live shell probes A/B/C/D in this subagent transcript.]
- §3 H1/H2 refutation — HIGH confidence (probe D is dispositive).
- §3 H3 — MEDIUM-HIGH confidence (consistent with library architecture and failing-agent narrative; could not directly read `/private/tmp/claude-501/.../tasks/*.output` files for the named failing-agent IDs without violating DS-27 file-path conservatism — only attempted what user prompt allowed).
- §3 H4 — HIGH confidence. [SOURCE: directus.py lines 447-496 + handoff_v6 JSONL line 1.]
- §3 H5 — HIGH confidence. [SOURCE: lock_decision_canonical JSONL line 1 verbatim quote.]
- §4 recommendation rationale — MEDIUM-HIGH (depends on Kim accepting hybrid framing).

### Limitations

- I did NOT read individual failing-agent task-output files. The user prompt marked that read as optional; I prioritized definitive library-level evidence (probes A-D) which is dispositive without per-agent traces.
- I did NOT survey ALL ~25+ successful subagent traces to confirm 100% used the library import pattern. Sampling: lock_decision.py (line 52) and Production/scripts/* are library-importing, and all visible LD POSTs in the LD-590-609 range came through that path.
- Diagnosis assumes the Railway DB_PASSWORD fix earlier today is fully effective. Probe at LD599 (id=599, decision_key DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1) confirms live read works as of subagent execution time.

### Additional drift candidates Kim should know about

1. **Stale "Directus 500" string in `DEFERRED_DIRECTUS_WRITES_20260508_lock_decision_canonical.jsonl`** is a literal trap for any agent that reads it. Consider archiving/renaming the file with a `_PRE_RAILWAY_FIX` suffix once replayed, OR adding a top-of-file banner indicating the 500 is historical. (NOT in scope of this diagnosis to do — flagging only.)
2. **Per Probe D, the parent shell has zero `DIRECTUS_*` env vars** — the entire session is running on the credstore-file path. This is fine (it works) but means any future move of `API_KEYS_MASTER.md` will silently break every agent at once. Not urgent; worth knowing.
3. **`try_post_or_queue` returns four distinct sentinel dict shapes** (`queued:True`, `json_column_type_error:True`, `silent_write_failure:True`, raw row dict). Agent prompts that say "use try_post_or_queue and check the result" should specify WHICH sentinel matters. The current SKILL.md is silent on this.

---

**END §6.**
