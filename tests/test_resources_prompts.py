# SPDX-License-Identifier: Apache-2.0

"""Resource and runbook contracts through real in-process MCP sessions."""

import json
from contextlib import asynccontextmanager
from dataclasses import replace

import anyio
import pytest
import responses
from mcp import ClientSession
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.shared.memory import create_client_server_memory_streams

from awx_mcp import server
from awx_mcp.settings import get_settings
from tests.conftest import set_test_settings


@asynccontextmanager
async def mcp_session(target):
    """Exercise JSON-RPC dispatch, including resource errors, in memory."""
    lowlevel = getattr(target, "_lowlevel_server", target)
    async with create_client_server_memory_streams() as (client_io, server_io):
        async with anyio.create_task_group() as group:
            group.start_soon(
                lowlevel.run,
                *server_io,
                lowlevel.create_initialization_options(),
            )
            async with ClientSession(*client_io) as session:
                initialized = await session.initialize()
                yield session, initialized
            group.cancel_scope.cancel()


def configured_server(**overrides):
    register = getattr(server, "register_capabilities", None)
    assert callable(register), "startup must explicitly register resources and prompts"
    target = MCPServer("resources-test", middleware=[server._capture_request_headers])
    register(target, replace(get_settings(), **overrides))
    return target


@responses.activate
def test_resources_read_actual_awx_content_with_correct_mime():
    target = configured_server(read_only=True)
    resources = [
        ("awx://jobs/42", "/jobs/42/", {"id": 42, "status": "failed"}),
        ("awx://inventories/7", "/inventories/7/", {"id": 7, "name": "web"}),
        (
            "awx://inventory-sources/8",
            "/inventory_sources/8/",
            {"id": 8, "source": "scm"},
        ),
        ("awx://projects/9", "/projects/9/", {"id": 9, "scm_revision": "abc"}),
    ]
    for _, path, payload in resources:
        responses.get(f"https://test.example.com/api/v2{path}", json=payload)
    responses.get(
        "https://test.example.com/api/v2/jobs/42/stdout/?format=txt",
        body="PLAY [web]\nfatal: [host1]: FAILED!\n",
        content_type="text/plain",
    )

    async def run():
        async with mcp_session(target) as (session, initialized):
            assert initialized.capabilities.resources is not None
            assert initialized.capabilities.prompts is not None
            assert (await session.list_resources()).resources == []
            templates = (await session.list_resource_templates()).resource_templates
            assert {t.uri_template for t in templates} == {
                "awx://jobs/{id}",
                "awx://jobs/{id}/stdout",
                "awx://inventories/{id}",
                "awx://inventory-sources/{id}",
                "awx://projects/{id}",
            }
            for uri, _, payload in resources:
                result = await session.read_resource(uri)
                assert len(result.contents) == 1
                assert result.contents[0].mime_type == "application/json"
                assert json.loads(result.contents[0].text) == payload
            stdout = (await session.read_resource("awx://jobs/42/stdout")).contents[0]
            assert stdout.mime_type == "text/plain"
            assert stdout.text == "PLAY [web]\nfatal: [host1]: FAILED!\n"

    anyio.run(run)
    assert all(c.request.method == "GET" for c in responses.calls)


@responses.activate
def test_resource_errors_are_rpc_errors_and_invalid_ids_never_reach_awx():
    target = configured_server()
    responses.get(
        "https://test.example.com/api/v2/jobs/404/",
        status=404,
        json={"detail": "No Job matches the given query."},
    )

    async def run():
        async with mcp_session(target) as (session, _):
            with pytest.raises(MCPError, match="No Job matches"):
                await session.read_resource("awx://jobs/404")
            with pytest.raises(MCPError, match="integer"):
                await session.read_resource("awx://jobs/not-an-id")
            for uri in ("awx://credentials/1", "awx://jobs/42?format=html"):
                with pytest.raises(MCPError, match="Unknown resource"):
                    await session.read_resource(uri)

    anyio.run(run)
    assert len(responses.calls) == 1


