"""
directus_admin_client.py — thin wrapper around DirectusClient for admin scripts.

Exposes the interface expected by governance_drift_check.py and any other
Production/scripts/ tool that needs `get_items` / `post_item` / `patch_item`
with credential-free construction.

Usage:
    from credentials_lib.directus_admin_client import DirectusAdminClient, DirectusAdminError

    client = DirectusAdminClient()          # loads creds automatically
    rows   = client.get_items("prod_locked_decisions", filters={...}, limit=-1)
    row    = client.post_item("app_blockers", {"title": "...", ...})
"""

from __future__ import annotations

from .credentials import load_credentials
from .directus import DirectusClient, DirectusError


class DirectusAdminError(Exception):
    """Re-exported for callers that catch DirectusAdminError by name."""
    pass


class DirectusAdminClient:
    """
    Admin-flavoured Directus client with no-arg constructor.

    Loads credentials via load_credentials() and wraps DirectusClient,
    translating its interface into the `get_items` / `post_item` /
    `patch_item` shape used by governance_drift_check.py and audit scripts.
    """

    def __init__(self):
        creds = load_credentials()
        self._client = DirectusClient(
            creds["directus_url"],
            creds["directus_email"],
            creds["directus_password"],
        )
        self._client.authenticate()

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------

    def _wrap(self, fn, *args, **kwargs):
        """Call a DirectusClient method and re-raise as DirectusAdminError."""
        try:
            return fn(*args, **kwargs)
        except DirectusError as e:
            raise DirectusAdminError(str(e)) from e

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_items(
        self,
        collection: str,
        *,
        filters: dict | None = None,
        fields: list[str] | str | None = None,
        sort: str | list | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """
        Fetch items from a Directus collection.

        Args:
            collection: Collection name, e.g. 'prod_locked_decisions'
            filters:    dict of {field: {operator: value}} passed to DirectusClient.get()
            fields:     list or comma-string of fields to return
            sort:       sort expression, e.g. '-created_at'
            limit:      max records; pass -1 for no limit (maps to Directus limit=-1)

        Returns:
            list of item dicts
        """
        params: dict = {}

        if filters:
            for field, ops in filters.items():
                if isinstance(ops, dict):
                    for op, val in ops.items():
                        params[f"filter[{field}][{op}]"] = val
                else:
                    params[f"filter[{field}][_eq]"] = ops

        if fields:
            params["fields"] = (
                ",".join(fields) if isinstance(fields, list) else fields
            )

        if sort:
            params["sort"] = sort if isinstance(sort, str) else ",".join(sort)

        if limit is not None:
            params["limit"] = limit  # -1 = no limit in Directus

        try:
            resp = self._client._request("GET", f"/items/{collection}", params=params)
        except DirectusError as e:
            raise DirectusAdminError(str(e)) from e

        return resp.get("data", [])

    def post_item(self, collection: str, payload: dict) -> dict:
        """
        Create a new item in a collection.

        Args:
            collection: Collection name
            payload:    Field values for the new item

        Returns:
            The created item dict (includes 'id')
        """
        try:
            resp = self._client._request("POST", f"/items/{collection}", data=payload)
        except DirectusError as e:
            raise DirectusAdminError(str(e)) from e
        return resp.get("data", {})

    def patch_item(self, collection: str, item_id: int | str, payload: dict) -> dict:
        """
        Update an existing item.

        Args:
            collection: Collection name
            item_id:    Record ID
            payload:    Fields to update

        Returns:
            The updated item dict
        """
        try:
            resp = self._client._request(
                "PATCH", f"/items/{collection}/{item_id}", data=payload
            )
        except DirectusError as e:
            raise DirectusAdminError(str(e)) from e
        return resp.get("data", {})
