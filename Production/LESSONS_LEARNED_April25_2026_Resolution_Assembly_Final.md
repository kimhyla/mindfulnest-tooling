# Lessons Learned — April 25, 2026 — Event 1 Resolution Video: Final Assembly + Audio Mix

**Session window:** April 25, 2026 (continuation from April 24 session)  
**Primary outcome:** `event1_resolution_v35_1777168932.mp4` — 22.5s full resolution video, Kim approved ("save it. approved. DONE!")  
**Registered:** prod_assets id=38, prod_activity_log id=1282  
**Builds on:** `LESSONS_LEARNED_April24_2026_Resolution_Lipsync_Assembly.md` (produced v20 which this session uses as the base)

---

## Why this document exists

This session took the approved lipsync clip (v20) and assembled the complete Event 1 resolution video in 35 iterations. The core mistakes were: confusing which clip Kim meant, wrong pillarbox handling, silent audio streams breaking concat, wrong magic duration, wrong heartwood cut point, and wrong SFX placement. Each class is documented here.

---

## PART 1 — Source Clip Identification

### 1. "The approved clip with full audio" = tessa_resolution_final_v20.mp4

**What happened:** Many early iterations used wrong clips (beat01_tessa_exit_stitched_v1.mp4, tessa_resolution_lipsync_v1.mp4, separate per-beat clips). Kim kept saying "the approved one? the mp4 with full audio — the old full one."

**The answer:** `Production/Event_1/kling_clips/tessa_resolution_final_v20.mp4` — 18s, contains all 3 resolution scenes with lipsync dialogue, is the canonical approved source from the April 24 session.

**Rule:** When Kim references "the approved clip" without a filename, check prod_assets for the most recent registered video with "APPROVED" or "Kim verdict: approved" in notes. Do not guess from disk filenames — the disk has dozens of intermediates.

**v20 structure (locked reference):**
| Timecode | Content |
|----------|---------|
| t=0–5s | Tessa animated lipsync |
| t=5–9s | OLD "pee" magic trail (unwanted) |
| t=9–13.5s | Heartwood wide shot + magic |
| t=13.5–18s | Runestone activation |

Dialogue "whoah, where's it going now?" ends at t=5.864s (confirmed via silencedetect).

---

### 2. Use v20 directly as s1 — do not stitch separate lipsync clips

**What happened:** Many iterations tried to isolate the lipsync portion using separately-registered lipsync clips, which caused confusion about audio, timing, and which clip had what.

**The correct approach:** Copy v20 (`shutil.copy2`), trim the copy to exactly 6.0s. This:
- Preserves the complete lipsync + audio verbatim
- Cuts at the natural dialogue end (5.864s + 0.136s buffer = 6.0s)
- Shows only 0.136s of old magic at the cut point — imperceptible at the join with new magic
- Never touches the original v20

**Rule:** Never overwrite or modify v20. Copy first, trim the copy.

---

### 3. Never use freeze frames for lipsync segments

**What happened:** v27 attempted to freeze Tessa's face at t=5s while audio continued. Kim: "you cut off the lipsyncing for 'whoah where is it going', her mouth no longer moves."

**Rule:** Freeze frames destroy lipsync. If you need to hold a shot while dialogue finishes, extend the video clip — never freeze the frame. The source clip (v20) has animated mouth movement through t=5.864s; cutting at 6.0s preserves all of it.

---

## PART 2 — ffmpeg Assembly: Audio Streams

### 4. Every segment in a concat must have BOTH video AND audio streams

**What happened:** Silent segments (magic sparkle trail, heartwood extracted without audio) had no audio stream. ffmpeg concat demuxer dropped all audio from the entire output when even one segment was missing an audio stream.

**The fix:** Add a synthesized silent audio stream to every video-only segment:
```python
# In filter_complex:
"anullsrc=r=44100:cl=mono,atrim=duration=3.5[aout]"
```

