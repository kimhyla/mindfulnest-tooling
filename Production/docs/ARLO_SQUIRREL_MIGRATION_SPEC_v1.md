# Arlo Squirrel Migration Spec v1

Status: execution spec  
Date: 2026-06-10  
Scope: Event_1 intro/pre guide-character migration from Chipper bird to Arlo squirrel

## Decision

Create a new active guide identity named **Arlo** using the vest squirrel assets. Do not mutate the old Chipper bird in place and pretend it is the same character. Chipper remains legacy/archived; Arlo becomes the active intro guide.

Reason: previous failures came from stale identity surfaces. "Chipper" existed simultaneously as a speaker alias, bird-class prompt branch, Kling Element, Beat Gen reference image, persisted O3 prompt, pinned canonical tail, and accepted video path. Reusing the same name makes old bird references easier to miss.

## Canonical Arlo Assets

Canonical full-body reference:

- `Production/Arlo/poses/arlo_canonical_neutral_vest.png`

Allowed supporting references:

- `Production/Arlo/poses/arlo_happy_vest.png`
- `Production/Arlo/poses/arlo_confident_vest.png`
- `Production/Arlo/poses/arlo_worried_vest.png`
- `Production/Arlo/poses/arlo_sad_vest.png`
- `Production/Arlo/poses/arlo_wizard_room_wide_vest.png`
- `Production/Arlo/poses/arlo_wizard_room_medium_vest.png`
- `Production/Arlo/poses/arlo_wizard_room_neutral_vest.png`

Source folder:

- `Production/NEW STYLE CHARACTERS/CHIPPER SQUIRREL/`

## Active Identity Surfaces To Update

1. `character_subjects.json`
   - Add `Arlo` as an active/pending character.
   - Use the same ElevenLabs/Kling voice settings as Chipper unless a separate voice profile is created.
   - Register a fresh Kling Element from Arlo squirrel assets.
   - Do not reuse Chipper element IDs.

2. `production_server.py`
   - Add `Arlo` speaker alias.
   - Add `Arlo` voice profile fallback to Chipper voice if Directus does not yet have a separate Arlo row.
   - Add `Arlo` squirrel motion vocabulary.
   - Ensure `Arlo` is not in `BIRD_SPEAKERS`.
   - Ensure prompt constraints use mouth/paw/tail language, not beak/wing/feather language.

3. `beat_generator.py`
   - Add Arlo to speaker aliases.
   - Add Arlo to species/still prompt anchors.
   - Add Arlo to default reference maps and GPT species anchors.
   - Ensure Arlo prompts say squirrel, paws, tail, blue scarf, green vest.

4. `lib/paths.py`
   - Add Arlo default pose path to `character_pose_paths()`.

5. `lib/end_frame_prompt.py`
   - Add Arlo end-frame hint.

6. Active Beat Generator state
   - For Event_1 intro/pre Chipper beats only, change speaker to Arlo.
   - Replace Chipper reference images with Arlo reference images.
   - Rewrite `kling_o3_prompt` / `kling_o3_prompt_prepared` to squirrel-safe language.
   - Clear old generated/accepted O3 fields so the UI cannot reuse bird MP4s.

7. Canonical intro tail
   - Do not reuse `templates/chipper_teleport_intro/canonical_registry.json`.
   - Create or reserve `templates/arlo_teleport_intro/`.
   - Clear bird-specific canonical tail locks from active intro/pre Arlo beat state until a new Arlo tail is approved.

8. Storyboard scope bug
   - `video=intro` must resolve Beat Generator phase `pre`.
   - `video=resolution` must resolve `post`.
   - Live verification required after restart.

## Do Not Proceed Conditions

Stop before regeneration if any active intro/pre path still contains:

- `Chipper/poses`
- `master_chipper`
- old Chipper Element IDs: `312987294498500`, `312924252190306`
- `Guide Bird`, `Pip`, `assistant bird` as active intro speaker
- prompt anatomy terms for Arlo: `bird`, `magpie`, `beak`, `wing`, `wings`, `feather`, `feathers`
- `canonical_intro_tail`, `canonical_mirror_video`, or `templates/chipper_teleport_intro` in active Arlo intro beat state
- existing Chipper O3 MP4 paths as accepted/current videos for active Arlo beats

Legacy docs, tests, and backup snapshots may retain those strings if they are outside the active runtime path and the audit classifies them as legacy-only.

## QA Gates

Gate A: Snapshot
- Back up `character_subjects.json`, `beat_generator_state.json`, `production_state.json`, and relevant template registry files before mutation.

Gate B: Asset
- Verify all Arlo canonical images exist and have shortest side >= 600px.

Gate C: Code
- Compile patched Python files.
- Run focused prompt checks proving Arlo is squirrel-class and not bird-class.

Gate D: Element
- Register or validate Arlo Kling Element.
- Verify `character_subjects.json` has Arlo active with a non-Chipper `element_id`.

Gate E: State
- Active intro/pre Chipper beats become Arlo beats.
- Old accepted/generated bird video fields are cleared.
- Resolution/post is untouched except for global code support.

Gate F: Audit
- Active intro/pre Arlo audit returns zero stale bird references.
- Endpoint audit confirms `video=intro` returns `pre`.

Gate G: Deployment
- Restart Storyboard server.
- Confirm HTTP 200 at `/`.
- Confirm live BG session state returns Arlo intro/pre beats.
- Browser smoke: open Storyboard intro and confirm Beat Generator is on intro/pre, not post.

## Regeneration Policy

Only after Gates A-G pass, regenerate Arlo intro beats. Start with one or two O3 clips, inspect frames/contact sheets, then continue. Send to Stitcher only after visual approval gates pass.
