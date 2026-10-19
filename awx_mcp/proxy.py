# SPDX-License-Identifier: Apache-2.0

"""Client proxy mode (``awx-mcp --remote <URL>``).

Runs no AWX-facing server. Instead it exposes a local stdio MCP server to the
user's MCP client and relays every request to a central awx-mcp over
streamable-http, injecting the user's own AWX token as an ``Authorization:
Bearer`` header. This gives the same UX as local mode (an ``awx-mcp`` command
plus an ``ANSIBLE_TOKEN`` env var) while all AWX access is attributed and logged
centrally.

This module deliberately never imports ``awx_mcp.server``: proxy users do not
set ``ANSIBLE_BASE_URL`` (the central server manages AWX access), and do not
need the local server or tool catalog. Outbound TLS settings
come from the shared, server-free :mod:`awx_mcp.tls_config`.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Any
from urllib.parse import urlparse

import anyio
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    GetPromptRequestParams,
    GetPromptResult,
    InitializeResult,
    InputRequiredResult,
    InputResponses,
    ListPromptsResult,
    ListResourcesResult,
    ListResourceTemplatesResult,
    ListToolsResult,
    PaginatedRequestParams,
    ReadResourceRequestParams,
    ReadResourceResult,
    TextContent,
)

from .settings import Settings, configure_settings, get_settings
from .tls_config import resolve_ssl_verify
from .usage import record_proxy_tool_call
from .utils import mask_secrets, package_version

logger = logging.getLogger("awx-mcp.proxy")

# Generous read timeout: a relayed tool call blocks until the central server
# finishes its AWX request (which itself allows a long read), so the proxy must
# not time out first.
_HTTP_TIMEOUT = httpx2.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)


def _first_error_text(content: list[Any]) -> str | None:
    """Return the first text block from an errored result, secret-masked.

    Used to enrich the usage record when the central server returns a normal
    ``is_error=True`` result (not an exception): the first ``TextContent.text`` is
    the human-readable error, so we mask any inline secret and log it as detail.
    """
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            return mask_secrets(text)
    return None


async def _relay_tool_call(
    upstream: ClientSession,
    name: str,
    arguments: dict,
    *,
    usage_user: str,
    central_host: str,
    input_responses: InputResponses | None = None,
    request_state: str | None = None,
) -> CallToolResult | InputRequiredResult:
    """Relay one tool call to the central server and record usage.

    Extracted from the ``on_call_tool`` handler so the error branches can be
    unit-tested with a mocked ``upstream``. Behaviour is unchanged: a normal
    result (including ``is_error=True``) is returned as-is; a transport failure is
    degraded into an ``is_error=True`` result instead of crashing the relay. Usage
    is recorded in ``finally`` (fire-and-forget). ``error_detail`` is pre-set to
    ``None`` so it is defined on the exception path where ``result`` is unbound.

    ``allow_input_required=True`` keeps a multi-round-trip answer relayable: the
    default makes the SDK raise on an ``InputRequiredResult``, which this
    function's ``except`` would then mislabel as "central awx-mcp unreachable".
    The proxy is a relay, so it must hand that result to its own client
    untouched — hence ``is_error`` is read with ``getattr`` (an
    ``InputRequiredResult`` carries no such field and counts as a success), and
    ``input_responses`` / ``request_state`` are forwarded so the client's retry
    leg reaches the central server with the state it minted.
    """
    start = time.monotonic()
    success = True
    captured: BaseException | None = None
    error_detail: str | None = None
    try:
        result = await upstream.call_tool(
            name,
            arguments,
            allow_input_required=True,
            input_responses=input_responses,
            request_state=request_state,
        )
        is_error = bool(getattr(result, "is_error", False))
        success = not is_error
        if is_error:
            error_detail = _first_error_text(getattr(result, "content", []))
        return result
    except Exception as exc:  # noqa: BLE001 — degrade, don't crash
        success = False
        captured = exc
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"central awx-mcp unreachable: {exc}",
                )
            ],
            is_error=True,
        )
    finally:
        record_proxy_tool_call(
            name,
            start,
            success,
            captured,
            user=usage_user,
            awx_host=central_host,
            params=arguments,
            error_detail=error_detail,
        )


def _create_proxy(
    upstream: ClientSession,
    initialized: InitializeResult,
    *,
    usage_user: str,
    central_host: str,
) -> Server:
    """Relay supported capabilities over the same authenticated upstream session.

    Return whole SDK results to preserve pagination, MIME, content and metadata.
    Resource/prompt failures propagate as JSON-RPC errors, never content strings.
    Subscriptions and change notifications are not advertised or relayed.
    """

    async def list_tools(
        _ctx: ServerRequestContext[Any, Any], params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        return await upstream.list_tools(params=params)

    async def call_tool(
        _ctx: ServerRequestContext[Any, Any], params: CallToolRequestParams
    ) -> CallToolResult | InputRequiredResult:
        return await _relay_tool_call(
            upstream,
            params.name,
            params.arguments or {},
            usage_user=usage_user,
            central_host=central_host,
            input_responses=params.input_responses,
            request_state=params.request_state,
        )

    async def list_resources(
        _ctx: ServerRequestContext[Any, Any], params: PaginatedRequestParams | None
    ) -> ListResourcesResult:
        return await upstream.list_resources(params=params)

    async def list_templates(
        _ctx: ServerRequestContext[Any, Any], params: PaginatedRequestParams | None
    ) -> ListResourceTemplatesResult:
        return await upstream.list_resource_templates(params=params)

    async def read_resource(
        _ctx: ServerRequestContext[Any, Any], params: ReadResourceRequestParams
    ) -> ReadResourceResult | InputRequiredResult:
        return await upstream.read_resource(
            params.uri,
            allow_input_required=True,
            input_responses=params.input_responses,
            request_state=params.request_state,
            meta=params.meta,
        )

    async def list_prompts(
        _ctx: ServerRequestContext[Any, Any], params: PaginatedRequestParams | None
    ) -> ListPromptsResult:
        return await upstream.list_prompts(params=params)

    async def get_prompt(
        _ctx: ServerRequestContext[Any, Any], params: GetPromptRequestParams
    ) -> GetPromptResult | InputRequiredResult:
        return await upstream.get_prompt(
            params.name,
            params.arguments,
            allow_input_required=True,
            input_responses=params.input_responses,
            request_state=params.request_state,
            meta=params.meta,
        )

    info, capabilities = initialized.server_info, initialized.capabilities
    return Server(
        "awx-mcp-proxy",
        version=package_version(),
        title=f"{info.title or info.name} (via proxy)",
        instructions=initialized.instructions,
        website_url=info.website_url,
        on_list_tools=list_tools if capabilities.tools is not None else None,
        on_call_tool=call_tool if capabilities.tools is not None else None,
        on_list_resources=list_resources
        if capabilities.resources is not None
        else None,
        on_list_resource_templates=(
            list_templates if capabilities.resources is not None else None
        ),
        on_read_resource=read_resource if capabilities.resources is not None else None,
        on_list_prompts=list_prompts if capabilities.prompts is not None else None,
        on_get_prompt=get_prompt if capabilities.prompts is not None else None,
    )


async def _run_proxy_async(url: str, token: str, ssl_verify: bool | str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    # A user may restrict their own session to read-only; the central server
    # enforces it per request. This can only tighten access.
    if get_settings().read_only:
        headers["X-AWX-Read-Only"] = "true"

    central_host = urlparse(url).hostname or "unknown"
    usage_user = get_settings().usage_user or "local"

    async with httpx2.AsyncClient(
        headers=headers, verify=ssl_verify, timeout=_HTTP_TIMEOUT
    ) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read_stream,
            write_stream,
        ):
            async with ClientSession(read_stream, write_stream) as upstream:
                init_result = await upstream.initialize()
                logger.info("Connected to central awx-mcp at %s", url)

                proxy = _create_proxy(
                    upstream,
                    init_result,
                    usage_user=usage_user,
                    central_host=central_host,
                )

                init_opts = proxy.create_initialization_options()
                async with stdio_server() as (stdio_read, stdio_write):
                    await proxy.run(stdio_read, stdio_write, init_opts)


def run_proxy(url: str, settings: Settings | None = None) -> None:
    """Run the stdio<->central relay until stdin closes.

    Reads the caller's token from ``ANSIBLE_TOKEN`` (PAT only — username/password
    cannot be forwarded as a Bearer header) and the outbound TLS-verify setting
    from ``ANSIBLE_SSL_VERIFY`` / ``ANSIBLE_CA_BUNDLE`` (verifying the connection
    to the central awx-mcp, not to AWX). Exits non-zero with a clear message on
    a fatal startup/connection error.
    """
    settings = settings or Settings.from_env(
        overrides={"remote_url": url, "transport": "proxy"}
    )
    try:
        settings.validate_startup()
        ssl_verify = resolve_ssl_verify(logger, url, settings)
    except ValueError as exc:
        sys.exit(str(exc))
    configure_settings(settings)
    from . import usage

    usage.configure()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    token = settings.token
    assert token is not None

    try:
        anyio.run(_run_proxy_async, url, token, ssl_verify)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001 — surface a clean fatal error
        logger.error("proxy to %s failed: %s", url, exc)
        sys.exit(f"awx-mcp --remote failed: {exc}")
