# Kling status fields — write-cache model (Phase 2)

**Marker:** `KLING_STATUS_WRITE_CACHE_V1`  
**Status:** Active — 2026-06-28  
**Authority:** `Production/tools/kling_stitch_readiness.py`

---

## Problem

Sidecar stores redundant fields that can drift:

| Field | Intended meaning today | Drift risk |
|-------|------------------------|------------|
| `kling_o3_video_path` | Active delivery clip on disk | Low — disk is truth |
| `kling_o3_status` | Legacy lifecycle + still-insert branch | High — export used to gate on this alone |
| `status` | Mirror of kling status | High — duplicate of above |

The 2026-06 Send to Stitcher regression was exactly this: **disk said ready, status said not**.

---

## Phase 1 (shipped)

- **Export read gate:** `beat_kling_stitch_export_ready` — for O3/element beats, active user-selectable file on disk + not job-busy wins. Status string is **not** the export gate (except still-insert explicit approve branch).
- **Write gate:** `finalize_kling_delivery_clip` / `align_beat_active_delivery_clip` / `active_delivery_sidecar_fields` — only paths that may set `kling_o3_status` when pinning delivery.
- **Client mirror:** `beatKlingStitchExportReady` / `beatHasActiveO3DeliveryClip`.

---

## Phase 2 rules (this spec)

### O3 / element / avatar beats

1. **Export / Send to Stitcher:** MUST call `beat_kling_stitch_export_ready` only — never `kling_o3_status === 'approved'`.
2. **Status fields:** treated as **write-cache** — updated when delivery is pinned, not read for export decisions.
3. **Heal on read:** `sync_kling_stitch_status_from_active_clip` may align cache from disk during session GET — does not create export authority.
4. **UI labels:** may display `kling_o3_status` for operator context — not for enabling export.

### Still-insert beats

- **Unchanged:** explicit operator stitch approve via `kling_o3_still_stitch_approved` or approved + clip branch in stitch contract.
- Import delivery → `still_rendered` + `status=draft` (not `approved` until operator approves).

### Forbidden (CI enforced)

- Client export files gating on `kling_o3_status === 'approved'`.
- Server `beat["kling_o3_status"] = "approved"` outside `kling_stitch_readiness.py`.
- Pipeline dict literals with inline `"kling_o3_status": "approved"`.

### Future Phase 3 (optional)

- Stop persisting `status` mirror entirely for O3 beats.
- Derive display badge from `kling_o3_video_path_exists` + job_busy only.

---

## Related specs

- `STORYBOARD_AUTHORITY_REGISTRY_v1.md`
- `STORYBOARD_AUTHORITY_FULL_AUDIT_2026-06-28.md`
- `BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1.md`
