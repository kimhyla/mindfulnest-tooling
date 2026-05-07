# Arc Release Schedule
> **GENERATED** by `generate_arc_release_schedule.py` — do not edit manually
> Parameters: cadence_fast=3.0/wk, cadence_aspir=2.0/wk, buffer=2wk, production_lead=4wk
> Launch date: [PENDING — re-run with --launch-date when launch date locks]
> Generated: 2026-04-25 17:58 UTC
>
> Arc 1 is bundled at install (LD-282) — schedule covers Arcs 2-10 only.
> **3×/wk column** = fastest-family worst-case planning anchor (LD-352: uncapped therapist prescription).
> **2×/wk column** = aspirational default (LD-339 Parent Weekly Plan, 26wk program).
> CDN-live signal = Firestore `arc_manifests/{arcId}` existence (LD-406).
> Re-run generator after any change to launch date or cadence assumption.

| Arc | Mods | 3×/wk CDN Deadline | 3×/wk Prod Start | 2×/wk CDN Deadline | 2×/wk Prod Start |
|-----|------|--------------------|------------------|--------------------|------------------|
| Arc 2 | 6 | T+4wk | AT LAUNCH | T+5wk | T+1wk |
| Arc 3 | 6 | T+6wk | T+2wk | T+8wk | T+4wk |
| Arc 4 | 6 | T+8wk | T+4wk | T+11wk | T+7wk |
| Arc 5 | 6 | T+10wk | T+6wk | T+14wk | T+10wk |
| Arc 6 | 6 | T+12wk | T+8wk | T+17wk | T+13wk |
| Arc 7 | 6 | T+14wk | T+10wk | T+20wk | T+16wk |
| Arc 8 | 6 | T+16wk | T+12wk | T+23wk | T+19wk |
| Arc 9 | 6 | T+18wk | T+14wk | T+26wk | T+22wk |
| Arc 10 | 5 | T+20wk | T+16wk | T+29wk | T+25wk |

> Launch date not yet locked — dates shown as relative offsets from T (launch day).

## Activation instructions (when launch date locks)

```bash
# 1. Re-run generator with the locked launch date
python3 Production/scripts/generate_arc_release_schedule.py \
    --launch-date YYYY-MM-DD --write-md Production/ARC_RELEASE_SCHEDULE.md

# 2. Apply Directus migration (one-time)
python3 Production/migrations/create_prod_arc_release_schedule.py --apply

# 3. Write schedule rows to Directus
python3 Production/scripts/generate_arc_release_schedule.py \
    --launch-date YYYY-MM-DD --write-directus

# 4. Uncomment the arc_cadence_monitor launchd plist entry in
#    ~/Library/LaunchAgents/com.mindfulnest.arc-cadence-monitor.plist
#    and run: launchctl load ~/Library/LaunchAgents/com.mindfulnest.arc-cadence-monitor.plist
```

## Slip-handling policy

When an arc misses its production-start deadline:
- `arc_cadence_monitor.py` creates a CRITICAL `app_blockers` row
- **No auto-cascade** — downstream deadlines do not shift automatically
- Kim re-runs this generator with an updated `--launch-date` (or adjusted `--buffer-weeks`) to see revised deadlines
- Re-running overwrites this file and upserts Directus rows (idempotent)

## Stream F Item 8 (post-launch)

`prod_family_velocity_observations` collection and real family-velocity telemetry
are deferred to Stream F Item 8, activating T+4 weeks post-launch.
See `app_blockers` feature_id=stream_f_item_8_velocity_telemetry.
