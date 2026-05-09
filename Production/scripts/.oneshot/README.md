# One-shot scripts

Scripts in this directory are NOT permanent infrastructure. They are
date-stamped one-time data migrations or diagnostics. They run once
per the situation that prompted them and are then archived or
deleted.

DO NOT add tools here unless they are explicitly one-shot. Permanent
beat/state management belongs in `Production/scripts/` at the parent
level OR through the v59 mutation channel (`pathappPatch`).

When a script's purpose is fulfilled:
- Move to `Production/scripts/.archive/<YYYY-MM-DD>/` with the
  `prod_activity_log` row id captured in a sidecar README, OR
- Delete entirely if no archival value

Discoverability for Claude: `ls Production/scripts/.oneshot/` before
creating a new beat-management tool — there may be one already. The
shared utility is `Production/lib/directus_admin_client.py` +
`StateManager.mutate_video_state` from `production_server.py`.

Established 2026-05-05 per `DISPLAY_ORDER_STRICT_V1` architectural
tighten — Kim flagged "patches on patches" risk; the redundant
`clean_orphan_beats_v3.py` was deleted in favor of write-time server
prune; one-shot scripts are now visibly separated from permanent
infrastructure.
