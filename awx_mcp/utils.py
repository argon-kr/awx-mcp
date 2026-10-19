# SPDX-License-Identifier: Apache-2.0

import json
import re
from typing import Any


def package_version() -> str:
    """Installed awx-mcp distribution version, or ``"unknown"`` from a raw tree."""
    try:
        from importlib.metadata import version

        return version("awx-mcp")
    except Exception:  # noqa: BLE001 — metadata absent in an uninstalled checkout
        return "unknown"


# --- Secret masking -----------------------------------------------------------
# Shared by the usage instrumentation and the API client so that bearer tokens /
# token=... / password=... never reach a log sink, the usage JSONL, an exception
# message propagated to the MCP client, or the diagnostic log.
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"Bearer\s+\S+", re.IGNORECASE), "Bearer ***"),
    (re.compile(r"(token[\"']?\s*[:=]\s*)\S+", re.IGNORECASE), r"\1***"),
    (re.compile(r"(password[\"']?\s*[:=]\s*)\S+", re.IGNORECASE), r"\1***"),
]


def mask_secrets(text: str) -> str:
    """Redact bearer tokens, token=... and password=... occurrences from text."""
    if not text:
        return text
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def to_json(obj: object) -> str:
    """Serialize a tool result compactly for the MCP text content block.

    Compact separators and no indentation: tool results go straight into the
    model's context, where pretty-printing whitespace is pure token cost.
    ``ensure_ascii=False`` keeps non-ASCII names (e.g. Korean/Japanese host or
    template names) readable instead of ``\\uXXXX`` escapes.
    """
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def validate_json_str(value: str, param_name: str) -> None:
    """Validate a JSON string parameter.

    Raises ``ValueError`` (surfaced to the client as an ``isError`` tool result
    by ``server._surface_tool_errors``) when ``value`` is not valid JSON.
    """
    parse_json_str(value, param_name)


def parse_json_str(value: str, param_name: str) -> Any:
    """Parse a JSON string parameter.

    Returns the parsed value. Raises ``ValueError`` naming ``param_name`` when
    ``value`` is not valid JSON, so the tool call fails with ``isError`` instead
    of returning an error-shaped payload that reads as success.
    """
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {param_name}: {exc.msg}") from exc
