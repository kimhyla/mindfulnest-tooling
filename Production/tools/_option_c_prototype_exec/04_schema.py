"""Create prod_storyboard_beats + prod_video_candidates collections in LOCAL Directus.

Field specs from LD-204. Idempotent: safe to re-run — skips any collection
or field that already exists. Writes validation results to stdout.
"""
from __future__ import annotations
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import local  # type: ignore
from lib.directus import DirectusError  # type: ignore

BEATS = "prod_storyboard_beats"
CANDIDATES = "prod_video_candidates"


def _exists_collection(c, name: str) -> bool:
    try:
        c._request("GET", f"/collections/{name}")
        return True
    except DirectusError as e:
        if e.status == 403 or e.status == 404:
            return False
        raise


def _exists_field(c, collection: str, field: str) -> bool:
    try:
        c._request("GET", f"/fields/{collection}/{field}")
        return True
    except DirectusError as e:
        if e.status in (403, 404):
            return False
        raise


def _create_collection(c, name: str, note: str):
    if _exists_collection(c, name):
        print(f"  collection {name} exists")
        return
    payload = {
        "collection": name,
        "meta": {
            "note": note,
            "display_template": None,
            "hidden": False,
            "singleton": False,
            "accountability": "all",
            "color": "#6644FF",
            "icon": "movie",
        },
        "schema": {
            "name": name,
        },
        "fields": [
            {
                "field": "id",
                "type": "uuid",
                "meta": {
                    "hidden": True,
                    "interface": "input",
                    "readonly": True,
                    "special": ["uuid"],
                },
                "schema": {
                    "is_primary_key": True,
                    "has_auto_increment": False,
                    "is_nullable": False,
                },
            }
        ],
    }
    c._request("POST", "/collections", data=payload)
    print(f"  created collection {name}")


def _create_field(c, collection: str, field: str, payload: dict):
    if _exists_field(c, collection, field):
        print(f"  field {collection}.{field} exists")
        return
    payload["field"] = field
    c._request("POST", f"/fields/{collection}", data=payload)
    print(f"  created field {collection}.{field}")


def _str(interface="input", options=None, choices=None, required=False):
    meta = {"interface": interface, "special": None}
    opts = options or {}
    if choices:
        opts["choices"] = [{"text": ch, "value": ch} for ch in choices]
        meta["interface"] = "select-dropdown"
    if opts:
        meta["options"] = opts
    return {
        "type": "string",
        "meta": meta,
        "schema": {"is_nullable": not required},
    }


def _text(required=False):
    return {
        "type": "text",
        "meta": {"interface": "input-multiline"},
        "schema": {"is_nullable": not required},
    }


def _int(required=False, default=None):
    schema = {"is_nullable": not required}
    if default is not None:
        schema["default_value"] = default
    return {
        "type": "integer",
        "meta": {"interface": "input"},
        "schema": schema,
    }


def _bool(default=False):
    return {
        "type": "boolean",
        "meta": {"interface": "boolean"},
        "schema": {"is_nullable": False, "default_value": default},
    }


def _timestamp(auto=None):
    meta = {"interface": "datetime", "readonly": bool(auto), "hidden": False, "width": "half"}
    schema = {"is_nullable": True}
    special = []
    if auto == "created":
        special = ["date-created"]
    elif auto == "updated":
        special = ["date-updated"]
    if special:
        meta["special"] = special
    return {
        "type": "timestamp",
        "meta": meta,
        "schema": schema,
    }


def _file():
    return {
        "type": "uuid",
        "meta": {
            "interface": "file",
            "special": ["file"],
        },
        "schema": {"is_nullable": True},
    }


def _m2o_uuid(related_collection: str):
    return {
        "type": "uuid",
        "meta": {
            "interface": "select-dropdown-m2o",
            "special": ["m2o"],
            "options": {"template": "{{id}}"},
        },
        "schema": {"is_nullable": True, "foreign_key_table": related_collection},
    }


def _o2m_alias():
    return {
        "type": "alias",
        "meta": {
            "interface": "list-o2m",
            "special": ["o2m"],
        },
    }


def build_beats(c):
    _create_collection(c, BEATS, "Option C prototype: storyboard beats for Event_2 Luna (M2). Prototype-scoped — tear down on prototype teardown.")

    # Scalars
    _create_field(c, BEATS, "module_id", _int(required=True))
    _create_field(c, BEATS, "beat_number", _int(required=True))
    _create_field(c, BEATS, "phase", _str(choices=["A", "B", "C"]))
    _create_field(c, BEATS, "beat_order", _int())
    _create_field(c, BEATS, "speaker", _str())
    _create_field(c, BEATS, "dialogue_text", _text())
    _create_field(c, BEATS, "dialogue_text_locked_tts", _text())
    _create_field(c, BEATS, "text_modified_after_tts", _bool(default=False))
    _create_field(c, BEATS, "image_override", _file())
    _create_field(c, BEATS, "trim_start_ms", _int())
    _create_field(c, BEATS, "trim_end_ms", _int())
    _create_field(c, BEATS, "lipsync_status",
                  _str(choices=["none", "queued", "running", "done", "failed"]))
    _create_field(c, BEATS, "lipsync_output", _file())
    _create_field(c, BEATS, "kim_verdict",
                  _str(choices=["pending", "approved", "rejected"]))
    _create_field(c, BEATS, "kim_feedback", _text())
    _create_field(c, BEATS, "status",
                  _str(choices=["pending", "animating", "lipsyncing", "approved"]))
    _create_field(c, BEATS, "updated_at", _timestamp(auto="updated"))

    # selected_option: M2O to candidates — candidate collection may not exist yet
    # when this runs; we defer the M2O until after candidates exists (below).


