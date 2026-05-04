#!/usr/bin/env python3
"""
find_asset.py — Asset discovery tool for MindfulNest production pipeline.

LD-421 build (2026-04-26). Implements the 5-step deterministic "find me X" protocol.
Outputs HTML preview in Safari per feedback_file_links.md (locked 2026-04-26).

5-Step Protocol:
    Step 0: Full-text iteration_notes search (Kim's HARD case)
    Step 1: Alias table exact + fuzzy match
    Step 2: colloquial_name + tags search
    Step 3: notes + asset_name search (broader, lower precision)
    Step 4: Disk fallback (ONLY if all Directus paths return zero)
    Step 5: Present HTML preview + ask

Exit codes:
    0 = exactly one match
    1 = multiple candidates
    2 = zero matches
    3 = Directus error
"""
import os
import sys
import json
import argparse
import subprocess
import platform as _platform
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Cross-platform PROJECT_ROOT resolution (per LD-367, mirrors docx_confirmation_hook.py).
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

_PREVIEWS_DIR = os.path.join(_PROJECT_ROOT, 'Production', '_previews')
_ASSET_FOCUS_FILE = Path.home() / '.claude/mindfulnest-cache/asset_focus.json'

# Canonical disk locations for fallback search
_CANONICAL_LOCATIONS = [
    'Production/Event_1/exports/',
    'Production/Event_1/preserved_winners/',
    'Production/Event_1/',
    'Production/Event_2/',
    'Production/Character_Assets/',
]


# --- Internal helpers ---

def _client() -> directus.DirectusClient:
    """Get Directus client."""
    creds = credentials.load_credentials()
    return directus.DirectusClient(
        creds['directus_url'],
        creds['directus_email'],
        creds['directus_password']
    )


def _search_iteration_notes(client, phrase: str, filters: dict) -> List[Dict]:
    """Step 0: Full-text search on iteration_notes (Kim's HARD case)."""
    results = []
    try:
        filter_parts = [f'filter[iteration_notes][_icontains]={phrase}']
        if filters.get('module_id'):
            filter_parts.append(f'filter[module_id][_eq]={filters["module_id"]}')
        if filters.get('event_id'):
            filter_parts.append(f'filter[event_id][_eq]={filters["event_id"]}')

        url = f'/items/prod_assets?{"&".join(filter_parts)}&limit=50'
        for r in client._request('GET', url)['data']:
            r['_match_source'] = 'iteration_notes'
            r['_score'] = 1.0
            results.append(r)
    except Exception:
        pass
    return results


def _search_aliases(client, phrase: str) -> List[Dict]:
    """Step 1: Alias table search."""
    results = []
    try:
        alias_results = client._request(
            'GET',
            f'/items/prod_asset_aliases?filter[alias_text][_icontains]={phrase}&limit=50'
        )['data']

        if alias_results:
            asset_ids = [a['asset_id'] for a in alias_results]
            ids_str = ','.join(str(i) for i in asset_ids)
            assets = client._request('GET', f'/items/prod_assets?filter[id][_in]={ids_str}')['data']
            for a in assets:
                a['_match_source'] = 'alias'
                a['_score'] = 0.95
                results.append(a)
    except Exception:
        pass
    return results


def _search_colloquial_tags(client, phrase: str, filters: dict) -> List[Dict]:
    """Step 2: colloquial_name + tags search."""
    results = []
    try:
        filter_parts = []
        if filters.get('module_id'):
            filter_parts.append(f'filter[module_id][_eq]={filters["module_id"]}')
        if filters.get('event_id'):
            filter_parts.append(f'filter[event_id][_eq]={filters["event_id"]}')
        base_filter = '&'.join(filter_parts) if filter_parts else ''

        # colloquial_name
        url = f'/items/prod_assets?filter[colloquial_name][_icontains]={phrase}&{base_filter}&limit=50'
        for r in client._request('GET', url)['data']:
            r['_match_source'] = 'colloquial_name'
            r['_score'] = 0.85
            results.append(r)

    except Exception:
        pass
    return results


def _search_notes_name(client, phrase: str, filters: dict) -> List[Dict]:
    """Step 3: notes + asset_name search (broader)."""
    results = []
    try:
        filter_parts = []
        if filters.get('module_id'):
            filter_parts.append(f'filter[module_id][_eq]={filters["module_id"]}')
        if filters.get('event_id'):
            filter_parts.append(f'filter[event_id][_eq]={filters["event_id"]}')
        base_filter = '&'.join(filter_parts) if filter_parts else ''

        # notes
        url = f'/items/prod_assets?filter[notes][_icontains]={phrase}&{base_filter}&limit=50'
        for r in client._request('GET', url)['data']:
            r['_match_source'] = 'notes'
            r['_score'] = 0.7
            results.append(r)

        # asset_name
        url = f'/items/prod_assets?filter[asset_name][_icontains]={phrase}&{base_filter}&limit=50'
        for r in client._request('GET', url)['data']:
            r['_match_source'] = 'asset_name'
            r['_score'] = 0.6
            results.append(r)

    except Exception:
        pass
    return results


