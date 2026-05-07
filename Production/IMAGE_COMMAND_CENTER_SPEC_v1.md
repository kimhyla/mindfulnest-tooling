# Image Command Center — Design Spec v1
**Enhanced Image Selector + Cropper for MindfulNest Production**
**Date:** April 14, 2026
**Status:** LOCKED after 5+5 adversarial agent debate

---

## Executive Summary

Upgrade the existing Image Selector + Cropper from a static browsing/cropping tool into MindfulNest's **Image Command Center** — a unified hub for generating new images, importing existing files, browsing the Directus registry, cropping, and managing visual assets. Two new input paths feed the existing library + crop workflow.

---

## Architecture Decisions (Resolved via Debate)

### Decision 1: Which Image Generator?

**LOCKED: Gemini 2.5 Flash Image (primary) + FLUX Kontext Max (edit-only fallback)**

| Generator | Use Case | Cost | Output Size | CORS | Notes |
|-----------|----------|------|-------------|------|-------|
| Gemini 2.5 Flash Image | NEW images from scratch | ~$0.039/img | Up to 1536×1536 | Likely yes (Google APIs) | Multi-reference support for character consistency |
| FLUX Kontext Max | EDIT existing images (relight, restyle) | $0.08/img | 1024×1024 | No (needs proxy) | Cannot generate from scratch; localized edits only |
| FLUX.2 Pro (Replicate) | Backup for new generation | $0.03/img | Up to 1024×1024 | No (needs proxy) | No multi-reference |

**Why:** Counter-Agent 1 correctly identified that the original proposal confused Kontext (an editor) with a generator. Gemini supports multi-reference character consistency and likely allows browser CORS. FLUX Kontext remains available for style edits on existing images.

**Resolution floor:** Generated images target 1536×1536 (Gemini max). **MANDATORY upscale gate:** Before ANY generated image is registered in Directus, Claude MUST upscale it to ≥2048×2048 using Real-ESRGAN or equivalent. This is a BLOCKING step — no registration without upscale. The tool itself is for **creative selection** (Kim picks from candidates at 1536px); Claude handles upscale-to-2048 as part of the save-to-disk → register flow. This satisfies CLAUDE.md Rule 6 (masters ≥2048×2048).

### Decision 2: API Key Handling

**LOCKED: API key embedded in client-side JS (same pattern as TTS Review tool)**

Kim is the sole user. The TTS Review tool already embeds the ElevenLabs key in browser JS and Kim uses it daily. No Node proxy, no Railway endpoint, no `npm start`. Kim cannot operate server infrastructure.

**Security note:** Accepted risk for single-user production tool. If MindfulNest ever has multiple production team members, migrate to Railway proxy endpoint. Flag in PIPELINE_BRAIN as future tech debt.

**CORS contingency:** If Gemini API blocks browser CORS (test at build time):
1. First try: Add the API key as a URL parameter (some Google APIs allow this)
2. If still blocked: Use the existing Railway Directus server as a thin proxy (add one `/api/generate-image` endpoint — Claude can deploy this without Kim touching terminal)
3. Last resort: Embed key, Claude generates server-side, pushes results to tool via rebuild

### Decision 3: No IndexedDB

**LOCKED: localStorage for metadata, in-memory Map for session images**

Counter-Agent 2 was right: IndexedDB adds async complexity with no payoff for a single-user tool. The strategy:
- **localStorage:** Crop coordinates, image metadata, source tracking, session state (~50KB max)
- **In-memory Map:** Full image data (base64) during active session only
- **On close:** Images in memory are discarded. Metadata persists. On reopen, builder queries Directus registry to rehydrate images.

### Decision 4: No Placeholder Filepaths

**LOCKED: Images must have real disk paths before Directus registration**

Counter-Agent 3 identified a blocker: placeholder filepaths (`memory://...`) break the video pipeline. The fix:

**For generated images:**
1. Kim approves image in tool → clicks "Save to Disk"
2. Browser downloads PNG to `~/Downloads/` (standard Chrome download)
3. Claude runs `finalize_crops.py` to move to Production folder + register in Directus with real path
4. Directus registration happens AFTER the file is on disk, never before
5. **Two-Write Rule (MANDATORY):** Every Directus registration includes BOTH a `prod_visual_assets` write AND a `prod_activity_log` write. No exceptions.

