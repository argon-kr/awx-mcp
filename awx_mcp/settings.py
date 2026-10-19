# SPDX-License-Identifier: Apache-2.0
"""Immutable configuration, parsed explicitly at process startup.

``ENV_VARS`` owns supported environment names, defaults and documentation.
Importing this module neither reads the environment nor validates AWX access.
CLI-only auth/transport choices deliberately have no environment mapping.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class EnvSpec:
    name: str
    field: str
    default: Any
    doc: str
    kind: str = "string"
    internal: bool = False


ENV_VARS: tuple[EnvSpec, ...] = (
    EnvSpec(
        "ANSIBLE_BASE_URL", "base_url", None, "AWX base URL. Bare hosts use HTTPS."
    ),
    EnvSpec("ANSIBLE_TOKEN", "token", None, "Personal access token."),
    EnvSpec("ANSIBLE_USERNAME", "username", None, "Username for local authentication."),
    EnvSpec("ANSIBLE_PASSWORD", "password", None, "Password for local authentication."),
    EnvSpec(
        "ANSIBLE_SSL_VERIFY",
        "ssl_verify",
        True,
        "Verify outbound TLS certificates.",
        "bool",
    ),
    EnvSpec(
        "ANSIBLE_CA_BUNDLE", "ca_bundle", None, "Custom CA bundle for outbound TLS."
    ),
    EnvSpec("ANSIBLE_LOG_LEVEL", "log_level", "INFO", "Diagnostic logging level."),
    EnvSpec(
        "AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT",
        "enable_credential_management",
        False,
        "Expose four sensitive credential/user write tools.",
        "bool",
    ),
    EnvSpec(
        "AWX_MCP_READ_ONLY",
        "read_only",
        False,
        "Expose only read tools, or restrict the proxy session.",
        "bool",
    ),
    EnvSpec(
        "AWX_MCP_TOOLSETS",
        "toolsets",
        None,
        "Comma-separated tool modules, or all.",
        "toolsets",
    ),
    EnvSpec("AWX_MCP_HOST", "host", "127.0.0.1", "Central server bind address."),
    EnvSpec("AWX_MCP_PORT", "port", 8000, "Central server bind port.", "int"),
    EnvSpec(
        "AWX_MCP_STATELESS_HTTP",
        "stateless_http",
        False,
        "Enable stateless streamable HTTP.",
        "bool",
    ),
    EnvSpec(
        "AWX_MCP_TLS_ENABLE",
        "tls_enable",
        False,
        "Enable inbound TLS for network transports.",
        "bool",
    ),
    EnvSpec("AWX_MCP_TLS_CERT", "tls_cert", None, "Inbound TLS certificate file."),
    EnvSpec("AWX_MCP_TLS_KEY", "tls_key", None, "Inbound TLS private key file."),
    EnvSpec(
        "AWX_MCP_TLS_KEY_PASSWORD",
        "tls_key_password",
        None,
        "Password for the inbound TLS key.",
    ),
    EnvSpec(
        "AWX_MCP_USAGE_LOG_FILE",
        "usage_log_file",
        None,
        "Optional JSONL tool usage log.",
    ),
    EnvSpec("AWX_MCP_USAGE_USER", "usage_user", None, "Proxy usage attribution label."),
    EnvSpec(
        "AWX_MCP_ACCESS_LOG_FILE",
        "access_log_file",
        None,
        "Optional JSONL HTTP access log.",
    ),
    EnvSpec(
        "AWX_MCP_SERVER_LOG_FILE",
        "server_log_file",
        None,
        "Optional diagnostic log file.",
    ),
    EnvSpec(
        "AWX_MCP_SERVER_LOG_FORMAT",
        "server_log_format",
        "plain",
        "Diagnostic file format: plain or json.",
    ),
    EnvSpec(
        "AWX_MCP_LOG_BACKUP_COUNT",
        "log_backup_count",
        7,
        "Number of daily log backups.",
        "backup_count",
    ),
    EnvSpec(
        "AWX_HTTP_TIMEOUT_READ",
        "http_timeout_read",
        90,
        "AWX HTTP read timeout in seconds.",
        "int",
    ),
    EnvSpec(
        "AWX_MCP_REMOTE_URL",
        "remote_url",
        None,
        "Central server URL for the stdio proxy.",
    ),
)

_DEFAULTS = {spec.field: spec.default for spec in ENV_VARS}


def parse_toolsets(value: str) -> tuple[str, ...] | None:
    """Parse an explicit selection without importing server/tool modules."""
    parts = tuple(part.strip() for part in value.split(","))
    if not all(parts):
        raise ValueError(
            "toolsets must contain non-empty comma-separated names or 'all'."
        )
    if parts == ("all",):
        return None
    if "all" in parts:
        raise ValueError("toolsets: 'all' cannot be combined with individual names.")
    return tuple(dict.fromkeys(parts))


def _parse(spec: EnvSpec, value: str) -> Any:
    if spec.kind == "bool":
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"", "0", "false", "no", "off"}:
            return False
        raise ValueError(f"{spec.name} must be true or false.")
    if spec.kind in {"int", "backup_count"}:
        try:
            return int(value)
        except ValueError as exc:
            if spec.kind == "backup_count":
                return spec.default
            raise ValueError(f"{spec.name} must be an integer.") from exc
    if spec.kind == "toolsets":
        return parse_toolsets(value)
    return value or None


@dataclass(frozen=True)
class Settings:
    base_url: str | None = _DEFAULTS["base_url"]
    token: str | None = field(default=_DEFAULTS["token"], repr=False)
    username: str | None = _DEFAULTS["username"]
    password: str | None = field(default=_DEFAULTS["password"], repr=False)
    ssl_verify: bool = _DEFAULTS["ssl_verify"]
    ca_bundle: str | None = _DEFAULTS["ca_bundle"]
    log_level: str = _DEFAULTS["log_level"]
    enable_credential_management: bool = _DEFAULTS["enable_credential_management"]
    read_only: bool = _DEFAULTS["read_only"]
    toolsets: tuple[str, ...] | None = _DEFAULTS["toolsets"]
    host: str = _DEFAULTS["host"]
    port: int = _DEFAULTS["port"]
    stateless_http: bool = _DEFAULTS["stateless_http"]
    tls_enable: bool = _DEFAULTS["tls_enable"]
    tls_cert: str | None = _DEFAULTS["tls_cert"]
    tls_key: str | None = _DEFAULTS["tls_key"]
    tls_key_password: str | None = field(
        default=_DEFAULTS["tls_key_password"], repr=False
    )
    usage_log_file: str | None = _DEFAULTS["usage_log_file"]
    usage_user: str | None = _DEFAULTS["usage_user"]
    access_log_file: str | None = _DEFAULTS["access_log_file"]
    server_log_file: str | None = _DEFAULTS["server_log_file"]
    server_log_format: str = _DEFAULTS["server_log_format"]
    log_backup_count: int = _DEFAULTS["log_backup_count"]
    http_timeout_read: int = _DEFAULTS["http_timeout_read"]
    remote_url: str | None = _DEFAULTS["remote_url"]
    auth_mode: str = "static"
    transport: str = "stdio"

    def __post_init__(self) -> None:
        if self.base_url and not urlparse(self.base_url).scheme:
            object.__setattr__(self, "base_url", "https://" + self.base_url)
        if not 1 <= self.port <= 65535:
            raise ValueError("AWX_MCP_PORT must be between 1 and 65535.")
        if self.http_timeout_read <= 0:
            raise ValueError("AWX_HTTP_TIMEOUT_READ must be positive.")
        if self.log_backup_count < 0:
            raise ValueError("AWX_MCP_LOG_BACKUP_COUNT must not be negative.")
        if self.server_log_format not in {"plain", "json"}:
            raise ValueError("AWX_MCP_SERVER_LOG_FORMAT must be plain or json.")
        if self.auth_mode not in {"static", "passthrough"}:
            raise ValueError("auth_mode must be static or passthrough.")
        if self.transport not in {"stdio", "sse", "streamable-http", "proxy"}:
            raise ValueError("Unknown transport.")

    @classmethod
    def from_env(
        cls,
        mapping: Mapping[str, str] | None = None,
        *,
        overrides: Mapping[str, Any] | None = None,
    ) -> Settings:
        """Parse a supplied mapping, or the process environment when omitted.

        Overrides use dataclass field names and typed values. They win before
        parsing, so a valid CLI override can replace an invalid env value.
        """
        env = os.environ if mapping is None else mapping
        if env.get("AWX_MCP_TRANSPORT"):
            raise ValueError(
                "AWX_MCP_TRANSPORT has been removed. Use 'awx-mcp --serve' "
                "(add --sse for SSE), or 'awx-mcp --stdio' for local mode."
            )
        values = dict(overrides or {})
        for spec in ENV_VARS:
            if spec.field not in values and spec.name in env:
                values[spec.field] = _parse(spec, env[spec.name])
        for key in ("log_level", "server_log_format"):
            if values.get(key):
                values[key] = (
                    values[key].upper() if key == "log_level" else values[key].lower()
                )
        return cls(**values)

    def validate_startup(self) -> None:
        """Validate credentials and URLs only for the selected running mode."""
        if self.remote_url:
            if not self.token:
                raise ValueError(
                    "ANSIBLE_TOKEN is required for --remote (proxy) mode. "
                    "ANSIBLE_USERNAME/PASSWORD are not supported."
                )
            _validate_url(self.remote_url, "AWX_MCP_REMOTE_URL")
            if self.toolsets is not None:
                raise ValueError(
                    "--toolsets/AWX_MCP_TOOLSETS is not supported with --remote. "
                    "Configure toolsets on the central --serve server."
                )
            return
        if not self.base_url:
            raise ValueError(
                "ANSIBLE_BASE_URL environment variable is required. Example: ANSIBLE_BASE_URL=https://awx.example.com/"
            )
        _validate_url(self.base_url, "ANSIBLE_BASE_URL")
        if (
            self.auth_mode == "static"
            and not self.token
            and not (self.username and self.password)
        ):
            raise ValueError(
                "Authentication is required. Set either ANSIBLE_TOKEN or both "
                "ANSIBLE_USERNAME and ANSIBLE_PASSWORD environment variables."
            )

    @property
    def outbound_verify(self) -> bool | str:
        """Resolved requests/httpx value. File validation happens at startup."""
        return (self.ca_bundle or True) if self.ssl_verify else False


def _validate_url(value: str, name: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{name} must be an HTTP or HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{name} must not contain embedded credentials.")


_settings = Settings()


def get_settings() -> Settings:
    """Return the immutable configuration installed at startup."""
    return _settings


def configure_settings(settings: Settings) -> None:
    """Install startup configuration before requests are accepted."""
    global _settings
    _settings = settings
