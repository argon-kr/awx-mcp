#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check security links, registered tool docs/counts and supported env symbols.

CHANGELOG is intentionally excluded because its counts are historical.
The generator compares current docs against actual MCP registration, so
consistently stale counts across every document still fail this guard.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from awx_mcp.settings import ENV_VARS  # noqa: E402
from scripts.gen_tool_docs import READMES, generate  # noqa: E402

ENV_PATTERN = re.compile(r"`((?:AWX_MCP|AWX_HTTP|ANSIBLE)_[A-Z0-9_]*)`")


def check_parity(root: Path) -> list[str]:
    errors = []
    if not (root / "SECURITY.md").is_file():
        errors.append("MISSING: SECURITY.md does not exist")
    supported = {spec.name for spec in ENV_VARS}
    user_facing = {spec.name for spec in ENV_VARS if not spec.internal}
    for name in READMES:
        path = root / name
        if not path.is_file():
            errors.append(f"MISSING: {name} does not exist")
            continue
        content = path.read_text(encoding="utf-8")
        if "security.md" not in content.lower():
            errors.append(f"MISSING LINK: {name} does not reference SECURITY.md")
        documented = set(ENV_PATTERN.findall(content))
        missing, ghosts = (
            sorted(user_facing - documented),
            sorted(documented - supported),
        )
        if missing:
            errors.append(f"ENV VAR MISSING FROM README: {name} is missing {missing}")
        if ghosts:
            errors.append(
                f"ENV VAR GHOST IN README: {name} documents {ghosts} "
                "which the code never reads"
            )
    try:
        if generate(root, check=True):
            errors.append(
                "GENERATED DOCS STALE: run uv run python scripts/gen_tool_docs.py"
            )
    except (ValueError, OSError) as exc:
        errors.append(f"GENERATED DOCS INVALID: {exc}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    errors = check_parity(args.root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("OK: doc parity verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
