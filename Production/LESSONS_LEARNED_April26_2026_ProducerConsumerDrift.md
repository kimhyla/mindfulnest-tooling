# Lessons Learned — April 26, 2026: Producer/Consumer Drift + Cache-Key Staleness

**Status:** Pinned reference. Two bugs in one session, same root pattern.
**Companions:** [LESSONS_LEARNED_LibrarySidebar_April24_2026_v2.md](LESSONS_LEARNED_LibrarySidebar_April24_2026_v2.md), [PATCH_V43_SPEC.md](tools/PATCH_V43_SPEC.md), `session_20260426_0700.md`.

---

## TL;DR

A new producer (state field, file path, audio output, anything stored) was added to one part of the system without auditing every downstream **consumer** AND every **cache** keyed on the previous assumption. Both today's bugs trace to this pattern. Yesterday's storyboard library bug was the parallel-implementations-racing variant. They're all the same root: **when you add or change what something means, the readers and caches built on the old meaning go silent-stale.**

---

## Bug 1 — `_serve_beat_audio` ignored storyboard-namespaced TTS subdir

**Producer:** `_tts_regenerate_for_beat` writes new audio to `story_scene_tts_v2/<storyboard_stem>/line_NN_<speaker>.mp3` (namespaced subdir adopted ~April 19–26).
**Consumer that broke:** All 7 callsites of `_find_beat_audio` in `production_server.py` (Preview Beat, lipsync submit ×2, animation duration ×3, text-edit staleness check). All called the resolver without `app=self.app`, so it fell through to scanning the parent dir and returned April-19 leftovers.
**Symptom:** Kim regen'd audio, server confirmed success, Preview Beat still played the old audio. Page refresh + server restart didn't help (bug was in code, not cache).
**Fix:** Added `app=self.app` to all 7 callsites at [production_server.py:6171, 6498, 6936, 7055, 7352, 7645, 7843](tools/production_server.py).
**Severity if unfixed:** Lipsync would submit stale audio to ByteDance — money + time burned on wrong takes.

## Bug 2 — `resolve_beat_file` ignored `beat.final` + normalized cache outlived its premise

**Producer A:** `_handle_use_as_final` ([production_server.py:6668](tools/production_server.py:6668)) writes `beat.final = {source, file, approved_at}` when Kim clicks "use as final (no lipsync)."
**Consumer that broke:** `resolve_beat_file` in [lib/ffmpeg_stitch.py:124](tools/lib/ffmpeg_stitch.py:124) checked only `beat.lipsync` (priority 1) and `phase_1.options` (priority 2). Skipped `beat.final` entirely. Stale lipsync silently shadowed Kim's explicit override.
**Producer B (the cache trap):** Even after fixing the resolver, the stitcher's normalized cache at `preview/normalized/{bid}_normalized.mp4` had been built from the OLD source. Cache invalidation logic was `src.mtime > norm.mtime`. When the resolver returned a different file path, the cache check compared the NEW source's mtime (Apr 14) against the cache built from the OLD source (Apr 26). New source older → "no rebuild needed" → trim + concat ran over the wrong data.
**Symptom:** Beat 1 stitched as Chipper (from stale lipsync-derived normalized) even though resolver correctly returned the Tessa option_A file. Code-level simulation showed the fix worked. Visible output didn't change.
**Fix:** Added priority 0 to `resolve_beat_file` checking `beat.final.file`. Source-keyed the normalized cache filename: `{bid}_normalized_{md5(src_path)[:10]}.mp4`. Archived 16 stale cache files into `preview/_archive_stale_pre_srckey_20260426/`.
**Severity if unfixed:** Final stitched MP4 silently uses wrong content for any beat where Kim used the "no lipsync" path.

---

## The pattern (rule, not anecdote)

When you add a new state field, a new file path, or change what an existing field means, **two passes** before declaring done:

1. **Consumer audit.** `grep` every reader that touches the OLD field/path/meaning. Each one needs to be updated or proven irrelevant. The number of callsites is the work, not the symptom.
2. **Cache audit.** Every cache keyed on the OLD assumption is a silent failure waiting for the next regen. Cache keys must encode the source's identity, not just its mtime. If a cache filename or hash doesn't change when the source identity changes, the cache invalidates wrong.

Code-level simulation ("I called the function, it returned the right thing") is **not proof** for user-visible bugs. Verify the visible artifact changed: extract a frame, hit the endpoint, md5 the bytes.

---

## Watch-fors

These are the smells that mean the pattern is back:

- "I edited the file, restarted the server, and the symptom is unchanged." → consumer or cache problem, not code.
- "Same content size, different hash filename." → fresh cache write, but content still derived from stale intermediate.
- "Worked yesterday, broke today after I clicked X." → X added a new producer; readers haven't caught up.
- "First time this beat/clip/file has been touched since the convention changed." → stale cache from before the change is now wrong.

---

## Rule references

- **Rule 27** (Delete Obsolete Workarounds) — `OBSOLETE_WORKAROUND_DELETION_V1`. Both bugs today are this rule. The mtime cache check was a workaround whose premise was "one source per beat forever"; the namespaced TTS subdir was a producer change without consumer-audit.
- **Rule 28** (Three-Bug Diagnosis) — `THREE_BUG_DIAGNOSIS_V1`. Bug 2 surfaced only after Bug 1 was fixed; the cache-key bug was a third concurrent layer. Fix-and-stop would have left the system half-broken.
- **Rule 29** (Server Staleness) — `SERVER_STALENESS_CHECK_V1`. Hit twice today (once correctly applied, once where I needed to also verify symptom moved).
- **Rule 33** (Verify Server and File Before Test) — `VERIFY_SERVER_AND_FILE_BEFORE_TEST_V1`. Needs strengthening: "verify VISIBLE OUTPUT changed, not just that code-level paths return new values."