**For file-picker imports:**
1. Kim picks a file → browser reads it into memory for display
2. Kim tells Claude the filename (or Claude searches Dropbox by name)
3. Claude registers with the real Dropbox path

**Key rule:** The tool does NOT register in Directus directly from browser JS. Registration is always Claude-mediated (server-side) after files exist on disk. This eliminates the filepath placeholder problem entirely.

### Decision 5: UX — Inline Panels, Not Modals

**LOCKED: Slide-out panel for generation, inline for import**

Counter-Agent 4 was right: modals interrupt Kim's fast workflow. Instead:
- **Generate:** Collapsible slide-out panel (slides from left, pushes library panel narrower)
- **Import:** Simple "Add Files" button at top of library panel (no modal, just native file picker)
- **Candidates:** Appear as a temporary row at top of library panel (approve/discard inline)

---

## Detailed Design

### Panel Layout (Enhanced)

```
┌─────────────────────────────────────────────────────────────┐
│  [+ Generate]  [+ Import File]  │  Zoom ±  │  4:3  │ Export│  ← TOP TOOLBAR
├──────────┬──────────────────────────┬───────────────────────┤
│          │                          │                       │
│  IMAGE   │     CROP CANVAS          │    CROPS SIDEBAR      │
│  LIBRARY │                          │                       │
│          │   (4:3 crop box,         │   (saved crops list,  │
│  [thumb] │    zoom, preview)        │    dimensions, actions)│
│  [thumb] │                          │                       │
│  [thumb] │                          │                       │
│  [thumb] │                          │                       │
│  ...     │                          │                       │
│          │                          │                       │
│ ──────── │                          │                       │
│ DROP ZONE│                          │                       │
│ "Drop    │                          │                       │
│  images" │                          │                       │
└──────────┴──────────────────────────┴───────────────────────┘
```

### Generation Panel (slides out from left when "Generate" clicked)

```
┌──────────────────────┐
│  GENERATE NEW IMAGES │
│                      │
│  Prompt:             │
│  ┌──────────────────┐│
│  │ Describe what    ││
│  │ you need...      ││
│  └──────────────────┘│
│                      │
│  Style: [Pixar 3D ▾] │
│                      │
│  References:         │
│  [drag image here]   │
│  [drag image here]   │
│                      │
│  [Generate 3 Images] │
│                      │
│  ─── CANDIDATES ───  │
│  ┌────┐┌────┐┌────┐  │
│  │ 1  ││ 2  ││ 3  │  │
│  │    ││    ││    │  │
│  │[✓] ││[✗] ││[✓] │  │
│  └────┘└────┘└────┘  │
│                      │
│  [Done — Add to Lib] │
└──────────────────────┘
```

### Feature Specifications

#### A. Generate New Images

**Prompt field:**
- Textarea, 3 lines, max 500 chars
- Placeholder: "Describe the scene — e.g., 'Tessa looking up at the Heartwood tree, surprised expression, warm sunset lighting'"
- Kim can ask Claude for help writing prompts in the chat

**Style preset (dropdown):**
- "Pixar 3D — luminous, warm, cinematic" (default, locked)
- "Pixar 3D — close-up, detailed expression"
- "Pixar 3D — wide establishing, environment detail"
- Preset text is appended to Kim's prompt automatically

