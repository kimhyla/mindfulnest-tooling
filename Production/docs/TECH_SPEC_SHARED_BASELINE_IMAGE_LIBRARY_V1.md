# TECH_SPEC — Shared Baseline Image Library V1

**Status:** Ready to implement  
**Branch:** `feat/shared-baseline-image-library-v1` (proposed)  
**Extends:** `Production/lib/event_library.py`, `Production/tools/server_handlers/cropper.py`  
**Supersedes (partially):** per-event-only library visibility for Kim’s curated BG still set; does **not** revert `ed05205` canonical-tier UI removal  
**Related LDs / prior work:** `migrate_per_event_library.py` (Jun 2026), `826c9cd` (`apply_to_all_events`), `ed05205` (canonical removed from library grid), `b5104ac` (metadata-only list + on-demand thumbs)

---

## 1. Purpose

Kim’s **18 curated Event_3 source stills** (uploaded 2026-06-26) must appear in the **Images library panel** on **every Event_N, every milestone scope, every dedicated server port** — without re-uploading per event.

Today each event only lists files under its own `Event_N/library/images/sources/`. Event_3 has 18 sources; Event_1 has 59; Event_4 has 5 (manual one-off copy). The old `Production/canonical_images/` + `canonical_image_registry.json` set (7 intro/Element contract images) is **intentionally excluded** from `GET /api/cr/library` since 2026-06-23 and **must stay excluded** (`tier: canonical` is smoke-forbidden).

This spec introduces a **shared baseline image library** — same architectural pattern as `Production/assets/sound_library/` (global folder, merged at list time, delete-protected, single source of truth on Dropbox).

---

## 2. Causeless cause

> **Kim’s approved BG still set was stored per-event, while the UI merged global tiers (Element poses, Character_Assets) without a global still baseline.**  
> New events bootstrapped empty dirs only (`ensure_event_library_dirs`). Canonical registry injection was removed from the library grid to stop clutter/confusion. Result: “empty library” on new events and “randomized” feeling from Element pose auto-scan.

---

## 3. Invariant (SHARED_BASELINE_IMAGE_LIBRARY_V1)

| Layer | Role |
|-------|------|
| **`Production/assets/image_library/baseline/`** | **Sole authority** for Kim’s shared BG still bytes (16 images after contamination cleanup — see §8) |
| **`Production/baseline_image_registry.json`** | Metadata: stable `key`, `filename`, `display_name`, `tags`, optional `source_note` |
| **`Event_N/library/images/sources/`** | **Event-local uploads only** — unchanged semantics |
| **`Production/canonical_images/`** | **Intro/Element contract** — unchanged; still excluded from library grid |
| **`GET /api/cr/library`** | Merges **Tier 0 baseline** + existing tiers; baseline rows use `tier: "source"`, `shared_baseline: true`, `tags` includes `"baseline"` |
| **Delete** | Baseline paths return `403 BASELINE_IMAGE_PROTECTED` (mirror `CANONICAL_IMAGE_PROTECTED`) |
| **Path resolution** | `library_image_roots()` + `resolve_library_image_path()` include baseline dir |

### 3.1 What we explicitly do NOT do

| Banned | Reason |
|--------|--------|
| Re-inject `tier: "canonical"` into `cr_library` | Removed in `ed05205`; UI filters it; `smoke_per_event_library.sh` fails if present |
| Copy baseline PNGs into every `Event_N/library/` | Drift, duplication, milestone skeleton mismatch |
| Expand `canonical_images/` with BG stills | That folder is intro/Element contract; different lifecycle |
| `shutil.copy2` heal into `library/sources/` | `test_library_sources_immutable.py` regression class |
| Per-event upload on `event/create` | Operator burden; violates “use without reloading” |

---

## 4. Repro evidence (pre-fix — captured 2026-06-27)

### 4.1 API — Event_3 dedicated server `:5113`

```bash
curl -s "http://localhost:5113/api/cr/library?event_id=Event_3" | python3 -m json.tool
```

| Metric | Value | Evidence |
|--------|-------|----------|
| Total library rows | 37 | curl body 2026-06-27 |
| `tier: source` | 18 | Event_3 uploads only |
| `tier: element_pose` | 19 | Auto-scanned from `Production/<Char>/poses/` |
| `tier: canonical` | 0 | Post-`ed05205` — not injected |
| Contaminated sources | 2 | `element_pose_contaminated: true` on filenames below |

