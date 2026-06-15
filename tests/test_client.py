# SPDX-License-Identifier: Apache-2.0

# pyright: reportAny=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnusedCallResult=false, reportAttributeAccessIssue=false, reportDeprecated=false

import builtins
import json
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANSIBLE_BASE_URL", "https://test.example.com/")
os.environ.setdefault("ANSIBLE_TOKEN", "test-token")

setattr(builtins, "Dict", dict)
setattr(builtins, "List", list)

from awx_mcp.client import (  # noqa: E402 — env vars must be set before module import
    AnsibleClient,
    handle_pagination,
)


def make_response(
    status_code=200,
    text='{"ok": true}',
    json_value=None,
    json_error=None,
    content_type="application/json",
):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.headers = {"Content-Type": content_type}
    if json_error is not None:
        response.json.side_effect = json_error
    else:
        response.json.return_value = (
            json_value if json_value is not None else {"ok": True}
        )
    return response


def test_handle_pagination_single_page_returns_all_results():
    client = MagicMock()
    client.request.return_value = {"results": [{"id": 1}, {"id": 2}], "next": None}

    result = handle_pagination(client, "/api/v2/items/", {})

    assert result == [{"id": 1}, {"id": 2}]
    client.request.assert_called_once_with(
        "GET", "/api/v2/items/", params={"page_size": 200}
    )


def test_handle_pagination_multi_page_collects_all_results():
    client = MagicMock()
    client.request.side_effect = [
        {"results": [{"id": 1}, {"id": 2}], "next": "/api/v2/items/?page=2"},
        {"results": [{"id": 3}], "next": None},
    ]

    result = handle_pagination(client, "/api/v2/items/", {})

    assert result == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert client.request.call_count == 2
    assert client.request.call_args_list[0].kwargs["params"] == {"page_size": 200}
    assert client.request.call_args_list[1].kwargs["params"] is None


def test_handle_pagination_limit_stops_collection_when_reached():
    client = MagicMock()
    client.request.return_value = {
        "results": [{"id": 1}, {"id": 2}, {"id": 3}],
        "next": "/api/v2/items/?page=2",
    }

    result = handle_pagination(client, "/api/v2/items/", {"limit": 2})

    assert result == [{"id": 1}, {"id": 2}]
    assert client.request.call_count == 1


def test_handle_pagination_offset_skips_items_and_respects_limit():
    client = MagicMock()
    client.request.side_effect = [
        {"results": [{"id": 1}, {"id": 2}, {"id": 3}], "next": "/api/v2/items/?page=2"},
        {"results": [{"id": 4}, {"id": 5}, {"id": 6}], "next": None},
    ]

    result = handle_pagination(client, "/api/v2/items/", {"offset": 2, "limit": 3})

    assert result == [{"id": 3}, {"id": 4}, {"id": 5}]
    assert client.request.call_args_list[0].kwargs["params"] == {
        "page_size": 3,
        "page": 1,
    }


def test_handle_pagination_without_results_key_wraps_response_in_list():
    client = MagicMock()
    payload = {"id": 7, "name": "single-object"}
    client.request.return_value = payload

    result = handle_pagination(client, "/api/v2/items/", {})

    assert result == [payload]


def test_handle_pagination_empty_results_returns_empty_list():
    client = MagicMock()
    client.request.return_value = {"results": [], "next": None}

    result = handle_pagination(client, "/api/v2/items/", {})

    assert result == []


@patch("awx_mcp.client.requests.Session")
def test_request_get_calls_session_request_correctly(mock_session_cls):
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.request.return_value = make_response(
        status_code=200, json_value={"ok": True}
    )
    client = AnsibleClient(base_url="https://test.example.com/", token="tkn")

    client.request("GET", "/api/v2/items/", params={"a": 1})

    from awx_mcp.client import DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT

    mock_session.request.assert_called_once_with(
        method="GET",
        url="https://test.example.com/api/v2/items/",
        headers={"Content-Type": "application/json", "Authorization": "Bearer tkn"},
        params={"a": 1},
        json=None,
        timeout=(DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT),
    )


@patch("awx_mcp.client.requests.Session")
def test_request_post_sends_json_data(mock_session_cls):
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.request.return_value = make_response(
        status_code=200, json_value={"id": 1}
    )
    client = AnsibleClient(base_url="https://test.example.com/", token="tkn")

    client.request("POST", "/api/v2/items/", data={"name": "x"})

    assert mock_session.request.call_args.kwargs["json"] == {"name": "x"}


