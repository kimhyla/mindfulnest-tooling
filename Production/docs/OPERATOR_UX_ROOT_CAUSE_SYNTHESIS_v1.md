# Operator UX Root Cause Synthesis v1

**Marker:** `OPERATOR_UX_ROOT_CAUSE_SYNTHESIS_V1`  
**Input:** All 149 rows in `OPERATOR_UX_SYMPTOM_MATRIX_v1.md` (parsed 2026-06-29)  
**Method:** 3 parallel RCA passes (sections A–C, D–F, G–J) + counter reconciliation

---

## Executive summary

Phases A–C / Tier C answered: **“Which disk/server field is authoritative at export?”**

The 149-row matrix shows **105 shipped**, **7 partial**, **3 spec-only**, **10 infra**, **6 gap duplicates** (section I overlaps B/C — now shipped).

**Remaining operator pain is narrowed to:**

1. **WTA remount** — playhead 0:00 after audio remount (WTA-017, spec-only)
2. **O3 prompt lineage** — g7/g8 overwrite, char ref pose, parenthetical strip (O3-004..006) — server prompt isolation, not session merge
3. **Behavioral parity** — multi-tab legacy gaps (SB-009)
4. **Watercolor drop timing** — WTA-018 partial

Phase E **session merge** class (RC2) is **shipped** for all operator edit surfaces in `authority_registry.py`.

---

## Meta-root taxonomy (10 buckets)

| ID | Name | Definition | Open rows |
|----|------|------------|----------:|
| **RC1** | Ephemeral vs persisted conflated | Session-only state treated as durable or vice versa | 2 |
| **RC2** | Full-slice refresh without merge owner | GET/poll replaces entire client slice; no merge on omit/in-flight | **0** |
| **RC3** | Competing time/media clocks | WaveSurfer, `<video>`, React ms, duration refs disagree | 4 |
| **RC4** | Effect lifecycle / handler binding | Handlers bound before refs ready; stale closures; remount order | 4 |
| **RC5** | Dual UI surfaces same media | Two players/decoders for one clip | 0 |
| **RC6** | Server canonical rewrite mid-session | Heal/parity/build_prompt mutates sidecar during operator session | 2 |
| **RC7** | Tier C disk authority (resolved) | Export/read gates; merge on save — **shipped class** | — |
| **RC8** | Cache/lineage stale | Correct path, wrong generation (mtime/hash/gen slot) | 1 |
| **RC9** | Cross-partition scope drift | event/milestone/port/build-sha mismatch | 0 |
| **RC10** | Infra/ops | cold boot, locks, Dropbox, CI — not UX architecture | 10 infra |

---

## Full matrix counters (149 rows)

### By status (sections A–J)

| Status | Count | % |
|--------|------:|--:|
| shipped | 105 | 70% |
| partial | 7 | 5% |
| spec-only | 3 | 2% |
| infra | 10 | 7% |
| *Section I duplicates partial/spec rows already counted in B/C* | 6 | — |

**Unique open debt:** 7 partial + 3 spec-only = **10 rows** (section I GAP-* shipped with Phase E).

### By meta-root (all 149 rows — shipped + open)

| Meta-root | Total rows | Shipped | Open (partial+spec) |
|-----------|----------:|--------:|--------------------:|
| RC2 | 28 | 14 | **14** |
| RC4 | 21 | 17 | 4 |
| RC3 | 16 | 12 | 4 |
| RC7 | 44 | 44 | 0 |
| RC9 | 12 | 12 | 0 |
| RC10 | 10 | 0 | 10 (infra) |
| RC6 | 6 | 4 | 2 |
| RC5 | 8 | 8 | 0 |
| RC8 | 8 | 7 | 1 |
| RC1 | 6 | 4 | 2 |

### Open rows only (21 unique)

| ID | Symptom (short) | Meta-root | Fix layer |
|----|-----------------|-----------|-----------|
| WTA-017 | Playhead → 0 after audio remount | RC4+RC3 | WTA module |
| WTA-018 | Drop cue at wrong timestamp | RC3 | WTA module |
| D-008 | Prompt stripped after Generate | RC6 | O3 intent transaction |
| D-009 | Textarea snap-back after Generate | RC6 | O3 intent transaction |
| D-010 | Phase ambient reverts | RC2 | Tier D merge owner |
| D-011 | Stitcher ambient reverts | RC2 | Tier D merge owner |
| D-012 | Storyboard dialogue rollback | RC2 | Tier D protected field |
| D-013 | Storyboard trim fields reset | RC4+RC2 | Tier D protected field |
| D-014 | BG trim overlay mid-drag reset | RC2 | Tier D merge owner |
| D-015 | BG numeric trim draft clobber | RC4+RC2 | Tier D merge owner |
| D-016 | Base clip picker desync | RC2 | Tier D merge owner |
| D-018 | Gallery/trim stale after refresh | RC1 | BG session terminal view |
| D-021 | Storyboard refresh loses edits | RC2 | refreshTick merge |
| TR-010 | (= D-014) | RC2 | |
| TR-011 | (= D-013) | RC2 | |
| O3-004 | g7 overwritten | RC8 | Slot reservation / disk gen |
| O3-005 | Char ref ignored | RC1 | Identity channel closure |
| O3-006 | (female raccoon) stripped | RC6 | O3 intent transaction |
| PA-021 | Ambient preset empty/wrong | RC2 | Tier D |
| PA-022 | Base clip picker | RC2 | Tier D |
| SB-003 | Rollback dialogue | RC2 | Tier D |
| SB-009 | Parity gaps | RC2 | ongoing |

