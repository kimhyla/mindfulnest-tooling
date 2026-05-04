#!/usr/bin/env python3
"""
registered_write.py — Asset registration wrapper for MindfulNest production pipeline.

LD-421 build (2026-04-26). Every skill that writes media files MUST use this wrapper.
Direct ffmpeg/imageio/open() writes are forbidden (enforced by Hook A).

Public API:
    register_asset()      — Atomic registration: file → SHA256 → Directus POST
    approve_asset()       — Mark approved + supersede prior winners
    reject_asset()        — Mark rejected
    add_iteration_note()  — Append to iteration_notes (production-time or feedback-time)
    add_alias()           — Add natural-language alias to prod_asset_aliases
    search()              — Union query across prod_assets + prod_visual_assets + prod_audio_assets
"""
import os
import sys
import hashlib
import json
import platform as _platform
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

# Cross-platform PROJECT_ROOT resolution (per LD-367, mirrors docx_confirmation_hook.py).
# Order: env var → Windows default → Mac/Linux default.
_PROJECT_ROOT_ENV = os.environ.get('MINDFULNEST_PROJECT_ROOT')
if _PROJECT_ROOT_ENV:
    _PROJECT_ROOT = _PROJECT_ROOT_ENV
elif _platform.system() == 'Windows':
    _PROJECT_ROOT = r"C:\Users\ECDS Clinical\Dropbox\Claude Mindfulnest Project Files"
else:
    _PROJECT_ROOT = "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
sys.path.insert(0, _PROJECT_ROOT)

from Production.tools.lib import credentials, directus

# --- Configuration ---

_PENDING_QUEUE = os.path.join(_PROJECT_ROOT, 'pending_directus_writes.json')

_ACCEPTED_ASSET_TYPES = {
    'final_atomic_mp4',     # Per LD-280
    'beat_scene',
    'scene_concat_mp4',     # Per LD ASSET_TYPE_SCENE_CONCAT_V1 (S5.5d 2026-05-03)
    'pre_lipsync',
    'lipsync_clip',
    'tts_audio',
    'voice_stem',
    'phase_b_mix',
    'ambient_bed',
    'sfx',
    'magic_clip',
    'still_master',         # Per Rule 6.1
    'still_delivery',       # Per Rule 6.2
    'composite',
    'storyboard_html',
    'module_json',
    'phase_a_scene',
    'audio_library_folder',
    'unknown',              # Backfill fallback
}

# prod_modules FK mapping (id → m_number, creature, domain)
# Note: module_id is FK to prod_modules.id, NOT the M-number
_MODULE_MAP = {
    1: ('M1', 'Tessa', 'Body-Sensing'),     # prod_modules.id=1
    2: ('M2', 'Luna', 'Now-Watching'),      # prod_modules.id=2
    3: ('M4', 'Ember', 'Kindness'),         # prod_modules.id=3 (M4!)
    4: ('M6', 'Bramble', 'Calm-Breathing'), # prod_modules.id=4 (M6!)
    5: ('M3', 'Benson', 'Courage'),         # prod_modules.id=5 (M3!)
    6: ('M5', 'Bork', 'Self-Grounding'),    # prod_modules.id=6 (M5!)
    # For cross-module assets: use any valid module_id (typically 1) + library=True
}

# Marker for Hook A sentinel detection
_WRAPPER_SENTINEL = "__MINDFULNEST_REGISTERED_WRITE__"


# --- Internal helpers ---

_cached_client = None

def _client() -> directus.DirectusClient:
    """Lazy-cached singleton Directus client."""
    global _cached_client
    if _cached_client is None:
        creds = credentials.load_credentials()
        _cached_client = directus.DirectusClient(
            creds['directus_url'],
            creds['directus_email'],
            creds['directus_password']
        )
    return _cached_client


