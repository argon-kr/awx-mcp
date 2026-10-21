# SPDX-License-Identifier: Apache-2.0
"""Configuration failures, cache races and defensive runtime contracts."""

import importlib
import logging
import subprocess
import sys
from contextlib import contextmanager

import pytest
import responses
from mcp.server.mcpserver import MCPServer

from awx_mcp import client, proxy, server, utils
from awx_mcp.settings import Settings, parse_toolsets
from awx_mcp.tools import groups
from tests.conftest import set_test_settings
from tests.subprocess_helpers import coverage_env


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"http_timeout_read": 0}, "AWX_HTTP_TIMEOUT_READ"),
        ({"log_backup_count": -1}, "AWX_MCP_LOG_BACKUP_COUNT"),
        ({"server_log_format": "xml"}, "AWX_MCP_SERVER_LOG_FORMAT"),
        ({"auth_mode": "shared"}, "auth_mode"),
        ({"transport": "udp"}, "transport"),
    ],
)
def test_invalid_explicit_settings_are_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Settings(**kwargs)


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"base_url": None, "token": "test"}, "ANSIBLE_BASE_URL"),
        ({"base_url": "https://awx.test", "token": None}, "Authentication is required"),
        ({"base_url": "ftp://awx.test", "token": "test"}, "HTTP or HTTPS"),
        (
            {"base_url": "https://user:pw@awx.test", "token": "test"},
            "embedded credentials",
        ),
        ({"remote_url": "https://central.test/mcp", "token": None}, "ANSIBLE_TOKEN"),
    ],
)
def test_startup_rejects_missing_auth_or_unsafe_urls(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Settings(**kwargs).validate_startup()


def test_all_toolsets_cannot_be_mixed_with_individual_names():
    with pytest.raises(ValueError, match="cannot be combined"):
        parse_toolsets("all,jobs")


def test_module_entrypoint_reports_version():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import runpy,sys;sys.argv=['awx-mcp','--version'];"
            "runpy.run_module('awx_mcp.__init__',run_name='__main__')",
        ],
        env=coverage_env({"PATH": "/usr/bin:/bin", "PYTHONPATH": "."}),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"awx-mcp {importlib.metadata.version('awx-mcp')}"


@responses.activate
def test_relative_endpoint_without_leading_slash_preserves_subpath():
    responses.get(
        "https://awx.test/controller/api/v2/ping/", json={"version": "24.6.1"}
    )
    with client.AnsibleClient("https://awx.test/controller", token="test") as api:
        assert api.request("GET", "api/v2/ping/") == {"version": "24.6.1"}


@responses.activate
def test_whitespace_only_success_response_returns_empty_response_envelope():
    responses.post("https://awx.test/api/v2/action/", body=" \n\t", status=200)
    with client.AnsibleClient("https://awx.test", token="test") as api:
        assert api.request("POST", "/api/v2/action/") == {
            "status": "success",
            "message": "Empty response",
        }


def test_direct_client_context_authenticates_before_use(monkeypatch):
    def mint(self):
        self.token = "minted-synthetic-token"
        return self.token

    monkeypatch.setattr(client.AnsibleClient, "get_token", mint)
    with client.AnsibleClient(
        "https://awx.test", username="alice", password="fake"
    ) as api:
        assert api.get_headers()["Authorization"] == "Bearer minted-synthetic-token"


@responses.activate
def test_token_minted_between_snapshot_and_mint_lock_is_reused(monkeypatch):
    set_test_settings(monkeypatch, token=None, username="alice", password="fake")
    monkeypatch.setattr(client, "_cached_token", None)
    entries = 0

    @contextmanager
    def interleaved_lock():
        nonlocal entries
        entries += 1
        if entries == 2:
            # A competing caller finished minting after our empty snapshot.
            monkeypatch.setattr(client, "_cached_token", "other-caller-token")
        yield

    # Each acquisition schedules the competing caller at the relevant boundary.
    class Lock:
        def __enter__(self):
            self.context = interleaved_lock()
            return self.context.__enter__()

        def __exit__(self, *args):
            return self.context.__exit__(*args)

    monkeypatch.setattr(client, "_token_cache_lock", Lock())
    responses.get("https://test.example.com/api/v2/ping/", json={"ok": True})
    with client.get_ansible_client() as api:
        assert api.request("GET", "/api/v2/ping/") == {"ok": True}
    assert (
        responses.calls[0].request.headers["Authorization"]
        == "Bearer other-caller-token"
    )
    assert len(responses.calls) == 1  # No authentication or preflight request.


def test_reconfiguration_replaces_and_closes_old_diagnostic_file(tmp_path):
    root = logging.getLogger()
    old_level = root.level
    old_formatters = [(handler, handler.formatter) for handler in root.handlers]
    try:
        first = tmp_path / "first.log"
        second = tmp_path / "second.log"
        server.configure(
            Settings(
                base_url="https://awx.test", token="test", server_log_file=str(first)
            )
        )
        first_handler = server._server_log_handler
        server.logger.warning("first-configuration")
        server.configure(
            Settings(
                base_url="https://awx.test", token="test", server_log_file=str(second)
            )
        )
        server.logger.warning("second-configuration")
        assert first_handler.stream is None
        assert "first-configuration" in first.read_text()
        assert "second-configuration" not in first.read_text()
        assert "second-configuration" in second.read_text()
    finally:
        server.configure(Settings(base_url="https://awx.test", token="test"))
        root.setLevel(old_level)
        for handler, formatter in old_formatters:
            handler.setFormatter(formatter)


def test_header_lookup_failure_is_treated_as_missing_token():
    class BrokenHeaders:
        def get(self, name):
            raise RuntimeError("header unavailable")

    token = server._request_headers.set(BrokenHeaders())
    try:
        assert server.get_request_header("authorization") is None
    finally:
        server._request_headers.reset(token)


def test_tool_module_reload_replaces_owned_registration(monkeypatch):
    monkeypatch.setattr(server, "_REGISTRY", list(server._REGISTRY))
    importlib.reload(groups)
    target = MCPServer("reload-test")
    names = server.register_tools(target, Settings(toolsets=("groups",)))
    assert len(names) == len(set(names))
    specs = [s for s in server._REGISTRY if s.func.__name__ == "list_groups"]
    assert len(specs) == 1
    assert specs[0].func is groups.list_groups


def test_proxy_error_without_text_does_not_invent_error_detail():
    assert proxy._first_error_text([object()]) is None


def test_proxy_keyboard_interrupt_exits_cleanly(monkeypatch):
    def interrupted(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(proxy.anyio, "run", interrupted)
    proxy.run_proxy(
        "https://central.test/mcp",
        Settings(
            remote_url="https://central.test/mcp", token="test", transport="proxy"
        ),
    )


def test_package_version_metadata_failure_has_safe_fallback(monkeypatch):
    def unavailable(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", unavailable)
    assert utils.package_version() == "unknown"


def test_secret_masking_preserves_empty_message():
    assert utils.mask_secrets("") == ""