**Contaminated files (exclude from baseline seed):**

- `ChatGPT Image Jun 3, 2026, 04_49_48 PM (3).png` — API flag + `contamination_warning`
- `ChatGPT Image Jun 14, 2026, 04_36_22 AM.png` — API flag + `contamination_warning`

### 4.2 Cross-event source counts (same date)

| Event | Port | Source count | Notes |
|-------|------|--------------|-------|
| Event_1 | 5111 | 59 | Accumulated uploads + probes |
| Event_2 | 5112 | 38 | Per-event only |
| Event_3 | 5113 | 18 | Kim’s curated set (today) |
| Event_4 | 5114 | 5 | Manual parity copy (`826c9cd` era) |

### 4.3 Disk — baseline does not exist yet

```text
Production/assets/image_library/baseline/     → MISSING (to create)
Production/baseline_image_registry.json       → MISSING (to create)
Production/canonical_images/                  → 7 files (intro contract — keep separate)
```

### 4.4 Code — canonical excluded from library list

`Production/tools/server_handlers/cropper.py` `handle_cr_library` docstring (lines ~338–339):

> Canonical registry images are intentionally excluded — use canonical_images/ directly, not the event/milestone library panel.

`Production/scripts/smoke_per_event_library.sh` (lines 51–52): asserts no `tier == "canonical"` in list payload.

---

## 5. Baseline seed set (16 images)

Source of truth for bytes: **`Event_3/library/images/sources/`** on Dropbox (uploaded 2026-06-26).  
Stable filenames under `baseline/` — registry holds display names.

| Stable key / filename | Source file (Event_3) | Notes |
|----------------------|------------------------|-------|
| `baseline_still_01.png` | `ChatGPT Image Jun 3, 2026, 01_01_45 PM (5).png` | |
| `baseline_still_02.png` | `ChatGPT Image Jun 3, 2026, 04_27_01 PM.png` | |
| `baseline_still_03.png` | `ChatGPT Image Jun 3, 2026, 02_11_45 PM.png` | |
| `baseline_still_04.png` | `ChatGPT Image Jun 3, 2026, 02_11_02 PM (2).png` | |
| `baseline_still_05.png` | `ChatGPT Image Jun 3, 2026, 05_18_14 PM (3).png` | |
| `baseline_still_06.png` | `ChatGPT Image Jun 3, 2026, 03_05_28 PM.png` | |
| `baseline_still_07.png` | `ChatGPT Image Jun 3, 2026, 02_49_28 PM.png` | |
| `baseline_still_08.png` | `ChatGPT Image Jun 2, 2026, 12_50_43 PM.png` | |
| `baseline_still_09.png` | `ChatGPT Image Jun 25, 2026, 03_05_40 PM (1).png` | |
| `baseline_still_10.png` | `40edc382-c44c-4a0b-a9bc-6a6147e60ad3.png` | UUID upload |
| `baseline_still_11.png` | `ChatGPT Image Jun 3, 2026, 12_03_16 PM (1).png` | |
| `baseline_still_12.png` | `ChatGPT Image Jun 26, 2026, 09_55_36 PM.png` | |
| `baseline_still_13.png` | `ChatGPT Image Jun 26, 2026, 09_55_24 PM.png` | |
| `baseline_still_14.png` | `ChatGPT Image Jun 26, 2026, 09_55_12 PM.png` | |
| `baseline_still_15.png` | `ChatGPT Image Jun 26, 2026, 09_55_00 PM.png` | |
| `baseline_still_16.png` | `ChatGPT Image Jun 26, 2026, 09_50_51 PM.png` | |

**Excluded from baseline (contamination cleanup):**

| File | Action |
|------|--------|
| `ChatGPT Image Jun 3, 2026, 04_49_48 PM (3).png` | Do not seed; delete from Event_3 `sources/` after baseline live (or replace with clean original if Kim has one) |
| `ChatGPT Image Jun 14, 2026, 04_36_22 AM.png` | Same |

Seed script must **verify SHA256 ≠ any Element pose** under `Production/*/poses/` before copying (reuse `kling_character_registry.file_sha256` pattern from `handle_cr_library` contamination scan).

