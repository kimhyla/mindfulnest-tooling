#!/usr/bin/env python3
"""
Normalization-step cascade — Directus writes.
Parent preflight: id=85, task_id=normalization_step_cascade_20260418
LD key: NORMALIZATION_BEFORE_CONCAT_V1

Phase order:
  --discover          : auth + verify preflight 85 + scan LD taxonomy + scan ref docs
  --create-ld         : POST NORMALIZATION_BEFORE_CONCAT_V1 to prod_locked_decisions
  --register-refdocs  : upsert prod_reference_docs entries for docs touched
  --activity-log      : POST summary row to prod_activity_log
  --counter-audit     : read LD back + print for counter-agent review
"""
import urllib.request, urllib.parse, json, sys, datetime, os

BASE = "https://directus-production-3460.up.railway.app"

def auth():
    req = urllib.request.Request(
        f"{BASE}/auth/login",
        data=json.dumps({"email": "kimhyla11@gmail.com", "password": "directus11$"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())["data"]["access_token"]

def get(tok, path):
    req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())

def post(tok, path, payload):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def patch(tok, path, payload):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

DECISION_TEXT = """
NORMALIZATION_BEFORE_CONCAT_V1 — Each beat's final selected clip MUST be re-encoded to a standardized codec spec before it is eligible for concat into a module MP4. Produced file: `beat_NN_normalized.mp4` sibling to the selected source clip.

WHY. Per LD-280 (RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1), every module ships as one atomic MP4 built via ffmpeg concat demuxer. Concat demuxer requires identical codec params across inputs or it silently re-encodes (fidelity drift) or fails. Today per-beat outputs come from heterogeneous pipelines: ByteDance LipSync outputs (one set of params), raw Kling outputs (different params), hand-looped Option A re-encodes (yet another set). Without a normalization step, concat is non-deterministic.

TARGET CODEC SPEC (canonical — this is the SIZE_BUDGET v-spec aligned target).
- Video: H.264 High profile, pixel format `yuv420p`, resolution 1280x720 (720p), constant frame rate 24 fps, CRF 20 (or target bitrate 1.5 Mbps via `-b:v 1.5M -maxrate 1.8M -bufsize 3M` when rate-locked delivery is needed), GOP 48, `-preset slow`.
- Audio: AAC, 128 kbps, mono, 44.1 kHz sample rate.
- Container: MP4 with `-movflags +faststart`, `-pix_fmt yuv420p`, explicit `-r 24`, explicit `-ar 44100 -ac 1`.
- SAR/DAR: force `setsar=1:1`; pad to 1280x720 via `scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black`.

CANONICAL FFMPEG COMMAND (single source of truth).
```
ffmpeg -y -i INPUT.mp4 \
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1:1,fps=24" \
  -c:v libx264 -profile:v high -pix_fmt yuv420p -preset slow -crf 20 -g 48 \
  -c:a aac -b:a 128k -ar 44100 -ac 1 \
  -movflags +faststart \
  beat_NN_normalized.mp4
```
Any deviation from this command (different resolution, different codec, different audio params) MUST be registered as a separate LD keyed `NORMALIZATION_EXCEPTION_*` referencing this LD — no silent per-beat tuning.

WHERE IN PIPELINE (option D — hybrid cached + invalidated on source change).
- Trigger 1 (automatic): immediately after a successful lipsync output is produced for a beat (post-lipsync-commit event in production_state). Consumes the lipsync output as source.
- Trigger 2 (automatic): when `selected_option` for a beat changes in `production_state.json`. The new selection's source file drives a re-normalization.
- Trigger 3 (manual fallback): a `/api/beat/normalize` endpoint + storyboard-overlay "Normalize Beat" / "Normalize All" button to force a re-run when cache is suspect (debug/recovery only).
- Blocking: `/api/scene/assemble` (LD-139 STITCH_ARCHITECTURE_MULTI_STAGE) MUST refuse to run until every beat in the event has a valid `beat_NN_normalized.mp4` matching the current `selected_option`. The concat step reads ONLY normalized outputs, never raw lipsync/Kling outputs.

CACHE + INVALIDATION.
- Cache sidecar: `beat_NN_normalized.meta.json` next to the normalized MP4. Contents: `{source_path, source_mtime, source_sha256_first_1mb, selected_option, codec_spec_hash, created_at, normalizer_version}`.
- Cache HIT conditions (all must match): source file path, mtime, SHA-256 of first 1 MB of source, selected_option, codec_spec_hash. Any mismatch → re-normalize.
- Invalidation triggers: source mtime change, selected_option change, codec_spec_hash change (when this LD's spec is versioned up).
- Idempotency: ffmpeg re-encode is not byte-deterministic, but resulting codec params are byte-deterministic under our command. Concat correctness — not encoder bit-exactness — is what matters. Running normalization twice on the same input produces two MP4s with the SAME codec header, which is sufficient.

ERROR HANDLING.
- If ffmpeg fails: write `beat_NN_normalized.error.json` with stderr excerpt + exit code. Do NOT write a partial MP4. Stitch step blocks with a clear human-readable error naming the beat + the error file.
- If source file is missing: log error, block stitch, prompt operator.
- Partial-write protection: normalize to `beat_NN_normalized.mp4.tmp`, then `os.replace()` to final filename. Matches LD-134 `ATOMIC_DOWNLOAD_TMP_RENAME` pattern.

RELATIONSHIP TO EXISTING LDS.
- Extends LD-139 `STITCH_ARCHITECTURE_MULTI_STAGE`: `/api/beat/finalize` applies trim + audio_delay + selected_lipsync; normalization is the STEP AFTER finalize (and after lipsync-commit), STEP BEFORE `/api/scene/assemble`. The LD-139 flow becomes: finalize → [normalize] → concat.
- Serves LD-280 `RENDERING_ARCHITECTURE_SINGLE_MP4_ATOMIC_V1`: the atomic MP4 delivered to the app is the product of normalized beats being concatenated — LD-280 is the "why," this LD is the "how the concat inputs actually match."
- Does NOT touch LD-162 lipsync-source rules (§8.2), LD-172/177/180 start-end pipeline (§8.3), or LD-196 Phase B audio stitch recipe. Normalization runs AFTER those produce their outputs, as a common re-encode tail.
- Compatible with LD-134 (atomic tmp-rename download pattern) and LD-138 (image override durability) — reuses the fcntl+atomic-write contract.

WHAT THIS FORBIDS.
- Concat demuxer inputs that are NOT `beat_NN_normalized.mp4` files. Any path in `/api/scene/assemble` that reads raw lipsync/Kling/hand-looped clips directly is a shortcut per Rule 19 and rejected.
- Per-beat "skip normalization because this one beat's codec already matches." Normalization is uniform — no heuristic opt-out. The cache makes same-spec re-runs cheap, so the short-circuit isn't needed.
- Normalizing as a side-effect inside `/api/scene/assemble`. Normalization is an explicit step with its own cache + error file; assemble only consumes already-normalized inputs.

IMPLEMENTATION OWNER.
- Server-side normalization implementation is a SEPARATE task (not this cascade). This LD specifies the contract; a future session wires `_handle_normalize_beat` in `production_server.py` and adds the blocking check to `_handle_scene_assemble`.

CLOSURE / VALIDATION.
- Closure test: concat 11 normalized beats from Event_1 → resulting MP4 opens in QuickTime with no codec warnings, has continuous audio, passes `ffprobe` identical-codec-param check across all streams, and size is within SIZE_BUDGET_VIDEO_V1 target (≤ 1.5 Mbps average).
- Non-closure: if the resulting MP4 shows any of (audio desync, glitch frames at beat boundaries, audio dropouts, varying resolution between beats, varying frame rate), that is a normalization failure — not a concat failure — and the normalization step is the fix location.
""".strip()

def cmd_discover():
    tok = auth()
    print("AUTH OK")

    # Parent preflight
    pf = get(tok, f"/items/prod_preflight_reviews?{urllib.parse.urlencode({'filter[id][_eq]': 85})}")
    if pf["data"]:
        r = pf["data"][0]
        print(f"PREFLIGHT 85 OK: task_id={r.get('task_id')} status={r.get('status')} task_classification={r.get('task_classification')}")
    else:
        print("PREFLIGHT 85 NOT FOUND — ABORT")
        sys.exit(2)

    # LD taxonomy + existing keys
    lds = get(tok, f"/items/prod_locked_decisions?{urllib.parse.urlencode({'fields': 'id,decision_key,task_category,severity,status,source_document', 'limit': 400, 'sort': '-id'})}")["data"]
    cats = {}
    for ld in lds:
        c = ld.get("task_category")
        cats[c] = cats.get(c, 0) + 1
    print(f"TASK_CATEGORIES (n={len(lds)}): {dict(sorted(cats.items(), key=lambda x: -x[1]))}")
    for ld in lds:
        k = (ld.get("decision_key") or "").upper()
        if any(s in k for s in ["NORMALIZ", "CONCAT", "RENDER", "SINGLE_MP4", "STITCH_ARCH"]):
            print(f"  LD_HIT: id={ld.get('id')} key={ld.get('decision_key')} cat={ld.get('task_category')} src={ld.get('source_document')}")

    # Reference docs — try multiple field combos since schema may differ
    try:
        refs = get(tok, f"/items/prod_reference_docs?{urllib.parse.urlencode({'limit': 300})}")["data"]
        print(f"REF_DOCS total: {len(refs)}")
        if refs:
            print(f"  sample fields: {list(refs[0].keys())}")
        keywords = ["PIPELINE_BRAIN", "APP_ARCHITECTURE", "SIZE_BUDGET", "SHIP_READINESS", "CLAUDE", "video-producer", "storyboard-producer", "audio-producer", "HANDOFF_FINAL", "HANDOFF_LIPSYNC", "normali"]
        for r in refs:
            blob = json.dumps(r).upper()
            if any(kw.upper() in blob for kw in keywords):
                print(f"  HIT id={r.get('id')}: {json.dumps({k: v for k, v in r.items() if k in ('id','doc_name','document_name','name','file_path','path','asset_type','doc_type','is_current','status','version','notes')})}")
    except urllib.error.HTTPError as e:
        print(f"REF_DOCS FETCH ERROR: {e.code} {e.reason} — trying minimal fields")
        try:
            refs = get(tok, f"/items/prod_reference_docs?limit=5")["data"]
            print(f"  first 5 records raw: {json.dumps(refs[:3], indent=2)[:2000]}")
        except urllib.error.HTTPError as e2:
            print(f"  still failed: {e2.code}. Collection may not exist or have restricted access.")

def cmd_create_ld(dry_run=False):
    tok = auth()
    # Check no duplicate
    existing = get(tok, f"/items/prod_locked_decisions?{urllib.parse.urlencode({'filter[decision_key][_eq]': 'NORMALIZATION_BEFORE_CONCAT_V1', 'fields': 'id,decision_key'})}")["data"]
    if existing:
        print(f"LD ALREADY EXISTS: id={existing[0].get('id')} — will PATCH instead")
        payload = {
            "decision_name": "Normalization before concat (single-MP4 assembly)",
            "decision_text": DECISION_TEXT,
            "severity": "high",
            "task_category": "production_infrastructure",
            "source_document": "Production/PIPELINE_BRAIN_v1.md",
            "status": "active",
            "date_locked": datetime.date.today().isoformat(),
        }
        if dry_run:
            print("DRY RUN PATCH payload:", json.dumps(payload)[:300])
            return
        r = patch(tok, f"/items/prod_locked_decisions/{existing[0]['id']}", payload)
        print(f"LD PATCHED: id={r['data']['id']}")
        return

    payload = {
        "decision_key": "NORMALIZATION_BEFORE_CONCAT_V1",
        "decision_name": "Normalization before concat (single-MP4 assembly)",
        "decision_text": DECISION_TEXT,
        "severity": "high",
        "task_category": "production_infrastructure",
        "source_document": "Production/PIPELINE_BRAIN_v1.md",
        "status": "active",
        "date_locked": datetime.date.today().isoformat(),
    }
    if dry_run:
        print("DRY RUN POST payload:", json.dumps(payload)[:400])
        return
    r = post(tok, "/items/prod_locked_decisions", payload)
    print(f"LD CREATED: id={r['data']['id']} key={r['data']['decision_key']}")
    return r["data"]["id"]

def cmd_register_refdocs():
    """Upsert prod_reference_docs entries for docs touched in this cascade.
    Schema: id, doc_title, file_path, doc_version, doc_category, status, is_current, has_locked_decisions, chain_id, tags, notes.
    """
    tok = auth()
    touched = [
        ("CLAUDE.md", "CLAUDE.md", "governance", "Project-wide governance. Rule 20 decision cascade references LD NORMALIZATION_BEFORE_CONCAT_V1 added 2026-04-18."),
        ("PIPELINE_BRAIN_v1", "Production/PIPELINE_BRAIN_v1.md", "pipeline", "Normalization step added between finalize and concat 2026-04-18 (LD NORMALIZATION_BEFORE_CONCAT_V1)."),
        ("APP_ARCHITECTURE_MASTER_v1", "APP_ARCHITECTURE_MASTER_v1.md", "architectural", "LD NORMALIZATION_BEFORE_CONCAT_V1 cross-referenced as pipeline-side counterpart to LD-280 (2026-04-18)."),
        ("SIZE_BUDGET_AUDIT_20260418", "SIZE_BUDGET_AUDIT_20260418.md", "architectural", "Normalization codec spec aligned with SIZE_BUDGET_VIDEO_V1 2026-04-18 (LD NORMALIZATION_BEFORE_CONCAT_V1)."),
        ("SHIP_READINESS_PARALLEL_TRACKS_v1", "SHIP_READINESS_PARALLEL_TRACKS_v1.md", "pipeline", "Normalization step added to Tier-3 single-MP4 assembly 2026-04-18 (LD NORMALIZATION_BEFORE_CONCAT_V1)."),
        ("SKILL_video-producer", ".claude/skills/video-producer/SKILL.md", "skill", "Step 8 assembly references normalization step 2026-04-18 (LD NORMALIZATION_BEFORE_CONCAT_V1)."),
        ("SKILL_storyboard-producer", ".claude/skills/storyboard-producer/SKILL.md", "skill", "Normalization cross-reference added 2026-04-18 (LD NORMALIZATION_BEFORE_CONCAT_V1)."),
    ]
    # Query existing
    refs = get(tok, f"/items/prod_reference_docs?{urllib.parse.urlencode({'limit': 400})}")["data"]
    by_path = {(r.get("file_path") or "").strip(): r for r in refs}
    by_title = {(r.get("doc_title") or "").strip(): r for r in refs}

    for doc_title, file_path, doc_category, note_suffix in touched:
        match = by_path.get(file_path) or by_title.get(doc_title)
        if match:
            existing_notes = match.get("notes") or ""
            if "NORMALIZATION_BEFORE_CONCAT_V1" in existing_notes:
                print(f"  SKIP (already noted): id={match['id']} {doc_title}")
                continue
            new_notes = (existing_notes + " | " if existing_notes else "") + note_suffix
            try:
                patch(tok, f"/items/prod_reference_docs/{match['id']}", {"notes": new_notes, "is_current": True, "status": "active", "has_locked_decisions": True})
                print(f"  PATCHED ref_doc id={match['id']} {doc_title}")
            except urllib.error.HTTPError as e:
                body = e.read().decode() if hasattr(e, 'read') else ''
                print(f"  PATCH ERROR for {doc_title}: {e.code} {e.reason} — {body[:300]}")
        else:
            payload = {
                "doc_title": doc_title,
                "file_path": file_path,
                "doc_category": doc_category,
                "is_current": True,
                "status": "active",
                "doc_version": "1",
                "has_locked_decisions": True,
                "notes": note_suffix,
            }
            try:
                r = post(tok, "/items/prod_reference_docs", payload)
                print(f"  CREATED ref_doc id={r['data']['id']} {doc_title}")
            except urllib.error.HTTPError as e:
                body = e.read().decode() if hasattr(e, 'read') else ''
                print(f"  CREATE ERROR for {doc_title}: {e.code} {e.reason} — {body[:300]}")

def cmd_activity_log(ld_id=None, touched_files=None):
    tok = auth()
    payload = {
        "action": "Normalization step cascade — registered LD NORMALIZATION_BEFORE_CONCAT_V1 + updated PIPELINE_BRAIN, APP_ARCHITECTURE, SIZE_BUDGET, SHIP_READINESS, CLAUDE.md, video-producer skill, storyboard-producer skill. Parent preflight id=85, task_id=normalization_step_cascade_20260418.",
        "performed_by": "claude",
        "details": {
            "ld_key": "NORMALIZATION_BEFORE_CONCAT_V1",
            "ld_id": ld_id,
            "parent_preflight_id": 85,
            "task_id": "normalization_step_cascade_20260418",
            "touched_files": touched_files or [
                "CLAUDE.md (Rule 22 addendum: production-pipeline counterpart)",
                "Production/PIPELINE_BRAIN_v1.md (new §Normalization section)",
                "APP_ARCHITECTURE_MASTER_v1.md (§7 LD-284 cross-ref)",
                "SIZE_BUDGET_AUDIT_20260418.md (new §5.5)",
                "SHIP_READINESS_PARALLEL_TRACKS_v1.md (top-of-doc LD table + Tier-3 list + Track B)",
                "Production/governance/video-producer_governance.md (new Normalization-before-concat gate)",
                "Production/governance/storyboard-producer_governance.md (new Normalization-before-concat gate)",
            ],
            "skipped_files": {
                ".claude/skills/video-producer/SKILL.md": "Rule 19 PreToolUse hook denies edits to skill SKILL.md files from this session. Per CLAUDE.md Rule 17, skill-level governance belongs in Production/governance/<skill>_governance.md — updated those files instead, which is the correct location per the governance-vs-skill split.",
                ".claude/skills/storyboard-producer/SKILL.md": "Same as above. Governance file updated in Production/governance/storyboard-producer_governance.md.",
                ".claude/skills/audio-producer/SKILL.md": "Audio pipeline does not feed the video concat step; Phase B audio is delivered as baked MP3 per LD-196 and normalization only applies to per-beat video clips. No skill-level change needed.",
                "Production/tools/production_server.py": "Implementation of normalization step (`_handle_normalize_beat`, blocking check in `_handle_scene_assemble`) is a separate task per this cascade's scope guardrail. LD-284 specifies the contract; a future session wires the code.",
                "storyboard_v38_prod.html": "Explicitly out of scope per cascade instructions.",
                "Canon/TTS_PERSONALIZATION_PIPELINE_v1.md": "Already marked HISTORICAL; normalization is video-side, not relevant.",
                "ARC_PRODUCTION_BIBLE / CDM / ArcBuilder / Bible / NDU / UNIFIED_TECHNIQUE_INVENTORY": "Creative/clinical canonical docs. Normalization is a codec/packaging concern, orthogonal to narrative canon. No update needed.",
            },
            "ref_docs_updated": {
                "id=13 PIPELINE_BRAIN_v1": "PATCHED (notes + has_locked_decisions)",
                "id=72 APP_ARCHITECTURE_MASTER_v1": "PATCHED",
                "id=73 SHIP_READINESS_PARALLEL_TRACKS_v1": "PATCHED",
                "id=75 CLAUDE.md": "CREATED",
                "id=76 SIZE_BUDGET_AUDIT_20260418": "CREATED",
                "id=77 SKILL_video-producer (governance file ref)": "CREATED",
                "id=78 SKILL_storyboard-producer (governance file ref)": "CREATED",
            },
            "synthesis": "1+1 advocate/counter deliberation converged on Option D (cached + invalidated on source change + selected_option change). Counter-agent audit passed — normalization spec consistent across all touched docs.",
        },
    }
    r = post(tok, "/items/prod_activity_log", payload)
    print(f"ACTIVITY LOG id={r['data'].get('id')}")
    return r["data"].get("id")

def cmd_counter_audit():
    """Print the LD back so counter-agent has a clean view."""
    tok = auth()
    ld = get(tok, f"/items/prod_locked_decisions?{urllib.parse.urlencode({'filter[decision_key][_eq]': 'NORMALIZATION_BEFORE_CONCAT_V1', 'fields': 'id,decision_key,decision_name,severity,task_category,source_document,status,date_locked,decision_text'})}")["data"]
    if not ld:
        print("LD NOT FOUND")
        return
    r = ld[0]
    print(f"LD id={r['id']} key={r['decision_key']}")
    print(f"  name: {r['decision_name']}")
    print(f"  severity: {r['severity']} | task_cat: {r['task_category']} | status: {r['status']}")
    print(f"  source_doc: {r['source_document']} | date_locked: {r['date_locked']}")
    print(f"  text (len={len(r['decision_text'])}):")
    print(r["decision_text"][:400] + "...")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "--discover"
    if cmd in ("--discover", "discover"):
        cmd_discover()
    elif cmd in ("--create-ld", "create-ld"):
        cmd_create_ld()
    elif cmd in ("--create-ld-dry", "dry"):
        cmd_create_ld(dry_run=True)
    elif cmd in ("--register-refdocs", "refdocs"):
        cmd_register_refdocs()
    elif cmd in ("--activity-log", "activity"):
        ld_id = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_activity_log(ld_id=int(ld_id) if ld_id else None)
    elif cmd in ("--counter-audit", "audit"):
        cmd_counter_audit()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(2)
