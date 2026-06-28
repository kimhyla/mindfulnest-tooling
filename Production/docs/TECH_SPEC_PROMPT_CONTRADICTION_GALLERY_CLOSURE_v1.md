# TECH_SPEC — Prompt Contradiction Gate + Gallery Closure Module Fix v1

**Status:** Authoritative  
**Branch:** `fix/prompt-contradiction-gallery-closure`  
**Parent:** `TECH_SPEC_O3_GALLERY_CLOSURE_v1.md`, Truth Stack prompt-box law (`4d4617e`, `b017687`)  
**Closes:** Event_3 resolution Loral beat “No flowers” + Sweetroses hallucination pain; `beat_generator_sidecar` import crash on gallery finalize

---

## Category-unlocker

- **Bug category A:** **Phantom module alias on gallery finalize path** — `refresh_beat_gallery_fields_for_finalize` imports nonexistent `beat_generator_sidecar`; every O3 Element job that hits gallery reconcile raises `ModuleNotFoundError`, surfacing as “O3/lipsync attempt failed” in UI.
- **Category fix A:** Single module authority — use `beat_generator` (same as pipeline + tests). CI grep gate forbids `import beat_generator_sidecar`. Regression test calls `refresh_beat_gallery_fields_for_finalize` under pytest.

- **Bug category B:** **Verbatim prompt self-contradiction** — prompt-box law correctly sends operator text verbatim; partial edits leave negation (“No flowers”) and positive visuals (“blooming Sweetroses”, “wreath behind her”) in one submit. Kling follows positive nouns; operator believes sidecar “overwrote” them.
- **Category fix B:** **Pre-submit contradiction linter** (server fail-closed + UI mirror) — detect known negation/positive pairs before Generate; block with `PROMPT_SELF_CONTRADICTORY` and list conflicting lines. Never auto-rewrite (box law preserved).

- **Fix type:** CATEGORY (both)

---

## 1. Problem evidence (2026-06-27)

| Evidence | Value |
|----------|-------|
| URL | `http://localhost:5113/?event=Event_3&video=resolution` |
| Beat | `bg_arc1_event3_post_beat_03` (UI sidebar Beat 4, Loral) |
| build-sha | `ac11059` (all dedicated ports) |
| Sidecar prompt | Contains both “No flowers” and “blooming Sweetroses in background” |
| Import repro | `ModuleNotFoundError: No module named 'beat_generator_sidecar'` |
| `o3_prompt_box_law` | `true` — verbatim submit working as designed |

---

## 2. Deliverables

| # | Layer | File | Change |
|---|-------|------|--------|
| 1 | Gallery finalize | `o3_gallery_closure.py` | `import beat_generator as bg` only |
| 2 | Test | `tests/test_o3_gallery_closure.py` | `refresh_beat_gallery_fields_for_finalize` smoke |
| 3 | Linter | `beat_generator.py` | `lint_kling_o3_prompt_contradictions()` |
| 4 | Submit gate | `validate_o3_submit_prompt_for_mode()` | Return `PROMPT_SELF_CONTRADICTORY` |
| 5 | UI | `promptContradictionLint.ts` + `BgTab.tsx` | Block Generate with same messages |
| 6 | CI | `verify_beatgen_siblings_durability.sh` | Grep: no `beat_generator_sidecar` import |
| 7 | Tests | `test_prompt_contradiction_lint.py` | Event_3 Loral fixture + clean prompt |

---

## 3. Contradiction rules (v1)

1. **No flowers** negation + any of: `sweetrose`, `sweet-rose`, `blooming`, `wreath`, `flowers in background`, `garden of sweet`
2. **Nothing additional is added** + blooming/wreath/sprout/addition language
3. Messages cite both conflicting phrases; operator must edit prompt manually

Out of scope: auto-strip (violates prompt-box law); Claude author rebuild on save.

---

## 4. Full QA gates

- pytest: `test_o3_gallery_closure.py`, `test_prompt_contradiction_lint.py`
- TS: `promptContradictionLint.test.ts`
- Deploy: mirror → restart `:5113` → build-sha = HEAD
- Browser: hard refresh resolution → Generate on contradictory beat → blocked toast; fix prompt → Generate proceeds
- `verify_beatgen_deploy_smoke.sh 5113`

---

## 5. Sibling categories still open after ship

- O3 heartbeat during long Kling waits
- Auto author `scene_notes` footer injection on extract (source of legacy Sweetrose lines — operator must delete)
- Truth Stack S9 all-port smoke automation