---

## 6. Registry schema

**Path:** `Production/baseline_image_registry.json` (tooling repo + Dropbox mirror)

```json
{
  "version": 1,
  "id": "event3_curated_baseline_v1",
  "apply_to_all_events": true,
  "images": [
    {
      "key": "baseline_still_01",
      "filename": "baseline_still_01.png",
      "display_name": "Baseline still 01",
      "tags": ["baseline", "shared", "location"],
      "source_note": "Event_3 upload 2026-06-26 — ChatGPT Image Jun 3 01_01_45 PM (5)"
    }
  ]
}
```

Tracked in `Production/lib/production_snapshot.py` `GLOBAL_FILES` alongside `canonical_image_registry.json`.

---

## 7. Implementation map

| File | Change |
|------|--------|
| **`Production/lib/event_library.py`** | Add `baseline_images_dir()`, `baseline_registry_path()`, `load_baseline_registry()`, `list_baseline_meta()`, `is_baseline_image_path()`; extend `library_image_roots()` + `resolve_library_image_path()` |
| **`Production/tools/server_handlers/cropper.py`** | **Tier 0** in `handle_cr_library` (before sidecar scan): iterate registry → baseline dir; emit `tier: "source"`, `shared_baseline: true`, `asset_type: "still_master"` optional; `_append` with dedupe by key. Extend `handle_cr_library_delete` + `handle_cr_upload` guards for baseline paths |
| **`Production/scripts/seed_baseline_image_library.py`** | One-time + idempotent: copy 16 Event_3 sources → baseline/ with stable names; write registry; SHA256 gate vs Element poses; `--dry-run` |
| **`Production/scripts/cleanup_contaminated_library_sources.py`** | Delete the 2 contaminated Event_3 files (and optionally same-name copies on Event_1/2/4 if hash match); `--dry-run` |
| **`Production/tools/tests/test_baseline_image_library.py`** | Unit: registry load, path roots, list injection, delete 403, milestone scope sees baseline, dedupe vs event source same key |
| **`Production/tools/tests/test_milestone_cr_library.py`** | Extend: milestone on Event_2 server lists baseline rows from global dir |
| **`Production/scripts/verify_baseline_image_library_durability.sh`** | Source guards + pytest + live smoke (§10) |
| **`Production/scripts/verify_tooling_dropbox_parity.py`** | Add `Production/lib/event_library.py`, `Production/baseline_image_registry.json` to `REGISTRY_COMPARE_PATHS`; add `cropper.py` already in CODE_PARITY |
| **`Production/lib/production_snapshot.py`** | Add `baseline_image_registry.json` to `GLOBAL_FILES` |
| **`Production/tools/storyboard-v2/src/components/LibraryPanel.tsx`** | (Optional Phase B) Badge/filter: `shared_baseline` chip; filter “Baseline / My uploads / All”. **Not required for V1 ship** if baseline rows appear in Images tab with `display_name` |
| **`Production/scripts/deploy_storyboard_v59.sh`** | No change required unless UI Phase B ships |

### 7.1 Tier 0 list row shape (server contract)

```json
{
  "key": "baseline_still_01",
  "filename": "baseline_still_01.png",
  "tier": "source",
  "abs_path": "/…/Production/assets/image_library/baseline/baseline_still_01.png",
  "thumb_url": "/api/cr/thumb?abs_path=…",
  "display_name": "Baseline still 01",
  "tags": ["baseline", "shared", "location"],
  "shared_baseline": true,
  "asset_type": "still_master",
  "is_master": true,
  "has_crop": false
}
```

**Dedup rule:** If an event-local `sources/` file has the same stem as a baseline key, **event-local wins** (append baseline first, then event sources skip seen keys — or append event first; **choose event-local wins**: scan event sources first, then baseline only for keys not in `seen_keys`).

Recommended order in `handle_cr_library`:

1. Tier 0 baseline (registry order)  
2. Tier 1 sidecar accepted stills  
3. Tier 1b event sources  
4. Tier 2 crops  
5. Tier 3 character_master  
6. Tier 3b element_pose  
7. Tier 4 watercolors  

### 7.2 Delete protection

Mirror `is_canonical_image_path` check in `handle_cr_library_delete`:

