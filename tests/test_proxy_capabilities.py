# SPDX-License-Identifier: Apache-2.0

"""Resource/prompt relay behavior over two real in-memory MCP sessions."""

import anyio
import pytest
from mcp.server.lowlevel import Server
from mcp.shared.exceptions import MCPError
from mcp.types import (
    BlobResourceContents,
    GetPromptResult,
    ListPromptsResult,
    ListResourcesResult,
    ListResourceTemplatesResult,
    PaginatedRequestParams,
    Prompt,
    PromptMessage,
    ReadResourceResult,
    Resource,
    ResourceTemplate,
    TextContent,
    TextResourceContents,
)

from awx_mcp import proxy
from tests.test_resources_prompts import mcp_session


def create_relay(upstream, initialized):
    factory = getattr(proxy, "_create_proxy", None)
    assert callable(factory), "proxy must relay upstream resources and prompts"
    return factory(
        upstream, initialized, usage_user="fixture", central_host="localhost"
    )


def test_proxy_preserves_pagination_resource_content_metadata_and_prompt_arguments():
    async def list_resources(ctx, params):
        assert params.cursor == "resource-page-2"
        return ListResourcesResult(
            resources=[
                Resource(
                    uri="awx://jobs/42",
                    name="job",
                    mime_type="application/json",
                    meta={"revision": "fixture"},
                )
            ],
            next_cursor="resource-page-3",
            meta={"page": 2},
        )

    async def list_templates(ctx, params):
        assert params.cursor == "template-page-2"
        return ListResourceTemplatesResult(
            resource_templates=[
                ResourceTemplate(
                    uri_template="awx://jobs/{id}",
                    name="job",
                    mime_type="application/json",
                    meta={"source": "central"},
                )
            ],
            next_cursor="template-page-3",
        )

    async def read_resource(ctx, params):
        if params.uri == "awx://jobs/404":
            raise MCPError(-32002, "AWX job not found", {"status": 404})
        return ReadResourceResult(
            contents=[
                TextResourceContents(
                    uri=params.uri,
                    mime_type="text/plain",
                    text="failed host1",
                    meta={"source": "central"},
                ),
                BlobResourceContents(
                    uri=params.uri,
                    mime_type="application/octet-stream",
                    blob="AAE=",
                    meta={"encoding": "fixture"},
                ),
            ],
            meta={"read": "complete"},
        )

    async def list_prompts(ctx, params):
        assert params.cursor == "prompt-page-2"
        return ListPromptsResult(
            prompts=[Prompt(name="triage", description="Read checks")],
            next_cursor="prompt-page-3",
            meta={"page": 2},
        )

    async def get_prompt(ctx, params):
        if params.name == "missing":
            raise MCPError(-32602, "Unknown prompt from central")
        return GetPromptResult(
            description=params.name,
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"Read job {params.arguments['job_id']}",
                    ),
                )
            ],
            meta={"source": "central"},
        )

    central = Server(
        "fixture-central",
        instructions="Use caller permissions",
        on_list_resources=list_resources,
        on_list_resource_templates=list_templates,
        on_read_resource=read_resource,
        on_list_prompts=list_prompts,
        on_get_prompt=get_prompt,
    )

    async def run():
        async with mcp_session(central) as (upstream, initialized):
            relay = create_relay(upstream, initialized)
            async with mcp_session(relay) as (session, proxy_init):
                assert proxy_init.instructions == "Use caller permissions"
                assert proxy_init.capabilities.resources is not None
                assert not proxy_init.capabilities.resources.subscribe
                assert proxy_init.capabilities.prompts is not None
                assert proxy_init.capabilities.tools is None
                resources = await session.list_resources(
                    params=PaginatedRequestParams(cursor="resource-page-2")
                )
                assert resources.next_cursor == "resource-page-3"
                assert resources.meta == {"page": 2}
                assert resources.resources[0].meta == {"revision": "fixture"}
                templates = await session.list_resource_templates(
                    params=PaginatedRequestParams(cursor="template-page-2")
                )
                assert templates.next_cursor == "template-page-3"
                assert templates.resource_templates[0].meta == {"source": "central"}
                result = await session.read_resource("awx://jobs/42")
                assert result.meta == {"read": "complete"}
                assert result.contents[0].text == "failed host1"
                assert result.contents[0].mime_type == "text/plain"
                assert result.contents[0].meta == {"source": "central"}
                assert result.contents[1].blob == "AAE="
                assert result.contents[1].mime_type == "application/octet-stream"
                prompts = await session.list_prompts(
                    params=PaginatedRequestParams(cursor="prompt-page-2")
                )
                assert prompts.next_cursor == "prompt-page-3"
                assert prompts.meta == {"page": 2}
                prompt = await session.get_prompt("triage", {"job_id": "42"})
                assert prompt.messages[0].content.text == "Read job 42"
                assert prompt.meta == {"source": "central"}
                with pytest.raises(MCPError, match="AWX job not found") as error:
                    await session.read_resource("awx://jobs/404")
                assert error.value.code == -32002
                assert error.value.data == {"status": 404}
                with pytest.raises(MCPError, match="Unknown prompt from central"):
                    await session.get_prompt("missing")

    anyio.run(run)


def test_proxy_does_not_advertise_unavailable_capabilities():
    async def run():
        async with mcp_session(Server("minimal-central")) as (upstream, initialized):
            relay = create_relay(upstream, initialized)
            async with mcp_session(relay) as (_, proxy_init):
                assert proxy_init.capabilities.resources is None
                assert proxy_init.capabilities.prompts is None
                assert proxy_init.capabilities.tools is None

    anyio.run(run)
