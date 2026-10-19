# SPDX-License-Identifier: Apache-2.0

"""Small resource operations shared by tool modules that own the client context."""

from collections.abc import Mapping
from typing import Any

from ..client import AnsibleClient, handle_pagination
from ..utils import to_json


def drop_none(**fields: Any) -> dict[str, Any]:
    """Omit absent optional fields while retaining explicit false/empty values."""
    return {key: value for key, value in fields.items() if value is not None}


def list_resource(
    client: AnsibleClient,
    endpoint: str,
    *,
    limit: int = 20,
    offset: int = 0,
    name: str | None = None,
    params: Mapping[str, Any] | None = None,
) -> str:
    """Serialize a paginated resource list with an optional partial-name filter."""
    query = dict(params or {})
    query.update(limit=limit, offset=offset)
    if name and name.strip():
        query["name__icontains"] = name.strip()
    return to_json(handle_pagination(client, endpoint, query, with_meta=True))


def get_resource(client: AnsibleClient, endpoint: str) -> str:
    """Serialize one resource without changing the API response fields."""
    return to_json(client.request("GET", endpoint))


def delete_resource(client: AnsibleClient, endpoint: str, *, message: str) -> str:
    """Delete a resource and return its tool-specific success message."""
    client.request("DELETE", endpoint)
    return to_json({"status": "success", "message": message})
