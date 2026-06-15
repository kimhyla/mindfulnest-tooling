# Magic + End-Frame Fixes — Implementation Plan v1.1
Date: 2026-05-20
Branch: `feature/magic-and-endframe-20260520`
Marker: `MAGIC_ENDFRAME_SPEC_20260520_91F3A0B5D4E2`
Cursor-debate status: CONVERGED (round 2)

## §1 Task

### Topic 2 — Preview Still/Video doesn't show magic; magic_*_path lands on wrong partition (BUGS)

Empirical evidence (2026-05-20, captured pre-spec):

- `videos.resolution.beats.beat_01.magic_still_path` MISSING after a successful magic_still render against resolution beat_01.
- `videos.intro.beats.beat_01.magic_still_path` SET to the actual rendered filename `magic_still_beat_01_20260520-164348.mp4`.
- Kim's URL when triggering magic from storyboard: `/magic?mode=magic_still&beat_id=beat_01&source_image_path=Production%...` — NO `scope_video_role` URL parameter present.
- `path_picker.html` line ~286 defaults `scopeVideoRole = …  || 'intro'`; server-side `handle_magic_still` + `handle_magic_video` also default to `'intro'` at the `_pin` capture.
- Even if the writeback landed on the correct partition, `StoryboardTab.tsx` line ~1147 chooses `previewVideoSrc` for `previewOptIdx === -1` as `beat.final.file` — NOT `beat.magic_still_path` — so Preview Still on a beat with magic_still_path would still play the non-magic still-as-final mp4.

### Topic 1 — End-frame iteration UI (NEW FEATURE)

