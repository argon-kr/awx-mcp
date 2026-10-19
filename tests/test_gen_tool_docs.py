# SPDX-License-Identifier: Apache-2.0
"""Generated docs must reflect registration and reject stale, read-only checks."""

import os
import subprocess
import sys
from pathlib import Path

import anyio
import pytest
from mcp.server.mcpserver import MCPServer

from awx_mcp import server
from awx_mcp.settings import Settings
from scripts.gen_tool_docs import READMES, load_catalog

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gen_tool_docs.py"


def fixture_docs(root):
    (root / "SECURITY.md").write_text("Security policy.\n")
    (root / "pyproject.toml").write_text('description = "fixture"\n')
    for name in ("README.md", "README.ko.md", "README.ja.md"):
        (root / name).write_text(
            "원문 before\n<!-- TOOL_TABLES:BEGIN -->\nstale\n"
            "<!-- TOOL_TABLES:END -->\n원문 after\n"
            "<!-- TOOLSET_SUMMARY:BEGIN -->\nstale\n"
            "<!-- TOOLSET_SUMMARY:END -->\n",
            encoding="utf-8",
        )


def run_generator(root, *args):
    driver = (
        "import runpy, socket, sys\n"
        "def deny_network(*args, **kwargs):\n"
        "    raise AssertionError('documentation generation attempted network')\n"
        "socket.socket.connect = deny_network\n"
        "sys.argv = sys.argv[1:]\n"
        "runpy.run_path(sys.argv[0], run_name='__main__')\n"
    )
    return subprocess.run(
        [sys.executable, "-c", driver, str(SCRIPT), "--root", str(root), *args],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "AWX_MCP_TOOLSETS": "invalid"},
        check=False,
    )