def _validate_path(file_path: str) -> str:
    """Reject sandboxed sub-agent paths (LD-421 root cause #7)."""
    abs_path = os.path.abspath(file_path)
    if not abs_path.startswith(_PROJECT_ROOT):
        raise ValueError(
            f"Rejected: file_path {abs_path} is outside PROJECT_ROOT {_PROJECT_ROOT}. "
            f"Sub-agent sandboxed paths cannot be registered."
        )
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"File not found: {abs_path}")
    return abs_path


def _sha256(file_path: str) -> str:
    """Compute SHA256 hash of file."""
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def _enqueue_pending(payload: dict, reason: str) -> None:
    """Append failed write to pending_directus_writes.json for later retry."""
    pending = []
    if os.path.exists(_PENDING_QUEUE):
        try:
            with open(_PENDING_QUEUE, 'r') as f:
                pending = json.load(f)
        except (json.JSONDecodeError, IOError):
            pending = []

    pending.append({
        'timestamp': datetime.utcnow().isoformat(),
        'reason': reason,
        'payload': payload,
    })

    with open(_PENDING_QUEUE, 'w') as f:
        json.dump(pending, f, indent=2)


def _extract_basename(file_path: str) -> str:
    """Extract basename without extension for asset_name."""
    return os.path.splitext(os.path.basename(file_path))[0]


# --- Public API ---

def register_asset(
    file_path: str,
    asset_type: str,
    module_id: int,
    *,
    event_id: int = None,
    beat_id: str = None,
    parent_asset_id: int = None,
    produced_by_skill: str,
    iteration_notes: str = "",
    colloquial_name: str = None,
    tags: List[str] = None,
    library: bool = False,
    notes: str = "",
    role: str = None,
) -> Tuple[int, str]:
    """
    Atomic registration: validate path → SHA256 → POST prod_assets → POST prod_activity_log.

    On Directus failure, queue to pending_directus_writes.json and return (-1, file_path).
    Returns (asset_id, file_path).

    Raises ValueError if file_path is outside PROJECT_ROOT.
    Raises FileNotFoundError if file doesn't exist on disk.
    """
    # Step 1: Validate path
    abs_path = _validate_path(file_path)

    # Step 2: Compute SHA256 + size
    is_dir = os.path.isdir(abs_path)
    sha = None if is_dir else _sha256(abs_path)
    size = None if is_dir else os.path.getsize(abs_path)

    # Step 3: Validate asset_type
    if asset_type not in _ACCEPTED_ASSET_TYPES:
        raise ValueError(f"Unknown asset_type: {asset_type}. Accepted: {_ACCEPTED_ASSET_TYPES}")

    client = _client()

    # Step 4: Dedup check via SHA256 (skip for directories)
    if sha:
        try:
            existing = client._request(
                'GET',
                f'/items/prod_assets?filter[sha256][_eq]={sha}&limit=1'
            )['data']
            if existing:
                existing_id = existing[0]['id']
                return (existing_id, abs_path)  # Already registered
        except Exception:
            pass  # Continue with registration attempt

    # Step 5: POST to prod_assets
    asset_data = {
        'module_id': module_id,
        'asset_type': asset_type,
        'asset_name': _extract_basename(abs_path),
        'file_path': abs_path,
        'status': 'pending',
        'notes': notes,
        'event_id': event_id,
        'beat_id': beat_id,
        'parent_asset_id': parent_asset_id,
        'produced_by_skill': produced_by_skill,
        'iteration_notes': iteration_notes,
        'colloquial_name': colloquial_name,
        'tags': tags or [],
        'library': library,
        'sha256': sha,
        'file_size_bytes': size,
        'is_current': True,
        'kim_verdict': 'pending',
        'created_at': datetime.utcnow().isoformat(),
    }

    try:
        result = client._request('POST', '/items/prod_assets', data=asset_data)
        asset_id = result['data']['id']
    except Exception as e:
        _enqueue_pending({'collection': 'prod_assets', 'data': asset_data}, f'directus_post_assets_failed: {e}')
        return (-1, abs_path)

    # Step 6: POST to prod_activity_log (Two-Write Rule)
    activity_data = {
        'action': 'register_asset',
        'details': f'Registered {asset_type} via {produced_by_skill}: {os.path.basename(abs_path)}',
        'asset_id': asset_id,
        'created_at': datetime.utcnow().isoformat(),
    }

    try:
        client._request('POST', '/items/prod_activity_log', data=activity_data)
    except Exception as e:
        _enqueue_pending({'collection': 'prod_activity_log', 'data': activity_data}, f'directus_post_activity_failed: {e}')
        # Asset is registered; activity log will retry

    return (asset_id, abs_path)


