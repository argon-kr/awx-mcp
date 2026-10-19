# SPDX-License-Identifier: Apache-2.0
"""Parity must reject missing/ghost env symbols and stale generated tools."""

import subprocess
import sys
from pathlib import Path

from awx_mcp.settings import ENV_VARS
from scripts.gen_tool_docs import READMES, generate

ROOT = Path(__file__).resolve().parents[1]


def run_parity(root):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_doc_parity.py"),
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_parity_checks_generated_rows_env_registry_and_security_links(tmp_path):
    (tmp_path / "SECURITY.md").write_text("security\n")
    (tmp_path / "pyproject.toml").write_text('description = "fixture"\n')
    for name in READMES:
        (tmp_path / name).write_text(
            "SECURITY.md\n"
            + "\n".join(f"`{spec.name}`" for spec in ENV_VARS if not spec.internal)
            + "\n<!-- TOOL_TABLES:BEGIN -->\n<!-- TOOL_TABLES:END -->\n"
            + "<!-- TOOLSET_SUMMARY:BEGIN -->\n<!-- TOOLSET_SUMMARY:END -->\n"
        )
    generate(tmp_path)
    result = run_parity(tmp_path)
    assert result.returncode == 0, result.stderr

    path = tmp_path / "README.ko.md"
    path.write_text(path.read_text().replace("`AWX_MCP_TOOLSETS`", "`AWX_MCP_GHOST`"))
    path = tmp_path / "README.ja.md"
    path.write_text(path.read_text().replace("SECURITY.md", "unrelated.md"))
    path = tmp_path / "README.md"
    path.write_text(path.read_text().replace("| `list_jobs` |", "| `removed_jobs` |"))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = run_parity(tmp_path)
    assert result.returncode == 1
    assert "AWX_MCP_TOOLSETS" in result.stderr
    assert "AWX_MCP_GHOST" in result.stderr
    assert "MISSING LINK: README.ja.md" in result.stderr
    assert "STALE: README.md" in result.stderr
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
