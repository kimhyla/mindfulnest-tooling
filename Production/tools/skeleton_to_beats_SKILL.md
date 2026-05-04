---
name: skeleton-to-beats
description: Converts arc skeleton event sections into storyboard beat lists.
---

# skeleton-to-beats

Converts one event section from an arc skeleton .md file into a `lines[]` JSON array ready for the storyboard builder.

## REQUIRED OUTPUT — all 8 fields, every beat, no exceptions

Every beat in the output array MUST have exactly these 8 fields:

```json
{
  "speaker":        "Luna",
  "text":           "HOW DID YOU DO THIS!?!?",
  "emotion":        "ecstatic, spinning, can't contain herself",
  "image":          "none",
  "audio_key":      null,
  "pause":          0.5,
  "section":        "Discovery",
  "video_sequence": "intro"
}
```

- `image`: ALWAYS the string `"none"` — Kim assigns images in the browser
- `audio_key`: ALWAYS `null` (JSON null, not the string "null")
- `emotion`: NEVER empty — always a short delivery phrase
- `video_sequence`: ALWAYS either `"intro"` or `"resolution"` — never omit this

Missing any of these 8 fields is a failure. Do not add extra fields.

## Hard rules (never violate)

1. **Verbatim Kim dialogue** — copy character-for-character, including caps, ellipses, "!?!?", etc. No tags on Kim's lines — output them clean.
2. **[CLAUDE INVENTED] tag** — ONLY on lines Claude invented (bridge lines, transitions not present in the skeleton): `"[CLAUDE INVENTED] {text}"`
3. **Preserve placeholders verbatim** — `{childName}`, `{childPronounPossessive}`, etc. — never replace with "the child", "you", etc.
4. **Canonical speaker names**: "Guide Bird" → `"Chipper"`, "Pip" → `"Chipper"`, "Myrrhin" → `"Cedric"`
5. **No therapeutic framing in text** — delivery cues go in `emotion`, not `text`
6. **Stage directions** get their own beat: `"speaker": "[Stage Direction]"`, text is clean (no tag)

## emotion field

Short delivery phrase. Examples:
- Extract inline skeleton cue: `[to camera, warmly]` → `"emotion": "to camera, warmly"`, remove from text
- Infer from context: Luna discovery peak → `"emotion": "ecstatic, spinning, can't contain herself"`
- Tessa in pain → `"emotion": "pained, embarrassed"`
- Stage direction beat → `"emotion": "quiet, still moment"` or `"emotion": "transition — intro ends here"`

## video_sequence field — THREE VIDEO TYPES

Every beat gets tagged `"intro"`, `"resolution"`, or `"full"` based on where it falls relative to the module boundary.

**`"intro"`** — everything BEFORE and including the first `► INSERT MODULE` marker. The narrative leading up to the spell. The intro ALWAYS ends with Chipper facing camera introducing the module, followed by the `► INSERT MODULE` stage direction beat.

**`"resolution"`** — everything AFTER all modules. The creature transforms, the inscription is revealed, the runestone lights up, the arc hook fires. First resolution beat = first visible creature change after the module ends.

**`"full"`** — used for events with NO module at all (e.g., Event 0 Opening Storybook, arc transition scenes). Every beat in a no-module event is tagged `"full"`.

**How to detect the type:** scan the skeleton section for `► INSERT MODULE`. If present → intro + resolution split. If absent → all beats are `"full"`.

## 4-Phase process

**Phase 1 — Spine:** Read the section. Scan for `► INSERT MODULE` markers.
- **Found:** mark the intro/resolution boundary. Identify: creature's problem, child's arrival, spell offer, module handoff, creature's transformation, stone lighting.
- **Not found:** all content is one continuous video (`"full"`). Identify the narrative arc start to finish.

**Phase 2 — Slots:** Assign beats across the full section. Stage direction beats add cinematic context. Merge moments that share an image; give emotional peaks their own slot.
- Module events: target 8–12 intro beats + 4–8 resolution beats
- Non-module events: target as many beats as the content needs, no fixed target

