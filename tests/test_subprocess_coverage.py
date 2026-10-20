# SPDX-License-Identifier: Apache-2.0
"""Prove an isolated startup probe contributes its execution to coverage."""

import os
import subprocess
import sys
from pathlib import Path

from coverage import CoverageData

ROOT = Path(__file__).resolve().parents[1]


def test_tls_subprocess_execution_is_recorded(tmp_path):
    # This driver imports no production module itself. server.py can only be
    # measured if our existing isolated TLS probe propagates instrumentation.
    driver = tmp_path / "driver.py"
    driver.write_text(
        "from tests.test_tls_server import _run\n"
        "result = _run({})\n"
        "assert result.returncode == 0, result.stderr\n"
        "assert result.stdout.strip() == 'null', result.stdout\n"
    )
    data_path = tmp_path / ".coverage"
    env = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": str(ROOT),
        "COVERAGE_FILE": str(data_path),
    }
    measured = subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "run",
            f"--rcfile={ROOT / 'pyproject.toml'}",
            "--source=awx_mcp",
            str(driver),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert measured.returncode == 0, measured.stdout + measured.stderr
    combined = subprocess.run(
        [sys.executable, "-m", "coverage", "combine"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert combined.returncode == 0, combined.stdout + combined.stderr
    data = CoverageData(basename=str(data_path))
    data.read()
    lines = data.lines(str(ROOT / "awx_mcp" / "server.py"))
    assert lines, "The isolated TLS probe ran, but its execution was not collected"
    # The child probe records only part of the package. A passing probe cannot
    # make this partial package coverage pass the configured 100% report gate.
    report = subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "report",
            f"--rcfile={ROOT / 'pyproject.toml'}",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert report.returncode == 2, report.stdout + report.stderr
    assert "fail-under=100.00" in report.stdout
