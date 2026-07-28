# TECH SPEC — Storyboard Hot Media Authority (Dual-Root) v1

**Status:** APPROVED BY CONSENSUS (3×3 debate 2026-07-28) — implement phased; not a big-bang  
**Marker:** `STORYBOARD_HOT_MEDIA_AUTHORITY_V1`  
**Scope:** Authoring toolchain only (Beat Gen, Stitcher, Phase A/B, Library, `/files`). Kid app unchanged.  
**Parent:** `STORYBOARD_OPTION_B_SPEC_v1.md` (unchanged dual root)  
**Related:** `BG_O3_FFMPEG_DURABILITY_SPEC_v1.md`, `STORYBOARD_UNIFIED_PLAYBACK_SPEC_v1.md`, `media_hot_root.py`, `media_playback_cache.py`, PR #130 (`KLING_O3_EXPORT_DURATION_LOCAL_PROBE_V1` / `KLING_O3_DURATION_UNREADABLE_V1`), `KLING_O3_EXPORT_LOCAL_CLIP_V1` (export worker — sibling session)

**Non-goals:**

- Moving `event_dir` off Dropbox  
- Rewriting sidecar / registry paths to `~/.mindfulnest/...`  
- Claiming “Dropbox is cured” for JSON locks, sync lag, or incomplete cloud download  
- Big-bang rewrite of every `_ffprobe_duration` call in one PR  

---

## 1. Problem class

macOS Dropbox **File Provider** (CloudStorage) is unreliable for **live** open / stat / range-read / ffprobe under concurrent Storyboard load (errno 11/35, hangs without raise, duration=0, opaque ffmpeg exit 1).

That is **not** the same as “Dropbox as the folder where Event_N lives.” Option B correctly keeps Dropbox as durable runtime data. The bug class is: **hot-path I/O treats CloudStorage like a local disk.**

### Proven instances

