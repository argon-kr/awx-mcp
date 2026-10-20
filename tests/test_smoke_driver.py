# SPDX-License-Identifier: Apache-2.0

"""The smoke command must reject protocol-level tool errors and empty results."""

import os
import sys

import anyio
import pytest
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

from scripts import mcp_smoke_test as smoke


def drive_probe(body: str):
    script = (
        "from mcp.server.mcpserver import MCPServer\n"
        "from mcp.server.mcpserver.exceptions import ToolError\n"
        "mcp = MCPServer('smoke-fixture')\n"
        "@mcp.tool(structured_output=False)\n"
        "def get_ansible_version() -> str:\n"
        f"    {body}\n"
        "mcp.run(transport='stdio')\n"
    )

    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-c", script])
        with open(os.devnull, "w") as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                return await smoke._drive(read, write)

    return anyio.run(run)


def leaf_errors(exc):
    # anyio wraps errors during stream teardown, including on Python 3.10.
    nested = getattr(exc, "exceptions", ())
    if nested:
        for child in nested:
            yield from leaf_errors(child)
    else:
        yield exc


@pytest.mark.parametrize(
    "body, message",
    [
        ("raise ToolError('fixture probe denied')", "fixture probe denied"),
        ("return ''", "returned no text"),
    ],
)
def test_smoke_rejects_failed_or_empty_probe_instead_of_reporting_pass(body, message):
    with pytest.raises(Exception) as caught:
        drive_probe(body)
    errors = list(leaf_errors(caught.value))
    assert any(
        isinstance(exc, RuntimeError)
        and "get_ansible_version" in str(exc)
        and message in str(exc)
        for exc in errors
    ), errors


def test_smoke_accepts_successful_probe():
    count, text = drive_probe('return \'{"version":"24.6.1"}\'')
    assert count == 1
    assert text == '{"version":"24.6.1"}'


def test_unknown_mode_lists_exercise_as_supported_choice(monkeypatch):
    monkeypatch.setenv("ANSIBLE_BASE_URL", "http://127.0.0.1:1/")
    monkeypatch.setenv("ANSIBLE_TOKEN", "fixture-token")
    monkeypatch.setattr(sys, "argv", ["mcp_smoke_test.py", "unknown"])

    with pytest.raises(SystemExit, match="Choose:.*exercise"):
        anyio.run(smoke.main)
