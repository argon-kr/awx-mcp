# SPDX-License-Identifier: Apache-2.0

"""Regression tests for Form-mode credential elicitation.

Verifies that:
- ``result.action == "decline"`` short-circuits and does NOT POST to AWX.
- ``result.action == "cancel"`` short-circuits and does NOT POST to AWX.
- Invalid JSON in elicited inputs returns the validation error envelope BEFORE POST.
- ``result.action == "accept"`` with valid JSON proceeds to POST.

Strategy: Set ``AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT=true`` BEFORE importing the
gated tools. Use ``FakeContext`` and patch ``get_ansible_client`` at the
import site.
"""

import os

os.environ["AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT"] = "true"
os.environ.setdefault("ANSIBLE_BASE_URL", "https://test.example.com/")
os.environ.setdefault("ANSIBLE_TOKEN", "fake-test-token")

import asyncio  # noqa: E402
import json  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

from awx_mcp.tools.credentials import (  # noqa: E402
    create_credential,
    update_credential,
)
from awx_mcp.tools.users import create_user, update_user  # noqa: E402
from tests.conftest import (  # noqa: E402
    FakeContext,
    _FakeElicitData,
    _FakeElicitResult,
    fake_client_factory,
)


def _ctx(action: str, **kwargs) -> FakeContext:
    data = _FakeElicitData(**kwargs) if kwargs else None
    return FakeContext(_FakeElicitResult(action, data))


# ---------------------------------------------------------------------------
# Decline / Cancel paths must NOT POST to AWX
# ---------------------------------------------------------------------------


def test_create_credential_decline_short_circuits_no_POST():
    api = MagicMock()
    with patch(
        "awx_mcp.tools.credentials.get_ansible_client",
        new=fake_client_factory(api),
    ):
        result = asyncio.run(
            create_credential(
                name="x",
                credential_type_id=1,
                organization_id=1,
                ctx=_ctx("decline"),
            )
        )
    payload = json.loads(result)
    assert payload["status"] == "cancelled"
    api.request.assert_not_called()


def test_create_credential_cancel_short_circuits_no_POST():
    api = MagicMock()
    with patch(
        "awx_mcp.tools.credentials.get_ansible_client",
        new=fake_client_factory(api),
    ):
        result = asyncio.run(
            create_credential(
                name="x",
                credential_type_id=1,
                organization_id=1,
                ctx=_ctx("cancel"),
            )
        )
    payload = json.loads(result)
    assert payload["status"] == "cancelled"
    api.request.assert_not_called()


def test_create_user_decline_short_circuits_no_POST():
    api = MagicMock()
    with patch(
        "awx_mcp.tools.users.get_ansible_client",
        new=fake_client_factory(api),
    ):
        result = asyncio.run(
            create_user(
                username="alice",
                ctx=_ctx("decline"),
            )
        )
    payload = json.loads(result)
    assert payload["status"] == "cancelled"
    api.request.assert_not_called()


def test_create_user_cancel_short_circuits_no_POST():
    api = MagicMock()
    with patch(
        "awx_mcp.tools.users.get_ansible_client",
        new=fake_client_factory(api),
    ):
        result = asyncio.run(
            create_user(
                username="alice",
                ctx=_ctx("cancel"),
            )
        )
    payload = json.loads(result)
    assert payload["status"] == "cancelled"
    api.request.assert_not_called()


# ---------------------------------------------------------------------------
# Invalid JSON path returns error BEFORE POST
# ---------------------------------------------------------------------------


def test_create_credential_invalid_json_returns_error_before_POST():
    api = MagicMock()
    with patch(
        "awx_mcp.tools.credentials.get_ansible_client",
        new=fake_client_factory(api),
    ):
        result = asyncio.run(
            create_credential(
                name="x",
                credential_type_id=1,
                organization_id=1,
                ctx=_ctx("accept", inputs="not-valid-json{{"),
            )
        )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "inputs" in payload["message"]
    api.request.assert_not_called()


def test_update_credential_invalid_json_returns_error_before_PATCH():
    api = MagicMock()
    with patch(
        "awx_mcp.tools.credentials.get_ansible_client",
        new=fake_client_factory(api),
    ):
        result = asyncio.run(
            update_credential(
                credential_id=1,
                ctx=_ctx("accept", inputs="not-json{{"),
                update_inputs=True,
            )
        )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert "inputs" in payload["message"]
    api.request.assert_not_called()


# ---------------------------------------------------------------------------
# Accept paths DO POST
# ---------------------------------------------------------------------------


def test_create_credential_accept_with_valid_json_POSTs_to_AWX():
    api = MagicMock()
    api.request.return_value = {"id": 42, "name": "x"}
    with patch(
        "awx_mcp.tools.credentials.get_ansible_client",
        new=fake_client_factory(api),
    ):
        result = asyncio.run(
            create_credential(
                name="x",
                credential_type_id=1,
                organization_id=1,
                ctx=_ctx("accept", inputs='{"username":"admin","password":"s"}'),
            )
        )
    api.request.assert_called_once()
    method, endpoint = api.request.call_args.args[:2]
    assert method == "POST"
    assert endpoint == "/api/v2/credentials/"
    assert "id" in result


def test_create_user_accept_with_password_POSTs_to_AWX():
    api = MagicMock()
    api.request.return_value = {"id": 7, "username": "alice"}
    with patch(
        "awx_mcp.tools.users.get_ansible_client",
        new=fake_client_factory(api),
    ):
        result = asyncio.run(
            create_user(
                username="alice",
                ctx=_ctx("accept", password="s3cret"),
            )
        )
    api.request.assert_called_once()
    method, endpoint = api.request.call_args.args[:2]
    assert method == "POST"
    assert endpoint == "/api/v2/users/"
    assert "alice" in result


def test_update_user_password_decline_short_circuits():
    """When update_password=True and elicit returns decline, no PATCH."""
    api = MagicMock()
    with patch(
        "awx_mcp.tools.users.get_ansible_client",
        new=fake_client_factory(api),
    ):
        result = asyncio.run(
            update_user(
                user_id=1,
                ctx=_ctx("decline"),
                update_password=True,
            )
        )
    payload = json.loads(result)
    assert payload["status"] == "cancelled"
    api.request.assert_not_called()
