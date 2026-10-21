# Releases and downloads

awx-mcp uses its own stable SemVer line, starting at 1.0.0. The tested AWX
version, currently 24.6.1, is a separate compatibility statement. This guide
describes the automated release path, not evidence that a release already exists.

## Download a published version

Open the Releases page of the repository you intend to trust:

- Upstream: https://github.com/lycorp-jp/awx-mcp/releases
- For a fork, open that fork's own Releases page. A fork release does not publish
  an upstream image or MCP Registry entry.

Each successfully published GitHub Release contains the dated CHANGELOG section
as its body and these downloadable assets:

| Asset | Use |
| --- | --- |
| `awx_mcp-<version>-py3-none-any.whl` | Install the Python package without building awx-mcp locally |
| `awx_mcp-<version>.tar.gz` | Build/install from the source distribution |
| `release-notes.md` | Save the same notes displayed in the Release body |
| `SHA256SUMS` | Check the integrity of the attached assets |
| `server.json` | Upstream only, validated OCI manifest for MCP Registry publication |

These are Python distributions, not standalone executables. Python >= 3.10 and
package dependencies are required. Both local-server and client-proxy modes use
the same package.

Download all the listed assets into one directory and verify their checksums:

```bash
sha256sum --check SHA256SUMS
# macOS alternative:
shasum -a 256 --check SHA256SUMS
```

Run a downloaded wheel, using its actual path and version:

```bash
uvx --no-cache --from /absolute/path/awx_mcp-1.0.0-py3-none-any.whl awx-mcp --version
```

Use the same `--from` path in an MCP client's command arguments. Preserve its
existing `--remote <central-url>` and `ANSIBLE_TOKEN` configuration for proxy
mode, or `ANSIBLE_BASE_URL` and authentication for local stdio. The example
filename assumes that version has actually been published.

## Maintainer release procedure

1. Choose the next independent `MAJOR.MINOR.PATCH` version. Align
   `pyproject.toml`, the root package version in `uv.lock`, the Dockerfile's
   default `VERSION`, and `server.json` version and versioned image identifier.
2. Move changes from `Unreleased` into exactly one dated heading such as
   `## [1.0.0] - 2026-10-21`. Leave `Unreleased` empty. Review the notes because
   this exact section becomes the Release body. Keep historical entries.
3. Run the project checks in `CONTRIBUTING.md`, including 100% statement coverage.
   Preview validation without publishing anything, using the actual repository:

   ```bash
   uv run python scripts/prepare_release.py v1.0.0 \
     --repository lycorp-jp/awx-mcp --output-dir .release
   # In a fork, substitute its owner/repo, for example argon-kr/awx-mcp.
   ```

4. Commit and review the release cut, then merge it through the repository's
   normal review process. An authorized maintainer creates and pushes the exact
   `vMAJOR.MINOR.PATCH` tag on that reviewed commit. A branch push or PR merge
   alone does not publish a release.
5. Check the **Release** workflow and the resulting Releases page. Invalid tags,
   version mismatches, unfinished notes, test failures, coverage below 100% or
   package installation failures stop the build before GitHub Release creation.

The workflow uses the repository's `GITHUB_TOKEN`. Its GitHub Release job alone
gets `contents: write`. Forks may need Actions and repository policy to permit
this job. No PyPI token or new secret is needed for GitHub downloads.

The upstream build additionally validates its OCI identity and official MCP
Registry schema. The upstream image job publishes GHCR images, while the
GitHub Release job depends only on the validated package build. This means a
downloadable GitHub Release can succeed even if image publication fails.
MCP Registry publication waits for both the image and GitHub Release and uses
GitHub OIDC. Check each job before claiming an image or Registry entry exists.
Forks skip the upstream image, OCI schema and Registry publication jobs.

The pipeline does not bump versions, cut changelog sections, create tags or
update an internal mirror or a running central server. Those remain explicit
maintainer operations. It accepts stable tags only, without leading zeros or
prerelease/build suffixes. Tags are never overwritten by the workflow.