**Rule:** Before concat, run `ffprobe -show_streams` on EVERY input segment and confirm each has both `codec_type: video` and `codec_type: audio`. If any is missing audio, add anullsrc before concat. Never concat without checking first.

---

### 5. anullsrc must be bounded with atrim when used in filter_complex

**What happened:** `anullsrc=r=44100:cl=mono` generates infinite silence. In filter_complex, without `atrim`, ffmpeg tries to process an infinite stream and either hangs or produces unexpected duration.

**Rule:**
```python
# WRONG:
"anullsrc=r=44100:cl=mono[aout]"

# CORRECT:
"anullsrc=r=44100:cl=mono,atrim=duration=3.5[aout]"
```
Always pair anullsrc with `atrim=duration=X` where X matches the video segment duration exactly.

---

### 6. ffmpeg concat.txt requires absolute paths

**What happened:** Using relative paths (e.g., `file 's1.mp4'`) in the concat list caused ffmpeg to fail silently or error out depending on the working directory.

**Rule:** Always write absolute paths in concat.txt:
```python
concat_list.write_text("\n".join(f"file '{str(f.resolve())}'" for f in seg_files))
```

---

## PART 3 — Magic Trail Production

### 7. MagicCompositor requires a STILL PNG — extract programmatically, not by screenshot

**What happened:** Kim asked "you shouldn't just take a screenshot, won't that degrade the quality?" Screenshots are low-res pixel grabs. The correct method is programmatic frame extraction.

**The correct technique:**
```bash
ffmpeg -ss 1.0 -i source.mp4 -vframes 1 -update 1 -q:v 1 /tmp/frame_1.0s.png
```
This produces a lossless 1280×720 PNG at exactly the specified timestamp.

**Rule:** Always extract frames with ffmpeg. Never use screenshots as MagicCompositor source images.

---

### 8. Extract multiple candidate frames and let Kim choose — do not pick one yourself

**What happened:** The first frame choice (t=4.95s) had a weird face expression. Kim rejected it. A second round at t=1.0s (wide eyes, neutral) was accepted.

**Rule:** Extract frames at multiple timestamps (1.0s, 2.0s, 3.0s, 3.5s, 4.0s, 4.5s), open them all in Preview or Finder for Kim to review, then use whichever she selects. Do not make the visual judgment yourself.

**Locked result:** t=1.0s from v20 — Tessa with wide eyes looking up, neutral expression — is the approved background for the Event 1 magic sparkle trail.

---

### 9. Magic trail duration: 3.5s for the tessa_exit_right path

**What happened:**
- 2.0s: Trail didn't reach screen edge (x=1.0). Kim: "the magic trail didn't get all the way to the edge."
- 3.5s: Trail reaches edge and looks good.
- 5.0s: Too slow.

**Rule:** For the `tessa_exit_right` path (path_pts ending at x=1.0), minimum duration to reach the screen edge is 3.5s. The approved magic segment is 3.5s.

---

### 10. Heartwood source cut point: v20 t=10.0s, not t=13.0s

**What happened:** First attempt used v20 t=13.0s as the heartwood section start, which gave only 5s of content. Kim: "you cut out too much of that scene."

**Rule:** s3 (heartwood+runestone) starts at v20 t=10.0s. This gives 8s of natural-paced content ending at v20 t=18s. Never cut past t=10.0s — that removes too much of the heartwood approach.

**Final s3 parameters:** `ffmpeg -ss 10.0 -i v20.mp4` — 8.0s duration.

---

## PART 4 — Guidebird / Pillarboxing

### 11. Guidebird source (720×544) must be pillarboxed, never stretched

**What happened:** First attempt stretched the 720×544 guidebird clip to 1280×720, causing visible distortion. Kim flagged it as "stretched" in the first review.

**The correct pillarbox filter:**
```python
VSCALE = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black"
```

This preserves the 720×544 aspect ratio and adds black bars on left/right.

