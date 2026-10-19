"""Release preparation must reject inconsistent or unfinished releases."""

import json
import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


def cli(*args, remote_url=None):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("ANSIBLE_", "AWX_"))
    }
    if remote_url:
        env["AWX_MCP_REMOTE_URL"] = remote_url
    return subprocess.run(
        [sys.executable, "-m", "awx_mcp", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )


def test_version_without_awx_configuration():
    result = cli("--version")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"awx-mcp {version('awx-mcp')}"
    assert not result.stderr


@pytest.mark.parametrize("mode", [[], ["--stdio"]])
def test_stdio_modes_initialize_and_list_tools(mode):
    async def connect():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "awx_mcp", *mode],
            cwd=str(ROOT),
            env={
                "ANSIBLE_BASE_URL": "https://awx.example.com/",
                "ANSIBLE_TOKEN": "fake-distribution-smoke-token",
            },
        )
        with anyio.fail_after(15):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    tools = await session.list_tools()
                    return initialized, tools

    initialized, tools = anyio.run(connect)
    assert initialized.server_info.name == "awx-mcp"
    assert initialized.server_info.version == version("awx-mcp")
    assert "list_inventories" in {tool.name for tool in tools.tools}


@pytest.mark.parametrize(
    "args, remote_url",
    [
        (("--stdio", "--serve"), None),
        (("--stdio", "--remote", "https://central.example/mcp"), None),
        (("--stdio",), "https://central.example/mcp"),
        (("--serve",), "https://central.example/mcp"),
    ],
)
def test_explicit_mode_conflicts_are_usage_errors(args, remote_url):
    result = cli(*args, remote_url=remote_url)
    assert result.returncode == 2
    assert "mutually exclusive" in result.stderr
    assert "ANSIBLE_BASE_URL" not in result.stderr


def release_fixture(tmp_path, version="1.0.0"):
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "awx-mcp"\nversion = "{version}"\n'
    )
    (tmp_path / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [Unreleased]\n\n## [{version}] - 2026-10-19\n\n"
        "### Added\n- Release improvements.\n\n"
        "## [24.6.1] - 2026-05-15\n\n- Historical release.\n\n"
        "[Unreleased]: https://example.com/compare\n"
    )
    manifest = {
        "name": "io.github.lycorp-jp/awx-mcp",
        "version": version,
        "repository": {
            "source": "github",
            "url": "https://github.com/lycorp-jp/awx-mcp",
        },
        "packages": [
            {
                "registryType": "oci",
                "identifier": f"ghcr.io/lycorp-jp/awx-mcp:{version}",
                "transport": {"type": "stdio"},
            }
        ],
    }
    (tmp_path / "server.json").write_text(json.dumps(manifest))
    return tmp_path


def prepare(root, tag="v1.0.0", repository="lycorp-jp/awx-mcp"):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/prepare_release.py"),
            tag,
            "--root",
            str(root),
            "--repository",
            repository,
            "--output-dir",
            str(root / "output"),
        ],
        text=True,
        capture_output=True,
        timeout=10,
    )


@pytest.mark.parametrize("version", ["0.1.0", "1.0.0", "1.2.3", "10.20.30"])
def test_prepare_semver_release_and_extract_only_its_notes(tmp_path, version):
    root = release_fixture(tmp_path, version)
    result = prepare(root, f"v{version}")
    assert result.returncode == 0, result.stderr
    notes = (root / "output/release-notes.md").read_text()
    assert "Release improvements." in notes
    assert "Historical release." not in notes
    assert "example.com/compare" not in notes
    assert json.loads((root / "output/server.json").read_text())["version"] == version


@pytest.mark.parametrize(
    "tag",
    ["v1.0.0.1", "v01.0.0", "v1.00.0", "v1.0.00", "v1.0", "v1.0.0-rc.1"],
)
def test_prepare_rejects_non_stable_semver_before_writing_output(tmp_path, tag):
    root = release_fixture(tmp_path, tag[1:])
    result = prepare(root, tag)
    assert result.returncode != 0
    assert "vMAJOR.MINOR.PATCH" in result.stderr
    assert not (root / "output").exists()


@pytest.mark.parametrize("mismatch", ["tag", "manifest", "image", "unreleased", "fork"])
def test_prepare_rejects_release_mismatch_before_writing_output(tmp_path, mismatch):
    root = release_fixture(tmp_path)
    tag = "v1.0.0"
    repository = "lycorp-jp/awx-mcp"
    if mismatch == "tag":
        tag = "v1.0.1"
    elif mismatch in ("manifest", "image"):
        manifest = json.loads((root / "server.json").read_text())
        if mismatch == "manifest":
            manifest["version"] = "24.6.1"
        else:
            manifest["packages"][0]["identifier"] = "ghcr.io/lycorp-jp/awx-mcp:latest"
        (root / "server.json").write_text(json.dumps(manifest))
    elif mismatch == "unreleased":
        changelog = (root / "CHANGELOG.md").read_text()
        (root / "CHANGELOG.md").write_text(
            changelog.replace("## [Unreleased]", "## [Unreleased]\n\n- Pending change.")
        )
    else:
        repository = "someone/awx-mcp"
    result = prepare(root, tag, repository)
    assert result.returncode != 0
    assert not (root / "output").exists()
    assert result.stderr.strip()


def test_changelog_extractor_rejects_missing_and_duplicate_versions(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    for text in (
        "## [Unreleased]\n\n- Pending change.\n",
        "## [24.6.1] - 2026-10-19\n- First.\n## [24.6.1] - 2026-10-20\n- Second.\n",
    ):
        changelog.write_text(text)
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/changelog_section.py"),
                "24.6.1",
                "--changelog",
                str(changelog),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        assert not result.stdout
