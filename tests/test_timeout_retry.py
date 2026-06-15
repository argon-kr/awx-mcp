# SPDX-License-Identifier: Apache-2.0

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANSIBLE_BASE_URL", "https://test.example.com/")
os.environ.setdefault("ANSIBLE_TOKEN", "test-token")

import requests

from awx_mcp.client import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    AnsibleClient,
    handle_pagination,
)
from awx_mcp.exceptions import AnsibleHTTPError


def _resp(status=200, text='{"ok":true}', json_value=None):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.headers = {"Content-Type": "application/json"}
    r.json.return_value = json_value if json_value is not None else {"ok": True}
    return r


@patch("awx_mcp.client.requests.Session")
def test_default_timeout_applied(mock_session_cls):
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.request.return_value = _resp()
    client = AnsibleClient(base_url="https://test.example.com/", token="t")
    client.request("GET", "/api/v2/items/")
    kwargs = mock_session.request.call_args.kwargs
    assert kwargs["timeout"] == (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT)


@patch("awx_mcp.client.requests.Session")
def test_timeout_raises_AnsibleHTTPError(mock_session_cls):
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.request.side_effect = requests.exceptions.ConnectTimeout("slow")
    client = AnsibleClient(base_url="https://test.example.com/", token="t")
    try:
        client.request("GET", "/api/v2/items/")
        raise AssertionError("expected AnsibleHTTPError")
    except AnsibleHTTPError as e:
        assert "timeout" in str(e).lower()


@patch("awx_mcp.client.requests.Session")
def test_request_exception_wraps_to_AnsibleHTTPError(mock_session_cls):
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    mock_session.request.side_effect = requests.exceptions.ConnectionError("net")
    client = AnsibleClient(base_url="https://test.example.com/", token="t")
    try:
        client.request("GET", "/api/v2/items/")
        raise AssertionError("expected AnsibleHTTPError")
    except AnsibleHTTPError as e:
        assert "request error" in str(e).lower()


def test_env_override_AWX_HTTP_TIMEOUT_READ(monkeypatch):
    monkeypatch.setenv("AWX_HTTP_TIMEOUT_READ", "5")
    # reload to pick up env
    import importlib

    import awx_mcp.client as client_mod

    importlib.reload(client_mod)
    assert client_mod.DEFAULT_READ_TIMEOUT == 5
    # restore
    monkeypatch.setenv("AWX_HTTP_TIMEOUT_READ", "90")
    importlib.reload(client_mod)


def test_pagination_zero_limit_returns_empty():
    client = MagicMock()
    result = handle_pagination(client, "/api/v2/items/", {"limit": 0})
    assert result == []
    client.request.assert_not_called()


def test_pagination_cumulative_timeout_returns_partial_envelope(monkeypatch):
    """Simulate cumulative budget exhaustion by patching time.monotonic."""
    import awx_mcp.client as client_mod

    times = iter([0.0, 1.0, 1000.0, 2000.0])

    def fake_time():
        return next(times)

    monkeypatch.setattr(client_mod.time, "monotonic", fake_time)

    client = MagicMock()
    client.request.side_effect = [
        {"results": [{"id": 1}], "next": "/api/v2/items/?page=2"},
        {"results": [{"id": 2}], "next": "/api/v2/items/?page=3"},
    ]
    result = handle_pagination(client, "/api/v2/items/", {})
    assert len(result) == 1
    assert result[0]["error"] == "pagination_timeout"
    assert result[0]["partial"] is True
    assert result[0]["pages_fetched"] >= 1


def test_retry_adapter_mounted_for_https():
    client = AnsibleClient(base_url="https://test.example.com/", token="t")
    assert "https://" in client.session.adapters
    adapter = client.session.adapters["https://"]
    # Retry instance has total attribute
    assert adapter.max_retries.total == 3
    assert 502 in adapter.max_retries.status_forcelist
    assert 503 in adapter.max_retries.status_forcelist
    assert 504 in adapter.max_retries.status_forcelist
    assert 429 in adapter.max_retries.status_forcelist
