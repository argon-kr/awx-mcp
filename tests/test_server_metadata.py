# SPDX-License-Identifier: Apache-2.0

"""Server identity, instructions and per-tool metadata advertised to clients."""

import anyio
import pytest

import awx_mcp.tools  # noqa: F401  (registers the tools on server.mcp)
from awx_mcp import server
from awx_mcp.utils import package_version


def test_server_identity_and_instructions():
    assert server.mcp.name == "awx-mcp"
    assert server.mcp.version == package_version()
    instructions = server.mcp.instructions or ""
    # the conventions the model needs before its first call
    for needle in ("offset + returned < count", "get_job_stdout", "403"):
        assert needle in instructions


@pytest.mark.parametrize(
    ("name", "title"),
    [
        ("list_job_templates", "List job templates"),
        ("list_object_roles", "List object roles"),
        ("get_project_update_stdout", "Get project update stdout"),
        ("list_rbac_x", "List RBAC x"),
    ],
)
def test_tool_title(name, title):
    assert server.tool_title(name) == title


def test_every_tool_has_a_title_and_open_world_hint():
    tools = anyio.run(server.mcp.list_tools)
    missing_title = [t.name for t in tools if not t.title]
    not_open_world = [
        t.name for t in tools if not (t.annotations and t.annotations.open_world_hint)
    ]
    assert missing_title == []
    assert not_open_world == []
