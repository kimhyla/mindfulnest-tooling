# Beat Gen — new event checklist

Use when standing up **Event_N** (or a new video role) so you do not re-fight Event_2 triage bugs.

Code heals run automatically on first BG session load. This checklist covers **runtime setup** code cannot invent.

## Before first Generate

1. **Event folder** exists under Dropbox `Production/Event_N/` with storyboard HTML deployed.
2. **Extract / plan beats** — sidecar segment populated (`beat_generator_state.json`).
3. **Per cast member with dialogue O3:**
   - Element registered (`character_subjects.json` + Kling Element poses under `Production/<Char>/poses/`)
   - Voice sample auditioned (`kling_voice_samples/<char>.mp3`)
   - **Pose-only** updates: Beat Gen **Add to Element** or `--refresh-poses-only`
   - **Voice refresh:** only with `--refresh-voice --confirm-voice-overwrite` + A/B one known-good beat
4. **Canonical BG refs** wired per beat (or segment defaults).

## Smoke before batch redo

For each Element-bound speaker in the event:

1. Pick **one** beat (not the whole batch).
2. Generate O3 once — confirm female/male voice, char ref, prompt V2 shape in sidecar.
3. Listen to delivery; compare to a reference beat if voice sounds wrong.
4. Only then batch redo / Send to Stitcher.

## After tooling changes

```bash
cd ~/Projects/mindfulnest-tooling
bash Production/scripts/deploy_storyboard_v59.sh --event Event_N
```

Hard refresh Storyboard — header `build-sha` must match latest commit.

## Proof artifacts to keep

- Deploy log showing `verify_o3_intro_contract` + live prompt smoke pass
- `build-sha` Kim sees in UI
- One job log under `Event_N/arlo_o3_jobs/` for the smoke beat

## Common “looks like code bug but is setup”

| Symptom | Usually |
|---------|---------|
| Generic/wrong voice | Missing or drifted Element voice bind — not beat-specific code |
| Char ref mismatch toast | Library PNG not on Element — Add to Element pose |
| Prompt reverts on refresh | Empty `scene_notes` + no framing keywords — use closeup/medium shot/head and torso |
| Beat vanished after edit | Sidecar race (fixed in code) — hard refresh; if persists, check deploy sha |
