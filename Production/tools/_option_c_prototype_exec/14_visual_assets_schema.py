"""Create prod_visual_assets collection in LOCAL Directus.

Schema mirrors the hosted production pattern (prod_visual_assets): id,
module_id, event_number, filename, filepath, asset_type, status,
shot_number, width, height, file (FK to directus_files), created_at.
"""
from __future__ import annotations
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import local  # type: ignore
from lib.directus import DirectusError  # type: ignore

VA = "prod_visual_assets"


def _exists(c, path):
    try:
        c._request("GET", path)
        return True
    except DirectusError as e:
        if e.status in (403, 404):
            return False
        raise


def _create_collection(c):
    if _exists(c, f"/collections/{VA}"):
        print(f"  collection {VA} exists")
        return
    c._request("POST", "/collections", data={
        "collection": VA,
        "meta": {
            "note": "Option C prototype: 4:3 image library mirror of hosted prod_visual_assets (Event_1 Tessa/Chipper crops).",
            "singleton": False,
            "accountability": "all",
            "icon": "image",
            "color": "#6644FF",
        },
        "schema": {"name": VA},
        "fields": [{
            "field": "id",
            "type": "uuid",
            "meta": {"hidden": True, "readonly": True, "interface": "input", "special": ["uuid"]},
            "schema": {"is_primary_key": True, "has_auto_increment": False, "is_nullable": False},
        }],
    })
    print(f"  created collection {VA}")


def _field(c, field, payload):
    if _exists(c, f"/fields/{VA}/{field}"):
        print(f"  field {VA}.{field} exists")
        return
    payload["field"] = field
    c._request("POST", f"/fields/{VA}", data=payload)
    print(f"  created field {VA}.{field}")


def build_fields(c):
    _field(c, "module_id", {
        "type": "integer", "meta": {"interface": "input", "width": "half"},
        "schema": {"is_nullable": False, "default_value": 1},
    })
    _field(c, "event_number", {
        "type": "integer", "meta": {"interface": "input", "width": "half"},
        "schema": {"is_nullable": False, "default_value": 1},
    })
    _field(c, "filename", {
        "type": "string", "meta": {"interface": "input"},
        "schema": {"is_nullable": False},
    })
    _field(c, "filepath", {
        "type": "text", "meta": {"interface": "input-multiline"},
        "schema": {"is_nullable": False},
    })
    _field(c, "asset_type", {
        "type": "string",
        "meta": {
            "interface": "select-dropdown",
            "options": {"choices": [
                {"text": "crop", "value": "crop"},
                {"text": "still", "value": "still"},
                {"text": "master", "value": "master"},
                {"text": "thumbnail", "value": "thumbnail"},
                {"text": "upscale", "value": "upscale"},
            ]},
        },
        "schema": {"is_nullable": False, "default_value": "crop"},
    })
    _field(c, "status", {
        "type": "string",
        "meta": {
            "interface": "select-dropdown",
            "options": {"choices": [
                {"text": "approved", "value": "approved"},
                {"text": "pending", "value": "pending"},
                {"text": "rejected", "value": "rejected"},
            ]},
        },
        "schema": {"is_nullable": False, "default_value": "approved"},
    })
    _field(c, "shot_number", {
        "type": "integer", "meta": {"interface": "input"},
        "schema": {"is_nullable": True},
    })
    _field(c, "width", {
        "type": "integer", "meta": {"interface": "input", "width": "half", "readonly": True},
        "schema": {"is_nullable": True},
    })
    _field(c, "height", {
        "type": "integer", "meta": {"interface": "input", "width": "half", "readonly": True},
        "schema": {"is_nullable": True},
    })
    _field(c, "rule6_compliant", {
        "type": "boolean",
        "meta": {"interface": "boolean", "note": "width AND height >= 600 (Rule 6)"},
        "schema": {"is_nullable": False, "default_value": False},
    })
    _field(c, "file", {
        "type": "uuid",
        "meta": {"interface": "file-image", "special": ["file"]},
        "schema": {"is_nullable": True, "foreign_key_table": "directus_files"},
    })
    _field(c, "source_note", {
        "type": "text",
        "meta": {"interface": "input-multiline",
                 "note": "Where this crop was sourced: _temp_images/, crops/, storyboard base64, etc."},
        "schema": {"is_nullable": True},
    })
    _field(c, "created_at", {
        "type": "timestamp",
        "meta": {"interface": "datetime", "readonly": True, "special": ["date-created"]},
        "schema": {"is_nullable": True},
    })


def main():
    c = local()
    _create_collection(c)
    build_fields(c)
    fields = c.get_fields(VA)
    print(f"\n  {VA}: {len(fields)} fields: {sorted(f['field'] for f in fields)}")


if __name__ == "__main__":
    main()