**Phase 3 — Dialogue + tags:** For each slot: (a) find Kim's line → copy verbatim → output clean, no tag; or (b) no Kim line → write bridge → prepend `[CLAUDE INVENTED]`. Extract inline cues to `emotion`. Set `video_sequence` (`"intro"` / `"resolution"` / `"full"`). Set `pause` (1.0 for emotional peaks, 0.0 for rapid back-and-forth, 0.5 default). Preserve all `{placeholders}`.

**Phase 4 — Dedup:** Check for repeated information. Verify: if module event, last `"intro"` beat is Chipper facing camera and first `"resolution"` beat shows creature's visible change.

## Output format

Kim specifies which video to build. Filter the output accordingly:

| Kim says | Output |
|----------|--------|
| "intro video" / "intro beats" | Only beats with `video_sequence: "intro"`. Last beat = `► INSERT MODULE` stage direction. |
| "resolution video" / "win video" / "resolution beats" | Only beats with `video_sequence: "resolution"`. First beat = creature's first visible change. |
| "full video" / no-module event | All beats (tagged `"full"`). |

**Default** (if Kim doesn't specify): ask in ONE line — "Intro, resolution, or full video?"

Output ONLY the raw JSON array for the requested video. No markdown fence. No prose before or after. The array is written directly to a `.json` file.

## Examples

**Last intro beat (Chipper camera handoff):**
```json
{
  "speaker": "Chipper",
  "text": "Luna's SO close to cracking this puzzle. But she's so tense she can't think straight! You know - I have another Magic Spell we could try. It's called the Breath-Squeezers Spell. [magic sound] It's the greatest spell for anyone who's stressed out. Wanna try it?",
  "emotion": "to camera, warmly",
  "image": "none",
  "audio_key": null,
  "pause": 0.5,
  "section": "Module Intro",
  "video_sequence": "intro"
}
```

**Module boundary beat:**
```json
{
  "speaker": "[Stage Direction]",
  "text": "► INSERT MODULE M2 — Breath-Squeezers Spell (Squeeze-and-Release / Progressive Tension Release)",
  "emotion": "transition — intro ends here",
  "image": "none",
  "audio_key": null,
  "pause": 0,
  "section": "Module",
  "video_sequence": "intro"
}
```

**First resolution beat (creature transforms):**
```json
{
  "speaker": "[Stage Direction]",
  "text": "Visible magic disperses from around Luna. Her shoulders drop. Her wings relax. The magnifying glass steadies in her grip.",
  "emotion": "quiet, still — the tension releases",
  "image": "none",
  "audio_key": null,
  "pause": 1.0,
  "section": "Resolution",
  "video_sequence": "resolution"
}
```

**Suggested bridge:**
```json
{
  "speaker": "Chipper",
  "text": "[CLAUDE INVENTED] {childName}, this is Luna — she's been searching for the Heartwood for years!",
  "emotion": "excited, introductory",
  "image": "none",
  "audio_key": null,
  "pause": 0.5,
  "section": "Arrival",
  "video_sequence": "intro"
}
```

## Auto-push to beat generator

After generating the beats array, POST it to the running production server so beats appear in the Beat Generator tab automatically.

**Implementation (execute this after generating the beats):**

```python
import urllib.request, json

payload = {
    "arc_number": <arc_number>,      # e.g., 1
    "event_id": <event_id>,          # e.g., "2"
    "phase": <phase>,                # "pre", "post", or "full"
    "beats": <beats_array>           # the generated lines[] array
}

req = urllib.request.Request(
    "http://localhost:5111/api/bg/inject-beats",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        result = json.loads(resp.read())
    print(f"✓ Beats injected: {result['count']} beats loaded into beat generator.")
    print(f"  Arc {payload['arc_number']}, Event {payload['event_id']}, Phase: {payload['phase']}")
    print("  Open the Beat Generator tab — your beats are ready.")
except Exception as e:
    print(f"✗ Server not running or inject failed: {e}")
    print("  Outputting beats here instead:")
    print(json.dumps(beats_array, indent=2))
```

**Behavior:**
- Always attempt the POST first
- On success: report arc/event/phase and beat count
- On failure (connection refused, timeout, error): fall back to printing JSON in chat
- Never silently swallow failures