```python
if abs_path_hint and is_baseline_image_path(abs_path_hint, prod_root):
    return 403 BASELINE_IMAGE_PROTECTED
```

Also reject delete glob hits under `baseline_images_dir`.

---

## 8. Immediate cleanup (mandatory in same PR)

### 8.1 Contaminated library sources

**Category:** Element-byte overwrite of user library uploads (closed class in `test_library_sources_immutable.py`; these are legacy artifacts).

| Step | Action |
|------|--------|
| 1 | Run cleanup script with `--dry-run`; print SHA256 + matching Element path if any |
| 2 | Delete contaminated files from `Event_3/library/images/sources/` |
| 3 | Grep Dropbox for same basename on Event_1/2/4; delete only if SHA256 matches contaminated hash |
| 4 | Re-GET `/api/cr/library?event_id=Event_3` — contaminated flags must be 0 |
| 5 | **Do not** add these two files to baseline seed |

### 8.2 Operator note

If Kim needs those two scenes in the library, re-upload clean PNGs to **event-local** sources (not baseline) until reviewed for Element hash collision.

---

## 9. Blast radius

| Change | Impact | Mitigation |
|--------|--------|------------|
| +16 global baseline tiles on every library list | JSON payload size | Metadata-only list + on-demand thumbs (`b5104ac`); smoke asserts list `< 250KB`; baseline adds ~16 rows ≈ safe |
| Baseline visible on all events | Event_1 list grows by ≤16 (deduped) | Dedupe by key; Event_1 keeps its 59 local uploads |
| Milestone scope | Baseline global — works on skeleton `library_event_dir` | Test `scope_milestone_id=milestone1_arc1` |
| Delete mis-click on baseline | Data loss | 403 + no delete button disable in UI (optional: hide ✕ on `shared_baseline` tiles — Phase B) |
| Path confinement / cropper | Baseline dir must be in approved roots | Extend `library_image_roots()`; test thumb + full serve |
| Dropbox sync | New folder under `assets/` | Seed script writes to Dropbox; parity script verifies |
| Confusion with `canonical_images/` | Two global image systems | Docs + tags; canonical stays out of grid; baseline uses `tier: source` |
| Element pose clutter unchanged | Still ~19 pose tiles | **Out of scope V1** — optional Phase C: filter poses out of Images tab default |

**Out of scope V1:** Hiding Element poses from Images tab; prod_assets Directus registration for baseline rows; auto-seed on `event/create` (baseline is global — new events need no copy).

---

## 10. Multipass proof plan (mandatory — no heal-before-proof)

### Pass 0 — Category-unlocker (before any code)

```markdown
## Category-unlocker
- **Bug category:** Per-event library isolation — no global BG still baseline; new events appear empty; Kim re-uploads same assets.
- **Category fix:** Shared baseline directory + registry + Tier 0 merge in cr_library + path roots + delete guard + seed/cleanup scripts + durability gates.
- **Fix type:** CATEGORY
- **Plan:** See §10 passes 1–7; commit on feature branch; deploy all affected ports.
```

### Pass 1 — Repro (cold, before edit)

Record and attach to PR:

- [ ] `curl -s http://localhost:5113/api/cr/library?event_id=Event_3` → save JSON; count source=18, contaminated=2  
- [ ] `curl -s http://localhost:5114/api/cr/library?event_id=Event_4` → count source=5, baseline keys absent  
- [ ] `curl -s http://localhost:5111/` → extract `build-sha` meta  
- [ ] Screenshot: Event_3 library Images tab — sparse vs Event_1 (browser, hard refresh)

### Pass 2 — Unit tests

```bash
cd ~/Projects/mindfulnest-tooling
python3 -m pytest \
  Production/tools/tests/test_baseline_image_library.py \
  Production/tools/tests/test_milestone_cr_library.py \
  Production/tools/tests/test_event_library_scoping.py \
  Production/tools/tests/test_cr_library_metadata_only.py \
  Production/tools/tests/test_library_sources_immutable.py \
  -q
```

All green before deploy.

### Pass 3 — Seed + cleanup (Dropbox)

```bash
python3 Production/scripts/seed_baseline_image_library.py --dry-run
python3 Production/scripts/seed_baseline_image_library.py
python3 Production/scripts/cleanup_contaminated_library_sources.py --dry-run
python3 Production/scripts/cleanup_contaminated_library_sources.py
```

