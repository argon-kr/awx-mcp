"""Extract one dated Keep a Changelog release section without link definitions."""

import argparse
import re
from datetime import date
from pathlib import Path

HEADING = re.compile(r"^## \[([^\]]+)\](?: - (\d{4}-\d{2}-\d{2}))?\s*$", re.MULTILINE)


def sections(text: str) -> list[tuple[str, str | None, str]]:
    headings = list(HEADING.finditer(text))
    return [
        (
            match[1],
            match[2],
            text[
                match.end() : headings[index + 1].start()
                if index + 1 < len(headings)
                else len(text)
            ],
        )
        for index, match in enumerate(headings)
    ]


def release_section(text: str, version: str) -> str:
    matches = [entry for entry in sections(text) if entry[0] == version]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one changelog section for {version}.")
    _, released, body = matches[0]
    if not released:
        raise ValueError(f"Changelog section {version} must have a release date.")
    date.fromisoformat(released)
    body = re.split(r"^\[[^\]]+\]:", body, maxsplit=1, flags=re.MULTILINE)[0].strip()
    if not any(line.strip() and not line.startswith("#") for line in body.splitlines()):
        raise ValueError(f"Changelog section {version} is empty.")
    return f"## [{version}] - {released}\n\n{body}\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    args = parser.parse_args()
    try:
        notes = release_section(args.changelog.read_text(), args.version)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Release preparation failed: {exc}\n")
    print(notes, end="")


if __name__ == "__main__":
    main()
