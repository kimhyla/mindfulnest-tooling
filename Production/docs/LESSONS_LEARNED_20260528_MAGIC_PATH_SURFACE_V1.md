# Lessons Learned — Magic Path Surface Lock (2026-05-28)

## Symptom

Magic trail on beat_01 (resolution / Tessa) appeared as a straight diagonal across the frame, unrelated to the circular path Kim drew on the turtle shell.

## Root causes (ranked)

1. **Stale render on disk** — `magic_video_beat_01_20260527-222702.mp4` predates correct path drawing. Agent smoke tests on 2026-05-27 overwrote production state with 2-point diagonal test paths (documented in `CURSOR_CONSULT_3BUGS_20260527_v1.md`).

2. **Draw surface ≠ composite surface** — V2 drew paths against the scene still; v59 `magic_video` must draw against **frame 0 of the lipsync clip** (720×544). The still crop is 1236×927 with different framing. Same aspect ratio (~1.33) fooled the old `_aspect_correct` AR-only heuristic — no correction applied, path landed on wrong pixels.

3. **Dimension drift** — `handle_magic_video` decoded at raw ffprobe W×H while `MagicCompositor` could crop odd dimensions; trail tensor and RGB decode buffer could diverge by 1px.

4. **Misleading UI copy** — path_picker said “draw on the still reference” for `magic_video` mode after CANVAS_MISMATCH_FIX already switched to video frame loading.

## V2 vs v59

| V2 | v59 |
|----|-----|
| `scene_registry.yaml` + async path submit | One-shot POST `/api/storyboard/magic_video` |
| Path + scene geometry co-located | Beat stores output filename only (`magic_video_path`) |
| Single canonical bg per scene | Still crop vs lipsync video are different surfaces |

## Fix (LD-828) — one canvas, three places

**Invariant:** path_picker canvas, `/api/storyboard/video_frame`, and `MagicCompositor` + ffmpeg decode MUST share the same even W×H.

1. `_magic_canvas_dims()` — even-width/height crop (libx264 rule).
2. `handle_storyboard_video_frame` — ffprobe + `scale=W:H` before PNG pipe.
3. `path_picker applyImage` — same even dims + `path_authored_against`.
4. `handle_magic_video` — reject `PATH_SURFACE_MISMATCH` when authored dims ≠ video dims; composite at `mc.W` × `mc.H`.
5. Persist `magic_manual_path` + `magic_path_authored_against` on beat for audit/re-render.

## Operator steps after deploy

1. Hard refresh storyboard (`Cmd+Shift+R`).
2. Click **Add magic on video** (not still) for beat_01.
3. Confirm path picker shows **lipsync frame** (720×544), not still crop.
4. Draw 4–8 points on the shell arc; submit.
5. Preview Still — new filename timestamp must differ from `20260527-222702`.

## Locked decisions

- **LD-828** `MAGIC_PATH_SURFACE_DIM_LOCK_V1` — no AR-only correction; exact dim match required for magic_video.
- **LD-829** `MAGIC_MANUAL_PATH_STATE_PERSIST_V1` — beat stores last submitted path for debugging.
- **LD-831** `MAGIC_PATH_POLYLINE_INTERP_V1` — `manual_path` / path_picker points are connected with straight segments (`polyline`), NOT de Casteljau Bezier smoothing. path_picker canvas uses `lineTo`; compositor must match point-for-point.