**Rule:** Always check source resolution with ffprobe before assuming codec params. For any non-1280×720 source, use AR-preserving scale+pad, never a direct scale to 1280×720.

---

## PART 5 — Ambient Bed + SFX Mixing

### 12. Ambient bed for Event 1: option2.mp3 at -26dB, 2.5s fade-in, 2.0s fade-out

**What happened:** Kim confirmed the ambient bed for the resolution video should match the intro. The intro (prod_assets id=6) uses `ambient bed pretty option2.mp3` mixed at -26dB.

**Locked parameters for all Event 1 videos:**
```python
ambient = "Production/ambient bed pretty option2.mp3"
volume = "-26dB"
fadein = 2.5   # seconds
fadeout = 2.0  # seconds
```

**ffmpeg filter:**
```python
f"[1:a]atrim=0:{dur},asetpts=PTS-STARTPTS,"
f"afade=t=in:st=0:d=2.5,"
f"afade=t=out:st={fadeout_start}:d=2.0,"
f"volume=-26dB[bed];"
f"[0:a][bed]amix=inputs=2:duration=first:normalize=0[aout]"
```

---

### 13. Find ambient bed source via Directus notes, not by guessing disk files

**What happened:** First attempt to identify the intro's ambient bed involved guessing from disk filenames (wooden flute files, `meditation_pretty_v1.mp3`). Both were wrong. Kim: "wildly wrong."

**The correct method:** Query `prod_assets` or `prod_activity_log` for the registered intro video entry. The activity log notes for the Phase A audio mix (prod_assets id=27) explicitly state: "mixed with ambient bed meditation_pretty_v1.mp3." The intro v5 (prod_assets id=6) notes say "ambient bed option2.mp3 seamless loop."

**Rule:** When identifying which audio file was used in an approved video, read the Directus registration notes first. Don't search the disk by filename pattern.

---

### 14. Magic SFX placement: at the moment of VISIBLE magic, not at total duration

**What happened:** First SFX placement was at t=19.84s (near end of video). Kim: "you put it in at the wrong sub-second of 0.22, it should be at the moment corresponding to the shot with the one glowing orange runestone."

**What "00.22" in Kim's message meant:** The 00:22 timestamp shown in QuickTime's player bar is the TOTAL DURATION (not a target offset). Kim meant the orange runestone shot, which occurs at approximately t=15.9s in v35.

**Locked SFX parameters:**
```python
sfx_file = "magic burst sound for in video.mp3"  # 2.66s
sfx_start = 15.9   # t= in final video (orange runestone activation)
volume = 0.45      # not crazy loud
fadein = 0.3       # gentle rise
fadeout = 1.2      # trails into guidebird (starts t=17.5s)
```

The 2.66s SFX at t=15.9s ends at t=18.56s — about 1s into the guidebird segment, matching Kim's "let it trail into the first second or two of the final clip."

---

### 15. "00.22" notation = QuickTime's displayed total duration, not a sub-second or minute mark

**What happened:** Kim wrote "snip it directly over minute 00.22" which parsed ambiguously. The QuickTime player showed 00:17 / 00:22 (current / total). She meant: position it at the 00:22 area (near end), specifically at the orange runestone visual.

**Rule:** When Kim references a timestamp from a QuickTime screenshot, read both the current-position number AND the total-duration number visible in the player, and determine which one she's referencing by context (what's visible on screen at that moment).

---

## PART 6 — Directus Registration

### 16. prod_assets status enum: "approved" is not a valid value

**What happened:** Trying to write `status: "approved"` to prod_assets returned HTTP 500: `invalid input value for enum prod_asset_status: "approved"`.

**The only valid value:** `"pending"` (confirmed from existing rows). Record Kim's approval in the `notes` field instead.

**Template:**
```python
asset_payload = {
    "module_id": 1,           # integer, required
    "asset_type": "video",
    "asset_name": "event1_resolution_v35_APPROVED",
    "file_path": "Production/...",
    "status": "pending",      # only valid enum value
    "notes": "KIM APPROVED 2026-04-25. [description]"
}
```