@responses.activate
def test_passthrough_resource_cannot_fall_back_to_server_token(monkeypatch):
    set_test_settings(monkeypatch, auth_mode="passthrough", token="SERVER-SECRET")
    target = configured_server()

    async def run():
        async with mcp_session(target) as (session, _):
            with pytest.raises(MCPError, match="token is required"):
                await session.read_resource("awx://inventories/7")

    anyio.run(run)
    assert len(responses.calls) == 0


@responses.activate
def test_runbooks_have_actionable_arguments_and_perform_no_awx_io():
    target = configured_server()
    cases = [
        (
            "failed_job_triage",
            "job_id",
            "42",
            {
                "get_job",
                "get_job_stdout",
                "get_job_events",
                "get_job_host_summaries",
            },
        ),
        (
            "pre_change_inventory_check",
            "inventory_id",
            "7",
            {
                "get_inventory",
                "list_hosts",
                "list_groups",
                "list_inventory_sources",
            },
        ),
        (
            "project_sync_review",
            "project_id",
            "9",
            {
                "get_project",
                "list_project_updates",
                "get_project_update",
                "get_project_update_stdout",
                "list_project_playbooks",
            },
        ),
    ]

    async def run():
        async with mcp_session(target) as (session, _):
            prompts = {p.name: p for p in (await session.list_prompts()).prompts}
            assert set(prompts) == {case[0] for case in cases}
            for name, argument, value, tool_names in cases:
                assert [(a.name, a.required) for a in prompts[name].arguments] == [
                    (argument, True)
                ]
                result = await session.get_prompt(name, {argument: value})
                assert result.messages[0].role == "user"
                text = result.messages[0].content.text
                for tool in tool_names:
                    assert tool in text
                assert f"{argument}={value}" in text
                assert "confirm" in text.lower() and "write" in text.lower()
                assert "offset" in text
            with pytest.raises(MCPError):
                await session.get_prompt("failed_job_triage", {})
            with pytest.raises(MCPError, match="integer"):
                await session.get_prompt("failed_job_triage", {"job_id": "invalid"})

    anyio.run(run)
    assert len(responses.calls) == 0


@responses.activate
def test_reconfiguration_removes_stale_capabilities_and_preserves_unrelated_ones():
    target = configured_server()

    @target.resource("custom://context/{id}")
    def custom_resource(id: str) -> str:
        return id

    @target.prompt()
    def custom_prompt() -> str:
        return "Custom instructions"

    async def run():
        # Read first to catch accidental retention of instantiated templates.
        responses.get("https://test.example.com/api/v2/jobs/42/", json={"id": 42})
        async with mcp_session(target) as (session, _):
            await session.read_resource("awx://jobs/42")
        server.register_capabilities(
            target, replace(get_settings(), toolsets=("inventories",), read_only=True)
        )
        async with mcp_session(target) as (session, _):
            templates = (await session.list_resource_templates()).resource_templates
            assert {t.uri_template for t in templates} == {
                "awx://inventories/{id}",
                "awx://inventory-sources/{id}",
                "custom://context/{id}",
            }
            assert [p.name for p in (await session.list_prompts()).prompts] == [
                "custom_prompt"
            ]
            with pytest.raises(MCPError, match="Unknown resource"):
                await session.read_resource("awx://jobs/42")
        server.register_capabilities(
            target, replace(get_settings(), toolsets=("jobs",), read_only=True)
        )
        async with mcp_session(target) as (session, _):
            assert {p.name for p in (await session.list_prompts()).prompts} == {
                "custom_prompt",
                "failed_job_triage",
            }
            tools = {t.name for t in (await session.list_tools()).tools}
            assert {"get_job", "get_job_stdout"} <= tools
            assert "relaunch_job" not in tools

    anyio.run(run)
