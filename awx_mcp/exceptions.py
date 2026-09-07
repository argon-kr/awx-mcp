# SPDX-License-Identifier: Apache-2.0

"""Typed exception hierarchy for AWX/Tower API errors.

All API errors inherit from AnsibleAPIError. Tools let them propagate;
``awx_mcp.server._surface_tool_errors`` re-raises them as MCPServer's
``ToolError`` so the message reaches the model as an ``is_error`` result. (Since
mcp 2.1 any other exception type is masked to a bare ``Error executing tool
<name>``.) The subclass tells auth, validation and transport failures apart.
"""


class AnsibleAPIError(Exception):
    """Base class for all AWX/Tower API errors raised by AnsibleClient."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AnsibleAuthError(AnsibleAPIError):
    """Authentication or authorization failure (401, 403, CSRF/login failure)."""


class AnsibleHTTPError(AnsibleAPIError):
    """Non-auth HTTP error response (4xx other than 401/403, all 5xx)."""


class AnsibleValidationError(AnsibleAPIError):
    """400 Bad Request with field-level validation errors from AWX."""