Verify:

- [ ] 16 files under `Dropbox/…/Production/assets/image_library/baseline/`  
- [ ] `baseline_image_registry.json` present tooling + Dropbox  
- [ ] Contaminated Event_3 files gone  

### Pass 4 — Mirror tooling → Dropbox + parity

```bash
# deploy_storyboard_v59.sh rsyncs tooling → Dropbox (or manual rsync per operator workflow)
python3 Production/scripts/verify_tooling_dropbox_parity.py
# exit 0 on CODE_PARITY_PATHS; baseline registry in REGISTRY_COMPARE (warn ok pre-seed, strict after)
MN_REGISTRY_PARITY_STRICT=1 python3 Production/scripts/verify_tooling_dropbox_parity.py
bash Production/scripts/verify_baseline_image_library_durability.sh
bash Production/scripts/verify_per_event_library_durability.sh
```

### Pass 5 — Deploy + restart (all ports Kim uses)

For each port in `{5111, 5112, 5113, 5114}`:

```bash
bash Production/scripts/deploy_storyboard_v59.sh --event Event_N   # or fanout per deploy script
curl -s -X POST "http://localhost:PORT/api/server/restart"
curl -s -o /dev/null -w '%{http_code}' "http://localhost:PORT/"   # → 200
curl -s "http://localhost:PORT/" | sed -n 's/.*name="build-sha" content="\([^"]*\)".*/\1/p'
git rev-parse --short HEAD   # must match served build-sha
```

Dedicated-port recovery (Part 3 G):

- If `:5112` (or any dedicated port) not HTTP 200 within 60s after restart API → relaunch from Dropbox per `verify_beatgen_deploy_smoke.sh` pattern; re-proof.

### Pass 6 — API proof (post-deploy, no manual heal)

| Check | Command | Expected |
|-------|---------|----------|
| Event_3 baseline present | `curl -s :5113/api/cr/library?event_id=Event_3 \| jq '[.images[] \| select(.shared_baseline==true)] \| length'` | `16` |
| Event_4 baseline present | same on `:5114` | `16` |
| Event_1 dedupe | `:5111` — baseline keys present; local uploads still present | source count ≥ 59 + baseline (minus dedupes) |
| No canonical tier | all ports | zero `tier=="canonical"` |
| Contamination gone | Event_3 | zero `element_pose_contaminated` on remaining sources |
| Milestone scope | `curl -s :5112/api/cr/library?scope_milestone_id=milestone1_arc1` | baseline ≥ 16 |
| Delete guard | POST `/api/cr/library/delete` with baseline `abs_path` | `403 BASELINE_IMAGE_PROTECTED` |
| Thumb | GET first baseline `thumb_url` | HTTP 200, JPEG |
| Full image | GET `/api/cr/full?abs_path=…` | 200 + data_uri |
| Scope A | `/api/event/current` on dedicated port matches URL event | event_id = Event_N |
| Scope A dedicated 409 | POST `event/load` wrong event on `:5112` | `409 DEDICATED_PORT_PIN_IMMUTABLE` |

### Pass 7 — Browser visual proof (Kim perspective — mandatory)

Use cursor-ide-browser MCP or manual; **hard refresh** same URL before judging.

| # | URL | Visual acceptance |
|---|-----|-------------------|
| 1 | `http://localhost:5113/?event=Event_3` | Images tab shows 16 baseline tiles + Event_3 local uploads; **no** contaminated warning chips on remaining tiles |
| 2 | `http://localhost:5114/?event=Event_4` | Same 16 baseline tiles visible without re-upload |
| 3 | `http://localhost:5112/?event=Event_2&scope_milestone_id=milestone1_arc1&…` | Milestone scope: baseline tiles visible |
| 4 | Drag baseline tile → Beat Gen `@Image1` or cropper drop | Thumbnail resolves; no 403 |
| 5 | Hard refresh repeat on (1) and (2) | Tiles persist (proves server-side, not client cache only) |
| 6 | Screenshot saved to `.runtime_baseline_library_qa/` for deliverable | |

**Not required for this task (no Generate touch):** Pass C in-flight O3/Avatar Pro checklist — skip unless implementation accidentally touches Generate handlers.

