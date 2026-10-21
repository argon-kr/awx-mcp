"""Validate a tag against package, changelog and OCI metadata before publishing."""

import argparse
import json
import re
from pathlib import Path

from changelog_section import release_section, sections

REPOSITORY = "lycorp-jp/awx-mcp"


def prepare(root: Path, tag: str, repository: str) -> tuple[str, dict]:
    if repository != REPOSITORY:
        raise ValueError(
            "Publishing upstream identity is restricted to lycorp-jp/awx-mcp."
        )
    if not re.fullmatch(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", tag):
        raise ValueError(
            "Release tag must be stable SemVer vMAJOR.MINOR.PATCH "
            "with no leading zeros."
        )
    version = tag[1:]
    project = re.search(
        r"^\[project\]\s*\n(.*?)(?=^\[|\Z)",
        (root / "pyproject.toml").read_text(),
        re.MULTILINE | re.DOTALL,
    )
    package_version = re.search(
        r'^version\s*=\s*"([^"]+)"', project[1] if project else "", re.MULTILINE
    )
    if not package_version or package_version[1] != version:
        raise ValueError(f"Tag {tag} does not match pyproject.toml version.")
    changelog = (root / "CHANGELOG.md").read_text()
    entries = sections(changelog)
    released = [entry[0] for entry in entries if entry[0] != "Unreleased"]
    if not released or released[0] != version:
        raise ValueError("Tag must match the newest changelog release.")
    for name, _, body in entries:
        if name == "Unreleased":
            body = re.split(r"^\[[^\]]+\]:", body, maxsplit=1, flags=re.MULTILINE)[0]
            if any(
                line.strip() and not line.startswith("#") for line in body.splitlines()
            ):
                raise ValueError(
                    "Unreleased contains changes. Cut a dated release before tagging."
                )
    notes = release_section(changelog, version)
    manifest = json.loads((root / "server.json").read_text())
    if (
        manifest.get("version") != version
        or manifest.get("name") != "io.github.lycorp-jp/awx-mcp"
        or manifest.get("repository", {}).get("url")
        != f"https://github.com/{REPOSITORY}"
    ):
        raise ValueError(
            "server.json version or upstream identity does not match the release."
        )
    packages = manifest.get("packages", [])
    if len(packages) != 1 or packages[0].get("registryType") != "oci":
        raise ValueError("Only the GitHub Container Registry OCI package is supported.")
    if packages[0].get("identifier") != f"ghcr.io/{REPOSITORY}:{version}":
        raise ValueError("OCI image tag must exactly match the release version.")
    if packages[0].get("transport") != {"type": "stdio"}:
        raise ValueError("The OCI package must use stdio transport.")
    return notes, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        notes, manifest = prepare(args.root, args.tag, args.repository)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Release preparation failed: {exc}\n")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "release-notes.md").write_text(notes)
    (args.output_dir / "server.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Validated release {args.tag}.")


if __name__ == "__main__":
    main()
