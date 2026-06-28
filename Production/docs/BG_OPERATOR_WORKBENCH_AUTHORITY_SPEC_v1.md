# Beat Gen — Operator Workbench Authority Spec v1

**Status:** Implemented — 2026-06-20 (`feat/bg-job-truth-complete`)  
**Owner:** mindfulnest-tooling (`Production/tools/`, `storyboard-v2/`)  
**Amends:** `BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1.md` (extends read-only GET + job_busy to operator visuals)

**User-facing promise:** What you drop in Beat Gen **stays visible** after builds and refresh; still scene, char ref, BG ref, prompts, and gallery slots all read from **one resolver per concept** — never from parallel client heuristics.

---

## 1. Concepts and authorities

| Concept | Persisted (disk) | Derived on GET (`beat._derived`) |
|---------|------------------|----------------------------------|
| Still scene (Ken Burns source) | `accepted_library_ref`, `gpt_options[0]`, `bg_ref_image` — kept in sync by `write_still_scene_source()` | `still_scene_display` |
| Char ref (Element / pose) | `reference_image` (+ lock) | `char_ref_display` (includes implicit Element default path) |
| BG ref (O3 motion backdrop) | `bg_ref_image` (+ lock) | `bg_ref_display` (includes segment default) |
| Generation mode | `pipeline`, `beat_render_mode`, `o3_generate_mode` | `generation_mode` |
| Prompt textarea | Mode-specific stored fields | `display_prompt` — **never overwrite** `kling_o3_prompt` on GET |
| Gallery slots | `kling_o3_options[]` | `option_slots[3]` from `normalize_kling_o3_option_slots` |
| Element char gate | sidecar fields | `element_char_ref_ok` recomputed each GET |
| Job busy | terminal + pointer + subprocess + still-render registry | `job_busy` |

Still+TTS beats intentionally show **two** images: `still_scene_display` (forest/library still) and `char_ref_display` (Element pose for TTS).

---

## 2. Resolver chain (single source)

`operator_workbench_contract.resolve_beat_still_scene_abs_path`:

1. `accepted_library_ref.abs_path`
2. `gpt_options[].local_path|abs_path`
3. `flux_options[]` (legacy)
4. `bg_ref_image`, `reference_image`, frame refs

Render, magic_still, and UI **must** use this chain — not parallel client copies.

---

## 3. Write paths

| Action | Function | Fields written (still_insert) |
|--------|----------|-------------------------------|
| Library drop (option tile or BG ref) | `write_still_scene_source()` | `accepted_library_ref`, `gpt_options[slot]`, `bg_ref_image`, `accepted_image_key` |
| Char ref drop | existing `update-beat` | `reference_image` only |
| Still render write-back | includes still-source snapshot fields | provenance preserved |

---

## 4. Session GET

- Beats returned **as on disk** for operator fields.
- `_derived` block attached per beat — thumbs, display refs, slots, prompts.
- No in-memory heal of `kling_o3_prompt`, approval status, or gallery rows on GET.
- One-time persist migration via `_migrate_sidecar` / `migrate_operator_workbench_beat`.

---

## 5. Job busy

- `beat_job_busy` + in-flight still render registry (`_STILL_RENDER_BUSY`).
- Client gates all ref/library/pipeline mutations on `job_busy` only.
- Error code: `BEAT_JOB_BUSY` (alias `INTENT_JOB_ACTIVE` for compat).

---

## 6. Still+TTS option row

When `generation_mode === still_insert` and videos exist:

- BG ref slot shows `still_scene_display`.
- Option row shows server `option_slots` (videos only).
- Source still never hidden — always in BG ref / `still_scene_display`.
