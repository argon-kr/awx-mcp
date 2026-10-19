# SPDX-License-Identifier: Apache-2.0

"""
Ansible MCP Server - Server Configuration

MCPServer instance, environment configuration, and logging setup.
"""

import contextvars
import json
import logging
import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import urllib3
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .exceptions import AnsibleAPIError
from .settings import Settings, configure_settings, get_settings
from .tls_config import resolve_ssl_verify
from .usage import instrument_tool, make_timed_rotating_handler
from .utils import package_version, truthy, wrap_tool_call

# --- Inbound request headers -------------------------------------------------
# Passthrough mode needs the caller's headers from deep inside a tool body
# (client.py builds the AWX auth from them, and the read-only gate checks
# X-AWX-Read-Only). mcp 1.x exposed a process-wide request context for this
# (`mcp.get_context().request_context.request`); mcp 2.x removed it and only
# hands the request to a `Context`-annotated tool parameter. Threading a `ctx`
# argument through all 145 tools is not viable, so the headers are captured once
# per inbound message by the middleware below and read back off a ContextVar.
_request_headers: contextvars.ContextVar[Mapping[str, str] | None] = (
    contextvars.ContextVar("awx_mcp_request_headers", default=None)
)


async def _capture_request_headers(
    ctx: ServerRequestContext[Any, Any], call_next: CallNext
) -> HandlerResult:
    """Publish the inbound request's headers for the duration of the message.

    Registered as MCPServer middleware, so it wraps every request/notification
    with the transport's HTTP request already attached. ``ctx.request`` is
    ``None`` on stdio (no headers), which leaves the ContextVar unset and
    ``get_request_header`` returning ``None`` — the same behaviour local mode had
    under mcp 1.x. The token is reset in ``finally`` so a header value can never
    leak into a later message handled on the same task.
    """
    request = getattr(ctx, "request", None)
    headers = getattr(request, "headers", None) if request is not None else None
    token = _request_headers.set(headers)
    try:
        return await call_next(ctx)
    finally:
        _request_headers.reset(token)


# Sent to the client in the initialize result. Clients surface it to the model
# before any tool call, so it carries the cross-cutting conventions that would
# otherwise be rediscovered (or missed) one tool description at a time.
SERVER_INSTRUCTIONS = """\
awx-mcp exposes the AWX (Ansible automation controller) REST API v2.

Conventions that apply to every tool:
- list_* tools return {"count", "returned", "offset", "results"}. `count` is the
  server-side total. When offset + returned < count, call again with
  offset = offset + returned. The default page size is 20.
- To turn a name into an ID, pass the list tool's name argument
  (e.g. list_job_templates(template_name=...)) instead of paging everything.
  It is a case-insensitive partial match, so check `count` for ambiguity.
- Before changing or deleting something, get_* it first and confirm with the
  user. Tools annotated destructive (delete_*, revoke_*, cancel_*) cannot be
  undone.
- launch_job / launch_workflow return immediately with a job ID. Poll get_job /
  get_workflow_job until `status` is successful, failed, error or canceled,
  then read get_job_stdout for the output.
- Errors from AWX (401/403/404/400) are returned verbatim. A 403 means the
  caller's AWX token lacks the role; do not retry it unchanged.
"""

# Initialize the MCP server. Unlike mcp 1.x FastMCP, MCPServer takes no
# host/port/stateless_http: those are per-transport and are passed at the
# sse_app()/streamable_http_app() call sites in __init__.main().
mcp = MCPServer(
    "awx-mcp",
    title="AWX MCP Server",
    version=package_version(),
    instructions=SERVER_INSTRUCTIONS,
    website_url="https://github.com/lycorp-jp/awx-mcp",
    middleware=[_capture_request_headers],
)

logger = logging.getLogger("ansible-mcp")
_PLAIN_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_server_log_handler: logging.Handler | None = None