### Pass 8 — Beat Gen deploy smoke (Part 3 B — run when server touched)

```bash
bash Production/scripts/verify_beatgen_deploy_smoke.sh 5112
bash Production/scripts/verify_beatgen_deploy_smoke.sh 5113
```

- [ ] `PRAGMA integrity_check` ok on `~/.mindfulnest/state/beatgen.db`  
- [ ] Milestone `session-state` beats ≥ 1, no disk I/O error  

### Pass 9 — Commit + PR

- [ ] Commit on `feat/shared-baseline-image-library-v1`  
- [ ] `gh pr create` with Full QA report (§12 template)  
- [ ] Never Bugbot / Find Issues  

---

## 11. 3×3 debate summary

| Agent | Position | Resolution |
|-------|----------|------------|
| **A1 Server** | Global folder + Tier 0 merge in existing `cr_library` | **Adopt** — smallest diff, matches sound_library |
| **A2 Server** | Re-inject old `tier: canonical` | **Reject** — tests + UI forbid; confuses intro contract |
| **A3 Server** | Copy files to every Event_N on create | **Reject** — drift class (Event_4 already diverged) |
| **B1 Client** | Separate API `/api/cr/baseline_library` | **Reject** — LibraryPanel already merges stitch audio; one list is simpler |
| **B2 Client** | Hide delete on `shared_baseline` | **Defer Phase B** — server 403 is sufficient V1 |
| **B3 Client** | Filter Element poses from Images tab | **Defer Phase C** — separate clutter category |
| **C1 QA** | Seed script SHA256 gate vs Element poses | **Adopt** — prevents repeat contamination |
| **C2 QA** | Browser drag-drop proof mandatory | **Adopt** — Kim’s success criterion |
| **C3 QA** | Multipass on 5111–5114 | **Adopt** — dedicated ports are production workflow |

**Verdict:** Shared `assets/image_library/baseline/` + registry + Tier 0 server merge + cleanup + full multipass including browser.

---

## 12. Deliverable report template (implementation PR)

```markdown
## Full QA — Shared Baseline Image Library V1

**Root cause:** Per-event `library/images/sources/` isolation with no global BG baseline tier; canonical registry removed from grid in ed05205; new events empty. (Evidence: §4 repro curls.)

**Category fix:** `SHARED_BASELINE_IMAGE_LIBRARY_V1` — global baseline dir + registry + Tier 0 cr_library merge + path roots + delete guard.

**Proof:**
- Repro: §4 JSON archived
- Unit: pytest test_baseline_image_library.py … (paste output)
- Smoke: verify_baseline_image_library_durability.sh exit 0
- API: Event_3/4 baseline count=16; delete 403; no canonical tier
- Deploy: build-sha = `<sha>` on ports 5111–5114
- Browser: screenshots in `.runtime_baseline_library_qa/` — hard refresh ×2

**Commit:** `<sha>` on `feat/shared-baseline-image-library-v1`

**Sibling categories still open:**
- Element pose clutter in Images tab (Phase C)
- Event_1/2/4 local duplicates of baseline scenes (harmless dedupe; optional prune)
```

---

## 13. Taxonomy pass (mandatory before closing implementation)

### 13.1 Primary bug category

**Global-vs-scoped library asset visibility** — curated BG stills scoped per-event while other library tiers (Element poses, sound_library) are global or auto-merged.

### 13.2 Sibling bugs (same category)

| Sibling | Location | Status after V1 |
|---------|----------|-----------------|
| Event_4 manual 5-image parity | `Event_4/library/sources/` | Baseline supersedes need; local copies optional prune |
| Empty library on `event/create` | `event_video.py` `ensure_event_library_dirs` only | **Closed** for baseline (global); local still empty until upload |
| Watercolors per-event only | `library/watercolors/` | **Open** — different asset class |
| Legacy `beat_generator_stills/` path refs | grep `BG_STILLS_DIR` | **Open audit** — not in V1 scope |

### 13.3 Parallel categories (different truth layers)

| Category | Layer |
|----------|-------|
| Element-byte library contamination | Hash collision / heal overwrite |
| `canonical_images/` intro contract | Template hydrate, not library grid |
| prod_assets Directus registration | Metadata enrichment (`_enrich_library_items_prod_assets`) |
| Client tier filter hiding canonical | UI filter in `LibraryPanel.tsx` TIER_TO_FILTER_MAP |

