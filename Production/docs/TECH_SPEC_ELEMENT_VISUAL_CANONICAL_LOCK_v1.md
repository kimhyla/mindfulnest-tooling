# Element Visual Canonical Lock v1

**Status:** Shipped — 2026-07-04  
**Marker:** `ELEMENT_VISUAL_CANONICAL_LOCK_V1`  
**Parent registry:** `STORYBOARD_AUTHORITY_REGISTRY_v1.md`  
**Supersedes (partial):** `TECH_SPEC_ELEMENT_CHAR_REF_AUTHORITY_v1.md` — auto-promote on Generate / Add to Element  
**Durability gate:** `Production/scripts/verify_element_visual_canonical_lock_durability.sh`

---

## Problem (causeless cause)

Kling Element **visual identity** was path-based and mutable across three stores:

1. Beat `reference_image.abs_path`
2. Registry `frontal_image` (Element frontal)
3. Registry `refer_images[]`

There was **no byte-level lock**. Silent auto-promotion on char-ref drop / O3 submit could overwrite `frontal_image` with the wrong PNG (e.g. gray `benson_pose_neutral.png` instead of tan `baseline_char_rabbit_gardener.png`). Deploy copies tooling → server but **never** overwrites Dropbox `character_subjects.json` — runtime registry drift persisted across restarts.

**Patch scripts are rejected.** One-off heal/re-point PNG scripts do not clear the bug class.

---

## Intended operator workflow

| Action | Effect |
|--------|--------|
| **Drop char ref on beat** | Beat-local ref only; reconcile if bytes already in poses dir, else **Add to Element** (refer only) |
| **Add to Element** | Copy pose → `Production/<Char>/poses/`; append to `refer_images`; re-register Element; **does not change `frontal_image`** |
| **Set as Element identity** (confirm modal) | **Sole write path** for `frontal_image` + `frontal_sha256`; locks beat ref; re-registers Element |
| **Generate O3** | Never silently changes Element frontal identity |

---

## 4×4 agent debate (simplicity-producing consensus)

### Architecture agent

**Proposal:** Stamp `frontal_sha256` at every identity write; verify on read via `verify_frontal_sha256`. Only `set_element_identity()` may assign `frontal_image`. Remove `promote_frontal` from `add_element_pose` and from `try_register_dropped_char_ref_on_element`.

**Verdict:** Accept — single write gate + sha equality is simpler than filename heuristics or per-speaker patch scripts.

### Blast-radius agent

**Concerns:** Existing active characters without sha; approved O3 videos baked with old identity; Library Add to Element; auto-register on drop; `resolve_frontal_abs_path` strict mode.

**Mitigations:**

- Lazy sha migration on `load_character_subjects` for `status==active` (no frontal overwrite).
- Fail-closed: sha mismatch → `ElementVisualCanonicalError` on strict reads.
- `add_element_pose` / drop reconcile: refer-only forever.
- Existing approved clips unchanged until regen — expected, documented.
- New API `POST /api/bg/set-element-identity` + BgTab confirm modal.

**Verdict:** Accept with lazy migration + explicit operator identity path.

### Operator UX agent

**Proposal A:** Add to Element = refer-only (green button).  
**Proposal D:** Separate **Set as Element identity** (amber button + confirm modal).  
**Reject:** Silent promote on Generate; `promote_frontal: true` in UI.

**Verdict:** A+D — two explicit buttons; identity change always requires confirmation.

### QA agent

**Proposal:** Sha-equality verify (not filename grep); generalize durability script by speaker; delete one-off `heal_benson_*` scripts; pytest for `set_element_identity`, refer-only `add_element_pose`, and drop path without promote.

**Verdict:** Accept — `verify_element_visual_canonical_lock_durability.sh` + `test_element_visual_canonical_lock.py`.

---

## Authority contract

| Field | Authority |
|-------|-----------|
| `frontal_image` | Set only by `set_element_identity()` |
| `frontal_sha256` | Stamped at identity write; verified on read |
| `refer_images` | `add_element_pose`, `set_element_identity`, reconcile |
| Beat `reference_image` | Operator drop / align; locked on identity set |

**Read gate:** `verify_frontal_sha256(cfg)` → used by `resolve_frontal_abs_path(strict=True)`  
**Write gate:** `set_element_identity(character, source_abs_path, wavespeed_key)`

---

## API

### `POST /api/bg/set-element-identity`

Body: `{ beat_id?, speaker?, abs_path? }` — beat supplies speaker/path when present.

Response: `{ ok, pose_rel, frontal_sha256, element_id, element_char_ref_ok?, thumb_b64? }`

Errors: `409 ELEMENT_VISUAL_CANONICAL_ERROR` on stamp failure.

### `POST /api/bg/add-element-pose` (unchanged route, changed semantics)

No `promote_frontal` parameter. Refer-only.

---

## Files

| Layer | File |
|-------|------|
| Registry | `Production/tools/kling_character_registry.py` |
| Drop path | `Production/tools/beat_generator.py` → `try_register_dropped_char_ref_on_element` |
| HTTP | `Production/tools/server_handlers/background.py` |
| UI | `Production/tools/storyboard-v2/src/components/BgTab.tsx` |
| Durability | `Production/scripts/verify_element_visual_canonical_lock_durability.sh` |
| Tests | `Production/tools/tests/test_element_visual_canonical_lock.py` |

**Deleted (patch class):** `Production/scripts/heal_benson_element_frontal_authority.py`, `verify_benson_element_frontal_authority.sh`

---

## Operator proof (post-deploy)

1. Hard refresh Beat Gen (Event port).
2. On Benson beat with desired char ref: click **Set as Element identity** → confirm.
3. Verify registry: `frontal_sha256` matches PNG bytes on disk.
4. Regen one beat — video identity matches pinned art.
5. **Add to Element** with a different pose does not change `frontal_image`.

---

## Non-goals

- Rewriting already-approved O3 delivery MP4s in place.
- Deploy-time overwrite of Dropbox `character_subjects.json`.
- Filename-based canonical selection (`benson_pose_neutral` vs `baseline_char_rabbit_gardener` heuristics).
