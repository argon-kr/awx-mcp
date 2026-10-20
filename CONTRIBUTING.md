# Contributing

Thanks for your interest in contributing to awx-mcp.

## Dev Setup

Requires Python >= 3.10 and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/lycorp-jp/awx-mcp.git
cd awx-mcp
uv sync --dev
```

Run tests:

```bash
uv run pytest tests/ --cov=awx_mcp --cov-fail-under=100
```

The required metric is **statement coverage for all of `awx_mcp/`**, including
isolated Python subprocesses. Coverage below 100% fails CI and release tests.
This is an execution metric, not a claim of complete branch coverage or proof
that every behavior is correct.

`pyproject.toml` enables coverage.py's subprocess instrumentation and SIGTERM
data saving. Subprocess tests that build a minimal environment must pass it
through `tests.subprocess_helpers.coverage_env`, which forwards only coverage
settings and keeps application credentials isolated. Always wait for child
processes to exit so pytest-cov can combine their records. No additional source
exclusions are used to reach the gate. Coverage.py's default exclusion of the
existing `@overload` type declarations remains in effect, as listed in the JSON
report's `excluded_lines`. All 35 source modules are measured.

CI uploads combined `coverage.xml` and `coverage.json` for each Python version
as `coverage-python-<version>` artifacts, retained for 14 days even on test
failure. The JSON report lists executed and missing lines per source file.
To generate the same records locally:

```bash
uv run pytest tests/ --cov=awx_mcp --cov-fail-under=100 \
  --cov-report=term-missing --cov-report=xml --cov-report=json
```

Run linter:

```bash
uv run ruff check .
uv run ruff format --check .
```

### Local pre-commit hooks

After `uv sync --dev`, install the repository hooks and run them once:

```bash
uvx pre-commit install
uvx pre-commit run --all-files
```

The local hooks run Ruff lint, Ruff format checking, mypy, and documentation
parity across the project with `uv run --locked`. Their tool versions come
from `pyproject.toml` and `uv.lock`, with no separate hook dependency pins.
Checks also run for documentation-only commits. They report stale generated
documentation instead of rewriting it. Run the generator explicitly when
needed, review the diff, and rerun the hooks. Tests and the coverage gate
remain part of the full CI checks below.

## Code Style

- Linting and formatting via `ruff`. Config is in `pyproject.toml`.
- Follow the patterns already in the codebase. Each domain module lives under `awx_mcp/tools/` and follows the same structure.
- Type hints are expected on all public functions.
- Keep tool functions focused. One tool, one operation.

## Adding a Tool

1. Add the function to the matching domain module under `awx_mcp/tools/`.
   Keep AWX endpoint selection, IDs, and client context in the domain module.
   `awx_mcp/tools/__init__.py` automatically discovers modules whose names do
   not start with `_`. The module basename becomes the toolset name for
   `--toolsets` and `AWX_MCP_TOOLSETS`.
2. Use `@read_tool` for read-only operations or `@write_tool(...)` for writes,
   with accurate `destructive` and `idempotent` annotations. These decorators
   collect tool specifications for explicit startup registration and enforce
   the read-only gate. Sensitive credential/user writes use
   `@maybe_credential_management_tool` and remain opt-in behind
   `AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT`. Follow `SECURITY.md` before adding
   any sensitive input handling. Add a typed signature and a docstring that
   explains when to use the tool, its parameters, and any destructive impact.
3. Reuse `awx_mcp/tools/_helpers.py` for compatible list, get, and delete
   operations and `drop_none(**fields)` for optional update fields. Preserve
   meaningful empty values, pagination envelopes, and existing JSON
   validation. Keep domain-specific operations in their modules.
4. Add endpoint-level tests with the real `AnsibleClient` and mocked HTTP
   responses. Assert the HTTP method, endpoint, query/body, returned content,
   and relevant validation or AWX error paths. Verify registration in the
   selected toolset and read-only/credential modes when applicable. Never
   use real AWX credentials or write to an AWX instance in unit tests.
5. Run `uv run python scripts/gen_tool_docs.py` and review all generated
   regions in the three READMEs and the tool reference. Update narrative
   translations outside generated regions when behavior changes. Run
   `uv run python scripts/check_doc_parity.py` to verify the result without
   changing files.
6. Add a user-visible entry under `## [Unreleased]` in `CHANGELOG.md` and run
   all checks in the next section before opening a PR.

## Submitting a PR

1. Fork the repo and create a branch from `main`.
2. Make your changes. Add or update tests as needed.
   After changing tools or their docstrings, run `uv run python scripts/gen_tool_docs.py`.
   This updates the generated tables in all three READMEs and current tool-count
   claims from actual MCP registration. Keep narrative translations outside the
   generated regions up to date. Tool summaries use the original English docstring.
3. Run the same checks CI runs. All must pass:
   ```bash
   uv lock --check
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy awx_mcp/
   uv run python scripts/check_doc_parity.py
   uv run pytest tests/ -v --cov=awx_mcp --cov-fail-under=100
   ```
4. Add a line under `## [Unreleased]` in `CHANGELOG.md` for any user-visible change.
5. Open a pull request against `main`. Describe what changed and why.

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

Open an issue with the **Bug report** form on GitHub (blank issues are
disabled so every report carries the details below). Include:

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

`mypy` is a hard CI gate (`no_implicit_optional = true`). Pinned dev tool
versions live in `pyproject.toml [dependency-groups] dev`.

### Type checking notes

Optional tool parameters must be spelled `x: str | None = None`, never the
implicit `x: str = None`. Besides failing mypy, the implicit form renders in
`tools/list` as a JSON Schema whose `"type": "string"` contradicts its
`"default": null`, which strict MCP clients reject. Ruff rule `RUF013` catches
it at lint time.

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