class _JsonLogFormatter(logging.Formatter):
    """Render each diagnostic log record as a single JSON object (one per line)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "@timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "type": "diagnostic",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False)


def configure(settings: Settings) -> None:
    """Configure the process at startup, before accepting any requests.

    Repeating startup replaces owned log handlers and clears client/identity
    caches so a former configuration cannot leak credentials into the next one.
    Tool registration is explicit and separate via ``register_tools``.
    """
    global _server_log_handler
    settings.validate_startup()
    resolve_ssl_verify(logger, settings.base_url, settings)
    configure_settings(settings)
    from . import access_log, client, usage

    client.configure()
    usage.configure()
    access_log.configure()
    logging.basicConfig(level=settings.log_level, format=_PLAIN_LOG_FORMAT)
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    if _server_log_handler is not None:
        root.removeHandler(_server_log_handler)
        _server_log_handler.close()
        _server_log_handler = None
    serve = settings.transport in ("sse", "streamable-http")
    formatter = _JsonLogFormatter() if serve else logging.Formatter(_PLAIN_LOG_FORMAT)
    for handler in root.handlers:
        handler.setFormatter(formatter)
    if settings.server_log_file:
        _server_log_handler = make_timed_rotating_handler(settings.server_log_file)
        _server_log_handler.setFormatter(
            _JsonLogFormatter()
            if serve or settings.server_log_format == "json"
            else formatter
        )
        root.addHandler(_server_log_handler)
    if not settings.ssl_verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    if settings.base_url and urlparse(settings.base_url).scheme == "http":
        logger.warning(
            "ANSIBLE_BASE_URL uses http://: the AWX token and all traffic are "
            "sent unencrypted. Use https:// in production."
        )
    if settings.auth_mode == "passthrough" and (
        settings.token or settings.username or settings.password
    ):
        logger.warning(
            "AUTH_MODE=passthrough (--serve): server-side ANSIBLE_TOKEN / "
            "ANSIBLE_USERNAME / ANSIBLE_PASSWORD are ignored. Every AWX call "
            "uses the per-request caller token."
        )
    if settings.enable_credential_management:
        logger.warning(
            "AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT=true: sensitive credential/user "
            "write tools use Form-mode elicitation. Use only in trusted, "
            "isolated environments. See README.md#security."
        )
    if settings.read_only:
        logger.warning("AWX_MCP_READ_ONLY=true: only read tools are exposed.")


# Read-only compatibility aliases for existing embedders. Runtime consumers use
# get_settings(), never copied constants, so subsequent startup sees one source.
_ALIASES = {
    "ANSIBLE_BASE_URL": "base_url",
    "ANSIBLE_USERNAME": "username",
    "ANSIBLE_PASSWORD": "password",
    "ANSIBLE_TOKEN": "token",
    "ANSIBLE_SSL_VERIFY": "outbound_verify",
    "AUTH_MODE": "auth_mode",
    "READ_ONLY": "read_only",
    "ENABLE_CREDENTIAL_MANAGEMENT": "enable_credential_management",
    "MCP_HOST": "host",
    "MCP_PORT": "port",
    "STATELESS_HTTP": "stateless_http",
    "TLS_ENABLE": "tls_enable",
    "TLS_CERT": "tls_cert",
    "TLS_KEY": "tls_key",
    "TLS_KEY_PASSWORD": "tls_key_password",
    "SERVER_LOG_FILE": "server_log_file",
    "SERVER_LOG_FORMAT": "server_log_format",
}


def __getattr__(name: str) -> Any:
    if name in _ALIASES:
        return getattr(get_settings(), _ALIASES[name])
    raise AttributeError(name)


def resolve_tls_kwargs(
    transport: str, settings: Settings | None = None
) -> dict[str, str] | None:
    """Resolve uvicorn ``ssl_*`` kwargs for inbound TLS, or ``None`` when off.

    Returns ``None`` when TLS is disabled or when the transport is ``stdio``
    (which has no socket — a warning is logged if TLS was requested anyway).
    Raises ``ValueError`` when TLS is enabled for a network transport but the
    certificate/key are missing or point to non-existent files, so a
    misconfigured server fails fast at startup instead of silently serving
    plain HTTP.
    """
    settings = settings or get_settings()
    if not settings.tls_enable:
        return None
    if transport == "stdio":
        logger.warning(
            "AWX_MCP_TLS_ENABLE is set but transport=stdio has no network "
            "socket — TLS settings are ignored for stdio."
        )
        return None

    cert, key = settings.tls_cert, settings.tls_key
    missing = [
        name
        for name, value in (("AWX_MCP_TLS_CERT", cert), ("AWX_MCP_TLS_KEY", key))
        if not value
    ]
    if missing:
        raise ValueError(
            "AWX_MCP_TLS_ENABLE=true requires " + " and ".join(missing) + " to be set."
        )
    # After the missing check both are set; narrow str | None -> str for mypy.
    assert cert is not None and key is not None
    for name, path in (("AWX_MCP_TLS_CERT", cert), ("AWX_MCP_TLS_KEY", key)):
        if not os.path.isfile(path):
            raise ValueError(f"{name} points to a file that does not exist: {path}")

    kwargs: dict[str, str] = {"ssl_certfile": cert, "ssl_keyfile": key}
    if settings.tls_key_password:
        kwargs["ssl_keyfile_password"] = settings.tls_key_password
    return kwargs


def get_request_header(name: str) -> str | None:
    """Return an inbound request header (case-insensitive), or ``None``.

    Reads the Starlette headers published by ``_capture_request_headers`` for the
    message currently being handled. Returns ``None`` outside a request and on
    stdio (no HTTP request exists), and never raises — a header lookup must not
    be able to fail a tool.
    """
    headers = _request_headers.get()
    if headers is None:
        return None
    try:
        return headers.get(name)
    except Exception:  # noqa: BLE001 — header access must never fail a tool
        return None


def _request_is_read_only(settings: Settings | None = None) -> bool:
    """True when the current passthrough request opted into read-only mode.

    Only meaningful in passthrough mode: a caller may send
    ``X-AWX-Read-Only: true`` to restrict their own session to read tools. This
    can only tighten access (never loosen it) and is advisory self-restriction,
    not a security boundary — the real boundary is the caller's AWX token scope.
    """
    if (settings or get_settings()).auth_mode != "passthrough":
        return False
    return truthy(get_request_header("x-awx-read-only"))


def _read_only_gated(
    func: Callable[..., Any], settings: Settings | None = None
) -> Callable[..., Any]:
    """Wrap a write tool so a read-only caller's invocation is rejected.

    In static/local mode this is a no-op (the check short-circuits on
    ``AUTH_MODE``). In passthrough mode a request carrying a truthy
    ``X-AWX-Read-Only`` header is refused with a clear error before the tool
    body runs. Supports sync and async tools.
    """
    message = (
        f"'{func.__name__}' is a write operation and read-only mode is enabled "
        "for this session (X-AWX-Read-Only)."
    )

    @contextmanager
    def _gate(_kwargs: dict[str, Any]) -> Iterator[None]:
        if _request_is_read_only(settings):
            raise PermissionError(message)
        yield

    return wrap_tool_call(func, _gate)


# Failures a tool is *expected* to report to the caller: AWX API errors (401 /
# 403 / 400 / 5xx text from AWX), the per-request read-only gate, and argument
# validation. Everything else is a crash.
_ANTICIPATED_TOOL_ERRORS: tuple[type[BaseException], ...] = (
    AnsibleAPIError,
    PermissionError,
    ValueError,
)


def _surface_tool_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    """Re-raise anticipated failures as ``ToolError`` so their text reaches the model.

    Since mcp 2.1 (python-sdk #3314) MCPServer treats any exception other than
    ``ToolError`` as a crash: the client sees only ``Error executing tool <name>``
    and the traceback goes to the server log. That is right for a genuine bug,
    but an AWX 401/403/400 message, the read-only refusal or a bad-argument
    ``ValueError`` is *for* the model: it needs the text to fix the call or to
    tell the user. Wrapping those in ``ToolError`` keeps the message on the wire
    on both mcp 2.0 and 2.1 (identical ``Error executing tool <name>: <text>``).

    Sits outside ``instrument_tool`` so the usage log still records the original
    exception class; it stays reachable here as ``__cause__``. Supports sync and
    async tools.
    """

    @contextmanager
    def _surface(_kwargs: dict[str, Any]) -> Iterator[None]:
        try:
            yield
        except _ANTICIPATED_TOOL_ERRORS as exc:
            raise ToolError(str(exc)) from exc

    return wrap_tool_call(func, _surface)


# Acronyms kept upper-case in human-readable tool titles.
_TITLE_ACRONYMS = {"rbac": "RBAC", "scm": "SCM", "id": "ID", "ee": "EE"}


def tool_title(name: str) -> str:
    """Human-readable tool title: ``list_job_templates`` -> ``List job templates``.

    Clients show ``title`` in their tool pickers and approval prompts; the
    snake_case name stays the stable identifier the model calls.
    """
    words = [_TITLE_ACRONYMS.get(w, w) for w in name.split("_")]
    title = " ".join(words)
    return title[0].upper() + title[1:]


@dataclass(frozen=True)
class ToolSpec:
    func: Callable[..., Any]
    kind: str
    annotations: ToolAnnotations
    toolset: str


_REGISTRY: list[ToolSpec] = []


def _collect(
    func: Callable[..., Any], kind: str, annotations: ToolAnnotations
) -> Callable[..., Any]:
    spec = ToolSpec(func, kind, annotations, func.__module__.rsplit(".", 1)[-1])
    # Module reloads replace the existing specification without changing order.
    for index, previous in enumerate(_REGISTRY):
        if (previous.func.__module__, previous.func.__name__) == (
            func.__module__,
            func.__name__,
        ):
            _REGISTRY[index] = spec
            break
    else:
        _REGISTRY.append(spec)
    return func


def read_tool(func):
    """Collect a pure read/GET tool. Registration happens at startup."""
    return _collect(
        func, "read", ToolAnnotations(readOnlyHint=True, openWorldHint=True)
    )


def write_tool(*, destructive: bool = False, idempotent: bool = False):
    """Collect a write tool, preserving its safety annotations."""

    def deco(func):
        return _collect(
            func,
            "write",
            ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=destructive,
                idempotentHint=idempotent,
                openWorldHint=True,
            ),
        )

    return deco


def maybe_credential_management_tool(func):
    """Collect an opt-in sensitive credential/user write tool."""
    return _collect(
        func,
        "credential",
        ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )


def register_tools(target: MCPServer, settings: Settings) -> list[str]:
    """Expose the selected toolsets and gates, replacing previous registration.

    Tools are imported deterministically. Import errors propagate rather than
    silently omitting a module. User-registered unrelated tools are preserved.
    """
    from . import tools  # noqa: F401 - imports every module to collect specs

    available = {spec.toolset for spec in _REGISTRY}
    if settings.toolsets is not None:
        if not settings.toolsets:
            raise ValueError("toolsets selection must not be empty.")
        unknown = set(settings.toolsets) - available
        if unknown:
            raise ValueError(
                "Unknown toolset(s): "
                + ", ".join(sorted(unknown))
                + ". Available: "
                + ", ".join(sorted(available))
            )
    selected = [
        spec
        for spec in _REGISTRY
        if (settings.toolsets is None or spec.toolset in settings.toolsets)
        and (not settings.read_only or spec.kind == "read")
        and (settings.enable_credential_management or spec.kind != "credential")
    ]
    owned_names = {spec.func.__name__ for spec in _REGISTRY}
    for tool in list(target._tool_manager.list_tools()):
        if tool.name in owned_names:
            target.remove_tool(tool.name)
    for spec in selected:
        func = (
            spec.func if spec.kind == "read" else _read_only_gated(spec.func, settings)
        )
        target.tool(
            title=tool_title(spec.func.__name__),
            annotations=spec.annotations,
            structured_output=False,
        )(_surface_tool_errors(instrument_tool(func)))
    return [spec.func.__name__ for spec in selected]


def register_capabilities(target: MCPServer, settings: Settings) -> None:
    """Register the selected tools, read resources and instruction-only prompts."""
    from .prompts import register_prompts
    from .resources import register_resources

    register_tools(target, settings)
    register_resources(target, settings)
    register_prompts(target, settings)


def warn_if_exposed(host: str, tls_enabled: bool) -> None:
    """Warn when the network server binds a non-local address without TLS.

    Called from ``__init__.main()`` for ``--serve`` with the effective (post-CLI)
    host, so the warning reflects what the process actually binds. In passthrough
    mode the per-request AWX token travels in a header, so plaintext transport
    exposes credentials — hence the emphasis on TLS.
    """
    if host in ("127.0.0.1", "localhost", "::1"):
        return
    if not tls_enabled:
        logger.warning(
            "Central server bound to %s without in-process TLS. In passthrough "
            "mode the caller's AWX token travels in a request header — enable "
            "AWX_MCP_TLS_ENABLE (or front it with an authenticating TLS reverse "
            "proxy) so tokens are not sent in clear text.",
            host,
        )
    else:
        logger.info("Central server bound to %s (in-process TLS enabled).", host)
