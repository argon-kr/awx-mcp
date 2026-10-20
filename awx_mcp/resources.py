# SPDX-License-Identifier: Apache-2.0

"""Small read-only resource views over the existing AWX read tools."""

import json
from collections.abc import Callable
from dataclasses import dataclass

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError
from pydantic import TypeAdapter

from .exceptions import AnsibleAPIError
from .settings import Settings
from .tools import inventories, jobs, projects

_INTEGER = TypeAdapter(int)


@dataclass(frozen=True)
class ResourceSpec:
    uri: str
    name: str
    description: str
    toolset: str
    read: Callable[[int], str]
    mime_type: str = "application/json"


_RESOURCES = (
    ResourceSpec(
        "awx://jobs/{id}",
        "job",
        "AWX playbook job status and metadata.",
        "jobs",
        jobs.get_job,
    ),
    ResourceSpec(
        "awx://jobs/{id}/stdout",
        "job_stdout",
        "AWX playbook job stdout as text.",
        "jobs",
        jobs.get_job_stdout,
        "text/plain",
    ),
    ResourceSpec(
        "awx://inventories/{id}",
        "inventory",
        "AWX inventory details.",
        "inventories",
        inventories.get_inventory,
    ),
    ResourceSpec(
        "awx://inventory-sources/{id}",
        "inventory_source",
        "AWX inventory source configuration and sync status.",
        "inventories",
        inventories.get_inventory_source,
    ),
    ResourceSpec(
        "awx://projects/{id}",
        "project",
        "AWX project SCM configuration and status.",
        "projects",
        projects.get_project,
    ),
)


def _reader(spec: ResourceSpec) -> Callable[[str], str]:
    def read(id: str) -> str:
        try:
            # URI parameters arrive as strings. Match the integer coercion used
            # by tool input validation before interpolating an API endpoint.
            result = spec.read(_INTEGER.validate_python(id))
            if spec.mime_type == "text/plain":
                return json.loads(result)["stdout"]
            return result
        except (AnsibleAPIError, PermissionError, ValueError) as exc:
            # Resources have JSON-RPC errors, not success-shaped error content.
            raise ResourceError(str(exc)) from exc

    return read


def register_resources(target: MCPServer, settings: Settings) -> None:
    """Replace owned templates while preserving unrelated registrations."""
    # SDK 2.x has no public template-removal API. It does not cache resources
    # instantiated from templates, so removing the template also removes reads.
    for spec in _RESOURCES:
        target._resource_manager._templates.pop(spec.uri, None)
    for spec in _RESOURCES:
        if settings.toolsets is None or spec.toolset in settings.toolsets:
            target.resource(
                spec.uri,
                name=spec.name,
                description=spec.description,
                mime_type=spec.mime_type,
            )(_reader(spec))
