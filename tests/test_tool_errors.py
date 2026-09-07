# SPDX-License-Identifier: Apache-2.0

"""Tests for ``_surface_tool_errors``: anticipated tool failures reach the model.

Since mcp 2.1 (python-sdk #3314) MCPServer masks any exception other than
``ToolError`` raised by a tool as a bare ``Error executing tool <name>``. Every
AWX 401/403/400 message, the read-only refusal and argument-validation errors
would vanish from the model's view. ``read_tool`` / ``write_tool`` therefore
wrap each tool so those anticipated failures are re-raised as ``ToolError``.

These tests pin:

* which exception types are converted (``AnsibleAPIError`` subclasses,
  ``PermissionError``, ``ValueError``) and that the text and ``__cause__`` are kept
* that anything else still propagates unchanged (a crash stays a crash)
* sync and async tools, and that ``functools.wraps`` metadata survives so
  MCPServer's schema generation is unaffected
* end-to-end through ``MCPServer.call_tool`` on whichever mcp is installed: the
  failure text is present in what the SDK raises for the client
"""

import inspect

import anyio
import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from awx_mcp import server
from awx_mcp.exceptions import (
    AnsibleAuthError,
    AnsibleHTTPError,
    AnsibleValidationError,
)

TOKEN_REQUIRED = (
    "An AWX token is required in passthrough mode. Send it as "
    "'Authorization: Bearer <token>' (or the X-AWX-Token header)."
)


@pytest.mark.parametrize(
    "exc",
    [
        AnsibleAuthError(TOKEN_REQUIRED, status_code=401),
        AnsibleHTTPError("AWX returned 502 Bad Gateway", status_code=502),
        AnsibleValidationError("name: This field is required.", status_code=400),
        PermissionError(
            "'launch_job' is a write operation and read-only mode is enabled"
        ),
        ValueError("job_template_id must be a positive integer"),
    ],
    ids=lambda e: type(e).__name__,
)
def test_anticipated_error_becomes_tool_error_with_same_text(exc):
    @server._surface_tool_errors
    def tool():
        raise exc

    with pytest.raises(ToolError) as info:
        tool()

    assert str(info.value) == str(exc)
    assert info.value.__cause__ is exc


def test_unexpected_error_propagates_unchanged():
    @server._surface_tool_errors
    def tool():
        raise KeyError("results")

    with pytest.raises(KeyError):
        tool()


def test_async_tool_is_wrapped_too():
    @server._surface_tool_errors
    async def tool():
        raise AnsibleAuthError(TOKEN_REQUIRED, status_code=401)

    assert inspect.iscoroutinefunction(tool)
    with pytest.raises(ToolError, match="token is required"):
        anyio.run(tool)


def test_async_unexpected_error_propagates_unchanged():
    @server._surface_tool_errors
    async def tool():
        raise KeyError("results")

    with pytest.raises(KeyError):
        anyio.run(tool)


def test_return_value_and_metadata_are_preserved():
    def tool(job_id: int, name: str = None) -> dict:
        """Look up a job."""
        return {"id": job_id, "name": name}

    wrapped = server._surface_tool_errors(tool)

    assert wrapped(7, name="x") == {"id": 7, "name": "x"}
    assert wrapped.__name__ == "tool"
    assert wrapped.__doc__ == "Look up a job."
    assert inspect.signature(wrapped) == inspect.signature(tool)


def test_failure_text_reaches_the_client_through_mcpserver():
    """End-to-end on the installed SDK: the message is in what the client gets.

    ``MCPServer.call_tool`` raises ``ToolError`` for the request handler to turn
    into an ``is_error`` result; on mcp >= 2.1 an unwrapped exception would
    surface as a bare ``Error executing tool get_ansible_version`` instead.
    """
    srv = MCPServer("awx-test")

    @srv.tool()
    @server._surface_tool_errors
    def get_ansible_version() -> dict:
        raise AnsibleAuthError(TOKEN_REQUIRED, status_code=401)

    with pytest.raises(ToolError) as info:
        anyio.run(srv.call_tool, "get_ansible_version", {})

    text = str(info.value)
    assert text.startswith("Error executing tool get_ansible_version")
    assert "token is required" in text.lower()
