# Contributing

Thanks for your interest in contributing to awx-mcp.

## Dev Setup

Requires Python >= 3.10 and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/lycorp-jp/awx-mcp.git
cd awx-mcp
uv sync
```

Run tests:

```bash
uv run pytest
```

Run linter:

```bash
uv run ruff check .
uv run ruff format --check .
```

## Code Style

- Linting and formatting via `ruff`. Config is in `pyproject.toml`.
- Follow the patterns already in the codebase. Each domain module lives under `awx_mcp/tools/` and follows the same structure.
- Type hints are expected on all public functions.
- Keep tool functions focused. One tool, one operation.

## Submitting a PR

1. Fork the repo and create a branch from `main`.
2. Make your changes. Add or update tests as needed.
3. Run `pytest` and `ruff check .` locally. Both must pass.
4. Open a pull request against `main`. Describe what changed and why.

Keep PRs focused. One logical change per PR is easier to review and merge.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org):

```
feat: add support for workflow approval nodes
fix: handle pagination when listing large inventories
docs: update tool count in README
refactor: extract common pagination logic to helper
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

## Reporting Bugs

Open an issue on GitHub. Include:

- AWX version
- Python version
- What you ran and what you expected
- The full error output or traceback

Check existing issues first to avoid duplicates.

## Linting and Type Checking

Lint and format with `ruff` (config in `pyproject.toml`):

```bash
uv run ruff check .
uv run ruff format --check .
```

Both run in CI (the lint workflow) and must pass for a PR to merge.

Type checking uses `mypy`:

```bash
uv run mypy awx_mcp/
```

`mypy` runs as a CI step on every PR with `continue-on-error: true` — it
currently reports no issues, but is surfaced as a warning rather than a hard
gate so the build does not break on new type findings. Pinned dev tool versions
live in `pyproject.toml [dependency-groups] dev`.

### Type checking notes

The `[tool.mypy]` config is intentionally lenient (`no_implicit_optional = false`)
to accommodate the `name: str = None` implicit-Optional pattern used across the
tool function signatures. A future change may set `no_implicit_optional = true`
and promote the CI step from `continue-on-error: true` to a hard gate once the
codebase is comfortable under stricter settings.

## Code of Conduct

This project follows a [Code of Conduct](CODE_OF_CONDUCT.md) to foster fair and inclusive collaboration.
We expect all community members and contributors to adhere to it.
We believe that mutual respect and cooperation are essential in building a sustainable open source ecosystem.

## Developer Certificate of Origin (DCO)

All contributions must comply with the [Developer Certificate of Origin (DCO)](DCO.md). Please review it before contributing.

When making a commit, please include a DCO sign-off by using the following flag:

```
git commit -s -m "Commit message"
```

This will automatically add the Signed-off-by line to your commit message.
The [DCO workflow](.github/workflows/dco.yml) enforces this on every pull
request — commits without a `Signed-off-by` trailer fail the check. To fix an
existing branch: `git rebase --signoff origin/main && git push --force-with-lease`.

## Corporate Contributor License Agreement

If you are contributing on behalf of a company, organization, or institution, we require a signed Corporate Contributor License Agreement (CCLA).
This ensures that your employer or organization has authorized your contribution.
Contributions from corporate entities will only be accepted once the CCLA has been signed and submitted.

Please [contact us](mailto:dl_oss_dev@lycorp.co.jp) if you need the CCLA (Corporate Contributor License Agreement).