def _search_disk_fallback(phrase: str) -> List[Dict]:
    """Step 4: Disk filename grep (ONLY if Directus returned zero)."""
    results = []
    phrase_lower = phrase.lower().replace(' ', '_').replace('-', '_')

    for loc in _CANONICAL_LOCATIONS:
        loc_path = os.path.join(_PROJECT_ROOT, loc)
        if not os.path.exists(loc_path):
            continue

        for root, dirs, files in os.walk(loc_path):
            for f in files:
                if f.lower().endswith(('.mp4', '.mp3', '.wav', '.png', '.jpg', '.webp')):
                    fname_lower = f.lower()
                    # Simple substring match
                    if phrase_lower in fname_lower or any(w in fname_lower for w in phrase_lower.split('_')):
                        full_path = os.path.join(root, f)
                        results.append({
                            'id': None,
                            'asset_name': os.path.splitext(f)[0],
                            'file_path': full_path,
                            'asset_type': 'unknown',
                            'kim_verdict': 'unregistered',
                            'iteration_notes': None,
                            'notes': f'DISK FALLBACK: Not in Directus. Found in {loc}',
                            '_match_source': 'disk_fallback',
                            '_score': 0.3,
                            '_source_collection': 'disk',
                        })

    return results


def _dedupe_results(results: List[Dict]) -> List[Dict]:
    """Remove duplicates by id, keeping highest score."""
    seen = {}
    for r in results:
        rid = r.get('id')
        if rid is None:
            # Disk fallback results - dedupe by path
            rid = r.get('file_path')
        if rid not in seen or r.get('_score', 0) > seen[rid].get('_score', 0):
            seen[rid] = r
    return list(seen.values())


def _generate_html(phrase: str, results: List[Dict], timestamp: str) -> str:
    """Generate HTML preview page."""
    verdict_colors = {
        'approved': '#2e7d32',
        'pending': '#f0c000',
        'rejected': '#c62828',
        'superseded': '#9e9e9e',
        'unregistered': '#ff5722',
    }

    items_html = ""
    for i, r in enumerate(results, 1):
        verdict = r.get('kim_verdict', 'pending')
        color = verdict_colors.get(verdict, '#666')
        file_path = r.get('file_path', '')
        is_video = file_path.lower().endswith(('.mp4', '.mov'))
        is_audio = file_path.lower().endswith(('.mp3', '.wav'))
        is_image = file_path.lower().endswith(('.png', '.jpg', '.webp'))

        # Media preview
        media_html = ""
        if is_video and os.path.exists(file_path):
            rel_path = os.path.relpath(file_path, _PREVIEWS_DIR)
            media_html = f'<video controls preload="metadata" style="max-width:100%;max-height:300px;"><source src="{rel_path}" type="video/mp4"></video>'
        elif is_audio and os.path.exists(file_path):
            rel_path = os.path.relpath(file_path, _PREVIEWS_DIR)
            media_html = f'<audio controls preload="metadata"><source src="{rel_path}" type="audio/mpeg"></audio>'
        elif is_image and os.path.exists(file_path):
            rel_path = os.path.relpath(file_path, _PREVIEWS_DIR)
            media_html = f'<img src="{rel_path}" style="max-width:100%;max-height:300px;">'

        score = r.get('_score', 0)
        match_src = r.get('_match_source', 'unknown')

        items_html += f'''
        <div class="item" style="border-left: 4px solid {color};">
            <h2><span class="score-badge">score: {score:.2f} [{match_src}]</span>{i}. {r.get('asset_name', 'Unknown')}</h2>
            {media_html}
            <div class="meta">
                <strong>Verdict:</strong> {verdict} ({r.get('kim_approved_at', 'N/A')})<br>
                <strong>ID:</strong> {r.get('id', 'N/A')} | <strong>Type:</strong> {r.get('asset_type', 'N/A')}<br>
                <strong>Module/Event/Beat:</strong> M{r.get('module_id', '?')} / E{r.get('event_id', '?')} / {r.get('beat_id', 'N/A')}<br>
                <strong>Produced by:</strong> {r.get('produced_by_skill', 'N/A')}<br>
                <strong>Iteration notes:</strong> {(r.get('iteration_notes') or 'N/A')[:300]}<br>
                <strong>SHA256:</strong> {(r.get('sha256') or 'N/A')[:16]}...
            </div>
            <div class="path">{file_path}</div>
        </div>
        '''

    if not items_html:
        items_html = '''
        <div class="empty-state">
            <h2>No matches found for this search.</h2>
            <p>Suggestions:</p>
            <ul>
                <li>Try different keywords from Kim's feedback or file names</li>
                <li>Check if the asset is registered in Directus</li>
                <li>Browse the canonical locations manually</li>
            </ul>
        </div>
        '''

    return f'''<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Find: "{phrase}" — {timestamp}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 20px; background: #f5f5f5; }}
h1 {{ color: #333; }}
.subtitle {{ color: #666; margin-bottom: 20px; }}
.item {{ background: white; padding: 15px; margin: 15px 0; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.item h2 {{ margin-top: 0; color: #333; font-size: 1.1em; }}
.score-badge {{ float: right; font-size: 0.85em; color: #666; font-weight: normal; }}
.meta {{ color: #555; font-size: 0.9em; line-height: 1.6; margin: 10px 0; }}
.path {{ font-family: monospace; font-size: 0.8em; color: #888; word-break: break-all; padding: 8px; background: #f9f9f9; border-radius: 4px; margin-top: 10px; }}
video, audio, img {{ margin: 10px 0; border-radius: 4px; }}
.empty-state {{ text-align: center; padding: 40px; background: white; border-radius: 8px; }}
.empty-state h2 {{ color: #666; }}
</style>
</head><body>
<h1>Find results: "{phrase}"</h1>
<div class="subtitle">{len(results)} candidate(s) — sorted by score then date desc — {timestamp}</div>
{items_html}
</body></html>
'''