@patch("awx_mcp.client.requests.Session")
def test_request_returns_parsed_json_for_200_responses(mock_session_cls):
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.request.return_value = make_response(
        status_code=200, json_value={"id": 99}
    )
    client = AnsibleClient(base_url="https://test.example.com/", token="tkn")

    result = client.request("GET", "/api/v2/items/99/")

    assert result == {"id": 99}


@patch("awx_mcp.client.requests.Session")
def test_request_returns_success_for_204_responses(mock_session_cls):
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.request.return_value = make_response(status_code=204, text="")
    client = AnsibleClient(base_url="https://test.example.com/", token="tkn")

    result = client.request("DELETE", "/api/v2/items/99/")

    assert result == {"status": "success"}


@patch("awx_mcp.client.requests.Session")
def test_request_raises_exception_for_error_status_codes(mock_session_cls):
    from awx_mcp.exceptions import AnsibleHTTPError

    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.request.return_value = make_response(
        status_code=500, text="server exploded"
    )
    client = AnsibleClient(base_url="https://test.example.com/", token="tkn")

    try:
        client.request("GET", "/api/v2/items/")
        raise AssertionError("Expected AnsibleHTTPError for 500 response")
    except AnsibleHTTPError as exc:
        assert "Ansible API error: 500" in str(exc)


@patch("awx_mcp.client.requests.Session")
def test_request_handles_non_json_responses(mock_session_cls):
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.request.return_value = make_response(
        status_code=200,
        text="plain text body",
        json_error=json.JSONDecodeError("Expecting value", "x", 0),
        content_type="text/plain",
    )
    client = AnsibleClient(base_url="https://test.example.com/", token="tkn")

    result = client.request("GET", "/api/v2/text/")

    assert result["status"] == "success"
    assert result["content_type"] == "text/plain"
    assert result["text"] == "plain text body"


@patch("awx_mcp.client.requests.Session")
def test_get_headers_includes_authorization_when_token_set(mock_session_cls):
    mock_session_cls.return_value = MagicMock()
    client = AnsibleClient(base_url="https://test.example.com/", token="abc")

    headers = client.get_headers()

    assert headers["Authorization"] == "Bearer abc"
    assert headers["Content-Type"] == "application/json"


@patch("awx_mcp.client.requests.Session")
def test_get_headers_omits_authorization_when_token_missing(mock_session_cls):
    mock_session_cls.return_value = MagicMock()
    client = AnsibleClient(base_url="https://test.example.com/")

    headers = client.get_headers()

    assert "Authorization" not in headers
    assert headers["Content-Type"] == "application/json"


def test_AnsibleAuthError_carries_status_code():
    from awx_mcp.exceptions import AnsibleAuthError

    err = AnsibleAuthError("denied", status_code=401)
    assert err.status_code == 401
    assert "denied" in str(err)


def test_exceptions_subclass_AnsibleAPIError():
    from awx_mcp.exceptions import (
        AnsibleAPIError,
        AnsibleAuthError,
        AnsibleHTTPError,
        AnsibleValidationError,
    )

    for cls in (AnsibleAuthError, AnsibleHTTPError, AnsibleValidationError):
        assert issubclass(cls, AnsibleAPIError)
        assert issubclass(cls, Exception)


@patch("awx_mcp.client.requests.Session")
def test_AnsibleAuthError_raised_on_401(mock_session_cls):
    from awx_mcp.exceptions import AnsibleAuthError

    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.request.return_value = make_response(
        status_code=401, text="unauthorized"
    )
    client = AnsibleClient(base_url="https://test.example.com/", token="tkn")
    try:
        client.request("GET", "/api/v2/items/")
        raise AssertionError("expected AnsibleAuthError")
    except AnsibleAuthError as e:
        assert e.status_code == 401


@patch("awx_mcp.client.requests.Session")
def test_AnsibleHTTPError_raised_on_5xx(mock_session_cls):
    from awx_mcp.exceptions import AnsibleHTTPError

    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.request.return_value = make_response(status_code=500, text="boom")
    client = AnsibleClient(base_url="https://test.example.com/", token="tkn")
    try:
        client.request("GET", "/api/v2/items/")
        raise AssertionError("expected AnsibleHTTPError")
    except AnsibleHTTPError as e:
        assert e.status_code == 500


@patch("awx_mcp.client.requests.Session")
def test_AnsibleValidationError_raised_on_400(mock_session_cls):
    from awx_mcp.exceptions import AnsibleValidationError

    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.request.return_value = make_response(status_code=400, text="invalid")
    client = AnsibleClient(base_url="https://test.example.com/", token="tkn")
    try:
        client.request("GET", "/api/v2/items/")
        raise AssertionError("expected AnsibleValidationError")
    except AnsibleValidationError as e:
        assert e.status_code == 400