| Incident | Layer green | Layer failed | Lesson |
|----------|-------------|--------------|--------|
| Event_6 Send to Stitcher — false “Apply Trim” | — | Preflight duration on Dropbox masters | #130: local duration probe + `DURATION_UNREADABLE` |
| Event_6 job `7f3e8c8f-59e` — button “starting” then fail | Preflight (#130) | Export worker ffprobe Dropbox `*_baked.mp4` | **Gate ≡ worker** — fixing one layer is not a cure |
| Beat Gen gray / spin on warm clips | — | `/files` probed Dropbox before warm `pb_*` | TRUE_CACHE_FIRST hot-serve |

### Operator fear (valid)

Every Storyboard feature still **names** Dropbox paths (`--event-dir`, sidecar `kling_o3_video_path`, assembled exports). Changing that naming model would break Mac↔PC sync, deploy, LaunchAgents, and operator mental model. This spec **does not** change naming. It changes **how live bytes are read**.

---

## 2. Decision (consensus)

**Dual-root hot media authority:**

| Layer | Location | Role |
|-------|----------|------|
| **Cold / durable** | Dropbox `Production/Event_N/` (`event_dir`) | Masters, sidecar fields, assembled finals, library sources, export job JSON, PC↔Mac sync |
| **Hot / ephemeral** | `~/.mindfulnest/media/<Event_N>/` (or `MN_MEDIA_HOT_ROOT`) | `.playback_cache`, trim/cut scratch, materialize targets for ffprobe/ffmpeg `-i` / browser range |

**Invariant:** If an operator click or worker needs an answer in ~seconds (play, trim validate, export concat, thumb), it MUST NOT depend on File Provider succeeding on the CloudStorage master in that moment. It MUST use hot-workspace bytes (or fail closed with an honest error).

**Forbidden interpretations:**

- “Take Dropbox out of the picture”  
- “Move Storyboard to local-only”  
- “Rewrite all paths in sidecars to local”  
- “Preflight green ⇒ Send to Stitcher works” without worker proof  

---

## 3. Authority model

### 3.1 What stays on Dropbox forever

| Artifact | Path pattern | Notes |
|----------|--------------|-------|
| Event root | `…/Production/Event_N/` | `--event-dir` for LaunchAgents `:5111`–`:5117` |
| O3 / delivery masters | `kling_o3_clips/*.mp4` | Sidecar keeps Dropbox absolute paths |
| Assembled stitch exports | `assembled/intro_*.mp4` etc. | Durable deliverables |
| Library sources | `library/**` | |
| `production_state.json` | Event root | |
| Export job records | `bg_export_stitcher_jobs/*.json` | Still Dropbox — see §8 honest scope |
| Registry | `Production/character_subjects.json` | Cat-2; never tooling→Dropbox overwrite on deploy |
| Storyboard HTML fanout | `storyboard_v59_prod.html` | Deploy parity |

### 3.2 What must be hot-local for live I/O

| Operation | Required adapter |
|-----------|------------------|
| Browser `/files` range serve | `ensure_hot_serve_file` (TRUE_CACHE_FIRST) |
| ffprobe duration for trim/export/cut gates | `ffprobe_media_duration` |
| ffmpeg `-i` for trim/cut bake | `ensure_local_media` → hot path |
| Send to Stitcher concat inputs | Resolve via `_kling_o3_export_clip_path` / `resolve_segment_stitch_export_clip_paths` — **never** reuse CloudStorage `kling_o3_baked_path` |
| Magic-on-video source | Same export clip resolver |
| New trim scratch / bake output | `kling_o3_trim_scratch_dir(event_dir)` → hot workspace |

### 3.3 Single I/O authority (target)

One conceptual authority: **hot media resolve**.

| Entry | Module | Purpose |
|-------|--------|---------|
| `ensure_hot_serve_file` | `media_playback_cache.py` | Bytes for HTTP range / serve |
| `ensure_local_media` | `beat_generator.py` → hot serve | Bytes for ffmpeg `-i` |
| `ffprobe_media_duration` | `beat_generator.py` | Duration without Dropbox ffprobe |
| `kling_o3_trim_scratch_dir` | `media_hot_root.py` / `beat_generator` | Scratch under hot workspace |
| `_export_baked_path_is_hot_reusable` | `beat_generator.py` | Reject Dropbox legacy bakes |

**Rule:** New hot-path code MUST call one of the above. Raw `_ffprobe_duration(CloudStorage path)`, bare `open`/`isfile`/`realpath` on CloudStorage media in request/worker paths is a **forbid-list** violation (§6).

Durable **writes** of masters and finals still commit to Dropbox (via `copy_file_durable` / `run_ffmpeg_to_dest` staging). Hot copies are **derived cache**, never authoritative path rewrites in sidecar.

---

## 4. Freshness and failure contracts

### 4.1 Cache freshness

- Prefer basename warm hit (`pb_*_<basename>`) when present (TRUE_CACHE_FIRST).  
- When Dropbox metadata is available, invalidate/replace when size+mtime disagree with cache token.  
- When Dropbox metadata is **unavailable** (stall/errno): serve warm cache if present; **do not** invent bytes.  
- If no warm cache and Dropbox probe fails/times out: **fail closed** with honest error (`DURATION_UNREADABLE`, “File Provider busy — local cache not ready”), never silent wrong media.

### 4.2 Stale / split-brain

Serving wrong trim/export because cache and master diverged silently is **worse** than a stall. Prefer:

1. Hard fail + retry UX, or  
2. Rematerialize when token/source path proves mismatch (`_o3_baked_cache_matches_source`, bake token).

### 4.3 PC ↔ Mac

- Dropbox remains the shared truth.  
- Each machine warms its own `~/.mindfulnest/media/<Event_N>/`.  
- After first open / play / trim on a machine, hot layer fills.  
- Do not assume Mac cache exists because PC trimmed — hydrate on use.  
- Optional later: explicit “warm Event_N” operator action; not required for v1.

---

## 5. Phased execution (avoids #130 trap)

**Global rule:** No phase is “done” until **gate + worker + one real user-path** agree on the **same** live build-sha (Option B deploy proof).

| Phase | Name | Delivers | Exit proof |
|-------|------|----------|------------|
| **P0** | Spec + forbid inventory | This doc; inventory of raw CloudStorage probes | Doc merged; inventory table in §9 |
| **P1** | Send to Stitcher worker (sibling) | `KLING_O3_EXPORT_LOCAL_CLIP_V1` — reject Dropbox bakes; localize concat inputs; soft-fail stitch ffprobe | Real Event_N export job succeeds after “starting”; build-sha match; pytest `test_export_rejects_dropbox_baked_clip.py` |
| **P2** | Forbid-list + CI gate | Script/pytest fails if new hot-path raw `_ffprobe_duration` / CloudStorage open patterns appear in allowlisted modules | `verify_hot_media_authority_durability.sh` green |
| **P3** | Trim / Apply / preview parity | All trim set + preview duration paths use `ffprobe_media_duration`; bake only to hot scratch | Event_6 trim audit: no “Could not read clip duration” storm on warm clips |
| **P4** | Stitcher live I/O | Slot dry / mux / SFX extract / ambient probe via hot serve | Stitcher play + one SFX path on pilot event |
| **P5** | Phase A/B + vendor | High-traffic `_ffprobe_duration` on stems/lipsync via media duration helper | One Phase A duration path smoke |
| **P6** | Library / thumbs / crop | Already partly hot; close remaining Dropbox-first probes | Thumb + library list on pilot port |
| **P7** | Legacy cleanup (optional) | Stop *writing* new bakes under Dropbox `assembled/_kling_o3_trim_scratch`; optional delete stale Dropbox scratch | New bake paths under `~/.mindfulnest/media/...`; **never** delete Dropbox masters |

**Pilot order:** Prove P1 on **one** event/port (prefer Event_6 if that is the active wound, else Event_2 `:5112`) for a real operator send → then fleet roll.

**Ownership:** P1 may land in a sibling session. This tech-spec repo track owns P0 + P2+ coordination and must not claim P1 done until live build-sha includes it.

---

## 6. Forbid-list (category lock)

### Forbidden in request handlers, export workers, trim/cut setters, stitch extract

1. `_ffprobe_duration(path)` when `path_is_cloud_storage_backed(path)` without prior `ensure_local_media` / `ffprobe_media_duration`  
2. Reusing `kling_o3_baked_path` when path is CloudStorage-backed  
3. ffmpeg `-i` pointing at CloudStorage without `ensure_local_media`  
4. `/files` streaming CloudStorage bytes when a hot cache miss policy says fail (never raw Dropbox range as success path)

### Allowed

1. Durable **write** commit to Dropbox after local encode  
2. Sidecar **storing** Dropbox absolute paths  
3. `isfile`/`stat` with short timeout / durable retry for **existence** checks when no hot alternative — prefer hot basename first  
4. CLI / one-off scripts outside Storyboard HTTP (still prefer hot helpers)

### Durability gate (P2)

`Production/scripts/verify_hot_media_authority_durability.sh`:

- Grep allowlisted modules for forbidden patterns  
- Pytest: Dropbox bake rejected; `ffprobe_media_duration` routes cloud→local; gate≡worker contract fixture  
- Markers present: `STORYBOARD_HOT_MEDIA_AUTHORITY_V1`, `KLING_O3_EXPORT_DURATION_LOCAL_PROBE_V1`, `KLING_O3_EXPORT_LOCAL_CLIP_V1` (when P1 merged)

---

## 7. Full QA requirements (every phase that ships code)

```
Full QA progress:
- [ ] 1. Reproduce — log/job id / preflight vs worker evidence
- [ ] 2. Fix — category slice only (this phase’s pipeline)
- [ ] 3. Multipass unit + contract tests (≥2 shapes: warm cache hit, Dropbox-baked reject)
- [ ] 4. Commit on feature branch before deploy
- [ ] 5. deploy_option_b.sh --event Event_N — [deploy] complete + fleet build-sha == HEAD
- [ ] 6. User-path: browser hard refresh; one real click path; cite build-sha table
```

**Never** call a phase done after pytest-only or “fixed in tooling only.”

---

## 8. Honest scope (what this does **not** fix)

| Still on Dropbox | Risk remaining |
|------------------|----------------|
| `bg_export_stitcher_jobs/*.json` + export.lock | File Provider can stall job poll/create |
| Sidecar SQLite mirror sync / some audits | Occasional slow refresh |
| Incomplete Dropbox download / vacation sync lag | Hot cache cannot invent missing masters — hard fail |
| LaunchAgents / backups scanning Event trees | Need Dropbox present; not a click-latency path |

Tech spec success = **operator clicks and media workers just work** when masters exist on Dropbox. It is **not** “Dropbox sync never lags.”

---

## 9. Inventory baseline (P0 — living table)

Update this table as phases close. Status: `DONE` / `IN_FLIGHT` / `TODO` / `PARTIAL` / `WONTFIX v1`.

**Coverage rule:** Every **Storyboard HTTP / async worker** path that ffprobes, range-serves, or ffmpeg-reads CloudStorage media MUST appear here. CLI one-offs and pytest helpers may stay raw until touched. Multiple local `def ffprobe_duration` copies are cousins of the same class — forbid-list must name modules, not only `beat_generator._ffprobe_duration`.

### 9.1 Already closed / in flight

| ID | Area | Hot? | Status | Adapter / notes |
|----|------|------|--------|-----------------|
| H1 | `/files` playback | Y | DONE | TRUE_CACHE_FIRST |
| H2 | Trim bake ffmpeg `-i` | Y | DONE | `ensure_local_media` |
| H3 | Trim/export **preflight** duration | Y | DONE | #130 `ffprobe_media_duration` |
| H4 | Send to Stitcher **export worker** clips | Y | IN_FLIGHT (sibling) | `KLING_O3_EXPORT_LOCAL_CLIP_V1` |
| H5 | Reject Dropbox `*_baked.mp4` reuse | Y | IN_FLIGHT (sibling) | `_export_baked_path_is_hot_reusable` |
| H6 | Forbid-list CI | — | TODO | P2 — must cover **all** ffprobe defs in §9.5 |

### 9.2 Beat Gen (trim / O3 / magic / session)

| ID | Area | Hot? | Status | Phase | Notes |
|----|------|------|--------|-------|-------|
| H7 | Trim preview / `set_o3_option_trim` / `set_kling_o3_beat_trim` / cut setters | Y | PARTIAL | P3 | Some use `ffprobe_media_duration`; remaining raw probes in `beat_generator` cut/hydrate/bake helpers |
| H7b | `background.py` still-insert bake `bg._ffprobe_duration` | Y | TODO | P3 | Line ~7735 family |
| H7c | `background.py` other ffmpeg src duration (~1402) | Y | TODO | P3 | |
| H8 | Magic-on-video source | Y | PARTIAL | P1→P3 | Shares export resolver — re-prove after P1 live |
| H8b | `kling_o3.py` delivery duration assert (`bg._ffprobe_duration`) | Y | TODO | P3 | |
| H13 | Session-state / migrate / reconcile mass `isfile` on clips | Y | TODO | P3/P6 | Stall class under Dropbox load |
| H13b | O3 disk reconcile / orphan recovery path probes | Y | TODO | P3 | |
| H14 | Legacy Dropbox trim scratch **writes** | — | TODO | P7 | Stop new writes under Dropbox `assembled/_kling_o3_trim_scratch` |
| H14b | Sidecar still **pointing** at legacy Dropbox bakes | Y | IN_FLIGHT | P1 | Read path fixed by reject+rematerialize; pointers may linger until rewrite/clear |

### 9.3 Stitcher

| ID | Area | Hot? | Status | Phase | Notes |
|----|------|------|--------|-------|-------|
| H9 | Stitcher dry / mux / slot playback ffprobe | Y | TODO | P4 | `stitch_slot_playback`, slot timeline |
| H9b | SFX extract / waveform peaks | Y | PARTIAL | P4 | Some `ensure_hot_serve_file` already (stitch_editor) |
| H9c | Ambient bed hydrate / loop / seam ffprobe | Y | TODO | P4 | |
| H9d | `credentials_lib/ffmpeg_stitch.ffprobe_duration` | Y | TODO | P1/P4 | Used by concat A/V assert — soft-fail + local path required |
| H9e | `stitch_bake_finalize._ffprobe_duration_ms` | Y | TODO | P4 | |
| H9f | Stitcher bake / preview normalize inputs | Y | TODO | P4 | |

### 9.4 Phase A / B + vendor + production_server

| ID | Area | Hot? | Status | Phase | Notes |
|----|------|------|--------|-------|-------|
| H10 | `server_handlers/phases.py` stem/lipsync/trim durations | Y | TODO | P5 | Many `_ffprobe_duration` call sites |
| H10b | `phase_a_av_post.py` | Y | TODO | P5 | Own probe helper usage |
| H10c | `phase_a_*_lipsync.py` / idle / middle / chipper / beak | Y | TODO | P5 | Multiple modules |
| H10d | `phase_a_chipper_bytedance_lipsync.ffprobe_duration` | Y | TODO | P5 | **Separate def** |
| H10e | `phase_a_chipper_face_composite._ffprobe_duration` | Y | TODO | P5 | **Separate def** |
| H10f | `phase_b_kling_base_prep.py` | Y | TODO | P5 | |
| H10g | `phase_b_path_a_pipeline.ffprobe_duration` | Y | TODO | P5 | **Separate def** |
| H10h | `production_server.py` phase/audio/video duration helpers | Y | TODO | P5 | Own `_ffprobe_duration` + `_ffprobe_duration_ms` |
| H11 | `server_handlers/vendor_jobs.py` idle/clip durations | Y | TODO | P5 | |
| H11b | `kling_element_voice.ffprobe_duration` | Y | TODO | P5 | Element/voice setup |

### 9.5 Library / crop / misc Storyboard

| ID | Area | Hot? | Status | Phase | Notes |
|----|------|------|--------|-------|-------|
| H12 | Library thumbs / CR thumb | Y | PARTIAL | P6 | cropper already hot-serve on miss |
| H12b | Library list / metadata walks | Y | PARTIAL | P6 | File Provider walk stalls |
| H12c | Crop save / source open | Y | PARTIAL | P6 | |
| H16 | Watercolor / phase cue media serve | Y | TODO | P6 | If served via `/files` → H1; else add |
| H17 | Milestone scope media paths | Y | TODO | P4/P6 | Same adapters; different `event_dir` |
| H18 | `teleport_intro_kit.ffprobe_duration` | Y | TODO | P5/P7 | If still in operator path |
| H19 | `pin_event_canonical_module._ffprobe_duration_ms` | Y | TODO | P5 | |

### 9.6 Separate ffprobe implementations (forbid-list must include)

P2 CI must flag **raw CloudStorage probes** in at least:

- `beat_generator._ffprobe_duration` (OK only after localize / non-cloud)
- `production_server._ffprobe_duration` / `_ffprobe_duration_ms`
- `credentials_lib/ffmpeg_stitch.ffprobe_duration`
- `phase_a_chipper_bytedance_lipsync.ffprobe_duration`
- `phase_a_chipper_face_composite._ffprobe_duration`
- `phase_a_beak_rig_proof._ffprobe_duration`
- `phase_b_path_a_pipeline.ffprobe_duration`
- `kling_element_voice.ffprobe_duration`
- `teleport_intro_kit.ffprobe_duration`
- `stitch_bake_finalize._ffprobe_duration_ms`
- `pin_event_canonical_module._ffprobe_duration_ms`
- `scripts/trim_ambient_bed_silence._ffprobe_duration_s` (CLI — lower priority)

Long-term: collapse to one `ffprobe_media_duration` (or lib helper) for Storyboard media.

### 9.7 Durable Dropbox (not hot-I/O cousins — do not “phase off Dropbox”)

| ID | Area | Hot? | Status | Notes |
|----|------|------|--------|-------|
| H15 | Export job JSON `bg_export_stitcher_jobs/` | N | WONTFIX v1 | Honest scope §8 |
| H15b | Sidecar / `production_state` / masters / assembled finals | N | KEEP | Option B cold store |
| H15c | LaunchAgents `--event-dir` Dropbox | N | KEEP | |
| H15d | Daily backup / weekly snapshot | N | KEEP | |
| H15e | Deploy fanout / parity | N | KEEP | |

### 9.8 Coverage statement

- **Phase buckets P0–P7** cover the whole **program** of Storyboard hot-I/O cousins.  
- **v1 table H1–H15 alone was incomplete** at leaf level; §9.2–§9.6 are the expanded cousin body (audit 2026-07-28).  
- New call sites found later MUST be added here in the same PR that touches them (living inventory).

---

## 10. Plain-language operator contract

1. **Your Event files stay in Dropbox** on Mac and PC.  
2. **Scratch/speed copies** live under `~/.mindfulnest/media` on the machine you are using — disposable.  
3. **A green check alone is not enough** — Send to Stitcher (and later each feature) must complete the real job on the live build-sha.  
4. **We will not move the house** (Event folders) off Dropbox.  
5. **We will not live forever** on one-button patches; we close the hot-I/O class in phases with proof.

---

## 11. Success criteria (program)

- [ ] P1 live on pilot event: Send to Stitcher completes after “starting” with no Dropbox `*_baked` ffprobe in failure logs  
- [ ] P2 forbid-list gate green on `main`  
- [ ] Pilot day: play → trim → export → refresh → still good on one port  
- [ ] Fleet build-sha parity after each shipping phase  
- [ ] No sidecar paths rewritten to `~/.mindfulnest`  
- [ ] Authority registry row for `storyboard_hot_media` (ship with P2)

---

## 12. 3×3 debate record

| Role | Verdict |
|------|---------|
| Pro | Dual-root PRO with mandatory hot path + Full QA per cousin |
| Skeptic | APPROVE WITH GATES (single authority, forbid-list, gate≡worker, freshness, write policy, honest JSON scope) |
| Operator | YES-WITH-SEQUENCE (Dropbox stays home; no big-bang; no gate-only) |

**Consensus:** Proceed with this dual-root plan; reject remount/off-Dropbox and reject “just work with no gates.”

---

## 13. Document control

| Version | Date | Change |
|---------|------|--------|
| v1 | 2026-07-28 | Initial consensus spec from thread + architecture + 3×3 debate |
| v1.1 | 2026-07-28 | Expanded §9 cousin inventory (leaf modules + multi-ffprobe defs); coverage statement |
