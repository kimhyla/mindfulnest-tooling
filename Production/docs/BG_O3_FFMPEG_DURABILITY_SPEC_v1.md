# BG O3 FFmpeg Durability — Five-Layer Category Fix Spec v1

**Status:** REVISE → implement (3×3 debate: comprehensive 3/10 pre-impl, appropriateness 6/10, accuracy 7/10)  
**Scope:** Beat Gen trim/cut + Send to Stitcher export path  
**Event proof target:** Event_2 intro (`localhost:5112`)  
**Build order:** L1 → L4 → L2 → L5 → L3 (L3 after input cache; bake contracts below)

## Problem class

Send to Stitcher fails intermittently with `ffmpeg cut-out failed: … Resource deadlock avoided` when ffmpeg reads/writes under macOS Dropbox CloudStorage. Secondary UX class: dual start/end crop blocked by legacy single cut-out model and deferred materialization at export.

## Dependency-ordered layers

| Layer | Name | Depends on | Delivers |
|-------|------|------------|----------|
| **L1** | Cloud-aware ffmpeg I/O | — | All ffmpeg outputs stage on local disk; commit with errno 11/35 retry |
| **L2** | Trim model unification | L1 | Edge crops use `trim_start_s`/`trim_back_s` only; middle cut-out explicit |
| **L3** | Bake on Apply Cut | L1, L2 | Approved trim baked to stable per-option MP4 at Apply; export reads baked artifact |
| **L4** | Event compute cache | L1 | ffmpeg `-i` reads from local cache mirror; Dropbox = authority only |
| **L5** | Segment export resilience | L1–L4 | Per-beat materialize retry + structured error; concat uses baked/cache paths |

---

## L1 — Cloud-aware ffmpeg I/O

### Module

`Production/lib/ffmpeg_io.py`:

- `path_is_cloud_storage_backed(path) -> bool`
- `local_staging_temp_path(*, suffix, prefix) -> Path`
- `commit_local_file_to_dest(local, dest) -> None` (wraps durable copy + unlink)
- `run_ffmpeg_to_dest(cmd_builder, dest, *, timeout) -> Path` — builds cmd with local tmp output, commits

### Migration from beat_generator

Move helpers from `beat_generator.py`; re-export for backward compat.

### Call sites (this phase — export hot path)

1. `materialize_o3_cut_out_clip` / `materialize_kling_o3_trimmed_clip` (already migrated — import from lib)
2. `_ffmpeg_concat_kling_clips_reencode` — final `assembled/*.mp4` via local stage
3. `trim_kling_o3_clip_post_speech` — same-dir tmp → local stage
4. `credentials_lib/stitch_cache_build.atomic_ffmpeg_output` — cloud-aware tmp dir

### Contract tests

- `test_ffmpeg_io_cloud_staging.py` — cloud dest never receives ffmpeg output path directly
- Extend `test_o3_per_option_trim.py` materialize test to import from lib

---

## L2 — Trim model unification

### Behavior

1. **`migrate_o3_options_edge_cut_to_trim`** — already converts head/tail cut-out to trim (keep middle cut-out).
2. **`migrate_segment_o3_trims_for_export(beats)`** — run on every Send to Stitcher before concat; persist sidecar if changed.
3. **Export priority change:** if beat has trim active → use trim path even if stale cut fields exist (cut cleared on migrate).
4. **UI:** Apply Cut already posts trim only; no change required.

### Sidecar fields (unchanged)

- Per-option: `trim_start_s`, `trim_back_s` | `cut_start_s`, `cut_end_s` (middle only)
- Beat cache: mirrored from active option

### Contract tests

- Golden: Event_2 sidecar beats with `cut 0→X` migrate to trim on export prep
- Middle cut beat_22 stays cut-out; materialize uses L1 staging

---

## L3 — Bake on Apply Cut

### New sidecar fields (per option + beat cache when active)

- `kling_o3_baked_path` — absolute path to baked MP4
- `kling_o3_baked_token` — `{gen}_{trim_token}` or `{gen}_{cut_token}` for invalidation