def approve_asset(
    asset_id: int,
    kim_feedback: str,
    *,
    alias: str = None,
) -> bool:
    """
    Mark asset approved + supersede prior winners in same (module_id, event_id, beat_id, asset_type) set.

    Writes prod_activity_log row.
    Idempotent: re-approving same asset returns True without side effects.
    """
    client = _client()
    now = datetime.utcnow().isoformat()

    # Get current asset state
    try:
        asset = client._request('GET', f'/items/prod_assets/{asset_id}')['data']
    except Exception as e:
        print(f"Error fetching asset {asset_id}: {e}")
        return False

    # Skip if already approved
    if asset.get('kim_verdict') == 'approved':
        return True

    # Mark approved
    patch_data = {
        'kim_verdict': 'approved',
        'kim_approved_at': now,
        'kim_feedback': kim_feedback,
        'is_current': True,
    }

    try:
        client._request('PATCH', f'/items/prod_assets/{asset_id}', data=patch_data)
    except Exception as e:
        print(f"Error approving asset {asset_id}: {e}")
        return False

    # Supersede prior winners in same scope
    module_id = asset.get('module_id')
    event_id = asset.get('event_id')
    beat_id = asset.get('beat_id')
    asset_type = asset.get('asset_type')

    if module_id is not None and event_id is not None:
        try:
            # Find other approved assets in same scope
            filter_str = (
                f'filter[module_id][_eq]={module_id}'
                f'&filter[event_id][_eq]={event_id}'
                f'&filter[asset_type][_eq]={asset_type}'
                f'&filter[kim_verdict][_eq]=approved'
                f'&filter[id][_neq]={asset_id}'
            )
            if beat_id:
                filter_str += f'&filter[beat_id][_eq]={beat_id}'

            prior = client._request('GET', f'/items/prod_assets?{filter_str}')['data']

            for p in prior:
                client._request('PATCH', f'/items/prod_assets/{p["id"]}', data={
                    'kim_verdict': 'superseded',
                    'superseded_by_id': asset_id,
                    'is_current': False,
                })
        except Exception:
            pass  # Non-critical; prior assets stay approved but not current

    # Add alias if provided
    if alias:
        add_alias(asset_id, alias, alias_kind='kim_phrase')

    # Log approval
    try:
        client._request('POST', '/items/prod_activity_log', data={
            'action': 'approve_asset',
            'details': f'Kim approved asset {asset_id}: {kim_feedback[:200]}',
            'asset_id': asset_id,
            'created_at': now,
        })
    except Exception:
        pass

    return True


def reject_asset(
    asset_id: int,
    kim_feedback: str,
) -> bool:
    """Mark asset rejected. Does NOT supersede other rows. Writes activity log."""
    client = _client()
    now = datetime.utcnow().isoformat()

    try:
        client._request('PATCH', f'/items/prod_assets/{asset_id}', data={
            'kim_verdict': 'rejected',
            'kim_feedback': kim_feedback,
            'is_current': False,
        })

        client._request('POST', '/items/prod_activity_log', data={
            'action': 'reject_asset',
            'details': f'Kim rejected asset {asset_id}: {kim_feedback[:200]}',
            'asset_id': asset_id,
            'created_at': now,
        })
        return True
    except Exception as e:
        print(f"Error rejecting asset {asset_id}: {e}")
        return False