### 13.4 Underlying chain (3 whys)

1. **Why empty Event_3?** — Only files in `Event_3/library/sources/` list; no global baseline.  
2. **Why no global baseline?** — Migration moved stills to Event_1-only; canonical set was 7 intro images, later removed from grid.  
3. **Why remove canonical from grid?** — Clutter + milestone scope refactor (`ed05205`); intro images still resolved by path for templates.

### 13.5 Missing gates that would have caught this earlier

| Gate | Would catch |
|------|-------------|
| `verify_baseline_image_library_durability.sh` | Missing global baseline on Event_4+ |
| Cross-event library count floor in CI | Event_N < baseline minimum |
| Browser library tile count snapshot | Kim-visible empty library |

### 13.6 What remains open after V1

- Element pose tiles mixed into Images tab default view  
- Optional UI: baseline badge, hide delete on shared rows  
- Optional: prod_assets rows for baseline stills  
- Prune duplicate per-event copies of baseline scenes on Event_1/2/4  
- Watercolor global baseline (if Kim wants parity with sound_library later)

---

## 14. Part 3 durability gates (library/server touch)

| Gate | Applies? | Action |
|------|----------|--------|
| **A. Milestone SQLite** | Low — library list only | Confirm `init_bg_paths(milestone_dir=…)` still never calls `bootstrap_sqlite_sidecar_from_json`; no change expected |
| **B. Deploy smoke** | Yes | Run `verify_beatgen_deploy_smoke.sh` on 5112 + 5113 after deploy |
| **C. Dual-server DB** | No change | Document if beatgen.db shared across ports |
| **D. Recovery hardening** | No change | |
| **E. O3 job event-dir resolver** | No touch | Skip Generate proofs unless scope creep |
| **F. Cross-surface parity sweep** | Yes | Grep `library_image_roots`, `resolve_library_image_path`, `event_images_sources_dir` for handlers that build ref paths — ensure baseline dir included (cropper full/thumb, background ref drop, O3 intent snapshot if reads library paths) |
| **G. Dedicated-port restart** | Yes | §10 Pass 5 — all four ports HTTP 200 + build-sha |

### 14.1 Cross-surface grep checklist (implementation)

```bash
rg -l 'library_image_roots|resolve_library_image_path|event_images_sources_dir' Production/
```

Every consumer that resolves user BG still paths must find baseline keys. Minimum files to verify in tests:

- `server_handlers/cropper.py` (list, thumb, full, delete, upload guard)
- `lib/event_library.py` (roots + resolve)
- `server_handlers/background.py` (beat ref / image drop) — read-only audit; add test if gap found

---

## 15. Implementation order (single PR)

1. `event_library.py` helpers + tests (no server behavior yet)  
2. `seed_baseline_image_library.py` + run on Dropbox  
3. `cleanup_contaminated_library_sources.py` + run  
4. `cropper.py` Tier 0 + delete guard  
5. `production_snapshot.py` + parity script paths  
6. `verify_baseline_image_library_durability.sh`  
7. Full multipass §10  
8. Browser screenshots + Full QA report  
9. Commit + PR  

---

## 16. Rollback

| Step | Rollback |
|------|----------|
| Server code | Revert commit; redeploy; restart |
| Baseline files on Dropbox | Leave in place (harmless) or delete `assets/image_library/baseline/` + registry |
| Event_3 cleanup | Restore from Dropbox version history if needed |

---

## 17. Acceptance criteria (ship gate)

- [ ] 16 baseline images on disk + registry in tooling and Dropbox  
- [ ] 2 contaminated Event_3 sources removed  
- [ ] `GET /api/cr/library` returns 16 `shared_baseline: true` on Event_3, Event_4, Event_1, milestone scope  
- [ ] Zero `tier: canonical` in library list (smoke passes)  
- [ ] Baseline delete returns 403  
- [ ] Drag baseline → beat ref works in browser  
- [ ] `build-sha` = git HEAD on 5111–5114 after deploy  
- [ ] Browser hard-refresh proof with screenshots  
- [ ] pytest + durability scripts exit 0  
- [ ] Commit + PR with Full QA report  

---

*End of spec.*