### Functions

- `o3_baked_export_token(beat, *, video_path) -> str`
- `bake_o3_active_export_clip(beat, event_dir, *, slot_index, video_path) -> dict`
- Clear baked fields on: clear trim, clip change, generation bump, redo

### Apply path

`handle_bg_kling_o3_trim` — after persist (not `preview_only`), call `bake_o3_active_export_clip`.

### Export path

`_kling_o3_export_clip_path`:

1. If baked path exists, token matches, file on disk → return baked (no ffmpeg)
2. Else existing materialize (L1 staging) as fallback

### Contract tests

- Apply trim → baked file exists + export uses baked without re-encode (mock ffmpeg call count)
- Clear trim → baked fields removed

---

## L4 — Event compute cache

### Module

`Production/lib/event_media_cache.py`:

- Cache root: `~/.cache/mindfulnest/events/{event_id}/`
- `ensure_local_media(path: Path, *, event_id) -> Path` — copy if missing or source mtime newer
- Uses `copy_file_durable` for promotion from Dropbox

### Integration

- `materialize_*` and `_ffmpeg_concat_*` pass `-i` through `ensure_local_media`
- Cache invalidation: source mtime/size mismatch

### Contract tests

- First call copies; second call hits cache (no copy if mtime unchanged)

---

## L5 — Segment export resilience

### Functions

- `materialize_beat_export_clip_with_retry(beat, event_dir, scratch_dir, *, max_attempts=12) -> Path`
- Wraps `resolve_beat_stitch_export_clip_path`; retries on `sidecar_io_transient` + ffmpeg errno in message

### Export handler

`concat_kling_o3_approved_beats`:

- Pre: `migrate_segment_o3_trims_for_export(beats)`
- Per beat: retry wrapper
- On failure: error includes `beat_id` + last stderr snippet

### Contract tests

- Simulated errno 11 on first materialize attempt succeeds on retry

---

## Deploy & QA matrix

| Step | Command / proof |
|------|-----------------|
| Unit | `pytest tests/test_ffmpeg_io_cloud_staging.py tests/test_o3_per_option_trim.py tests/test_o3_export_durability.py -v` |
| Parity | Mirror tooling → Dropbox; `verify_tooling_dropbox_parity.py` |
| Bundle | `npm run build` in storyboard-v2 (vite if tsc blocked) |
| Server | Restart `:5112`; HTTP 200 |
| User path | POST export-to-stitcher scoped Event_2; assembled MP4 exists + duration > 0 |
| Browser | Beat 4: Apply dual trim → Send to Stitcher toast success |

---

## Out of scope (follow-on)

- Full sweep of all ffmpeg call sites in phases.py / production_server.py (documented in L1 audit)
- Moving entire Event_2 tree off Dropbox

---

## 3×3 agent debate summary (pre-implementation)

| Reviewer | Score | Verdict | Key finding |
|----------|-------|---------|-------------|
| Comprehensiveness | 3/10 | REVISE | L2–L5 unimplemented at audit time; concat still wrote to Dropbox |
| Appropriateness | 6/10 | REVISE | Build order L1→L4→L2→L5→L3; L3 needs bake failure + WYSIWYG contracts |
| Accuracy | 7/10 | REVISE | Spec must label current vs planned; trim-over-cut was not yet shipped |

**Consensus:** Ship all five layers; order **L1 → L4 → L2 → L5 → L3**; bake-on-apply must fail loud (`O3_TRIM_BAKE_FAILED`).

---

## Execution proof (2026-06-22)

- **Unit:** `31 passed` — `test_ffmpeg_io_cloud_staging`, `test_o3_export_durability`, `test_o3_per_option_trim`, `test_o3_per_option_cut`, `test_sidecar_io_durability`
- **User path:** Event_2 intro concat → `intro_kling_o3_20260622T193933Z.mp4` — **149,525,651 bytes**, **178.28s**, **25 beat boundaries**
- **Browser:** Storyboard v2 loads at `http://127.0.0.1:5112/` — Event_2 / intro scope confirmed
