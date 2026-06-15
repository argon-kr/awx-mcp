# SPDX-License-Identifier: Apache-2.0

"""AWX MCP Server - MCP server for Ansible Tower/AWX."""

import argparse

from . import tools  # noqa: F401
from .server import TRANSPORT, VALID_TRANSPORTS, logger, mcp


def main():
    """Entry point for the awx-mcp command.

    Transport defaults come from the AWX_MCP_TRANSPORT / AWX_MCP_HOST /
    AWX_MCP_PORT environment variables and can be overridden by CLI flags.
    """
    parser = argparse.ArgumentParser(
        prog="awx-mcp",
        description="MCP server for Ansible Tower/AWX.",
    )
    parser.add_argument(
        "--transport",
        choices=VALID_TRANSPORTS,
        default=TRANSPORT,
        help="Transport protocol (default: %(default)s, env: AWX_MCP_TRANSPORT).",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind host for sse/streamable-http (env: AWX_MCP_HOST).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port for sse/streamable-http (env: AWX_MCP_PORT, default 8000).",
    )
    args = parser.parse_args()

    if args.host is not None:
        mcp.settings.host = args.host
    if args.port is not None:
        mcp.settings.port = args.port

    if args.transport == "stdio":
        logger.info("Starting awx-mcp (transport=stdio)")
    else:
        logger.info(
            "Starting awx-mcp (transport=%s) on %s:%s",
            args.transport,
            mcp.settings.host,
            mcp.settings.port,
        )

    mcp.run(transport=args.transport)
