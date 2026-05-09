"""Configure Directus presets for prod_storyboard_beats.

Creates three presets (each stored as a bookmark in directus_presets):
- Kanban by Status (primary view, grouped by beat.status, refresh every 10s)
- Table (inline-editable dialogue_text / kim_verdict / kim_feedback)
- Detail view: Directus renders detail based on field interfaces already
  configured in 04_schema.py; image_override is a file field, video_options
  is list-o2m showing each candidate's clip_path, selected_option is an M2O
  dropdown. No preset needed for detail; it's schema-driven.
"""
from __future__ import annotations
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import local  # type: ignore
from credentials_lib.directus import DirectusError  # type: ignore

BEATS = "prod_storyboard_beats"


def _existing_presets(c, collection):
    r = c._request("GET", "/presets", params={
        "filter[collection][_eq]": collection,
        "limit": 100,
    })
    return r.get("data", [])


def _upsert_preset(c, payload):
    # Presets are keyed by bookmark + collection + user + role.
    existing = _existing_presets(c, payload["collection"])
    match = next(
        (p for p in existing
         if p.get("bookmark") == payload.get("bookmark")
         and p.get("user") == payload.get("user")
         and p.get("role") == payload.get("role")),
        None,
    )
    if match:
        r = c._request("PATCH", f"/presets/{match['id']}", data=payload)
        print(f"  updated preset '{payload['bookmark']}' ({payload['layout']}) id={match['id']}")
    else:
        r = c._request("POST", "/presets", data=payload)
        print(f"  created preset '{payload['bookmark']}' ({payload['layout']}) id={r.get('data',{}).get('id')}")


def build_kanban(c):
    _upsert_preset(c, {
        "collection": BEATS,
        "bookmark": "Kanban by Status",
        "user": None,
        "role": None,
        "layout": "kanban",
        "icon": "view_kanban",
        "color": "#6644FF",
        "refresh_interval": 10,  # Kanban auto-refresh test (Exit Criterion #3)
        "filter": None,
        "search": None,
        "layout_query": {
            "kanban": {
                "sort": ["beat_number"],
                "fields": [
                    "id", "beat_number", "speaker", "dialogue_text",
                    "status", "phase", "image_override", "kim_verdict",
                    "video_options.id", "video_options.option_label",
                    "video_options.clip_path",
                ],
                "limit": 200,
            }
        },
        "layout_options": {
            "kanban": {
                "groupField": "status",
                "titleField": "beat_number",
                "textField": "dialogue_text",
                "imageField": "image_override",
                "groupTitleField": "speaker",
            }
        },
    })


def build_tabular(c):
    _upsert_preset(c, {
        "collection": BEATS,
        "bookmark": "Table (inline edit)",
        "user": None,
        "role": None,
        "layout": "tabular",
        "icon": "table_rows",
        "color": "#8866FF",
        "refresh_interval": None,
        "layout_query": {
            "tabular": {
                "sort": ["beat_number"],
                "fields": [
                    "beat_number", "phase", "speaker",
                    "dialogue_text", "status",
                    "kim_verdict", "kim_feedback",
                    "updated_at",
                ],
                "limit": 200,
            }
        },
        "layout_options": {
            "tabular": {
                "widths": {
                    "beat_number": 80,
                    "phase": 80,
                    "speaker": 140,
                    "dialogue_text": 400,
                    "status": 140,
                    "kim_verdict": 130,
                    "kim_feedback": 300,
                    "updated_at": 160,
                }
            }
        },
    })


def main():
    c = local()
    build_kanban(c)
    build_tabular(c)
    presets = _existing_presets(c, BEATS)
    print(f"\n{BEATS} has {len(presets)} preset(s): {[p['bookmark'] for p in presets]}")


if __name__ == "__main__":
    main()