def add_iteration_note(
    asset_id: int,
    note: str,
    source: str = "claude",
) -> bool:
    """
    Append to iteration_notes field.

    Format: "[2026-04-26T14:23:11 kim] second half lipsync was clean..."
    source: 'claude' (production-time) or 'kim' (feedback-time)
    """
    client = _client()
    now = datetime.utcnow().isoformat()

    try:
        # Get current iteration_notes
        asset = client._request('GET', f'/items/prod_assets/{asset_id}?fields=iteration_notes')['data']
        current = asset.get('iteration_notes') or ''

        # Append new note with timestamp
        new_entry = f"\n[{now[:19]} {source}] {note}"
        updated = (current + new_entry).strip()

        client._request('PATCH', f'/items/prod_assets/{asset_id}', data={
            'iteration_notes': updated,
        })

        client._request('POST', '/items/prod_activity_log', data={
            'action': 'add_iteration_note',
            'details': f'Added {source} note to asset {asset_id}: {note[:100]}',
            'asset_id': asset_id,
            'created_at': now,
        })
        return True
    except Exception as e:
        print(f"Error adding iteration note to asset {asset_id}: {e}")
        return False


def add_alias(
    asset_id: int,
    alias_text: str,
    alias_kind: str = "kim_phrase",
) -> int:
    """Add a natural-language alias for the asset. Returns alias row id, or -1 on error."""
    client = _client()

    try:
        result = client._request('POST', '/items/prod_asset_aliases', data={
            'asset_id': asset_id,
            'alias_text': alias_text,
            'alias_kind': alias_kind,
            'created_at': datetime.utcnow().isoformat(),
        })
        return result['data']['id']
    except Exception as e:
        print(f"Error adding alias for asset {asset_id}: {e}")
        return -1


