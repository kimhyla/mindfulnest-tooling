# Mac Phase A layered readiness

**Default Send route:** `PHASE_A_ARLO_LAYERED_ROUTE_V1`  
(green `full_loop_30s` idle → Kling lipsync → chromakey onto chair plate)

**ByteDance is opt-in only:** set `MN_PHASE_A_BYTEDANCE=1` (or POST body
`{"route":"bytedance"}`). Do not set this for normal Send.

**Branch:** `feature/phase-ab-beatgen-layered-durability` (SHA `2e80ce8` or later)

Windows cannot start Mac launchd. Run deploy/start **on the Mac**.

---

## Kim steps (Event_6 stem/lipsync already exist)

1. **Get the media into Event_6** (Dropbox search often misses these):
   - Prefer folder:  
     `Dropbox/.../Production/_TRANSFER_TO_MAC/Event_6_phase_a_20260723/`
   - Or unzip Downloads copy:  
     `Event_6_phase_a_stem_and_lipsync_20260723.zip`
   - Copy the three files into:  
     `.../Production/Event_6/`
     - `phase_a_voice_stem_20260723-094806.mp3`
     - `phase_a_lipsync_20260723-110753.mp4`
     - `phase_a_lipsync_20260723-110753.json`

2. **Checkout the feature branch** (in `mindfulnest-tooling`):
   ```bash
   git fetch
   git checkout feature/phase-ab-beatgen-layered-durability
   git pull
   ```

3. **Deploy or start Event_6** (Mac only):
   ```bash
   bash Production/scripts/deploy_option_b.sh --event Event_6
   ```
   Or at minimum:
   ```bash
   bash Production/scripts/start_event_server.sh Event_6
   ```

4. **Open and hard-refresh:**  
   http://localhost:5116/?event=Event_6

5. **Optional verify before Send:**
   ```bash
   bash Production/scripts/verify_phase_a_layered_mac.sh Event_6
   ```

---

## Any future event (layered Phase A Send)

Category-1 code is global after checkout + deploy. Category-2 ARLO assets are
shared once under Dropbox:

| Asset | Path under `Production/` |
|-------|--------------------------|
| Green idle | `NEW STYLE CHARACTERS/ARLO/arlo_gesture_idle_full_loop_30s_green_1920x1080_v1.mp4` |
| Chair plate | `NEW STYLE CHARACTERS/ARLO/arlo_room_plate_chair_study_1280x720_v2.png` |
| Key canvas | `NEW STYLE CHARACTERS/ARLO/arlo_key_canvas_1280x720_v1.png` |

Event folder only needs that event’s stem (and outputs). Missing ARLO assets =
Send will fail on every event until Dropbox has them.

---

## State pin fields (after copying transfer files)

Confirm / set on Event_6 Phase A state:

- `phase_a_voice_stem` → `phase_a_voice_stem_20260723-094806.mp3`
- lipsync video pin → `phase_a_lipsync_20260723-110753.mp4`
- matching sidecar json → `phase_a_lipsync_20260723-110753.json`

---

## Code contract (do not regress)

`handle_phase_a_lipsync` in `Production/tools/server_handlers/phases.py`:

- Default → `_handle_phase_a_lipsync_layered`
- Only ByteDance when `MN_PHASE_A_BYTEDANCE=1` or body `route=bytedance`

Marker: `PHASE_A_ARLO_LAYERED_ROUTE_V1`  
Tech spec: `TECH_SPEC_PHASE_A_ARLO_LAYERED_DEFAULT_ROUTE_v1.md`
