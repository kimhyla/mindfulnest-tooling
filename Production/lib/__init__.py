"""
MindfulNest production pipeline library.

Vendor wrappers + shared utilities. Per spec v2 §C9, vendor clients are SPLIT by workload:

- directus_admin_client: short admin requests (locked decisions, activity log, preflight reviews).
  Uses requests + urllib3.Retry for connection-pool reuse and idempotent retry semantics.

- wavespeed_poll_client: long-lived polling against WaveSpeed motion/lipsync endpoints.
  Uses http.client with OP_NO_TICKET + OP_NO_COMPRESSION + fresh SSL context per call,
  per LD-137 POLL_CLIENT_ROOT_CAUSE_HTTP_CLIENT. Never use requests/urllib for polling.

Other planned modules (Wave B+):
- elevenlabs_client
- asset_registration
- config_loaders (TOML + JSON + Zod schemas)
"""
