> ⚠️ **SUPERSEDED 2026-05-03** — This spec describes the original gpt-image-1 prompt with `_GPT_SPECIES_ANCHOR` text descriptions. Current production architecture is:
> - **Model:** `gpt-image-2` per LD-440 (was gpt-image-1 in this doc)
> - **Prompt:** image-led ~380-char per LD-439 (was 1152-char species-anchor in this doc)
> - **Code source of truth:** `Production/tools/beat_generator.py:934-947` for `build_gpt_still_prompt()`
> Refer to LD-439 + LD-440 for current architecture; this doc is retained for historical context only. Banner added in S5.5a1 LD housekeeping (preflight #194).

# GPT Stills Generation — Full Technical Specification v1
**Date:** 2026-04-26  
**Status:** SUPERSEDED 2026-05-03 (originally: Ready for CLI implementation)  
**Produced by:** Three-axis Opus debate (prompt / architecture / UX) + Desktop synthesis  
**Decision basis:** Existing `beat_generator.py` + `production_server.py` audit + API_KEYS_MASTER.md verification + Kim's confirmed workflow  

---

## 0. Purpose and Scope

Switch MindfulNest's Beat Generator still-image generation from FLUX Kontext Pro (BFL API) to OpenAI `gpt-image-1` (OpenAI `/v1/images/edits`). The switch addresses the root cause of visual inconsistency: the current FLUX pipeline composites character + background into a side-by-side JPEG and passes it as a single reference — FLUX cannot semantically separate "the left half is the character, the right half is the background." GPT accepts them as truly distinct inputs.

**In scope:** `beat_generator.py` additions, `production_server.py` additions, storyboard HTML patch (new "GPT Stills" button + render update).  
**Out of scope:** FLUX pipeline removal (FLUX stays as fallback), Kling animation pipeline, lipsync pipeline, Directus registration of final accepted stills (already handled by existing accept-option flow).

---

## 1. Success Criteria

- Kim clicks "GPT Stills" on a beat card → 3 options appear in the option slots, all showing the character naturally composited into the background
- Character is visually consistent across 3 options (same proportions, colors, species identity)
- No side-by-side composite artifact (split-frame, palette bleed)
- FLUX options already in the sidecar continue to render correctly (zero regression)
- Total time from button click to 3 images visible: ≤ 45 seconds for one beat
- No server crash or hang under a 5-beat batch (15 concurrent GPT calls)

---

## 2. Architecture Overview

```
Kim drags BG ref image → bg-ref-slot on beat card   (already exists, no change)
Kim clicks "GPT Stills" button (NEW)
        ↓
POST /api/bg/submit-gpt-batch  {beat_ids: [...]}
        ↓ returns {job_id, beat_ids} immediately
Background ThreadPoolExecutor(max_workers=6)
        ↓ for each beat × 3 options (flat task queue):
        ↓   open(char_ref), open(bg_ref)
        ↓   call OpenAI /v1/images/edits  [gpt-image-1]
        ↓   decode base64 → save PNG to beat_generator_stills/
        ↓   generate thumb → write to sidecar beat["gpt_options"][i]
        ↓
Client polls GET /api/bg/poll-gpt-status?job_id=xxx  (every 5s, same cadence as FLUX)
        ↓ returns per-slot {status, key, thumb_b64, gallery_b64} as slots complete
UI swaps in each option thumbnail as it arrives (streaming display)
        ↓
Kim accepts option → existing accept-option flow unchanged
```

---

## 3. Locked Decisions

| # | Decision | Rationale |
|---|---|---|
| GPT-1 | Model: `gpt-image-1` | Already in API_KEYS_MASTER.md, tested manually by Kim |
| GPT-2 | Two separate `image[]` inputs (char + bg) | NOT side-by-side composite — this is the root fix |
| GPT-3 | Keep async job_id pattern (POST → poll) | 5-beat batch = 15 calls × 25s = too long to block HTTP |
| GPT-4 | Write to `gpt_options[]` sidecar field (separate from `flux_options[]`) | Zero regression — existing render reads `flux_options` unchanged |
| GPT-5 | UI render reads `beat.gpt_options \|\| beat.flux_options` | Single line change, backward compatible |
| GPT-6 | BG ref slot unchanged — Kim always drags manually | Slot already exists; no auto-detect logic (any location/scene auto-detect is an error) |
| GPT-7 | `ThreadPoolExecutor(max_workers=6)` flat across all beats × options | I/O-bound; 6 in-flight saturates throughput without hitting rate limit (~50 img/min tier-2) |
| GPT-8 | Image size `1024x1024` | Feeds Cropper for 4:3 crop; Rule 6 upscale handles shortest-side enforcement |
| GPT-9 | Cost recorded in sidecar `gpt_options[i].cost_usd` + one `prod_activity_log` row per job | Per Rule 31 Directus is canonical for cost queries |
| GPT-10 | Failed option slot: write `{error, key, source}` — don't drop | Kim can see which slots failed; per-slot "Regenerate" (future) |
| GPT-11 | Prompt: species anchor first, then pose/emotion, then scene integration, then style lock | Order matters — GPT weights early tokens for identity preservation |
| GPT-12 | 3 variation prompts differ ONLY in pose/framing — never in species anchors or style | Prevents character drift across options |

---

## 4. File Changes Required

### 4.1 `Production/tools/beat_generator.py` — ADDITIONS ONLY

Insert after line 648 (end of `poll_batch`), before `process_still_image`:

**A. `_openai_api_key()`** — reads `sk-proj-...` key from API_KEYS_MASTER.md, same pattern as `_bfl_api_key()`.

**B. `_make_gpt_thumb(img_bytes)`** — PIL thumbnail helper, returns `(thumb_b64, gallery_b64)`. Inline (don't call `process_still_image` — that function's filename scheme conflicts with GPT's naming).

```python
def _make_gpt_thumb(img_bytes):
    """Generate thumb + gallery b64 from raw PNG bytes. Returns (thumb_b64, gallery_b64)."""
    try:
        from PIL import Image as _PIL
        import io as _io
        img = _PIL.open(_io.BytesIO(img_bytes)).convert("RGB")
        # Rule 6: shortest side ≥ 600px
        w, h = img.size
        if min(w, h) < 600:
            scale = 600 / min(w, h)
            img = img.resize((int(w * scale), int(h * scale)), _PIL.LANCZOS)
        # Thumbnail
        thumb = img.copy()
        thumb.thumbnail((200, 150), _PIL.LANCZOS)
        buf = _io.BytesIO()
        thumb.convert("RGB").save(buf, "JPEG", quality=72)
        thumb_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        # Gallery (600px longest side)
        gallery = img.copy()
        gallery.thumbnail((600, 600), _PIL.LANCZOS)
        buf2 = _io.BytesIO()
        gallery.convert("RGB").save(buf2, "JPEG", quality=82)
        gallery_b64 = "data:image/jpeg;base64," + base64.b64encode(buf2.getvalue()).decode()
        return thumb_b64, gallery_b64
    except Exception as e:
        print(f"[GPT] thumb generation failed: {e}")
        return "", ""
```

**C. `_GPT_SPECIES_ANCHOR`** dict — per-character identity lock strings:

```python
_GPT_SPECIES_ANCHOR = {
    "Tessa":   ("small green sea turtle",
                "pale jade shell with darker edge plates, oversized round expressive eyes, "
                "short stubby limbs, no neck wrinkles"),
    "Luna":    ("small owl",
                "dark charcoal-brown feathers, enormous round amber eyes, "
                "white facial disc, compact rounded body"),
    "Benson":  ("small bunny",
                "soft grey fur, long upright ears, wide anxious kind eyes, "
                "small pink nose, white underbelly"),
    "Ember":   ("fox kit",
                "bright auburn-orange fur, white chest and muzzle, "
                "alert triangular ears, bushy tail"),
    "Bork":    ("tiny firefly",
                "translucent wings, round glowing abdomen with warm yellow-green bioluminescence, "
                "tiny compound eyes"),
    "Bramble": ("large bear",
                "mossy dark brown fur with patches of green lichen, "
                "gentle giant proportions, small round ears, soft dark eyes"),
    "Chipper": ("small songbird",
                "warm orange-yellow plumage, round compact body, "
                "tiny black eyes, short orange beak CLOSED"),
    "Cedric":  ("old wizard",
                "long flowing blue-grey robes with star motifs, "
                "long white beard, pointed hat, wise kind expression"),
}
```

**D. `_GPT_VARIATION_POSE`** — 3 safe pose/framing variations:

```python
_GPT_VARIATION_POSE = [
    ("facing the viewer, centered in frame, medium shot",
     "weight evenly balanced, calm open stance"),
    ("slightly turned to three-quarter view, medium shot",
     "weight shifted, one step mid-motion"),
    ("centered in frame, medium-wide shot with more background visible",
     "natural relaxed posture"),
]
```

**E. `_emotion_to_body_mechanics(emotion_raw, dialogue="")`** — converts free-form emotion text to visible body language:

```python
def _emotion_to_body_mechanics(emotion_raw, dialogue=""):
    e = (emotion_raw or "").lower()
    d = (dialogue or "").lower()
    if any(w in e for w in ["ecstatic", "spinning", "can't contain", "jumping"]):
        return "mid-spin with arms spread wide, head tilted back, eyes wide and crinkled"
    if any(w in e for w in ["shocked", "stunned", "realization"]):
        return "eyes wide open, leaning slightly back, surprised expression"
    if any(w in e for w in ["pained", "embarrassed", "ashamed"]):
        return "shoulders drawn in, eyes averted downward, body angled slightly away"
    if any(w in e for w in ["warm", "gentle", "kind", "tender"]):
        return "leaning slightly forward, gentle open posture, soft warm expression"
    if any(w in e for w in ["excited", "energetic", "bouncing"]):
        return "upright posture, slight forward lean, bright alert expression"
    if any(w in e for w in ["sad", "sorrowful", "tears"]):
        return "slightly hunched, eyes downcast, soft sad expression"
    if any(w in e for w in ["curious", "wondering", "puzzled"]):
        return "head tilted to one side, eyes bright with inquiry"
    if any(w in e for w in ["determined", "brave", "resolve"]):
        return "chin raised, shoulders back, direct forward gaze"
    if any(w in e for w in ["camera", "warmly", "to camera"]):
        return "facing directly forward, warm inviting expression, slight forward lean"
    if any(w in d for w in ["?", "what", "how", "why"]):
        return "quizzical expression, head slightly tilted"
    return "calm attentive expression, natural relaxed posture"
```

**F. `build_gpt_still_prompt(beat, option_variation=0)`**:

```python
def build_gpt_still_prompt(beat, option_variation=0):
    speaker = beat.get("speaker", "Chipper")
    emotion_raw = beat.get("emotion", "")
    dialogue = beat.get("text", "") or beat.get("dialogue_text", "")

    species, anchors = _GPT_SPECIES_ANCHOR.get(
        speaker,
        (f"{speaker} character", "Pixar 3D animated style, cartoon proportions")
    )
    emotion_body = _emotion_to_body_mechanics(emotion_raw, dialogue)
    pose_position, body_stance = _GPT_VARIATION_POSE[option_variation % 3]

    return (
        f"A single {species} character composited naturally into the provided background scene. "
        f"CHARACTER from reference image 1: {species} with {anchors}. "
        f"Maintain EXACT proportions, colors, and facial features from the reference. "
        f"Identity lock: this is {speaker}, a {species}. "
        f"POSE: {speaker} is {emotion_body}. "
        f"{body_stance}, {pose_position}. "
        f"SCENE INTEGRATION from reference image 2: "
        f"Place {speaker} in the background scene. "
        f"Match the scene's lighting direction, color temperature, and atmospheric haze. "
        f"Character feet firmly on the ground surface with a soft contact shadow. "
        f"STYLE: Pixar 3D animated feature film still, subsurface scattering on skin, "
        f"warm cinematic lighting, expressive cartoon proportions, high detail. "
        f"NOT flat, NOT 2D illustration, NOT anime, NOT photorealistic. "
        f"PROHIBIT: no text, no watermarks, no UI elements, no second character, "
        f"no humans, no open mouth, no teeth showing, no extra limbs, no logos."
    )
```

**G. `submit_gpt_stills(beat, num_options=3)`** — synchronous, returns list of result dicts:

```python
def submit_gpt_stills(beat, num_options=3):
    """Synchronous GPT still generation. Returns list of result dicts, one per option.
    Each dict: {local_path, key, filename, source, cost_usd, thumb_b64, gallery_b64}
    or {error, key, source} on failure. Run in a thread for non-blocking behavior."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai SDK not installed — run: pip install openai")

    api_key = _openai_api_key()
    client = OpenAI(api_key=api_key)
    beat_id = beat.get("beat_id", "unknown")
    speaker = beat.get("speaker", "")

    # Resolve character reference (per-beat override → creature master)
    override = beat.get("reference_image")
    if override and os.path.exists(override):
        char_ref = override
    else:
        _c = _CREATURE_REFS.get(speaker)
        char_ref = os.path.normpath(_c) if _c and os.path.exists(_c) else None
    if not char_ref:
        raise RuntimeError(f"[GPT] No character reference found for speaker '{speaker}'. "
                           f"Check Character_Assets/{speaker.lower()}_reference_master.png")

    # Resolve background reference (Kim always drags manually — no auto-detect)
    bg_ref = beat.get("bg_ref_image")
    if bg_ref and not os.path.exists(bg_ref):
        print(f"[GPT] bg_ref_image missing on disk, ignoring: {bg_ref}")
        bg_ref = None

    os.makedirs(BG_STILLS_DIR, exist_ok=True)
    results = []

    for opt_idx in range(num_options):
        prompt = build_gpt_still_prompt(beat, option_variation=opt_idx)
        key = f"bg_{beat_id}_gpt_opt{opt_idx}"
        try:
            # Open fresh file handles each iteration (position resets)
            open_files = []
            image_inputs = []
            try:
                f_char = open(char_ref, "rb")
                open_files.append(f_char)
                image_inputs.append(f_char)
                if bg_ref:
                    f_bg = open(bg_ref, "rb")
                    open_files.append(f_bg)
                    image_inputs.append(f_bg)

                response = client.images.edit(
                    model="gpt-image-1",
                    image=image_inputs,
                    prompt=prompt,
                    n=1,
                    size="1024x1024",
                    response_format="b64_json",
                )
            finally:
                for f in open_files:
                    f.close()

            img_bytes = base64.b64decode(response.data[0].b64_json)
            ts = int(time.time())
            filename = f"bg_{beat_id}_gpt_opt{opt_idx}_{ts}.png"
            local_path = os.path.join(BG_STILLS_DIR, filename)
            with open(local_path, "wb") as out:
                out.write(img_bytes)

            thumb_b64, gallery_b64 = _make_gpt_thumb(img_bytes)
            print(f"[GPT] ✓ {beat_id} opt{opt_idx}: {filename}")
            results.append({
                "local_path": local_path,
                "key": key,
                "filename": filename,
                "source": "gpt-image-1",
                "cost_usd": 0.08,
                "thumb_b64": thumb_b64,
                "gallery_b64": gallery_b64,
            })
        except Exception as e:
            print(f"[GPT] ✗ {beat_id} opt{opt_idx}: {e}")
            results.append({"error": str(e), "key": key, "source": "gpt-image-1"})

        time.sleep(0.5)

    return results
```

---

### 4.2 `Production/tools/production_server.py` — ADDITIONS ONLY

**A. In-memory job registry** — add near the top of the server class or as module-level:

```python
import concurrent.futures as _cf

_GPT_JOBS = {}          # job_id → {"status": "running"|"done", "results": {beat_id: [...]}}
_GPT_EXECUTOR = None    # lazy-init ThreadPoolExecutor

def _gpt_executor():
    global _GPT_EXECUTOR
    if _GPT_EXECUTOR is None:
        _GPT_EXECUTOR = _cf.ThreadPoolExecutor(max_workers=6, thread_name_prefix="gpt-stills")
    return _GPT_EXECUTOR
```

**B. `_handle_bg_submit_gpt_batch(body)`** — new handler, mirrors `_handle_bg_submit_flux`:

```python
def _handle_bg_submit_gpt_batch(self, body):
    """POST /api/bg/submit-gpt-batch {beat_ids: [...]}
    Spawns GPT generation in background. Returns {job_id, beat_ids} immediately."""
    beat_ids = body.get("beat_ids", [])
    if not beat_ids:
        return self._send_json(400, {"error": "beat_ids required"})

    job_id = str(uuid.uuid4())[:8]
    bg = _bg_module()
    with bg._sidecar_lock:
        sidecar = bg._load_sidecar_migrated()

    beats_to_run = []
    for bid in beat_ids:
        _, beat = bg.find_beat(sidecar, bid)
        if beat:
            beats_to_run.append(dict(beat))  # snapshot (avoid lock contention in thread)

    _GPT_JOBS[job_id] = {"status": "running", "results": {}, "total": len(beats_to_run) * 3}

    def _run_job():
        futures = {}
        executor = _gpt_executor()
        for beat in beats_to_run:
            bid = beat["beat_id"]
            future = executor.submit(bg.submit_gpt_stills, beat, 3)
            futures[future] = bid

        for future in _cf.as_completed(futures, timeout=300):
            bid = futures[future]
            try:
                results = future.result()
                # Write to sidecar
                with bg._sidecar_lock:
                    sc = bg.read_sidecar()
                    _, beat_obj = bg.find_beat(sc, bid)
                    if beat_obj:
                        beat_obj["gpt_options"] = results
                        beat_obj["status"] = "stills_ready"
                    bg.write_sidecar(sc)
                _GPT_JOBS[job_id]["results"][bid] = results
            except Exception as e:
                print(f"[GPT] job {job_id} beat {bid} error: {e}")
                _GPT_JOBS[job_id]["results"][bid] = [{"error": str(e)}]

        _GPT_JOBS[job_id]["status"] = "done"
        # Log to activity log (Directus)
        try:
            total_cost = sum(
                r.get("cost_usd", 0)
                for opts in _GPT_JOBS[job_id]["results"].values()
                for r in opts if isinstance(r, dict)
            )
            _log_activity(f"GPT stills job {job_id}: {len(beats_to_run)} beats, "
                          f"~${total_cost:.2f}", task_category="stills_generation")
        except Exception:
            pass

    import threading
    threading.Thread(target=_run_job, daemon=True, name=f"gpt-job-{job_id}").start()

    return self._send_json(200, {"ok": True, "job_id": job_id,
                                  "beat_ids": beat_ids, "total_options": len(beats_to_run) * 3})
```

**C. `_handle_bg_poll_gpt_status()`** — GET handler:

```python
def _handle_bg_poll_gpt_status(self):
    """GET /api/bg/poll-gpt-status?job_id=xxx
    Returns per-beat option results as they complete."""
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
    job_id = (qs.get("job_id") or [""])[0]
    if not job_id or job_id not in _GPT_JOBS:
        return self._send_json(404, {"error": f"job {job_id} not found"})

    job = _GPT_JOBS[job_id]
    return self._send_json(200, {
        "status": job["status"],
        "results": job["results"],   # {beat_id: [{local_path, key, thumb_b64, ...}, ...]}
        "total": job["total"],
        "done_count": sum(len(v) for v in job["results"].values()),
    })
```

**D. Route additions** — in the server's routing/dispatch block, add alongside the flux routes:

```python
# In POST dispatch:
if path == "/api/bg/submit-gpt-batch":
    return self._handle_bg_submit_gpt_batch(body)

# In GET dispatch:
if path.startswith("/api/bg/poll-gpt-status"):
    return self._handle_bg_poll_gpt_status()
```

---

### 4.3 Storyboard HTML — Path B patch (new file: `patch_v49_gpt_stills_button.py`)

**Target:** Apply to current active storyboard version (v47 or whichever Kim is on).

Inject a `<script>` block before `</html>` that:

**A. Adds global GPT mode state:**
```javascript
var BG_GEN_MODE = 'gpt'; // 'gpt' | 'flux' — default GPT
```

**B. Adds "⚡ GPT Stills" button** to each beat card's action row (in `_bgRenderBeats`), alongside existing Generate Stills button. Minimal change: the existing per-beat generate button is overloaded with a mode toggle, OR a second small button is added. Recommended: small mode badge `[GPT ▾]` on the existing "Generate Stills" button.

Actually simpler: replace the call in `_bgSubmitBeat` to check `BG_GEN_MODE` and route to either `/api/bg/submit-flux-batch` or `/api/bg/submit-gpt-batch`.

**C. Updates `_bgRenderBeats` option display** — one line change:
```javascript
// Before:
var options = beat.flux_options || [];
// After:
var options = beat.gpt_options || beat.flux_options || [];
```

**D. Adds GPT poll loop** — mirrors existing FLUX poll logic, calls `/api/bg/poll-gpt-status?job_id=xxx`, updates option slots as results arrive.

**E. Adds GPT mode toggle button** in the Beat Generator toolbar (alongside "⚡ Generate All Stills"):
```html
<button id="bg-gen-mode-btn" class="b" onclick="_bgToggleGenMode()">Mode: GPT ✨</button>
```

**Full patch script:** `Production/tools/patch_v49_gpt_stills_button.py` — Path B pattern (read → SHA256 → inject → verify → write).

---

## 5. Implementation Order (CLI Terminal)

Execute in this exact order. Each step must complete and verify before the next.

```
Step 1: Edit beat_generator.py
  - Add _openai_api_key() after _bfl_api_key()
  - Add _GPT_SPECIES_ANCHOR dict
  - Add _GPT_VARIATION_POSE list  
  - Add _emotion_to_body_mechanics()
  - Add _make_gpt_thumb()
  - Add build_gpt_still_prompt()
  - Add submit_gpt_stills()
  ✓ Verify: python3 -c "import beat_generator; print('ok')" (from Production/tools/)

Step 2: Edit production_server.py
  - Add _GPT_JOBS + _gpt_executor() (module level, near other globals)
  - Add _handle_bg_submit_gpt_batch() method
  - Add _handle_bg_poll_gpt_status() method
  - Wire routes in dispatch block
  ✓ Verify: python3 -c "import production_server; print('ok')"

Step 3: Restart production server
  ✓ Verify: lsof -ti:5111 → new PID, started AFTER py file edits

Step 4: Smoke test via CLI (no UI needed)
  python3 -c "
  import sys; sys.path.insert(0, 'Production/tools')
  import beat_generator as bg
  key = bg._openai_api_key()
  print('Key:', key[:12] + '...')
  prompt = bg.build_gpt_still_prompt({'speaker':'Tessa','emotion':'warm, grateful','text':'Thank you'}, 0)
  print('Prompt OK:', len(prompt), 'chars')
  "

Step 5: One-beat end-to-end test via CLI (costs ~$0.24)
  python3 -c "
  import sys; sys.path.insert(0, 'Production/tools')
  import beat_generator as bg
  test_beat = {
    'beat_id': 'test_gpt_001',
    'speaker': 'Tessa',
    'emotion': 'warm, grateful',
    'text': 'Thank you so much.',
    'bg_ref_image': 'Production/Backgrounds/heartwood/view from inside heartwood area.png'
  }
  results = bg.submit_gpt_stills(test_beat, num_options=1)
  print(results[0].get('local_path') or results[0].get('error'))
  "
  ✓ Verify: image file exists, open in Preview

Step 6: Write patch_v49_gpt_stills_button.py + run it
  ✓ Verify: SHA256 base64 hash identical before/after
  ✓ Verify: grep "_bgToggleGenMode\|gpt_options\|submit-gpt-batch" v49 file → found

Step 7: Open v49 in browser, test full flow:
  - Beat Generator tab → set BG ref → click "GPT Stills" → options appear
  - Switch to FLUX mode → click "Generate Stills" → FLUX options appear
  - Both visible in option slots
```

---

## 6. Files Touched

| File | Change type | Safe to edit in CLI |
|---|---|---|
| `Production/tools/beat_generator.py` | Additions only (insert after line 648) | Yes |
| `Production/tools/production_server.py` | Additions only (new methods + 2 route lines) | Yes |
| `Production/Event_1/storyboard_v4X_prod.html` | Path B patch script (new version) | Yes — script only |

**Files NOT touched:**
- `beat_generator_state.json` (sidecar — no schema migration needed; `gpt_options` is additive)
- `FLUX` pipeline code (`submit_flux_kontext`, `poll_flux_result`, `submit_beat_stills`)
- Any `.docx` narrative files

---

## 7. Known Risks and Mitigations

| Risk | Mitigation |
|---|---|
| OpenAI SDK `image=list` not supported in v2.32.0 | Use `urllib` multipart fallback (see Appendix A) |
| GPT content policy on "magic spell" children content | Prompt avoids emotional adjectives; uses body mechanics; no spell/magic language in prompt |
| Character drift across events | Fixed species anchors + `identity lock` phrase repeated; validated by Kim's manual test |
| `_log_activity` not available in production_server module scope | Wrap in try/except; cost is logged to sidecar regardless |
| Server restart kills in-progress FLUX jobs | No change to FLUX path; restart timing is Kim's control |

---

## Appendix A: urllib Multipart Fallback

If `client.images.edit(image=[f1, f2], ...)` raises TypeError (list not supported), use:

```python
def _openai_images_edit_multipart(api_key, char_path, bg_path, prompt, size="1024x1024"):
    """Raw multipart POST to /v1/images/edits — fallback if SDK list-image fails."""
    import uuid as _uuid
    boundary = "MNBoundary" + _uuid.uuid4().hex[:12]
    parts = []

    def _file_part(field, path):
        with open(path, "rb") as f:
            data = f.read()
        fname = os.path.basename(path)
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field}"; filename="{fname}"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode() + data + b"\r\n"

    def _text_part(field, value):
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()

    body = (
        _file_part("image[]", char_path) +
        (_file_part("image[]", bg_path) if bg_path else b"") +
        _text_part("model", "gpt-image-1") +
        _text_part("prompt", prompt) +
        _text_part("size", size) +
        _text_part("response_format", "b64_json") +
        _text_part("n", "1") +
        f"--{boundary}--\r\n".encode()
    )

    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection("api.openai.com", context=ctx, timeout=120)
    try:
        conn.request("POST", "/v1/images/edits", body=body, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        })
        resp = conn.getresponse()
        data = json.loads(resp.read())
    finally:
        conn.close()

    if "data" not in data:
        raise RuntimeError(f"OpenAI error: {data}")
    return base64.b64decode(data["data"][0]["b64_json"])
```

---

## 8. Handoff Checklist for CLI Session

```
□ Read this spec fully before touching any file
□ Read current beat_generator.py lines 400-650 (key area for insertion)
□ Read current production_server.py dispatch block (find route insertion points)
□ Read current storyboard HTML lines 4379-4440 (generate button wiring)
□ Run Step 1 → verify import clean
□ Run Step 2 → verify import clean
□ Restart server → confirm new PID
□ Run Step 4 smoke test (no API cost)
□ Run Step 5 one-beat test (~$0.24)
□ Open image in Preview → show Kim
□ Kim approves → write patch_v49 → test full UI flow
□ Log LD to prod_locked_decisions: GPT_STILLS_PIPELINE_V1
□ Update prod_activity_log with implementation session
```