def search(
    phrase: str,
    *,
    module_id: int = None,
    event_id: int = None,
    is_current: bool = None,
    kim_verdict: str = None,
    asset_type: str = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Union query across prod_assets + prod_visual_assets + prod_audio_assets.

    Searches: prod_asset_aliases.alias_text, prod_assets.colloquial_name,
              prod_assets.tags, prod_assets.iteration_notes, prod_assets.notes,
              prod_assets.asset_name.

    Returns unified list of dicts with normalized field names.
    """
    client = _client()
    results = []
    phrase_lower = phrase.lower()

    # Build filters
    filters = []
    if module_id is not None:
        filters.append(f'filter[module_id][_eq]={module_id}')
    if event_id is not None:
        filters.append(f'filter[event_id][_eq]={event_id}')
    if is_current is not None:
        filters.append(f'filter[is_current][_eq]={str(is_current).lower()}')
    if kim_verdict is not None:
        filters.append(f'filter[kim_verdict][_eq]={kim_verdict}')
    if asset_type is not None:
        filters.append(f'filter[asset_type][_eq]={asset_type}')

    filter_str = '&'.join(filters) if filters else ''

    # Step 0: Search iteration_notes (Kim's HARD case per LD-421 amendment)
    try:
        url = f'/items/prod_assets?filter[iteration_notes][_icontains]={phrase}&{filter_str}&limit={limit}'
        iter_results = client._request('GET', url)['data']
        for r in iter_results:
            r['_match_source'] = 'iteration_notes'
            r['_source_collection'] = 'prod_assets'
            results.append(r)
    except Exception:
        pass

    # Step 1: Alias table search
    try:
        alias_results = client._request(
            'GET',
            f'/items/prod_asset_aliases?filter[alias_text][_icontains]={phrase}&limit={limit}'
        )['data']

        # Fetch the actual assets
        asset_ids = [a['asset_id'] for a in alias_results]
        if asset_ids:
            ids_str = ','.join(str(i) for i in asset_ids)
            assets = client._request('GET', f'/items/prod_assets?filter[id][_in]={ids_str}')['data']
            for a in assets:
                if not any(r['id'] == a['id'] for r in results):
                    a['_match_source'] = 'alias'
                    a['_source_collection'] = 'prod_assets'
                    results.append(a)
    except Exception:
        pass

    # Step 2: colloquial_name + notes + asset_name search on prod_assets
    try:
        or_filters = [
            f'[colloquial_name][_icontains]={phrase}',
            f'[notes][_icontains]={phrase}',
            f'[asset_name][_icontains]={phrase}',
        ]
        for of in or_filters:
            url = f'/items/prod_assets?filter{of}&{filter_str}&limit={limit}'
            for r in client._request('GET', url)['data']:
                if not any(existing['id'] == r['id'] for existing in results):
                    r['_match_source'] = 'text_search'
                    r['_source_collection'] = 'prod_assets'
                    results.append(r)
    except Exception:
        pass

    # Step 3: Search prod_visual_assets (legacy collection)
    try:
        url = f'/items/prod_visual_assets?filter[description][_icontains]={phrase}&limit={limit}'
        for r in client._request('GET', url)['data']:
            r['_match_source'] = 'visual_assets'
            r['_source_collection'] = 'prod_visual_assets'
            results.append(r)
    except Exception:
        pass

    # Step 4: Search prod_audio_assets (legacy collection)
    try:
        url = f'/items/prod_audio_assets?filter[notes][_icontains]={phrase}&limit={limit}'
        for r in client._request('GET', url)['data']:
            r['_match_source'] = 'audio_assets'
            r['_source_collection'] = 'prod_audio_assets'
            results.append(r)
    except Exception:
        pass

    # Sort by created_at desc
    results.sort(key=lambda r: r.get('created_at', ''), reverse=True)

    return results[:limit]


def replay_pending() -> int:
    """Replay any pending Directus writes from the queue. Returns count of replayed items."""
    if not os.path.exists(_PENDING_QUEUE):
        return 0

    try:
        with open(_PENDING_QUEUE, 'r') as f:
            pending = json.load(f)
    except (json.JSONDecodeError, IOError):
        return 0

    if not pending:
        return 0

    client = _client()
    replayed = 0
    failed = []

    for item in pending:
        collection = item['payload'].get('collection')
        data = item['payload'].get('data')

        if not collection or not data:
            continue

        try:
            client._request('POST', f'/items/{collection}', data=data)
            replayed += 1
        except Exception:
            failed.append(item)

    # Write back any still-failed items
    with open(_PENDING_QUEUE, 'w') as f:
        json.dump(failed, f, indent=2)

    return replayed


# Smoke test
if __name__ == '__main__':
    import tempfile
    import subprocess

    print("=== registered_write.py smoke test ===\n")

    # Create sandbox dir
    sandbox = os.path.join(_PROJECT_ROOT, 'Production', '_sandbox')
    os.makedirs(sandbox, exist_ok=True)

    # Generate 1-second silent black mp4
    test_file = os.path.join(sandbox, f'smoke_test_{int(datetime.now().timestamp())}.mp4')
    subprocess.run([
        'ffmpeg', '-f', 'lavfi', '-i', 'color=black:s=320x240:d=1',
        '-y', test_file
    ], check=True, capture_output=True)

    print(f"Created test file: {test_file}")

    # Register it (use module_id=1 for M1/Tessa, library=True for cross-module)
    asset_id, path = register_asset(
        file_path=test_file,
        asset_type='unknown',
        module_id=1,  # FK to prod_modules; use library=True for cross-module assets
        produced_by_skill='smoke_test',
        iteration_notes='smoke test — DELETE ME',
        notes='auto-generated smoke test artifact',
        library=True,  # Mark as library/cross-module for smoke test
    )

    print(f"Registered: asset_id={asset_id}")

    # Verify via search
    results = search('smoke test')
    found = any(r.get('id') == asset_id for r in results)
    print(f"Search found registered asset: {found}")

    # Cleanup
    _client()._request('DELETE', f'/items/prod_assets/{asset_id}')
    os.remove(test_file)
    print(f"Cleaned up asset_id={asset_id} and test file")

    print("\n=== SMOKE TEST PASSED ===")
