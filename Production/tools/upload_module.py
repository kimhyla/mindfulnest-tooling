#!/usr/bin/env python3
"""
Stream F — Module MP4 Upload Pipeline

Governing LDs:
  LD-406 CDN_PROVIDER_V1            — Firebase Storage (gs://mindfulnestkids.firebasestorage.app)
  LD-404 MANIFEST_SCHEMA_V1         — {moduleId, contentHash, cdnUrl, sizeBytes, phaseBoundaries, arcId}
  LD-283 SIZE_BUDGET_PER_MODULE_V1  — 60 MB target / 80 MB hard ceiling
  LD-280 SINGLE_MP4_ATOMIC_V1       — one atomic MP4 per module, never overwrite in-flight
  LD-282 CATALOG_DELIVERY_ARC_AT_A_TIME_V1 — arc-level manifest after all modules in arc uploaded

Commands:
  upload   — upload a finalized MP4, write Firestore manifest + Directus records
  publish  — flip published: true on a staged module (makes it visible to app)
  status   — show current upload state for a module
  arc-manifest — write arc-level manifest to Firestore after all modules in arc are staged

Usage examples:
  doppler run -- python3 upload_module.py upload \\
      --module m1 --arc arc1 \\
      --file /path/to/module_M1_v1.mp4 \\
      --phase-boundaries 45.2,180.5

  doppler run -- python3 upload_module.py publish --module m1

  doppler run -- python3 upload_module.py status --module m1

  doppler run -- python3 upload_module.py arc-manifest --arc arc1

Auth: uses gcloud user credentials (kimhyla11@gmail.com) for Storage + Firestore.
      Run `gcloud auth login` if token expires.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from directus_admin_client import DirectusAdminClient

# ─── Constants ────────────────────────────────────────────────────────────────

FIREBASE_PROJECT = "mindfulnestkids"
STORAGE_BUCKET = "mindfulnestkids.firebasestorage.app"
FIRESTORE_BASE = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT}/databases/(default)/documents"

# LD-283 size limits
SIZE_TARGET_BYTES = 60 * 1024 * 1024   # 60 MB
SIZE_CEILING_BYTES = 80 * 1024 * 1024  # 80 MB hard ceiling


# ─── Directus helpers ─────────────────────────────────────────────────────────

def _directus_module_int_id(module_id_str: str) -> Optional[int]:
    """
    Look up the integer primary key of a prod_modules row by m_number string (e.g. 'm1').
    prod_modules.m_number is stored as integer (1, 2, …). Parses 'm1' → 1.
    Returns None if not found — callers must handle None by omitting the FK field.
    """
    try:
        num = int(module_id_str.lstrip("mM"))
        client = DirectusAdminClient()
        rows = client.get_items(
            "prod_modules",
            filters={"m_number": {"_eq": num}},
            fields=["id", "m_number"],
            limit=1,
        )
        return rows[0]["id"] if rows else None
    except Exception:
        return None


# ─── Auth ─────────────────────────────────────────────────────────────────────

def gcloud_access_token() -> str:
    """Get a short-lived gcloud user access token."""
    try:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if not token:
            raise RuntimeError("Empty token returned")
        return token
    except Exception as e:
        sys.exit(f"ERROR: gcloud auth failed — {e}\nRun: gcloud auth login")


# ─── Firestore helpers ─────────────────────────────────────────────────────────

def firestore_get(collection: str, doc_id: str, token: str) -> Optional[dict]:
    """GET a Firestore document. Returns None if not found."""
    url = f"{FIRESTORE_BASE}/{collection}/{doc_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def firestore_patch(collection: str, doc_id: str, fields: dict, token: str) -> dict:
    """
    PATCH specific fields on a Firestore document.
    Writes only the named fields — non-destructive update.
    Fields dict maps field name → Python value (str, int, float, bool, list, None).
    """
    def _to_firestore_value(v):
        if v is None:
            return {"nullValue": None}
        if isinstance(v, bool):
            return {"booleanValue": v}
        if isinstance(v, int):
            return {"integerValue": str(v)}
        if isinstance(v, float):
            return {"doubleValue": v}
        if isinstance(v, list):
            return {"arrayValue": {"values": [_to_firestore_value(i) for i in v]}}
        return {"stringValue": str(v)}

    fs_fields = {k: _to_firestore_value(v) for k, v in fields.items()}
    update_mask = "&".join(f"updateMask.fieldPaths={k}" for k in fields)
    url = f"{FIRESTORE_BASE}/{collection}/{doc_id}?{update_mask}"
    body = json.dumps({"fields": fs_fields}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


# ─── SHA-256 ──────────────────────────────────────────────────────────────────
#
# IMPORTANT: This must match the hash computed by the app's downloadManager.ts,
# which uses expo-crypto digestStringAsync on the base64-encoded file content
# (FileSystem.readAsStringAsync with EncodingType.Base64 → SHA256 of that string).
# SHA256 of raw bytes ≠ SHA256 of base64(raw bytes) — these are different digests.
# Fixed 2026-04-25 (Stream C preflight 156, counter-agent CRITICAL finding).

def sha256_file(path: Path) -> str:
    """SHA-256 of base64(file bytes) — matches expo-crypto digestStringAsync behavior."""
    import base64 as _base64
    raw = path.read_bytes()
    b64_str = _base64.b64encode(raw).decode("ascii")
    return hashlib.sha256(b64_str.encode("utf-8")).hexdigest()


# ─── gsutil helpers ───────────────────────────────────────────────────────────

def gsutil_upload(local_path: Path, gcs_path: str, dry_run: bool = False) -> None:
    """Upload a file to GCS with checksum metadata."""
    cmd = [
        "gsutil", "-h", "Content-Type:video/mp4",
        "cp", str(local_path), gcs_path,
    ]
    if dry_run:
        print(f"  [dry-run] Would run: {' '.join(cmd)}")
        return
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gsutil upload failed:\n{result.stderr}")


def gsutil_stat(gcs_path: str) -> dict:
    """Return metadata dict from gsutil stat."""
    result = subprocess.run(
        ["gsutil", "stat", gcs_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gsutil stat failed:\n{result.stderr}")
    meta = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta


def next_version(module_id: str, token: str) -> int:
    """Read current content_version from Firestore; return next version."""
    doc = firestore_get("modules", module_id, token)
    if not doc:
        return 1
    fields = doc.get("fields", {})
    ver_field = fields.get("content_version", {})
    current = int(ver_field.get("integerValue", "0"))
    return current + 1


# ─── Commands ────────────────────────────────────────────────────────────────

def cmd_upload(args) -> None:
    module_id = args.module.lower()      # e.g. "m1"
    arc_id = args.arc.lower()            # e.g. "arc1"
    mp4_path = Path(args.file).expanduser().resolve()

    if not mp4_path.exists():
        sys.exit(f"ERROR: File not found: {mp4_path}")
    if mp4_path.suffix.lower() != ".mp4":
        sys.exit(f"ERROR: File must be .mp4, got: {mp4_path.suffix}")

    size_bytes = mp4_path.stat().st_size

    # LD-283 size check
    if size_bytes > SIZE_CEILING_BYTES:
        sys.exit(
            f"ERROR: File exceeds LD-283 hard ceiling of 80 MB "
            f"({size_bytes / 1024 / 1024:.1f} MB). Re-encode before uploading."
        )
    if size_bytes > SIZE_TARGET_BYTES:
        print(
            f"WARNING: File exceeds 60 MB target ({size_bytes / 1024 / 1024:.1f} MB). "
            f"Under 80 MB hard ceiling — proceeding."
        )
    else:
        print(f"  Size: {size_bytes / 1024 / 1024:.1f} MB ✓ (under 60 MB target)")

    # Phase boundaries — PHASE_BOUNDARIES_NAMED_OBJECT_V1.
    # Accepts: intro=0,phase_a=15.2,phase_b=42.7,resolution=310.1
    # end_s is next entry's start_s; last entry's end_s = --duration (or start_s if omitted).
    phase_boundaries: list[dict] = []
    if args.phase_boundaries:
        try:
            pairs = [p.split("=", 1) for p in args.phase_boundaries.split(",")]
            starts = [(name.strip(), float(s.strip())) for name, s in pairs]
            total_dur = getattr(args, "duration", 0.0) or 0.0
            phase_boundaries = [
                {
                    "name": name,
                    "start_s": start_s,
                    "end_s": starts[i + 1][1] if i + 1 < len(starts) else total_dur or start_s,
                }
                for i, (name, start_s) in enumerate(starts)
            ]
        except (ValueError, IndexError):
            sys.exit(
                "ERROR: --phase-boundaries must be name=start_s pairs, "
                "e.g. intro=0,phase_a=15.2,phase_b=42.7,resolution=310.1"
            )

    print(f"\nComputing SHA-256...")
    content_hash = sha256_file(mp4_path)
    print(f"  Hash: {content_hash[:16]}...")

    token = gcloud_access_token()
    version = next_version(module_id, token)
    storage_key = f"modules/{arc_id}/{module_id}/module_v{version}.mp4"
    gcs_path = f"gs://{STORAGE_BUCKET}/{storage_key}"
    cdn_url = gcs_path  # D1 CF resolves to signed URL at download time (LD-406)

    print(f"\nUploading to {gcs_path} ...")
    gsutil_upload(mp4_path, gcs_path, dry_run=args.dry_run)

    if not args.dry_run:
        print("  Verifying upload via gsutil stat...")
        meta = gsutil_stat(gcs_path)
        # Validate size matches
        remote_size_str = meta.get("Content-Length") or meta.get("Content length", "0")
        try:
            remote_size = int(remote_size_str.replace(",", ""))
        except ValueError:
            remote_size = 0
        if remote_size and remote_size != size_bytes:
            sys.exit(
                f"ERROR: Size mismatch after upload. "
                f"Local={size_bytes} Remote={remote_size}. Aborting manifest write."
            )
        print(f"  Upload verified ✓ ({remote_size or size_bytes} bytes)")

    # Write Firestore manifest (PATCH — non-destructive)
    print(f"\nWriting Firestore manifest to modules/{module_id} ...")
    manifest_fields = {
        "moduleId": module_id,
        "contentHash": content_hash,
        "cdnUrl": cdn_url,
        "sizeBytes": size_bytes,
        "phaseBoundaries": phase_boundaries,
        "arcId": arc_id,
        "content_version": version,
        "published": False,
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
        "status": "staged",
    }

    if not args.dry_run:
        try:
            firestore_patch("modules", module_id, manifest_fields, token)
            print(f"  Firestore manifest written ✓ (published: false)")
        except Exception as e:
            print(f"  WARNING: Firestore write failed — {e}")
            print(f"  Queuing to pending_directus_writes.json for retry.")
            _queue_offline({
                "_type": "firestore_patch",
                "collection": "modules",
                "doc_id": module_id,
                "fields": manifest_fields,
            })
    else:
        print(f"  [dry-run] Would PATCH modules/{module_id} with manifest fields")

    # Write Directus prod_assets row
    # prod_assets schema: module_id (int FK, required), asset_type, asset_name, file_path, status, notes
    print(f"\nRegistering in Directus prod_assets ...")
    module_int_id = _directus_module_int_id(module_id)
    if module_int_id is None:
        sys.exit(
            f"ERROR: Module '{module_id}' not found in Directus prod_modules. "
            f"Add the module row to prod_modules before uploading its MP4."
        )
    directus_payload = {
        "asset_type": "module_mp4",
        "asset_name": f"{module_id}_v{version}.mp4",
        "file_path": storage_key,
        "status": "pending",
        "notes": json.dumps({
            "arc_id": arc_id, "version": version,
            "size_bytes": size_bytes, "content_hash": content_hash,
            "phase_boundaries": phase_boundaries, "stream": "F",
        }),
    }
    if module_int_id is not None:
        directus_payload["module_id"] = module_int_id
    if not args.dry_run:
        try:
            client = DirectusAdminClient()
            asset_row = client.post_item("prod_assets", directus_payload)
            asset_id = asset_row.get("id", "?")
            print(f"  Directus prod_assets id={asset_id} ✓")
        except Exception as e:
            print(f"  WARNING: Directus prod_assets write failed — {e}")
            _queue_offline({"_type": "directus_post", "collection": "prod_assets", "payload": directus_payload})

    # Write activity log — module_int_id already resolved above (non-None guaranteed)
    # prod_activity_log schema: action (text), module_id (int FK nullable), details (json)
    activity_payload: dict = {
        "action": f"module_upload_{module_id}_v{version}",
        "details": json.dumps({
            "module_id_str": module_id, "arc_id": arc_id, "version": version,
            "gcs_path": gcs_path, "size_bytes": size_bytes,
            "content_hash": content_hash[:16] + "...",
            "phase_boundaries": phase_boundaries, "stream": "F",
            "task_id": "stream-f-upload-cmd",
        }),
    }
    if module_int_id is not None:
        activity_payload["module_id"] = module_int_id
    if not args.dry_run:
        try:
            client = DirectusAdminClient()
            client.post_item("prod_activity_log", activity_payload)
            print(f"  Activity log written ✓")
        except Exception as e:
            print(f"  WARNING: Activity log write failed — {e}")
            _queue_offline({"_type": "directus_post", "collection": "prod_activity_log", "payload": activity_payload})

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UPLOAD COMPLETE (staged, not yet live)
  Module:  {module_id}  v{version}
  Arc:     {arc_id}
  Size:    {size_bytes / 1024 / 1024:.1f} MB
  Hash:    {content_hash[:32]}...
  GCS:     {gcs_path}
  Status:  staged (published=false)

To make this module visible to the app, run:
  python3 upload_module.py publish --module {module_id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


def cmd_publish(args) -> None:
    module_id = args.module.lower()
    token = gcloud_access_token()

    doc = firestore_get("modules", module_id, token)
    if not doc:
        sys.exit(f"ERROR: No Firestore document found for modules/{module_id}. Upload first.")

    fields = doc.get("fields", {})
    if not fields.get("cdnUrl"):
        sys.exit(f"ERROR: modules/{module_id} has no cdnUrl. Was it uploaded via this script?")
    if fields.get("published", {}).get("booleanValue"):
        print(f"modules/{module_id} is already published. Nothing to do.")
        return

    print(f"Publishing modules/{module_id} ...")
    firestore_patch("modules", module_id, {"published": True, "publishedAt": datetime.now(timezone.utc).isoformat()}, token)
    print(f"  published: true ✓")

    # Activity log — module_id is int FK; extra context in details JSON
    pub_int_id = _directus_module_int_id(module_id)
    pub_activity: dict = {
        "action": f"module_published_{module_id}",
        "details": json.dumps({
            "module_id_str": module_id, "stream": "F",
            "notes": f"Module {module_id} set to published=true — now visible to app.",
            "task_id": "stream-f-upload-cmd",
        }),
    }
    if pub_int_id is not None:
        pub_activity["module_id"] = pub_int_id
    try:
        client = DirectusAdminClient()
        client.post_item("prod_activity_log", pub_activity)
        print(f"  Activity log written ✓")
    except Exception as e:
        print(f"  WARNING: Activity log write failed — {e}")
        _queue_offline({"_type": "directus_post", "collection": "prod_activity_log", "payload": pub_activity})

    print(f"\n✓ {module_id} is now live — app will serve it on next manifest refresh.")


def cmd_status(args) -> None:
    module_id = args.module.lower()
    token = gcloud_access_token()

    doc = firestore_get("modules", module_id, token)
    if not doc:
        print(f"modules/{module_id}: NOT FOUND in Firestore")
        return

    fields = doc.get("fields", {})

    def fv(name, key="stringValue"):
        return fields.get(name, {}).get(key, fields.get(name, {}).get("booleanValue", fields.get(name, {}).get("integerValue", "—")))

    print(f"\nmodules/{module_id} status:")
    print(f"  arcId:           {fv('arcId')}")
    print(f"  contentHash:     {fv('contentHash')[:32]}..." if fv('contentHash') != '—' else "  contentHash:     —")
    print(f"  cdnUrl:          {fv('cdnUrl')}")
    print(f"  sizeBytes:       {fv('sizeBytes', 'integerValue')}")
    print(f"  content_version: {fv('content_version', 'integerValue')}")
    print(f"  published:       {fv('published', 'booleanValue')}")
    print(f"  status:          {fv('status')}")
    print(f"  uploadedAt:      {fv('uploadedAt')}")
    print(f"  publishedAt:     {fv('publishedAt')}")

    # Check GCS object exists
    cdn_url = fv("cdnUrl")
    if cdn_url and cdn_url.startswith("gs://"):
        result = subprocess.run(["gsutil", "stat", cdn_url], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"\n  GCS object: ✓ exists")
        else:
            print(f"\n  GCS object: ✗ NOT FOUND at {cdn_url}")


def cmd_arc_manifest(args) -> None:
    """
    Write a per-arc manifest to Firestore (LD-282 arc-at-a-time delivery).
    Document: arc_manifests/{arcId}
    Fields: {arcId, modules: [{moduleId, cdnUrl, contentHash, sizeBytes, phaseBoundaries}], publishedAt}
    All modules in arc must be staged (published=true preferred, or --force-unpublished).
    """
    arc_id = args.arc.lower()
    token = gcloud_access_token()

    # Discover module IDs for this arc from Firestore modules collection
    # We query all modules documents and filter by arcId field
    url = f"{FIRESTORE_BASE}/modules?pageSize=100"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        result = json.load(r)

    arc_modules = []
    for doc in result.get("documents", []):
        doc_fields = doc.get("fields", {})
        doc_arc = doc_fields.get("arcId", {}).get("stringValue", "")
        if doc_arc == arc_id:
            mid = doc_fields.get("moduleId", {}).get("stringValue", "")
            cdn = doc_fields.get("cdnUrl", {}).get("stringValue", "")
            hash_ = doc_fields.get("contentHash", {}).get("stringValue", "")
            size = int(doc_fields.get("sizeBytes", {}).get("integerValue", 0))
            boundaries = [
                v.get("doubleValue", v.get("integerValue", 0))
                for v in doc_fields.get("phaseBoundaries", {}).get("arrayValue", {}).get("values", [])
            ]
            published = doc_fields.get("published", {}).get("booleanValue", False)
            if mid and cdn:
                arc_modules.append({
                    "moduleId": mid,
                    "cdnUrl": cdn,
                    "contentHash": hash_,
                    "sizeBytes": size,
                    "phaseBoundaries": boundaries,
                    "published": published,
                })

    if not arc_modules:
        sys.exit(f"ERROR: No uploaded modules found for arcId='{arc_id}'. Upload modules first.")

    unpublished = [m["moduleId"] for m in arc_modules if not m["published"]]
    if unpublished and not getattr(args, "force_unpublished", False):
        print(f"WARNING: {len(unpublished)} module(s) not yet published: {unpublished}")
        print("Include them anyway? Pass --force-unpublished to confirm.")
        if input("Include unpublished modules? [y/N] ").lower() != "y":
            sys.exit("Aborted.")

    arc_modules_clean = [{k: v for k, v in m.items() if k != "published"} for m in arc_modules]
    arc_manifest_fields = {
        "arcId": arc_id,
        "modules": arc_modules_clean,   # stored as array of maps — Firestore REST handles nested
        "publishedAt": datetime.now(timezone.utc).isoformat(),
        "module_count": len(arc_modules_clean),
    }

    # Firestore array-of-maps requires a different value structure
    def _map_value(d: dict) -> dict:
        def _v(val):
            if isinstance(val, bool):
                return {"booleanValue": val}
            if isinstance(val, int):
                return {"integerValue": str(val)}
            if isinstance(val, float):
                return {"doubleValue": val}
            if isinstance(val, list):
                return {"arrayValue": {"values": [_v(i) for i in val]}}
            return {"stringValue": str(val)}
        return {"mapValue": {"fields": {k: _v(v) for k, v in d.items()}}}

    # Build the modules array value
    modules_array_value = {
        "arrayValue": {"values": [_map_value(m) for m in arc_modules_clean]}
    }

    fs_fields = {
        "arcId": {"stringValue": arc_id},
        "modules": modules_array_value,
        "publishedAt": {"stringValue": datetime.now(timezone.utc).isoformat()},
        "module_count": {"integerValue": str(len(arc_modules_clean))},
    }

    update_mask = "&".join(f"updateMask.fieldPaths={k}" for k in fs_fields)
    url = f"{FIRESTORE_BASE}/arc_manifests/{arc_id}?{update_mask}"
    body = json.dumps({"fields": fs_fields}).encode()
    req = urllib.request.Request(
        url, data=body, method="PATCH",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        json.load(r)

    print(f"\narc_manifests/{arc_id} written ✓")
    print(f"  Modules included: {[m['moduleId'] for m in arc_modules_clean]}")
    print(f"  Total entries: {len(arc_modules_clean)}")

    try:
        client = DirectusAdminClient()
        client.post_item("prod_activity_log", {
            "action": f"arc_manifest_written_{arc_id}",
            "details": json.dumps({
                "arc_id": arc_id, "module_count": len(arc_modules_clean),
                "modules": [m["moduleId"] for m in arc_modules_clean],
                "stream": "F",
            }),
        })
    except Exception:
        pass


def cmd_rollback(args) -> None:
    """
    Roll back a published module to a fixed state.

    Path A (forward rollback — new file):
      Upload a replacement MP4 as the next version number.
      Atomically patch Firestore manifest: cdnUrl, contentHash, sizeBytes,
      content_version, rollback_from_version, rollback_reason, rollback_at.
      Keeps published=true so the app immediately serves the new version.
      App clients detect contentHash change on next cache verification and
      re-download automatically (Stream C item 16 / LD-404 contentHash).

    Path B (backward revert — existing version):
      Re-point Firestore manifest to an already-uploaded earlier GCS version.
      No new file upload. Verifies GCS object exists before patching.
      Same audit fields written.

    GCS retention note: old versions are intentionally kept on GCS (never deleted)
    per LD-406 "never overwrite in-flight." ~3 versions × 60 MB × 59 modules ≈ 10 GB
    max = ~$0.026/month. Review and clean up manually if budget becomes a concern.
    """
    module_id = args.module.lower()
    reason = (args.reason or "").strip()
    if not reason:
        sys.exit("ERROR: --reason is required for audit trail. Describe what was wrong with the current version.")

    token = gcloud_access_token()

    # ── Guard: manifest must already exist (module must have been uploaded) ──
    doc = firestore_get("modules", module_id, token)
    if not doc:
        sys.exit(f"ERROR: No Firestore manifest for modules/{module_id}. Run 'upload' first.")

    fields = doc.get("fields", {})
    current_cdn_url = fields.get("cdnUrl", {}).get("stringValue", "")
    if not current_cdn_url:
        sys.exit(f"ERROR: modules/{module_id} has no cdnUrl. Was it uploaded via this script?")

    # Read arc_id from Firestore (not from args — avoids mismatch)
    arc_id = fields.get("arcId", {}).get("stringValue", "")
    if not arc_id:
        sys.exit(f"ERROR: modules/{module_id} Firestore manifest has no arcId field. Re-upload with 'upload' command to repair.")

    current_version = int(fields.get("content_version", {}).get("integerValue", "0"))
    current_hash = fields.get("contentHash", {}).get("stringValue", "")
    current_published = fields.get("published", {}).get("booleanValue", False)

    if not current_published:
        print(f"NOTE: modules/{module_id} is staged but not yet published. Rollback will upload/revert and publish it.")

    # ════════════════════════════════════════════════════════
    # PATH B — backward revert to existing GCS version
    # ════════════════════════════════════════════════════════
    if args.revert_to_version is not None:
        target_version = args.revert_to_version

        # Guard: cannot revert to current version (no-op)
        if target_version == current_version:
            sys.exit(f"ERROR: --revert-to-version {target_version} is the current live version. Nothing to revert.")

        # Guard: cannot revert to a future version
        if target_version > current_version:
            sys.exit(f"ERROR: --revert-to-version {target_version} is higher than current version {current_version}. Use 'upload' to add a new version.")

        target_key = f"modules/{arc_id}/{module_id}/module_v{target_version}.mp4"
        target_gcs = f"gs://{STORAGE_BUCKET}/{target_key}"

        # Guard: verify GCS object actually exists before touching Firestore
        print(f"Verifying GCS object at {target_gcs} ...")
        stat_result = subprocess.run(["gsutil", "stat", target_gcs], capture_output=True, text=True)
        if stat_result.returncode != 0:
            sys.exit(
                f"ERROR: Version {target_version} not found on GCS at {target_gcs}.\n"
                f"Cannot revert — GCS object may have been manually deleted.\n"
                f"Available: check 'gsutil ls gs://{STORAGE_BUCKET}/modules/{arc_id}/{module_id}/'"
            )
        print(f"  GCS object confirmed ✓")

        # Read size from GCS stat for accurate manifest
        meta = gsutil_stat(target_gcs)
        size_str = (meta.get("Content-Length") or meta.get("Content length", "0")).replace(",", "")
        try:
            size_bytes = int(size_str)
        except ValueError:
            size_bytes = 0

        # Try to recover SHA-256 for target version from Directus (stored in notes JSON)
        content_hash = ""
        try:
            client = DirectusAdminClient()
            assets = client.get_items(
                "prod_assets",
                filters={"asset_name": {"_eq": f"{module_id}_v{target_version}.mp4"}},
                fields=["id", "notes"],
            )
            if assets:
                notes_str = assets[0].get("notes", "")
                try:
                    notes_data = json.loads(notes_str)
                    content_hash = notes_data.get("content_hash", "")
                    if not size_bytes:
                        size_bytes = notes_data.get("size_bytes", 0)
                except (json.JSONDecodeError, TypeError):
                    pass
        except Exception:
            pass

        if not content_hash:
            print(
                "WARNING: SHA-256 for target version not found in Directus prod_assets.\n"
                "  contentHash will be cleared — app will detect mismatch and re-download (correct behavior)."
            )

        patch_fields: dict = {
            "cdnUrl": target_gcs,
            "content_version": target_version,
            "published": True,
            "rollback_from_version": current_version,
            "rollback_reason": reason,
            "rollback_at": datetime.now(timezone.utc).isoformat(),
        }
        if content_hash:
            patch_fields["contentHash"] = content_hash
        if size_bytes:
            patch_fields["sizeBytes"] = size_bytes

        print(f"Patching Firestore manifest: v{current_version} → v{target_version} ...")
        firestore_patch("modules", module_id, patch_fields, token)
        print(f"  Firestore manifest updated ✓")

        _write_rollback_activity(
            module_id=module_id,
            arc_id=arc_id,
            from_version=current_version,
            to_version=target_version,
            reason=reason,
            path="B",
            new_gcs=target_gcs,
            new_hash=content_hash,
            new_size=size_bytes,
        )

        print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROLLBACK COMPLETE (Path B — backward revert)
  Module:  {module_id}
  Reverted: v{current_version} → v{target_version}
  Reason:  {reason}
  GCS:     {target_gcs}
  Status:  published=true

App clients will detect contentHash change on next cache
verification and re-download automatically (LD-404 + Stream C item 16).
To undo this revert: run rollback again with the desired version.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
        return

    # ════════════════════════════════════════════════════════
    # PATH A — forward rollback: upload replacement file
    # ════════════════════════════════════════════════════════
    if not args.file:
        sys.exit(
            "ERROR: Provide either --file <path> (forward rollback) "
            "or --revert-to-version N (backward revert)."
        )

    mp4_path = Path(args.file).expanduser().resolve()
    if not mp4_path.exists():
        sys.exit(f"ERROR: File not found: {mp4_path}")
    if mp4_path.suffix.lower() != ".mp4":
        sys.exit(f"ERROR: File must be .mp4, got: {mp4_path.suffix}")

    size_bytes = mp4_path.stat().st_size

    # LD-283 size guard
    if size_bytes > SIZE_CEILING_BYTES:
        sys.exit(
            f"ERROR: Replacement file exceeds LD-283 80 MB ceiling "
            f"({size_bytes / 1024 / 1024:.1f} MB). Re-encode before rolling back."
        )
    if size_bytes > SIZE_TARGET_BYTES:
        print(f"WARNING: {size_bytes / 1024 / 1024:.1f} MB > 60 MB target — under 80 MB ceiling.")
    else:
        print(f"  Size: {size_bytes / 1024 / 1024:.1f} MB ✓")

    print("Computing SHA-256 of replacement file ...")
    new_hash = sha256_file(mp4_path)
    print(f"  Hash: {new_hash[:16]}...")

    # Guard: same-file no-op — block rollback to identical content
    if new_hash == current_hash:
        sys.exit(
            f"ERROR: Replacement file has the same SHA-256 as the current live version ({current_hash[:16]}...).\n"
            f"This is a no-op — the file has not changed. Check that you passed the correct replacement file."
        )

    new_version = current_version + 1
    storage_key = f"modules/{arc_id}/{module_id}/module_v{new_version}.mp4"
    gcs_path = f"gs://{STORAGE_BUCKET}/{storage_key}"

    print(f"\nUploading replacement as v{new_version} to {gcs_path} ...")
    gsutil_upload(mp4_path, gcs_path)

    # Verify upload
    print("  Verifying upload via gsutil stat ...")
    meta = gsutil_stat(gcs_path)
    size_str = (meta.get("Content-Length") or meta.get("Content length", "0")).replace(",", "")
    try:
        remote_size = int(size_str)
    except ValueError:
        remote_size = 0
    if remote_size and remote_size != size_bytes:
        sys.exit(
            f"ERROR: Size mismatch after upload (local={size_bytes}, remote={remote_size}).\n"
            f"Aborting Firestore patch — old version {current_version} remains live."
        )
    print(f"  Upload verified ✓ ({remote_size or size_bytes} bytes)")

    # Phase boundaries: keep existing unless new ones provided (PHASE_BOUNDARIES_NAMED_OBJECT_V1)
    phase_boundaries_patch: dict = {}
    if getattr(args, "phase_boundaries", "") and args.phase_boundaries:
        try:
            pairs = [p.split("=", 1) for p in args.phase_boundaries.split(",")]
            starts = [(name.strip(), float(s.strip())) for name, s in pairs]
            total_dur = getattr(args, "duration", 0.0) or 0.0
            phase_boundaries_patch = {
                "phaseBoundaries": [
                    {
                        "name": name,
                        "start_s": start_s,
                        "end_s": starts[i + 1][1] if i + 1 < len(starts) else total_dur or start_s,
                    }
                    for i, (name, start_s) in enumerate(starts)
                ]
            }
        except (ValueError, IndexError):
            sys.exit(
                "ERROR: --phase-boundaries must be name=start_s pairs, "
                "e.g. intro=0,phase_a=15.2,phase_b=42.7,resolution=310.1"
            )

    # Atomic Firestore PATCH — update all LD-404 manifest fields + audit trail
    patch_fields = {
        "cdnUrl": gcs_path,
        "contentHash": new_hash,
        "sizeBytes": size_bytes,
        "content_version": new_version,
        "published": True,
        "rollback_from_version": current_version,
        "rollback_reason": reason,
        "rollback_at": datetime.now(timezone.utc).isoformat(),
        **phase_boundaries_patch,
    }

    print(f"Patching Firestore manifest: v{current_version} → v{new_version} ...")
    firestore_patch("modules", module_id, patch_fields, token)
    print(f"  Firestore manifest updated ✓ (still published=true)")

    # Directus prod_assets — register replacement as new version
    # schema: module_id (int FK, required), asset_type, asset_name, file_path, status, notes
    rb_int_id = _directus_module_int_id(module_id)
    if rb_int_id is None:
        sys.exit(
            f"ERROR: Module '{module_id}' not found in Directus prod_modules. "
            f"Cannot register rollback — add the module row first."
        )
    asset_payload = {
        "asset_type": "module_mp4",
        "asset_name": f"{module_id}_v{new_version}.mp4",
        "file_path": storage_key,
        "status": "pending",
        "notes": json.dumps({
            "arc_id": arc_id, "version": new_version,
            "size_bytes": size_bytes, "content_hash": new_hash,
            "rollback_from_version": current_version, "reason": reason,
            "stream": "F",
        }),
    }
    if rb_int_id is not None:
        asset_payload["module_id"] = rb_int_id
    try:
        client = DirectusAdminClient()
        asset_row = client.post_item("prod_assets", asset_payload)
        print(f"  Directus prod_assets id={asset_row.get('id')} ✓")
    except Exception as e:
        print(f"  WARNING: Directus prod_assets write failed — {e}")
        _queue_offline({"_type": "directus_post", "collection": "prod_assets", "payload": asset_payload})

    _write_rollback_activity(
        module_id=module_id,
        arc_id=arc_id,
        from_version=current_version,
        to_version=new_version,
        reason=reason,
        path="A",
        new_gcs=gcs_path,
        new_hash=new_hash,
        new_size=size_bytes,
    )

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROLLBACK COMPLETE (Path A — forward re-upload)
  Module:  {module_id}
  Replaced: v{current_version} → v{new_version}
  Reason:  {reason}
  Size:    {size_bytes / 1024 / 1024:.1f} MB
  Hash:    {new_hash[:32]}...
  GCS:     {gcs_path}
  Status:  published=true (live immediately)

App clients will detect contentHash change on next cache
verification and re-download automatically (LD-404 + Stream C item 16).
Old version v{current_version} remains on GCS as fallback
(use: rollback --module {module_id} --revert-to-version {current_version} --reason "..." to undo).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


def _write_rollback_activity(
    module_id: str,
    arc_id: str,
    from_version: int,
    to_version: int,
    reason: str,
    path: str,
    new_gcs: str,
    new_hash: str,
    new_size: int,
) -> None:
    """Write Directus activity log entry for a rollback. Queues offline on failure."""
    module_int_id = _directus_module_int_id(module_id)
    payload: dict = {
        "action": f"module_rollback_{module_id}_v{from_version}_to_v{to_version}",
        "details": json.dumps({
            "module_id_str": module_id, "arc_id": arc_id,
            "path": path, "from_version": from_version, "to_version": to_version,
            "reason": reason, "new_gcs": new_gcs,
            "new_hash": new_hash[:16] + "...", "new_size": new_size,
            "stream": "F", "task_id": "stream-f-rollback-cmd-20260425",
        }),
    }
    if module_int_id is not None:
        payload["module_id"] = module_int_id
    try:
        client = DirectusAdminClient()
        row = client.post_item("prod_activity_log", payload)
        print(f"  Activity log written (id={row.get('id')}) ✓")
    except Exception as e:
        print(f"  WARNING: Activity log write failed — {e}")
        _queue_offline({"_type": "directus_post", "collection": "prod_activity_log", "payload": payload})


# ─── Offline queue ────────────────────────────────────────────────────────────

_QUEUE_FILE = Path(__file__).parent.parent.parent / "pending_directus_writes.json"


def _queue_offline(entry: dict) -> None:
    entries = []
    if _QUEUE_FILE.exists():
        try:
            entries = json.loads(_QUEUE_FILE.read_text())
        except Exception:
            pass
    entries.append(entry)
    _QUEUE_FILE.write_text(json.dumps(entries, indent=2))
    print(f"  Queued to {_QUEUE_FILE.name} for next-session drain.")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Stream F — Module MP4 upload pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    # upload
    p_up = sub.add_parser("upload", help="Upload a finalized module MP4")
    p_up.add_argument("--module", required=True, help="Module ID, e.g. m1")
    p_up.add_argument("--arc", required=True, help="Arc ID, e.g. arc1")
    p_up.add_argument("--file", required=True, help="Path to finalized module.mp4")
    p_up.add_argument("--phase-boundaries", default="",
        help="Named phase boundaries: name=start_s pairs, e.g. intro=0,phase_a=15.2,phase_b=42.7,resolution=310.1")
    p_up.add_argument("--duration", type=float, default=0.0,
        help="Total module duration in seconds (used to compute end_s of last phase boundary)")
    p_up.add_argument("--dry-run", action="store_true", help="Validate + plan without writing anything")

    # publish
    p_pub = sub.add_parser("publish", help="Set module published=true (make visible to app)")
    p_pub.add_argument("--module", required=True, help="Module ID, e.g. m1")

    # status
    p_st = sub.add_parser("status", help="Show current upload state for a module")
    p_st.add_argument("--module", required=True, help="Module ID, e.g. m1")

    # arc-manifest
    p_arc = sub.add_parser("arc-manifest", help="Write per-arc Firestore manifest (LD-282)")
    p_arc.add_argument("--arc", required=True, help="Arc ID, e.g. arc1")
    p_arc.add_argument("--force-unpublished", action="store_true",
                       help="Include staged-but-unpublished modules in the arc manifest")

    # rollback
    p_rb = sub.add_parser(
        "rollback",
        help="Roll back a published module — re-upload fixed file (Path A) or revert to earlier version (Path B)",
    )
    p_rb.add_argument("--module", required=True, help="Module ID, e.g. m1")
    p_rb.add_argument("--reason", required=True, help="Reason for rollback (required for audit trail)")
    p_rb.add_argument("--file", default=None,
                      help="Path to replacement MP4 (Path A — forward rollback)")
    p_rb.add_argument("--revert-to-version", type=int, default=None,
                      help="Earlier version number to revert to (Path B — backward revert, no new upload)")
    p_rb.add_argument("--phase-boundaries", default="",
                      help="Update phase boundaries (Path A only), comma-separated seconds")

    args = parser.parse_args()
    {
        "upload": cmd_upload,
        "publish": cmd_publish,
        "status": cmd_status,
        "arc-manifest": cmd_arc_manifest,
        "rollback": cmd_rollback,
    }[args.command](args)


if __name__ == "__main__":
    main()