def _clear_asset_focus():
    """Clear the asset_focus.json after successful find."""
    try:
        if _ASSET_FOCUS_FILE.exists():
            _ASSET_FOCUS_FILE.write_text('{}')
    except Exception:
        pass


# --- Main ---

def find(
    phrase: str,
    *,
    module_id: int = None,
    event_id: int = None,
    no_preview: bool = False,
    json_output: bool = False,
) -> int:
    """
    Execute 5-step find protocol.

    Returns exit code: 0=one match, 1=multiple, 2=zero, 3=error
    """
    filters = {}
    if module_id:
        filters['module_id'] = module_id
    if event_id:
        filters['event_id'] = event_id

    try:
        client = _client()
    except Exception as e:
        print(f"Error: Could not connect to Directus: {e}", file=sys.stderr)
        return 3

    all_results = []

    # Step 0: iteration_notes
    all_results.extend(_search_iteration_notes(client, phrase, filters))

    # Step 1: aliases
    all_results.extend(_search_aliases(client, phrase))

    # Step 2: colloquial_name + tags
    all_results.extend(_search_colloquial_tags(client, phrase, filters))

    # Step 3: notes + asset_name
    all_results.extend(_search_notes_name(client, phrase, filters))

    # Dedupe
    results = _dedupe_results(all_results)

    # Step 4: Disk fallback (ONLY if zero Directus results)
    if not results:
        disk_results = _search_disk_fallback(phrase)
        results.extend(disk_results)

    # Sort by score desc, then created_at desc
    results.sort(key=lambda r: (r.get('_score', 0), r.get('created_at', '')), reverse=True)

    # Output
    if json_output:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(f"Found {len(results)} result(s) for '{phrase}'")
        for i, r in enumerate(results[:5], 1):
            print(f"  {i}. {r.get('asset_name', 'Unknown')} (id={r.get('id')}, verdict={r.get('kim_verdict')}, score={r.get('_score', 0):.2f})")
        if len(results) > 5:
            print(f"  ... and {len(results) - 5} more")

    # Generate HTML preview (unless --no-preview)
    if not no_preview:
        os.makedirs(_PREVIEWS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        slug = phrase.lower().replace(' ', '_')[:20]
        preview_path = os.path.join(_PREVIEWS_DIR, f'find_{slug}_{timestamp}.html')

        html = _generate_html(phrase, results, timestamp)
        with open(preview_path, 'w') as f:
            f.write(html)

        # Open in browser (platform-portable)
        _system = _platform.system()
        if _system == 'Darwin':
            subprocess.run(['open', preview_path], check=False)
            subprocess.run(['osascript', '-e', 'tell application "Safari" to activate'], check=False)
        elif _system == 'Windows':
            subprocess.run(['cmd', '/c', 'start', '', preview_path], check=False, shell=False)
        else:
            subprocess.run(['xdg-open', preview_path], check=False)
        print(f"\nHTML preview: {preview_path}")

    # Clear asset focus (Phase 0 amendment: exit 3 fallback would skip this)
    _clear_asset_focus()

    # Return exit code
    if len(results) == 0:
        return 2
    elif len(results) == 1:
        return 0
    else:
        return 1


def main():
    parser = argparse.ArgumentParser(description='Find assets by phrase')
    parser.add_argument('--phrase', '-p', required=True, help='Search phrase')
    parser.add_argument('--module', '-m', type=int, help='Filter by module_id')
    parser.add_argument('--event', '-e', type=int, help='Filter by event_id')
    parser.add_argument('--no-preview', action='store_true', help='Skip HTML preview')
    parser.add_argument('--json', action='store_true', help='Output JSON only')

    args = parser.parse_args()

    exit_code = find(
        phrase=args.phrase,
        module_id=args.module,
        event_id=args.event,
        no_preview=args.no_preview,
        json_output=args.json,
    )

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
