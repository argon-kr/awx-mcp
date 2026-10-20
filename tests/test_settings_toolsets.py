# SPDX-License-Identifier: Apache-2.0
"""Explicit startup settings and selective tool exposure contracts."""

import dataclasses
import subprocess
import sys

import anyio
import pytest
from mcp.server.mcpserver import MCPServer

from awx_mcp import server
from tests.subprocess_helpers import coverage_env


def test_imports_without_configuration_have_no_startup_side_effects():
    result = subprocess.run(
        [sys.executable, "-c", "import awx_mcp.server, awx_mcp.client; print('ok')"],
        env=coverage_env({"PATH": "/usr/bin:/bin", "PYTHONPATH": "."}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ok\n"


def test_settings_isolated_defaults_and_secret_repr(monkeypatch):
    from awx_mcp.settings import Settings

    monkeypatch.setenv("ANSIBLE_TOKEN", "ambient-secret")
    settings = Settings.from_env({})
    assert settings.token is None
    assert settings.ssl_verify is True
    assert settings.read_only is False
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.http_timeout_read == 90
    settings = Settings.from_env(
        {"ANSIBLE_TOKEN": "test-secret", "ANSIBLE_PASSWORD": "pw-secret"},
        overrides={"tls_key_password": "tls-secret"},
    )
    assert all(
        secret not in repr(settings)
        for secret in ("test-secret", "pw-secret", "tls-secret")
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        settings.port = 42


def test_settings_parses_env_and_explicit_overrides():
    from awx_mcp.settings import Settings

    settings = Settings.from_env(
        {
            "ANSIBLE_BASE_URL": "awx.example.test",
            "AWX_MCP_PORT": "9001",
            "AWX_MCP_READ_ONLY": "YES",
            "AWX_MCP_TOOLSETS": "jobs, hosts",
            "AWX_MCP_AUTH_MODE": "passthrough",
            "AWX_MCP_EFFECTIVE_TRANSPORT": "sse",
        },
        overrides={"port": 8123, "toolsets": ("inventories",)},
    )
    assert settings.base_url == "https://awx.example.test"
    assert settings.port == 8123
    assert settings.read_only is True
    assert settings.toolsets == ("inventories",)
    assert settings.auth_mode == "static"
    assert settings.transport == "stdio"


@pytest.mark.parametrize(
    "env,name",
    [
        ({"AWX_MCP_PORT": "no"}, "AWX_MCP_PORT"),
        ({"AWX_MCP_PORT": "-1"}, "AWX_MCP_PORT"),
        ({"AWX_HTTP_TIMEOUT_READ": "0"}, "AWX_HTTP_TIMEOUT_READ"),
        ({"ANSIBLE_SSL_VERIFY": "tru"}, "ANSIBLE_SSL_VERIFY"),
        ({"AWX_MCP_TOOLSETS": ""}, "toolsets"),
        ({"AWX_MCP_TOOLSETS": "jobs,"}, "toolsets"),
    ],
)
def test_invalid_settings_fail_clearly(env, name):
    from awx_mcp.settings import Settings

    with pytest.raises(ValueError, match=name):
        Settings.from_env(env)


def test_registry_collects_without_registering_and_reconfiguration_removes_tools():
    from awx_mcp.settings import Settings

    target = MCPServer("isolated")
    names = server.register_tools(target, Settings(toolsets=("jobs",)))
    assert "list_jobs" in names and "cancel_job" in names
    assert "list_hosts" not in names
    assert server.register_tools(target, Settings(toolsets=("jobs",))) == names
    assert [t.name for t in anyio.run(target.list_tools)] == names
    restricted = server.register_tools(
        target, Settings(toolsets=("hosts",), read_only=True)
    )
    assert "list_hosts" in restricted
    assert "create_host" not in restricted and "list_jobs" not in restricted
    assert [t.name for t in anyio.run(target.list_tools)] == restricted


@pytest.mark.parametrize("read_only", [False, True])
@pytest.mark.parametrize("credentials", [False, True])
def test_multiple_toolsets_preserve_read_only_and_sensitive_gates(
    read_only, credentials
):
    from awx_mcp.settings import Settings

    target = MCPServer("matrix")
    names = server.register_tools(
        target,
        Settings(
            toolsets=("credentials", "users"),
            read_only=read_only,
            enable_credential_management=credentials,
        ),
    )
    assert {"list_credentials", "get_user"} <= set(names)
    assert ("delete_user" in names) is (not read_only)
    assert ("create_credential" in names) is (credentials and not read_only)
    assert "list_jobs" not in names


@pytest.mark.parametrize("selection", [("missing",), ()])
def test_registry_rejects_unknown_or_empty_selection(selection):
    from awx_mcp.settings import Settings

    with pytest.raises(ValueError, match="toolset"):
        server.register_tools(MCPServer("invalid"), Settings(toolsets=selection))


@pytest.mark.parametrize(
    "argv,env,message",
    [
        (["--toolsets", "missing"], {}, "Unknown toolset"),
        (["--toolsets", ""], {}, "toolsets"),
        (
            ["--remote", "https://central.test/mcp", "--toolsets", "jobs"],
            {},
            "--remote",
        ),
        ([], {"AWX_MCP_TRANSPORT": "stdio"}, "--serve"),
    ],
)
def test_cli_rejects_invalid_config_with_exit_two(argv, env, message):
    result = subprocess.run(
        [sys.executable, "-m", "awx_mcp", *argv],
        env=coverage_env(
            {
                "PATH": "/usr/bin:/bin",
                "PYTHONPATH": ".",
                "ANSIBLE_BASE_URL": "https://awx.test",
                "ANSIBLE_TOKEN": "dummy",
                **env,
            }
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, result.stderr
    assert message in result.stderr


def test_cli_override_and_read_only_are_explicit_without_environment_writes(
    monkeypatch,
):
    import awx_mcp
    from awx_mcp.settings import get_settings

    monkeypatch.setenv("AWX_MCP_TOOLSETS", "invalid")
    monkeypatch.setenv("AWX_MCP_AUTH_MODE", "passthrough")
    monkeypatch.setenv("AWX_MCP_EFFECTIVE_TRANSPORT", "sse")
    monkeypatch.setattr(sys, "argv", ["awx-mcp", "--toolsets", "jobs", "--read-only"])
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: None)
    awx_mcp.main()
    settings = get_settings()
    assert settings.auth_mode == "static" and settings.transport == "stdio"
    assert settings.read_only is True and settings.toolsets == ("jobs",)
    import os

    assert os.environ["AWX_MCP_AUTH_MODE"] == "passthrough"
    assert os.environ["AWX_MCP_EFFECTIVE_TRANSPORT"] == "sse"
    names = [t.name for t in anyio.run(server.mcp.list_tools)]
    assert "list_jobs" in names and "cancel_job" not in names


def test_registry_metadata_and_wire_format_survive():
    from awx_mcp.settings import Settings

    target = MCPServer("metadata")
    server.register_tools(target, Settings(toolsets=("jobs",)))
    tools = anyio.run(target.list_tools)
    assert tools
    assert all(
        t.title and t.annotations.open_world_hint and t.output_schema is None
        for t in tools
    )


def test_all_toolsets_expose_default_and_opt_in_tool_counts():
    from awx_mcp.settings import Settings

    target = MCPServer("all")
    default = server.register_tools(target, Settings())
    all_names = server.register_tools(
        target, Settings(enable_credential_management=True)
    )
    assert len(default) == 141
    assert len(all_names) == 145
    assert set(all_names) - set(default) == {
        "create_credential",
        "update_credential",
        "create_user",
        "update_user",
    }


@pytest.mark.parametrize("sse", [False, True])
def test_serve_auth_and_transport_ignore_external_internal_variables(monkeypatch, sse):
    import uvicorn

    import awx_mcp
    from awx_mcp.settings import get_settings

    for key in ("ANSIBLE_TOKEN", "ANSIBLE_USERNAME", "ANSIBLE_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AWX_MCP_AUTH_MODE", "static")
    monkeypatch.setenv("AWX_MCP_EFFECTIVE_TRANSPORT", "stdio")
    monkeypatch.setenv("AWX_MCP_READ_ONLY", "true")
    monkeypatch.setenv("AWX_MCP_TOOLSETS", "jobs")
    argv = ["awx-mcp", "--serve"] + (["--sse"] if sse else [])
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    awx_mcp.main()
    settings = get_settings()
    assert settings.auth_mode == "passthrough"
    assert settings.transport == ("sse" if sse else "streamable-http")
    assert settings.read_only is True
    names = [tool.name for tool in anyio.run(server.mcp.list_tools)]
    assert "list_jobs" in names
    assert "cancel_job" not in names and "list_hosts" not in names


def test_passthrough_never_falls_back_to_static_credentials(monkeypatch):
    from awx_mcp import client
    from awx_mcp.exceptions import AnsibleAuthError
    from tests.conftest import set_test_settings

    set_test_settings(
        monkeypatch,
        auth_mode="passthrough",
        token="server-token",
        username="server-user",
        password="server-password",
    )
    monkeypatch.setattr(client, "get_request_token", lambda: None)
    with pytest.raises(AnsibleAuthError):
        with client.get_ansible_client():
            pytest.fail("missing caller token must never reach the tool body")
    monkeypatch.setattr(client, "get_request_token", lambda: "caller-token")
    with client.get_ansible_client() as actual:
        assert actual.token == "caller-token"
        assert actual.username is None and actual.password is None


@pytest.mark.parametrize("flag,env_read_only", [(True, "false"), (False, "true")])
@pytest.mark.parametrize(
    "ssl_verify,expected_verify", [(None, True), ("true", True), ("false", False)]
)
def test_proxy_cli_read_only_reaches_the_outbound_header(
    monkeypatch, flag, env_read_only, ssl_verify, expected_verify
):
    import awx_mcp
    from awx_mcp import proxy

    monkeypatch.delenv("ANSIBLE_BASE_URL", raising=False)
    monkeypatch.delenv("ANSIBLE_CA_BUNDLE", raising=False)
    monkeypatch.setenv("ANSIBLE_TOKEN", "fake-proxy-test-token")
    if ssl_verify is None:
        monkeypatch.delenv("ANSIBLE_SSL_VERIFY", raising=False)
    else:
        monkeypatch.setenv("ANSIBLE_SSL_VERIFY", ssl_verify)
    monkeypatch.setenv("AWX_MCP_READ_ONLY", env_read_only)
    argv = ["awx-mcp", "--remote", "https://central.test/mcp"]
    if flag:
        argv.append("--read-only")
    monkeypatch.setattr(sys, "argv", argv)
    captured = {}

    def stop_at_http_boundary(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("captured before network access")

    monkeypatch.setattr(proxy.httpx2, "AsyncClient", stop_at_http_boundary)
    with pytest.raises(SystemExit, match="captured before network"):
        awx_mcp.main()
    assert captured["headers"]["X-AWX-Read-Only"] == "true"
    assert captured["headers"]["Authorization"] == "Bearer fake-proxy-test-token"
    assert captured["verify"] is expected_verify


def test_reconfigure_uses_new_url_token_and_session():
    from awx_mcp import client
    from awx_mcp.settings import Settings

    server.configure(Settings(base_url="https://one.test", token="first-token"))
    with client.get_ansible_client() as first:
        first_session = first.session
        assert first.token == "first-token"
    server.configure(Settings(base_url="https://two.test", token="second-token"))
    with client.get_ansible_client() as second:
        assert second.token == "second-token"
        assert second.base_url == "https://two.test"
        assert second.session is not first_session


def test_importing_tool_modules_only_collects_specs():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import awx_mcp.tools; from awx_mcp import server; "
            "assert len(server._REGISTRY) == 145; "
            "assert not server.mcp._tool_manager.list_tools()",
        ],
        env=coverage_env({"PATH": "/usr/bin:/bin", "PYTHONPATH": "."}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("value", ["all", "jobs,jobs", " jobs , hosts "])
def test_toolset_all_and_normalized_selections(value):
    from awx_mcp.settings import Settings

    settings = Settings.from_env({"AWX_MCP_TOOLSETS": value})
    names = server.register_tools(MCPServer("normalized"), settings)
    assert "list_jobs" in names
    assert len(names) == len(set(names))
    if value == "all":
        assert "list_hosts" in names and "list_users" in names


def test_version_ignores_invalid_environment_without_loading_server():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, awx_mcp; sys.argv = ['awx-mcp', '--version']; "
            "\ntry: awx_mcp.main()"
            "\nfinally: assert 'awx_mcp.server' not in sys.modules",
        ],
        env=coverage_env(
            {
                "PATH": "/usr/bin:/bin",
                "PYTHONPATH": ".",
                "AWX_MCP_PORT": "invalid",
                "AWX_MCP_TRANSPORT": "retired",
            }
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("awx-mcp ")
