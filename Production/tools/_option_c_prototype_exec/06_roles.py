"""Create kim_producer role with scoped permissions.

Produces:
- Role `kim_producer`
- Policy `kim_producer_policy` with CRUD on prod_storyboard_beats +
  prod_video_candidates, read on directus_files, create on directus_files
  (for image_override drops), trigger on directus_flows, read on own user.
- Access row linking role -> policy
- User `producer@mindfulnest.dev` / `producer-prototype` assigned to role

kim_admin already exists as the bootstrap admin (kim@mindfulnest.dev /
local-prototype); no new admin needed.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import local  # type: ignore
from credentials_lib.directus import DirectusError  # type: ignore

BEATS = "prod_storyboard_beats"
CANDIDATES = "prod_video_candidates"

ROLE_NAME = "kim_producer"
POLICY_NAME = "kim_producer_policy"
USER_EMAIL = "producer@mindfulnest.dev"
USER_PASSWORD = "producer-prototype"


def _find(c, path, name_field, name_value):
    r = c._request("GET", path, params={
        f"filter[{name_field}][_eq]": name_value,
        "limit": 1,
    })
    data = r.get("data", [])
    return data[0] if data else None


def upsert_role(c):
    existing = _find(c, "/roles", "name", ROLE_NAME)
    if existing:
        print(f"  role {ROLE_NAME} exists id={existing['id']}")
        return existing
    r = c._request("POST", "/roles", data={
        "name": ROLE_NAME,
        "icon": "drive_file_rename_outline",
        "description": "Kim-as-producer test role for Option C prototype",
    })
    created = r.get("data", {})
    print(f"  created role {ROLE_NAME} id={created['id']}")
    return created


def upsert_policy(c):
    existing = _find(c, "/policies", "name", POLICY_NAME)
    if existing:
        print(f"  policy {POLICY_NAME} exists id={existing['id']}")
        return existing
    r = c._request("POST", "/policies", data={
        "name": POLICY_NAME,
        "icon": "policy",
        "description": "Producer-scoped permissions for prototype: CRUD on beats and candidates, read/create on files, trigger on flows.",
        "app_access": True,
        "admin_access": False,
    })
    created = r.get("data", {})
    print(f"  created policy {POLICY_NAME} id={created['id']}")
    return created


def upsert_access(c, role_id, policy_id):
    r = c._request("GET", "/access", params={
        f"filter[role][_eq]": role_id,
        f"filter[policy][_eq]": policy_id,
        "limit": 1,
    })
    if r.get("data"):
        print(f"  access link role->policy exists")
        return r["data"][0]
    created = c._request("POST", "/access", data={
        "role": role_id,
        "policy": policy_id,
        "sort": 1,
    }).get("data", {})
    print(f"  linked role {role_id} <- policy {policy_id} (access id={created.get('id')})")
    return created


def grant_permission(c, policy_id, collection, action, fields="*"):
    # Check if exists
    r = c._request("GET", "/permissions", params={
        f"filter[policy][_eq]": policy_id,
        f"filter[collection][_eq]": collection,
        f"filter[action][_eq]": action,
        "limit": 1,
    })
    if r.get("data"):
        return r["data"][0]
    created = c._request("POST", "/permissions", data={
        "policy": policy_id,
        "collection": collection,
        "action": action,
        "permissions": {},
        "validation": {},
        "presets": {},
        "fields": fields,
    }).get("data", {})
    print(f"    grant {collection}.{action} (fields={fields if fields == '*' else '…'})")
    return created


def upsert_user(c, role_id):
    existing = _find(c, "/users", "email", USER_EMAIL)
    if existing:
        print(f"  user {USER_EMAIL} exists id={existing['id']}")
        # Make sure it's still on the producer role
        if existing.get("role") != role_id:
            c._request("PATCH", f"/users/{existing['id']}", data={"role": role_id})
            print(f"    updated user.role -> {role_id}")
        return existing
    created = c._request("POST", "/users", data={
        "email": USER_EMAIL,
        "password": USER_PASSWORD,
        "first_name": "Kim",
        "last_name": "(Producer)",
        "role": role_id,
        "status": "active",
    }).get("data", {})
    print(f"  created user {USER_EMAIL} id={created['id']}")
    return created


def main():
    c = local()
    role = upsert_role(c)
    policy = upsert_policy(c)
    upsert_access(c, role["id"], policy["id"])

    # Grants: CRUD on the two prototype collections
    for coll in [BEATS, CANDIDATES]:
        for action in ["create", "read", "update", "delete"]:
            grant_permission(c, policy["id"], coll, action)

    # File read + create (so drag-drop can upload image_override)
    for action in ["create", "read", "update"]:
        grant_permission(c, policy["id"], "directus_files", action)
    # File folder read so uploader UI can list folders
    grant_permission(c, policy["id"], "directus_folders", "read")

    # Flow trigger (not manage)
    grant_permission(c, policy["id"], "directus_flows", "read")

    # Presets: read (so kim_producer sees the Kanban bookmark)
    grant_permission(c, policy["id"], "directus_presets", "read")

    upsert_user(c, role["id"])

    # Summary
    perms = c._request("GET", "/permissions", params={
        f"filter[policy][_eq]": policy["id"], "limit": 100,
    }).get("data", [])
    print(f"\n  {POLICY_NAME} has {len(perms)} permission grants")


if __name__ == "__main__":
    main()