def build_candidates(c):
    _create_collection(c, CANDIDATES, "Option C prototype: video candidates (A/B/C options per beat). Prototype-scoped.")

    _create_field(c, CANDIDATES, "option_label", _str())
    _create_field(c, CANDIDATES, "source",
                  _str(choices=["kling", "seedance", "kling_startend", "event1_reuse"]))
    _create_field(c, CANDIDATES, "clip_path", _text())
    _create_field(c, CANDIDATES, "duration_ms", _int())
    _create_field(c, CANDIDATES, "created_at", _timestamp(auto="created"))


def build_relation_beats_to_candidates(c):
    """M2O: prod_video_candidates.beat_id -> prod_storyboard_beats (many candidates per beat).
       O2M alias: prod_storyboard_beats.video_options."""
    # First: beat_id M2O on candidates
    if not _exists_field(c, CANDIDATES, "beat_id"):
        c._request("POST", f"/fields/{CANDIDATES}", data={
            "field": "beat_id",
            "type": "uuid",
            "meta": {
                "interface": "select-dropdown-m2o",
                "special": ["m2o"],
                "options": {"template": "{{beat_number}} · {{speaker}}"},
            },
            "schema": {"is_nullable": True, "foreign_key_table": BEATS},
        })
        print(f"  created field {CANDIDATES}.beat_id (M2O -> {BEATS})")
    # Second: O2M alias on beats
    if not _exists_field(c, BEATS, "video_options"):
        c._request("POST", f"/fields/{BEATS}", data={
            "field": "video_options",
            "type": "alias",
            "meta": {
                "interface": "list-o2m",
                "special": ["o2m"],
            },
        })
        print(f"  created field {BEATS}.video_options (O2M alias)")
    # Third: the relation linking them
    # Check existing relations to avoid duplicate
    relations = c._request("GET", "/relations").get("data", [])
    existing = [r for r in relations
                if r.get("collection") == CANDIDATES and r.get("field") == "beat_id"]
    if not existing:
        c._request("POST", "/relations", data={
            "collection": CANDIDATES,
            "field": "beat_id",
            "related_collection": BEATS,
            "meta": {
                "one_field": "video_options",
                "sort_field": None,
                "one_deselect_action": "nullify",
            },
            "schema": {"on_delete": "SET NULL"},
        })
        print(f"  created relation {CANDIDATES}.beat_id -> {BEATS}")
    else:
        print(f"  relation {CANDIDATES}.beat_id -> {BEATS} exists")


def build_relation_beats_selected_option(c):
    """M2O: prod_storyboard_beats.selected_option -> prod_video_candidates."""
    if not _exists_field(c, BEATS, "selected_option"):
        c._request("POST", f"/fields/{BEATS}", data={
            "field": "selected_option",
            "type": "uuid",
            "meta": {
                "interface": "select-dropdown-m2o",
                "special": ["m2o"],
                "options": {"template": "{{option_label}} · {{source}}"},
            },
            "schema": {"is_nullable": True, "foreign_key_table": CANDIDATES},
        })
        print(f"  created field {BEATS}.selected_option (M2O -> {CANDIDATES})")
    relations = c._request("GET", "/relations").get("data", [])
    existing = [r for r in relations
                if r.get("collection") == BEATS and r.get("field") == "selected_option"]
    if not existing:
        c._request("POST", "/relations", data={
            "collection": BEATS,
            "field": "selected_option",
            "related_collection": CANDIDATES,
            "meta": {},
            "schema": {"on_delete": "SET NULL"},
        })
        print(f"  created relation {BEATS}.selected_option -> {CANDIDATES}")
    else:
        print(f"  relation {BEATS}.selected_option -> {CANDIDATES} exists")


def summarize(c):
    for coll in [BEATS, CANDIDATES]:
        fields = c.get_fields(coll)
        names = sorted(f["field"] for f in fields)
        print(f"\n{coll} ({len(names)} fields): {names}")


def main():
    c = local()
    print("=== Create beats ===")
    build_beats(c)
    print("=== Create candidates ===")
    build_candidates(c)
    print("=== Create relation: beats <-O2M- candidates ===")
    build_relation_beats_to_candidates(c)
    print("=== Create relation: beats -M2O-> candidates (selected_option) ===")
    build_relation_beats_selected_option(c)
    print("=== Summary ===")
    summarize(c)

if __name__ == "__main__":
    main()