def test_stale_tables_check_is_non_mutating_and_generation_is_idempotent(tmp_path):
    fixture_docs(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = run_generator(tmp_path, "--check")
    assert result.returncode == 1, result.stderr
    assert "README.md" in result.stderr
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before

    result = run_generator(tmp_path)
    assert result.returncode == 0, result.stderr
    generated = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    readmes = [data for name, data in generated.items() if name.startswith("README")]
    assert all("원문 before" in data.decode() for data in readmes)
    assert all("원문 after" in data.decode() for data in readmes)
    assert run_generator(tmp_path, "--check").returncode == 0
    assert run_generator(tmp_path).returncode == 0
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == generated
    tables = [
        data.decode()
        .split("<!-- TOOL_TABLES:BEGIN -->")[1]
        .split("<!-- TOOL_TABLES:END -->")[0]
        for data in readmes
    ]
    assert len(set(tables)) == 1

    # A stale count in a generated toolset heading must fail even when every
    # README agrees. The check must compare the actual registered surface.
    catalog = load_catalog()
    toolset = catalog.toolsets[0]
    count = sum(tool.toolset == toolset for tool in catalog.tools)
    for name in READMES:
        path = tmp_path / name
        path.write_text(
            path.read_text().replace(
                f"### `{toolset}` ({count} tools",
                f"### `{toolset}` ({count + 1} tools",
            )
        )
    stale = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert run_generator(tmp_path, "--check").returncode == 1
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == stale


def test_counts_are_checked_against_registry_and_restore_without_rewriting_prose(
    tmp_path,
):
    fixture_docs(tmp_path)
    snippets = {
        "README.md": (
            "![MCP Tools](https://img.shields.io/badge/MCP_Tools-0-blue)\n"
            '    AWX_MCP["AWX MCP Server<br/>(awx-mcp)<br/>'
            '0 tools (0 default + 0 opt-in)"]\n'
            "A historical example mentioned 99 tools.\n"
            "Historical surface: 99 tools (95 default + 4 opt-in).\n"
        ),
        "README.ko.md": (
            '    AWX_MCP["AWX MCP Server<br/>(awx-mcp)<br/>'
            '0개 도구 (기본 0 + opt-in 0)"]\n'
        ),
        "README.ja.md": (
            '    AWX_MCP["AWX MCP Server<br/>(awx-mcp)<br/>'
            '0 ツール (デフォルト 0 + opt-in 0)"]\n'
        ),
    }
    for name, snippet in snippets.items():
        path = tmp_path / name
        path.write_text(snippet + path.read_text())
    (tmp_path / "SECURITY.md").write_text(
        "deployment registers 0 of 0 tools and exposes\n"
    )
    (tmp_path / "pyproject.toml").write_text(
        'description = "MCP server for AWX/Ansible Tower - '
        '0 tools (0 default + 0 opt-in) for REST API v2"\n'
    )
    assert run_generator(tmp_path).returncode == 0
    assert run_generator(tmp_path, "--check").returncode == 0
    catalog = load_catalog()
    total, default = catalog.total_count, catalog.default_count
    assert f"{default} of {total}" in (tmp_path / "SECURITY.md").read_text()
    assert (
        f"{total} tools ({default} default + {total - default} opt-in)"
        in (tmp_path / "pyproject.toml").read_text()
    )
    assert "0개 도구" not in (tmp_path / "README.ko.md").read_text()
    assert "0 ツール" not in (tmp_path / "README.ja.md").read_text()
    assert (
        "A historical example mentioned 99 tools."
        in (tmp_path / "README.md").read_text()
    )
    assert (
        "Historical surface: 99 tools (95 default + 4 opt-in)."
        in (tmp_path / "README.md").read_text()
    )

    mutations = {
        "README.md": (f"{total} tools (", f"{total + 1} tools ("),
        "SECURITY.md": (f"of {total} tools", f"of {total + 1} tools"),
        "pyproject.toml": (f"{total} tools (", f"{total + 1} tools ("),
    }
    for name, (current, stale) in mutations.items():
        path = tmp_path / name
        path.write_text(path.read_text().replace(current, stale))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert run_generator(tmp_path, "--check").returncode == 1
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


@pytest.mark.parametrize("missing", ["SECURITY.md", "pyproject.toml"])
def test_missing_count_document_is_an_error_without_partial_writes(tmp_path, missing):
    fixture_docs(tmp_path)
    (tmp_path / missing).unlink()
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = run_generator(tmp_path)
    assert result.returncode == 1
    assert missing in result.stderr
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_catalog_uses_real_schemas_default_gates_and_sorted_toolsets():
    from scripts.gen_tool_docs import load_catalog, render_tables

    catalog = load_catalog()
    default = MCPServer("doc-default-test")
    default_names = set(server.register_tools(default, Settings()))
    all_tools = MCPServer("doc-all-test")
    all_names = set(
        server.register_tools(all_tools, Settings(enable_credential_management=True))
    )
    schemas = {tool.name: tool for tool in anyio.run(all_tools.list_tools)}
    assert {tool.name for tool in catalog.tools} == all_names
    assert catalog.default_count == len(default_names)
    assert catalog.total_count == len(all_names)
    assert {tool.name for tool in catalog.tools if tool.opt_in} == {
        "create_credential",
        "update_credential",
        "create_user",
        "update_user",
    }
    for tool in catalog.tools:
        assert tool.input_schema == schemas[tool.name].input_schema
        assert tool.read_only == schemas[tool.name].annotations.read_only_hint
    ordering = [(tool.toolset, tool.name) for tool in catalog.tools]
    assert ordering == sorted(ordering)
    rendered = render_tables(catalog)
    assert "| `list_jobs` | Read |" in rendered
    assert "| `create_credential` | Write (opt-in) |" in rendered


@pytest.mark.parametrize(
    "doc, expected",
    [
        ("List jobs. More details follow.", "List jobs."),
        ("List jobs. optionally filter the list.", "List jobs."),
        (
            "Read alpha | beta\n values.\n\nArgs:\n x: ignored",
            "Read alpha \\| beta values.",
        ),
        (
            "Return data without a period\n\nArgs:\n x: ignored",
            "Return data without a period",
        ),
    ],
)
def test_summary_uses_first_sentence_and_escapes_markdown(doc, expected):
    from scripts.gen_tool_docs import summarize

    assert summarize(doc) == expected


def test_unknown_or_duplicate_markers_are_rejected_without_writes(tmp_path):
    fixture_docs(tmp_path)
    path = tmp_path / "README.ko.md"
    path.write_text(path.read_text().replace("<!-- TOOL_TABLES:END -->", ""))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = run_generator(tmp_path)
    assert result.returncode == 1
    assert "TOOL_TABLES" in result.stderr
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
