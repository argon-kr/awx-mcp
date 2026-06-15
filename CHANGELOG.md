# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com),
and this project adheres to [Semantic Versioning](https://semver.org).

## [Unreleased]

### Security
- The four credential/user write tools (`create_credential`, `update_credential`,
  `create_user`, `update_user`) are now opt-in via
  `AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT=true` (default: `false`). The default
  deployment registers 142 of 146 tools and exposes no tool that handles
  sensitive data.
- When the flag is enabled, the server logs a stderr warning noting that the
  gated tools use Form-mode elicitation, which is not spec-compliant for
  sensitive data per the MCP specification. See [SECURITY.md](SECURITY.md).
- `AWX_MCP_READ_ONLY=true` exposes only read tools (`list_*`/`get_*`); all
  write/destructive tools are unregistered at startup.

### Added
- Typed exception hierarchy (`AnsibleAPIError`, `AnsibleAuthError`,
  `AnsibleHTTPError`, `AnsibleValidationError`); error envelopes carry an
  `error_type` discriminator.
- HTTP request timeout (`connect=10s`, `read=90s`; override via
  `AWX_HTTP_TIMEOUT_READ`) and retry policy (3 retries, exponential backoff with
  jitter on 429/502/503/504, honors `Retry-After`, safe methods only).
- Cumulative pagination budget that returns a partial-results envelope when
  exceeded; zero-limit guard (`limit=0` returns `[]` without an HTTP call).
- Best-effort token revocation on shutdown (`atexit`) for tokens minted via
  username/password auth.

### Changed
- `ANSIBLE_BASE_URL` is accepted with or without a trailing slash.
- Concurrent token refresh is serialized with a lock to avoid minting duplicate
  tokens.

## [24.6.1]

### Changed
- Version scheme tracks the AWX upstream release
  (<https://github.com/ansible/awx/releases/tag/24.6.1>).
- License changed to Apache License 2.0.

### Added
- SPDX-License-Identifier headers on all source files.
- `CODE_OF_CONDUCT.md`, `DCO.md`, and `CONTRIBUTING.md`.

### Improved
- Tool docstrings enhanced with disambiguation cues, return hints, chaining
  guides, and destructive-operation warnings.

## [1.0.1]

### Fixed
- `create_job_template`: removed the deprecated `credential_id` parameter
  (AWX 24.x uses multi-credential M2M; use
  `associate_credential_with_template()` instead).

### Added
- `create_execution_environment` / `update_execution_environment`: added the
  `pull` parameter (`"always"`, `"missing"`, `"never"`).

## [1.0.0]

### Added
- Initial release: MCP tools for the AWX REST API v2 across 20 domain modules
  (inventories, hosts, groups, projects, job templates, jobs, credentials,
  organizations, teams, users, workflow templates, workflow jobs, schedules,
  execution environments, notifications, labels, RBAC, instances, system, and
  ad hoc commands).
- `AnsibleClient` with token caching and pagination support.
- Configurable SSL verification.
- Token and username/password authentication.
