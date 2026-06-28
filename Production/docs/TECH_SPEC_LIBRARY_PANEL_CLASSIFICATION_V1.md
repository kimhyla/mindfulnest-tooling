# TECH_SPEC — Library Panel Classification V1

**Status:** Implemented  
**Invariant:** `LIBRARY_PANEL_CLASSIFICATION_V1`  
**Extends:** `Production/lib/library_panel_contract.py`, `GET /api/cr/library`

## 1. Problem class

Library rows were classified in three places (disk `tier`, Directus `asset_type`, client `TIER_TO_FILTER_MAP`). Any drift produced “N items on disk, 0 visible” on refresh across events.

## 2. Category fix

| Layer | Role |
|-------|------|
| **`library_panel_contract.py`** | Sole authority mapping disk `tier` → `panel_tabs[]` |
| **`GET /api/cr/library`** | Every list row includes `panel_tabs`; optional `?panel=images` server filter |
| **Directus enrich** | Overlay only (`is_master`, `has_crop`, `prod_asset_type`); never overwrites `tier` or `panel_tabs` |
| **`LibraryPanel.tsx`** | Filters on `panel_tabs.includes(activeTier)`; legacy tier map is fallback only |

## 3. Row contract

```json
{
  "tier": "element_pose",
  "panel_tabs": ["images"],
  "thumb_url": "/api/cr/thumb?abs_path=..."
}
```

| Disk `tier` | `panel_tabs` |
|-------------|--------------|
| `source`, `cropped`, `character_master`, `element_pose` | `["images"]` |
| `watercolor` | `["watercolors"]` |
| `canonical` | *(row excluded from list)* |

## 4. Durability gates

- `Production/tools/tests/test_library_panel_contract.py`
- `Production/scripts/verify_library_panel_contract_durability.sh` (deploy + session durability)
- Live: all dedicated ports — `panel_tabs` present; `?panel=images` count > 0 when library non-empty

## 5. Related

- `TECH_SPEC_SHARED_BASELINE_IMAGE_LIBRARY_V1.md` — global baseline bytes (Tier 0 merge)
- Kim BS3 lock 2026-05-06 — tab names unchanged