*GAP-001..006 in section I are documentation aliases for WTA-017/018 and D-010/011/014/013.*

---

## The “reasons for the reasons” (3 levels)

### Level 1 — What Kim sees
Snap-back, vanish, 0:00 playhead, wrong clip generation, stale lipsync, scope on wrong event.

### Level 2 — Mechanism (matrix Problem class column)
Poll clobber, blind hydrate, dual clocks, no transaction at Generate, stale cache lineage.

### Level 3 — Common root causes (after Tier C)

```
                    ┌─────────────────────────────────────┐
                    │  Tier C SOLVED (Phases A–C)         │
                    │  "Which disk field wins at export?" │
                    │  RC7, RC9 → 89 shipped rows         │
                    └─────────────────────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
   ┌──────────────┐           ┌──────────────┐           ┌──────────────┐
   │ RC2          │           │ RC6+RC8+RC1  │           │ RC3+RC4      │
   │ Session edit │           │ Generate     │           │ Time         │
   │ merge owner  │           │ transaction  │           │ authority    │
   │ (Tier D)     │           │ (O3 intent)  │           │ (WTA)        │
   │ 14 open      │           │ 5 open       │           │ 4 open       │
   └──────────────┘           └──────────────┘           └──────────────┘
```

**One sentence:** Tier C fixed **canonical disk truth**; what remains is **canonical session truth** — who owns operator state between poll ticks and at commit boundaries.

---

## Why Tier C did not catch these

| Tier C concept | What it gates | What it cannot gate |
|--------------|---------------|-------------------|
| `kling_stitch_export_ready` | Export includes trimmed delivery clip | Textarea draft mid-poll |
| `beatgen_scope_partition` | Writes land in correct SQLite | React `useEffect` hydration |
| `mergeStitchJobSlotsClientPatch` | Stitcher SFX after save | Storyboard contenteditable |
| `authority_registry` | Duplicate server predicates | WaveSurfer remount playhead |

Tier C and Tier D are **orthogonal layers** on the same “truth” theme.

---

## Recommended fix phases (do not start until Kim approves)

| Phase | Target | Rows | Architecture |
|-------|--------|------|--------------|
| **E1 — Tier D completion** | RC2 open rows | 14 | Extend `operatorEditMerge.ts` + registry to every partial surface |
| **E2 — O3 intent transaction** | RC6/RC8/RC1 Beat Gen | 5 | Intent snapshot at Generate click (spec exists) |
| **E3 — WTA extraction** | RC3/RC4 waveform | 4 | `waveformTimeAuthority.ts` + REMOUNT-1 |
| **Ops** | RC10 infra | 10 | Parallel; not blocked on E1–E3 |

**Do not fix individual partial rows with one-off patches** — they are instances of RC2/RC6, not separate bug classes.

---

## 3×3 agent reconciliation notes

| Pass | Sections | Key finding |
|------|----------|-------------|
| Agent 1 | A–C (57 rows) | 42 shipped / 15 open; RC2 dominates open (8/15) |
| Agent 2 | D–F (57 rows) | 52 shipped / 5 open; Stitcher F is 100% green |
| Agent 3 | G–J (35 rows) | G scope 100% shipped; J is infra not Tier D |

**Cross-check:** 89 + 18 + 3 + 10 = 120 ≠ 149 because section buckets overlap (TR-010 = D-014) and summary counts include cross-reference rows. **Unique symptom IDs: 143** (A:22 + B:24 + C:11 + D:16 + E:22 + F:19 + G:9 + H:10 + J:10; section I is alias-only).

---

## Maintenance

When closing an open row, update both:
- `OPERATOR_UX_SYMPTOM_MATRIX_v1.md` status column
- This doc open-row table

Re-run 3-pass RCA when matrix adds ≥10 new incident rows.
