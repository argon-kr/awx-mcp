# SPDX-License-Identifier: Apache-2.0

"""
Ansible MCP Server - Server Configuration

FastMCP instance, environment configuration, and logging setup.
"""

import logging
import os

import urllib3
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

# Transport configuration
TRANSPORT = os.environ.get("AWX_MCP_TRANSPORT", "stdio").lower()
VALID_TRANSPORTS = ("stdio", "sse", "streamable-http")
if TRANSPORT not in VALID_TRANSPORTS:
    raise ValueError(
        f"Invalid AWX_MCP_TRANSPORT={TRANSPORT!r}. "
        f"Choose one of: {', '.join(VALID_TRANSPORTS)}."
    )
MCP_HOST = os.environ.get("AWX_MCP_HOST", "127.0.0.1")
try:
    MCP_PORT = int(os.environ.get("AWX_MCP_PORT", "8000"))
except ValueError as exc:
    raise ValueError("AWX_MCP_PORT must be an integer.") from exc

# Initialize FastMCP server (host/port apply to the sse and streamable-http
# transports; ignored for stdio)
mcp = FastMCP("ansible", host=MCP_HOST, port=MCP_PORT)

# Configuration
ANSIBLE_BASE_URL = os.environ.get("ANSIBLE_BASE_URL")
ANSIBLE_USERNAME = os.environ.get("ANSIBLE_USERNAME")
ANSIBLE_PASSWORD = os.environ.get("ANSIBLE_PASSWORD")
ANSIBLE_TOKEN = os.environ.get("ANSIBLE_TOKEN")
ANSIBLE_SSL_VERIFY = os.environ.get("ANSIBLE_SSL_VERIFY", "false").lower() in (
    "true",
    "1",
    "yes",
)
ENABLE_CREDENTIAL_MANAGEMENT = os.environ.get(
    "AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT", "false"
).lower() in ("true", "1", "yes")
READ_ONLY = os.environ.get("AWX_MCP_READ_ONLY", "false").lower() in (
    "true",
    "1",
    "yes",
)

# Validate required environment variables
if not ANSIBLE_BASE_URL:
    raise ValueError(
        "ANSIBLE_BASE_URL environment variable is required. "
        "Example: ANSIBLE_BASE_URL=https://awx.example.com/"
    )
if not ANSIBLE_TOKEN and not (ANSIBLE_USERNAME and ANSIBLE_PASSWORD):
    raise ValueError(
        "Authentication is required. Set either ANSIBLE_TOKEN or both "
        "ANSIBLE_USERNAME and ANSIBLE_PASSWORD environment variables."
    )

# Logging setup
logging.basicConfig(
    level=os.environ.get("ANSIBLE_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ansible-mcp")

# Suppress InsecureRequestWarning when SSL verification is disabled
if not ANSIBLE_SSL_VERIFY:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def read_tool(func):
    """Register a pure read/GET MCP tool.

    Always registered (read tools are exposed even in read-only mode) and
    annotated with ``readOnlyHint=True``.
    """
    return mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(func)


def write_tool(*, destructive: bool = False, idempotent: bool = False):
    """Register a write MCP tool unless AWX_MCP_READ_ONLY is enabled.

    When ``READ_ONLY`` is true the tool is left unregistered (returned as-is).
    Otherwise it is registered with annotations describing whether the write is
    destructive and/or idempotent.
    """

    def deco(func):
        if READ_ONLY:
            return func
        return mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=destructive,
                idempotentHint=idempotent,
            )
        )(func)

    return deco


def maybe_credential_management_tool(func):
    """Register an MCP tool only when AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT=true.

    Gates the four credential/user write tools (``create_credential``,
    ``update_credential``, ``create_user``, ``update_user``) that collect
    sensitive data via Form-mode elicitation. By default the flag is unset and
    these tools are not registered, so the shipped server exposes no tool that
    handles sensitive data.

    Sensitive credential/user writes are still writes, so they are also gated by
    ``READ_ONLY``: when read-only mode is enabled they are not registered even
    if credential management is enabled.
    """
    if ENABLE_CREDENTIAL_MANAGEMENT and not READ_ONLY:
        return mcp.tool(
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
            )
        )(func)
    return func


if ENABLE_CREDENTIAL_MANAGEMENT:
    logger.warning(
        "AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT=true detected. "
        "Credential/user write tools (create_credential, update_credential, "
        "create_user, update_user) are now exposed and use Form-mode elicitation, "
        "which is not spec-compliant for sensitive data per the MCP specification. "
        "Use only in trusted, isolated environments. "
        "See README.md#security for the threat model."
    )

if READ_ONLY:
    logger.warning(
        "AWX_MCP_READ_ONLY=true detected. All write/destructive tools are "
        "unregistered; only read tools are exposed."
    )

if TRANSPORT != "stdio" and MCP_HOST not in ("127.0.0.1", "localhost", "::1"):
    logger.warning(
        "AWX_MCP_TRANSPORT=%s is bound to %s:%s and reachable over the network. "
        "The server has no built-in authentication — place it behind an "
        "authenticating TLS reverse proxy and restrict access.",
        TRANSPORT,
        MCP_HOST,
        MCP_PORT,
    )