---

### 17. prod_activity_log module_id is an integer, not "m1"

**What happened:** Posting `module_id: "m1"` returned HTTP 500: `invalid input syntax for type integer: "m1"`.

**Rule:** `prod_activity_log.module_id` is an integer column. Use the integer (e.g., `1`) or omit it (NULL). Never pass the string "m1".

**Working template:**
```python
log_payload = {
    "action": "event1_resolution_v35_APPROVED — [description]. Kim: approved DONE 2026-04-25.",
    "kim_verdict": "approved"
    # module_id omitted (NULL) — avoids type error
}
```

---

### 18. prod_assets module_id is required (NOT NULL)

**What happened:** Omitting module_id returned HTTP 400: `Value is required for field module_id`.

**Rule:** Always include `"module_id": 1` (integer) in prod_assets writes. It cannot be null.

---

### 19. prod_visual_assets returns 403 on certain filter queries

**What happened:** Querying `prod_visual_assets` with `filter[event_id][_eq]=e1` returned HTTP 403. The collection has stricter access rules than prod_assets.

**Rule:** For registered deliverables, use `prod_assets`. For production stills/images in the pipeline, use `prod_visual_assets` only without complex filters if access issues arise. When in doubt, use prod_assets for all registration writes.

---

## PART 7 — The Approved Final Assembly

### 20. Final v35 construction (locked for reference)

```
SOURCE CLIPS:
  s1: v20 copy, cut to 6.0s          (Tessa lipsync + dialogue)
  s2: MagicCompositor on t=1.0s frame (sparkle trail 3.5s, tessa_ori style, seed=99)
  s3: v20 from t=10.0s, 8.0s          (heartwood + runestone, natural pace)
  s4: guidebird_beat01_lipsync_final_1777161280.mp4, pillarboxed (4.96s)

NORMALIZATION (all segments):
  video: scale=1280:720:force_original_aspect_ratio=decrease,pad=...color=black
  audio: aresample=44100,aformat=sample_fmts=fltp:channel_layouts=mono
  codec: libx264 / yuv420p / 24fps / crf=18 / aac 128k mono

CONCAT: ffmpeg concat demuxer, then fade in 0.5s / fade out 0.5s

AMBIENT BED (v34 step):
  ambient bed pretty option2.mp3 at -26dB, fadein=2.5s, fadeout=2.0s

MAGIC ZING (v35 step):
  magic burst sound for in video.mp3 at t=15.9s, vol=0.45, fadein=0.3s, fadeout=1.2s

TOTAL DURATION: 22.5s
OUTPUT: event1_resolution_v35_1777168932.mp4 (4.26 MB)
REGISTERED: prod_assets id=38
```

---

## PART 8 — Process Lessons

### 21. Check Directus before guessing at disk files for any "approved" asset

Three times this session, guessing disk filenames led to the wrong answer (lipsync clips, music files, ambient bed). The correct flow:
1. Query `prod_assets` with a text search in notes for "APPROVED", "Kim verdict", or the scene name
2. Read the notes field — it contains exact filenames of all components used
3. Only then go to disk to open/use the file

### 22. QuickTime Player is mandatory for all audio/video review

Never use computer:// links (auto-play, no pause control) or HTML players (break in Cowork). Always:
```bash
open -a "QuickTime Player" /path/to/file.mp4
```

### 23. Iteration table — v33 through v35

| Version | What changed | Outcome |
|---------|-------------|---------|
| v33 | First clean assembly: s1+s2+s3+s4, pillarbox fixed, audio fixed | Kim: "ok!!! Fine!! fair enough!!!" |
| v34 | + ambient bed option2 at -26dB, 2.5s/2s fade | Kim: "that's fine" |
| v35 | + magic zing sfx at t=15.9s, vol=0.45, trailing into guidebird | Kim: "save it. approved. DONE!" |
