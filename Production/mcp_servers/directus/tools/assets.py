"""Asset tools: register_asset, find_asset.

Both delegate to Production/tools/registered_write.py. That wrapper enforces
LD-421/422 (ASSET_FINDABILITY_BUILD_V1) — atomic SHA256 + dedup + Two-Write
Rule (prod_assets row + prod_activity_log row). The MCP server MUST go
through this wrapper, not bypass it (per CLAUDE.md Rule 34).

Eager top-of-module imports (locked 2026-05-10 per LD
MCP_REGISTERED_WRITE_MIGRATED_TO_TOOLING_V1; see
Production/docs/V59_REGISTERED_WRITE_MIGRATION_SPEC_v1.md): registered_write
+ credentials_lib are now in this tooling-mcp tree at canonical paths.
Failure to import here surfaces at MCP boot (fail-fast), not at first tool
invocation (fail-late) — per CLAUDE.md Rule 19.

Pre-existing dual-lib situation (out of scope for this migration; see spec
§4 FOLLOWUP-1): registered_write.py imports Production.tools.credentials_lib.directus
(21612 b), distinct from the Production.lib.directus (28989 b) used by the
MCP server's CRUD/decisions/activity tools. Both work today; unification
is a future PR.
"""

from __future__ import annotations

from typing import Any

# Eager imports — proven reachable at MCP boot per V59_REGISTERED_WRITE_MIGRATION_SPEC_v1.
from Production.tools.registered_write import register_asset as _reg, search as _search


def register(mcp: Any) -> None:
    @mcp.tool(
        name="register_asset",
        description=(
            "Register a media asset (file or directory) in prod_assets per "
            "CLAUDE.md Rule 34 (ASSET_FINDABILITY_BUILD_V1). Atomic: SHA256 + "
            "dedup-check + POST prod_assets + POST prod_activity_log Two-Write "
            "Rule. Returns existing asset_id if SHA256 already registered "
            "(idempotent on dedup).\n\n"
            "Required:\n"
            "- file_path (str): absolute path inside the project\n"
            "- asset_type (str enum): final_atomic_mp4 | beat_scene | "
            "  scene_concat_mp4 | pre_lipsync | lipsync_clip | tts_audio | "
            "  voice_stem | phase_b_mix | ambient_bed | sfx | magic_clip | "
            "  still_master | still_delivery | composite | storyboard_html | "
            "  module_json | phase_a_scene | audio_library_folder | unknown\n"
            "- module_id (int): FK to prod_modules.id (NOT M-number)\n"
            "- produced_by_skill (str): the skill or tool that produced this asset\n\n"
            "Optional: event_id, beat_id, parent_asset_id, iteration_notes, "
            "colloquial_name, tags, library, notes, role.\n\n"
            "Returns: {ok: true, asset_id: int, file_path: str} | "
            "{ok: false, queued: true, ...} on Directus failure."
        ),
    )
    def register_asset(
        file_path: str,
        asset_type: str,
        module_id: int,
        produced_by_skill: str,
        event_id: int | None = None,
        beat_id: str | None = None,
        parent_asset_id: int | None = None,
        iteration_notes: str = "",
        colloquial_name: str | None = None,
        tags: list[str] | None = None,
        library: bool = False,
        notes: str = "",
        role: str | None = None,
    ) -> dict:
        try:
            asset_id, abs_path = _reg(
                file_path=file_path,
                asset_type=asset_type,
                module_id=module_id,
                event_id=event_id,
                beat_id=beat_id,
                parent_asset_id=parent_asset_id,
                produced_by_skill=produced_by_skill,
                iteration_notes=iteration_notes,
                colloquial_name=colloquial_name,
                tags=tags,
                library=library,
                notes=notes,
                role=role,
            )
            if asset_id == -1:
                return {"ok": False, "queued": True, "file_path": abs_path}
            return {"ok": True, "asset_id": asset_id, "file_path": abs_path}
        except (ValueError, FileNotFoundError) as e:
            return {"ok": False, "validation_error": True, "msg": f"{type(e).__name__}: {e}"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "internal_error": True, "msg": f"{type(e).__name__}: {e}"}

    @mcp.tool(
        name="find_asset",
        description=(
            "Search registered assets by natural-language phrase. Union query "
            "across prod_assets, prod_visual_assets, prod_audio_assets, plus "
            "prod_asset_aliases. Searches: iteration_notes, colloquial_name, "
            "tags, alias_text, asset_name, notes.\n\n"
            "Per CLAUDE.md Rule 34: this tool MUST be queried first when Kim "
            "references 'the approved clip' / 'the one with X' — disk inspection "
            "is fallback only.\n\n"
            "Optional filters: module_id, event_id, is_current, kim_verdict, "
            "asset_type. Default limit=50.\n\n"
            "Returns: {ok: true, results: list[dict], count: int}. Each result "
            "carries _match_source (iteration_notes | alias | colloquial_name | "
            "tag | asset_name) and _source_collection."
        ),
    )
    def find_asset(
        phrase: str,
        module_id: int | None = None,
        event_id: int | None = None,
        is_current: bool | None = None,
        kim_verdict: str | None = None,
        asset_type: str | None = None,
        limit: int = 50,
    ) -> dict:
        try:
            results = _search(
                phrase=phrase,
                module_id=module_id,
                event_id=event_id,
                is_current=is_current,
                kim_verdict=kim_verdict,
                asset_type=asset_type,
                limit=limit,
            )
            return {"ok": True, "results": results, "count": len(results)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "internal_error": True, "msg": f"{type(e).__name__}: {e}"}