Currently `_handle_add_options_startend` (production_server.py ~8780+) generates the OpenAI end frame in-memory and immediately submits to Kling in one click. Kim cannot see the end frame before Kling spends $0.90. If OpenAI hallucinates (e.g. drops the character's glasses), Kim only learns after a full Kling render.

Kim's required flow:
1. Drag-drop start image (unchanged).
2. Click "✏ Preview end frame" → server calls OpenAI once (~$0.04), saves PNG to disk, writes `beat.end_frame_path`, returns the URL. Thumbnail appears next to the start image.
3. Iterate as needed: click again for a fresh n=1 sample OR add a textarea addendum (one-shot per click, auto-clears after submit) OR upload your own PNG (from chatgpt.com web, $0).
4. Click "🔄 Regenerate B + C" — server reads `beat.end_frame_path` from disk; does NOT call OpenAI; submits start + saved end to Kling for opt B + opt C ($0.90).
5. If no `end_frame_path` exists at Regen B+C time, server returns 400 — Kim must preview at least once first.

## §2 Approach

### Topic 2 fixes

**Bug-A1** — `StoryboardTab.tsx` lines ~1694-1703: include `&scope_video_role=${activeTargetVideo}` in the `/magic?…` URL constructed for both "Add magic on still" and "Add magic on video" buttons. Use the same `activeTargetVideo` value the rest of the component already reads.

**Bug-A2** — `path_picker.html` line ~286: if URL `scope_video_role` param is absent AND `window.opener` is accessible AND has a `scope_video_role` URL param itself, read from opener. Otherwise leave scopeVideoRole `null` (NOT default `'intro'`). Server (Bug-A3) refuses the null on its end.

**Bug-A3** — `server_handlers/background.py` `handle_magic_still` and `handle_magic_video`: replace `(body or {}).get("scope_video_role", "intro")` defaults with explicit 400 `VIDEO_ROLE_REQUIRED` errors. Use `_assert_event_scope(..., allow_missing_video_role=False)` (validator already supports the flag — production_server.py:5537; default is False so this just makes intent explicit and removes the legacy `or "intro"` rescue path inside the handler).

**Bug-A4** — Same handlers, after `scope_router.mutate_partition`: read the partition back and assert `partition.beats[beat_id].magic_*_path == magic_filename`. If not, return 500 with `STATE_WRITEBACK_VERIFY_FAILED` + log loud. Response includes `partition_written` field on success.

- **CRITICAL placement note (cursor 2026-05-20)**: the existing `try/except Exception as exc: print(f"[magic_*] WARN state writeback failed: {exc}")` at background.py:712-713 (still) and ~995 (video) is a SWALLOW-ALL catch. The new read-back verify MUST live OUTSIDE this try/except, OR raise a distinct exception type that we re-raise (not log-and-continue). Otherwise the verify failure gets silently swallowed exactly like the bug we're fixing. Implementation: after the `try/except` block finishes, do the read-back as a separate operation that DOES propagate failures.

**Bug-B1** — `StoryboardTab.tsx` `previewVideoSrc` priority chain at `previewOptIdx === -1`:
- **Cursor review 2026-05-20**: magic_still_path files are written to `event_dir/` (background.py:641-642), but `/asset/` serves ONLY from `clips_dir/`. Therefore must use `/files?path=...` to serve magic playback. NOT `/asset/`.

```ts
previewOptIdx === -1
  ? (beat.magic_still_path && beat.magic_still_path_exists !== false
       ? `${SERVER_BASE}/files?path=${encodeURIComponent(`Production/${eventId}/${beat.magic_still_path}`)}&v=${beat._version ?? 0}`
       : (beat.final?.source === 'still_image' && beat.final?.file && beat.final?.file_exists !== false
           ? _finalFileSrc : null))
```

Same priority chain mirrored for the magic_video case (where final is a video), referencing `beat.magic_video_path` + `magic_video_path_exists`.

**Bug-B2** — Small `✨ magic` badge inline next to the Preview Still button when `beat.magic_still_path` (or `beat.magic_video_path`) is truthy. No new button — Kim already has many.

**Bug-B3 (NEW per cursor review)** — Extend `_read_state_with_file_flags` (production_server.py:~8150-8214) to also annotate:
- `beat.magic_still_path_exists` (bool — file present at `event_dir / magic_still_path`)
- `beat.magic_video_path_exists` (bool — file present at `event_dir / magic_video_path`)
- `beat.end_frame_path_exists` (bool — file present at `event_dir / "end_frames" / end_frame_path`)

**Path-resolution discipline (cursor 2026-05-20):** the existing `_annotate_block` defaults to `clips_dir` resolution for options/lipsync/final. Magic outputs are written to `event_dir` (root, not `clips_dir`); end-frames to `event_dir / "end_frames"`. The new annotations MUST explicitly resolve against those bases, not the `clips_dir` default. Implementation should pass an explicit resolver root per field OR use absolute `event_dir / <subpath>` checks.

Without this, orphaned references (file deleted from disk, state still set) cause silent 404s in `<video src=…>` exactly like the LD-807 case we just hit on beat_03 earlier today.

### Topic 1 build

**T1-Phase 1** — Extract shared helper `Production/lib/end_frame_prompt.py::build_end_frame_prompt(beat: dict, speaker_canonical: str, addendum: str | None) -> str`. Pull lines 8349-8462 of `production_server.py` verbatim into the helper. Helper returns: `canonical + ("\n\nKim addendum: " + addendum.strip() if addendum else "")`. Append vendor-specific safety tail (Rule 8 mouth/beak) ONCE at the very end. Both `_handle_add_options_startend` and the new preview endpoint call this. **No imports from production_server.py** (cycle risk) — caller passes `speaker_canonical` as input arg.

**T1-Phase 2** — New `POST /api/beat/preview_end_frame`:
- Body: `{scope_event_id, scope_video_role, beat_id, prompt_addendum?: string}` (NO intro default; 400 if missing video_role)
- Resolve speaker → canonical → bird/non-bird Rule 8 tail
- Build prompt via shared helper
- Call `openai_image_edit_generate_end_frame` (or FLUX per LD-730 vendor selection)
- Auto-upscale to ≥600px via existing `auto_upscale_image`
- Validate dims via existing `validate_image_dimensions`
- Save PNG to `Production/Event_N/end_frames/{beat_id}_endframe_{ISO_TS}.png` (mkdir if needed)
- Mutate state via `scope_router.mutate_partition`: set `beat.end_frame_path = filename`
- DS-22 read-back verify before responding
- Prune: keep only the 3 most-recent `{beat_id}_endframe_*.png` files in the dir, delete older
- Return `{ok, end_frame_path, end_frame_url, partition_written}`
- Cost ~$0.04 per call (OpenAI) or $0.03 (FLUX)

**T1-Phase 3** — New `POST /api/beat/upload_end_frame` (JSON + base64, **NOT multipart**):
- Cursor review 2026-05-20: production_server.py uses BaseHTTPRequestHandler with `_read_json` only; precedent for client-side base64 upload is `handle_cr_upload` in cropper.py:679. Match that pattern (no new multipart parser).
- JSON body: `{scope_event_id, scope_video_role, beat_id, file_b64: string (base64-encoded PNG/JPG/WEBP bytes), mime: string}`
- Same scope-requirement + same partition validation as Phase 2
- Decode base64; sniff MIME; convert non-PNG to PNG via PIL
- Save with same naming convention: `{beat_id}_endframe_{ISO_TS}.png`
- Same DS-22 read-back + same prune
- Returns same response shape as Phase 2
- Cost: $0
- Client side (Phase 6 UI): use `FileReader.readAsDataURL` on picked file, strip `data:image/...;base64,` prefix, send as JSON.

**T1-Phase 4** — `_handle_add_options_startend` change:
- If `beat.end_frame_path` is set AND the file exists at `Production/Event_N/end_frames/{filename}`: READ those bytes, base64-encode, use as `end_b64_uri`. SKIP the existing OpenAI/FLUX call entirely.
- If `beat.end_frame_path` is absent OR file missing: RETURN 400 `END_FRAME_REQUIRED` with hint `"Click 'Preview end frame' first; or upload one via the upload button."`
- **NO GRANDFATHERING** (cursor 2026-05-20): refusal triggers ALWAYS when `beat.end_frame_path` is absent/missing, even if `phase_1.options` already exist. Kim explicitly confirmed: Regen B+C must require an approved end frame. Existing beats with options but no end_frame_path need a one-time `Preview end frame` click before next Regen B+C.
- (No silent fallback to live-generation — explicit refuse per Kim's directive.)

**T1-Phase 5** — Pruning helper: simple Python function `_prune_end_frames(beat_dir: Path, beat_id: str, keep: int = 3) -> list[Path]`. List `{beat_id}_endframe_*.png`, sort by mtime desc, unlink everything past index `keep`. Returns list of pruned paths for logging.

**T1-Phase 6** — UI in `StoryboardTab.tsx` beat row, sibling to the existing Regen B+C button:
- "✏ Preview end frame" button → POST JSON to `/api/beat/preview_end_frame`, on 200 setEndFramePath(response.end_frame_path), clear addendum textarea
- Inline `<input>` for addendum (single-line; addendum is short): placeholder `"e.g. ensure all accessories remain (glasses, backpack)"`
- "📤 Upload end frame" button → file picker; `FileReader.readAsDataURL(file)`, strip `data:image/...;base64,` prefix, POST JSON to `/api/beat/upload_end_frame`; same setEndFramePath + clear textarea
- Conditional `<img src={end_frame_url}>` thumbnail (50×50 with 1px border) when `beat.end_frame_path` is set AND `beat.end_frame_path_exists !== false`
- Existing "🔄 Regenerate B + C" button: when `beat.end_frame_path` is unset or `beat.end_frame_path_exists === false`, render disabled with tooltip `"Preview an end frame first"`; when set + exists, enabled
- **Double-submit guard** (cursor 2026-05-20): track in-flight state per beat — `pendingEndFrameOp: Record<string, boolean>` keyed by `beat_id` (NOT a single scalar — multiple beat cards may be in-flight simultaneously, though Kim typically operates on one at a time). While the entry for current beat is `true`, DISABLE Preview button + Upload button + Regen B+C on THAT beat. Spinner inline next to the button. Re-enable on response (success or error).
- Addendum input auto-clears on successful response (`onSuccess` callback resets the controlled value)
- 6-layer wiring documented inline in comments
- `BeatCard` interface gains `end_frame_path?: string` + `end_frame_path_exists?: boolean` fields

### Topic 4 (deferred to follow-up — NOT in this spec)

Systemic `or "intro"` ban + lint guard. Cursor surfaced this; out of scope for THIS spec per Kim's "don't bloat scope" pattern. Filed as a separate follow-up LD/blocker after delivery if Kim approves.

## §3 Files to be modified

### Topic 2
- `Production/tools/storyboard-v2/src/components/StoryboardTab.tsx` (Bug-A1, B1, B2)
- `Production/tools/path_picker.html` (Bug-A2)
- `Production/tools/server_handlers/background.py` (Bug-A3, A4)
- `Production/tools/production_server.py` (Bug-B3 file_exists enrichment extension)

### Topic 1
- `Production/lib/end_frame_prompt.py` (NEW — Phase 1)
- `Production/tools/production_server.py` (Phase 4 — refuse + read disk; route registration for new endpoints; helper invocation site)
- `Production/tools/server_handlers/background.py` (NEW handler entry points — Phase 2 + 3; pruning helper Phase 5)
- `Production/tools/storyboard-v2/src/components/StoryboardTab.tsx` (Phase 6 UI)
- `Production/tools/storyboard-v2/src/api/endpoints.ts` (new endpoint URLs)
- `Production/tools/storyboard-v2/src/api/client.ts` (JSON POST helper only — NO multipart per Phase 3 revision; existing `apiPost` already handles JSON)

### Audit/Governance
- `Production/docs/MAGIC_AND_ENDFRAME_FIXES_20260520_v1.md` (this file — registered in prod_reference_docs id=232)
- LD `MAGIC_ENDFRAME_FIXES_SPEC_20260520_V1` (locked, id=814)
- `prod_activity_log` coordinator-start row id=6172

## §4 Integration Contract (must verify at runtime)

### Topic 1 observables

| # | User action | Observable | Probe |
|---|---|---|---|
| 1 | Kim drag-drops a beat image (start frame) on resolution beat | `beat.image_path` set on `videos.resolution.beats.<beat_id>` partition (NOT intro) | `curl /api/v2/event/Event_1/state` + jq |
| 2 | Kim clicks "✏ Preview end frame" (empty addendum) on resolution beat | OpenAI called once; PNG appears under `Event_N/end_frames/<beat_id>_endframe_<TS>.png`; `beat.end_frame_path` set on `videos.resolution.beats.<beat_id>`; response includes `partition_written: "resolution"` | curl POST; state probe; `ls -la`; assert response shape |
| 3 | Kim views end-frame thumbnail in UI | `<img src="…/files?path=Production/Event_N/end_frames/<file>">` returns HTTP 200 with non-zero bytes | `curl -I` URL |
| 4 | Kim clicks "✏ Preview end frame" a 2nd time (with or without addendum change) | NEW TS PNG appears; OpenAI called again (~$0.04); `beat.end_frame_path` advances to new file; old file retained (until 4th attempt triggers prune of oldest) | state probe diff + `ls -la \| sort` |
| 5 | Kim clicks "📤 Upload end frame" + selects local PNG | JSON+base64 POST received; PNG decoded + saved with same naming; state updated; **OpenAI NOT called** | curl POST with base64 body; server log: no `[preview_end_frame]` line; only `[upload_end_frame]`. |
| 6 | Kim clicks "🔄 Regenerate B + C" (`/api/beat/add_options`) with no `end_frame_path` | Server returns 400 `END_FRAME_REQUIRED` | curl POST; assert HTTP 400 |
| 7 | Kim clicks "🔄 Regenerate B + C" WITH approved `end_frame_path` | Server reads PNG from disk; submits start+end to Kling; no OpenAI call; opt B + opt C entries appear in state | server log: `[add_options:startend] reading saved end_frame_path` |
| 8 | After 4 preview iterations on the same beat | Only 3 most-recent PNGs remain in `end_frames/<beat_id>_*.png`; oldest unlinked | `ls -la \| wc -l` |

### Topic 2 observables

| # | User action | Observable | Probe |
|---|---|---|---|
| T2-1 | Kim clicks "Add magic on still" from storyboard resolution view | path_picker URL has `&scope_video_role=resolution` | grep dist/index.html for the URL build site; manual smoke confirms |
| T2-2 | path_picker submits POST without scope_video_role | Server returns 400 VIDEO_ROLE_REQUIRED | curl POST without role |
| T2-3 | path_picker submits POST WITH scope_video_role=resolution | magic_still_path lands on `videos.resolution.beats.<beat_id>` | state probe; assert NOT in `videos.intro` |
| T2-4 | Response includes partition_written | JSON has `partition_written: "resolution"` | curl POST; jq |
| T2-5 | Kim clicks Preview Still on beat with magic_still_path | `<video src="/files?path=Production/Event_N/<magic_still_path>">` plays (NOT the still-as-final). Use `/files?path=` since magic writes to `event_dir`. | dist grep for `magic_still_path && magic_still_path_exists !== false` + `/files?path=`; curl `-I` on the `/files?path=…` URL |
| T2-6 | DS-22 read-back verify on magic write | If `mutate_partition` silently writes to wrong partition, server returns 500 `STATE_WRITEBACK_VERIFY_FAILED` (does NOT silently succeed). | code review of the verify block: assert it raises (not just logs) on mismatch |
| T2-7 | path_picker fallback to window.opener scope_video_role | If `/magic?...` URL has no `scope_video_role` BUT `window.opener.location.href` has one, path_picker reads it | code review of the scope-resolution block in path_picker.html line ~286; ordinary flow gets role via Bug-A1 anyway |
| T2-8 | Bug-B3 file_exists enrichment | `/api/state` and `/api/v2/event/<id>/state` annotate `magic_still_path_exists` / `magic_video_path_exists` / `end_frame_path_exists` on every beat with those fields set | curl + jq + assert presence + correct boolean for known-existing + known-orphan |

## §5 Out of scope (explicit)

- Storing `beat.end_frame_prompt_effective` in state (decided: NO — Kim's explicit dropped per 2026-05-20 inline)
- n=3 variants per "Preview end frame" click (decided: n=1, just click again for fresh sample)
- Audit-trail recording `end_frame_path` on each `phase_1.options[]` entry (decided: redundant since both opts B+C share the same end frame)
- Topic 4 systemic `or "intro"` ban (deferred to separate follow-up LD)
- Backfill end_frame_path for already-rendered options (no migration — applies to NEW Regen B+C clicks only)
- Animated GIF/video end frames (PNG only)
- Server-side prompt safety filtering beyond existing Rule 8 (no new filters)
- Migration of existing magic_still_path entries currently on `videos.intro.beats.beat_01` to the correct resolution partition (out of scope; Kim must re-render any beats whose magic landed on wrong partition before the fix)

## §6 Cursor cross-review prompt (final diff review)

Send this verbatim to cursor-agent at end of implementation, before declaring complete:

```
You are reviewing a diff that implements Production/docs/MAGIC_AND_ENDFRAME_FIXES_20260520_v1.md.

For each of the integration-contract observables in §4 (Topic 1 rows 1-8 + Topic 2 rows T2-1 to T2-8),
check the diff for the SPECIFIC code path that delivers that observable:

1. Cite file:line where the code lives
2. Identify any path that bypasses the contract (e.g. silent fallback to 'intro',
   silent OpenAI call when end_frame_path is set, missing pruning, missing
   refuse-without-end-frame at Regen B+C, swallowed verify failure)
3. Flag any string/path-shape that doesn't match what the contract probe would
   look for (e.g. partition_written field name typo, end_frame_path filename
   pattern drift, /asset/ vs /files? confusion)
4. Flag any out-of-scope changes that crept in
5. Look specifically for BUG-3-class lapses: code text shipped but unreachable
   (e.g. handler not bound to a route, helper function not called from intended
   site, scope-validator default that pre-empts new logic)
6. Verify Bug-A4 read-back verify is OUTSIDE the existing swallow-all try/except
   at background.py:712-713 (still) and ~995 (video) — NOT inside.

Output: per observable, one of {PASS / FAIL / NEEDS-PROBE} with one-line
justification citing file:line.

No code. Terse. Max 500 words total.
```

## §7 Pre-execution checklist

- [x] Concurrent-session check (zero running)
- [x] Branch created: `feature/magic-and-endframe-20260520`
- [x] Spec doc v1.0 written to disk (commit 0dadbe9)
- [x] Spec v1.1 incorporating cursor R1+R2 feedback
- [x] Spec registered in `prod_reference_docs` (id=232)
- [x] LD `MAGIC_ENDFRAME_FIXES_SPEC_20260520_V1` locked (id=814) with marker proof
- [x] Coordinator-start activity row in `prod_activity_log` (id=6172)
- [x] Cursor R1 review of spec → 5 changes folded
- [x] Cursor R2 review of spec → 3 more nits folded; verdict CONVERGED
- [ ] Phase 1 (Topic 2 implementation) begin