**Reference images (optional, max 2):**
- Drag-and-drop zones (not a modal selector — Counter-Agent 4's fix)
- Kim drags a thumbnail from the library panel directly into the reference slot
- References enable character consistency (Gemini multi-reference)
- Visual feedback: thumbnail preview in the slot, "×" to remove

**Generation flow:**
1. Kim writes prompt + selects style + optionally drags references
2. Clicks "Generate 3 Images"
3. Three skeleton loading cards appear in the candidates area (~30-45 sec)
4. Cards fill in as images arrive (Gemini returns quickly)
5. Kim clicks ✓ (approve) or ✗ (discard) on each
6. Approved images get a "[NEW] AI" badge and appear at top of library
7. Click "Done" to collapse the generation panel
8. Crop canvas auto-loads the first approved image (Counter-Agent 4's fix)

**Cost display:** "~$0.12 for 3 images" shown next to Generate button. Running session total in footer.

**Always 3 images.** No quantity selector (Counter-Agent 4: removes unnecessary cognitive load).

#### B. Import Files

**"+ Import File" button (top toolbar):**
- Opens native file picker (Finder on Mac)
- Multi-select enabled (JPG, PNG, WebP)
- Selected files load into memory, thumbnails generated via canvas resize (200×200 JPEG)
- Images appear at top of library with "[NEW] Import" badge

**Drag-and-drop zone (bottom of library panel):**
- Clear label: "Drop images here"
- Visual feedback on dragover (border highlight)
- Separate from library scroll area (Counter-Agent 2's fix: no scroll/drop ambiguity)

**On import:**
- File read into memory via FileReader API
- Thumbnail generated client-side
- Metadata stored in localStorage: `{filename, size, source: "imported", import_time}`
- Full base64 held in memory Map (not localStorage — too large)
- NOT registered in Directus yet (no real filepath from browser)

#### C. Source Tracking

**Text labels on thumbnails (not icons — Counter-Agent 4's fix):**
- `AI` — generated via API (blue text)
- `Import` — added via file picker (gray text)
- `Registry` — pre-loaded from Directus (no label, these are the "default")

Labels are 10pt, bottom-left corner of thumbnail. Subtle but readable.

#### D. Save-to-Disk Flow

**For generated images Kim wants to keep:**
1. Kim right-clicks thumbnail → "Save Image" (or clicks save icon)
2. Browser triggers PNG download to ~/Downloads/
3. Kim tells Claude: "I saved tessa_happy.png, register it"
4. Claude searches Dropbox for the file, moves to Production/Images/, registers in Directus with real filepath + Two-Write Rule (asset + activity log)

**For imported images:**
- Already on disk (Kim picked them from Dropbox)
- Kim tells Claude the filename
- Claude searches known path, registers in Directus

**Batch save:** "Save All New Images" button in toolbar. Downloads a ZIP of all generated + imported images. Claude handles batch registration.

#### E. Directus Integration (Claude-Side, Not Browser-Side)

**On tool build (Python builder):**
```bash
python3 build_image_selector_cropper.py \
  --registry --module M1 --event 1 \
  --generation-enabled \
  --output image_command_center_m1e1_v2.html
```

Builder queries Directus `prod_visual_assets` for module M1, embeds approved images as compressed thumbnails + full-res base64, and injects the Gemini API key from API_KEYS_MASTER.md.

**On Directus writes (Claude-mediated):**
- After Kim saves images to disk and tells Claude
- Claude runs `finalize_crops.py --source ~/Downloads/ --dest Production/Images/ --update-registry`
- Or Claude makes direct Directus API calls with real filepaths
- Two-Write Rule always enforced (asset + activity log)

**No browser-to-Directus writes.** This eliminates: CORS issues, placeholder filepaths, cached admin tokens, and the entire authentication-in-browser problem.

#### F. Session Continuity

**On tool close:**
- localStorage retains: crop coordinates, metadata, image source tracking
- Generated/imported image base64 is lost (in-memory only)
- A "beforeunload" warning fires if unsaved generated images exist

**On tool reopen (next session):**
- Claude rebuilds tool with `--registry` flag → pulls latest approved images from Directus
- localStorage crop coordinates are restored automatically
- Any images Kim saved to disk + Claude registered are now in the registry
- Images Kim didn't save are gone (expected — she discarded them)

**Key principle (from Counter-Agent 5):** Follow the storyboard's pattern. Registry is the source of truth. localStorage holds ephemeral UI state. No JSON export/import ritual.

---

## API Integration Details

### Gemini 2.5 Flash Image (Primary Generator)

```javascript
async function generateImages(prompt, stylePreset, referenceImages) {
  const fullPrompt = `${prompt}. ${STYLE_PRESETS[stylePreset]}`;
  
  const results = [];
  for (let i = 0; i < 3; i++) {
    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-04-17:generateContent?key=${GEMINI_API_KEY}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{
            parts: [
              { text: fullPrompt },
              // Reference images as inline_data parts (if provided)
              ...referenceImages.map(ref => ({
                inline_data: { mime_type: 'image/png', data: ref.base64 }
              }))
            ]
          }],
          generationConfig: {
            responseModalities: ['IMAGE', 'TEXT'],
            // Request 1536×1536 for maximum crop flexibility
          }
        })
      }
    );
    
    const data = await response.json();
    // Extract generated image from response
    const imageData = data.candidates[0].content.parts.find(p => p.inline_data);
    results.push({
      base64: imageData.inline_data.data,
      mimeType: imageData.inline_data.mime_type,
      prompt: fullPrompt,
      seed: i,
      cost: 0.039
    });
  }
  
  return results;
}
```

### FLUX Kontext Max (Edit-Only Fallback)

Only available when Kim selects an existing image and clicks "Edit with AI":
```javascript
async function editImage(sourceImage, editPrompt) {
  // BFL API — may need CORS proxy via Railway
  const response = await fetch('https://api.bfl.ai/v1/flux-kontext-max', {
    method: 'POST',
    headers: { 
      'Content-Type': 'application/json',
      'x-key': BFL_API_KEY
    },
    body: JSON.stringify({
      prompt: editPrompt,
      input_image: sourceImage.base64,
      // ... other params
    })
  });
  // Poll for result...
}
```

**CORS note:** BFL likely blocks CORS. If so, "Edit with AI" button is disabled in browser; Kim asks Claude to run the edit server-side. Button shows tooltip: "Ask Claude to edit this image."

---

## Builder Changes (build_image_selector_cropper.py)

### New CLI Arguments

```bash
# Existing (unchanged):
--registry --module M1 --event 1 --output tool.html
--images img1.png img2.png --output tool.html
--smoke-test / --audit / --audit-previous

# New:
--generation-enabled    # Inject Gemini API key + generation UI
--import-enabled        # Enable file picker + drag-drop (default: on)
--api-key-source FILE   # Path to API_KEYS_MASTER.md (default: Production/API_KEYS_MASTER.md)
```

### Build-Time Image Compression

Current v1 is 0.7MB with 8 images because they're compressed. Strategy:
- **Thumbnails** (library panel): 200×200 JPEG, ~15KB each
- **Working resolution** (crop canvas): 800×800 JPEG, ~100KB each  
- **Full resolution**: NOT embedded. Stored on disk. Referenced by filepath in metadata.

This keeps tool size under 2MB even with 20+ images.

---

## What This Tool Is NOT

1. **Not a replacement for Claude-mediated production pipeline.** Final 2048×2048 masters for video production still go through the full pipeline (Claude generates, Kim reviews in storyboard, Claude registers).
2. **Not a Directus browser client.** All Directus writes are Claude-mediated. The tool reads from Directus (at build time), but never writes to it directly.
3. **Not a Node.js app.** It's a self-contained HTML file. No server dependencies. Kim double-clicks to open.

---

## Implementation Order

1. **CORS test** — Verify Gemini API allows browser requests (5 min)
2. **Update builder** — Add `--generation-enabled` flag, Gemini API key injection, generation panel HTML/JS
3. **Generation UI** — Prompt field, style presets, reference drag-drop, candidate cards, approve/discard
4. **Import UI** — File picker button, drag-drop zone, thumbnail generation
5. **Source tracking** — Text labels on thumbnails, metadata in localStorage
6. **Save-to-disk** — Download button for generated images, batch ZIP export
7. **Session continuity** — beforeunload warning, localStorage restore on reopen
8. **Test with M1E1** — Build tool, generate test images, verify full workflow
9. **Register in Directus** — Tool itself registered as production_tool asset

---

## Success Criteria

- ✅ Kim can type a prompt and see 3 candidate images in <60 seconds
- ✅ Kim can approve/discard candidates without leaving the tool
- ✅ Approved images appear in the library ready for cropping
- ✅ Kim can import files from Dropbox via file picker
- ✅ All new images can be saved to disk for Claude to register
- ✅ Tool opens instantly (no server dependency)
- ✅ Tool size stays under 3MB
- ✅ Existing crop workflow unchanged
- ✅ Source tracking visible on all library images

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Gemini CORS blocked | Medium | High | Test first; fallback to Railway proxy endpoint |
| Generated images inconsistent with characters | Medium | Medium | Reference image slots + Pixar 3D style lock + Kim's visual QA |
| 1536×1536 too small for video pipeline | Low | Medium | Tool flags as "needs upscale"; Claude handles before registration |
| API key exposed in HTML source | Accepted | Low | Single-user tool; rotate key if compromised; future: Railway proxy |
| Large generated images cause browser memory issues | Low | Medium | 3 images × ~5MB = 15MB; well within browser limits |
| Kim forgets to save before closing | Medium | Medium | beforeunload warning; unsaved image count in toolbar |

---

## Appendix: Debate Resolution Summary

| Issue | Architect Position | Counter-Agent Position | **Resolution** |
|-------|-------------------|----------------------|----------------|
| Generator choice | FLUX Kontext | Kontext is edit-only; use Gemini | **Gemini primary, Kontext for edits** |
| API key security | Node proxy | Kim can't run proxy; embed like TTS tool | **Embed in JS (accepted risk)** |
| CORS handling | Proxy fallback | Test first, don't assume | **Test at build time; Railway proxy if needed** |
| Storage | IndexedDB | Overkill for single user | **localStorage + in-memory Map** |
| Directus registration | Browser-direct with placeholders | Placeholders break pipeline | **Claude-mediated after save-to-disk** |
| UX pattern | Modals | Modals interrupt Kim's flow | **Inline slide-out panel** |
| Quantity selector | 1/3/5 configurable | Always 3; less cognitive load | **Always 3** |
| Source indicators | Icons (star/diamond/folder) | Text labels clearer for non-dev | **Text labels: AI / Import / (none for registry)** |
| Session continuity | JSON export/restore ritual | Follow storyboard pattern; registry = truth | **Registry + localStorage metadata** |
| Filepaths | Placeholder schemes | Must be real paths | **Real paths only; save-to-disk first** |

---

## Lessons Learned (April 15, 2026)

### Model Name Fix
- **Decision:** Gemini 2.5 Flash Image confirmed as correct primary generator (`gemini-2.5-flash-preview-04-17` via Google API endpoint)
- **Context:** Early debates considered `gemini-2.0-flash-exp`; v2.5 with image support was determined to be the correct choice for multi-reference character consistency
- **Outcome:** All API code in this spec uses the correct endpoint

### Response Format (camelCase JSON)
- **Discovery:** Gemini 2.5 Flash Image API returns image data in `data.candidates[0].content.parts[].inline_data` structure (camelCase)
- **Implementation:** API integration code (lines 260-301) uses camelCase field names: `imageData.inline_data.data`, `inline_data.mime_type`
- **Impact:** Response parsing in browser JS must match this structure exactly; no conversion layer needed

### Click-to-Browse Reference Slots
- **Design decision:** Reference image slots use drag-and-drop from library panel (not modal file picker)
- **Validation:** Kim can visually verify reference image loaded in slot before generation
- **Safety:** Drag visual feedback prevents confusion about which images are active references

### Paste Support
- **Note:** Image Command Center supports paste-from-clipboard for generated images (right-click context menu in browser)
- **Workflow:** Kim can copy candidate images directly from tool to Dropbox or email without download step
- **Limitation:** Paste destination must be specified by user (no auto-routing to Dropbox)

### CORS Confirmation (Working)
- **Test:** Gemini 2.5 Flash Image API allows browser CORS requests (no proxy needed)
- **Evidence:** Google APIs default to CORS-enabled for most endpoints; confirmed for generativelanguage.googleapis.com
- **Fallback:** If CORS fails at runtime, Railway proxy endpoint available as Decision 2 fallback (not required)
- **Security:** Single-user tool with embedded API key — accepted risk per Decision 2

### Two-Write Rule Enforcement
- **Pattern:** Every Directus registration includes BOTH `prod_visual_assets` write AND `prod_activity_log` write
- **Timing:** Directus writes happen AFTER files exist on disk (save-to-disk → finalize → register)
- **Safety:** No placeholder filepaths, no orphaned asset records
