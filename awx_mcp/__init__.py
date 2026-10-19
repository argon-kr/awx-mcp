# SPDX-License-Identifier: Apache-2.0

"""AWX MCP Server - MCP server for Ansible Tower/AWX."""

import argparse
import sys
from dataclasses import replace
from importlib.metadata import version


def main():
    """Entry point for the awx-mcp command.

    Three mutually exclusive running modes, selected by CLI flags:

    * ``--stdio`` (default) local stdio server using this process's own AWX
                         credentials (``ANSIBLE_TOKEN`` / USERNAME+PASSWORD).
    * ``--remote <URL>`` client proxy: no local server; relays stdio to a
                         central awx-mcp, injecting the caller's ``ANSIBLE_TOKEN``
                         as an ``Authorization: Bearer`` header.
    * ``--serve``        central multi-user server (streamable-http, or sse with
                         ``--sse``) that authenticates each request with the
                         caller's own token (passthrough).

    Heavy imports (``server``/``tools``/``proxy``) are deferred into the branch
    that needs them. Proxy mode does not import server or local tool modules.
    """
    parser = argparse.ArgumentParser(
        prog="awx-mcp",
        description="MCP server for Ansible Tower/AWX.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {version('awx-mcp')}"
    )
    parser.add_argument(
        "--stdio", action="store_true", help="Run the local stdio server (default)."
    )
    parser.add_argument(
        "--remote",
        metavar="URL",
        default=None,
        help=(
            "Client proxy mode: connect to a central awx-mcp at URL instead of "
            "running a local server (env: AWX_MCP_REMOTE_URL)."
        ),
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Run the central multi-user server (streamable-http; --sse for sse).",
    )
    parser.add_argument(
        "--sse",
        action="store_true",
        help="With --serve, serve the sse transport instead of streamable-http.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind host for --serve (env: AWX_MCP_HOST, default 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port for --serve (env: AWX_MCP_PORT, default 8000).",
    )
    parser.add_argument(
        "--toolsets",
        metavar="NAMES",
        default=None,
        help=(
            "Comma-separated toolsets, or all (env: AWX_MCP_TOOLSETS). "
            "Server-global with --serve."
        ),
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Restrict to read tools (also enabled by AWX_MCP_READ_ONLY).",
    )
    args = parser.parse_args()

    from .settings import Settings, parse_toolsets

    overrides = {}
    for field in ("host", "port"):
        if getattr(args, field) is not None:
            overrides[field] = getattr(args, field)
    if args.remote is not None:
        overrides["remote_url"] = args.remote
    try:
        if args.toolsets is not None:
            overrides["toolsets"] = parse_toolsets(args.toolsets)
        settings = Settings.from_env(overrides=overrides)
        settings = replace(settings, read_only=settings.read_only or args.read_only)
    except ValueError as exc:
        parser.error(str(exc))
    remote_url = settings.remote_url

    # --- Mutual exclusivity -------------------------------------------------
    if sum((args.stdio, args.serve, bool(remote_url))) > 1:
        parser.error(
            "--stdio, --serve and --remote/AWX_MCP_REMOTE_URL are mutually exclusive."
        )
    if remote_url and (args.serve or args.host or args.port is not None or args.sse):
        parser.error(
            "--remote runs no server; it cannot be combined with "
            "--serve/--host/--port/--sse."
        )
    if args.sse and not args.serve:
        parser.error("--sse is only valid together with --serve.")

    # --- Proxy mode ---------------------------------------------------------
    if remote_url:
        # Import only the proxy; never touch server (no ANSIBLE_BASE_URL here).
        from .proxy import run_proxy

        settings = replace(settings, transport="proxy")
        try:
            settings.validate_startup()
        except ValueError as exc:
            parser.error(str(exc))
        run_proxy(remote_url, settings)
        return

    # Mode and transport are explicit startup values, never environment IPC.
    transport = ("sse" if args.sse else "streamable-http") if args.serve else "stdio"
    settings = replace(
        settings,
        auth_mode="passthrough" if args.serve else "static",
        transport=transport,
    )
    from .access_log import AccessLogMiddleware
    from .server import (
        configure,
        logger,
        mcp,
        register_tools,
        resolve_tls_kwargs,
        warn_if_exposed,
    )

    try:
        settings.validate_startup()
        register_tools(mcp, settings)
        configure(settings)
        tls_kwargs = resolve_tls_kwargs(transport, settings)
    except ValueError as exc:
        parser.error(str(exc))

    if transport == "stdio":
        logger.info("Starting awx-mcp (local stdio server)")
        mcp.run(transport="stdio")
        return

    # Central server (--serve). Resolve the effective bind address (CLI flag wins
    # over the env default), then optionally serve over TLS. resolve_tls_kwargs
    # validates the cert/key and raises on misconfiguration. mcp 2.x takes the
    # bind host per transport at the app factory instead of on the server object,
    # so the resolved values are threaded through explicitly.
    host, port = settings.host, settings.port
    warn_if_exposed(host, tls_enabled=bool(tls_kwargs))
    logger.info(
        "Starting awx-mcp --serve (transport=%s, %s) on %s:%s",
        transport,
        "https" if tls_kwargs else "http",
        host,
        port,
    )

    # Drive uvicorn directly (MCPServer.run() cannot pass TLS options or wrap the
    # app in middleware). log_config=None routes uvicorn's own loggers through
    # the root logging config (JSON in --serve, see server.py); access_log=False
    # drops uvicorn's plain-text access lines — the JSON access log
    # (AccessLogMiddleware) is the access record.
    import uvicorn

    app = (
        mcp.sse_app(host=host)
        if transport == "sse"
        else mcp.streamable_http_app(host=host, stateless_http=settings.stateless_http)
    )
    app = AccessLogMiddleware(app)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_config=None,
        access_log=False,
        **(tls_kwargs or {}),
    )


if __name__ == "__main__":
    sys.exit(main())
