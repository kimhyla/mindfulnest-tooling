---
name: restore-beats
description: Restore Beat Generator, Stitcher, Phase A/B production state from durable snapshots. Use when Kim says "restore the beats", "restore beat gen", "beats are gone", or asks to recover trims/voiceovers/stitcher state.
---

# Restore beats (production snapshot)

## What gets backed up automatically

Every write to these files updates `Production/.production_snapshots/latest/`:

- `beat_generator_state.json` — all Beat Gen beats (trims, O3 status, still voiceovers, magic paths)
- `tools/stitch_editor_state.json` — Stitcher slots, SFX, beat boundaries, transitions
- `Production/Event_N/production_state.json` — Storyboard beats, Phase A/B pins, lipsync files
- `Production/Event_N/phase_*_lipsync_*.json` — lipsync audio lineage sidecars

Timestamped archives land in `Production/.production_snapshots/archive/` (every ~5 min during active writes, or on explicit backup).

**Media (MP4/MP3) is not copied** — it stays on disk under `Event_N/`. Snapshots restore the JSON that points at those files.

## When Kim says "restore the beats"

1. **Stop storyboard servers** for affected events (or restart after restore).
2. **List snapshots** (optional):
   ```bash
   cd ~/Projects/mindfulnest-tooling
   python3 Production/scripts/restore_production_snapshot.py --list
   ```
3. **Restore latest** (all events):
   ```bash
   python3 Production/scripts/restore_production_snapshot.py --latest
   ```
4. **Restore one event only**:
   ```bash
   python3 Production/scripts/restore_production_snapshot.py --latest --event Event_2
   ```
5. **Restore a specific archive**:
   ```bash
   python3 Production/scripts/restore_production_snapshot.py --snapshot-id 20260616T141500Z
   ```
6. **Mirror tooling → Dropbox** if Python changed (`post_tooling_change_smoke.sh` step 3).
7. **Restart event servers** and hard-refresh Beat Generator / Stitcher / Phase tabs.
8. **Verify**: curl `/api/bg/session-state?scope_event_id=Event_2&scope_video_role=intro` — beat count matches expectation.

Pre-restore safety: restore script auto-creates `archive/*_pre_restore` unless `--no-pre-backup`.

## Manual backup (before risky ops)

```bash
python3 Production/scripts/backup_production_snapshot.py
```

## Deploy note

Snapshot hooks live in `beat_generator.write_sidecar` and `production_server` state writes. After editing those files, mirror tooling → Dropbox and restart servers so hooks are live on Kim's runtime.

## Do not use for

- Recovering deleted MP4/MP3 files (use Dropbox version history or `Event_N/kling_o3_clips/_preserved/`)
- Git-based restore (sidecar is not in git)
